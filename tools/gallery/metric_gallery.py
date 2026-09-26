#!/usr/bin/env python3
"""Per-metric comparison gallery across the four study conditions.

Produces, for EVERY metric in `metric_catalog.py`, one self-contained figure
showing all eight series (4 conditions x 2 architectures), a numbers table, and
a blog-ready page that explains the metric in isolation beside its figure.

The figure shades the FINAL PHASE on every panel and labels each arm's mean over
it. That is the last twelve change requests of sixty, because `phase_for` bins a
run into fifths. The table under the figure gives that mean for all five phases.
Every number here is descriptive: no slope, no interval, no significance test and
no effect size, all of which need the FDR correction that lives in each run's
`summary.md`. Phase means are free arithmetic and are computed on every build;
only the bootstrap slope in `metrics.csv` costs time, and only it needs `--stats`.

Why a separate tool rather than a flag on `harness/analyze.py`: `analyze` is
per-RUN. It recomputes one run's branches and answers "what happened in this
run". This reads the already-computed `records.concat.csv` of SEVERAL runs and
answers "how does this one metric look across all four conditions" -- the view a
reader needs to understand a metric on its own. It deliberately recomputes
nothing: if a number here disagrees with a run's `summary.md`, the run is right
and this tool has a bug.

Aggregation is kept identical to `analyze.plot_metric` on purpose (drop NaN,
mean across chains per checkpoint, OLS on the mean curve, bootstrap CI over
chains) by importing those primitives rather than reimplementing them.

Usage
-----
    python -m tools.gallery.metric_gallery                  # all four runs, all metrics
    python -m tools.gallery.metric_gallery --only node_path_cc,cost_usd
    python -m tools.gallery.metric_gallery --n-boot 2000    # publication CIs (slow)
    python -m tools.gallery.metric_gallery --img-base https://example.com/figs/

Run mapping lives in RUNS below. A condition is what the agent was PROMPTED
with, not what the run's `strategy` column is named -- `blind-202609010045` is
recorded as `impact_gated` but its implement prompt carried the cost formula and
its gate fired on 3 of 1200 checkpoints, so it is labelled `formula-provided`
here. Change the mapping, not the labels, if you add a run.
"""
from __future__ import annotations

import argparse
import csv
import html
import math
import os
import re
import sys
from collections import defaultdict

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import numpy as np

from harness import analyze
# The phase bins are DEFINED in the runner and stamped onto every record. They
# are imported rather than restated so this tool cannot drift from the column
# it is reading. Sixty change requests divide into five bins of twelve, so
# "Final" is the mean of the last twelve.
from harness.run_experiment import PHASES
from tools.gallery import metric_catalog as cat

# --------------------------------------------------------------------------
# The four conditions, in the order they were run and the order they are shown.
# `label` is what a reader sees; `blurb` is the one-line reminder of what the
# condition actually DID, repeated on every figure so a metric can be read in
# isolation without scrolling back to the introduction.
# --------------------------------------------------------------------------
RUNS = [
    ("just-solve", "blind-202608100006",
     "Control. The change request and nothing else."),
    ("cohesion-prompt", "blind-202609160027",
     "One plain-English paragraph asking for well-structured code. No metric named."),
    ("impact-gated", "blind-202609031757",
     "A tool grades each change and asks the agent to refactor when it scores badly."),
    # AGENTS.md calls this condition `metric-in-prompt`; "formula-provided" is
    # the reader-facing name used in the blog series. Same condition.
    ("formula-provided", "blind-202609010045",
     "The scoring formula itself pasted into the implement prompt."),
]

ARMS = ["spring", "officefloor"]
ARM_LABEL = {"spring": "Spring", "officefloor": "OfficeFloor"}

# Colour follows the ARCHITECTURE, never its rank or its condition, so an arm
# keeps its hue in every figure here AND in every figure `analyze` produces.
# Validated pair (light surface): adjacent CVD dE 24.7 protan, normal-vision
# dE 33.6, both >= 3:1 contrast.
ARM_COLORS = dict(analyze.ARM_COLORS)

INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8880"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

START_PHASE, FINAL_PHASE = PHASES[0], PHASES[-1]

# The shading for the final-phase window on every panel. A warm grey a shade
# darker than the surface: it has to read as a marked-off region of the x-axis
# and not as another data band, so it is neutral where every data colour is not.
FINAL_BAND = "#efece3"

# index.html is published with its figures next to it, so its <img src> is always
# relative. Never wire --img-base to this; see that flag's help.
PAGE_IMG_BASE = "figs/"


# --------------------------------------------------------------------------
# House-style guard on the catalogue prose.
#
# Everything in `metric_catalog.py` is PUBLISHED text. The blog's rules are
# short sentences and no dash punctuation, and markdown emphasis does not render
# on an HTML page, so an asterisk reaches the reader as an asterisk. Both are
# easy to reintroduce and invisible until someone reads the live page. This
# fails the build instead, at import, before anything is written.
#
# Hyphenated compound words are fine and are what the pattern deliberately
# misses: it looks only for a dash with whitespace on at least one side, plus the
# em and en dash characters, which have no legitimate use in this prose.
# --------------------------------------------------------------------------
_DASH = re.compile(r"[\u2014\u2013]|\s-\s|\s-\S|\S-\s")
_MD_EMPH = re.compile(r"(?<![\w*])\*\w[^*\n]*\w\*(?![\w*])")
# Code spans and HTML tags are exempt. A command-line flag legitimately reads
# `--name-status -M`, and a style attribute reads `text-decoration:overline`.
# Neither is dash punctuation, and rewriting them to satisfy the rule would make
# the documentation wrong. Everything outside a code span is still checked.
_EXEMPT = re.compile(r"<code>.*?</code>|<[^>]+>", re.S)
_PROSE_FIELDS = ("title", "source", "what", "formula", "terms", "how", "read",
                 "caveat")


def check_catalog_style() -> None:
    bad: list[str] = []
    for key, entry in cat.M.items():
        for field in _PROSE_FIELDS:
            text = _EXEMPT.sub(" ", entry.get(field) or "")
            if _DASH.search(text):
                bad.append(f"{key}.{field}: dash punctuation")
            if _MD_EMPH.search(text):
                bad.append(f"{key}.{field}: markdown *emphasis* (use <i>/<b>)")
    for gkey, gtitle, gintro in cat.GROUPS:
        for label, raw in (("title", gtitle), ("intro", gintro)):
            text = _EXEMPT.sub(" ", raw)
            if _DASH.search(text):
                bad.append(f"GROUPS[{gkey}].{label}: dash punctuation")
            if _MD_EMPH.search(text):
                bad.append(f"GROUPS[{gkey}].{label}: markdown *emphasis*")
    if bad:
        raise SystemExit(
            "metric_catalog.py violates the house style (see its docstring):\n  "
            + "\n  ".join(bad)
            + "\n\nBreak the sentence, or use a colon. Hyphenated compounds are fine."
        )


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load_run(results_dir: str, run_id: str) -> list[dict]:
    path = os.path.join(results_dir, run_id, "records.concat.csv")
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path}: no rows")
    # The additive-only / mutative-only impact views are DERIVED in analyze.main
    # and never written to the CSV, so synthesise them the same way here. Blank,
    # not zero: a checkpoint of the other type has no value, and zero would drag
    # the mean of a filtered view toward nothing.
    for r in rows:
        is_mut = str(r.get("checkpoint_type", "")).strip() == "mutative"
        for f in analyze.IMPACT_BASE_FIELDS:
            v = r.get(f, "")
            r[f + "_add"] = "" if is_mut else v
            r[f + "_mut"] = v if is_mut else ""
        # The boolean columns (strict_pass, iso_pass, core_pass, build_ok,
        # gate_invalid, ...) are written as True/False, which float() cannot read
        # -- without this the pass-rate metrics silently come back empty rather
        # than erroring. Coerced to 1/0 so their mean across chains IS the rate,
        # matching what `analyze` computes via its own boolean reader. Only exact
        # true/false spellings are rewritten, so no numeric column is touched.
        for k, v in r.items():
            lv = str(v).strip().lower()
            if lv == "true":
                r[k] = "1"
            elif lv == "false":
                r[k] = "0"
    return rows


def split_by_arm(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["arm"]].append(r)
    return out


# --------------------------------------------------------------------------
# Aggregation -- deliberately the same primitives `analyze` plots with
# --------------------------------------------------------------------------
def mean_curve(rows: list[dict], field: str):
    """(checkpoints, mean, sd, n_chains) across chains, NaNs dropped."""
    cs = analyze.series_by_chain(rows, field)
    if not cs:
        return None
    acc = analyze._bucket_by_checkpoint(cs)
    ks = sorted(acc)
    if not ks:
        return None
    mean = np.array([float(np.mean(acc[k])) for k in ks])
    sd = np.array([float(np.std(acc[k])) for k in ks])
    return np.array(ks, dtype=float), mean, sd, len(cs)


def phase_mean_by_chain(rows: list[dict], field: str, phase: str) -> dict[int, float]:
    """chain -> mean of `field` over that phase. A phase mean rather than the tip
    value: it is defined for the sparse fields (the probe, re-edit rate, handler
    TCC) where a single checkpoint is often blank, and it is far less noisy for
    the per-checkpoint rate fields (cost, regressions) where one tip value says
    little. The figure shades the window it used and the table names it."""
    acc: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        if str(r.get("phase", "")).strip() != phase:
            continue
        v = analyze._f(r.get(field))
        if not math.isnan(v):
            acc[int(r["chain"])].append(v)
    return {c: float(np.mean(vs)) for c, vs in acc.items() if vs}


def all_phase_means(rows: list[dict], field: str) -> dict[str, float]:
    """phase -> mean over chains of that chain's mean within the phase.

    Averaged per chain FIRST, then across chains, so a chain that happens to be
    missing a checkpoint does not get a smaller vote than one that is complete.
    This is the same two-step `analyze` uses for its phase-binned table.

    Pure arithmetic over rows already in memory, so it runs on every build. The
    bootstrap is the only expensive thing in this tool and it stays behind
    `--stats`.
    """
    out: dict[str, float] = {}
    for ph in PHASES:
        per_chain = phase_mean_by_chain(rows, field, ph)
        out[ph] = (float(np.mean(list(per_chain.values())))
                   if per_chain else float("nan"))
    return out


def phase_window(rows: list[dict], phase: str):
    """(first, last) checkpoint number of `phase`, or None.

    Read off the data rather than assumed: `phase_for` bins 1..n into fifths, so
    the window is only checkpoints 49 to 60 while a run is sixty long. A shorter
    run must shade its own window, not this one.
    """
    ks = [int(r["checkpoint"]) for r in rows
          if str(r.get("phase", "")).strip() == phase
          and str(r.get("checkpoint", "")).strip()]
    return (min(ks), max(ks)) if ks else None


def slope_ci(rows: list[dict], field: str, n_boot: int):
    cs = analyze.series_by_chain(rows, field)
    if not cs:
        return (float("nan"),) * 3
    try:
        return analyze.bootstrap_slope(cs, n_boot=n_boot)
    except Exception:                                  # noqa: BLE001
        return (float("nan"),) * 3


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fmt(v: float, sig: int = 3) -> str:
    """A number a reader can read aloud. Never scientific notation.

    Halstead effort runs to eight figures and the concentration indices run to
    six decimal places, so the obvious `%g` reaches for an exponent at both ends
    and prints `1.15e+07`. That is unreadable in a blog table and it is worse on
    a figure, where it sits next to a plain number from another panel and the
    two no longer compare by eye. Both ends are spelled out in full instead:
    thousands separators going up, and enough decimal places to carry `sig`
    significant digits going down.
    """
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "--"
    a = abs(v)
    # Floating-point zero. An OLS slope over a series that never moves comes back
    # as -4.291e-18, and spelling that one out in full gives eighteen leading
    # zeros. The smallest number any metric here reports honestly is about 1e-6,
    # so anything nine orders below that is arithmetic noise and reads as zero.
    if a < 1e-9:
        return "0"
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 1:
        return f"{v:.2f}"
    if a >= 1e-3:
        return f"{v:.{sig}g}"
    # Below a thousandth, %g switches to an exponent. Count the leading zeros
    # and ask for that many places plus the significant digits wanted.
    dec = sig - 1 - int(math.floor(math.log10(a)))
    return f"{v:.{dec}f}"


def pct_change(a: float, b: float) -> str:
    if math.isnan(a) or math.isnan(b) or a == 0:
        return "--"
    return f"{(b - a) / abs(a) * 100:+.0f}%"


# --------------------------------------------------------------------------
# The figure
# --------------------------------------------------------------------------
def build_figure(field: str, entry: dict, data: dict, out_path: str) -> bool:
    """One figure, all eight series, and nothing else.

    A row of four small multiples, one per condition, sharing a y-axis so the
    conditions are directly comparable by eye. Within each panel the two
    architectures are the two coloured lines, which is the comparison the study
    is actually about.

    The final phase is shaded on every panel and each arm's mean over that window
    is drawn as a dashed rule and labelled. That is the last twelve change
    requests of sixty. It is marked on the window it came from rather than
    printed in a corner, because a number in a corner does not say which
    checkpoints it averages, and the tip value of a noisy per-request metric
    (cost, regressions, re-edit rate) says very little on its own.

    That mean is the only number on the figure, and it is a DESCRIPTIVE one. There
    is still no slope, no interval, no significance test and no effect size here.
    Those need the Benjamini-Hochberg correction across all the metrics, which
    lives in each run's `summary.md`.

    Returns False when no series had any data, in which case the metric is simply
    not plotted.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    import matplotlib.ticker as mticker
    from matplotlib import gridspec

    curves = {}
    for cond, _rid, _blurb in RUNS:
        for arm in ARMS:
            c = data[cond][arm].get("curve")
            if c is not None:
                curves[(cond, arm)] = c
    if not curves:
        return False

    fig = plt.figure(figsize=(13.2, 6.1), facecolor=SURFACE)
    # Two rows. The trajectories on top, and beneath them one full-width strip
    # carrying the same eight final-phase means side by side. The strip is the
    # summary a reader wants after reading four panels, and putting it on the
    # SAME y-axis is what makes it readable at a glance: the flat line in the
    # strip sits at exactly the height of the dashed rule in its own panel.
    gs = gridspec.GridSpec(2, 4, figure=fig, wspace=0.13, hspace=0.60,
                           height_ratios=[2.45, 1.0],
                           left=0.062, right=0.987, top=0.770, bottom=0.102)

    direction = entry.get("direction", "")
    arrow = {"down": "lower is better", "up": "higher is better",
             "flat": "prediction: no difference between the arms",
             "": ""}.get(direction, "")

    axes = []
    for i, (cond, _rid, blurb) in enumerate(RUNS):
        ax = fig.add_subplot(gs[0, i], sharey=axes[0] if axes else None)
        axes.append(ax)
        ax.set_facecolor(SURFACE)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRID)
        ax.grid(axis="y", color=GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK_2, labelsize=8.5, length=3, width=0.7)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _pos: fmt(v)))

        # The final-phase window, shaded behind everything. Drawn from the data's
        # own phase stamps, so a run of a different length shades its own fifth.
        wins = [data[cond][a].get("final_window") for a in ARMS
                if data[cond][a].get("final_window")]
        win = (min(w[0] for w in wins), max(w[1] for w in wins)) if wins else None
        if win:
            ax.axvspan(win[0] - 0.5, win[1] + 0.5, color=FINAL_BAND,
                       linewidth=0, zorder=1)

        ends = {}
        for arm in ARMS:
            c = curves.get((cond, arm))
            if c is None:
                continue
            ks, mean, sd, _n = c
            col = ARM_COLORS[arm]
            ax.fill_between(ks, mean - sd, mean + sd, color=col, alpha=0.13,
                            linewidth=0, zorder=2)
            # Deliberately unequal widths: on the binary detector metrics both
            # arms sit at exactly 0.0 for whole panels, and two equal lines drawn
            # on the same pixels hide one arm completely. The wider under-line
            # leaves a visible fringe of the first arm's colour wherever the two
            # coincide, and reads as two ordinary lines wherever they do not.
            ax.plot(ks, mean, color=col, linewidth=2.7 if arm == ARMS[0] else 1.8,
                    solid_capstyle="round", zorder=3 + ARMS.index(arm))
            # Anchored at the START of the shaded window, not at the last point.
            # The final-phase number is printed at the window's right edge, and
            # an arm name anchored at the last point lands on top of it.
            j = int(np.argmin(np.abs(ks - win[0]))) if win else len(ks) - 1
            ends[arm] = (ks[j], mean[j])

        # Direct labels on the first panel only. Drawn INSIDE the axes, because a
        # label in the gutter gets clipped by the next panel, nudged apart
        # vertically so two lines that finish close together do not print on top
        # of each other, and stroked in the surface colour so the text stays
        # legible where it crosses its own line.
        if i == 0 and ends:
            hi_arm = max(ends, key=lambda a: ends[a][1])
            for arm, (x, y) in ends.items():
                dy = 11 if arm == hi_arm and len(ends) > 1 else -13
                ax.annotate(ARM_LABEL[arm], xy=(x, y), xytext=(-4, dy),
                            textcoords="offset points", color=ARM_COLORS[arm],
                            fontsize=8.8, fontweight="bold", va="center",
                            ha="right", zorder=6,
                            path_effects=[pe.withStroke(linewidth=3.2,
                                                        foreground=SURFACE)])

        ax.set_title(cond, fontsize=10.5, color=INK, fontweight="bold", pad=25)
        # Two-line condition reminder between the title and the axes, so a panel
        # pasted into a post on its own still says what the condition WAS.
        ax.text(0.5, 1.018, _wrap(blurb, 46), transform=ax.transAxes,
                ha="center", va="bottom", fontsize=7.2, color=INK_MUTED,
                linespacing=1.3)
        ax.set_xlabel("change request (1-60)", fontsize=8.5, color=INK_2)
        if i == 0:
            ax.set_ylabel(field, fontsize=9, color=INK_2)
        else:
            ax.tick_params(labelleft=False)

    # The final-phase mean is deliberately NOT drawn on these panels. It lives
    # in the strip below, once, at a readable size. Marking it in both places
    # meant every panel carried a dashed rule and two numbers competing with the
    # curves for the same few pixels, and on a metric whose arms nearly coincide
    # the two labels had to be shoved apart to avoid printing over each other.
    # The panels are for the trajectory. The strip is for where it ended up.

    # ----------------------------------------------------------------
    # The final-phase strip, full width beneath the four panels.
    #
    # One position per series, in the panels' own order, so each condition's
    # pair sits directly under the panel it came from. The short flat line is
    # the mean over the final twelve change requests, which is the same number
    # the dashed rule marks above. The dots are the ten individual runs.
    #
    # The dots are the reason this section exists. Four mean curves cannot show
    # whether a condition moved every run or two of them, and on this experiment
    # that distinction has already changed a conclusion: one prompt produced
    # several genuinely different architectures across its ten runs, and the
    # mean alone read as a clean win.
    # ----------------------------------------------------------------
    # NOT sharey with the panels. The panels span the whole run, from the first
    # change request to the sixtieth, so on that scale the eight final-phase
    # means collapse into the top fifth of the row and the between-run spread,
    # which is the only reason this section exists, becomes invisible. The strip
    # carries its own scale and says so in its title.
    strip = fig.add_subplot(gs[1, :])
    strip.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        strip.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        strip.spines[spine].set_color(GRID)
    strip.grid(axis="y", color=GRID, linewidth=0.7, zorder=0)
    strip.set_axisbelow(True)
    strip.tick_params(colors=INK_2, labelsize=8.5, length=3, width=0.7)
    strip.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _pos: fmt(v)))

    # Positions in AXES fraction, so each group lands under its own panel
    # regardless of how many conditions there are.
    n = len(RUNS)
    ticks, ticklabels, drew_any = [], [], False
    # One generator for the whole figure, seeded per metric, so a rebuild of the
    # same metric puts every dot back exactly where it was.
    rng = np.random.default_rng(abs(hash(field)) % (2 ** 32))
    for ci, (cond, _rid, _blurb) in enumerate(RUNS):
        centre = (ci + 0.5) / n
        for ai, arm in enumerate(ARMS):
            x = centre + (ai - (len(ARMS) - 1) / 2) * 0.052
            vals = [v for v in data[cond][arm].get("final_by_chain", {}).values()
                    if not math.isnan(v)]
            ticks.append(x)
            ticklabels.append(ARM_LABEL[arm])
            if not vals:
                continue
            drew_any = True
            col = ARM_COLORS[arm]
            jitter = (rng.random(len(vals)) - 0.5) * 0.026
            strip.scatter([x + j for j in jitter], vals, s=26, alpha=0.8,
                          color=col, edgecolors=SURFACE, linewidths=0.8, zorder=3)
            m = float(np.mean(vals))
            # The short flat line IS the average. Drawn over the dots and stroked
            # in the surface colour so it stays visible inside a tight cluster.
            strip.plot([x - 0.021, x + 0.021], [m, m], color=col, linewidth=2.6,
                       solid_capstyle="butt", zorder=5,
                       path_effects=[pe.withStroke(linewidth=4.4, foreground=SURFACE)])
            strip.annotate(fmt(m), xy=(x, m), xytext=(0, 8),
                           textcoords="offset points", color=col, fontsize=7.8,
                           fontweight="bold", va="bottom", ha="center", zorder=6,
                           path_effects=[pe.withStroke(linewidth=3.0,
                                                       foreground=SURFACE)])
    strip.set_xlim(0, 1)
    strip.set_xticks(ticks)
    strip.set_xticklabels(ticklabels, fontsize=7.2, color=INK_2)
    strip.set_ylabel(field, fontsize=9, color=INK_2)
    strip.set_title("Mean over the final twelve change requests, on its own "
                    "y-scale. Short line is the mean. One dot per run, so the "
                    "spread between runs is visible.",
                    fontsize=8.6, color=INK_MUTED, loc="left", pad=7)
    # Headroom for the value labels, which sit above their own line.
    slo, shi = strip.get_ylim()
    strip.set_ylim(slo, shi + (shi - slo) * 0.13)
    if not drew_any:
        strip.remove()

    title = entry.get("title", field)
    fig.text(0.062, 0.971, title, fontsize=15.5, color=INK, fontweight="bold",
             va="top")
    sub = f"{field}"
    if entry.get("source"):
        sub += f"  \u00b7  {entry['source']}"
    if arrow:
        sub += f"  \u00b7  {arrow}"
    fig.text(0.062, 0.916, sub, fontsize=9, color=INK_2, va="top")
    fig.text(0.062, 0.883,
             "line = mean of ten runs   \u00b7   band = \u00b11 SD across those runs"
             "   \u00b7   shaded = the final twelve change requests, "
             "summarised in the row below",
             fontsize=8.2, color=INK_MUTED, va="top")

    handles = [plt.Line2D([], [], color=ARM_COLORS[a], linewidth=2.4,
                          label=ARM_LABEL[a]) for a in ARMS]
    leg = fig.legend(handles=handles, loc="upper right",
                     bbox_to_anchor=(0.987, 0.994), frameon=False, ncol=2,
                     fontsize=9.5, handlelength=1.7, columnspacing=1.4)
    for t in leg.get_texts():
        t.set_color(INK)

    fig.savefig(out_path, dpi=132, facecolor=SURFACE)
    plt.close(fig)
    return True


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width)[:2])


# --------------------------------------------------------------------------
# Page generation
# --------------------------------------------------------------------------
def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


# The page ground is the SAME warm off-white the figures are drawn on
# (SURFACE, above), so a 13-inch PNG sits flush with the page instead of reading
# as a pasted rectangle. Dark mode keeps the warm bias and gives every figure a
# permanent light plate, because the charts are raster and cannot invert.
FONT_LINK = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=IBM+Plex+Mono:wght@400;500&'
             'family=IBM+Plex+Sans:wght@400;600&'
             'family=IBM+Plex+Serif:wght@600&display=swap">')

PAGE_CSS = """
:root{
  --ground:#fcfcfb; --raised:#f5f4ef; --ink:#12110e; --ink2:#57544c;
  --muted:#8b8779; --rule:#e3e1d9; --hair:#eeece5;
  --spring:#eb6834; --of:#2a78d6; --link:#1f63b4; --plate:#fcfcfb;
  --serif:"IBM Plex Serif",Georgia,"Times New Roman",serif;
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --measure:68ch;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#191918; --raised:#221f1d; --ink:#f4f3ee; --ink2:#b5b2a6;
  --muted:#8b8779; --rule:#34322c; --hair:#2a2825;
  --spring:#f07d4f; --of:#5b9df0; --link:#7db1f3; --plate:#fcfcfb;}}
:root[data-theme="dark"]{
  --ground:#191918; --raised:#221f1d; --ink:#f4f3ee; --ink2:#b5b2a6;
  --muted:#8b8779; --rule:#34322c; --hair:#2a2825;
  --spring:#f07d4f; --of:#5b9df0; --link:#7db1f3; --plate:#fcfcfb;}

*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
     font:400 16.5px/1.65 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding-block:52px 80px;
      padding-left:22px;padding-right:22px}
.measure{max-width:var(--measure)}
p{margin:0 0 .85em}
a{color:var(--link);text-underline-offset:2px}
a:focus-visible{outline:2px solid var(--of);outline-offset:3px;border-radius:2px}

/* --- masthead ------------------------------------------------------------ */
.eyebrow{font:500 .72rem/1 var(--mono);letter-spacing:.13em;
         text-transform:uppercase;color:var(--muted);margin:0 0 1.1em}
h1{font:600 clamp(2.1rem,4.4vw,3rem)/1.08 var(--serif);margin:0 0 .5em;
   letter-spacing:-.018em;text-wrap:balance}
.lede{font-size:1.14rem;line-height:1.58;color:var(--ink2);margin-bottom:1.5em}

/* --- section + metric headings ------------------------------------------- */
h2.group{font:600 1.72rem/1.2 var(--serif);letter-spacing:-.012em;
         margin:0 0 .34em;text-wrap:balance}
.groupband{margin:5rem 0 2.2rem;padding-top:1.6rem;border-top:2px solid var(--rule)}
.groupband:first-of-type{margin-top:3.2rem}
.groupintro{color:var(--ink2);margin:0}
h3{font:600 1.32rem/1.28 var(--serif);letter-spacing:-.01em;
   margin:0 0 .5rem;text-wrap:balance}

/* A metric is separated by space and a hairline, not a card. 101 identical
   boxes would flatten the hierarchy; the only lifted things on the page are the
   caveat (must not be skimmed past) and the numbers table. */
.metric{padding-top:2.6rem;margin-top:2.6rem;border-top:1px solid var(--hair)}
.metric:first-of-type{border-top:none;margin-top:0;padding-top:.4rem}
.metahead{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1rem;
          margin-bottom:1.35rem}
.key{font:400 .84rem/1 var(--mono);color:var(--muted)}
.dir{font:500 .74rem/1 var(--mono);letter-spacing:.06em;color:var(--ink2);
     border:1px solid var(--rule);border-radius:3px;padding:4px 8px;
     white-space:nowrap}
.dir .g{color:var(--of);font-weight:500}

/* --- figure -------------------------------------------------------------- */
figure{margin:0 0 1.6rem}
.plate{background:var(--plate);border:1px solid var(--rule);border-radius:4px;
       padding:6px}
.plate img{width:100%;height:auto;display:block}
figcaption{font:400 .82rem/1.5 var(--sans);color:var(--muted);margin-top:.6rem}

/* --- definition list ----------------------------------------------------- */
dl{margin:0 0 1.5rem;display:grid;grid-template-columns:9.2em 1fr;gap:.7rem 1.4rem;
   max-width:calc(var(--measure) + 10.6em)}
dt{font:500 .72rem/1.5 var(--mono);letter-spacing:.08em;text-transform:uppercase;
   color:var(--muted);padding-top:.28em}
dd{margin:0}
dd i{color:var(--ink2)}

p.what{max-width:var(--measure);font-size:1.02rem}

/* The equation block. Monospace-adjacent, on a raised surface, with the label
   set small above it so the formula itself owns the line. Allowed to scroll
   sideways on a narrow screen rather than wrapping mid-expression. */
.eq{max-width:calc(var(--measure) + 10.6em);background:var(--raised);
    border:1px solid var(--rule);border-radius:5px;padding:.8rem 1.1rem;
    margin:1.3rem 0}
.eqlabel{font:500 .68rem/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
         color:var(--muted);margin-bottom:.55rem}
.eqbody{font:400 1rem/2 var(--mono);color:var(--ink);overflow-x:auto;
        white-space:nowrap;padding-bottom:.2rem}
.eqbody sub,.eqbody sup{font-size:.72em;line-height:0}

.caveat{max-width:calc(var(--measure) + 10.6em);background:var(--raised);
        border-left:3px solid var(--spring);border-radius:0 4px 4px 0;
        padding:.95rem 1.2rem;margin:0 0 1.5rem}
.caveat b{font-weight:600}
.caveat .lbl{color:var(--spring)}

/* --- numbers ------------------------------------------------------------- */
.tablewrap{overflow-x:auto;margin:0}
td.cond{color:var(--ink2)}

/* The phase table. Numbers are monospace and right-aligned so a column can be
   read down as a column; the two label columns stay in the body face. The
   architecture cell carries the arm's own colour, which is the same hue as its
   line in the figure directly above it, so the table needs no legend. */
table.phases{border-collapse:collapse;width:100%;margin:0;
             font:400 .88rem/1.5 var(--sans);white-space:nowrap}
table.phases th{text-align:right;font-weight:600;color:var(--muted);
                font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;
                border-bottom:1.5px solid var(--rule);padding:0 0 .5rem .9rem}
table.phases td{border-bottom:1px solid var(--hair);text-align:right;
                padding:.42rem 0 .42rem .9rem;
                font:400 .84rem/1.5 var(--mono)}
table.phases th.l,table.phases td.l{text-align:left;padding-left:0}
table.phases td.l{font:400 .88rem/1.5 var(--sans)}
table.phases tr.grp td{border-top:1px solid var(--rule)}
table.phases td.arm{font-weight:600}
table.phases td.s{color:var(--spring)}
table.phases td.o{color:var(--of)}
/* Final is the column the figure shades, so it is the one the eye should land
   on. Everything else in the row is context for it. */
table.phases th.fin,table.phases td.fin{color:var(--ink);font-weight:600}
table.phases td.chg{color:var(--ink2)}
.tabcap{font:400 .82rem/1.55 var(--sans);color:var(--muted);
        margin:.65rem 0 1.7rem;max-width:var(--measure)}

/* --- contents + run key -------------------------------------------------- */
nav.toc{margin:3rem 0 0;border-top:2px solid var(--rule);padding-top:1.6rem}
nav.toc h2{font:500 .72rem/1 var(--mono);letter-spacing:.13em;
           text-transform:uppercase;color:var(--muted);margin:0 0 1.4rem}
nav.toc section{margin:0 0 1.5rem;break-inside:avoid}
nav.toc h3{font:600 .95rem/1.4 var(--sans);margin:0 0 .35rem}
nav.toc h3 a{color:var(--ink);text-decoration:none}
nav.toc ul{margin:0;padding:0;list-style:none}
nav.toc li{margin:.12rem 0;font-size:.92rem}
/* The contents is a long list -- 101 underlined blue links read as noise and
   compete with the section names. Quiet by default, affordance on hover. */
nav.toc a{color:var(--ink2);text-decoration:none}
nav.toc a:hover{color:var(--link);text-decoration:underline}
.toccols{columns:2;column-gap:2.6rem}

code{font:400 .9em/1.4 var(--mono);background:var(--raised);
     border-radius:3px;padding:.1em .34em}
.note code,.key code{background:none;padding:0}

table.runkey{border-collapse:collapse;width:100%;margin:0 0 1rem;
             font:400 .93rem/1.5 var(--sans)}
table.runkey th{text-align:left;font-weight:600;color:var(--ink2);font-size:.75rem;
                letter-spacing:.05em;text-transform:uppercase;
                border-bottom:1.5px solid var(--rule);padding:0 1.2rem .5rem 0}
table.runkey td{border-bottom:1px solid var(--hair);padding:.6rem 1.2rem .6rem 0;
                vertical-align:top}
table.runkey td.cond b{font-family:var(--mono);font-weight:500;font-size:.92rem}
.note{font-size:.9rem;color:var(--muted);max-width:var(--measure)}

@media (max-width:720px){
  .wrap{padding-block:34px 56px}
  dl{grid-template-columns:1fr;gap:.25rem}
  dt{padding-top:.75rem}
  dl,.caveat{max-width:none}
  .toccols{columns:1}
}
"""


def render_page(rows_by_group: dict, out_dir: str, img_rel: str, meta: dict,
                filename: str = "index.html") -> str:
    n_metrics = sum(len(v) for v in rows_by_group.values())
    parts = [
        "<title>PetClinic-Evolve Metric Gallery</title>",
        FONT_LINK,
        f"<style>{PAGE_CSS}</style>",
        "<div class='wrap'>",
        "<p class='eyebrow'>Architecture as the independent variable "
        "&middot; four conditions &middot; 4,800 checkpoints</p>",
        "<h1>One metric at a time</h1>",
        "<div class='measure'>",
        f"<p class='lede'>Every one of the {n_metrics} numbers this experiment "
        "reports, explained on its own: what it is, how it is computed, how to "
        "read it, and how it can be misread. Each one sits beside a figure "
        "showing all four prompting conditions across both architectures.</p>",
        "<p>An AI agent implements sixty change requests, one after another, all "
        "landing on the same REST endpoint. The full acceptance suite runs after "
        "every one. That happens on a conventional Spring codebase and on the same "
        "application built with OfficeFloor, ten independent runs each, with the "
        "model held fixed. These pages are the measuring instruments.</p>",
        "<p>Each figure carries the same eight series: four conditions across the "
        "top sharing a y-axis, and within each panel the two architectures as "
        "coloured lines. The line is the mean over ten runs. The band is "
        "&plusmn;1 standard deviation across those ten, so a gap you can see "
        "outside the bands is a gap the runs agree on.</p>",
        "<p>The shaded strip on the right of every panel is the final phase. That "
        "is the last twelve change requests of the sixty. The dashed rule across "
        "it is the mean over that window, which is the number to quote for where "
        "a run ended up. It is steadier than the value at the final checkpoint, "
        "and for the noisier per-request measures such as cost or regressions a "
        "single checkpoint says very little. The table under each figure gives "
        "that mean for all five phases, so you can see the shape of the run as "
        "numbers as well as as a line.</p>",
        "<p>Every metric carries its formula. The point is that you should be able "
        "to recompute the number rather than take it on trust, so each one names "
        "what is summed, over what population, and where the harness departs from "
        "the published definition.</p>",
        "</div>",
        "<h2 class='group' style='margin-top:3rem'>The four conditions</h2>",
        "<div class='tablewrap'><table class='runkey'><thead><tr>"
        "<th>condition</th><th>what the agent was given</th><th>run</th>"
        "</tr></thead><tbody>",
    ]
    for cond, rid, blurb in RUNS:
        parts.append(f"<tr><td class='cond'><b>{esc(cond)}</b></td>"
                     f"<td>{esc(blurb)}</td><td class='key'>{esc(rid)}</td></tr>")
    parts.append("</tbody></table></div>")
    parts.append(
        "<p class='note'>A condition is what the agent was <i>prompted</i> with, "
        "not what a run&rsquo;s <code>strategy</code> column is named. Every run is "
        "ten chains per architecture &times; sixty change requests = 1,200 "
        "checkpoints; the model, the change requests and the hidden acceptance "
        "suite are identical across all four.</p>")

    parts.append("<nav class='toc'><h2>Contents</h2><div class='toccols'>")
    for gkey, gtitle, _gintro in cat.GROUPS:
        items = rows_by_group.get(gkey, [])
        if not items:
            continue
        parts.append(f"<section><h3><a href='#g-{esc(gkey)}'>{esc(gtitle)}</a></h3><ul>")
        for field, entry, _d in items:
            parts.append(f"<li><a href='#{esc(field)}'>{esc(entry['title'])}</a></li>")
        parts.append("</ul></section>")
    parts.append("</div></nav>")

    for gkey, gtitle, gintro in cat.GROUPS:
        items = rows_by_group.get(gkey, [])
        if not items:
            continue
        parts.append(
            f"<div class='groupband' id='g-{esc(gkey)}'>"
            f"<h2 class='group'>{esc(gtitle)}</h2>"
            f"<p class='groupintro measure'>{gintro}</p></div>")
        for field, entry, d in items:
            parts.append(render_metric(field, entry, d, img_rel))

    parts.append(
        "<div class='groupband'><h2 class='group'>How the figures were "
        "produced</h2></div><div class='measure'>"
        "<p>Every figure is built from each run&rsquo;s "
        "<code>records.concat.csv</code>, the per-checkpoint record the harness "
        "writes, and aggregated exactly as the experiment&rsquo;s own analysis "
        "aggregates it. Missing values are dropped. Values are averaged across the "
        "ten independent runs at each change request, and the band is one standard "
        "deviation across those ten. Nothing here is recomputed from source. Where "
        "a figure disagrees with a run&rsquo;s own summary, the run is right and "
        "this page has a bug.</p>"
        "<p><b>Every number on this page is descriptive.</b> The phase means are "
        f"averages of the data and nothing more. There is no slope here, no "
        f"confidence interval, no significance test and no effect size, and that "
        f"is deliberate. Those are inferential claims, and across "
        f"{n_metrics} metrics a plain 95% interval manufactures several false "
        f"positives per run. They live in each run&rsquo;s "
        f"<code>summary.md</code>, which carries the Benjamini-Hochberg "
        f"correction over the whole family, Cliff&rsquo;s delta effect sizes, and "
        f"a counter-signals section listing every measure that came out against "
        f"its pre-declared expectation. A gap you can see between two phase means "
        f"here is a gap in the means. Whether it survives the correction is a "
        f"question this page does not answer.</p>"
        f"<p class='note'>Generated by <code>tools/gallery/metric_gallery.py</code>; "
        f"the explanations and formulas live in "
        f"<code>tools/gallery/metric_catalog.py</code>. {n_metrics} metrics, "
        f"{meta['n_figs']} figures.</p></div>")
    parts.append("</div>")

    out = os.path.join(out_dir, filename)
    with open(out, "w") as fh:
        fh.write("\n".join(parts) + "\n")
    return out


PHASE_NOTE = (
    "Each cell is the mean over that fifth of the run, averaged across the ten "
    "runs. Sixty change requests divide into five phases of twelve, so "
    "<b>Final</b> is the average of the last twelve, which is the window shaded "
    "in the figure. Change is Start to Final. These are descriptive means. There "
    "is no interval and no significance test on them.")


def phase_rows(d: dict):
    """(condition, arm, [mean per phase], start-to-final change) in figure order.

    The one place the table's contents are decided, so the page and the Blogger
    fragment cannot disagree about a number. They differ only in markup.
    """
    out = []
    for cond, _rid, _b in RUNS:
        for arm in ARMS:
            ph = d["data"][cond][arm].get("phases", {})
            vals = [ph.get(name, float("nan")) for name in PHASES]
            out.append((cond, arm, vals, pct_change(vals[0], vals[-1])))
    return out


def _all_blank(rows) -> bool:
    return all(all(math.isnan(v) for v in vals) for _c, _a, vals, _ch in rows)


def render_phase_table(d: dict) -> str:
    """The phase table for index.html. Empty string when the metric has no data
    anywhere, which is the same condition that drops its figure."""
    rows = phase_rows(d)
    if _all_blank(rows):
        return ""
    head = ("<tr><th class='l'>condition</th><th class='l'>architecture</th>"
            + "".join(f"<th{' class=\'fin\'' if name == FINAL_PHASE else ''}>"
                      f"{esc(name)}</th>" for name in PHASES)
            + "<th>change</th></tr>")
    body = []
    for i, (cond, arm, vals, chg) in enumerate(rows):
        first = i % len(ARMS) == 0
        grp = " class='grp'" if first and i else ""
        acls = "s" if arm == "spring" else "o"
        cells = "".join(
            f"<td class='fin'>{esc(fmt(v))}</td>" if name == FINAL_PHASE
            else f"<td>{esc(fmt(v))}</td>"
            for name, v in zip(PHASES, vals))
        body.append(
            f"<tr{grp}><td class='l cond'>{esc(cond) if first else ''}</td>"
            f"<td class='l arm {acls}'>{esc(ARM_LABEL[arm])}</td>"
            f"{cells}<td class='chg'>{esc(chg)}</td></tr>")
    return ("<div class='tablewrap'><table class='phases'><thead>"
            + head + "</thead><tbody>" + "".join(body)
            + "</tbody></table></div>"
            + f"<p class='tabcap'>{PHASE_NOTE}</p>")


# The direction is a real claim about the metric -- for the `amount` group it is
# the experiment's PREDICTION, not a preference -- so it is encoded in form (a
# glyph) as well as words, and sits beside the metric key rather than in prose.
DIR_CHIP = {
    "down": ("\u2193", "lower is better"),
    "up":   ("\u2191", "higher is better"),
    "flat": ("=", "prediction: no arm difference"),
    "":     ("\u00b7", "descriptive"),
}


def render_metric(field: str, entry: dict, d: dict, img_rel: str) -> str:
    glyph, dlabel = DIR_CHIP.get(entry.get("direction", ""), DIR_CHIP[""])
    p = [f"<div class='metric' id='{esc(field)}'>",
         f"<h3>{esc(entry['title'])}</h3>",
         "<div class='metahead'>",
         f"<span class='key'>{esc(field)}</span>",
         f"<span class='dir'><span class='g'>{glyph}</span> {esc(dlabel)}</span>",
         "</div>"]
    if d.get("fig"):
        p.append(
            f"<figure><div class='plate'><img src='{esc(img_rel)}{esc(field)}.png' "
            f"alt='{esc(entry['title'])}: four panels, one per condition, each "
            f"plotting Spring and OfficeFloor over the sixty change requests' "
            f"loading='lazy'></div></figure>")
    # Directly under the figure: the table is the figure's own numbers, and the
    # Final column is the window the figure shades.
    p.append(render_phase_table(d))
    if entry.get("what"):
        p.append(f"<p class='what'>{entry['what']}</p>")
    # The formula gets its own block rather than a definition-list row. It is the
    # reason this page exists in this form: a reader should be able to recompute
    # the number, and an equation buried in a prose column cannot be read.
    if entry.get("formula"):
        p.append("<div class='eq'><div class='eqlabel'>How it is calculated</div>"
                 f"<div class='eqbody'>{entry['formula']}</div></div>")
    p.append("<dl>")
    for k, lab in (("terms", "Where"), ("how", "In this harness"),
                   ("source", "Definition"), ("read", "How to read it")):
        if entry.get(k):
            p.append(f"<dt>{lab}</dt><dd>{entry[k]}</dd>")
    p.append("</dl>")
    if entry.get("caveat"):
        p.append(f"<div class='caveat'><b class='lbl'>Careful.</b> "
                 f"{entry['caveat']}</div>")
    p.append("</div>")
    return "\n".join(p)


# --------------------------------------------------------------------------
# Blogger output.
#
# Blogger posts are HTML FRAGMENTS pasted into the editor's HTML view, rendered
# inside the blog's own template. Two consequences drive everything below:
#
#   1. A <style> block in a post body fights the template and is stripped by
#      some themes, so every rule here is an inline style attribute and no
#      element carries a class. This matches the convention the existing posts
#      in blog/*.html already use.
#   2. Blogger cannot host 101 images for you without 101 manual uploads. So the
#      images are referenced by absolute URL from wherever they are hosted
#      (`--img-base`), and `publish_figs.sh` puts them on GitHub Pages in one
#      command. Nothing is uploaded through the Blogger editor.
#
# One post PER GROUP rather than one giant post: 101 figures is roughly 18 MB of
# images, which is a bad page at any connection speed, and the ten groups are
# already the natural post boundaries. `--blogger-single` overrides that.
# --------------------------------------------------------------------------
BL = {                                        # inline styles, Blogger-safe
    "h3": "margin: 1.9em 0 0.35em; font-size: 1.28em; line-height: 1.3;",
    "meta": "margin: 0 0 1em; font-size: 0.86em; color: rgb(119, 119, 119);",
    "code": "font-family: ui-monospace, Menlo, monospace; font-size: 0.95em;",
    "img": "width: 100%; height: auto; display: block; "
           "border: 1px solid rgb(221, 221, 221);",
    "cap": "margin: 0.5em 0 1.2em; font-size: 0.82em; color: rgb(136, 136, 136);",
    "eq": "margin: 1.2em 0; padding: 0.8em 1em; "
          "background: rgb(247, 247, 245); "
          "border: 1px solid rgb(225, 225, 220); border-radius: 4px;",
    "eqlabel": "font-size: 0.7em; letter-spacing: 0.1em; text-transform: uppercase; "
               "color: rgb(136, 136, 136); margin-bottom: 0.5em;",
    "eqbody": "font-family: ui-monospace, Menlo, monospace; font-size: 0.95em; "
              "line-height: 2; overflow-x: auto; white-space: nowrap;",
    "caveat": "margin: 1.1em 0; padding: 0.8em 1em; "
              "background: rgb(253, 245, 241); "
              "border-left: 3px solid rgb(235, 104, 52);",
    "table": "border-collapse: collapse; width: 100%; font-size: 0.88em;",
    "th": "padding: 6px 10px 6px 0; text-align: left;",
    "td": "padding: 6px 10px 6px 0;",
    "trh": "border-bottom: 2px solid rgb(204, 204, 204); text-align: left;",
    "tr": "border-bottom: 1px solid rgb(238, 238, 238);",
    "trg": "border-bottom: 1px solid rgb(238, 238, 238); "
           "border-top: 1px solid rgb(204, 204, 204);",
    "thn": "padding: 6px 0 6px 12px; text-align: right; font-size: 0.82em; "
           "letter-spacing: 0.05em; text-transform: uppercase; "
           "color: rgb(136, 136, 136);",
    "tdn": "padding: 5px 0 5px 12px; text-align: right; "
           "font-family: ui-monospace, Menlo, monospace; font-size: 0.92em;",
    "tdfin": "padding: 5px 0 5px 12px; text-align: right; font-weight: bold; "
             "font-family: ui-monospace, Menlo, monospace; font-size: 0.92em;",
    "tdchg": "padding: 5px 0 5px 12px; text-align: right; "
             "font-family: ui-monospace, Menlo, monospace; font-size: 0.92em; "
             "color: rgb(119, 119, 119);",
    "spring": "color: rgb(235, 104, 52); font-weight: bold;",
    "of": "color: rgb(42, 120, 214); font-weight: bold;",
    "note": "font-size: 0.86em; color: rgb(119, 119, 119);",
}
ARM_STYLE = {"spring": BL["spring"], "officefloor": BL["of"]}

BLOGGER_PREAMBLE = (
    '<p><i>Part of a <a href="https://blog.officefloor.net/2026/08/'
    'architecture-as-independent-variable.html" target="_blank">series</a> on how '
    'software architecture shapes AI driven code degradation. This post explains a '
    'group of measurements on their own. Each metric gets its definition, its '
    'figure, and its numbers.</i></p>\n'
    '<p>The setup is the same every time. An AI agent implements sixty change '
    'requests, one after another, all landing on the same REST endpoint. The full '
    'test suite runs after every one. That happens on a normal Spring codebase and '
    'on the same application built with OfficeFloor. Ten independent runs each. The '
    'model never changes.</p>\n'
    '<p>Every figure below carries the same eight series. Four prompting conditions '
    'run across the top, sharing a y-axis. Inside each panel the two architectures '
    'are the two coloured lines. The line is the mean of ten runs. The band is one '
    'standard deviation across those ten, so a gap you can see outside the bands is '
    'a gap the runs agree on.</p>\n'
    '<p>The shaded strip at the right of each panel is the final phase. That is the '
    'last twelve change requests of the sixty, and the dashed rule across it is the '
    'mean over that window. It is the number to quote for where a run ended up, '
    'because it is far steadier than the value at the final checkpoint. Under every '
    'figure is a table of that mean for all five phases, for all eight series.</p>\n'
    '<p>Beneath the four panels every figure carries one more row, running the full '
    'width, which puts those eight final-phase means side by side. The short flat '
    'line is the mean and each dot is one of the ten runs. Read that row before '
    'trusting any gap between two means, because a mean of ten runs can be carried '
    'by two of them, and on this experiment it sometimes is. That row has its own '
    'y-scale, since the panels above span the whole run and would flatten it.</p>\n'
    '<p>Each metric carries its formula, because you should be able to recompute '
    'the number rather than take it on trust.</p>\n'
)


def blogger_conditions_table() -> str:
    rows = "".join(
        f'<tr style="{BL["tr"]}"><td style="{BL["td"]}">'
        f'<code style="{BL["code"]}">{esc(c)}</code></td>'
        f'<td style="{BL["td"]}">{esc(b)}</td></tr>\n'
        for c, _r, b in RUNS)
    return (f'<table style="{BL["table"]}"><tbody>\n'
            f'<tr style="{BL["trh"]}"><th style="{BL["th"]}">condition</th>'
            f'<th style="{BL["th"]}">what the agent was given</th></tr>\n'
            f'{rows}</tbody></table>\n')


def blogger_phase_table(d: dict) -> str:
    """Same numbers as `render_phase_table`, in Blogger's inline-style markup.

    Built from `phase_rows` so the two cannot disagree. No class attributes and
    no <style> block, for the reasons in the section comment above.
    """
    rows = phase_rows(d)
    if _all_blank(rows):
        return ""
    head = (f'<tr style="{BL["trh"]}"><th style="{BL["th"]}">condition</th>'
            f'<th style="{BL["th"]}">architecture</th>'
            + "".join(f'<th style="{BL["thn"]}">{esc(name)}</th>'
                      for name in PHASES)
            + f'<th style="{BL["thn"]}">change</th></tr>\n')
    body = []
    for i, (cond, arm, vals, chg) in enumerate(rows):
        first = i % len(ARMS) == 0
        tr = BL["trg"] if first and i else BL["tr"]
        cells = "".join(
            f'<td style="{BL["tdfin"] if name == FINAL_PHASE else BL["tdn"]}">'
            f'{esc(fmt(v))}</td>'
            for name, v in zip(PHASES, vals))
        body.append(
            f'<tr style="{tr}"><td style="{BL["td"]}">'
            f'{esc(cond) if first else ""}</td>'
            f'<td style="{BL["td"]}"><span style="{ARM_STYLE[arm]}">'
            f'{esc(ARM_LABEL[arm])}</span></td>'
            f'{cells}<td style="{BL["tdchg"]}">{esc(chg)}</td></tr>\n')
    return (f'<table style="{BL["table"]}"><tbody>\n{head}{"".join(body)}'
            f'</tbody></table>\n'
            f'<p style="{BL["cap"]}">{PHASE_NOTE}</p>\n')


def blogger_metric(field: str, entry: dict, d: dict, img_base: str) -> str:
    glyph, dlabel = DIR_CHIP.get(entry.get("direction", ""), DIR_CHIP[""])
    out = [f'<h3 style="{BL["h3"]}">{esc(entry["title"])}</h3>\n',
           f'<p style="{BL["meta"]}"><code style="{BL["code"]}">{esc(field)}</code>'
           f' &nbsp;&middot;&nbsp; {glyph} {esc(dlabel)}'
           f' &nbsp;&middot;&nbsp; {entry.get("source", "")}</p>\n']
    if d.get("fig"):
        url = f"{img_base}{field}.png"
        # Linked so a reader can open the full size figure. The four panels are
        # small at blog column width and the detail is worth a click.
        out.append(f'<a href="{esc(url)}" target="_blank">'
                   f'<img src="{esc(url)}" alt="{esc(entry["title"])}" '
                   f'style="{BL["img"]}" loading="lazy"></a>\n')
        out.append(f'<p style="{BL["cap"]}">Line is the mean of ten runs. Band is '
                   f'one standard deviation. The shaded strip is the final twelve '
                   f'change requests and the dashed rule is their mean. The row '
                   f'beneath puts those eight means side by side, one dot per run, '
                   f'on its own y-scale. Click for full size.</p>\n')
    out.append(blogger_phase_table(d))
    if entry.get("what"):
        out.append(f'<p>{entry["what"]}</p>\n')
    if entry.get("formula"):
        out.append(f'<div style="{BL["eq"]}">'
                   f'<div style="{BL["eqlabel"]}">How it is calculated</div>'
                   f'<div style="{BL["eqbody"]}">{entry["formula"]}</div></div>\n')
    for k, lab in (("terms", "Where."), ("how", "In this harness."),
                   ("read", "How to read it.")):
        if entry.get(k):
            out.append(f'<p><b>{lab}</b> {entry[k]}</p>\n')
    if entry.get("caveat"):
        out.append(f'<div style="{BL["caveat"]}"><b>Careful.</b> '
                   f'{entry["caveat"]}</div>\n')
    return "".join(out)


def blogger_footnote(n_metrics: int) -> str:
    return (
        f'<p style="{BL["note"]}">Every figure is built from each run&rsquo;s '
        f'per-checkpoint record. Missing values are dropped. Values are averaged '
        f'across the ten independent runs at each change request, and the band is '
        f'one standard deviation across those ten. Nothing is recomputed from '
        f'source: where a figure disagrees with a run&rsquo;s own summary, the run '
        f'is right. The phase means in each table are averages of that same '
        f'record, over the twelve change requests in each fifth of the run, '
        f'averaged again across the ten runs.</p>\n'
        f'<p style="{BL["note"]}">Every number here is descriptive. There is no '
        f'slope, no confidence interval, no significance test and no effect size '
        f'on this page, because across {n_metrics} metrics a plain 95% interval '
        f'manufactures several false positives per run. The run summaries carry '
        f'those, with Benjamini-Hochberg FDR over the whole family and '
        f'Cliff&rsquo;s delta effect sizes. These posts explain what each metric '
        f'is. They are not where a result gets established.</p>\n')


def write_blogger(rows_by_group: dict, out_dir: str, img_base: str,
                  single: bool) -> list[str]:
    bdir = os.path.join(out_dir, "blogger")
    os.makedirs(bdir, exist_ok=True)
    n_metrics = sum(len(v) for v in rows_by_group.values())
    order = [g for g, _t, _i in cat.GROUPS]
    written = []

    def body_for(groups: list[str]) -> str:
        chunks = [BLOGGER_PREAMBLE, blogger_conditions_table()]
        for gkey in groups:
            items = rows_by_group.get(gkey, [])
            if not items:
                continue
            gtitle = next(t for g, t, _i in cat.GROUPS if g == gkey)
            gintro = next(i for g, _t, i in cat.GROUPS if g == gkey)
            chunks.append(f"<h2>{esc(gtitle)}</h2>\n<p>{gintro}</p>\n")
            for field, entry, d in items:
                chunks.append(blogger_metric(field, entry, d, img_base))
        chunks.append("<h2>How the numbers were produced</h2>\n")
        chunks.append(blogger_footnote(n_metrics))
        return "".join(chunks)

    if single:
        path = os.path.join(bdir, "all-metrics.html")
        with open(path, "w") as fh:
            fh.write(body_for([g for g in order if rows_by_group.get(g)]))
        written.append(path)
    else:
        for i, gkey in enumerate([g for g in order if rows_by_group.get(g)], 1):
            path = os.path.join(bdir, f"{i:02d}-{gkey}.html")
            with open(path, "w") as fh:
                fh.write(body_for([gkey]))
            written.append(path)

    readme = os.path.join(bdir, "00-HOW-TO-POST.txt")
    with open(readme, "w") as fh:
        fh.write(BLOGGER_HOWTO.format(
            img_base=img_base, n=len(written),
            files="\n  ".join(os.path.basename(w) for w in written)))
    written.append(readme)
    return written


BLOGGER_HOWTO = """How to put these in Blogger
===========================

Each .html file here is ONE Blogger post body. They are HTML fragments, not
whole pages. They carry no <style> block and no class attributes, so they
inherit your blog template and cannot fight it.

Images are NOT uploaded to Blogger. Every <img> points at:

  {img_base}

Host the figures there first, then paste. `tools/gallery/publish_figs.sh` does
the hosting in one command using GitHub Pages.

Steps
-----
1. Host the figures.

     ./tools/gallery/publish_figs.sh --push

   It prints the base URL when it finishes. Enable Pages on the repo once, from
   the gh-pages branch, if you have not already.

2. Regenerate these fragments against that URL.

     python -m tools.gallery.metric_gallery --no-figs --blogger \\
         --img-base https://<user>.github.io/<repo>/figs/

3. For each file: in Blogger, New post, switch the editor from Compose to HTML,
   paste the whole file, switch back to Compose to eyeball it, publish.

   There are {n} of them:

  {files}

Notes
-----
* One post per metric group, on purpose. All 101 figures in a single post is
  about 18 MB of images. Pass --blogger-single if you want one post anyway.
* Every image is wrapped in a link to itself, so a reader can click through to
  the full 1740px figure. The panels are small at blog column width.
* Do not re-upload the images through the Blogger editor. That is the 101 manual
  uploads this whole route exists to avoid, and it would also break the links.
* Every figure has the final phase shaded, with each architecture's mean over
  those last twelve change requests drawn and labelled, and a five-phase table
  under it. Those numbers cost nothing and are always there.
* Re-running step 2 is safe and cheap. Add --stats for metrics.csv, and
  --n-boot 2000 with it for publication grade confidence intervals, which takes
  about seven minutes. Neither changes the posts.
"""


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=os.path.join(_REPO, "results"))
    ap.add_argument("--out", default=os.path.join(_REPO, "blog", "metric-gallery"),
                    help="output directory for figs/, metrics.csv and index.html")
    ap.add_argument("--only", default="",
                    help="comma-separated metric keys to regenerate (default: all)")
    ap.add_argument("--n-boot", type=int, default=600,
                    help="bootstrap replicates for the slope CI (2000 for publication)")
    # index.html publishes its figures alongside itself, so it always references
    # them relatively. Only the Blogger fragments need an absolute host, because
    # they are pasted into someone else's page. Sharing one flag between the two
    # silently broke the local page the first time the Blogger URL was passed.
    ap.add_argument("--img-base", default="",
                    help="absolute URL prefix for <img src> in the BLOGGER "
                         "fragments, e.g. https://user.github.io/repo/figs/ . "
                         "index.html always uses its own relative figs/")
    ap.add_argument("--no-figs", action="store_true",
                    help="regenerate the page and the CSV without redrawing the PNGs")
    ap.add_argument("--stats", action="store_true",
                    help="also write metrics.csv: per metric, condition and arm, "
                         "all five phase means and a bootstrapped slope. OFF by "
                         "default. The phase means themselves are free and are on "
                         "the page, the posts and the figures either way; this flag "
                         "buys the SLOPE, which is the bootstrap and is all of the "
                         "run time")
    ap.add_argument("--reuse-stats", action="store_true",
                    help="read the SLOPES back from an existing metrics.csv instead "
                         "of bootstrapping them again. The bootstrap is the only "
                         "slow part (~7 min), and a prose-only edit changes no "
                         "number, so use this when iterating on text. Phase means "
                         "are always recomputed, because they are free and a stale "
                         "one would be silent. Only meaningful with --stats")
    ap.add_argument("--blogger", action="store_true",
                    help="also write Blogger-ready post fragments to <out>/blogger/ "
                         "(inline styles, absolute image URLs, one post per group)")
    ap.add_argument("--blogger-single", action="store_true",
                    help="with --blogger, emit ONE post containing every metric "
                         "instead of one post per group")
    args = ap.parse_args(argv)

    check_catalog_style()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    fig_dir = os.path.join(args.out, "figs")
    os.makedirs(fig_dir, exist_ok=True)

    # Cached stats, if asked for and present. Keyed (metric, condition, arm).
    cached: dict = {}
    if args.reuse_stats and args.stats:
        cpath = os.path.join(args.out, "metrics.csv")
        if os.path.isfile(cpath):
            with open(cpath, newline="") as fh:
                for r in csv.DictReader(fh):
                    cached[(r["metric"], r["condition"], r["arm"])] = r
            print(f"Reusing {len(cached)} cached stat rows from {cpath}")
        else:
            print(f"  --reuse-stats: no {cpath} yet, computing from scratch")

    print("Loading runs...")
    loaded = {}
    for cond, rid, _b in RUNS:
        rows = load_run(args.results_dir, rid)
        loaded[cond] = split_by_arm(rows)
        got = {a: len(v) for a, v in loaded[cond].items()}
        print(f"  {cond:18s} {rid}  {got}")
        missing = [a for a in ARMS if a not in loaded[cond]]
        if missing:
            print(f"    WARNING: no rows for {missing} -- those series will be blank")

    fields = [f for f in cat.M if not only or f in only]
    unknown = only - set(cat.M)
    if unknown:
        print(f"  WARNING: not in the catalogue, skipped: {sorted(unknown)}")

    rows_by_group: dict[str, list] = defaultdict(list)
    csv_rows = []
    n_figs = 0

    for i, field in enumerate(fields, 1):
        entry = cat.M[field]
        data = {}
        for cond, _rid, _b in RUNS:
            data[cond] = {}
            for arm in ARMS:
                rows = loaded[cond].get(arm, [])
                curve = mean_curve(rows, field) if rows else None
                # Phase means are arithmetic over rows already in memory, so they
                # cost nothing and are computed on EVERY build. The figures, the
                # page and the posts all show them. The bootstrap slope is the
                # only slow thing in this tool, and only it stays behind --stats.
                phases = all_phase_means(rows, field) if rows else {}
                if args.stats:
                    hit = cached.get((field, cond, arm))
                    if hit:
                        slope = tuple(analyze._f(hit[k]) for k in
                                      ("slope_per_rule", "slope_ci_lo", "slope_ci_hi"))
                    else:
                        slope = slope_ci(rows, field, args.n_boot) if rows else (float("nan"),) * 3
                else:
                    slope = (float("nan"),) * 3
                data[cond][arm] = {
                    "curve": curve,
                    "phases": phases,
                    "final_window": phase_window(rows, FINAL_PHASE) if rows else None,
                    # Per-chain final-phase values, for the summary strip under the
                    # panels. The mean alone cannot show that an effect is carried by
                    # two runs out of ten, and on this experiment it sometimes is.
                    "final_by_chain": (phase_mean_by_chain(rows, field, FINAL_PHASE)
                                       if rows else {}),
                    "slope": slope,
                }
        has_data = any(data[c][a]["curve"] is not None for c, _r, _b in RUNS for a in ARMS)
        if not has_data:
            print(f"  [{i:3d}/{len(fields)}] {field:32s} no data in any run -- skipped")
            continue

        drew = False
        png = os.path.join(fig_dir, f"{field}.png")
        if args.no_figs:
            drew = os.path.isfile(png)
        else:
            drew = build_figure(field, entry, data, png)
        n_figs += 1 if drew else 0

        rows_by_group[entry["group"]].append(
            (field, entry, {"data": data, "fig": drew}))
        for cond, _rid, _b in RUNS if args.stats else ():
            for arm in ARMS:
                d = data[cond][arm]
                sl, lo, hi = d["slope"]
                row = {
                    "metric": field, "title": entry["title"],
                    "group": entry["group"], "direction": entry.get("direction", ""),
                    "condition": cond, "arm": arm,
                }
                # All five phases, not just the two ends. `start_mean` and
                # `final_mean` keep their old spellings so anything already
                # reading this file still reads it.
                for ph in PHASES:
                    row[f"{ph.lower()}_mean"] = d["phases"].get(ph, float("nan"))
                row.update({
                    "slope_per_rule": sl, "slope_ci_lo": lo, "slope_ci_hi": hi,
                    "n_chains": d["curve"][3] if d["curve"] else 0,
                })
                csv_rows.append(row)
        print(f"  [{i:3d}/{len(fields)}] {field:32s} {'fig' if drew else '---'}")

    # Preserve the catalogue's authored order within each group.
    order = {f: n for n, f in enumerate(cat.M)}
    for g in rows_by_group:
        rows_by_group[g].sort(key=lambda t: order[t[0]])

    # A partial run writes to its OWN page and CSV. `--only` is for iterating on
    # one figure, and it used to rewrite index.html/metrics.csv down to just that
    # metric -- quietly destroying the full gallery from the last complete run,
    # with nothing in the output saying so.
    partial = bool(only)
    page_name = "index.partial.html" if partial else "index.html"

    csv_path = None
    if csv_rows:
        csv_name = "metrics.partial.csv" if partial else "metrics.csv"
        csv_path = os.path.join(args.out, csv_name)
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(csv_rows[0]))
            w.writeheader()
            w.writerows(csv_rows)

    page = render_page(rows_by_group, args.out, PAGE_IMG_BASE,
                       {"n_metrics": sum(len(v) for v in rows_by_group.values()),
                        "n_figs": n_figs},
                       filename=page_name)
    print(f"\nWrote {n_figs} figures to {fig_dir}")
    if csv_path:
        print(f"Wrote {csv_path}")
    print(f"Wrote {page}")

    if args.blogger or args.blogger_single:
        if not args.img_base.startswith(("http://", "https://")):
            print(f"\n  WARNING: --img-base is {args.img_base!r}, which is a "
                  f"relative path.\n  Blogger needs an absolute URL or the "
                  f"images will not load. Host the\n  figures first "
                  f"(tools/gallery/publish_figs.sh) and re-run with\n  "
                  f"--img-base https://<user>.github.io/<repo>/figs/")
        for w in write_blogger(rows_by_group, args.out, args.img_base,
                               args.blogger_single):
            print(f"Wrote {w}")
    if partial:
        print("\n  NOTE: --only run. The figures above ARE updated in figs/, but the\n"
              "  page and CSV went to *.partial.* so the full gallery is untouched.\n"
              "  Re-run without --only (or with --no-figs) to rebuild index.html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
