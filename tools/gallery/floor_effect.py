#!/usr/bin/env python3
"""The floor-effect check for the plasticity result.

The obvious alternative explanation for the plasticity gap is arithmetic rather
than architectural. Left alone, the additive arm already sits near an even
distribution and so has little room to move, while the mutative arm sits far
from one and so has a great deal. If that is the whole story, the asymmetry in S
is a fact about starting positions and not about architecture.

Two checks are computed here, and they disagree, which is the point.

CHECK A, the correlation. The floor-effect account predicts that S(spring)
tracks how far apart the two arms are when nothing is asked of them, which is
their separation under the control condition. "How far apart" has no canonical
scale, so the correlation is computed under four parameterisations. The answer
depends on which one is used, so all four are reported rather than the most
favourable. Pearson gets a Fisher z interval; Spearman is reported beside it
because both quantities span orders of magnitude and the relation need not be
linear.

CHECK B, the room-normalised spread. For the metrics with a well-defined
even-distribution limit, the range over conditions is divided by the room the
arm actually had at its control position rather than by its own level. An HHI or
a top-1 share over n units bottoms out at 1/n, a Gini at 0, and a normalised
entropy tops out at 1. This is the floor-effect account taken at its word: if it
is right, both arms consume a similar fraction of the room available to them and
the ratio of the room-normalised spreads is near 1.

Usage:
    python -m tools.gallery.floor_effect
    python -m tools.gallery.floor_effect --latex
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.gallery.bootstrap_ratio import (  # noqa: E402
    ARMS, PLACEMENT, RUNS, chain_values, load,
)

CONTROL = "just-solve"

# The even-distribution limit for each metric that has one, and the column
# holding the population size n it depends on. "lo" metrics bottom out at the
# floor and the interventions push them down; "hi" metrics top out at 1 and the
# interventions push them up.
#
# HHI and a top-1 share over n units are both 1/n at perfect equality. A Gini is
# 0 there and needs no n. A normalised entropy is H/log2(n), which is 1 there.
BOUNDED = {
    "cum_change_top1":         ("lo", "cum_change_files"),
    "cum_change_hhi":          ("lo", "cum_change_files"),
    "cum_change_entropy_norm": ("hi", None),
    "ccdist_file_top1":        ("lo", "ccdist_file_n"),
    "ccdist_file_hhi":         ("lo", "ccdist_file_n"),
    "ccdist_file_gini":        ("lo", None),
    "wmcdist_class_hhi":       ("lo", "ck_classes"),
}


def cell_mean(data, label, arm, field):
    v = chain_values(data[label], arm, field)
    return float(np.mean(v)) if len(v) else float("nan")


def spread(data, arm, field):
    means = [cell_mean(data, l, arm, field) for l, _ in RUNS]
    return (max(means) - min(means)) / abs(float(np.mean(means)))


def _pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    r = float(np.corrcoef(x, y)[0, 1])
    n = len(x)
    # Fisher z. n-3 because the transform's variance is 1/(n-3) for the
    # interval on a single correlation.
    z, se = math.atanh(r), 1.0 / math.sqrt(n - 3)
    return r, math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)


def _spearman(x, y):
    def rank(v):
        order = np.argsort(np.asarray(v, float))
        rk = np.empty(len(v))
        rk[order] = np.arange(1, len(v) + 1)
        return rk
    return _pearson(rank(x), rank(y))


def check_a(data, fields=PLACEMENT):
    """Correlate S(spring) against the arms' control separation, four ways."""
    S = [spread(data, "spring", f) for f in fields]
    sp = [cell_mean(data, CONTROL, "spring", f) for f in fields]
    of = [cell_mean(data, CONTROL, "officefloor", f) for f in fields]
    variants = {
        "absolute, |sp - of|":
            [abs(a - b) for a, b in zip(sp, of)],
        "relative to the arm mean, |sp - of| / mean(sp, of)":
            [abs(a - b) / abs((a + b) / 2) for a, b in zip(sp, of)],
        "relative to OfficeFloor, |sp - of| / of":
            [abs(a - b) / abs(b) for a, b in zip(sp, of)],
        "log ratio, |log(sp / of)|":
            [abs(math.log(a / b)) for a, b in zip(sp, of)],
    }
    out = []
    for name, x in variants.items():
        r, lo, hi = _pearson(x, S)
        rs = _spearman(x, S)[0]
        out.append((name, r, lo, hi, rs))
    return out


def check_b(data, spec=BOUNDED):
    """Range over conditions divided by the room available to the arm.

    "Room" needs an n, and an HHI or top-1 floor of 1/n moves when the number of
    units moves. The interventions create files and classes, so an arm can buy
    itself room by splitting, and a range measured against the floor it started
    at can exceed that room. Both definitions are therefore computed:

      room_ctl   floor from the arm's own control-condition n. The room it had
                 before any intervention, which is what the floor-effect
                 objection is actually about.
      room_wide  floor from the largest n that arm reached across the four
                 conditions, so the lowest floor it demonstrably could reach.
                 Always the more generous of the two, and it caps S_room at
                 roughly 100%.

    The ratio between arms is reported under both. If it is stable across them
    the conclusion does not turn on the choice.
    """
    out = []
    for field, (direction, n_col) in spec.items():
        row = {"metric": field}
        for arm in ARMS:
            means = [cell_mean(data, l, arm, field) for l, _ in RUNS]
            rng = max(means) - min(means)
            ctl = cell_mean(data, CONTROL, arm, field)
            if direction == "hi":
                floors = [1.0]                   # normalised entropy tops out at 1
            elif n_col is None:
                floors = [0.0]                   # a Gini bottoms out at 0
            else:                                # HHI and top-1 bottom out at 1/n
                ns = [cell_mean(data, l, arm, n_col) for l, _ in RUNS]
                floors = [1.0 / cell_mean(data, CONTROL, arm, n_col), 1.0 / max(ns)]
            room_ctl = abs(ctl - floors[0])
            room_wide = abs(ctl - floors[-1])
            row[arm] = {
                "S": spread(data, arm, field), "ctl": ctl,
                "room": room_ctl, "room_wide": room_wide,
                "S_room": rng / room_ctl if room_ctl else float("nan"),
                "S_room_wide": rng / room_wide if room_wide else float("nan"),
            }
        row["R"] = row["spring"]["S"] / row["officefloor"]["S"]
        row["R_room"] = row["spring"]["S_room"] / row["officefloor"]["S_room"]
        row["R_room_wide"] = (row["spring"]["S_room_wide"]
                              / row["officefloor"]["S_room_wide"])
        out.append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(_REPO, "results"))
    ap.add_argument("--latex", action="store_true")
    a = ap.parse_args(argv)
    data = load(a.results)

    print("=== CHECK A: does S(spring) track the arms' control separation?")
    print(f"    over the {len(PLACEMENT)} placement metrics\n")
    for name, r, lo, hi, rs in check_a(data):
        if a.latex:
            print(f"{name} & ${r:+.2f}$ & $[{lo:+.2f}, {hi:+.2f}]$ & ${rs:+.2f}$ \\\\")
        else:
            print(f"  {name:52s} r={r:+.3f}  95% CI [{lo:+.2f},{hi:+.2f}]"
                  f"  rho={rs:+.3f}")

    print("\n=== CHECK B: range over conditions as a fraction of the room available")
    print("    room is |control - even-distribution limit| for each arm\n")
    rows = sorted(check_b(data), key=lambda r: -r["R_room_wide"])
    print(f"  {'metric':26s} {'room_sp':>8} {'room_of':>8}"
          f" {'Sroom_sp':>9} {'Sroom_of':>9} {'Rroom':>6} {'Rwide':>6} {'R':>6}")
    for row in rows:
        s, o = row["spring"], row["officefloor"]
        if a.latex:
            print(f"\\texttt{{{row['metric'].replace('_', chr(92) + '_')}}} & "
                  f"{s['room_wide']:.3f} & {o['room_wide']:.3f} & "
                  f"{s['S_room_wide']*100:.0f}\\% & {o['S_room_wide']*100:.0f}\\% & "
                  f"{row['R_room_wide']:.1f} & {row['R']:.1f} \\\\")
        else:
            print(f"  {row['metric']:26s} {s['room_wide']:8.4f} {o['room_wide']:8.4f}"
                  f" {s['S_room_wide']*100:8.1f}% {o['S_room_wide']*100:8.1f}%"
                  f" {row['R_room']:6.2f} {row['R_room_wide']:6.2f} {row['R']:6.2f}")
    for key, label in (("R_room", "room at the control n "),
                       ("R_room_wide", "room at the widest n  ")):
        v = [r[key] for r in rows]
        print(f"\n  {label}: min {min(v):.2f}  median {float(np.median(v)):.2f}"
              f"  max {max(v):.2f}  all above 1: {all(x > 1 for x in v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
