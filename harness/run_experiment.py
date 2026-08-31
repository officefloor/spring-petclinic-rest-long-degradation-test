"""PetClinic-Evolve driver.

For each (arm, prompt-strategy, chain) it creates an isolated git worktree at the
arm's pre-feature base ref, then walks the ordered checkpoints. At each
checkpoint it:

  1. runs a FRESH headless agent with only the checkpoint spec (no carried
     context) and only THIS checkpoint's own acceptance test visible -- every prior
     test is hidden, so the agent has no checklist of earlier behaviour to preserve
     (SlopCodeBench's iterative-extension condition, made strict);
  2. commits the pure agent delta, then installs the full authored suite cp01..cpK
     (the priors the agent never saw) and gates on build + that suite -- so a change
     that silently broke earlier behaviour surfaces as a REAL regression;
  3. at phase boundaries, runs the read-only cold-reader probe;
  4. writes the checkpoint's RAW capture (agent envelope + event stream, the raw
     test-result map, the pre-normalisation agent diff, SHAs).

The run persists ONLY raw capture onto the evolve branches -- never any derived
number. Correctness scores and structural metrics (Erosion, Verbosity, hotspot,
blast radius, coupling, ...) ARE computed each checkpoint, but purely to narrate
progress in the log; analyze.py recomputes them from the commits + capture.

Usage:
  python -m harness.run_experiment --config config.yaml
  python -m harness.run_experiment --config config.yaml --arm spring --chain 0
  python -m harness.run_experiment --config config.yaml --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

import yaml

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from . import agent, capture, correctness, expand_path, impact_gate, metrics, parser_selftest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))


class ChainStopped(Exception):
    """Raised/flagged when the impact_gated pipeline gives up on a checkpoint: the
    change still fails ImpactGate after `max_refactors` refactors. The chain ends and
    is recorded as a clean-code failure (see run_chain / _impact_gated_implement)."""


def _confine_config(cfg: dict) -> dict | None:
    """Landlock confinement settings for the agent turn + probe, or None if
    disabled. `sentinels` are withheld paths that MUST be unreadable from inside
    the sandbox — the agent's fail-closed self-check refuses to run if any is
    still reachable, so the leak that exposed the CpNN suite via `find /` (harness
    acceptance/, checkpoints.yaml, prior runs in Trash) cannot silently recur."""
    ic = cfg.get("isolation", {}).get("agent_confinement", {})
    if not ic.get("enabled", False):
        return None
    sentinels = [p for p in (cfg.get("checkpoints_file"),
                             cfg.get("acceptance", {}).get("src_dir"),
                             HARNESS_DIR,
                             cfg.get("paths", {}).get("work_root")) if p]
    return {"enabled": True,
            "ro": list(ic.get("extra_ro_binds", [])),
            "rw": list(ic.get("extra_rw_binds", [])),
            "sentinels": sentinels}


CSV_FIELDS = [
    "run_id", "branch",
    "arm", "strategy", "chain", "checkpoint", "checkpoint_id", "phase",
    # process
    "agent_ok", "cost_usd", "input_tokens", "cache_read_tokens", "output_tokens",
    "num_turns", "duration_ms", "duration_api_ms",
    # correctness
    "build_ok", "total_selected", "strict_pass", "iso_pass", "core_pass",
    "core_p", "core_t", "error_p", "error_t", "func_p", "func_t",
    "regr_p", "regr_t", "regressions", "true_regressions", "checkpoint_type", "normalized_change",
    # structure (final numbers + the intermediates they are computed from)
    "erosion", "erosion_high_mass", "erosion_total_mass", "erosion_hot_fns",  # whole app
    "erosion_scoped", "erosion_scoped_high_mass", "erosion_scoped_total_mass", "subsystem_nfns",  # touched-file subsystem
    "erosion_handler", "erosion_handler_high_mass", "erosion_handler_total_mass",  # entry-handler class only
    "erosion_handler_hot_fns", "erosion_handler_class", "erosion_handler_nfns",
    "verbosity", "verbosity_clone_lines", "verbosity_pattern_lines", "verbosity_union_lines",
    "java_loc", "yaml_loc",
    "hotspot_nloc", "hotspot_cc", "hotspot_fn", "fn_count", "fn_nloc_avg", "fn_nloc_max", "fn_cc_max",
    "diff_added", "diff_removed", "files_touched",
    # blast radius: how much PRE-EXISTING code the rule disturbs vs. adds anew
    "existing_fns_modified", "files_modified", "files_created", "churn_added", "churn_removed",
    # god-class (WMC), entry-handler bloat, package reach, temporal coupling
    "wmc_max", "wmc_max_class", "wmc_max_methods", "wmc_max_nloc",
    "entry_cc", "entry_nloc", "entry_fn", "packages_touched",
    "reedit_body_lines", "reedit_prior_lines", "reedit_rate",
    # structural-impact score: context-weighted blast (max(WMC_other,1)·CC·max(1,Δlines)·files)
    "impact_mutation", "impact_godclass", "impact_composite",
    "impact_files_changed", "impact_new_files", "impact_new_fns", "impact_mut_fns", "impact_renames",
    # impact_gated pipeline (blank for ungated strategies): refactor count, verdict, the
    # accepted change's grade, and the refactor turns' cost/tokens (irreproducible)
    "ig_refactors", "ig_passed", "ig_stopped", "ig_grade",
    "ig_refactor_cost_usd", "ig_refactor_tokens",
    # probe (nullable)
    "probe_cost_usd", "probe_input_tokens", "probe_cache_read_tokens", "probe_recall",
    "pinned_touched",  # comma-separated pinned files the agent edited (blank = none)
    "acceptance_touched",  # acceptance test files the agent edited (restored; blank = none)
    "notes",
]

PHASES = ["Start", "Early", "Mid", "Late", "Final"]


def phase_for(idx: int, n: int) -> str:
    """Bin 1..n into five ordered phases (SlopCodeBench progress bins)."""
    b = min(4, int((idx - 1) / n * 5))
    return PHASES[b]


def git(args: list[str], check: bool = True) -> str:
    """Run git (the repo is passed via `-C <dir>` inside args) and return stripped
    stdout; raise on non-zero unless check=False."""
    proc = subprocess.run(["git"] + args, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def make_worktree(arm_cfg: dict, work_root: str, arm: str, strategy: str,
                  chain: int, run_id: str) -> tuple[str, str]:
    """Branch a fresh, run-tied line of history from the (untouched) base_ref.

    The base branch (e.g. spring-compare) is only ever READ as a start point; it
    is never checked out here and never has commits added to it. All checkpoint
    commits land on the new `evolve/<run_id>/<strategy>/<arm>/chain<n>` branch,
    which is kept after the run so reviewers can walk the progression.
    """
    repo = arm_cfg["repo"]
    base_ref = arm_cfg["base_ref"]
    branch = f"evolve/{run_id}/{strategy}/{arm}/chain{chain}"
    if branch == base_ref or not branch.startswith("evolve/"):
        raise RuntimeError(f"refusing to write to non-evolve branch {branch!r}")
    wt = os.path.join(work_root, run_id, f"{arm}-{strategy}-chain{chain}")

    # Idempotent re-run of the SAME run_id: clear only this run's worktree/branch.
    if os.path.isdir(wt):
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                       capture_output=True, text=True)
        shutil.rmtree(wt, ignore_errors=True)
    if subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", branch],
                      capture_output=True, text=True).returncode == 0:
        subprocess.run(["git", "-C", repo, "branch", "-D", branch], capture_output=True, text=True)

    os.makedirs(os.path.dirname(wt), exist_ok=True)
    git(["-C", repo, "worktree", "add", "-b", branch, wt, base_ref])
    return wt, branch


def build_prompt(strategy_template: str, spec: str) -> str:
    return strategy_template.replace("{spec}", spec)


def _seconds_until_reset(text: str) -> float | None:
    """Best-effort parse of a reset time like 'resets 6am (Australia/Perth)' into
    seconds from now. Returns None if it can't be parsed."""
    if not text or ZoneInfo is None:
        return None
    m = re.search(r"reset[s]?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?",
                  text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    try:
        tz = ZoneInfo(m.group(4)) if m.group(4) else None
    except Exception:
        tz = None
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds() + 60  # small buffer past the reset


def wait_for_window(ar, cfg: dict) -> float:
    """Sleep until the token window is expected to reopen, then return the number
    of seconds slept so the caller can record it. Uses the parsed reset time when
    available, else a poll interval; capped so a single wait can't run away."""
    limits = cfg.get("limits", {})
    secs = _seconds_until_reset(ar.result_text or ar.error)
    secs = secs if secs is not None else limits.get("poll_seconds", 1800)
    secs = max(60, min(secs, limits.get("max_sleep_seconds", 6 * 3600)))
    resume = datetime.now() + timedelta(seconds=secs)
    is_auth = agent.looks_like_auth((ar.error or "") + " " + (ar.result_text or ""))
    kind = "auth expired — re-login (`/login`) to resume" if is_auth else "token limit reached"
    print(f"    [limit] {kind} — waiting {int(secs)}s "
          f"(until ~{resume:%H:%M:%S}) then retrying the same checkpoint...", flush=True)
    time.sleep(secs)
    return secs


def wait_transient(attempt: int, ar, cfg: dict) -> float:
    """Short exponential backoff for a transient failure (network drop, API
    overload, no completion). Doubles each consecutive attempt up to a cap.
    Returns the seconds slept so the caller can record it."""
    limits = cfg.get("limits", {})
    base = limits.get("retry_backoff_seconds", 60)
    cap = limits.get("retry_backoff_max", 900)
    secs = min(base * (2 ** (attempt - 1)), cap)
    resume = datetime.now() + timedelta(seconds=secs)
    reason = (ar.error or ar.result_text or "").strip().splitlines()[0][:120] if (ar.error or ar.result_text) else "no completion"
    print(f"    [retry] transient failure (attempt {attempt}: {reason}) — waiting {int(secs)}s "
          f"(until ~{resume:%H:%M:%S}) then retrying the same checkpoint...", flush=True)
    time.sleep(secs)
    return secs


def _install_list(cp: dict) -> list[str]:
    """The acceptance-test source files a checkpoint installs. Defaults to its own
    `CpNNTests.java`. A checkpoint may instead declare `tests:` explicitly — used
    by a MUTATIVE checkpoint to ship its new test PLUS updated copies of the prior
    tests it changes (e.g. `["Cp08Tests.java", "cp08/Cp02Tests.java"]`). Each entry
    is a path under acceptance.src_dir; it installs to the worktree by basename, so
    `cp08/Cp02Tests.java` overwrites the running `Cp02Tests.java`."""
    tests = cp.get("tests")
    return list(tests) if tests else [f"Cp{cp['n']:02d}Tests.java"]


def _authored_set(cfg: dict, checkpoints: list[dict], k: int) -> dict[str, str]:
    """The CURRENT authored version of every acceptance test as of checkpoint k:
    a map of {installed basename -> source path under src_dir}. Walking the
    checkpoints in order, a later manifest entry for the same basename wins, so a
    mutative checkpoint's replacement becomes the authoritative version from then
    on. Shared infra (from acceptance.shared, installed at cp01) is included."""
    acc = cfg.get("acceptance") or {}
    authored: dict[str, str] = {os.path.basename(s): s for s in acc.get("shared", [])}
    for cp in checkpoints:
        if cp["n"] > k:
            break
        for entry in _install_list(cp):
            authored[os.path.basename(entry)] = entry
    return authored


_CPTEST_RE = re.compile(r"Cp\d+Tests\.java$")


def _own_test(cp: dict) -> str:
    """The checkpoint's OWN acceptance test class — the ONLY requirement test the
    agent may see while it works (never a mutative prior copy)."""
    return f"Cp{cp['n']:02d}Tests.java"


def _acc_dest(wt: str, cfg: dict) -> str | None:
    acc = cfg.get("acceptance")
    return os.path.join(wt, acc["dest_subpath"]) if acc else None


def _copy_authored(cfg: dict, entry: str, dest: str) -> str | None:
    """Copy an acceptance source file (path under src_dir) into dest by basename."""
    src = os.path.join(cfg["acceptance"]["src_dir"], entry)
    if os.path.isfile(src):
        os.makedirs(dest, exist_ok=True)
        base = os.path.basename(entry)
        shutil.copy2(src, os.path.join(dest, base))
        return base
    return None


def _view_entries(cfg: dict, cp: dict) -> list[str]:
    """Source entries the agent may see while working: shared infra + this
    checkpoint's own CpNNTests.java (never a mutative prior copy)."""
    acc = cfg.get("acceptance") or {}
    return list(acc.get("shared", [])) + [_own_test(cp)]


def set_agent_view(wt: str, cfg: dict, cp: dict) -> None:
    """Make the acceptance dir hold EXACTLY what the agent may see while it works:
    the shared infra plus THIS checkpoint's own CpNNTests.java. Every other
    requirement test — all priors, and any mutative prior copies — is removed.

    This is the crux of the regression measurement: the agent satisfies the current
    spec WITHOUT a checklist of prior tests to keep green, so a change that silently
    breaks earlier behaviour actually regresses (it is measured afterwards by
    install_measurement_suite). Installed by the previous checkpoint's reset commit,
    so each agent turn starts blind and its commit diff stays pure."""
    dest = _acc_dest(wt, cfg)
    if not dest:
        return
    entries = _view_entries(cfg, cp)
    keep = {os.path.basename(e) for e in entries}
    for entry in entries:
        _copy_authored(cfg, entry, dest)
    if os.path.isdir(dest):
        for fn in os.listdir(dest):
            if _CPTEST_RE.search(fn) and fn not in keep:
                os.remove(os.path.join(dest, fn))


def install_measurement_suite(wt: str, cfg: dict, checkpoints: list[dict], k: int) -> None:
    """Install the FULL authored suite (Cp01..CpK, with mutative-updated priors
    winning) for the post-agent regression gate. Overwrites the agent-view, so a
    tampered or weakened visible test cannot buy a false pass, and adds back every
    hidden prior so breakage on it surfaces as a regression."""
    dest = _acc_dest(wt, cfg)
    if not dest:
        return
    for entry in _authored_set(cfg, checkpoints, k).values():
        _copy_authored(cfg, entry, dest)


def scrub_test_artifacts(wt: str, cfg: dict) -> None:
    """Wipe the build output so the agent cannot infer the checkpoint SEQUENCE from
    it. The previous checkpoint's gate compiled and reported Cp01..Cp(k-1), leaving
    their compiled test classes and Surefire reports in target/; the agent runs with
    its cwd in the worktree and can read them (observed at cp60, where the agent
    enumerated the stale reports to deduce a sequence exists). Run `mvnw clean`, then
    remove target/ outright to be certain even if clean fails. target/ is gitignored,
    so this never affects a commit; the post-agent gate recompiles what it needs."""
    try:
        subprocess.run(["./mvnw", "-q", "-B", "clean"], cwd=wt,
                       capture_output=True, text=True,
                       timeout=(cfg.get("build") or {}).get("timeout", 1800))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass  # the rmtree below is the guaranteed backstop
    shutil.rmtree(os.path.join(wt, "target"), ignore_errors=True)


def mirror_source(src: str, dst: str, extra_excludes: tuple = ()) -> None:
    """Mirror `src` -> `dst` (an exact copy) of SOURCE files only: always exclude `.git`
    and `target/`, plus any `extra_excludes` (paths relative to the roots). Gives the
    agent a history-less sandbox -- no `.git` (can't `git log` the sequence), no
    `target/` (no prior build artifacts). `--delete` makes `dst` an exact mirror, so
    re-mirroring discards a failed attempt; mirroring the sandbox back onto the worktree
    propagates the agent's file deletions while the excludes preserve the worktree's own
    `.git`/`target/` and (via extra_excludes) its harness-managed acceptance tests."""
    os.makedirs(dst, exist_ok=True)
    # /evolve-results/ holds the committed per-checkpoint capture (test results, logs,
    # agent streams) — it must NEVER reach the sandbox (it would leak the whole checkpoint
    # sequence to the agent), and must be preserved on copy-back, so exclude it always.
    ex = (["--exclude=.git", "--exclude=/target/", "--exclude=/evolve-results/"]
          + [f"--exclude={e}" for e in extra_excludes])
    subprocess.run(["rsync", "-a", "--delete", *ex,
                    src.rstrip("/") + "/", dst.rstrip("/") + "/"],
                   check=True, capture_output=True, text=True)


# The single acceptance test the agent sees while working, renamed so NOTHING hints at a
# checkpoint number or a sequence: no CpNN in the filename or class, and no @Tag. (The
# test sources' comments are kept free of cpNN too, so the neutralized file has no leak.)
NEUTRAL_TEST = "AcceptanceTest.java"

# Testing modes (required --test-mode). They differ ONLY in what acceptance tests the
# agent SEES while it works. The post-agent gate always installs and runs the FULL authored
# cp01..cpK suite either way, so the correctness/regression measurement is identical across
# modes; the variable is the agent's test visibility, not how it is scored.
#   blind: the agent sees ONLY this checkpoint's own test, neutralised to AcceptanceTest.java
#          (no CpNN name, no @Tag). It cannot see prior tests or infer the sequence.
#   full:  the agent sees the FULL regression suite up to this checkpoint (cp01..cpK, with
#          real CpNN names), so it can run and preserve every accumulated rule as it works.
TEST_MODES = {
    "blind": "blind (single current test only; prior tests hidden)",
    "full":  "full regression suite (cp01..cpK visible to the agent)",
}


def _neutralize_test(text: str) -> str:
    """Rewrite a CpNNTests.java source so it carries no checkpoint-sequence hint: drop the
    `@Tag(...)` line and its `Tag` import, and rename `CpNNTests` -> `AcceptanceTest`
    EVERYWHERE (class decl, any constructor, any reference). Then a leak guard raises if
    any `@Tag` or `cp<digits>` token survives -- so a future test that leaks in an
    unforeseen way halts the run loudly instead of silently tipping off the agent."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("@Tag(") or s == "import org.junit.jupiter.api.Tag;":
            continue
        out.append(re.sub(r"\bCp\d+Tests\b", "AcceptanceTest", line))
    result = "\n".join(out) + "\n"
    leak = re.search(r"@Tag\b|\bcp\d+\b", result, re.IGNORECASE)
    if leak:
        raise RuntimeError(f"neutralized test still leaks a checkpoint hint: {leak.group(0)!r}")
    return result


def _neutral_test_text(cfg: dict, cp: dict) -> str:
    """The neutralized (AcceptanceTest) source for this checkpoint's own authored test."""
    src = os.path.join(cfg["acceptance"]["src_dir"], _own_test(cp))
    return _neutralize_test(open(src).read())


def _install_agent_view(acc: str, cfg: dict, cp: dict, checkpoints: list[dict]) -> None:
    """Populate a fresh acceptance dir with what the agent may SEE while it works, per
    `cfg['test_mode']`:
      blind: shared infra + this checkpoint's own test, neutralised to AcceptanceTest.java
             (no CpNN name, no @Tag) -- the agent cannot infer the sequence.
      full:  the full authored cp01..cpK suite (shared infra + every prior/current CpNNTests,
             mutative priors winning, real CpNN names) -- the agent sees the whole regression
             suite up to now."""
    shutil.rmtree(acc, ignore_errors=True)
    os.makedirs(acc, exist_ok=True)
    mode = cfg.get("test_mode")
    if mode == "blind":
        acc_src = cfg["acceptance"]["src_dir"]
        for s in cfg["acceptance"].get("shared", []):
            src = os.path.join(acc_src, s)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(acc, os.path.basename(s)))
        with open(os.path.join(acc, NEUTRAL_TEST), "w") as fh:
            fh.write(_neutral_test_text(cfg, cp))
    elif mode == "full":
        for entry in _authored_set(cfg, checkpoints, cp["n"]).values():
            _copy_authored(cfg, entry, acc)
    else:
        raise RuntimeError(f"unknown test_mode {mode!r}; pass --test-mode blind|full")


def _prepare_agent_sandbox(wt: str, sandbox: str, cfg: dict, cp: dict,
                           checkpoints: list[dict]) -> None:
    """Build the agent's history-less sandbox for one attempt: mirror the worktree source
    (production + pinned docs; no .git/target — the worktree carries no acceptance tests),
    then build a fresh acceptance dir holding the agent view for the active test_mode
    (`_install_agent_view`). No git history and no prior build output either way."""
    mirror_source(wt, sandbox)
    acc = os.path.join(sandbox, cfg["acceptance"]["dest_subpath"])
    _install_agent_view(acc, cfg, cp, checkpoints)


def detect_agent_tamper(wt: str, cfg: dict, cp: dict) -> list[str]:
    """Basenames among the agent-VISIBLE tests (shared + own CpNN) that the agent
    changed or deleted vs their authored source. Reported as acceptance_touched;
    the visible tests are restored to authored before the gate. Only the visible set
    is checked — the hidden priors are absent by design, not tampered."""
    dest = _acc_dest(wt, cfg)
    if not dest:
        return []
    acc = cfg["acceptance"]
    view = {os.path.basename(e): e for e in _view_entries(cfg, cp)}
    tampered = []
    for base, entry in view.items():
        src = os.path.join(acc["src_dir"], entry)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest, base)
        current = open(dst, "rb").read() if os.path.isfile(dst) else None
        if current != open(src, "rb").read():
            tampered.append(base)
    return tampered


def _detect_sandbox_tamper(acc_sandbox: str, cfg: dict, cp: dict,
                           checkpoints: list[dict]) -> list[str]:
    """Acceptance basenames the agent changed or deleted in the SANDBOX vs their authored
    source, matched to the active test_mode's visible set. Recorded as acceptance_touched;
    the gate reinstalls the authored suite afterwards, so tamper never buys a pass.
      blind: the one neutral AcceptanceTest.java vs the regenerated neutral source.
      full:  every visible cp01..cpK file (shared + CpNNTests) vs its authored source."""
    mode = cfg.get("test_mode")
    if mode == "blind":
        neutral_path = os.path.join(acc_sandbox, NEUTRAL_TEST)
        agent_test = open(neutral_path).read() if os.path.isfile(neutral_path) else ""
        return [] if agent_test == _neutral_test_text(cfg, cp) else [_own_test(cp)]
    if mode == "full":
        touched = []
        for entry in _authored_set(cfg, checkpoints, cp["n"]).values():
            base = os.path.basename(entry)
            src = os.path.join(cfg["acceptance"]["src_dir"], entry)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(acc_sandbox, base)
            current = open(dst, "rb").read() if os.path.isfile(dst) else None
            if current != open(src, "rb").read():
                touched.append(base)
        return touched
    raise RuntimeError(f"unknown test_mode {mode!r}; pass --test-mode blind|full")


def commit_run_manifest(wt: str, branch: str, run_id: str, arm: str, strategy: str,
                        chain: int, provenance: dict, snapshot: dict | None = None) -> None:
    """First commit on the evolve branch: the run's static manifest — `provenance.json`
    (everything known before the agent runs: run/model identity, harness SHA, tool and
    agent-environment versions) and a snapshot of the analysis-shaping config (`config/`).

    Written UP FRONT, not at the end, for two reasons: (1) an interrupted run stays
    self-describing — the config that shaped its checkpoints and the control it ran under
    travel with even a partial chain; (2) the control (tool/agent environment) is recorded
    as it was when the run began, before any drift over a multi-hour chain. The
    checkpoint->agent-SHA map is deliberately NOT here — it is derivable from the
    per-checkpoint capture records (which encode no-op turns as an empty sha), so `analyze`
    reads it from there and provenance never needs rewriting."""
    out_dir = os.path.join(wt, "evolve-results")
    os.makedirs(out_dir, exist_ok=True)
    capture.write_json(os.path.join(out_dir, "provenance.json"), provenance)
    if snapshot:
        capture.snapshot_config(snapshot.get("config"), snapshot.get("checkpoints"),
                                snapshot.get("astgrep_rules"), out_dir)
    subprocess.run(["git", "-C", wt, "add", "evolve-results"], capture_output=True, text=True)
    msg = f"manifest: {arm}/{strategy}/chain{chain} - run {run_id}"
    c = subprocess.run(["git", "-C", wt, "commit", "-m", msg, "--", "evolve-results"],
                       capture_output=True, text=True)
    print(f"  manifest commit on {branch}: "
          + ("ok" if c.returncode == 0 else (c.stdout.strip() or c.stderr.strip())[:120]))


def commit_chain_results(wt: str, branch: str, run_id: str, arm: str, strategy: str,
                         chain: int, cap_dir: str | None, headline: str = "") -> None:
    """Terminal 'results:' commit — the chain's completion marker. Provenance + config
    already landed in the manifest commit and each checkpoint's raw capture in its reset
    commit, so this normally adds nothing; it runs `assemble_into` as a backstop (persisting
    any staged capture not already committed) and always lands a commit — empty if there is
    nothing new — carrying the summary `headline`. Its presence on the branch is the signal
    that the chain finished rather than dying partway. Never persists derived numbers; every
    metric is recomputed by `analyze` from the checkpoint commits + capture."""
    out_dir = os.path.join(wt, "evolve-results")
    os.makedirs(out_dir, exist_ok=True)
    capture.assemble_into(cap_dir, out_dir)
    subprocess.run(["git", "-C", wt, "add", "evolve-results"], capture_output=True, text=True)
    msg = f"results: {arm}/{strategy}/chain{chain} - run {run_id} (raw capture)"
    if headline:
        msg += "\n\n" + headline
    c = subprocess.run(["git", "-C", wt, "commit", "--allow-empty", "-m", msg, "--", "evolve-results"],
                       capture_output=True, text=True)
    print(f"  results commit on {branch}: "
          + ("ok" if c.returncode == 0 else (c.stdout.strip() or c.stderr.strip())[:120]))


def _run_agent_turn(cfg: dict, wt: str, sandbox: str, cp: dict, model: str, prompt: str,
                    cap_dir: str, stream_file: str, checkpoints: list[dict]):
    """Run the agent for one checkpoint IN THE SANDBOX, retrying on a token/session
    limit or a transient failure. Each attempt rebuilds the sandbox fresh: a history-less
    copy of the worktree (no `.git`, no `target/`) whose ONLY acceptance test is the
    current one, renamed to the neutral AcceptanceTest.java (no CpNN, no @Tag). So the
    agent works from the current source alone -- no git history, no prior build output,
    no hint of a checkpoint sequence. The worktree is never touched. A limit waits for the
    quota reset; a transient failure backs off short. Returns (final AgentResult, log)."""
    limits = cfg.get("limits", {})
    attempts = transient_attempts = 0
    attempt_log: list[dict] = []  # every try (failed/limited too); last = success
    while True:
        _prepare_agent_sandbox(wt, sandbox, cfg, cp, checkpoints)  # fresh; discards any failed attempt
        ar = agent.run_agent(prompt, cwd=sandbox, model=model,
                             timeout=cfg.get("agent_timeout", 3600),
                             capture_path=os.path.join(cap_dir, stream_file),
                             confine=_confine_config(cfg))
        att = {"ok": ar.ok, "limit_reached": ar.limit_reached, "retryable": ar.retryable,
               "cost_usd": ar.cost_usd, "input_tokens": ar.input_tokens,
               "output_tokens": ar.output_tokens, "cache_read_tokens": ar.cache_read_tokens,
               "cache_creation_tokens": ar.cache_creation_tokens, "num_turns": ar.num_turns,
               "duration_ms": ar.duration_ms, "duration_api_ms": ar.duration_api_ms,
               "error": (ar.error or "")[:500], "wait_s": None}
        attempt_log.append(att)
        if not (ar.limit_reached or ar.retryable):
            return ar, attempt_log
        attempts += 1
        if attempts > limits.get("max_attempts", 500):
            raise RuntimeError("exceeded max retry attempts; aborting run")
        if ar.limit_reached:
            transient_attempts = 0
            att["wait_s"] = wait_for_window(ar, cfg)
        else:
            transient_attempts += 1
            if transient_attempts > limits.get("max_transient_attempts", 20):
                raise RuntimeError("too many consecutive transient failures; aborting run")
            att["wait_s"] = wait_transient(transient_attempts, ar, cfg)


def _log_checkpoint(row: dict, where: str, wt: str, base_for_cp: str,
                    agent_sha: str, accept_dir: str | None, outcome=None) -> None:
    """Print this checkpoint's key metrics and the production files the agent changed
    (COMMIT 1's diff, minus the injected acceptance tests). Log-only narration; every
    number is recomputed by analyze from the commits + capture."""
    k, phase, cid = row["checkpoint"], row["phase"], row["checkpoint_id"]
    api_s = round((row.get("duration_api_ms") or 0) / 1000)
    cache_k = (row.get("cache_read_tokens") or 0) // 1000
    print(f"  == {where} | cp{k:02d} [{phase}] {cid} ==")
    print(f"    tests  : strict={row['strict_pass']} iso={row['iso_pass']} core={row['core_pass']} "
          f"regressions={row['regressions']} norm_change={row['normalized_change']} "
          f"build_ok={row['build_ok']} selected={row['total_selected']}")
    # Which acceptance tests failed, so a red checkpoint is legible at a glance. A
    # failure in this checkpoint's own CpNN class means the agent didn't fully solve
    # it; a failure in a PRIOR CpMM class is a regression (intended only if this is a
    # mutative checkpoint that lists MM in `mutates`).
    if outcome is not None and getattr(outcome, "results", None):
        failed = [tid for tid, ok in outcome.results.items() if not ok]
        total = len(outcome.results)
        if failed:
            fail_msg = {d.get("test_id"): d.get("failure") for d in getattr(outcome, "detail", [])}
            own = f"Cp{k:02d}Tests"
            print(f"    FAILED : {len(failed)} of {total} test(s):")
            for tid in sorted(failed):
                short = tid.split(".")[-1]           # ClassName#method
                tag = "current" if short.startswith(own) else "regression"
                msg = (fail_msg.get(tid) or "").strip().replace("\n", " ")
                print(f"      - [{tag}] {short}" + (f"  {msg[:140]}" if msg else ""))
        else:
            print(f"    PASSED : all {total} cp01..cp{k:02d} test(s) green")
    print(f"    struct : erosion={row['erosion']} scoped={row['erosion_scoped']} "
          f"hotspot=CC{row.get('hotspot_cc')}/{row.get('hotspot_nloc')}nloc@{row.get('hotspot_fn')} "
          f"java_loc={row['java_loc']}")
    print(f"    churn  : +{row['diff_added']}/-{row['diff_removed']} lines, {row['files_touched']} files")
    print(f"    blast  : {row.get('existing_fns_modified')} existing fns modified, "
          f"{row.get('files_created')} new files, {row.get('files_modified')} modified")
    print(f"    class  : WMC_max={row.get('wmc_max')}@{row.get('wmc_max_class')} "
          f"entry=CC{row.get('entry_cc')}/{row.get('entry_nloc')}nloc@{row.get('entry_fn')} "
          f"pkgs={row.get('packages_touched')} reedit={row.get('reedit_rate')} "
          f"({row.get('reedit_prior_lines')}/{row.get('reedit_body_lines')} body lines)")
    print(f"    proc   : cost=${row['cost_usd']} api={api_s}s cache_read={cache_k}k turns={row['num_turns']}")
    flags = []
    for fld, lbl in (("pinned_touched", "pinned_touched"),
                     ("acceptance_touched", "acceptance_touched"), ("notes", "notes")):
        if str(row.get(fld, "")).strip():
            flags.append(f"{lbl}={str(row[fld])[:100]}")
    if flags:
        print("    flags  : " + "  ".join(flags))
    pathspec = ["--", ".", f":(exclude){accept_dir}"] if accept_dir else []
    changed = subprocess.run(
        ["git", "-C", wt, "diff", "--name-status", base_for_cp,
         agent_sha or base_for_cp, *pathspec], capture_output=True, text=True).stdout.strip()
    if changed:
        print("    changed:")
        for line in changed.splitlines():
            print(f"      {line}")
    else:
        print("    changed: (no production files)")
    print(flush=True)


def _gate_active(cfg: dict, strategy: str) -> bool:
    """True when the impact_gated pipeline should run for this strategy: the config
    has an `impact_gate` section whose `strategy` name matches the active strategy."""
    igc = cfg.get("impact_gate") or {}
    return bool(igc) and igc.get("strategy") == strategy


def _refactor_correctness(sandbox: str, cfg: dict, checkpoints: list[dict], k: int,
                          arm_cfg: dict) -> dict:
    """Record-only correctness of a refactor state: install the full authored cp01..cpK
    suite into the sandbox (which still holds the just-refactored code) and run the gate,
    returning a compact summary. NOT enforced — it never stops the pipeline; it lets
    `analyze` see whether a refactor preserved prior behaviour. The sandbox is rebuilt
    fresh for the next implement turn, so mutating it here is harmless."""
    acc_sandbox = os.path.join(sandbox, cfg["acceptance"]["dest_subpath"].rstrip("/"))
    for pf in cfg.get("isolation", {}).get("pin_files", []):
        base_txt = subprocess.run(["git", "-C", arm_cfg["repo"], "show",
                                   f"{arm_cfg['base_ref']}:{pf}"], capture_output=True, text=True)
        dst = os.path.join(sandbox, pf)
        if base_txt.returncode == 0:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w") as fh:
                fh.write(base_txt.stdout)
    shutil.rmtree(acc_sandbox, ignore_errors=True)
    install_measurement_suite(sandbox, cfg, checkpoints, k)
    scrub_test_artifacts(sandbox, cfg)
    outcome = correctness.run_tests(sandbox, k, cfg)
    passed = sum(1 for ok in (outcome.results or {}).values() if ok)
    return {"build_ok": outcome.build_ok, "total_selected": outcome.total_selected,
            "passed": passed, "total": len(outcome.results or {}),
            "error": (outcome.error or "")[:200] or None}


def _impact_gated_implement(cfg: dict, wt: str, sandbox: str, cp: dict, model: str,
                            template: str, cap_dir: str, checkpoints: list[dict],
                            arm_cfg: dict, base_for_cp: str):
    """The impact_gated implement->score->refactor loop for one checkpoint.

    Each iteration: the agent implements the change in the history-less sandbox, the
    production result is mirrored + staged on the worktree, and ImpactGate scores that
    staged delta (`--curve` vs the Java seed). If the grade clears the block percentile
    the implementation is ACCEPTED. Otherwise the implementation is DISCARDED (worktree
    reset to the clean base) and a refactor turn runs on that clean base, seeded with the
    files/drivers ImpactGate flagged and the change spec, then committed as
    `cpNN refactorM` for visibility; the next implement builds on it. Up to
    `max_refactors` refactors; still blocked after the last leaves the failing change
    staged and flags `stopped` so the caller ends the chain.

    Returns (ar, attempt_log, ig_block, base_for_cp, stopped). On return the worktree is
    mirrored + `git add -A` staged with the accepted (or, if stopped, the last failing)
    implementation, ready for the caller's COMMIT 1; refactor commits already landed.
    """
    igc = cfg["impact_gate"]
    cmd = igc["cmd"]
    block_p = float(igc.get("block_percentile", 98))
    warn_p = float(igc.get("warn_percentile", 90))
    mcfg = igc.get("measure_config")
    baseline_file = igc.get("baseline_file")           # grade vs a reference arm's distribution
    K = igc.get("curve_prior_weight")                  # 0 => grade PURELY vs that distribution
    max_ref = int(igc.get("max_refactors", 3))
    score_kw = dict(measure_config=mcfg, baseline_file=baseline_file, curve_prior_weight=K)
    acc_excl = (cfg["acceptance"]["dest_subpath"].rstrip("/") + "/",)
    k = cp["n"]
    pre_checkpoint_sha = base_for_cp
    attempts: list[dict] = []
    refactors = 0

    def block(passed: bool, stopped: bool) -> dict:
        return {"enabled": True, "block_percentile": block_p, "warn_percentile": warn_p,
                "max_refactors": max_ref, "refactors": refactors, "passed": passed,
                "stopped": stopped, "pre_checkpoint_sha": pre_checkpoint_sha,
                "attempts": attempts}

    for attempt in range(max_ref + 1):   # 0 = first implement; then up to max_ref refactors
        prompt = build_prompt(template, cp["spec"])
        ar, attempt_log = _run_agent_turn(cfg, wt, sandbox, cp, model, prompt, cap_dir,
                                          f"cp{k:02d}.agent.jsonl", checkpoints)
        mirror_source(sandbox, wt, extra_excludes=acc_excl)
        git(["-C", wt, "add", "-A"])
        ig = impact_gate.score(cmd, wt, block_p, warn_p, **score_kw)
        blocked = impact_gate.is_blocked(ig, block_p)
        attempts.append(impact_gate.attempt_summary("implement", ig, block_p))
        pct = impact_gate.grade_percentile(ig)
        print(f"    impact-gate: implement grade p{pct if pct is None else round(pct, 1)} "
              f"(block p{block_p:g})  impact={ig.get('impact')}  -> "
              f"{'BLOCKED' if blocked else 'PASS'}"
              + (f"  [refactors so far: {refactors}]" if refactors else ""), flush=True)
        if not blocked:
            return ar, attempt_log, block(passed=True, stopped=False), base_for_cp, False
        if attempt == max_ref:
            # Out of refactor budget and still blocked: keep the failing change staged for
            # inspection and end the chain. The caller records the full (failing) checkpoint.
            print(f"    impact-gate: STILL BLOCKED after {refactors} refactor(s) -> "
                  f"stopping the chain at cp{k:02d}", flush=True)
            return ar, attempt_log, block(passed=False, stopped=True), base_for_cp, True

        # DISCARD the blocked implementation, then REFACTOR on the clean base.
        git(["-C", wt, "reset", "--hard", base_for_cp])
        subprocess.run(["git", "-C", wt, "clean", "-fd"], capture_output=True, text=True)
        refactors += 1
        _prepare_agent_sandbox(wt, sandbox, cfg, cp, checkpoints)   # clean base + agent test view
        rprompt = impact_gate.refactor_prompt(igc["refactor_prompt"], cp, ig, block_p)
        rstream = f"cp{k:02d}.refactor{refactors}.jsonl"
        print(f"    impact-gate: refactor {refactors}/{max_ref} — restructuring flagged "
              f"classes before re-attempting the change", flush=True)
        rar = agent.run_agent(rprompt, cwd=sandbox, model=model,
                              timeout=cfg.get("agent_timeout", 3600),
                              label=f"refactor{refactors}",
                              capture_path=os.path.join(cap_dir, rstream),
                              confine=_confine_config(cfg))
        mirror_source(sandbox, wt, extra_excludes=acc_excl)
        git(["-C", wt, "add", "-A"])
        ig_ref = impact_gate.score(cmd, wt, block_p, warn_p, **score_kw)
        rtests = None
        if igc.get("record_refactor_correctness", True):
            rtests = _refactor_correctness(sandbox, cfg, checkpoints, k, arm_cfg)
        subprocess.run(["git", "-C", wt, "commit", "--allow-empty",
                        "-m", f"cp{k:02d} refactor{refactors} {cp['id']}"],
                       capture_output=True, text=True)
        rsha = git(["-C", wt, "rev-parse", "HEAD"])
        attempts.append(impact_gate.attempt_summary("refactor", ig_ref, block_p,
                                                    sha=rsha, agent=rar, tests=rtests))
        rpct = impact_gate.grade_percentile(ig_ref)
        print(f"    impact-gate: refactor {refactors} committed {rsha[:9]}  "
              f"grade p{rpct if rpct is None else round(rpct, 1)}  "
              f"cost=${rar.cost_usd:.4f}"
              + (f"  tests={rtests['passed']}/{rtests['total']} build_ok={rtests['build_ok']}"
                 if rtests else ""), flush=True)
        # Wipe the sandbox so the next implement turn rebuilds fresh from the refactored wt.
        # Critical for isolation: _refactor_correctness installs+builds the FULL cp01..cpK
        # suite, and rsync --delete PROTECTS target/, so its CpNN surefire reports + compiled
        # test classes would otherwise persist into the next (blind, Landlock-confined) turn
        # and leak the checkpoint sequence. A full wipe forces a clean history-less rebuild.
        shutil.rmtree(sandbox, ignore_errors=True)
        base_for_cp = rsha   # the refactor is the base the next implement builds on


def run_chain(cfg: dict, arm: str, strategy: str, chain: int, run_id: str,
              checkpoints: list[dict], dry_run: bool, max_cp: int | None) -> None:
    arm_cfg = cfg["arms"][arm]
    model = cfg["model"]
    n = len(checkpoints)
    template = cfg["prompt_strategies"][strategy]
    branch_preview = f"evolve/{run_id}/{strategy}/{arm}/chain{chain}"

    if dry_run:
        gate = ""
        if _gate_active(cfg, strategy):
            igc = cfg["impact_gate"]
            ref = (f"vs baseline {os.path.basename(igc['baseline_file'])} (K={igc.get('curve_prior_weight')})"
                   if igc.get("baseline_file") else "vs seed")
            gate = (f" [impact-gate ON: block p{igc.get('block_percentile')} {ref}, "
                    f"max_refactors={igc.get('max_refactors')}, cmd={' '.join(igc.get('cmd', []))}]")
        print(f"[dry-run] {arm}/{strategy}/chain{chain} [test-mode={cfg['test_mode']}]{gate}: "
              f"{n} checkpoints from {arm_cfg['repo']}@{arm_cfg['base_ref']} -> branch {branch_preview}")
        for cp in checkpoints[: (max_cp or n)]:
            print(f"    cp{cp['n']:02d} [{phase_for(cp['n'], n)}] {cp['id']}")
        return

    wt, branch = make_worktree(arm_cfg, cfg["paths"]["work_root"], arm, strategy, chain, run_id)
    base_commit = git(["-C", wt, "rev-parse", "HEAD"])  # base_ref commit; subsystem = files changed since
    print(f"\n=== {arm}/{strategy}/chain{chain}  branch={branch}  worktree={wt} ===")

    # First commit on the branch: the run's static manifest (provenance + config
    # snapshot), written before any checkpoint so a partial run is self-describing and
    # the control is captured before it can drift. The checkpoint->sha map is NOT here;
    # analyze derives it from the per-checkpoint capture records. Static provenance only.
    prov_extra = {
        "arm": arm, "strategy": strategy, "chain": chain, "branch": branch,
        "base_ref": arm_cfg["base_ref"], "base_commit": base_commit,
        "test_mode": cfg["test_mode"],   # which acceptance-view the agent worked under
    }
    if _gate_active(cfg, strategy):      # the gate is part of THIS run's control -> record it
        prov_extra["impact_gate"] = capture.impact_gate_provenance(cfg)
    prov = capture.provenance(cfg, run_id, model, HARNESS_DIR, extra=prov_extra)
    commit_run_manifest(wt, branch, run_id, arm, strategy, chain, prov, cfg.get("_snapshot"))

    # Capture artifacts are staged HERE (a sibling of the worktree) during the
    # chain, then copied into evolve-results/capture/ at the results commit — so
    # they never enter the per-checkpoint code commits or the diffs derived from
    # them. Cleared on an idempotent re-run of the same run_id.
    cap_dir = wt + "-capture"
    shutil.rmtree(cap_dir, ignore_errors=True)
    os.makedirs(cap_dir, exist_ok=True)

    # The agent works in this history-less sandbox (a copy of the worktree source with
    # no .git and no target/), never in the worktree itself, so it cannot read the
    # checkpoint git history or prior build output. Re-mirrored fresh each agent turn.
    # It IS `sandbox_root` directly (project contents sit right under it): a plain dir
    # named e.g. "sandbox", with NOTHING in the path — no run_id/arm/strategy/chain — to
    # hint at a checkpoint sequence, and no worktree/.git/capture sibling to `cd ..` into.
    # Reused across chains, which run sequentially and wipe it each turn. The harness
    # rmtree's it wholesale, so refuse a home/root path.
    sandbox = cfg["paths"]["sandbox_root"]
    if not sandbox or os.path.abspath(sandbox) in ("/", os.path.expanduser("~")):
        raise RuntimeError(f"paths.sandbox_root must be a dedicated directory, not {sandbox!r}")
    shutil.rmtree(sandbox, ignore_errors=True)

    # Derived numbers below are computed ONLY to narrate progress in the log — they
    # are never persisted. The branch stores raw capture; analyze recomputes.
    prior_passing: set[str] = set()
    captures: list[dict] = []
    strict_count = regr_count = 0  # running tallies for the results commit headline
    stopped = False                # impact_gated: set when a checkpoint gives up (ends the chain)

    limit = max_cp or n
    for cp in checkpoints[:limit]:
        k = cp["n"]
        phase = phase_for(k, n)
        row = {f: "" for f in CSV_FIELDS}
        row.update({"run_id": run_id, "branch": branch,
                    "arm": arm, "strategy": strategy, "chain": chain,
                    "checkpoint": k, "checkpoint_id": cp["id"], "phase": phase})
        where = f"run {run_id} | {arm}/{strategy} chain{chain}"
        print(f"\n--- {where} | cp{k:02d} [{phase}] {cp['id']} — running agent ---", flush=True)
        print(f"    test   : {TEST_MODES[cfg['test_mode']]}", flush=True)
        if cp.get("type") == "mutative":
            print(f"    type   : MUTATIVE (revises prior rules {cp.get('mutates', [])})", flush=True)
        print(f"    spec   : {cp['spec']}", flush=True)

        acc_sub = cfg["acceptance"]["dest_subpath"].rstrip("/")
        acc_sandbox = os.path.join(sandbox, acc_sub)
        pin_files = cfg.get("isolation", {}).get("pin_files", [])

        # The worktree carries ONLY the accumulating production code + pinned docs — no
        # acceptance tests (those live only in the sandbox). Its HEAD is the previous reset
        # commit and stays there through the agent turn, so it is COMMIT 1's parent and the
        # base for the production-only agent diff.
        base_for_cp = git(["-C", wt, "rev-parse", "HEAD"])

        # 1-3. Agent turn in the neutral, HISTORY-LESS SANDBOX (fresh session, no carried
        # context). _run_agent_turn rebuilds it each attempt: worktree source (no .git,
        # no target/) + a fresh acceptance dir holding only the shared infra and THIS
        # checkpoint's test as AcceptanceTest.java (no CpNN name, no @Tag). So the agent
        # gets no git history, no prior build output, and no hint of a checkpoint sequence.
        stream_file = f"cp{k:02d}.agent.jsonl"
        prompt = build_prompt(template, cp["spec"])   # the implement prompt (recorded either way)
        ig_block = None
        stopped = False
        if _gate_active(cfg, strategy):
            # impact_gated pipeline: implement -> ImpactGate -> discard+refactor -> re-implement,
            # up to max_refactors. Returns the accepted (or, if stopped, last failing) turn with
            # the worktree already mirrored + staged; base_for_cp advances past any refactor commit
            # so COMMIT 1's parent and the metrics base are the refactored code.
            ar, attempt_log, ig_block, base_for_cp, stopped = _impact_gated_implement(
                cfg, wt, sandbox, cp, model, template, cap_dir, checkpoints, arm_cfg, base_for_cp)
        else:
            ar, attempt_log = _run_agent_turn(cfg, wt, sandbox, cp, model, prompt, cap_dir,
                                              stream_file, checkpoints)
            # 4. Copy the agent's PRODUCTION result back onto the worktree (the sandbox-only
            # acceptance dir is excluded; .git/target preserved).
            mirror_source(sandbox, wt, extra_excludes=(acc_sub + "/",))
            git(["-C", wt, "add", "-A"])

        # Capture the production-only delta on top of the previous reset (or the last refactor).
        diff_file = f"cp{k:02d}.agent.diff"
        agent_diff = subprocess.run(["git", "-C", wt, "diff", "--cached", base_for_cp],
                                    capture_output=True, text=True).stdout
        with open(os.path.join(cap_dir, diff_file), "w") as fh:
            fh.write(agent_diff)

        row.update({"agent_ok": ar.ok, "cost_usd": round(ar.cost_usd, 4),
                    "input_tokens": ar.input_tokens, "cache_read_tokens": ar.cache_read_tokens,
                    "output_tokens": ar.output_tokens, "num_turns": ar.num_turns,
                    "duration_ms": ar.duration_ms, "duration_api_ms": ar.duration_api_ms})
        if ar.error:
            row["notes"] = ar.error[:200]

        # 5. Tamper detection (mode-aware): compare the agent-visible tests in the sandbox to
        # their authored source — any difference means the agent edited a test it could see
        # (blind: its one neutral test; full: any of the cp01..cpK suite). Flag a pinned-doc
        # edit too (the agent's CLAUDE.md was copied back).
        acceptance_touched = _detect_sandbox_tamper(acc_sandbox, cfg, cp, checkpoints)
        touched_pins = [pf for pf in pin_files
                        if git(["-C", wt, "status", "--porcelain", "--", pf], check=False)]
        row["pinned_touched"] = ",".join(touched_pins)
        row["acceptance_touched"] = ",".join(acceptance_touched)

        # COMMIT 1 — the AGENT commit: `git show` on it is EXACTLY the agent's production
        # change (incl. any CLAUDE.md edit). An empty commit => a no-op checkpoint.
        c1 = subprocess.run(["git", "-C", wt, "commit", "-m", f"cp{k:02d} agent {cp['id']}"],
                            capture_output=True, text=True)
        agent_sha = git(["-C", wt, "rev-parse", "HEAD"]) if c1.returncode == 0 else ""

        # 6. Prepare the GATE in the SANDBOX (never the worktree): restore the pinned docs
        # to their base version so an agent edit can't sway the gate, then swap the neutral
        # test for the FULL authored cp01..cpK suite (real CpNN names, so scoring by class
        # works). These are the priors the agent never saw, so a silent break shows up as a
        # real regression.
        for pf in pin_files:
            base_txt = subprocess.run(["git", "-C", wt, "show", f"{arm_cfg['base_ref']}:{pf}"],
                                      capture_output=True, text=True)
            dst = os.path.join(sandbox, pf)
            if base_txt.returncode == 0:
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                with open(dst, "w") as fh:
                    fh.write(base_txt.stdout)
            elif os.path.exists(dst):
                os.remove(dst)
        shutil.rmtree(acc_sandbox, ignore_errors=True)
        install_measurement_suite(sandbox, cfg, checkpoints, k)

        # 7. correctness gate IN THE SANDBOX: mvn clean, then run the full cp01..cpK suite
        # against the agent's production code. The console is retained for capture.
        scrub_test_artifacts(sandbox, cfg)
        outcome = correctness.run_tests(sandbox, k, cfg)
        build_log_file = None
        if outcome.console:
            build_log_file = f"cp{k:02d}.build.log"
            with open(os.path.join(cap_dir, build_log_file), "w") as fh:
                fh.write(outcome.console[:500_000])
        # A mutative checkpoint's `mutates` lists the prior rules it deliberately
        # changes; their tests are expected to change, so regressions there are
        # intended. true_regressions counts only breakage on the un-mutated surface.
        mutated = [int(m) for m in (cp.get("mutates") or [])]
        row["checkpoint_type"] = cp.get("type", "additive")
        row.update(correctness.outcome_row(outcome, prior_passing, mutated))
        prior_passing = outcome.passing
        if outcome.error and not row["notes"]:
            row["notes"] = outcome.error[:200]

        # 8. Normalise the worktree: restore the pinned docs to base (CLAUDE.md can never
        # become accumulating cross-checkpoint memory). No acceptance tests are threaded
        # through the worktree; the next checkpoint's neutral test is built fresh into the
        # sandbox by _run_agent_turn.
        for pf in pin_files:
            restored = subprocess.run(["git", "-C", wt, "checkout", arm_cfg["base_ref"], "--", pf],
                                      capture_output=True, text=True)
            if restored.returncode != 0:  # agent-created (not in base_ref) -> drop it
                fpath = os.path.join(wt, pf)
                if os.path.exists(fpath):
                    os.remove(fpath)

        # Structural metrics — LOGGING ONLY (analyze recomputes them). Over the AGENT commit
        # (base_for_cp..agent). Clean the jscpd scratch so it can never leak into a commit.
        metrics_cur = agent_sha or "HEAD"
        mrow, _ = metrics.compute_all(
            wt, arm_cfg, cfg["tools"], base_commit, base_for_cp, metrics_cur,
            exclude=cfg.get("acceptance", {}).get("dest_subpath"))
        row.update(mrow)
        shutil.rmtree(os.path.join(wt, ".jscpd-report"), ignore_errors=True)

        # Cold-reader probe (read-only), at probe.at_checkpoints. Runs in a fresh
        # HISTORY-LESS mirror so it can't `git log` the sequence either.
        probe_cfg = cfg.get("probe", {})
        at = probe_cfg.get("at_checkpoints")
        run_probe = (k in at) if at else ((k == 1) or (phase_for(k - 1, n) != phase))
        probe_record = None
        if probe_cfg.get("enabled", True) and run_probe:
            mirror_source(wt, sandbox)
            pr = agent.probe(cfg["probe"]["question"], cwd=sandbox, model=model,
                             expected=cfg["probe"].get("expected"),
                             capture_path=os.path.join(cap_dir, f"cp{k:02d}.probe.jsonl"),
                             confine=_confine_config(cfg))
            row.update({
                "probe_cost_usd": round(pr["probe_cost_usd"], 4),
                "probe_input_tokens": pr["probe_input_tokens"],
                "probe_cache_read_tokens": pr["probe_cache_read_tokens"],
                "probe_recall": ("" if pr["probe_recall"] is None else round(pr["probe_recall"], 3)),
            })
            probe_record = pr

        # Build this checkpoint's RAW capture record, then stage the WHOLE per-checkpoint
        # capture (record + build log + agent stream + diff + probe) into the worktree
        # under evolve-results/capture/, so COMMIT 2 carries it — each reset commit is
        # self-contained with its own test results and logs. The agent never sees it:
        # evolve-results/ is excluded from every sandbox mirror. 'reset' is left blank (it
        # is COMMIT 2's own not-yet-made hash; analyze derives from the agent commit shas).
        rec = capture.checkpoint_record(
            k, cp["id"], phase,
            {"commit": agent_sha, "reset": "", "preagent": base_for_cp,
             "prev": base_for_cp, "base": base_commit},
            ar, outcome, probe_record, touched_pins, acceptance_touched,
            stream_file, diff_file, build_log_file=build_log_file,
            attempts=attempt_log, spec=cp["spec"], prompt=prompt,
            ckpt_type=cp.get("type", "additive"), mutates=mutated, impact_gate=ig_block)
        capture.write_json(os.path.join(cap_dir, f"cp{k:02d}.json"), rec)
        wt_cap = os.path.join(wt, "evolve-results", "capture")
        os.makedirs(wt_cap, exist_ok=True)
        for f in os.listdir(cap_dir):
            if f.startswith(f"cp{k:02d}."):
                shutil.copy2(os.path.join(cap_dir, f), os.path.join(wt_cap, f))
        captures.append(rec)
        strict_count += 1 if row["strict_pass"] is True else 0
        regr_count += int(row["regressions"] or 0)

        # COMMIT 2 — the RESET commit: worktree normalisation + this checkpoint's capture.
        # Kept even if empty, so every checkpoint is a clean two-commit boundary.
        git(["-C", wt, "add", "-A"])
        subprocess.run(["git", "-C", wt, "commit", "--allow-empty",
                        "-m", f"cp{k:02d} reset {cp['id']}"], capture_output=True, text=True)

        # Key metrics + failing tests + changed files for this checkpoint, so progress is visible.
        _log_checkpoint(row, where, wt, base_for_cp, agent_sha,
                        cfg.get("acceptance", {}).get("dest_subpath"), outcome)

        # 9. Wipe the sandbox so the next checkpoint always starts from a clean, fully
        # rebuilt copy (no leftover Cp01..cpK gate tests or agent build output).
        shutil.rmtree(sandbox, ignore_errors=True)

        # impact_gated stop: the change never came under the block percentile within
        # max_refactors. The failing checkpoint is fully recorded above; end the chain
        # here (a clean-code failure — this architecture couldn't absorb the change
        # cleanly in the refactor budget).
        if stopped:
            igc = cfg.get("impact_gate", {})
            print(f"\n!!! {where} | STOPPED at cp{k:02d} {cp['id']}: still over the "
                  f"block percentile (p{igc.get('block_percentile')}) after "
                  f"{igc.get('max_refactors')} refactors.", flush=True)
            break

    # Terminal 'results:' commit: a completion marker. Provenance + config already
    # landed in the manifest commit and each checkpoint's raw capture in its reset
    # commit, so this normally adds nothing — it backstops any unstaged capture and
    # carries a derived one-liner for at-a-glance history (text only, not data).
    n_done = len(captures)
    stopped_at = f" STOPPED_AT_cp{captures[-1]['checkpoint']:02d}" if (captures and stopped) else ""
    headline = (f"checkpoints={n_done} strict_pass={strict_count}/{n_done} "
                f"regressions={regr_count}{stopped_at} (derived numbers recomputed by analyze)")
    commit_chain_results(wt, branch, run_id, arm, strategy, chain, cap_dir, headline)
    shutil.rmtree(sandbox, ignore_errors=True)  # the agent's history-less working copy

    # A gated stop ends this chain (recorded above). With stop_scope: run it also aborts
    # the whole run (every remaining arm/chain); default 'chain' lets the other cells run
    # so the comparison still gets data.
    if stopped and (cfg.get("impact_gate", {}).get("stop_scope") == "run"):
        raise ChainStopped(f"{arm}/{strategy}/chain{chain} stopped at cp{captures[-1]['checkpoint']:02d}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--test-mode", required=True, choices=sorted(TEST_MODES),
                    help="REQUIRED, no default. Which acceptance tests the agent sees while "
                         "it works. 'blind' = only this checkpoint's own test, neutralised "
                         "(prior tests hidden). 'full' = the full cp01..cpK regression suite "
                         "(real CpNN names). The post-agent gate runs the full suite either way.")
    ap.add_argument("--arm", action="append", help="restrict to arm(s); default all")
    ap.add_argument("--model", help="override config's model id (e.g. claude-opus-5). "
                    "The chosen model is recorded in provenance.json, so a run is "
                    "self-describing; use a descriptive --run-id to keep branches "
                    "from different models apart. See docs/RUN_WITH_A_DIFFERENT_MODEL.md.")
    ap.add_argument("--strategy", help="override active prompt strategy")
    ap.add_argument("--chain", type=int, help="run a single chain index")
    ap.add_argument("--max-checkpoints", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-id", help="ties branches + results to this run "
                    "(default: current time as YYYYMMDDHHMM). The --test-mode is "
                    "automatically prepended, so do NOT include it yourself.")
    args = ap.parse_args()

    # Fold the test mode into the run_id so blind and full runs can never collide on branch
    # names or work dirs (the branch path is evolve/<run_id>/... and does not otherwise carry
    # the mode). A run is thus self-identifying, e.g. blind-202608092351 / full-202608092351.
    base_run_id = args.run_id or datetime.now().strftime("%Y%m%d%H%M")
    run_id = f"{args.test_mode}-{base_run_id}"

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    # Test mode is a per-run choice, not a config default: it MUST be selected on the CLI
    # (argparse enforces required). Stored on cfg so the sandbox/tamper/provenance paths see it.
    cfg["test_mode"] = args.test_mode

    # Model is a config default (config.yaml: model:) but overridable per run on the
    # CLI, so anyone can re-run the experiment against a different AI without editing
    # config. The value flows through cfg["model"] to every agent turn, the probe, and
    # provenance.json, so a run stays self-describing regardless of where the id came
    # from. See docs/RUN_WITH_A_DIFFERENT_MODEL.md.
    if args.model:
        cfg["model"] = args.model

    # Resolve the harness's own relative paths against the config file's
    # directory, so the whole tree can be moved without editing paths.
    cfg_dir = os.path.dirname(os.path.abspath(args.config))

    def resolve(p):
        if p is None:
            return p
        p = expand_path(p)  # ${HOME}, $VAR, ~ (raises if a var is undefined)
        return p if os.path.isabs(p) else os.path.join(cfg_dir, p)

    for name, arm_cfg in cfg["arms"].items():
        arm_cfg["repo"] = expand_path(arm_cfg["repo"], f"arms.{name}.repo")

    cfg["checkpoints_file"] = resolve(cfg["checkpoints_file"])
    cfg["paths"]["work_root"] = resolve(cfg["paths"]["work_root"])
    cfg["paths"]["sandbox_root"] = resolve(cfg["paths"].get("sandbox_root") or "${HOME}/sandbox")
    cfg["paths"]["results_csv"] = resolve(cfg["paths"]["results_csv"])
    if cfg.get("tools", {}).get("astgrep_rules"):
        cfg["tools"]["astgrep_rules"] = resolve(cfg["tools"]["astgrep_rules"])
    if cfg.get("acceptance", {}).get("src_dir"):
        cfg["acceptance"]["src_dir"] = resolve(cfg["acceptance"]["src_dir"])
    # impact_gated pipeline: expand the impact-gate command (each element may use ${HOME})
    # and anchor any measure-config to the config dir.
    if cfg.get("impact_gate", {}).get("cmd"):
        cfg["impact_gate"]["cmd"] = [expand_path(c, "impact_gate.cmd")
                                     for c in cfg["impact_gate"]["cmd"]]
    if cfg.get("impact_gate", {}).get("measure_config"):
        cfg["impact_gate"]["measure_config"] = resolve(cfg["impact_gate"]["measure_config"])
    if cfg.get("impact_gate", {}).get("baseline_file"):
        # Absolute so impact-gate joins it OUTSIDE the arm worktree (never committed / seen
        # by the agent); a reference-arm distribution to grade against instead of the seed.
        cfg["impact_gate"]["baseline_file"] = resolve(cfg["impact_gate"]["baseline_file"])

    # Sources snapshotted into each results commit so a run is self-contained: the
    # config that shaped its metrics travels with it (analyze prefers this over the
    # live config when re-deriving).
    cfg["_snapshot"] = {
        "config": os.path.abspath(args.config),
        "checkpoints": cfg["checkpoints_file"],
        "astgrep_rules": cfg.get("tools", {}).get("astgrep_rules"),
    }

    with open(cfg["checkpoints_file"]) as fh:
        checkpoints = yaml.safe_load(fh)["checkpoints"]
    for i, cp in enumerate(checkpoints, 1):
        cp["n"] = i

    arms = args.arm or list(cfg["arms"].keys())
    strategy = args.strategy or cfg["active_strategy"]
    chains = [args.chain] if args.chain is not None else range(cfg["chains"])
    print(f"run_id = {run_id}")
    print(f"model = {cfg['model']}")
    print(f"test mode = {args.test_mode}: {TEST_MODES[args.test_mode]}")

    # Fail CLOSED on a blind measure. Every structural metric — and every gate
    # verdict — is function-based, so a Java file the parser cannot read scores as
    # "no complexity, no change" instead of erroring (lizard 1.24.0 does exactly
    # that to @Entity/@Table classes). Both stacks are probed with a change of that
    # shape before any agent runs; the gate probe is kept for provenance so each
    # run records the parser that actually decided its verdicts.
    gated = bool(strategy == (cfg.get("impact_gate") or {}).get("strategy"))
    try:
        probe = parser_selftest.require(cfg, gated)
    except (parser_selftest.ParserBlind, impact_gate.ImpactGateError) as e:
        # A blind parser, or a gate that cannot run at all — either way the gated
        # experiment cannot be measured. Fail here, before any worktree or agent turn.
        print(f"\n=== REFUSING TO RUN: {e}")
        return 2
    if gated and probe:
        cfg["impact_gate"]["_parser_probe"] = probe
        print(f"parser check = ok (gate lizard "
              f"{probe.get('lizard_version') or 'unknown'}, sees annotated classes)")

    # The run persists NO derived CSV — only raw capture onto the evolve branches.
    # Interleave arms per chain: spring/chain0, officefloor/chain0, spring/chain1,
    # ... so the two arms are matched in time (no temporal confound) and a run cut
    # short still has both arms for the chains it completed.
    try:
        for chain in chains:
            for arm in arms:
                run_chain(cfg, arm, strategy, chain, run_id, checkpoints,
                          args.dry_run, args.max_checkpoints)
    except ChainStopped as e:
        # impact_gated with stop_scope: run — a chain gave up, abort the whole run.
        print(f"\n=== RUN STOPPED: {e} (impact_gate.stop_scope=run) ===")
        return 3

    if args.dry_run:
        return 0
    print(f"\nRaw capture written to branches: evolve/{run_id}/{strategy}/<arm>/chain<n> in each repo")
    print(f"Next: python -m harness.analyze --config {args.config} --run-id {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
