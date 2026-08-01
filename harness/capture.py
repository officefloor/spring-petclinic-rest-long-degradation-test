"""Raw-capture layer.

The runner's job is split in two:

  * CAPTURE (here) — the per-checkpoint information that is LOST if it is not
    recorded at the instant the agent runs: the agent envelope (cost/tokens/
    model/turns), the full event stream, the RAW per-test results, the compiler
    output, and the pre-normalisation agent diff (the true agent delta, before
    CLAUDE.md is pinned back and the acceptance tests are reset). Plus a run
    provenance manifest (model, harness SHA, tool versions).

  * DERIVE (harness/metrics.py + analyze --recompute) — everything else. Erosion,
    verbosity, blast radius, coupling, WMC, etc. are pure functions of the
    committed source + git history, so they are NOT stored here: they are
    re-derived from the checkpoint commits. That is what lets a NEW metric be
    computed over OLD runs without re-invoking the (expensive) agent.

Capture artifacts are staged OUTSIDE the worktree during a chain and copied into
`evolve-results/capture/` only at the final results commit, so they never leak
into the per-checkpoint code commits (which would pollute the very diffs the
derive step reads).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess


def _cmd(args: list[str], timeout: int = 30) -> str:
    """Run a command and return combined stdout+stderr, first line, stripped.
    (java/mvn print their version to stderr, hence the merge.)"""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    out = (p.stdout + p.stderr).strip()
    return out.splitlines()[0] if out else ""


def tool_versions(cfg: dict) -> dict:
    """Versions of every external tool the derive step depends on, so results
    computed under different tool versions can be told apart."""
    import sys
    tools = cfg.get("tools", {})
    try:
        import lizard as _lz
        lizard_v = str(getattr(_lz, "version", "") or getattr(_lz, "__version__", ""))
    except Exception:
        lizard_v = ""
    return {
        "python": sys.version.split()[0],
        "lizard": lizard_v,
        "git": _cmd(["git", "--version"]),
        "java": _cmd(["java", "-version"]),
        "mvn": _cmd(["mvn", "-v"]),
        "jscpd": _cmd([tools.get("jscpd", "jscpd"), "--version"]),
        "astgrep": _cmd([tools.get("astgrep", "sg"), "--version"]),
        "claude": _cmd(["claude", "--version"]),
    }


def provenance(cfg: dict, run_id: str, model: str, harness_dir: str,
               extra: dict | None = None) -> dict:
    """Per-chain manifest: enough to know exactly what produced these commits and
    to reproduce the derive step deterministically."""
    prov = {
        "run_id": run_id,
        "model": model,
        "harness_git_sha": _cmd(["git", "-C", harness_dir, "rev-parse", "HEAD"]),
        "harness_git_dirty": bool(_cmd(["git", "-C", harness_dir, "status", "--porcelain"])),
        "tool_versions": tool_versions(cfg),
    }
    if extra:
        prov.update(extra)
    return prov


def checkpoint_record(k: int, cp_id: str, phase: str, shas: dict, agent_result,
                      outcome, probe: dict | None, pinned_touched: list[str],
                      acceptance_touched: list[str], stream_file: str | None,
                      diff_file: str | None) -> dict:
    """Assemble the raw, irreproducible record for one checkpoint. `outcome` is a
    correctness.TestOutcome (its RAW results map + detail are what matter here —
    every set-based correctness metric is re-derivable from them)."""
    ar = agent_result
    return {
        "checkpoint": k,
        "checkpoint_id": cp_id,
        "phase": phase,
        "commit_sha": shas.get("commit"),
        "preagent_sha": shas.get("preagent"),
        "prev_sha": shas.get("prev"),
        "base_sha": shas.get("base"),
        "agent": {
            "ok": ar.ok,
            "is_error": not ar.ok,
            "cost_usd": ar.cost_usd,
            "input_tokens": ar.input_tokens,
            "output_tokens": ar.output_tokens,
            "cache_read_tokens": ar.cache_read_tokens,
            "cache_creation_tokens": ar.cache_creation_tokens,
            "num_turns": ar.num_turns,
            "duration_ms": ar.duration_ms,
            "duration_api_ms": ar.duration_api_ms,
            "model": ar.model,
            "session_id": ar.session_id,
            "stop_reason": ar.stop_reason,
            "result_text": ar.result_text,
            "error": ar.error,
        },
        "agent_stream_file": stream_file,
        "agent_diff_file": diff_file,
        "tests": {
            "build_ok": outcome.build_ok,
            "build_output": outcome.build_output,
            "total_selected": outcome.total_selected,
            "results": outcome.results,     # {test_id: passed} — the atom
            "detail": outcome.detail,       # per-test time + failure text
            "error": outcome.error,
        },
        "probe": probe,
        "pinned_touched": pinned_touched,
        "acceptance_touched": acceptance_touched,
    }


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)


def assemble_into(cap_dir: str, results_dir: str) -> None:
    """Copy staged capture artifacts into evolve-results/capture/ for the final
    results commit. No-op if nothing was staged."""
    if not cap_dir or not os.path.isdir(cap_dir):
        return
    dest = os.path.join(results_dir, "capture")
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(cap_dir)):
        src = os.path.join(cap_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
