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

import yaml

from . import agent, correctness, metrics

CSV_FIELDS = [
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


def make_worktree(arm_cfg: dict, work_root: str, arm: str, strategy: str, chain: int) -> str:
    repo = arm_cfg["repo"]
    base_ref = arm_cfg["base_ref"]
    wt = os.path.join(work_root, f"{arm}-{strategy}-chain{chain}")
    branch = f"evolve/{arm}/{strategy}/chain{chain}"
    if os.path.isdir(wt):
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                       capture_output=True, text=True)
        shutil.rmtree(wt, ignore_errors=True)
    subprocess.run(["git", "-C", repo, "branch", "-D", branch], capture_output=True, text=True)
    os.makedirs(work_root, exist_ok=True)
    git(["-C", repo, "worktree", "add", "-b", branch, wt, base_ref])
    return wt


def build_prompt(strategy_template: str, spec: str) -> str:
    return strategy_template.replace("{spec}", spec)


def run_chain(cfg: dict, arm: str, strategy: str, chain: int,
              checkpoints: list[dict], writer, dry_run: bool, max_cp: int | None) -> None:
    arm_cfg = cfg["arms"][arm]
    model = cfg["model"]
    n = len(checkpoints)
    template = cfg["prompt_strategies"][strategy]

    if dry_run:
        print(f"[dry-run] {arm}/{strategy}/chain{chain}: {n} checkpoints from "
              f"{arm_cfg['repo']}@{arm_cfg['base_ref']}")
        for cp in checkpoints[: (max_cp or n)]:
            print(f"    cp{cp['n']:02d} [{phase_for(cp['n'], n)}] {cp['id']}")
        return

    wt = make_worktree(arm_cfg, cfg["paths"]["work_root"], arm, strategy, chain)
    print(f"\n=== {arm}/{strategy}/chain{chain}  worktree={wt} ===")

    prior_passing: set[str] = set()
    prev_ref = "HEAD"  # base commit of the worktree

    limit = max_cp or n
    for cp in checkpoints[:limit]:
        k = cp["n"]
        phase = phase_for(k, n)
        row = {f: "" for f in CSV_FIELDS}
        row.update({"arm": arm, "strategy": strategy, "chain": chain,
                    "checkpoint": k, "checkpoint_id": cp["id"], "phase": phase})

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

        # 2. commit whatever the agent produced so blast radius/regression work
        git(["-C", wt, "add", "-A"])
        commit = subprocess.run(["git", "-C", wt, "commit", "-m", f"cp{k:02d} {cp['id']}"],
                                capture_output=True, text=True)
        committed = commit.returncode == 0  # no-op commit if agent changed nothing

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
        br = metrics.blast_radius(wt, prev_ref if not committed else "HEAD~1", "HEAD")
        row.update({
            "erosion": round(metrics.erosion(fns), 4),
            "verbosity": ("" if vscore != vscore else round(vscore, 4)),  # NaN -> blank
            "java_loc": loc,
            "yaml_loc": yaml_loc(wt, arm_cfg.get("yaml_globs", [])),
        })
        row.update(hs)
        row.update(fp)
        row.update(br)
        prev_ref = "HEAD"

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

        writer.writerow(row)
        print(f"  cp{k:02d} [{phase:5}] cost=${row['cost_usd']:<6} "
              f"strict={row['strict_pass']} erosion={row['erosion']} "
              f"regr={row['regressions']} hotspotCC={row.get('hotspot_cc')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--arm", action="append", help="restrict to arm(s); default all")
    ap.add_argument("--strategy", help="override active prompt strategy")
    ap.add_argument("--chain", type=int, help="run a single chain index")
    ap.add_argument("--max-checkpoints", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    with open(cfg["checkpoints_file"]) as fh:
        checkpoints = yaml.safe_load(fh)["checkpoints"]
    for i, cp in enumerate(checkpoints, 1):
        cp["n"] = i

    arms = args.arm or list(cfg["arms"].keys())
    strategy = args.strategy or cfg["active_strategy"]
    chains = [args.chain] if args.chain is not None else range(cfg["chains"])

    csv_path = cfg["paths"]["results_csv"]
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    new_file = not os.path.isfile(csv_path)
    with open(csv_path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for arm in arms:
            for chain in chains:
                run_chain(cfg, arm, strategy, chain, checkpoints, writer,
                          args.dry_run, args.max_checkpoints)
                fh.flush()
    if not args.dry_run:
        print(f"\nWrote results to {csv_path}\nNext: python -m harness.analyze --config {args.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
