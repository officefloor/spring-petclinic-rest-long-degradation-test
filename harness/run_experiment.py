"""PetClinic-Evolve driver.

For each (arm, prompt-strategy, chain) it creates an isolated git worktree at the
arm's pre-feature base ref, then walks the ordered checkpoints. At each
checkpoint it:

  1. runs a FRESH headless agent with only the checkpoint spec (no carried
     context) -- SlopCodeBench's iterative-extension condition;
  2. commits, then gates on build + the accumulated acceptance suite cp01..cpK;
  3. scores correctness (Strict/ISO/Core, Normalized Change, regressions);
  4. computes structural metrics (Erosion, Verbosity, hotspot/fn-package,
     blast radius) over Java production source only;
  5. at phase boundaries, runs the read-only cold-reader probe;
  6. appends one row to the results CSV.

Usage:
  python -m harness.run_experiment --config config.yaml
  python -m harness.run_experiment --config config.yaml --arm spring --chain 0
  python -m harness.run_experiment --config config.yaml --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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

from . import agent, correctness, expand_path, metrics

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


def yaml_loc(root: str, globs: list[str]) -> int:
    import glob as _glob
    total = 0
    for g in globs:
        for path in _glob.glob(os.path.join(root, g), recursive=True):
            if path.endswith((".yml", ".yaml")) and os.path.isfile(path):
                with open(path, errors="ignore") as fh:
                    total += sum(1 for line in fh if line.strip() and not line.strip().startswith("#"))
    return total


def make_worktree(arm_cfg: dict, work_root: str, arm: str, strategy: str,
                  chain: int, run_id: str) -> tuple[str, str]:
    """Branch a fresh, run-tied line of history from the (untouched) base_ref.

    The base branch (e.g. spring-compare) is only ever READ as a start point; it
    is never checked out here and never has commits added to it. All checkpoint
    commits land on the new `evolve/<strategy>/<arm>/chain<n>/<run_id>` branch,
    which is kept after the run so reviewers can walk the progression.
    """
    repo = arm_cfg["repo"]
    base_ref = arm_cfg["base_ref"]
    branch = f"evolve/{strategy}/{arm}/chain{chain}/{run_id}"
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


def wait_for_window(ar, cfg: dict) -> None:
    """Sleep until the token window is expected to reopen, then return so the
    caller can retry. Uses the parsed reset time when available, else a poll
    interval; capped so a single wait can't run away."""
    limits = cfg.get("limits", {})
    secs = _seconds_until_reset(ar.result_text or ar.error)
    secs = secs if secs is not None else limits.get("poll_seconds", 1800)
    secs = max(60, min(secs, limits.get("max_sleep_seconds", 6 * 3600)))
    resume = datetime.now() + timedelta(seconds=secs)
    print(f"    [limit] token limit reached — waiting {int(secs)}s "
          f"(until ~{resume:%H:%M:%S}) then retrying the same checkpoint...", flush=True)
    time.sleep(secs)


def wait_transient(attempt: int, ar, cfg: dict) -> None:
    """Short exponential backoff for a transient failure (network drop, API
    overload, no completion). Doubles each consecutive attempt up to a cap."""
    limits = cfg.get("limits", {})
    base = limits.get("retry_backoff_seconds", 60)
    cap = limits.get("retry_backoff_max", 900)
    secs = min(base * (2 ** (attempt - 1)), cap)
    resume = datetime.now() + timedelta(seconds=secs)
    reason = (ar.error or ar.result_text or "").strip().splitlines()[0][:120] if (ar.error or ar.result_text) else "no completion"
    print(f"    [retry] transient failure (attempt {attempt}: {reason}) — waiting {int(secs)}s "
          f"(until ~{resume:%H:%M:%S}) then retrying the same checkpoint...", flush=True)
    time.sleep(secs)


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
                         chain: int, rows: list[dict], probe_texts: list[dict] | None = None,
                         metrics_details: list[dict] | None = None) -> None:
    """Write this chain's results into the worktree and make a final commit on
    the evolve branch, so the branch is a self-contained record: the 20
    checkpoint commits followed by one 'results:' commit. Nothing is written to
    the harness repo; everything lives with the code progression it describes.
    """
    if not rows:
        return

    def fnum(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0

    out_dir = os.path.join(wt, "evolve-results")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "records.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    n = len(rows)
    strict = sum(1 for r in rows if r.get("strict_pass") is True)
    regr = sum(int(fnum(r.get("regressions"))) for r in rows)
    cost = sum(fnum(r.get("cost_usd")) for r in rows)
    eros = [fnum(r.get("erosion")) for r in rows if str(r.get("erosion")).strip() != ""]
    e0, ef = (eros[0], eros[-1]) if eros else (float("nan"), float("nan"))
    touched = sum(1 for r in rows if str(r.get("pinned_touched", "")).strip())

    md = [
        f"# Results — {arm}/{strategy}/chain{chain}", "",
        f"- run_id: `{run_id}`",
        f"- branch: `{branch}`",
        f"- checkpoints: {n}",
        f"- strict pass: {strict}/{n}",
        f"- regressions (total): {regr}",
        f"- erosion: {e0:.4g} -> {ef:.4g} (delta {ef - e0:+.4g})",
        f"- cost: ${cost:.2f}",
        f"- CLAUDE.md touched: {touched}/{n} checkpoints", "",
        "| cp | phase | strict | erosion | cost | regr | pinned_touched |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(f"| {r.get('checkpoint')} | {r.get('phase')} | {r.get('strict_pass')} "
                  f"| {r.get('erosion')} | {r.get('cost_usd')} | {r.get('regressions')} "
                  f"| {r.get('pinned_touched')} |")
    with open(os.path.join(out_dir, "summary.md"), "w") as fh:
        fh.write("\n".join(md) + "\n")

    # Preserve the cold-reader probe answers (the one artifact not derivable from
    # the CSV) so recall can be re-graded later from the branch alone.
    for p in (probe_texts or []):
        pdir = os.path.join(out_dir, "probes")
        os.makedirs(pdir, exist_ok=True)
        cp = int(p.get("checkpoint", 0))
        with open(os.path.join(pdir, f"cp{cp:02d}.md"), "w") as fh:
            fh.write(f"# Cold-reader probe @ cp{cp:02d} ({p.get('phase')})\n\n"
                     f"keyword recall: {p.get('recall')}\n\n---\n\n{p.get('text', '')}\n")

    # Raw metric inputs + intermediates per checkpoint, so every erosion/verbosity
    # number can be recomputed by hand from the per-function CC/SLOC and the line
    # counts recorded here.
    for d in (metrics_details or []):
        mdir = os.path.join(out_dir, "metrics")
        os.makedirs(mdir, exist_ok=True)
        with open(os.path.join(mdir, f"cp{int(d.get('checkpoint', 0)):02d}.json"), "w") as fh:
            json.dump(d, fh, indent=2)

    subprocess.run(["git", "-C", wt, "add", "evolve-results"], capture_output=True, text=True)
    msg = (f"results: {arm}/{strategy}/chain{chain} - run {run_id}\n\n"
           f"checkpoints={n} strict_pass={strict}/{n} regressions={regr} "
           f"erosion {e0:.4g}->{ef:.4g} cost ${cost:.2f} claude_md_touched={touched}/{n}")
    c = subprocess.run(["git", "-C", wt, "commit", "-m", msg, "--", "evolve-results"],
                       capture_output=True, text=True)
    print(f"  results commit on {branch}: "
          + ("ok" if c.returncode == 0 else (c.stdout.strip() or c.stderr.strip())[:120]))


def run_chain(cfg: dict, arm: str, strategy: str, chain: int, run_id: str,
              checkpoints: list[dict], writer, dry_run: bool, max_cp: int | None) -> None:
    arm_cfg = cfg["arms"][arm]
    model = cfg["model"]
    n = len(checkpoints)
    template = cfg["prompt_strategies"][strategy]
    branch_preview = f"evolve/{strategy}/{arm}/chain{chain}/{run_id}"

    if dry_run:
        print(f"[dry-run] {arm}/{strategy}/chain{chain}: {n} checkpoints from "
              f"{arm_cfg['repo']}@{arm_cfg['base_ref']} -> branch {branch_preview}")
        for cp in checkpoints[: (max_cp or n)]:
            print(f"    cp{cp['n']:02d} [{phase_for(cp['n'], n)}] {cp['id']}")
        return

    wt, branch = make_worktree(arm_cfg, cfg["paths"]["work_root"], arm, strategy, chain, run_id)
    base_commit = git(["-C", wt, "rev-parse", "HEAD"])  # base_ref commit; subsystem = files changed since
    print(f"\n=== {arm}/{strategy}/chain{chain}  branch={branch}  worktree={wt} ===")

    prior_passing: set[str] = set()
    chain_rows: list[dict] = []
    probe_texts: list[dict] = []
    metrics_details: list[dict] = []

    limit = max_cp or n
    for cp in checkpoints[:limit]:
        k = cp["n"]
        phase = phase_for(k, n)
        row = {f: "" for f in CSV_FIELDS}
        row.update({"run_id": run_id, "branch": branch,
                    "arm": arm, "strategy": strategy, "chain": chain,
                    "checkpoint": k, "checkpoint_id": cp["id"], "phase": phase})
        print(f"\n--- cp{k:02d} [{phase}] {cp['id']} — running agent ---", flush=True)

        # 0. Inject ONLY this checkpoint's acceptance test (+ shared infra at
        # cp01). The agent then sees cp01..cpK, never future requirements. It is
        # NOT a separate commit -- it folds into this checkpoint's single commit.
        inject_checkpoint_tests(wt, cfg, k)

        # Snapshot the pre-agent state (prior commits + the uncommitted cp(K-1)
        # acceptance reset + the just-injected cpK test) as a throwaway commit, so
        # a token-limit-interrupted attempt can be rolled back and retried cleanly.
        git(["-C", wt, "add", "-A"])
        subprocess.run(["git", "-C", wt, "commit", "-q", "--allow-empty",
                        "-m", f"__preagent_cp{k:02d}__"], capture_output=True, text=True)
        preagent_ref = git(["-C", wt, "rev-parse", "HEAD"])
        base_for_cp = git(["-C", wt, "rev-parse", "HEAD~1"])  # = cp(K-1) commit

        # 1. agent turn (fresh session, no carried context). On a token-limit OR a
        # transient failure (network drop, API overload, no completion), discard
        # this attempt, WAIT, then retry the SAME checkpoint from the reset state.
        # Token limits wait for the quota reset; transient failures back off short.
        prompt = build_prompt(template, cp["spec"])
        limits = cfg.get("limits", {})
        attempts = 0
        transient_attempts = 0
        while True:
            ar = agent.run_agent(prompt, cwd=wt, model=model,
                                 timeout=cfg.get("agent_timeout", 3600))
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
                wait_for_window(ar, cfg)
            else:
                transient_attempts += 1
                if transient_attempts > limits.get("max_transient_attempts", 20):
                    raise RuntimeError("too many consecutive transient failures; aborting run")
                wait_transient(transient_attempts, ar, cfg)

        # Undo the snapshot commit (keep its contents staged) so the real cpNN
        # commit below contains the injected test + cp(K-1) reset + the agent work.
        subprocess.run(["git", "-C", wt, "reset", "--soft", base_for_cp],
                       capture_output=True, text=True)

        row.update({"agent_ok": ar.ok, "cost_usd": round(ar.cost_usd, 4),
                    "input_tokens": ar.input_tokens, "cache_read_tokens": ar.cache_read_tokens,
                    "output_tokens": ar.output_tokens, "num_turns": ar.num_turns,
                    "duration_ms": ar.duration_ms, "duration_api_ms": ar.duration_api_ms})
        if ar.error:
            row["notes"] = ar.error[:200]

        # 1b. Pin the leveling docs. CLAUDE.md is a FIXED human-authored project
        # guide that must be identical at every checkpoint (it offsets Spring's
        # training-data advantage for OfficeFloor, symmetrically for both arms).
        # If the agent edited a pinned file we note it and restore the base
        # version BEFORE committing, so the doc can never turn into accumulating
        # cross-checkpoint memory.
        touched_pins = []
        for pf in cfg.get("isolation", {}).get("pin_files", []):
            touched = subprocess.run(["git", "-C", wt, "status", "--porcelain", "--", pf],
                                     capture_output=True, text=True).stdout.strip()
            if touched:
                touched_pins.append(pf)
            restored = subprocess.run(["git", "-C", wt, "checkout", arm_cfg["base_ref"], "--", pf],
                                      capture_output=True, text=True)
            if restored.returncode != 0:  # not in base_ref -> agent created it; drop it
                fpath = os.path.join(wt, pf)
                if os.path.exists(fpath):
                    os.remove(fpath)
        row["pinned_touched"] = ",".join(touched_pins)

        # 1c. Detect (do NOT yet undo) any agent edits to the experimenter-owned
        # acceptance tests, so the commit below preserves exactly what the agent
        # changed about them.
        row["acceptance_touched"] = ",".join(restore_acceptance_tests(wt, cfg, k, write=False))

        # 2. one commit per checkpoint: the injected test + the agent's code,
        # including any acceptance-test edits the agent made (kept for review).
        git(["-C", wt, "add", "-A"])
        commit = subprocess.run(["git", "-C", wt, "commit", "-m", f"cp{k:02d} {cp['id']}"],
                                capture_output=True, text=True)
        committed = commit.returncode == 0

        # 3. Reset the acceptance tests to the authored version -- AFTER the commit
        # (so the agent's edits stay in history) but BEFORE the gate, so a weakened
        # test can never produce a false pass. The reset stays uncommitted and
        # folds into the NEXT checkpoint's commit, so the agent must also satisfy
        # the real (reset) test at the next step.
        restore_acceptance_tests(wt, cfg, k, write=True)

        # 4. correctness gate (runs on the authored tests)
        outcome = correctness.run_tests(wt, k, cfg)
        row.update({
            "build_ok": outcome.build_ok, "total_selected": outcome.total_selected,
            "strict_pass": outcome.all_pass, "iso_pass": outcome.iso_pass,
            "core_pass": outcome.core_all_pass,
            "core_p": outcome.core_pass, "core_t": outcome.core_total,
            "error_p": outcome.error_pass, "error_t": outcome.error_total,
            "func_p": outcome.func_pass, "func_t": outcome.func_total,
            "regr_p": outcome.regr_pass, "regr_t": outcome.regr_total,
        })
        if outcome.error and not row["notes"]:
            row["notes"] = outcome.error[:200]

        target_total = outcome.total_selected
        row["normalized_change"] = round(
            correctness.normalized_change(prior_passing, outcome.passing, target_total), 4)
        row["regressions"] = correctness.count_regressions(prior_passing, outcome.passing)
        prior_passing = outcome.passing

        # 5. structural metrics (Java production source only)
        fns = metrics.functions(wt, arm_cfg["source_globs"])
        loc = metrics.total_java_loc(fns)

        # Dynamic subsystem: production-Java functions in files changed since base.
        # A new class the agent creates shows up in this diff, so neither the
        # scoped erosion nor the hotspot can miss it.
        touched = set(git(["-C", wt, "diff", "--name-only", base_commit, "HEAD"]).splitlines())
        touched_fns = [f for f in fns if f["file"] in touched]

        ed = metrics.erosion_detail(fns)           # whole app (SlopCodeBench-comparable)
        eds = metrics.erosion_detail(touched_fns)  # scoped to the evolving footprint
        vscore, vdetail = metrics.verbosity(wt, arm_cfg.get("verbosity_dirs", ["src/main/java"]),
                                            loc, cfg["tools"])
        hs = metrics.hotspot_stats(touched_fns)     # worst function in the footprint
        fp = metrics.function_package_stats(wt, arm_cfg.get("function_package_glob"))
        prev_ref = "HEAD~1" if committed else "HEAD"
        br = metrics.blast_radius(wt, prev_ref, "HEAD",
                                  exclude=cfg.get("acceptance", {}).get("dest_subpath"))
        brd = metrics.blast_radius_detail(wt, prev_ref, "HEAD")
        wmc = metrics.wmc_stats(touched_fns)                    # god-class over the subsystem
        eh = metrics.entry_handler_stats(fns, arm_cfg.get("entry_handler"))  # whole-app: find it even when unchanged
        spread = metrics.change_spread(wt, prev_ref, "HEAD")
        reedit = metrics.reedit_stats(wt, base_commit, prev_ref, "HEAD")  # temporal coupling vs chain base
        row.update({
            "erosion": ed["erosion"],
            "erosion_high_mass": ed["high_mass"],
            "erosion_total_mass": ed["total_mass"],
            "erosion_hot_fns": ed["over_threshold"],
            "erosion_scoped": eds["erosion"],
            "erosion_scoped_high_mass": eds["high_mass"],
            "erosion_scoped_total_mass": eds["total_mass"],
            "subsystem_nfns": eds["n_functions"],
            "verbosity": ("" if vscore != vscore else round(vscore, 4)),  # NaN -> blank
            "verbosity_clone_lines": vdetail.get("clone_lines", ""),
            "verbosity_pattern_lines": vdetail.get("pattern_lines", ""),
            "verbosity_union_lines": vdetail.get("union_lines", ""),
            "java_loc": loc,
            "yaml_loc": yaml_loc(wt, arm_cfg.get("yaml_globs", [])),
        })
        row.update(hs)
        row.update(fp)
        row.update(br)
        row.update(brd)
        row.update(wmc)
        row.update(eh)
        row.update(spread)
        row.update(reedit)

        # Full raw inputs for this checkpoint (written into the results commit),
        # so every number can be recomputed by hand: per-function CC/SLOC + mass,
        # the erosion terms (whole + scoped), and the exact subsystem file set.
        metrics_details.append({
            "checkpoint": k,
            "erosion": ed,
            "erosion_scoped": eds,
            "subsystem_files": sorted({f["file"] for f in touched_fns}),
            "verbosity": {"value": (None if vscore != vscore else round(vscore, 4)),
                          **vdetail, "java_loc": loc},
            "hotspot": hs,
            "function_package": fp,
            "blast_radius": br,
            "blast_radius_detail": brd,
            "wmc": wmc,
            "entry_handler": eh,
            "change_spread": spread,
            "reedit": reedit,
            "functions": [{**f, "mass": round(metrics.function_mass(f), 4)} for f in fns],
        })

        # 6. cold-reader probe. Runs at the checkpoints listed in probe.at_checkpoints
        # (default: the first checkpoint of each phase).
        probe_cfg = cfg.get("probe", {})
        at = probe_cfg.get("at_checkpoints")
        run_probe = (k in at) if at else ((k == 1) or (phase_for(k - 1, n) != phase))
        if probe_cfg.get("enabled", True) and run_probe:
            pr = agent.probe(cfg["probe"]["question"], cwd=wt, model=model,
                             expected=cfg["probe"].get("expected"))
            row.update({
                "probe_cost_usd": round(pr["probe_cost_usd"], 4),
                "probe_input_tokens": pr["probe_input_tokens"],
                "probe_cache_read_tokens": pr["probe_cache_read_tokens"],
                "probe_recall": ("" if pr["probe_recall"] is None else round(pr["probe_recall"], 3)),
            })
            probe_texts.append({"checkpoint": k, "phase": phase,
                                "recall": pr["probe_recall"], "text": pr.get("probe_text", "")})

        writer.writerow(row)
        chain_rows.append(dict(row))

        # Key metrics for this checkpoint, so progress is visible in the logs.
        api_s = round((row.get("duration_api_ms") or 0) / 1000)
        cache_k = (row.get("cache_read_tokens") or 0) // 1000
        print(f"  == cp{k:02d} [{phase}] {cp['id']} ==")
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

        # Files the agent changed this checkpoint (excluding the injected acceptance
        # test), so progress is visible as the code evolves.
        accept_dir = cfg.get("acceptance", {}).get("dest_subpath")
        pathspec = ["--", ".", f":(exclude){accept_dir}"] if accept_dir else []
        changed = subprocess.run(
            ["git", "-C", wt, "diff", "--name-status", "HEAD~1" if committed else base_commit,
             "HEAD", *pathspec], capture_output=True, text=True).stdout.strip()
        if changed:
            print("    changed:")
            for line in changed.splitlines():
                print(f"      {line}")
        else:
            print("    changed: (no production files)")
        print(flush=True)

    # Final commit on the evolve branch: capture this chain's results alongside
    # the code progression it describes (nothing goes to the harness repo).
    commit_chain_results(wt, branch, run_id, arm, strategy, chain, chain_rows,
                         probe_texts, metrics_details)


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

    with open(cfg["checkpoints_file"]) as fh:
        checkpoints = yaml.safe_load(fh)["checkpoints"]
    for i, cp in enumerate(checkpoints, 1):
        cp["n"] = i

    arms = args.arm or list(cfg["arms"].keys())
    strategy = args.strategy or cfg["active_strategy"]
    chains = [args.chain] if args.chain is not None else range(cfg["chains"])
    print(f"run_id = {run_id}")

    if args.dry_run:
        # Interleave arms per chain: spring/chain0, officefloor/chain0, spring/chain1, ...
        for chain in chains:
            for arm in arms:
                run_chain(cfg, arm, strategy, chain, run_id, checkpoints, None,
                          True, args.max_checkpoints)
        return 0

    # Results live under a per-run directory so each run's data ties to its
    # branches: <results_dir>/<run_id>/records.csv
    results_csv = cfg["paths"]["results_csv"]
    csv_path = os.path.join(os.path.dirname(results_csv), run_id, os.path.basename(results_csv))
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    new_file = not os.path.isfile(csv_path)
    with open(csv_path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        # Interleave arms per chain: spring/chain0, officefloor/chain0, spring/chain1, ...
        # so the two arms are matched in time (no temporal confound) and a run cut
        # short still has both arms for the chains it completed.
        for chain in chains:
            for arm in arms:
                run_chain(cfg, arm, strategy, chain, run_id, checkpoints, writer,
                          args.dry_run, args.max_checkpoints)
                fh.flush()
    print(f"\nWrote results to {csv_path}")
    print(f"Branches (kept for review): evolve/{strategy}/<arm>/chain<n>/{run_id} in each repo")
    print(f"Next: python -m harness.analyze --config {args.config} --run-id {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
