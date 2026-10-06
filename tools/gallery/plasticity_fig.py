#!/usr/bin/env python3
"""The plasticity figure: how far each intervention moved each architecture.

One figure, two stacked panels, one shared x-axis.

The x-axis is each condition's final-phase value divided by that ARCHITECTURE'S
OWN control value, so 1.0 means "the intervention changed nothing here". That
normalisation is the whole point: it asks how far an architecture moved, not
where it started. The absolute levels are deliberately NOT on this figure,
because a reader would then have to hold two questions at once. They are in the
post's tables instead.

Top panel is the AMOUNT group, where Tesler predicts no movement for either arm.
Bottom panel is the ORGANISATION group, where the thesis predicts movement for
the mutative arm only.

Colour follows the ARCHITECTURE, exactly as in `analyze.py` and
`metric_gallery.py`, so an arm keeps its hue across every figure in the series.
The pair is the already-validated one: adjacent CVD dE 24.7 protan, normal
vision dE 33.6, both at or above 3:1 contrast on this surface.

Usage:
    python -m tools.gallery.plasticity_fig
    python -m tools.gallery.plasticity_fig --out blog/metric-gallery/figs
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics as _st
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from harness.analyze import ARM_COLORS

# Same run mapping as metric_gallery.RUNS. Kept as a literal rather than imported
# so this script has no import-time dependency on the catalogue's style guard.
RUNS = [
    ("just-solve", "blind-202608100006"),
    ("cohesion-prompt", "blind-202609160027"),
    ("impact-gated", "blind-202609031757"),
    ("formula-provided", "blind-202609010045"),
    ("ai-reviewed", "blind-202609290948"),
]
ARMS = ["spring", "officefloor"]
ARM_LABEL = {"spring": "Spring", "officefloor": "OfficeFloor"}
FINAL_PHASE = "Final"

# Marker per condition. Shape is the SECONDARY encoding, so the conditions
# are separable without colour, which colour is already spent on architecture.
# Indexed by position in RUNS, so a condition added there needs a shape added
# here. Asserted rather than cycled: two conditions sharing a shape is a silently
# unreadable figure, which is worse than a failed build.
COND_MARKER = ["o", "s", "^", "D", "v"]
assert len(COND_MARKER) >= len(RUNS), "add a marker shape for the new condition"

AMOUNT = [
    ("total_cc", "Total cyclomatic complexity"),
    ("halstead_volume", "Total Halstead volume"),
    ("ck_wmc_total", "Total weighted methods per class"),
    ("pmd_cognitive_total", "Total cognitive complexity"),
    ("total_fns", "Total functions"),
    ("java_loc", "Java lines of code"),
]

ORGANISATION = [
    ("cum_change_top1", "Share of all change in one file"),
    ("cum_change_hhi", "Concentration of change (HHI)"),
    ("cum_change_entropy_norm", "Spread of change (entropy)"),
    ("ccdist_file_top1", "Share of all CC in one file"),
    ("ccdist_file_hhi", "Concentration of CC over files (HHI)"),
    ("ccdist_file_gini", "Inequality of CC over files (Gini)"),
    ("wmcdist_class_hhi", "Concentration of WMC over classes (HHI)"),
    ("node_cc_median", "Complexity reachable from the endpoint"),
    ("ck_cbo_mean", "Mean coupling between objects"),
    ("propagation_cost", "Propagation cost"),
    ("total_files", "Files"),
]


def _fnum(v):
    if v in ("True", "true"):
        return 1.0
    if v in ("False", "false"):
        return 0.0
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def load(results_dir: str, run_id: str) -> list[dict]:
    path = os.path.join(results_dir, run_id, "records.concat.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def phase_mean(rows, arm, field, phase=FINAL_PHASE):
    """Mean over chains of each chain's mean over that phase's checkpoints.

    Chain-first, so a chain that lost checkpoints cannot outvote one that did
    not. This is the same aggregation `metric_gallery.phase_mean_by_chain` uses.
    """
    per_chain: dict[str, list[float]] = {}
    for r in rows:
        if r["arm"] != arm or r["phase"] != phase:
            continue
        v = _fnum(r.get(field))
        if v is None:
            continue
        per_chain.setdefault(r["chain"], []).append(v)
    means = [sum(v) / len(v) for v in per_chain.values() if v]
    return sum(means) / len(means) if means else None


def panel(ax, data, metrics, title, subtitle):
    # RUNS[0] is the control and RUNS[:4] are the four external-control
    # conditions; the last entry (ai-reviewed) is the reviewer lever, drawn
    # distinctly and EXCLUDED from the labelled spread so the label matches the
    # four-condition spread in the paper's table.
    n_ext = 4
    ys = list(range(len(metrics)))[::-1]
    for y, (field, label) in zip(ys, metrics):
        for ai, arm in enumerate(ARMS):
            vals = [phase_mean(data[cond], arm, field) for cond, _ in RUNS]
            if any(v is None for v in vals) or not vals[0]:
                continue
            rel = [v / vals[0] for v in vals]   # RUNS[0] is the control
            rel_ext = rel[:n_ext]
            # Vertical offset separates the two arms on the same metric row.
            yy = y + (0.17 if ai == 0 else -0.17)
            colour = ARM_COLORS[arm]
            # The range bar spans ALL conditions, so the reviewer's reach is
            # visible, but the external-control extent is drawn heavier.
            ax.plot([min(rel), max(rel)], [yy, yy], color=colour, linewidth=1.2,
                    alpha=0.22, solid_capstyle="round", zorder=2)
            ax.plot([min(rel_ext), max(rel_ext)], [yy, yy], color=colour,
                    linewidth=2.6, alpha=0.38, solid_capstyle="round", zorder=2)
            for ci, r in enumerate(rel[:n_ext]):
                ax.plot(r, yy, marker=COND_MARKER[ci], markersize=7,
                        color=colour, markeredgecolor="#fcfcfb",
                        markeredgewidth=1.2, zorder=3, linestyle="none")
            # The reviewer marker: a ring, larger, dark edge, so it reads as a
            # different KIND of point rather than a fifth condition in line.
            ax.plot(rel[-1], yy, marker=COND_MARKER[-1], markersize=10,
                    markerfacecolor="none", markeredgecolor=colour,
                    markeredgewidth=2.2, zorder=4, linestyle="none")
            # One direct label per arm per row: the FOUR-condition spread, which
            # is the number the paper's table reports. Never a label per marker.
            spread = (max(rel_ext) - min(rel_ext)) / _st.mean(rel_ext)
            ax.annotate(f"{spread * 100:.0f}%", (max(rel), yy),
                        textcoords="offset points", xytext=(9, 0), fontsize=7.5,
                        color="#52514e", va="center")
    ax.axvline(1.0, color="#b8b6b0", linewidth=1, zorder=1)
    ax.set_yticks(ys)
    ax.set_yticklabels([label for _, label in metrics], fontsize=8.5)
    ax.set_ylim(-0.7, len(metrics) - 0.3)
    ax.grid(True, axis="x", alpha=0.16, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(title, fontsize=10.5, loc="left", pad=20)
    ax.annotate(subtitle, (0, 1), xycoords="axes fraction",
                textcoords="offset points", xytext=(0, 5), fontsize=8.5,
                color="#52514e", va="bottom")


def build(results_dir: str, out_path: str) -> str:
    data = {cond: load(results_dir, run) for cond, run in RUNS}
    heights = [len(AMOUNT), len(ORGANISATION)]
    fig, axes = plt.subplots(
        2, 1, figsize=(9.6, 8.6), sharex=True,
        gridspec_kw={"height_ratios": heights, "hspace": 0.30})
    panel(axes[0], data, AMOUNT,
          "AMOUNT. How much complexity the sixty rules cost.",
          "Tesler's prediction: nothing moves. Neither architecture, "
          "under any condition, reviewer included.")
    panel(axes[1], data, ORGANISATION,
          "ORGANISATION. Where that complexity ended up.",
          "Four external controls move the mutative arm only. The AI reviewer "
          "(ring) is the one lever that moves the additive arm. Label = "
          "four-condition spread.")
    axes[1].set_xlabel(
        "Final-phase value relative to the same architecture's own control "
        "(control = 1.0)", fontsize=9)

    legend = [Line2D([], [], color=ARM_COLORS[a], marker="o", linestyle="none",
                     markersize=7, markeredgecolor="#fcfcfb", markeredgewidth=1.2,
                     label=ARM_LABEL[a]) for a in ARMS]
    legend += [Line2D([], [], color="#52514e", marker=COND_MARKER[i],
                      linestyle="none", markersize=6, label=cond)
               for i, (cond, _) in enumerate(RUNS[:4])]
    legend += [Line2D([], [], color="#52514e", marker=COND_MARKER[-1],
                      linestyle="none", markersize=8, markerfacecolor="none",
                      markeredgewidth=2.0, label="ai-reviewed (lever of a different kind)")]
    axes[0].legend(handles=legend, fontsize=8, frameon=False, ncol=4,
                   loc="lower left", bbox_to_anchor=(0, 1.16))

    fig.suptitle("External instruction moved one architecture; an AI reviewer moved the other",
                 fontsize=12.5, x=0.012, ha="left", y=0.988)
    # subplots_adjust rather than tight_layout: the y-axis labels are long and
    # tight_layout cannot see the annotations placed outside the axes, so it
    # crops both. A fixed left margin is the only thing that holds here.
    fig.subplots_adjust(left=0.265, right=0.945, top=0.885, bottom=0.075)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=140, facecolor="#fcfcfb")
    plt.close(fig)
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", default=os.path.join(_REPO, "results"))
    ap.add_argument("--out", default=os.path.join(_REPO, "blog", "metric-gallery", "figs"))
    args = ap.parse_args(argv)
    path = build(args.results, os.path.join(args.out, "plasticity.png"))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
