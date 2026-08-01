"""Analysis: phase-binned curves, degradation slopes with bootstrap CIs,
EvoScore, and Zero-Regression Rate. Emits PNG plots and a summary.md.

Headline statistic (SlopCodeBench): the degradation slope m = OLS slope of a
metric on checkpoint index, per arm. The thesis is confirmed if
  m_erosion(Spring) > 0 (CI excludes 0), m_erosion(OfficeFloor) ~ 0, and
  the Spring-minus-OfficeFloor slope CI excludes 0.

EvoScore (SWE-CI): gamma-weighted mean of a per-checkpoint success signal,
gamma >= 1 rewarding staying maintainable late.
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
import tempfile
from collections import defaultdict

import numpy as np
import yaml

from . import correctness, expand_path, metrics
from .run_experiment import CSV_FIELDS, phase_for

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _b(x):
    return str(x).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Re-derivation: the dataset is ALWAYS rebuilt from the checkpoint COMMITS plus
# the raw capture (the run persists nothing derived). This is what lets a metric
# added to metrics.compute_all be computed over OLD runs without re-invoking the
# agent — the expensive part (the commits + capture) is reused.
# ---------------------------------------------------------------------------

_BRANCH_RE = re.compile(r"^evolve/([^/]+)/([^/]+)/([^/]+)/chain(\d+)$")


def _evolve_branches(cfg: dict, run_id: str | None = None):
    """Yield (repo, branch, arm, strategy, chain) across the arm repos."""
    out = []
    for repo in sorted({ac["repo"] for ac in cfg["arms"].values()}):
        refs = subprocess.run(
            ["git", "-C", repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/evolve"],
            capture_output=True, text=True).stdout.splitlines()
        for br in (r.strip() for r in refs if r.strip()):
            m = _BRANCH_RE.match(br)
            if not m:
                continue
            rid, strat, arm, chain = m.groups()
            if run_id and rid != run_id:
                continue
            out.append((repo, br, arm, strat, int(chain)))
    return out


def _latest_run_id(cfg: dict) -> str | None:
    ids = sorted({t[0] for repo, br, *_ in _evolve_branches(cfg)
                  for t in [(_BRANCH_RE.match(br).group(1),)]})
    return ids[-1] if ids else None


def _cp_commits(repo: str, branch: str) -> dict[int, str]:
    """checkpoint number -> commit sha, parsed from the branch's 'cpNN id' commits
    (works even on runs made before the capture layer existed)."""
    out = subprocess.run(["git", "-C", repo, "log", "--format=%H %s", branch],
                         capture_output=True, text=True).stdout
    m: dict[int, str] = {}
    for line in out.splitlines():
        sha, _, subj = line.partition(" ")
        mt = re.match(r"cp0*(\d+)\b", subj)
        if mt:
            m.setdefault(int(mt.group(1)), sha)  # newest listing wins; each cp once
    return m


def _read_captures(repo: str, branch: str) -> dict[int, dict]:
    """checkpoint -> capture record, from evolve-results/capture/cpNN.json on the
    branch (empty for pre-capture runs)."""
    caps: dict[int, dict] = {}
    ls = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", branch, "evolve-results/capture/"],
        capture_output=True, text=True).stdout
    for path in ls.splitlines():
        mt = re.search(r"cp0*(\d+)\.json$", path)
        if not mt:
            continue
        blob = subprocess.run(["git", "-C", repo, "show", f"{branch}:{path}"],
                              capture_output=True, text=True)
        if blob.returncode == 0:
            try:
                caps[int(mt.group(1))] = json.loads(blob.stdout)
            except json.JSONDecodeError:
                pass
    return caps


def recompute_rows(cfg: dict, run_id: str, work_root: str,
                   exclude: str | None = None) -> list[dict]:
    """Rebuild every checkpoint row for `run_id` from its commits + capture.

    Structural metrics come from metrics.compute_all over a detached worktree at
    each checkpoint commit; correctness + agent/probe ephemera come from the raw
    capture. Emits rows keyed identically to run_experiment's CSV_FIELDS, so the
    rest of this module (slopes, plots, EvoScore, ...) is unchanged."""
    rows: list[dict] = []
    rc_root = os.path.join(work_root, "recompute")
    os.makedirs(rc_root, exist_ok=True)
    for repo, branch, arm, strat, chain in _evolve_branches(cfg, run_id):
        arm_cfg = cfg["arms"].get(arm)
        if not arm_cfg:
            continue
        cpmap = _cp_commits(repo, branch)
        if not cpmap:
            continue
        ks = sorted(cpmap)
        n = len(ks)
        base_commit = subprocess.run(
            ["git", "-C", repo, "rev-parse", f"{cpmap[ks[0]]}~1"],
            capture_output=True, text=True).stdout.strip()
        caps = _read_captures(repo, branch)
        prior_passing: set[str] = set()
        for k in ks:
            sha = cpmap[k]
            prev = cpmap.get(k - 1, base_commit)
            cap = caps.get(k) or {}
            row = {f: "" for f in CSV_FIELDS}
            row.update({
                "run_id": run_id, "branch": branch, "arm": arm, "strategy": strat,
                "chain": chain, "checkpoint": k,
                "checkpoint_id": cap.get("checkpoint_id", ""),
                "phase": cap.get("phase") or phase_for(k, n),
            })

            # DERIVE: structural metrics from the checkpoint commit (materialised
            # in a throwaway detached worktree — cheap; no build/agent involved).
            wt = os.path.join(rc_root, f"{arm}_{strat}_c{chain}_cp{k:02d}")
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "-C", repo, "worktree", "prune"],
                           capture_output=True, text=True)
            add = subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", wt, sha],
                                 capture_output=True, text=True)
            try:
                if add.returncode == 0:
                    mrow, _ = metrics.compute_all(wt, arm_cfg, cfg["tools"],
                                                  base_commit, prev, "HEAD", exclude=exclude)
                    row.update(mrow)
                else:
                    print(f"    ! worktree add failed for {branch} cp{k:02d}: "
                          f"{add.stderr.strip()[:120]}")
            finally:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                               capture_output=True, text=True)
                shutil.rmtree(wt, ignore_errors=True)

            # DERIVE: correctness from the RAW captured test-result map.
            tests = cap.get("tests") or {}
            results = tests.get("results")
            if results is not None:
                outcome = correctness.score_results(results, k)
                row.update({
                    "build_ok": tests.get("build_ok"),
                    "total_selected": outcome.total_selected,
                    "strict_pass": outcome.all_pass, "iso_pass": outcome.iso_pass,
                    "core_pass": outcome.core_all_pass,
                    "core_p": outcome.core_pass, "core_t": outcome.core_total,
                    "error_p": outcome.error_pass, "error_t": outcome.error_total,
                    "func_p": outcome.func_pass, "func_t": outcome.func_total,
                    "regr_p": outcome.regr_pass, "regr_t": outcome.regr_total,
                    "normalized_change": round(correctness.normalized_change(
                        prior_passing, outcome.passing, outcome.total_selected), 4),
                    "regressions": correctness.count_regressions(prior_passing, outcome.passing),
                })
                prior_passing = outcome.passing

            # Ephemera straight from capture (irreproducible; never recomputed).
            ag = cap.get("agent") or {}
            if ag:
                row.update({
                    "agent_ok": ag.get("ok"), "cost_usd": ag.get("cost_usd"),
                    "input_tokens": ag.get("input_tokens"),
                    "cache_read_tokens": ag.get("cache_read_tokens"),
                    "output_tokens": ag.get("output_tokens"),
                    "num_turns": ag.get("num_turns"),
                    "duration_ms": ag.get("duration_ms"),
                    "duration_api_ms": ag.get("duration_api_ms"),
                })
            probe = cap.get("probe")
            if probe:
                pr_recall = probe.get("probe_recall")
                row.update({
                    "probe_cost_usd": probe.get("probe_cost_usd"),
                    "probe_input_tokens": probe.get("probe_input_tokens"),
                    "probe_cache_read_tokens": probe.get("probe_cache_read_tokens"),
                    "probe_recall": ("" if pr_recall is None else round(pr_recall, 3)),
                })
            row["pinned_touched"] = ",".join(cap.get("pinned_touched") or [])
            row["acceptance_touched"] = ",".join(cap.get("acceptance_touched") or [])
            rows.append(row)
        print(f"  recomputed {branch}: {n} checkpoints"
              + ("" if caps else "  (no capture — structural metrics only)"))
    return rows


def group_key(r: dict) -> tuple[str, str]:
    return (r["arm"], r["strategy"])


def series_by_chain(rows: list[dict], field: str) -> dict[int, list[tuple[int, float]]]:
    """chain -> [(checkpoint, value)] sorted, dropping NaNs."""
    out: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r in rows:
        v = _f(r[field])
        if not math.isnan(v):
            out[int(r["chain"])].append((int(r["checkpoint"]), v))
    for c in out:
        out[c].sort()
    return out


def ols_slope(xs: np.ndarray, ys: np.ndarray) -> float:
    if len(xs) < 2:
        return math.nan
    return float(np.polyfit(xs, ys, 1)[0])


def bootstrap_slope(chain_series: dict[int, list[tuple[int, float]]],
                    n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean-curve slope with a bootstrap CI over chains.

    Each replicate resamples chains with replacement, averages the value at each
    checkpoint across the resampled chains, and fits a slope to that mean curve.
    Returns (point_estimate, ci_lo, ci_hi) at 95%.
    """
    chains = list(chain_series.keys())
    if not chains:
        return (math.nan, math.nan, math.nan)

    def mean_curve(sample: list[int]) -> tuple[np.ndarray, np.ndarray]:
        acc: dict[int, list[float]] = defaultdict(list)
        for c in sample:
            for k, v in chain_series[c]:
                acc[k].append(v)
        ks = sorted(acc)
        return np.array(ks, dtype=float), np.array([np.mean(acc[k]) for k in ks])

    xs, ys = mean_curve(chains)
    point = ols_slope(xs, ys)

    rng = np.random.default_rng(seed)
    slopes = []
    for _ in range(n_boot):
        sample = list(rng.choice(chains, size=len(chains), replace=True))
        bx, by = mean_curve(sample)
        s = ols_slope(bx, by)
        if not math.isnan(s):
            slopes.append(s)
    if not slopes:
        return (point, math.nan, math.nan)
    lo, hi = np.percentile(slopes, [2.5, 97.5])
    return (point, float(lo), float(hi))


def phase_means(rows: list[dict], field: str):
    order = ["Start", "Early", "Mid", "Late", "Final"]
    acc = defaultdict(list)
    for r in rows:
        v = _f(r[field])
        if not math.isnan(v):
            acc[r["phase"]].append(v)
    return order, [float(np.mean(acc[p])) if acc[p] else math.nan for p in order]


def evoscore(rows: list[dict], gamma: float, signal: str = "strict_pass") -> float:
    """gamma-weighted mean of a 0/1 (or continuous) success signal over a chain,
    averaged across chains."""
    per_chain = defaultdict(list)
    for r in rows:
        val = 1.0 if signal == "strict_pass" and _b(r[signal]) else \
              (_f(r[signal]) if signal != "strict_pass" else 0.0)
        per_chain[int(r["chain"])].append((int(r["checkpoint"]), val))
    scores = []
    for c, pairs in per_chain.items():
        pairs.sort()
        num = sum(gamma ** i * v for i, (_, v) in enumerate(pairs))
        den = sum(gamma ** i for i, _ in enumerate(pairs))
        if den > 0:
            scores.append(num / den)
    return float(np.mean(scores)) if scores else math.nan


def zero_regression_rate(rows: list[dict]) -> float:
    per_chain = defaultdict(int)
    seen = set()
    for r in rows:
        c = int(r["chain"])
        seen.add(c)
        per_chain[c] += int(_f(r["regressions"]) or 0)
    if not seen:
        return math.nan
    clean = sum(1 for c in seen if per_chain[c] == 0)
    return clean / len(seen)


METRICS_TO_PLOT = [
    ("erosion", "Structural erosion — whole app (SlopCodeBench Eq.3)"),
    ("erosion_scoped", "Structural erosion — touched-file subsystem"),
    ("verbosity", "Verbosity (SlopCodeBench Eq.4)"),
    ("cost_usd", "Cost per checkpoint (USD)"),
    ("duration_api_ms", "API time per checkpoint (ms, model inference)"),
    ("cache_read_tokens", "Cache-read tokens (comprehension proxy)"),
    ("hotspot_cc", "Hotspot cyclomatic complexity"),
    ("fn_nloc_max", "Max composed-function size (OfficeFloor)"),
    ("existing_fns_modified", "Blast radius — pre-existing functions modified per rule"),
    ("files_created", "New production files created per rule"),
    ("wmc_max", "God-class — max Weighted Methods per Class (WMC)"),
    ("entry_cc", "Entry-handler cyclomatic complexity (does the front door bloat)"),
    ("packages_touched", "Change spread — packages touched per rule"),
    ("reedit_rate", "Temporal coupling — share of rewritten lines from prior rules"),
]


def plot_metric(groups: dict, field: str, title: str, out_path: str) -> None:
    if not HAVE_MPL:
        return
    plt.figure(figsize=(7, 4.2))
    any_line = False
    for (arm, strat), rows in sorted(groups.items()):
        cs = series_by_chain(rows, field)
        if not cs:
            continue
        acc = defaultdict(list)
        for c in cs:
            for k, v in cs[c]:
                acc[k].append(v)
        ks = sorted(acc)
        if not ks:
            continue
        mean = [np.mean(acc[k]) for k in ks]
        sd = [np.std(acc[k]) for k in ks]
        line, = plt.plot(ks, mean, marker="o", label=f"{arm}/{strat}")
        plt.fill_between(ks, np.array(mean) - np.array(sd), np.array(mean) + np.array(sd),
                         alpha=0.15, color=line.get_color())
        any_line = True
    if not any_line:
        plt.close()
        return
    plt.title(title)
    plt.xlabel("checkpoint")
    plt.ylabel(field)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130)
    plt.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", help="which run to analyze (default: latest)")
    ap.add_argument("--gammas", default="1,1.5,2")
    args = ap.parse_args()
    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    # Single source of truth: the checkpoint COMMITS + raw capture on the evolve
    # branches. Every derived number is recomputed here (nothing derived is read
    # from the branches), so a metric added to metrics.compute_all applies to every
    # past run without re-invoking the agent.
    for name, arm_cfg in cfg["arms"].items():
        arm_cfg["repo"] = expand_path(arm_cfg["repo"], f"arms.{name}.repo")

    work_root = expand_path(cfg["paths"]["work_root"], "paths.work_root")
    if not os.path.isabs(work_root):
        work_root = os.path.join(os.path.dirname(os.path.abspath(args.config)), work_root)

    run_id = args.run_id or _latest_run_id(cfg)
    if not run_id:
        raise SystemExit("no evolve branches found; run the experiment first")
    rows = recompute_rows(cfg, run_id, work_root,
                          exclude=cfg.get("acceptance", {}).get("dest_subpath"))
    if not rows:
        raise SystemExit(f"no checkpoint commits found for run_id {run_id!r}")
    print(f"run_id {run_id}: recomputed {len(rows)} rows from checkpoint commits")

    # Analysis outputs are local, derived, and gitignored (never committed to the
    # harness repo). A concatenated CSV is written for transparency.
    results_csv = expand_path(cfg["paths"]["results_csv"], "paths.results_csv")
    if not os.path.isabs(results_csv):
        results_csv = os.path.join(os.path.dirname(os.path.abspath(args.config)), results_csv)
    out_root = os.path.join(os.path.dirname(results_csv), str(run_id))
    out_dir = os.path.join(out_root, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_root, "records.concat.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)

    gammas = [float(g) for g in args.gammas.split(",")]
    lines = ["# PetClinic-Evolve results\n"]

    # Degradation slopes (headline)
    lines.append("## Degradation slopes m (OLS of metric on checkpoint; 95% bootstrap CI)\n")
    lines.append("| arm/strategy | metric | slope m | CI low | CI high |")
    lines.append("|---|---|---:|---:|---:|")
    slope_fields = ["erosion", "erosion_scoped", "verbosity", "cost_usd",
                    "cache_read_tokens", "duration_api_ms", "hotspot_cc",
                    "existing_fns_modified", "files_created",
                    "wmc_max", "entry_cc", "packages_touched", "reedit_rate"]
    for gk, grp in sorted(groups.items()):
        for field in slope_fields:
            cs = series_by_chain(grp, field)
            if not cs:
                continue
            m, lo, hi = bootstrap_slope(cs)
            if math.isnan(m):
                continue
            lines.append(f"| {gk[0]}/{gk[1]} | {field} | {m:.4g} | {lo:.4g} | {hi:.4g} |")
    lines.append("")

    # Phase means
    lines.append("## Phase-binned means\n")
    for field in ["erosion", "verbosity", "cost_usd", "strict_pass"]:
        lines.append(f"### {field}")
        lines.append("| arm/strategy | Start | Early | Mid | Late | Final |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for gk, grp in sorted(groups.items()):
            if field == "strict_pass":
                order = ["Start", "Early", "Mid", "Late", "Final"]
                acc = defaultdict(list)
                for r in grp:
                    acc[r["phase"]].append(1.0 if _b(r["strict_pass"]) else 0.0)
                vals = [np.mean(acc[p]) if acc[p] else math.nan for p in order]
            else:
                _, vals = phase_means(grp, field)
            cells = " | ".join("" if math.isnan(v) else f"{v:.3g}" for v in vals)
            lines.append(f"| {gk[0]}/{gk[1]} | {cells} |")
        lines.append("")

    # EvoScore + Zero-Regression Rate
    lines.append("## EvoScore (strict_pass) and Zero-Regression Rate\n")
    header = "| arm/strategy | " + " | ".join(f"EvoScore γ={g}" for g in gammas) + " | Zero-Regr Rate |"
    lines.append(header)
    lines.append("|---" * (len(gammas) + 2) + "|")
    for gk, grp in sorted(groups.items()):
        evs = " | ".join(f"{evoscore(grp, g):.3f}" for g in gammas)
        zrr = zero_regression_rate(grp)
        lines.append(f"| {gk[0]}/{gk[1]} | {evs} | {zrr:.3f} |")
    lines.append("")

    # Pinned-doc (CLAUDE.md) touch rate: fraction of checkpoints where the agent
    # tried to edit a pinned leveling doc (its edit was reverted). A behavioural
    # signal, e.g. does one arm lean on CLAUDE.md as memory more than the other.
    lines.append("## Pinned-doc touch rate (share of checkpoints the agent edited a pinned file)\n")
    lines.append("| arm/strategy | touch rate | checkpoints |")
    lines.append("|---|---:|---:|")
    for gk, grp in sorted(groups.items()):
        touched = sum(1 for r in grp if str(r.get("pinned_touched", "")).strip())
        rate = touched / len(grp) if grp else float("nan")
        lines.append(f"| {gk[0]}/{gk[1]} | {rate:.3f} | {touched}/{len(grp)} |")
    lines.append("")

    # Acceptance-tamper rate: share of checkpoints where the agent edited an
    # experimenter-owned acceptance test (restored before scoring). Non-zero means
    # the agent tried to change the tests rather than satisfy them.
    lines.append("## Acceptance-tamper rate (share of checkpoints the agent edited a test)\n")
    lines.append("| arm/strategy | tamper rate | checkpoints |")
    lines.append("|---|---:|---:|")
    for gk, grp in sorted(groups.items()):
        t = sum(1 for r in grp if str(r.get("acceptance_touched", "")).strip())
        rate = t / len(grp) if grp else float("nan")
        lines.append(f"| {gk[0]}/{gk[1]} | {rate:.3f} | {t}/{len(grp)} |")
    lines.append("")

    # Blast radius: how much PRE-EXISTING code each new rule disturbs. The
    # isolation signal. Low existing-fns-modified with rules landing as new files
    # means a requirement is added by ADDITION, not by editing working code. A
    # "zero-blast" checkpoint touched no existing function at all.
    def _num(r, f):
        v = _f(r.get(f))
        return 0.0 if math.isnan(v) else v

    lines.append("## Blast radius (pre-existing code disturbed per rule)\n")
    lines.append("| arm/strategy | existing-fns-modified /chain | zero-blast cps | new-files /chain | churn +/- /chain |")
    lines.append("|---|---:|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        nch = len({int(r["chain"]) for r in grp}) or 1
        fns = sum(_num(r, "existing_fns_modified") for r in grp)
        newf = sum(_num(r, "files_created") for r in grp)
        add = sum(_num(r, "churn_added") for r in grp)
        rem = sum(_num(r, "churn_removed") for r in grp)
        zero = sum(1 for r in grp
                   if str(r.get("existing_fns_modified", "")).strip() != ""
                   and _num(r, "existing_fns_modified") == 0)
        lines.append(f"| {gk[0]}/{gk[1]} | {fns / nch:.1f} | {zero}/{len(grp)} | "
                     f"{newf / nch:.1f} | +{add / nch:.0f}/-{rem / nch:.0f} |")
    lines.append("")

    # God-class, entry-handler bloat, package reach, and temporal coupling. The
    # "final" columns are the last checkpoint's value averaged across chains; the
    # slope table above shows whether each climbs over the chain.
    def _final_mean(grp, field):
        by_chain = {}
        for r in grp:
            by_chain[int(r["chain"])] = r  # rows arrive in checkpoint order; keep last
        vals = [_f(r.get(field)) for r in by_chain.values()]
        vals = [v for v in vals if not math.isnan(v)]
        return float(np.mean(vals)) if vals else math.nan

    lines.append("## God-class, entry-handler, spread, temporal coupling\n")
    lines.append("| arm/strategy | final WMC_max | final entry CC | mean pkgs/rule | mean re-edit rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        wmc_f = _final_mean(grp, "wmc_max")
        ecc_f = _final_mean(grp, "entry_cc")
        pk = [_f(r.get("packages_touched")) for r in grp]
        pk = [v for v in pk if not math.isnan(v)]
        rr = [_f(r.get("reedit_rate")) for r in grp]
        rr = [v for v in rr if not math.isnan(v)]
        cell = lambda v: "" if math.isnan(v) else f"{v:.3g}"
        pk_m = f"{np.mean(pk):.2f}" if pk else ""
        rr_m = f"{np.mean(rr):.3f}" if rr else ""
        lines.append(f"| {gk[0]}/{gk[1]} | {cell(wmc_f)} | {cell(ecc_f)} | {pk_m} | {rr_m} |")
    lines.append("")

    # Plots
    for field, title in METRICS_TO_PLOT:
        out_png = os.path.join(out_dir, f"{field}.png")
        plot_metric(groups, field, title, out_png)
    if HAVE_MPL:
        lines.append("## Plots\n")
        for field, _ in METRICS_TO_PLOT:
            lines.append(f"- `analysis/{field}.png`")

    summary = os.path.join(out_dir, "summary.md")
    with open(summary, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote {summary}" + ("" if HAVE_MPL else "  (matplotlib missing: no PNGs)"))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
