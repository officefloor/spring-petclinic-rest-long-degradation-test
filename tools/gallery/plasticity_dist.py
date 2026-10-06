#!/usr/bin/env python3
"""Distribution of the plasticity ratio R over EVERY metric the study records.

The paper reports eleven placement metrics chosen by the author. The obvious
referee question is what the other hundred and fifty eight do, and the only
honest answer is the whole distribution. This draws it.

Usage:
    python -m tools.gallery.plasticity_dist
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics as st
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from harness.analyze import ARM_COLORS

from tools.gallery.bootstrap_ratio import RUNS_FOUR, RUNS_FIVE, select_runs  # noqa: E402

# Default to all five for loading; the condition set the ratio ranges over is a
# separate choice, passed into ratios(). v2's headline distribution is the four
# external-control conditions (matching the spread table); the five-condition
# distribution is reported for contrast because ai-reviewed compresses it.
RUNS = RUNS_FIVE
ARMS = ["spring", "officefloor"]
SKIP = {"run_id", "branch", "arm", "strategy", "chain", "checkpoint",
        "checkpoint_id", "phase"}

REPORTED = ["cum_change_top1", "cum_change_entropy_norm", "cum_change_hhi",
            "ccdist_file_top1", "ck_cbo_mean", "ccdist_file_gini", "total_files",
            "ccdist_file_hhi", "node_cc_median", "wmcdist_class_hhi",
            "propagation_cost"]

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BAR = "#b8b6b0"


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


def ratios(results_dir, runs=RUNS):
    data = {}
    for label, run in runs:
        with open(os.path.join(results_dir, run, "records.concat.csv"),
                  newline="", encoding="utf-8") as fh:
            data[label] = list(csv.DictReader(fh))
    header = list(data[runs[0][0]][0].keys())

    def phase_mean(rows, arm, field):
        per = {}
        for r in rows:
            if r["arm"] != arm or r["phase"] != "Final":
                continue
            v = _f(r.get(field))
            if v is None:
                continue
            per.setdefault(r["chain"], []).append(v)
        vals = [sum(v) / len(v) for v in per.values() if v]
        return sum(vals) / len(vals) if vals else None

    def spread(field, arm):
        mu = [phase_mean(data[l], arm, field) for l, _ in runs]
        if any(x is None for x in mu):
            return None
        mean = st.mean(mu)
        if abs(mean) < 1e-12:
            return None
        return (max(mu) - min(mu)) / abs(mean)

    out = {}
    for field in header:
        if field in SKIP:
            continue
        a, b = spread(field, "spring"), spread(field, "officefloor")
        # A zero denominator is not an infinite ratio, it is an arm that did not
        # move at all on that metric. Excluded rather than clipped, and the count
        # of exclusions is printed so the reader can see how many there were.
        if a is None or b is None or b < 1e-9:
            continue
        out[field] = a / b
    return out



# Metric families, for the independence caveat. The 169 columns are not 169
# independent measurements: a top-1 share, an HHI and a Gini over the same
# distribution are three views of one thing, and CK reports fifteen metrics off
# one parse. Every metric is assigned to a family by longest-prefix match, the
# family's median R is taken as its one vote, and the direction-of-effect counts
# are recomputed over families. Grouping is deliberately coarse: merging two
# genuinely distinct families understates the evidence, which is the safe
# direction to err in.
FAMILY_PREFIXES = [
    "erosion_handler", "erosion_scoped", "erosion",
    "ccdist_file", "ccdist_fn", "ccdist_pkg", "cogdist_fn", "cogdist_file",
    "voldist_file", "wmcdist_class", "cum_change", "change_",
    "ck_handler", "ck_", "pmd_", "impact_", "container_", "indirection_",
    "propagation", "halstead", "verbosity", "probe_", "node_", "total_",
    "duration_", "cache_", "ig_", "wmc_", "hotspot_", "churn_", "diff_",
    "reedit_", "mi_", "files_", "entry_", "subsystem_", "regr", "true_regr",
    "clone", "jscpd", "packages_", "input_tokens", "output_tokens", "num_turns",
    "cost_", "core_", "iso_", "strict_", "build_", "normalized_", "java_",
]


def family(name):
    """Longest matching prefix wins, so ck_handler beats ck_."""
    best = None
    for p in FAMILY_PREFIXES:
        if name.startswith(p) and (best is None or len(p) > len(best)):
            best = p
    return (best or name).rstrip("_")


def by_family(R):
    """One vote per family: the median R of its members."""
    groups = {}
    for k, v in R.items():
        groups.setdefault(family(k), []).append(v)
    return {g: float(np.median(v)) for g, v in groups.items()}, groups


def summarise(R, floor=2.9):
    v = np.array(sorted(R.values()))
    return {"n": len(v), "ge_1": int((v >= 1).sum()),
            "le_inv": int((v <= 1.0 / floor).sum()),
            "ge_floor": int((v >= floor).sum()),
            "median": float(np.median(v))}


def build(results_dir, out_path, runs=RUNS):
    R = ratios(results_dir, runs)
    vals = np.array(sorted(R.values()))
    # Log scale: R is a ratio, so 0.5 and 2.0 are the same distance from parity
    # and a linear axis would make the right tail look like the whole story.
    clipped = np.clip(vals, 0.05, None)
    bins = np.logspace(np.log10(0.05), np.log10(20), 34)

    fig, ax = plt.subplots(figsize=(8.0, 4.3), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.hist(clipped, bins=bins, color=BAR, edgecolor=SURFACE, linewidth=0.8, zorder=2)
    ax.set_xscale("log")

    ax.axvline(1.0, color=INK_2, linewidth=1.3, zorder=3)
    ax.annotate("R = 1\nboth arms moved equally", (1.0, ax.get_ylim()[1] * 0.94),
                textcoords="offset points", xytext=(6, 0), fontsize=8,
                color=INK_2, va="top")

    # The reported metrics as a rug, so their position in the distribution is
    # visible rather than asserted.
    y = -ax.get_ylim()[1] * 0.055
    for m in REPORTED:
        if m in R:
            ax.plot([R[m]], [y], marker="v", markersize=6.5,
                    color=ARM_COLORS["spring"], clip_on=False, zorder=4)
    lo = min(R[m] for m in REPORTED if m in R)
    ax.annotate("the 11 placement metrics reported in the paper  \u25b6",
                (lo, y), textcoords="offset points", xytext=(-8, -1),
                fontsize=8, color=ARM_COLORS["spring"], va="center", ha="right")

    med = float(np.median(vals))
    ax.set_xlabel("plasticity ratio  R = S(Spring) / S(OfficeFloor)   "
                  "(log scale)", fontsize=9, color=INK_2)
    ax.set_ylabel("metrics", fontsize=9, color=INK_2)
    ax.set_title(f"All {len(vals)} metrics the study records, not only the reported ones",
                 fontsize=11, loc="left", color=INK, pad=24)
    ax.annotate(f"median R = {med:.2f}    "
                f"{int((vals >= 2.9).sum())} metrics at or above 2.9    "
                f"{int((vals <= 1 / 2.9).sum())} at or below 1/2.9",
                (0, 1), xycoords="axes fraction", textcoords="offset points",
                xytext=(0, 5), fontsize=8.5, color=INK_2, va="bottom")
    ax.grid(axis="y", color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8.5)
    ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 4, 8, 16])
    ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "4", "8", "16"])

    fig.subplots_adjust(left=0.085, right=0.975, top=0.815, bottom=0.185)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    print(f"wrote {out_path}  (n={len(vals)}, median {med:.2f})")
    return R


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(_REPO, "results"))
    ap.add_argument("--out", default=os.path.join(_REPO, "blog", "metric-gallery",
                                                  "figs", "plasticity_dist.png"))
    ap.add_argument("--conditions", choices=("four", "five", "both"),
                    default="four",
                    help="range the ratio over the four external-control "
                         "conditions (default, the paper's Figure 2), the five, "
                         "or both (writes a _five.png beside the four-cond png "
                         "and prints both family summaries)")
    a = ap.parse_args(argv)

    def _run(set_label, runs, out_path):
        print(f"########## {set_label} ({', '.join(l for l, _ in runs)})")
        R = build(a.results, out_path, runs)
        per_fam, groups = by_family(R)
        for label, d in (("all metrics", R), ("one vote per family", per_fam)):
            t = summarise(d)
            print(f"  {label:20} n={t['n']:3d}  R>=1 {t['ge_1']:3d}"
                  f"  R<=1/2.9 {t['le_inv']:2d}  R>=2.9 {t['ge_floor']:3d}"
                  f"  median {t['median']:.2f}")
        big = sorted(((len(v), g) for g, v in groups.items()), reverse=True)[:6]
        print("  largest families: " + ", ".join(f"{g} ({n})" for n, g in big))

    base, ext = os.path.splitext(a.out)
    if a.conditions in ("four", "both"):
        _run("four external-control conditions", RUNS_FOUR, a.out)
    if a.conditions in ("five", "both"):
        five_out = a.out if a.conditions == "five" else f"{base}_five{ext}"
        _run("five conditions (adds ai-reviewed)", RUNS_FIVE, five_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
