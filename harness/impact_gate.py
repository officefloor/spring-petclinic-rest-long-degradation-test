"""ImpactGate integration: score a checkpoint change and shape a refactor prompt.

A thin wrapper around the standalone `impact-gate` CLI (lizard-only; installed
separately, see README prerequisites). Used ONLY by the `impact_gated` strategy.

After the agent implements a checkpoint, the harness stages the production diff on
the worktree and calls `impact-gate score --mode staged --curve`. The change's
structural-impact composite is graded against ImpactGate's shipped Java seed
distribution; a grade at or above the configured BLOCK percentile "fails" the gate.
On a fail the harness discards the change and runs a refactor turn seeded with the
files ImpactGate flagged, the specific cost-driver methods/classes, AND the change
spec (so the agent refactors to make THIS upcoming change land cleanly), then
re-attempts. Up to `max_refactors` refactors per checkpoint; still failing after the
last one stops the chain. See `run_experiment.run_chain`.

The measure is the same before-context-WMC signal `analyze` reports as
`impact_composite`, so the gate gates exactly the erosion metric the run analyses.
"""
from __future__ import annotations

import json
import subprocess


class ImpactGateError(RuntimeError):
    """impact-gate could not be run or produced no parseable result (a hard error:
    the gated experiment cannot proceed un-scored)."""


def score(cmd: list[str], repo: str, block_percentile: float, warn_percentile: float,
          measure_config: str | None = None, baseline_file: str | None = None,
          curve_prior_weight: float | None = None, timeout: int = 300) -> dict:
    """Score the STAGED production diff of `repo` and return the parsed JSON dict:
    `impact` (composite), `level` (ok|warn|block), `grade.percentile`, the ranked
    `files`, and `top_units`. Raises ImpactGateError if the binary is missing or
    emits no JSON.

    Stage the change (`git add -A`) before calling. `--mode staged` scores staged
    vs HEAD, so the diff is exactly this checkpoint's (or refactor's) delta.

    `baseline_file` (absolute, outside the worktree) grades the change against a
    reference distribution instead of the shipped seed — e.g. OfficeFloor's own observed
    impact_composite, so Spring is held to that cohesion (see build_impact_baseline). With
    `curve_prior_weight=0` the grade is PURELY that distribution's percentile (seed
    ignored); block_percentile is then read against the reference arm."""
    argv = [*cmd, "score", "--repo", repo, "--mode", "staged",
            "--format", "json", "--curve",
            "--block-percentile", str(block_percentile),
            "--warn-percentile", str(warn_percentile)]
    if baseline_file:
        argv += ["--baseline-file", baseline_file]
    if curve_prior_weight is not None:
        argv += ["--curve-prior-weight", str(curve_prior_weight)]
    if measure_config:
        argv += ["--measure-config", measure_config]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, OSError) as e:
        raise ImpactGateError(
            f"could not run impact-gate ({' '.join(cmd)!r}): {e}. Install it into the "
            "harness venv (pip install -e ~/ImpactGate) or set impact_gate.cmd in "
            "config.yaml to the impact-gate binary.") from e
    except subprocess.TimeoutExpired as e:
        raise ImpactGateError(f"impact-gate timed out after {timeout}s") from e
    # Exit codes: 0 = ok/warn, 2 = blocked, 1 = usage/environment error. Only 1 is a
    # real failure; 0 and 2 both carry a valid JSON verdict on stdout.
    if proc.returncode == 1:
        raise ImpactGateError(f"impact-gate error (exit 1): {proc.stderr.strip()[:400]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ImpactGateError(
            f"impact-gate produced no JSON (exit {proc.returncode}): "
            f"stdout={proc.stdout[:200]!r} stderr={proc.stderr.strip()[:200]!r}") from e


def grade_percentile(ig: dict) -> float | None:
    """The change's percentile grade against the seed (None if ungraded/empty)."""
    return (ig.get("grade") or {}).get("percentile")


def is_blocked(ig: dict, block_percentile: float) -> bool:
    """The fail decision: the change grades at or above the block percentile. Keyed
    on the grade directly (not the CLI's `blocked` flag, which additionally requires
    enforcement=block), so it means exactly "grade >= block_percentile". An empty /
    ungraded change (no production source touched) never fails."""
    pct = grade_percentile(ig)
    if pct is None:
        return bool(ig.get("blocked"))
    return pct >= block_percentile


def _format_files(ig: dict, limit: int = 8) -> str:
    lines = []
    for f in (ig.get("files") or [])[:limit]:
        if (f.get("cost") or 0) <= 0:
            continue
        lines.append(f"  - {f['path']}  (impact cost {f['cost']}: "
                     f"{f.get('mut_fns', 0)} existing function(s) changed, "
                     f"{f.get('new_fns', 0)} new)")
    return "\n".join(lines) or "  (no files flagged)"


def _format_drivers(ig: dict, limit: int = 8) -> str:
    # Design B: locations ONLY. The refactor prompt names WHERE complexity concentrated as a
    # symptom, never the cost figures — exposing the numbers re-introduces the metric the AI is
    # not supposed to optimise (that is what the neutral implement prompt is for). No CC / WMC /
    # cost here.
    lines = []
    for u in (ig.get("top_units") or [])[:limit]:
        if (u.get("cost") or 0) <= 0:
            continue
        cls = u.get("container") or "(file scope)"
        lines.append(f"  - {u['path']} :: {u['name']}  (in class {cls})")
    return "\n".join(lines) or "  (none)"


def refactor_prompt(template: str, cp: dict, ig: dict, block_percentile: float) -> str:
    """Fill the configured refactor template. Placeholders (all substituted by plain
    replace, so JSON braces in the template are safe):
      {spec}     the upcoming change the refactor should make simpler
      {files}    the files ImpactGate flagged, by impact cost
      {drivers}  the specific methods/classes driving the cost (CC + class weight)
      {grade}    the failing change's percentile grade
      {block}    the block percentile it must come under"""
    pct = grade_percentile(ig)
    return (template
            .replace("{spec}", cp.get("spec", ""))
            .replace("{files}", _format_files(ig))
            .replace("{drivers}", _format_drivers(ig))
            .replace("{grade}", "n/a" if pct is None else f"{pct:g}")
            .replace("{block}", f"{block_percentile:g}"))


def _agent_envelope(agent) -> dict:
    return {
        "ok": agent.ok, "cost_usd": agent.cost_usd,
        "input_tokens": agent.input_tokens, "output_tokens": agent.output_tokens,
        "cache_read_tokens": agent.cache_read_tokens,
        "cache_creation_tokens": agent.cache_creation_tokens,
        "num_turns": agent.num_turns, "duration_ms": agent.duration_ms,
        "duration_api_ms": agent.duration_api_ms, "model": agent.model,
        "stop_reason": agent.stop_reason, "error": agent.error,
    }


def attempt_summary(kind: str, ig: dict, block_percentile: float, sha: str = "",
                    agent=None, tests: dict | None = None,
                    quality: dict | None = None, quality_turns=None) -> dict:
    """One entry in the capture record's `impact_gate.attempts` list. `kind` is
    'implement' or 'refactor'. Records the grade/verdict, the flagged files/drivers
    (so a refactor's guidance is reproducible from capture), the commit sha, and —
    for a refactor — the irreproducible agent envelope + optional correctness. Design B
    adds, for a refactor, the code-quality verdict (`quality`, see quality_gate.summary)
    and the envelopes of any code-review turns it took to get clean (`quality_turns`)."""
    entry = {
        "kind": kind,
        "grade": grade_percentile(ig),
        "impact": ig.get("impact"),
        "blocked": is_blocked(ig, block_percentile),
        "files": [f for f in (ig.get("files") or []) if (f.get("cost") or 0) > 0],
        "drivers": ig.get("top_units") or [],
        "sha": sha,
    }
    if agent is not None:
        entry["agent"] = _agent_envelope(agent)
    if tests is not None:
        entry["tests"] = tests
    if quality is not None:
        entry["quality"] = quality
    if quality_turns:
        entry["quality_turns"] = [_agent_envelope(a) for a in quality_turns]
    return entry
