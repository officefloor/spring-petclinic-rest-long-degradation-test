#!/usr/bin/env python3
"""Cluster bootstrap over chains for the intervention spread S and the ratio R.

The point estimates in the paper are a range over the condition means, and a
range carries no uncertainty on its face. This attaches one.

S and R therefore DEPEND ON THE CONDITION SET, and v2 reports two of them.
`--conditions four` ranges over the four external-control levers (the same set
v1 used, though the numbers differ because the measure-calculation bugs were
fixed since v1). `--conditions five` adds `ai-reviewed`, a lever of a different
kind. `--conditions both` (the default) prints each in its own block. A v2
four-condition number is NOT comparable with a v1 table: the analysis was
corrected in between. A five-condition number is not comparable with either.

The resampling unit is the CHAIN, not the checkpoint. Checkpoints within a chain
are successive states of one codebase and are strongly dependent, so resampling
them would treat sixty correlated observations as sixty independent ones and
produce intervals far too narrow. Chains are genuinely independent runs, which
makes them the right cluster. This is the same choice `analyze.bootstrap_slope`
makes for the degradation slopes.

Each condition x arm cell is resampled independently, because chain 3 of one
condition has no relationship to chain 3 of another beyond both being draws from
the same agent.

Usage:
    python -m tools.gallery.bootstrap_ratio
    python -m tools.gallery.bootstrap_ratio --n-boot 50000 --latex
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# The condition set the spread ranges over is a CHOICE, and v2 reports two.
# RUNS_FOUR are the four EXTERNAL-CONTROL levers: the change request alone, a
# plain-language cohesion request, an impact gate, and the disclosed formula.
# Each sits outside the agent's own reasoning and constrains it from without.
# The fifth, ai-reviewed, is a different KIND of lever: a second agent reads the
# change and reasons about cohesion itself, which reaches into a composed
# pipeline in a way no external instruction does. Folding it into the same range
# conflates "how far instruction moves an architecture" with "how far AInative
# review moves it", so the two are reported separately and the default is both.
RUNS_FOUR = [("just-solve", "blind-202608100006"),
             ("cohesion-prompt", "blind-202609160027"),
             ("impact-gated", "blind-202609031757"),
             ("formula-provided", "blind-202609010045")]
RUNS_AIREVIEW = [("ai-reviewed", "blind-202609290948")]
RUNS_FIVE = RUNS_FOUR + RUNS_AIREVIEW
# The three external-control conditions that ran in September, i.e. RUNS_FOUR
# without the August control. The threats section recomputes S/R over just these
# to check that the control's three-week-earlier run date is not carrying the
# result (the "drop the August control" robustness check).
RUNS_SEP3 = RUNS_FOUR[1:]
# Backward-compatible default for importers (e.g. floor_effect) and loaders: the
# full five, so load() reads every run unless told otherwise.
RUNS = RUNS_FIVE


def select_runs(which):
    """Map a --conditions choice to a list of (set-label, runs) pairs."""
    if which == "four":
        return [("four external-control conditions", RUNS_FOUR)]
    if which == "five":
        return [("five conditions (adds ai-reviewed)", RUNS_FIVE)]
    if which == "sep3":
        return [("three September external conditions (drops the August control)",
                 RUNS_SEP3)]
    return [("four external-control conditions", RUNS_FOUR),
            ("five conditions (adds ai-reviewed)", RUNS_FIVE)]


ARMS = ["spring", "officefloor"]

PLACEMENT = ["cum_change_top1", "cum_change_entropy_norm", "cum_change_hhi",
             "ccdist_file_top1", "ck_cbo_mean", "ccdist_file_gini", "total_files",
             "ccdist_file_hhi", "node_cc_median", "wmcdist_class_hhi",
             "propagation_cost"]
AMOUNT = ["halstead_volume", "java_loc", "total_fns", "pmd_cognitive_total",
          "ck_wmc_total", "total_cc"]
# Arrangement metrics that do not separate the architectures. Reported in the
# paper's spread table as a third group, so they go through the same bootstrap.
NONSEPARATING = ["ck_lcom_mean", "ccdist_fn_gini", "cogdist_fn_gini"]


def _f(v):
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


def chain_values(rows, arm, field):
    """One value per chain: that chain's mean over the final phase."""
    per = {}
    for r in rows:
        if r["arm"] != arm or r["phase"] != "Final":
            continue
        v = _f(r.get(field))
        if v is None:
            continue
        per.setdefault(r["chain"], []).append(v)
    return np.array([np.mean(v) for v in per.values() if v])


def _spread(means):
    """S over an axis-0 stack of condition means (axis 0 = condition)."""
    return (np.max(means, axis=0) - np.min(means, axis=0)) / np.abs(np.mean(means, axis=0))


def bootstrap(data, field, n_boot=10000, seed=0, runs=None):
    runs = RUNS if runs is None else runs
    rng = np.random.default_rng(seed)
    cells = {(l, a): chain_values(data[l], a, field)
             for l, _ in runs for a in ARMS}
    if any(len(v) == 0 for v in cells.values()):
        return None
    reps = {}
    point = {}
    for arm in ARMS:
        draws = []
        for l, _ in runs:
            x = cells[(l, arm)]
            idx = rng.integers(0, len(x), size=(n_boot, len(x)))
            draws.append(x[idx].mean(axis=1))
        reps[arm] = _spread(np.array(draws))
        point[arm] = _spread(np.array([[cells[(l, arm)].mean()] for l, _ in runs]))[0]
    R = reps["spring"] / reps["officefloor"]
    return {
        "S_spring": point["spring"], "S_officefloor": point["officefloor"],
        "R": point["spring"] / point["officefloor"],
        "R_lo": float(np.percentile(R, 2.5)), "R_hi": float(np.percentile(R, 97.5)),
        "P_R_gt_1": float((R > 1).mean()),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(_REPO, "results"))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--latex", action="store_true",
                    help="emit the CI column as LaTeX table cells")
    ap.add_argument("--conditions", choices=("four", "five", "both", "sep3"),
                    default="both",
                    help="range S/R over the four external-control conditions, "
                         "the five (adding ai-reviewed), both (default), or sep3 "
                         "(the three September external conditions, dropping the "
                         "August control, for the run-date robustness check)")
    a = ap.parse_args(argv)
    data = load(a.results)

    for set_label, runs in select_runs(a.conditions):
        print(f"########## {set_label} "
              f"({', '.join(l for l, _ in runs)})")
        for name, fields in (("PLACEMENT", PLACEMENT), ("AMOUNT", AMOUNT),
                            ("NON-SEPARATING", NONSEPARATING)):
            print(f"=== {name}")
            excl = 0
            for f_ in fields:
                b = bootstrap(data, f_, a.n_boot, a.seed, runs=runs)
                excl += b["R_lo"] > 1
                if a.latex:
                    print(f"\\texttt{{{f_.replace('_', chr(92) + '_')}}}"
                          f" & {b['S_spring']*100:.0f}\\% & {b['S_officefloor']*100:.0f}\\%"
                          f" & {b['R']:.1f} & [{b['R_lo']:.2f}, {b['R_hi']:.2f}]"
                          f" & {b['P_R_gt_1']*100:.0f}\\% \\\\")
                else:
                    print(f"  {f_:26s} R={b['R']:6.1f}  95% CI [{b['R_lo']:6.2f},{b['R_hi']:7.2f}]"
                          f"  P(R>1)={b['P_R_gt_1']*100:5.1f}%")
            print(f"  {excl}/{len(fields)} with CI entirely above 1\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
