"""Build an ImpactGate baseline distribution from a completed run's OWN per-change
structural-impact observations.

Motivation. The `impact_gated` strategy (see harness/impact_gate.py) normally grades a
change against ImpactGate's generic OSS Java seed. But the experiment's real question is
whether prompting can hold the ERODING arm (Spring, one growing @RestController) to the
cohesion the SPREADING arm (OfficeFloor, many small wired functions) achieves naturally.
The prior run (blog.officefloor.net "The same complexity: one unit or twenty?") showed
OfficeFloor keeps each change tiny. So calibrate the gate to OfficeFloor's OWN observed
`impact_composite` distribution: grade every Spring change against "how impactful is this
vs the full distribution of OfficeFloor changes", and refactor when it lands above a chosen
percentile of that distribution. Held to OfficeFloor's numbers, Spring gets a chance to keep
similar cohesion — the thing under test.

This writes an ImpactGate baseline JSON (`{"_meta": {...}, "distribution": [sorted ints]}`,
the format impact-gate score --baseline-file consumes). Point config.yaml
impact_gate.baseline_file at it and set impact_gate.curve_prior_weight: 0 to grade PURELY
against this distribution (ignore the seed). Then block_percentile is read against the
reference arm's distribution: block_percentile 90 == "refactor when a change is more
impactful than 90% of OfficeFloor's changes".

Observations come from the run's analysis CSV (results/<run_id>/records.concat.csv, written
by `analyze`) when present — fast, no recompute — else they are recomputed from the branches
(slow). One observation = one checkpoint's `impact_composite` (agent-commit delta), > 0 only.

Usage:
  python -m harness.build_impact_baseline --config config.yaml --run-id blind-202608100006 \
      --arm officefloor --strategy just-solve --out baselines/officefloor.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os

import yaml

from . import expand_path


def _from_csv(csv_path: str, arm: str, strategy: str) -> list[int]:
    vals: list[int] = []
    with open(csv_path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("arm") != arm or r.get("strategy") != strategy:
                continue
            try:
                v = float(r.get("impact_composite", "") or "nan")
            except ValueError:
                continue
            if v > 0:
                vals.append(int(round(v)))
    return vals


def _from_branches(cfg: dict, run_id: str, arm: str, strategy: str) -> list[int]:
    """Fallback: recompute impact_composite from the branches (slow — materializes each
    checkpoint tree). Reuses analyze's own recompute path so the numbers match exactly."""
    from . import analyze
    work_root = expand_path(cfg["paths"]["work_root"], "paths.work_root")
    snap_tmp = os.path.join(work_root, "recompute-config", str(run_id) + "-baseline")
    os.makedirs(snap_tmp, exist_ok=True)
    eff_cfg = analyze._resolve_run_config(cfg, run_id, snap_tmp)
    rows = analyze.recompute_rows(eff_cfg, run_id, work_root,
                                  exclude=eff_cfg.get("acceptance", {}).get("dest_subpath"))
    vals: list[int] = []
    for r in rows:
        if r.get("arm") != arm or r.get("strategy") != strategy:
            continue
        try:
            v = float(r.get("impact_composite", "") or "nan")
        except (TypeError, ValueError):
            continue
        if v > 0:
            vals.append(int(round(v)))
    return vals


def _pct(sorted_vals: list[int], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    if q <= 0:
        return sorted_vals[0]
    if q >= 100:
        return sorted_vals[-1]
    i = (q / 100) * (len(sorted_vals) - 1)
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (i - lo) * (sorted_vals[hi] - sorted_vals[lo])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", required=True, help="the completed run to calibrate from")
    ap.add_argument("--arm", default="officefloor",
                    help="reference arm whose distribution defines cohesion (default officefloor)")
    ap.add_argument("--strategy", default="just-solve",
                    help="reference strategy (default just-solve — the ungated control)")
    ap.add_argument("--out", required=True, help="where to write the ImpactGate baseline JSON")
    ap.add_argument("--recompute", action="store_true",
                    help="ignore any analysis CSV and recompute from the branches (slow)")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    for name, arm_cfg in cfg["arms"].items():
        arm_cfg["repo"] = expand_path(arm_cfg["repo"], f"arms.{name}.repo")
    cfg_dir = os.path.dirname(os.path.abspath(args.config))

    def resolve(p):
        p = expand_path(p)
        return p if os.path.isabs(p) else os.path.join(cfg_dir, p)

    results_csv = resolve(cfg["paths"]["results_csv"])
    concat = os.path.join(os.path.dirname(results_csv), str(args.run_id), "records.concat.csv")

    if not args.recompute and os.path.exists(concat):
        vals = _from_csv(concat, args.arm, args.strategy)
        source = concat
    else:
        cfg["checkpoints_file"] = resolve(cfg["checkpoints_file"])
        cfg["paths"]["work_root"] = resolve(cfg["paths"]["work_root"])
        if cfg.get("tools", {}).get("astgrep_rules"):
            cfg["tools"]["astgrep_rules"] = resolve(cfg["tools"]["astgrep_rules"])
        vals = _from_branches(cfg, args.run_id, args.arm, args.strategy)
        source = f"branches (recomputed) for run {args.run_id}"

    if not vals:
        raise SystemExit(f"no positive impact_composite observations for {args.arm}/"
                         f"{args.strategy} in run {args.run_id} (source: {source}). "
                         "Run analyze first, or pass --recompute.")
    vals.sort()

    out = expand_path(args.out)
    out = out if os.path.isabs(out) else os.path.join(cfg_dir, out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    doc = {"_meta": {"tool": "impact-gate", "n": len(vals), "head": None,
                     "base_ref": f"{args.run_id}:{args.arm}/{args.strategy} impact_composite",
                     "source": os.path.basename(source)},
           "distribution": vals}
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=1)

    print(f"baseline written: {out}")
    print(f"  reference: {args.arm}/{args.strategy}  n={len(vals)}  (source: {source})")
    print(f"  distribution percentiles (composite impact):")
    for q in (50, 75, 90, 95, 98):
        print(f"    P{q:>2} = {_pct(vals, q):>10.0f}   "
              f"(block_percentile {q} fires when a change exceeds this)")
    print(f"    max  = {vals[-1]:>10.0f}")
    print("\nNext: set impact_gate.baseline_file to this path and impact_gate.curve_prior_weight: 0,")
    print("      pick impact_gate.block_percentile, then run --strategy impact_gated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
