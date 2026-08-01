"""PetClinic-Evolve driver.

For each (arm, prompt-strategy, chain) it creates an isolated git worktree at the
arm's pre-feature base ref, then walks the ordered checkpoints. At each
checkpoint it:

  1. runs a FRESH headless agent with only the checkpoint spec (no carried
     context) -- SlopCodeBench's iterative-extension condition;
  2. commits, then gates on build + the accumulated acceptance suite cp01..cpK;
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

from . import agent, capture, correctness, expand_path, metrics

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_FIELDS = [
    "run_id", "branch",
    "arm", "strategy", "chain", "checkpoint", "checkpoint_id", "phase",
    # process
    "agent_ok", "cost_usd", "input_tokens", "cache_read_tokens", "output_tokens",
    "num_turns", "duration_ms", "duration_api_ms",
    # correctness
    "build_ok", "total_selected", "strict_pass", "iso_pass", "core_pass",
    "core_p", "core_t", "error_p", "error_t", "func_p", "func_t",
    "regr_p", "regr_t", "regressions", "normalized_change",
    # structure (final numbers + the intermediates they are computed from)
    "erosion", "erosion_high_mass", "erosion_total_mass", "erosion_hot_fns",  # whole app
    "erosion_scoped", "erosion_scoped_high_mass", "erosion_scoped_total_mass", "subsystem_nfns",  # touched-file subsystem
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


def git(args: list[str], cwd: str | None = None, check: bool = True) -> str:
    proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
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
    print(f"    [limit] token limit reached — waiting {int(secs)}s "
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


def inject_checkpoint_tests(wt: str, cfg: dict, k: int) -> list[str]:
    """Copy ONLY checkpoint k's acceptance test (plus the shared infra at k=1)
    into the worktree. This is what keeps the agent from seeing future
    requirements: at checkpoint k the worktree contains cp01..cpk tests only.
    """
    acc = cfg.get("acceptance")
    if not acc:
        return []
    dest = os.path.join(wt, acc["dest_subpath"])
    os.makedirs(dest, exist_ok=True)
    wanted = list(acc.get("shared", [])) if k == 1 else []
    wanted.append(f"Cp{k:02d}Tests.java")
    copied = []
    for fn in wanted:
        src = os.path.join(acc["src_dir"], fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, fn))
            copied.append(fn)
    return copied


def restore_acceptance_tests(wt: str, cfg: dict, k: int, write: bool = True) -> list[str]:
    """Compare the experimenter-owned acceptance tests (cp01..cpK + shared infra)
    against the authored source. Returns the files the agent changed or deleted.

    With write=False it only DETECTS (used before the commit, so the agent's edit
    stays visible in that commit). With write=True it also rewrites the authored
    version (used AFTER the commit + gate, so the reset test folds into the next
    checkpoint's commit and the agent must satisfy it at the next step).
    """
    acc = cfg.get("acceptance")
    if not acc:
        return []
    dest = os.path.join(wt, acc["dest_subpath"])
    wanted = list(acc.get("shared", [])) + [f"Cp{i:02d}Tests.java" for i in range(1, k + 1)]
    tampered = []
    for fn in wanted:
        src = os.path.join(acc["src_dir"], fn)
        if not os.path.isfile(src):
            continue
        authored = open(src, "rb").read()
        dst = os.path.join(dest, fn)
        current = open(dst, "rb").read() if os.path.isfile(dst) else None
        if current != authored:
            tampered.append(fn)
            if write:
                os.makedirs(dest, exist_ok=True)
                with open(dst, "wb") as fh:
                    fh.write(authored)
    return tampered


def commit_chain_results(wt: str, branch: str, run_id: str, arm: str, strategy: str,
                         chain: int, cap_dir: str | None, provenance: dict | None,
                         headline: str = "", snapshot: dict | None = None) -> None:
    """Final 'results:' commit on the evolve branch. It persists ONLY the raw,
    irreproducible capture (`capture/`), the run `provenance.json`, and a snapshot
    of the analysis-shaping config (`config/`) — never any derived numbers. Every
    metric (erosion, verbosity, correctness, coupling, ...) is recomputed from the
    checkpoint commits + this capture by `analyze`, so the branch stays the single
    source of truth without duplicating derived data. `headline` is a
    human-readable one-liner for the commit message only.
    """
    out_dir = os.path.join(wt, "evolve-results")
    os.makedirs(out_dir, exist_ok=True)
    capture.assemble_into(cap_dir, out_dir)
    if provenance is not None:
        capture.write_json(os.path.join(out_dir, "provenance.json"), provenance)
    if snapshot:
        capture.snapshot_config(snapshot.get("config"), snapshot.get("checkpoints"),
                                snapshot.get("astgrep_rules"), out_dir)

    subprocess.run(["git", "-C", wt, "add", "evolve-results"], capture_output=True, text=True)
    msg = f"results: {arm}/{strategy}/chain{chain} - run {run_id} (raw capture)"
    if headline:
        msg += "\n\n" + headline
    c = subprocess.run(["git", "-C", wt, "commit", "-m", msg, "--", "evolve-results"],
                       capture_output=True, text=True)
    print(f"  results commit on {branch}: "
          + ("ok" if c.returncode == 0 else (c.stdout.strip() or c.stderr.strip())[:120]))


def run_chain(cfg: dict, arm: str, strategy: str, chain: int, run_id: str,
              checkpoints: list[dict], dry_run: bool, max_cp: int | None) -> None:
    arm_cfg = cfg["arms"][arm]
    model = cfg["model"]
    n = len(checkpoints)
    template = cfg["prompt_strategies"][strategy]
    branch_preview = f"evolve/{run_id}/{strategy}/{arm}/chain{chain}"

    if dry_run:
        print(f"[dry-run] {arm}/{strategy}/chain{chain}: {n} checkpoints from "
              f"{arm_cfg['repo']}@{arm_cfg['base_ref']} -> branch {branch_preview}")
        for cp in checkpoints[: (max_cp or n)]:
            print(f"    cp{cp['n']:02d} [{phase_for(cp['n'], n)}] {cp['id']}")
        return

    wt, branch = make_worktree(arm_cfg, cfg["paths"]["work_root"], arm, strategy, chain, run_id)
    base_commit = git(["-C", wt, "rev-parse", "HEAD"])  # base_ref commit; subsystem = files changed since
    print(f"\n=== {arm}/{strategy}/chain{chain}  branch={branch}  worktree={wt} ===")

    # Capture artifacts are staged HERE (a sibling of the worktree) during the
    # chain, then copied into evolve-results/capture/ at the results commit — so
    # they never enter the per-checkpoint code commits or the diffs derived from
    # them. Cleared on an idempotent re-run of the same run_id.
    cap_dir = wt + "-capture"
    shutil.rmtree(cap_dir, ignore_errors=True)
    os.makedirs(cap_dir, exist_ok=True)

    # Derived numbers below are computed ONLY to narrate progress in the log — they
    # are never persisted. The branch stores raw capture; analyze recomputes.
    prior_passing: set[str] = set()
    captures: list[dict] = []
    strict_count = regr_count = 0  # running tallies for the results commit headline

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

        # 0. Ensure this checkpoint's acceptance test is present. For k>=2 it was
        # injected by the PREVIOUS checkpoint's reset commit (COMMIT 2), so it is
        # already in HEAD; only cp01 (+ shared infra) is injected here. The agent
        # sees cp01..cpK, never future requirements.
        if k == 1:
            inject_checkpoint_tests(wt, cfg, 1)

        # Snapshot the pre-agent state as a throwaway commit so a token-limit- or
        # network-interrupted attempt can be rolled back and retried cleanly. It is
        # undone (soft reset) before COMMIT 1, so it never enters real history.
        git(["-C", wt, "add", "-A"])
        subprocess.run(["git", "-C", wt, "commit", "-q", "--allow-empty",
                        "-m", f"__preagent_cp{k:02d}__"], capture_output=True, text=True)
        preagent_ref = git(["-C", wt, "rev-parse", "HEAD"])
        base_for_cp = git(["-C", wt, "rev-parse", "HEAD~1"])  # prev reset commit (base_ref at cp01)

        # 1. agent turn (fresh session, no carried context). On a token-limit OR a
        # transient failure (network drop, API overload, no completion), discard
        # this attempt, WAIT, then retry the SAME checkpoint from the reset state.
        # Token limits wait for the quota reset; transient failures back off short.
        prompt = build_prompt(template, cp["spec"])
        limits = cfg.get("limits", {})
        attempts = 0
        transient_attempts = 0
        stream_file = f"cp{k:02d}.agent.jsonl"
        attempt_log: list[dict] = []  # every try (failed/limited too); last = success
        while True:
            ar = agent.run_agent(prompt, cwd=wt, model=model,
                                 timeout=cfg.get("agent_timeout", 3600),
                                 capture_path=os.path.join(cap_dir, stream_file))
            att = {"ok": ar.ok, "limit_reached": ar.limit_reached, "retryable": ar.retryable,
                   "cost_usd": ar.cost_usd, "input_tokens": ar.input_tokens,
                   "output_tokens": ar.output_tokens, "cache_read_tokens": ar.cache_read_tokens,
                   "cache_creation_tokens": ar.cache_creation_tokens, "num_turns": ar.num_turns,
                   "duration_ms": ar.duration_ms, "duration_api_ms": ar.duration_api_ms,
                   "error": (ar.error or "")[:500], "wait_s": None}
            attempt_log.append(att)
            if not (ar.limit_reached or ar.retryable):
                break
            attempts += 1
            if attempts > limits.get("max_attempts", 500):
                raise RuntimeError("exceeded max retry attempts; aborting run")
            subprocess.run(["git", "-C", wt, "reset", "--hard", preagent_ref],
                           capture_output=True, text=True)
            subprocess.run(["git", "-C", wt, "clean", "-fdq"], capture_output=True, text=True)
            if ar.limit_reached:
                transient_attempts = 0
                att["wait_s"] = wait_for_window(ar, cfg)
            else:
                transient_attempts += 1
                if transient_attempts > limits.get("max_transient_attempts", 20):
                    raise RuntimeError("too many consecutive transient failures; aborting run")
                att["wait_s"] = wait_transient(transient_attempts, ar, cfg)

        # Undo the snapshot commit (keep its contents staged) so COMMIT 1 (the
        # agent commit) is parented on the pre-agent state and its diff is EXACTLY
        # what the agent changed.
        subprocess.run(["git", "-C", wt, "reset", "--soft", base_for_cp],
                       capture_output=True, text=True)

        # Capture the true agent delta (identical to COMMIT 1's diff, kept for
        # convenience and to survive even if COMMIT 1 is empty).
        diff_file = f"cp{k:02d}.agent.diff"
        agent_diff = subprocess.run(["git", "-C", wt, "diff", preagent_ref],
                                    capture_output=True, text=True).stdout
        with open(os.path.join(cap_dir, diff_file), "w") as fh:
            fh.write(agent_diff)

        row.update({"agent_ok": ar.ok, "cost_usd": round(ar.cost_usd, 4),
                    "input_tokens": ar.input_tokens, "cache_read_tokens": ar.cache_read_tokens,
                    "output_tokens": ar.output_tokens, "num_turns": ar.num_turns,
                    "duration_ms": ar.duration_ms, "duration_api_ms": ar.duration_api_ms})
        if ar.error:
            row["notes"] = ar.error[:200]

        # Record what the agent touched, but DO NOT undo it yet — COMMIT 1 must
        # preserve exactly what the agent did (incl. any CLAUDE.md edit or
        # acceptance-test tamper). Normalisation happens in COMMIT 2 below.
        touched_pins = [pf for pf in cfg.get("isolation", {}).get("pin_files", [])
                        if git(["-C", wt, "status", "--porcelain", "--", pf], check=False)]
        acceptance_touched = restore_acceptance_tests(wt, cfg, k, write=False)
        row["pinned_touched"] = ",".join(touched_pins)
        row["acceptance_touched"] = ",".join(acceptance_touched)

        # 2. COMMIT 1 — the AGENT commit: `git show` on it is EXACTLY the agent's
        # change for this checkpoint. An empty commit (no changes) => no-op checkpoint.
        git(["-C", wt, "add", "-A"])
        c1 = subprocess.run(["git", "-C", wt, "commit", "-m", f"cp{k:02d} agent {cp['id']}"],
                            capture_output=True, text=True)
        agent_sha = git(["-C", wt, "rev-parse", "HEAD"]) if c1.returncode == 0 else ""

        # 3. Normalise for the next run: restore the pinned docs to base (CLAUDE.md
        # must be identical at every checkpoint — it can never become accumulating
        # cross-checkpoint memory) and reset the acceptance tests to authored —
        # BOTH before the gate, so a weakened test or an edited guide can never
        # produce a false pass. These land in COMMIT 2 below.
        for pf in cfg.get("isolation", {}).get("pin_files", []):
            restored = subprocess.run(["git", "-C", wt, "checkout", arm_cfg["base_ref"], "--", pf],
                                      capture_output=True, text=True)
            if restored.returncode != 0:  # agent-created (not in base_ref) -> drop it
                fpath = os.path.join(wt, pf)
                if os.path.exists(fpath):
                    os.remove(fpath)
        restore_acceptance_tests(wt, cfg, k, write=True)

        # 4. correctness gate (runs on the authored tests, pinned CLAUDE.md, and
        # the agent's production code)
        outcome = correctness.run_tests(wt, k, cfg)
        # Full build + test console (raw): a test that errors before producing a
        # Surefire report leaves no trace otherwise. Capped to keep the commit sane.
        build_log_file = None
        if outcome.console:
            build_log_file = f"cp{k:02d}.build.log"
            with open(os.path.join(cap_dir, build_log_file), "w") as fh:
                fh.write(outcome.console[:500_000])
        row.update(correctness.outcome_row(outcome, prior_passing))
        prior_passing = outcome.passing
        if outcome.error and not row["notes"]:
            row["notes"] = outcome.error[:200]

        # 5. COMMIT 2 — the RESET commit: the harness normalisation (pinned docs +
        # acceptance reset) plus the NEXT checkpoint's injected test — the content
        # that sets up the next run. Kept even if empty, so every checkpoint is a
        # clean two-commit boundary and cp(K+1)'s agent commit stays pure.
        if k < n:
            inject_checkpoint_tests(wt, cfg, k + 1)
        git(["-C", wt, "add", "-A"])
        subprocess.run(["git", "-C", wt, "commit", "--allow-empty",
                        "-m", f"cp{k:02d} reset {cp['id']}"], capture_output=True, text=True)
        reset_sha = git(["-C", wt, "rev-parse", "HEAD"])

        # 6. structural metrics — LOGGING ONLY (analyze recomputes them). Measured
        # over the AGENT commit (base_for_cp..agent), so the log shows the agent's
        # delta. Clean the jscpd scratch dir so it can never leak into a later commit.
        metrics_cur = agent_sha or "HEAD"
        mrow, _ = metrics.compute_all(
            wt, arm_cfg, cfg["tools"], base_commit, base_for_cp, metrics_cur,
            exclude=cfg.get("acceptance", {}).get("dest_subpath"))
        row.update(mrow)
        shutil.rmtree(os.path.join(wt, ".jscpd-report"), ignore_errors=True)

        # 7. cold-reader probe. Runs at the checkpoints listed in probe.at_checkpoints
        # (default: the first checkpoint of each phase).
        probe_cfg = cfg.get("probe", {})
        at = probe_cfg.get("at_checkpoints")
        run_probe = (k in at) if at else ((k == 1) or (phase_for(k - 1, n) != phase))
        probe_record = None
        if probe_cfg.get("enabled", True) and run_probe:
            pr = agent.probe(cfg["probe"]["question"], cwd=wt, model=model,
                             expected=cfg["probe"].get("expected"),
                             capture_path=os.path.join(cap_dir, f"cp{k:02d}.probe.jsonl"))
            row.update({
                "probe_cost_usd": round(pr["probe_cost_usd"], 4),
                "probe_input_tokens": pr["probe_input_tokens"],
                "probe_cache_read_tokens": pr["probe_cache_read_tokens"],
                "probe_recall": ("" if pr["probe_recall"] is None else round(pr["probe_recall"], 3)),
            })
            probe_record = pr  # raw probe (text/cost/tokens) goes into the capture record

        # RAW capture for this checkpoint: the irreproducible half (agent envelope,
        # the raw test-result map, build output, pinned/acceptance flags, commit
        # SHAs) referencing the stream + agent-diff files already written to cap_dir.
        rec = capture.checkpoint_record(
            k, cp["id"], phase,
            {"commit": agent_sha, "reset": reset_sha, "preagent": preagent_ref,
             "prev": base_for_cp, "base": base_commit},
            ar, outcome, probe_record, touched_pins, acceptance_touched,
            stream_file, diff_file, build_log_file=build_log_file,
            attempts=attempt_log, spec=cp["spec"], prompt=prompt)
        capture.write_json(os.path.join(cap_dir, f"cp{k:02d}.json"), rec)
        captures.append(rec)
        strict_count += 1 if row["strict_pass"] is True else 0
        regr_count += int(row["regressions"] or 0)

        # Key metrics for this checkpoint, so progress is visible in the logs.
        api_s = round((row.get("duration_api_ms") or 0) / 1000)
        cache_k = (row.get("cache_read_tokens") or 0) // 1000
        print(f"  == {where} | cp{k:02d} [{phase}] {cp['id']} ==")
        print(f"    tests  : strict={row['strict_pass']} iso={row['iso_pass']} core={row['core_pass']} "
              f"regressions={row['regressions']} norm_change={row['normalized_change']} "
              f"build_ok={row['build_ok']} selected={row['total_selected']}")
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
        if str(row.get("pinned_touched", "")).strip():
            flags.append(f"pinned_touched={row['pinned_touched']}")
        if str(row.get("acceptance_touched", "")).strip():
            flags.append(f"acceptance_touched={row['acceptance_touched']}")
        if str(row.get("notes", "")).strip():
            flags.append(f"notes={str(row['notes'])[:100]}")
        if flags:
            print("    flags  : " + "  ".join(flags))

        # Files the agent changed this checkpoint = COMMIT 1's diff (base_for_cp..
        # agent), minus the injected acceptance test, so progress is visible.
        accept_dir = cfg.get("acceptance", {}).get("dest_subpath")
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

    # Final commit on the evolve branch: persist ONLY the raw capture + provenance
    # (nothing derived, nothing goes to the harness repo). The commit message
    # carries a derived one-liner for at-a-glance history — text only, not data.
    prov = capture.provenance(cfg, run_id, model, HARNESS_DIR, extra={
        "arm": arm, "strategy": strategy, "chain": chain, "branch": branch,
        "base_ref": arm_cfg["base_ref"], "base_commit": base_commit,
        "checkpoint_shas": {c["checkpoint"]: c["commit_sha"] for c in captures},
    })
    n_done = len(captures)
    headline = (f"checkpoints={n_done} strict_pass={strict_count}/{n_done} "
                f"regressions={regr_count} (derived numbers recomputed by analyze)")
    commit_chain_results(wt, branch, run_id, arm, strategy, chain, cap_dir, prov, headline,
                         snapshot=cfg.get("_snapshot"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--arm", action="append", help="restrict to arm(s); default all")
    ap.add_argument("--strategy", help="override active prompt strategy")
    ap.add_argument("--chain", type=int, help="run a single chain index")
    ap.add_argument("--max-checkpoints", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-id", help="ties branches + results to this run "
                    "(default: current time as YYYYMMDDHHMM)")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d%H%M")

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

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
    cfg["paths"]["results_csv"] = resolve(cfg["paths"]["results_csv"])
    if cfg.get("tools", {}).get("astgrep_rules"):
        cfg["tools"]["astgrep_rules"] = resolve(cfg["tools"]["astgrep_rules"])
    if cfg.get("acceptance", {}).get("src_dir"):
        cfg["acceptance"]["src_dir"] = resolve(cfg["acceptance"]["src_dir"])

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

    # The run persists NO derived CSV — only raw capture onto the evolve branches.
    # Interleave arms per chain: spring/chain0, officefloor/chain0, spring/chain1,
    # ... so the two arms are matched in time (no temporal confound) and a run cut
    # short still has both arms for the chains it completed.
    for chain in chains:
        for arm in arms:
            run_chain(cfg, arm, strategy, chain, run_id, checkpoints,
                      args.dry_run, args.max_checkpoints)

    if args.dry_run:
        return 0
    print(f"\nRaw capture written to branches: evolve/{run_id}/{strategy}/<arm>/chain<n> in each repo")
    print(f"Next: python -m harness.analyze --config {args.config} --run-id {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
