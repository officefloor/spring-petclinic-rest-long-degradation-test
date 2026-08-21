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
from collections import defaultdict

import numpy as np
import yaml

from . import correctness, expand_path, git_out, metrics
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
        refs = git_out(repo, ["for-each-ref", "--format=%(refname:short)",
                              "refs/heads/evolve"]).splitlines()
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
    ids = {_BRANCH_RE.match(br).group(1) for _, br, *_ in _evolve_branches(cfg)}
    return max(ids) if ids else None


def _read_blob(repo: str, ref: str, path: str) -> str | None:
    """Content of ``<ref>:<path>``, or None if the path is absent at that ref."""
    p = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def _read_json_blob(repo: str, ref: str, path: str) -> dict | None:
    """Parse ``<ref>:<path>`` as JSON, or None if absent/unparseable."""
    txt = _read_blob(repo, ref, path)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def _cp_commits(repo: str, branch: str) -> dict[int, str]:
    """checkpoint number -> AGENT commit sha, parsed from commit messages (fallback
    for runs without provenance). Prefers the two-commit format's 'cpNN agent ...'
    commit; falls back to the legacy single 'cpNN <id>' commit."""
    out = git_out(repo, ["log", "--format=%H %s", branch])
    agent_m: dict[int, str] = {}
    legacy_m: dict[int, str] = {}
    for line in out.splitlines():
        sha, _, subj = line.partition(" ")
        ma = re.match(r"cp0*(\d+) agent\b", subj)
        if ma:
            agent_m.setdefault(int(ma.group(1)), sha)
            continue
        ml = re.match(r"cp0*(\d+)\b", subj)
        if ml and " reset " not in f" {subj} ":
            legacy_m.setdefault(int(ml.group(1)), sha)
    return agent_m or legacy_m


def _read_captures(repo: str, branch: str) -> dict[int, dict]:
    """checkpoint -> capture record, from evolve-results/capture/cpNN.json on the
    branch (empty for pre-capture runs)."""
    caps: dict[int, dict] = {}
    ls = git_out(repo, ["ls-tree", "-r", "--name-only", branch, "evolve-results/capture/"])
    for path in ls.splitlines():
        mt = re.search(r"cp0*(\d+)\.json$", path)
        if not mt:
            continue
        rec = _read_json_blob(repo, branch, path)
        if rec is not None:
            caps[int(mt.group(1))] = rec
    return caps


def _read_provenance(repo: str, branch: str) -> dict:
    """The chain's provenance.json (base_commit + tool/agent versions), written up
    front in the manifest commit. The checkpoint->sha map is NOT here; it is derived
    from the per-checkpoint capture records. Empty for pre-provenance runs."""
    return _read_json_blob(repo, branch, "evolve-results/provenance.json") or {}


def _resolve_run_config(live_cfg: dict, run_id: str, tmp_dir: str) -> dict:
    """Config to DERIVE with: prefer the per-run snapshot committed at run time (so
    metrics match how the run was configured), falling back to the live config for
    runs recorded before snapshots existed. Repo filesystem paths always come from
    the live environment; only the metric-shaping fields (globs, thresholds,
    entry-handler regex, ast-grep rules) are taken from the snapshot."""
    branches = _evolve_branches(live_cfg, run_id)
    if not branches:
        return live_cfg
    repo, branch = branches[0][0], branches[0][1]
    snap = _read_blob(repo, branch, "evolve-results/config/config.yaml")
    if snap is None:
        print("  (no per-run config snapshot; deriving with the live config.yaml)")
        return live_cfg
    run_cfg = yaml.safe_load(snap)
    # Repos are filesystem locations — take them from the live environment (matched
    # by arm name), not from the snapshot.
    for name, arm in run_cfg.get("arms", {}).items():
        live_arm = live_cfg.get("arms", {}).get(name)
        arm["repo"] = live_arm["repo"] if live_arm else expand_path(arm.get("repo"), f"arms.{name}.repo")
    # Extract the snapshotted ast-grep rules so Verbosity's pattern component
    # matches the run; if none were snapshotted, fall back to the live rules path.
    rel = "evolve-results/config/astgrep-rules"
    listing = git_out(repo, ["ls-tree", branch, rel]).strip()
    run_cfg.setdefault("tools", {})
    if listing:
        arch = subprocess.run(["git", "-C", repo, "archive", branch, rel], capture_output=True)
        if arch.returncode == 0:
            subprocess.run(["tar", "-x", "-C", tmp_dir], input=arch.stdout)
            run_cfg["tools"]["astgrep_rules"] = os.path.join(tmp_dir, rel)
    else:
        run_cfg["tools"]["astgrep_rules"] = live_cfg.get("tools", {}).get("astgrep_rules", "")
    print(f"  using per-run config snapshot from {branch}")
    return run_cfg


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
        caps = _read_captures(repo, branch)
        prov = _read_provenance(repo, branch)

        # Checkpoint list + per-checkpoint commit SHA. Prefer the per-checkpoint
        # capture records: each carries its OWN `commit_sha` ("" for a no-op turn
        # where the agent changed nothing -> no cpNN commit), so the map lists EVERY
        # checkpoint including no-ops, which parsing commit messages would silently
        # drop. Fall back to the legacy provenance map (older runs stored it there),
        # then to commit messages for pre-capture runs.
        if caps:
            shas = {k: (rec.get("commit_sha") or "") for k, rec in caps.items()}
        elif prov.get("checkpoint_shas"):
            shas = {int(k): (v or "") for k, v in prov["checkpoint_shas"].items()}
        else:
            shas = _cp_commits(repo, branch)
        base_commit = prov.get("base_commit") or ""
        if not shas:
            continue
        ks = sorted(shas)
        n = len(ks)
        if not base_commit:
            first_real = next((shas[k] for k in ks if shas[k]), "")
            base_commit = git_out(repo, ["rev-parse", f"{first_real}~1"]).strip() if first_real else ""
        if not base_commit:
            print(f"    ! {branch}: cannot determine base commit; skipping")
            continue

        prior_passing: set[str] = set()
        prev_tree = base_commit   # tree of the previous checkpoint (base before cp01)
        n_noop = 0
        subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True, text=True)
        for k in ks:
            real = shas.get(k) or ""     # AGENT commit sha; "" => no-op checkpoint
            tree = real or prev_tree     # a no-op reuses the previous checkpoint's tree
            # The agent commit's parent IS the previous reset commit, so diffing the
            # agent commit against its own parent yields the pure agent delta. A
            # no-op diffs the previous tree against itself (zero change).
            prev = f"{real}~1" if real else prev_tree
            if not real:
                n_noop += 1
            cap = caps.get(k) or {}
            row = {f: "" for f in CSV_FIELDS}
            row.update({
                "run_id": run_id, "branch": branch, "arm": arm, "strategy": strat,
                "chain": chain, "checkpoint": k,
                "checkpoint_id": cap.get("checkpoint_id", ""),
                "phase": cap.get("phase") or phase_for(k, n),
            })

            # DERIVE: structural metrics from the checkpoint tree (materialised in a
            # throwaway detached worktree — cheap; no build/agent involved). A no-op
            # reuses the previous tree, so its blast radius vs the previous
            # checkpoint is zero — exactly right.
            wt = os.path.join(rc_root, f"{arm}_{strat}_c{chain}_cp{k:02d}")
            shutil.rmtree(wt, ignore_errors=True)
            add = subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", wt, tree],
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
            prev_tree = tree

            # DERIVE: correctness from the RAW captured test-result map, via the
            # same outcome->row mapping the runner uses. build_ok comes from the
            # capture (a build failure leaves results empty, which score_results
            # can't otherwise distinguish).
            tests = cap.get("tests") or {}
            results = tests.get("results")
            if results is not None:
                outcome = correctness.score_results(results, k)
                outcome.build_ok = tests.get("build_ok", True)
                row["checkpoint_type"] = cap.get("type", "additive")
                row.update(correctness.outcome_row(outcome, prior_passing, cap.get("mutates") or []))
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
              + (f" ({n_noop} no-op)" if n_noop else "")
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


def _bucket_by_checkpoint(chain_series: dict[int, list[tuple[int, float]]],
                          sample: list[int] | None = None) -> dict[int, list[float]]:
    """checkpoint -> [value across the selected chains]. `sample` (chain keys, with
    repeats allowed for a bootstrap replicate) selects/weights which chains; default
    = each chain once. The shared aggregation for the mean curve and the plots."""
    keys = list(chain_series) if sample is None else sample
    acc: dict[int, list[float]] = defaultdict(list)
    for c in keys:
        for k, v in chain_series[c]:
            acc[k].append(v)
    return acc


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
        acc = _bucket_by_checkpoint(chain_series, sample)
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


def _mean_curve_slope(chain_series: dict[int, list[tuple[int, float]]],
                      sample: list[int]) -> float:
    """Slope of the checkpoint-averaged curve over the given (possibly resampled) chains."""
    acc = _bucket_by_checkpoint(chain_series, sample)
    ks = sorted(acc)
    if len(ks) < 2:
        return math.nan
    return ols_slope(np.array(ks, dtype=float), np.array([np.mean(acc[k]) for k in ks]))


def bootstrap_diff_slope(rows_a: list[dict], rows_b: list[dict], field: str,
                         n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Bootstrap CI for slope(A) − slope(B): the PAIRED test the thesis needs.

    Comparing each arm's slope CI to zero separately is not the same as testing that
    the two arms differ; this resamples chains within each arm independently and takes
    the slope difference per replicate. A returned CI that excludes 0 means the two
    arms genuinely degrade at different rates on this metric.
    """
    sa, sb = series_by_chain(rows_a, field), series_by_chain(rows_b, field)
    if not sa or not sb:
        return (math.nan, math.nan, math.nan)
    ka, kb = list(sa), list(sb)
    point = _mean_curve_slope(sa, ka) - _mean_curve_slope(sb, kb)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        da = _mean_curve_slope(sa, list(rng.choice(ka, len(ka), replace=True)))
        db = _mean_curve_slope(sb, list(rng.choice(kb, len(kb), replace=True)))
        if not (math.isnan(da) or math.isnan(db)):
            diffs.append(da - db)
    if not diffs:
        return (point, math.nan, math.nan)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return (point, float(lo), float(hi))


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Tie-averaged ranks (scipy-free, for Spearman)."""
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    return (sums / cnt)[inv]


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return math.nan
    rx, ry = _rankdata(x), _rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return math.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def spearman_ci(rows: list[dict], xf: str, yf: str,
                n_boot: int = 1000, seed: int = 0) -> tuple[float, float, float, int]:
    """Spearman ρ(xf, yf) over checkpoints with a chain-cluster bootstrap CI.

    Chains are the resampling unit (checkpoints within a chain are not independent).
    Returns (rho, ci_lo, ci_hi, n)."""
    by_chain: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        xv, yv = _f(r.get(xf, "")), _f(r.get(yf, ""))
        if not (math.isnan(xv) or math.isnan(yv)):
            by_chain[int(r["chain"])].append((xv, yv))
    chains = [c for c in by_chain if by_chain[c]]
    pts = [p for c in chains for p in by_chain[c]]
    n = len(pts)
    if n < 5:
        return (math.nan, math.nan, math.nan, n)
    rho = _spearman(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        sample = rng.choice(chains, len(chains), replace=True)
        pp = [p for c in sample for p in by_chain[c]]
        if len(pp) >= 5:
            b = _spearman(np.array([p[0] for p in pp]), np.array([p[1] for p in pp]))
            if not math.isnan(b):
                boots.append(b)
    if not boots:
        return (rho, math.nan, math.nan, n)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (rho, float(lo), float(hi), n)


def phase_means(rows: list[dict], field: str):
    order = ["Start", "Early", "Mid", "Late", "Final"]
    acc = defaultdict(list)
    for r in rows:
        v = _f(r[field])
        if not math.isnan(v):
            acc[r["phase"]].append(v)
    return order, [float(np.mean(acc[p])) if acc[p] else math.nan for p in order]


def evoscore(rows: list[dict], gamma: float) -> float:
    """gamma-weighted mean of the 0/1 strict-pass signal over a chain, averaged
    across chains (later checkpoints discounted by gamma**i)."""
    per_chain = defaultdict(list)
    for r in rows:
        val = 1.0 if _b(r["strict_pass"]) else 0.0
        per_chain[int(r["chain"])].append((int(r["checkpoint"]), val))
    scores = []
    for c, pairs in per_chain.items():
        pairs.sort()
        num = sum(gamma ** i * v for i, (_, v) in enumerate(pairs))
        den = sum(gamma ** i for i, _ in enumerate(pairs))
        if den > 0:
            scores.append(num / den)
    return float(np.mean(scores)) if scores else math.nan


def zero_regression_rate(rows: list[dict], field: str = "regressions") -> float:
    per_chain = defaultdict(int)
    seen = set()
    for r in rows:
        c = int(r["chain"])
        seen.add(c)
        per_chain[c] += int(_f(r.get(field)) or 0)
    if not seen:
        return math.nan
    clean = sum(1 for c in seen if per_chain[c] == 0)
    return clean / len(seen)


def regression_summary(rows: list[dict]) -> dict:
    """Totals for the intended-vs-true regression split, plus the count of mutative
    checkpoints (so a reader can see how much cross-cutting pressure the run had)."""
    total = sum(int(_f(r.get("regressions")) or 0) for r in rows)
    true = sum(int(_f(r.get("true_regressions")) or 0) for r in rows)
    n_mut = sum(1 for r in rows if str(r.get("checkpoint_type", "")).strip() == "mutative")
    return {"total": total, "true": true, "intended": total - true, "mutative_cps": n_mut}


METRICS_TO_PLOT = [
    ("erosion", "Structural erosion — whole app (SlopCodeBench Eq.3)"),
    ("erosion_scoped", "Structural erosion — touched-file subsystem"),
    ("erosion_handler", "Structural erosion — entry-handler class only (concentration signal)"),
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
    ("impact_mutation", "Impact — context-weighted mutation of existing functions"),
    ("impact_godclass", "Impact — context-weighted new-function additions"),
    ("impact_composite", "Impact — max(WMC_other,1)·CC·max(1,Δlines)·files per rule"),
]

# The three impact sub-scores, each reported in three slices: all checkpoints (the
# base field), additive-only (`_add`), and mutative-only (`_mut`). The derived view
# columns are synthesised in main() off the base fields (blank on the other type).
IMPACT_BASE_FIELDS = ["impact_mutation", "impact_godclass", "impact_composite"]
_IMPACT_LABEL = {"impact_mutation": "mutation of existing functions",
                 "impact_godclass": "new-function additions",
                 "impact_composite": "composite (max(WMC_other,1)·CC·max(1,Δlines)·files)"}
for _fld in IMPACT_BASE_FIELDS:
    METRICS_TO_PLOT.append((_fld + "_add", f"Impact ({_IMPACT_LABEL[_fld]}) — ADDITIVE checkpoints only"))
    METRICS_TO_PLOT.append((_fld + "_mut", f"Impact ({_IMPACT_LABEL[_fld]}) — MUTATIVE checkpoints only"))


def plot_metric(groups: dict, field: str, title: str, out_path: str) -> None:
    if not HAVE_MPL:
        return
    plt.figure(figsize=(7, 4.2))
    any_line = False
    for (arm, strat), rows in sorted(groups.items()):
        cs = series_by_chain(rows, field)
        if not cs:
            continue
        acc = _bucket_by_checkpoint(cs)
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

    # Everything derived is recomputed here from the commits + capture (see module
    # header); nothing derived is read from the branches.
    for name, arm_cfg in cfg["arms"].items():
        arm_cfg["repo"] = expand_path(arm_cfg["repo"], f"arms.{name}.repo")

    work_root = expand_path(cfg["paths"]["work_root"], "paths.work_root")
    if not os.path.isabs(work_root):
        work_root = os.path.join(os.path.dirname(os.path.abspath(args.config)), work_root)

    run_id = args.run_id or _latest_run_id(cfg)
    if not run_id:
        raise SystemExit("no evolve branches found; run the experiment first")
    # Derive with the run's OWN config snapshot (globs/thresholds/entry-handler/
    # ast-grep rules), so metrics match how that run was configured.
    snap_tmp = os.path.join(work_root, "recompute-config", str(run_id))
    shutil.rmtree(snap_tmp, ignore_errors=True)
    os.makedirs(snap_tmp, exist_ok=True)
    eff_cfg = _resolve_run_config(cfg, run_id, snap_tmp)
    rows = recompute_rows(eff_cfg, run_id, work_root,
                          exclude=eff_cfg.get("acceptance", {}).get("dest_subpath"))
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

    # Impact is reported in three slices — ALL checkpoints, ADDITIVE-only, MUTATIVE-only
    # — so the split can be read directly. The per-checkpoint impact value is the same
    # regardless of slice; the slices are just filtered VIEWS (a mutative checkpoint is a
    # mandated rule revision, and the context weight makes it genuine architectural signal
    # — the arm that isolated the concern pays less: Spring ~36k/mutative-cp vs OfficeFloor
    # ~4.8k on blind-202608100006). Synthesise `_add`/`_mut` view columns off the raw
    # (all-checkpoint) impact fields — blank on the other type, so the generic NaN-dropping
    # slope/plot machinery yields the filtered curve with no special casing. Done after the
    # raw CSV is written, so these derived views never bloat the CSV.
    for r in rows:
        is_mut = str(r.get("checkpoint_type", "")).strip() == "mutative"
        for f in IMPACT_BASE_FIELDS:
            v = r.get(f, "")
            r[f + "_add"] = "" if is_mut else v   # additive-only view
            r[f + "_mut"] = v if is_mut else ""    # mutative-only view

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)

    gammas = [float(g) for g in args.gammas.split(",")]
    lines = ["# PetClinic-Evolve results\n"]

    # Degradation slopes (headline)
    lines.append("## Degradation slopes m (OLS of metric on checkpoint; 95% bootstrap CI)\n")
    lines.append("| arm/strategy | metric | slope m | CI low | CI high |")
    lines.append("|---|---|---:|---:|---:|")
    slope_fields = ["erosion", "erosion_scoped", "erosion_handler", "verbosity", "cost_usd",
                    "cache_read_tokens", "duration_api_ms", "hotspot_cc",
                    "existing_fns_modified", "files_created",
                    "wmc_max", "entry_cc", "packages_touched", "reedit_rate",
                    "impact_mutation", "impact_godclass", "impact_composite"]
    # each impact sub-score also sliced additive-only (_add) and mutative-only (_mut)
    slope_fields += [f + s for f in IMPACT_BASE_FIELDS for s in ("_add", "_mut")]
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

    # Difference of slopes — the PAIRED test (per-arm CIs vs zero are not a between-arm test)
    lines.append("## Difference of slopes (arm A − arm B; 95% bootstrap CI over chains)\n")
    lines.append("A CI that excludes 0 means the two arms degrade at genuinely different rates on "
                 "that metric — the actual between-arm test, not eyeballing two separate CIs.\n")
    lines.append("| strategy | A − B | metric | slope diff | CI low | CI high | excludes 0 |")
    lines.append("|---|---|---|---:|---:|---:|:--:|")
    for strat in sorted({s for (_, s) in groups}):
        arms = [a for (a, s) in groups if s == strat]
        if len(arms) != 2:
            continue
        a1, a2 = (("spring", "officefloor") if {"spring", "officefloor"} <= set(arms)
                  else tuple(sorted(arms, reverse=True)))
        ra, rb = groups[(a1, strat)], groups[(a2, strat)]
        for field in slope_fields:
            d, lo, hi = bootstrap_diff_slope(ra, rb, field)
            if math.isnan(d):
                continue
            excl = "yes" if (lo > 0 or hi < 0) else "no"
            lines.append(f"| {strat} | {a1}−{a2} | {field} | {d:.4g} | {lo:.4g} | {hi:.4g} | {excl} |")
    lines.append("")

    # Impact-metric external validation — does per-checkpoint impact predict independent pain?
    lines.append("## Impact-metric validation (Spearman ρ of `impact_composite` vs independent outcomes)\n")
    lines.append("Within-arm correlation with signals measured *independently* of the git-diff impact "
                 "computation (agent cost/time, comprehension, unintended breakage); 95% CI by chain-cluster "
                 "bootstrap. A construct-validity check: does a change the metric scores as high-impact "
                 "actually cost more and break more?\n")
    lines.append("| arm/strategy | outcome | Spearman ρ | CI low | CI high | n |")
    lines.append("|---|---|---:|---:|---:|---:|")
    OUTCOMES = [("cost_usd", "agent $ (independent)"),
                ("cache_read_tokens", "comprehension (independent)"),
                ("duration_api_ms", "model time (independent)"),
                ("true_regressions", "broke untouched rule (independent)"),
                ("reedit_rate", "temporal coupling (git-derived)")]
    for gk, grp in sorted(groups.items()):
        for field, note in OUTCOMES:
            rho, lo, hi, n = spearman_ci(grp, "impact_composite", field)
            if math.isnan(rho):
                continue
            lines.append(f"| {gk[0]}/{gk[1]} | {note} | {rho:+.3f} | {lo:+.3f} | {hi:+.3f} | {n} |")
    lines.append("")
    lines.append("### `impact_composite` on checkpoints that caused a true regression vs not\n")
    lines.append("| arm/strategy | median (true regression) | median (none) | n true-regr |")
    lines.append("|---|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        wtr = [_f(r.get("impact_composite", "")) for r in grp
               if (_f(r.get("true_regressions", "")) or 0) > 0 and not math.isnan(_f(r.get("impact_composite", "")))]
        ntr = [_f(r.get("impact_composite", "")) for r in grp
               if (_f(r.get("true_regressions", "")) or 0) == 0 and not math.isnan(_f(r.get("impact_composite", "")))]
        if wtr and ntr:
            lines.append(f"| {gk[0]}/{gk[1]} | {np.median(wtr):.0f} | {np.median(ntr):.0f} | {len(wtr)} |")
    lines.append("")

    # Phase means
    lines.append("## Phase-binned means\n")
    for field in ["erosion", "erosion_handler", "impact_mutation", "impact_godclass",
                  "verbosity", "cost_usd", "strict_pass"]:
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

    # Regression split: a mutative checkpoint's changes to prior rules are INTENDED,
    # so its regressions there do not count as faults. true_regressions counts only
    # breakage on the surface the checkpoint was not asked to touch. The true
    # Zero-Regression Rate is the safety signal a purely additive run cannot give.
    lines.append("## Regressions: intended vs. true (un-mutated surface)\n")
    lines.append("| arm/strategy | mutative cps | total regr | intended | true regr | true Zero-Regr Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        rs = regression_summary(grp)
        tzrr = zero_regression_rate(grp, "true_regressions")
        lines.append(f"| {gk[0]}/{gk[1]} | {rs['mutative_cps']} | {rs['total']} | "
                     f"{rs['intended']} | {rs['true']} | {tzrr:.3f} |")
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
