#!/usr/bin/env python3
"""Per-cell table numbers for the paper's NON-spread tables, all five conditions.

The spread tables (S, R, the plasticity ratio) are produced by
`bootstrap_ratio`, `floor_effect` and `plasticity_dist`. Everything else the
paper tabulates -- the amount totals, the complexity ADDED over base, strict and
isolated correctness, the outcome measures, and the escape / duplication / money
paragraphs -- used to be hand-entered literals, which is exactly the drift the
rest of the pipeline warns about. This script derives them from the same five
`records.concat.csv` the spread scripts read, so a v2 number has a generator.

Final phase = rows with phase=='Final' (change requests 49-60). Cell aggregation
is chain-first: each chain's mean over its final-phase checkpoints, then the mean
(and sample SD, ddof=1) over the ten chains, so a chain missing a checkpoint does
not get a smaller vote. This is the aggregation `metric_gallery.phase_mean_by_chain`
and the paper's "(SD)" use.

Difference CIs are a percentile cluster bootstrap over chains: within each cell
the ten chains are resampled with replacement 20,000 times at a fixed seed of 0,
the cell mean recomputed, and the difference recomputed from the resampled means.

Base values (for the ADDED table) are the amount metrics at each arm's base_ref,
measured once by `metrics.compute_all` over a worktree at that commit -- the same
function analyze uses per checkpoint. They are properties of the two fixed base
trees and do not change between runs. To re-measure:

    git -C <arm repo> worktree add --detach /tmp/base <base_ref>
    python -c "import yaml,os; from harness import metrics; \
        c=yaml.safe_load(os.path.expandvars(open('config.yaml').read())); \
        a=c['arms']['spring']; \
        print(metrics.compute_all('/tmp/base', a, c['tools'], 'HEAD','HEAD')[0])"

Usage:
    python -m tools.gallery.paper_cells            # human-readable
    python -m tools.gallery.paper_cells --latex    # LaTeX table rows
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics as st
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.gallery.bootstrap_ratio import RUNS_FOUR, RUNS_FIVE  # noqa: E402

RUNS = RUNS_FIVE
ARMS = ["spring", "officefloor"]
NBOOT = 20000
SEED = 0

# Amount metrics at each arm's base_ref (pre-feature base tree), measured by
# metrics.compute_all. See the module docstring for the re-measurement command.
# pmd_cognitive_total is not defined at the base (no change scope), so the
# cognitive ADDED figure is not reported.
BASE = {
    "spring":      {"total_cc": 404.0, "halstead_volume": 153297.0,
                    "ck_wmc_total": 518.0, "total_files": 55, "total_fns": 278,
                    "java_loc": 1840},
    "officefloor": {"total_cc": 351.0, "halstead_volume": 152798.3,
                    "ck_wmc_total": 431.0, "total_files": 120, "total_fns": 256,
                    "java_loc": 1579, "yaml_loc": 460},
}

AMOUNT = ["total_cc", "halstead_volume", "ck_wmc_total", "pmd_cognitive_total"]
ADDED = ["total_cc", "halstead_volume", "ck_wmc_total"]


def _f(v):
    if v in ("True", "true"):
        return 1.0
    if v in ("False", "false"):
        return 0.0
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def load(results_dir):
    out = {}
    for label, run in RUNS:
        with open(os.path.join(results_dir, run, "records.concat.csv"),
                  newline="", encoding="utf-8") as fh:
            out[label] = list(csv.DictReader(fh))
    return out


def chain_means(rows, arm, field, phase="Final"):
    per = {}
    for r in rows:
        if r["arm"] != arm or r["phase"] != phase:
            continue
        v = _f(r.get(field))
        if v is None:
            continue
        per.setdefault(r["chain"], []).append(v)
    return {c: sum(v) / len(v) for c, v in per.items() if v}


def chain_sums(rows, arm, field):
    """Per-chain SUM over ALL 60 checkpoints (for per-run totals like money)."""
    per = {}
    for r in rows:
        if r["arm"] != arm:
            continue
        v = _f(r.get(field))
        if v is None:
            continue
        per.setdefault(r["chain"], 0.0)
        per[r["chain"]] += v
    return per


def cell(data, label, arm, field):
    cm = list(chain_means(data[label], arm, field).values())
    mean = st.mean(cm) if cm else float("nan")
    sd = st.stdev(cm) if len(cm) > 1 else 0.0
    return mean, sd, len(cm), cm


def tex(s):
    return s.replace("_", r"\_")


def boot_diff(a_vals, b_vals, nboot=NBOOT, seed=SEED):
    """Percentile bootstrap CI for mean(a) - mean(b), resampling each independently."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a_vals, float), np.asarray(b_vals, float)
    da = a[rng.integers(0, len(a), size=(nboot, len(a)))].mean(axis=1)
    db = b[rng.integers(0, len(b), size=(nboot, len(b)))].mean(axis=1)
    d = da - db
    return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def boot_pooled_diff(per_cond_a, per_cond_b, nboot=NBOOT, seed=SEED):
    """CI for the mean over conditions of (mean(a_c) - mean(b_c)).

    Resamples chains within each cell independently, recomputes each condition's
    arm means, averages the per-condition differences, 20,000 times.
    """
    rng = np.random.default_rng(seed)
    point = st.mean([st.mean(a) - st.mean(b) for a, b in zip(per_cond_a, per_cond_b)])
    reps = np.zeros(nboot)
    for a, b in zip(per_cond_a, per_cond_b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        da = a[rng.integers(0, len(a), size=(nboot, len(a)))].mean(axis=1)
        db = b[rng.integers(0, len(b), size=(nboot, len(b)))].mean(axis=1)
        reps += (da - db)
    reps /= len(per_cond_a)
    return point, float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))


def _spread(vals):
    m = st.mean(vals)
    return (max(vals) - min(vals)) / abs(m) if m else float("nan")


def sec_amount(data, latex):
    print("\n## AMOUNT (Table: finished-system amount, final phase)")
    for field in AMOUNT:
        cells = {(l, a): cell(data, l, a, field) for l, _ in RUNS for a in ARMS}
        allmeans = [cells[(l, a)][0] for l, _ in RUNS for a in ARMS
                    if cells[(l, a)][0] == cells[(l, a)][0]]
        spread = _spread(allmeans) if allmeans else float("nan")
        print(f"\n# {field}  spread(all {len(allmeans)} cells) = {spread*100:.0f}%")
        for arm in ARMS:
            row = []
            for l, _ in RUNS:
                m, sd, n, _ = cells[(l, arm)]
                row.append((l, m, sd))
            if latex:
                cellstrs = " & ".join(_fmt(m, sd, field) for _, m, sd in row)
                print(f"\\texttt{{{tex(field)}}} & \\textsc{{{arm[:4]}}} & {cellstrs} \\\\")
            else:
                print(f"  {arm:11s} " + "  ".join(
                    f"{l[:4]}={m:.1f}({sd:.1f})" for l, m, sd in row))


def sec_added(data, latex):
    print("\n## ADDED over base_ref (Table: complexity the 60 rules added)")
    for field in ADDED:
        print(f"\n# {field}")
        for arm in ARMS:
            base = BASE[arm][field]
            row = []
            cond_spread = []
            for l, _ in RUNS:
                m, sd, n, _ = cell(data, l, arm, field)
                row.append((l, m - base, sd))
                cond_spread.append(m - base)
            sp4 = _spread([x for (l, x, _) in row if l in dict(RUNS_FOUR)])
            sp5 = _spread(cond_spread)
            if latex:
                cs = " & ".join(_fmt(a, sd, field) for _, a, sd in row)
                print(f"\\texttt{{{tex(field)}}} & \\textsc{{{arm[:4]}}} & {cs} "
                      f"& {sp4*100:.0f}\\% & {sp5*100:.0f}\\% \\\\")
            else:
                print(f"  {arm:11s} base={base} " + "  ".join(
                    f"{l[:4]}=+{a:.0f}" for l, a, _ in row)
                    + f"   spread4={sp4*100:.0f}% spread5={sp5*100:.0f}%")


def sec_correctness(data, latex):
    print("\n## CORRECTNESS (Table: strict/iso/build + run counts)")
    for l, _ in RUNS:
        for arm in ARMS:
            sm, ssd, n, scm = cell(data, l, arm, "strict_pass")
            am, asd, _, _ = cell(data, l, arm, "strict_pass_adj")
            im, isd, _, _ = cell(data, l, arm, "iso_pass")
            bm, _, _, _ = cell(data, l, arm, "build_ok")
            at0 = sum(1 for x in scm if x == 0)
            hi = sum(1 for x in scm if x >= 0.8)
            if latex:
                print(f"{l} & \\textsc{{{arm[:4]}}} & {sm:.3f} & {am:.3f} & {at0} & {hi} "
                      f"& {im:.3f} & {bm:.3f} \\\\")
            else:
                print(f"  {l:16s} {arm:11s} strict={sm:.3f} adj={am:.3f} at0={at0} >=0.8={hi} "
                      f"iso={im:.3f} build={bm:.3f}")


def sec_outcome(data, latex):
    print("\n## OUTCOME (probe_recall, cost_usd, duration_api_ms) + pooled diff")
    for field, scale in (("probe_recall", 1.0), ("cost_usd", 1.0),
                         ("duration_api_ms", 0.001)):
        print(f"\n# {field}" + ("  (shown x1000 -> seconds)" if scale != 1 else ""))
        per_sp, per_of = [], []
        for l, _ in RUNS:
            sm, ssd, _, scm = cell(data, l, "spring", field)
            om, osd, _, ocm = cell(data, l, "officefloor", field)
            per_sp.append(scm)
            per_of.append(ocm)
            if latex:
                print(f"{l} & {sm*scale:.3f} & {ssd*scale:.3f} "
                      f"& {om*scale:.3f} & {osd*scale:.3f} \\\\")
            else:
                print(f"  {l:16s} sp={sm*scale:.3f}({ssd*scale:.3f}) "
                      f"of={om*scale:.3f}({osd*scale:.3f})")
        for setname, idx in (("4", slice(0, 4)), ("5", slice(0, 5))):
            d, lo, hi = boot_pooled_diff(per_sp[idx], per_of[idx])
            sep = sum(1 for a, b in zip(per_sp[idx], per_of[idx])
                      if (lambda r: r[1] > 0 or r[2] < 0)(boot_diff(a, b)))
            print(f"    pooled sp-of over {setname} cond: {d*scale:+.3f} "
                  f"[{lo*scale:+.3f}, {hi*scale:+.3f}]  "
                  f"(per-cond separating: {sep}/{len(per_sp[idx])})")


def sec_paragraphs(data, latex):
    print("\n## PARAGRAPHS: escape / duplication / money")
    print("\n# container_total (escape from the call graph)")
    for l, _ in RUNS:
        sm, ssd, _, _ = cell(data, l, "spring", "container_total")
        om, osd, _, _ = cell(data, l, "officefloor", "container_total")
        print(f"  {l:16s} sp={sm:.1f}({ssd:.1f})  of={om:.1f}({osd:.1f})")
    print("\n# duplication: dup_lines (abs) and dup_density")
    for field in ("dup_lines", "dup_density"):
        print(f"  [{field}]")
        for l, _ in RUNS:
            sm, ssd, _, _ = cell(data, l, "spring", field)
            om, osd, _, _ = cell(data, l, "officefloor", field)
            print(f"    {l:16s} sp={sm:.3f}({ssd:.3f})  of={om:.3f}({osd:.3f})")
    print("\n# money: per-RUN cost_usd (sum over 60 cp, mean over chains)")
    tot = 0.0
    for l, _ in RUNS:
        for arm in ARMS:
            sums = list(chain_sums(data[l], arm, "cost_usd").values())
            m = st.mean(sums)
            tot += sum(sums)
            print(f"  {l:16s} {arm:11s} ${m:.2f}/run")
    print(f"  TOTAL implement-turn spend over all {len(RUNS)*2} cells: ${tot:,.0f}")


def sec_convergence(data, latex):
    print("\n## CONVERGENCE CIs (percentile bootstrap over chains, 20k)")
    metrics_c = ["cum_change_top1", "ccdist_file_top1", "ccdist_file_hhi",
                 "wmcdist_class_hhi", "cum_change_entropy_norm"]
    print("\n# A) spring formula-provided  vs  officefloor just-solve (external control brings mutative arm to additive arm's rest)")
    for field in metrics_c:
        sc, _, _, _ = cell(data, "just-solve", "spring", field)
        _, _, _, a = cell(data, "formula-provided", "spring", field)
        _, _, _, b = cell(data, "just-solve", "officefloor", field)
        d, lo, hi = boot_diff(a, b)
        verdict = "tie" if lo <= 0 <= hi else ("sp-ahead" if d < 0 else "of-ahead")
        print(f"  {field:26s} spCtl={sc:.3f} spF={st.mean(a):.3f} ofCtl={st.mean(b):.3f} "
              f"diff={d:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict}")
    print("\n# B) officefloor ai-reviewed  vs  officefloor just-solve (AI review moves the ADDITIVE arm)")
    for field in metrics_c:
        _, _, _, a = cell(data, "ai-reviewed", "officefloor", field)
        _, _, _, b = cell(data, "just-solve", "officefloor", field)
        d, lo, hi = boot_diff(a, b)
        verdict = "moved" if not (lo <= 0 <= hi) else "tie"
        print(f"  {field:26s} ofCtl={st.mean(b):.3f} ofAI={st.mean(a):.3f} "
              f"diff={d:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict}")


def sec_erosion(data, latex):
    """The borrowed SlopCodeBench erosion measure at two scopes, final phase
    (Table tab:erosion). The CI is OF - Spring (additive minus mutative), the sign
    the paper table uses. For the whole-app `erosion` and the `erosion_hot_fns`
    count, lower is better, so a POSITIVE interval is the additive arm scoring
    worse. For `erosion_handler` the additive arm is identically zero, so a
    NEGATIVE interval is the mutative arm's own handler class eroding. The
    decomposition sentence in the subsection (total/over-threshold/in-handler
    mass) is emitted too, from the control run."""
    print("\n## EROSION (borrowed SlopCodeBench measure, final phase; CI = OF - Spring)")
    for field in ("erosion", "erosion_handler", "erosion_hot_fns"):
        print(f"\n# {field}")
        for l, _ in RUNS:
            sm, ssd, _, scm = cell(data, l, "spring", field)
            om, osd, _, ocm = cell(data, l, "officefloor", field)
            _, lo, hi = boot_diff(ocm, scm)
            sep = "yes" if (lo > 0 or hi < 0) else "no"
            if latex:
                print(f"\\texttt{{{tex(l)}}} & {sm:.3f} ({ssd:.3f}) & {om:.3f} ({osd:.3f}) "
                      f"& $[{lo:+.3f}, {hi:+.3f}]$ & {sep} \\\\")
            else:
                print(f"  {l:16s} sp={sm:.3f}({ssd:.3f}) of={om:.3f}({osd:.3f}) "
                      f"OF-S=[{lo:+.3f},{hi:+.3f}] {sep}")
    print("\n# mass decomposition, control run (just-solve), final phase")
    for arm in ARMS:
        hm, _, _, _ = cell(data, "just-solve", arm, "erosion_high_mass")
        tm, _, _, _ = cell(data, "just-solve", arm, "erosion_total_mass")
        hh, _, _, _ = cell(data, "just-solve", arm, "erosion_handler_high_mass")
        frac = 100 * hh / hm if hm else 0.0
        print(f"  {arm:11s} total_mass={tm:.0f} over_threshold={hm:.0f} "
              f"in_handler={hh:.1f} ({frac:.0f}% of over-threshold)")


def sec_prose(data, latex):
    """Inline prose numbers that are stated in the text but sit in no table, so
    they would otherwise have no generator and could drift silently (which is how
    the erosion CIs and the escape SD drifted before this section existed).

    - ck_lcom_mean per condition per arm. The spread section notes that cohesion,
      the thing the plain-language prompt asked for by name, separates the arms
      least and improves most under the condition that never named it. The prose
      cites the mutative arm's control, cohesion-prompt and formula-provided
      values, so all five are printed for both arms.
    - base-tree file count per arm, cited in the amount section ("404 ... across
      55 files and the additive arm 351 across 120"). Read from BASE; the
      re-measurement command is in the module docstring."""
    print("\n## PROSE numbers stated in the text but not in any table")
    print("\n# ck_lcom_mean by condition (final phase, mean over chains)")
    for arm in ARMS:
        cells = "  ".join(f"{l[:4]}={cell(data, l, arm, 'ck_lcom_mean')[0]:.1f}"
                          for l, _ in RUNS)
        print(f"  {arm:11s} {cells}")
    print("\n# base-tree file count per arm (from BASE; re-measure per the docstring)")
    for arm in ARMS:
        print(f"  {arm:11s} total_files={BASE[arm]['total_files']}")

    print("\n# isolated pass rate pooled over every checkpoint of every run")
    ok = tot = 0
    for l, _ in RUNS:
        for r in data[l]:
            v = _f(r.get("iso_pass"))
            if v is not None:
                tot += 1
                ok += v == 1.0
    print(f"  iso_pass = {ok}/{tot} = {100*ok/tot:.2f}% of checkpoints")

    print("\n# quality gate firings (a checkpoint where ig_refactors > 0)")
    for l in ("impact-gated", "formula-provided"):
        rows = data[l]
        fired = sum(1 for r in rows if (_f(r.get("ig_refactors")) or 0) > 0)
        print(f"  {l:16s} {fired} of {len(rows)} checkpoints")

    print("\n# additive-arm wiring and Java lines (officefloor), final phase")
    byaml = BASE["officefloor"]["yaml_loc"]
    bjava = BASE["officefloor"]["java_loc"]
    yam = [cell(data, l, "officefloor", "yaml_loc")[0] for l, _ in RUNS]
    jav = [cell(data, l, "officefloor", "java_loc")[0] for l, _ in RUNS]
    print(f"  base yaml_loc={byaml}  finish yaml_loc {min(yam):.0f} to {max(yam):.0f}"
          f"  -> yaml added {min(yam)-byaml:.0f} to {max(yam)-byaml:.0f}")
    print(f"  base java_loc={bjava}  -> java added {min(jav)-bjava:.0f} to {max(jav)-bjava:.0f}")


def _fmt(m, sd, field):
    if field == "halstead_volume":
        return f"{m:,.0f} ({sd:,.0f})"
    return f"{m:.0f} ({sd:.0f})"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(_REPO, "results"))
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--only", default="", help="comma list: amount,added,correctness,outcome,paragraphs,convergence,erosion,prose")
    a = ap.parse_args(argv)
    data = load(a.results)
    want = set(a.only.split(",")) if a.only else None
    secs = [("amount", sec_amount), ("added", sec_added),
            ("correctness", sec_correctness), ("outcome", sec_outcome),
            ("paragraphs", sec_paragraphs), ("convergence", sec_convergence),
            ("erosion", sec_erosion), ("prose", sec_prose)]
    for name, fn in secs:
        if want is None or name in want:
            fn(data, a.latex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
