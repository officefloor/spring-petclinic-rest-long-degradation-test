#!/usr/bin/env python3
"""Cluster bootstrap over chains for the intervention spread S and the ratio R.

The point estimates in the paper are a range over four condition means, and a
range carries no uncertainty on its face. This attaches one.

The resampling unit is the CHAIN, not the checkpoint. Checkpoints within a chain
are successive states of one codebase and are strongly dependent, so resampling
them would treat sixty correlated observations as sixty independent ones and
produce intervals far too narrow. Chains are genuinely independent runs, which
makes them the right cluster. This is the same choice `analyze.bootstrap_slope`
makes for the degradation slopes.

Each of the eight cells is resampled independently, because chain 3 of one
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

RUNS = [("just-solve", "blind-202608100006"),
        ("cohesion-prompt", "blind-202609160027"),
        ("impact-gated", "blind-202609031757"),
        ("formula-provided", "blind-202609010045")]
ARMS = ["spring", "officefloor"]

PLACEMENT = ["cum_change_top1", "cum_change_entropy_norm", "cum_change_hhi",
             "ccdist_file_top1", "ck_cbo_mean", "ccdist_file_gini", "total_files",
             "ccdist_file_hhi", "node_cc_median", "wmcdist_class_hhi",
             "propagation_cost"]
AMOUNT = ["halstead_volume", "java_loc", "total_fns", "pmd_cognitive_total",
          "ck_wmc_total", "total_cc"]


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
    """S over an axis-0 stack of four condition means."""
    return (np.max(means, axis=0) - np.min(means, axis=0)) / np.abs(np.mean(means, axis=0))


def bootstrap(data, field, n_boot=10000, seed=0):
    rng = np.random.default_rng(seed)
    cells = {(l, a): chain_values(data[l], a, field)
             for l, _ in RUNS for a in ARMS}
    if any(len(v) == 0 for v in cells.values()):
        return None
    reps = {}
    point = {}
    for arm in ARMS:
        draws = []
        for l, _ in RUNS:
            x = cells[(l, arm)]
            idx = rng.integers(0, len(x), size=(n_boot, len(x)))
            draws.append(x[idx].mean(axis=1))
        reps[arm] = _spread(np.array(draws))
        point[arm] = _spread(np.array([[cells[(l, arm)].mean()] for l, _ in RUNS]))[0]
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
    a = ap.parse_args(argv)
    data = load(a.results)

    for name, fields in (("PLACEMENT", PLACEMENT), ("AMOUNT", AMOUNT)):
        print(f"=== {name}")
        excl = 0
        for f_ in fields:
            b = bootstrap(data, f_, a.n_boot, a.seed)
            excl += b["R_lo"] > 1
            if a.latex:
                print(f"{f_:26s} & {b['R']:.1f} & [{b['R_lo']:.2f}, {b['R_hi']:.2f}] \\\\")
            else:
                print(f"  {f_:26s} R={b['R']:6.1f}  95% CI [{b['R_lo']:6.2f},{b['R_hi']:7.2f}]"
                      f"  P(R>1)={b['P_R_gt_1']*100:5.1f}%")
        print(f"  {excl}/{len(fields)} with CI entirely above 1\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
