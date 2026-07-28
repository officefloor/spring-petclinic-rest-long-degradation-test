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
import os
import shutil
import subprocess
import sys
from datetime import datetime

import yaml

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
    # structure
    "erosion", "verbosity", "java_loc", "yaml_loc",
    "hotspot_nloc", "hotspot_cc", "fn_count", "fn_nloc_avg", "fn_nloc_max", "fn_cc_max",
    "diff_added", "diff_removed", "files_touched",
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


def restore_acceptance_tests(wt: str, cfg: dict, k: int) -> list[str]:
    """Detect and undo any agent edits to the experimenter-owned acceptance tests
    (cp01..cpK + shared infra). Returns the list of files the agent changed or
    deleted; the authored version is rewritten so a weakened test can never let a
    checkpoint pass.
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
            os.makedirs(dest, exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(authored)
    return tampered


def commit_chain_results(wt: str, branch: str, run_id: str, arm: str, strategy: str,
                         chain: int, rows: list[dict], probe_texts: list[dict] | None = None) -> None:
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
    print(f"\n=== {arm}/{strategy}/chain{chain}  branch={branch}  worktree={wt} ===")

    prior_passing: set[str] = set()
    chain_rows: list[dict] = []
    probe_texts: list[dict] = []

    limit = max_cp or n
    for cp in checkpoints[:limit]:
        k = cp["n"]
        phase = phase_for(k, n)
        row = {f: "" for f in CSV_FIELDS}
        row.update({"run_id": run_id, "branch": branch,
                    "arm": arm, "strategy": strategy, "chain": chain,
                    "checkpoint": k, "checkpoint_id": cp["id"], "phase": phase})

        # 0. Inject ONLY this checkpoint's acceptance test (+ shared infra at
        # cp01). The agent then sees cp01..cpK, never future requirements. It is
        # NOT a separate commit -- it folds into this checkpoint's single commit.
        inject_checkpoint_tests(wt, cfg, k)

        # 1. agent turn (fresh session, no carried context)
        prompt = build_prompt(template, cp["spec"])
        ar = agent.run_agent(prompt, cwd=wt, model=model,
                             timeout=cfg.get("agent_timeout", 3600))
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

        # 1c. Acceptance tests are experimenter-owned. Report if the agent edited
        # any and restore the authored version BEFORE the gate/commit, so a
        # weakened test can never let a checkpoint pass.
        row["acceptance_touched"] = ",".join(restore_acceptance_tests(wt, cfg, k))

        # 2. one commit per checkpoint: the injected test + the agent's code.
        git(["-C", wt, "add", "-A"])
        commit = subprocess.run(["git", "-C", wt, "commit", "-m", f"cp{k:02d} {cp['id']}"],
                                capture_output=True, text=True)
        committed = commit.returncode == 0

        # 3. correctness gate
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

        # 4. structural metrics (Java production source only)
        fns = metrics.functions(wt, arm_cfg["source_globs"])
        loc = metrics.total_java_loc(fns)
        vscore, _ = metrics.verbosity(wt, arm_cfg.get("verbosity_dirs", ["src/main/java"]),
                                      loc, cfg["tools"])
        hs = metrics.hotspot_stats(fns, (arm_cfg.get("hotspot") or {}).get("file", ""),
                                   (arm_cfg.get("hotspot") or {}).get("methods", []))
        fp = metrics.function_package_stats(wt, arm_cfg.get("function_package_glob"))
        br = metrics.blast_radius(wt, "HEAD~1" if committed else "HEAD", "HEAD",
                                  exclude=cfg.get("acceptance", {}).get("dest_subpath"))
        row.update({
            "erosion": round(metrics.erosion(fns), 4),
            "verbosity": ("" if vscore != vscore else round(vscore, 4)),  # NaN -> blank
            "java_loc": loc,
            "yaml_loc": yaml_loc(wt, arm_cfg.get("yaml_globs", [])),
        })
        row.update(hs)
        row.update(fp)
        row.update(br)

        # 5. cold-reader probe at each phase boundary (first checkpoint of a phase)
        is_boundary = (k == 1) or (phase_for(k - 1, n) != phase)
        if cfg.get("probe", {}).get("enabled", True) and is_boundary:
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
        print(f"  cp{k:02d} [{phase:5}] cost=${row['cost_usd']:<6} "
              f"strict={row['strict_pass']} erosion={row['erosion']} "
              f"regr={row['regressions']} hotspotCC={row.get('hotspot_cc')}")

    # Final commit on the evolve branch: capture this chain's results alongside
    # the code progression it describes (nothing goes to the harness repo).
    commit_chain_results(wt, branch, run_id, arm, strategy, chain, chain_rows, probe_texts)


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
        for arm in arms:
            for chain in chains:
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
        for arm in arms:
            for chain in chains:
                run_chain(cfg, arm, strategy, chain, run_id, checkpoints, writer,
                          args.dry_run, args.max_checkpoints)
                fh.flush()
    print(f"\nWrote results to {csv_path}")
    print(f"Branches (kept for review): evolve/{strategy}/<arm>/chain<n>/{run_id} in each repo")
    print(f"Next: python -m harness.analyze --config {args.config} --run-id {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
