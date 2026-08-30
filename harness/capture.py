"""Raw-capture layer.

The runner's job is split in two:

  * CAPTURE (here) — the per-checkpoint information that is LOST if it is not
    recorded at the instant the agent runs: the agent envelope (cost/tokens/
    model/turns), the full event stream, the RAW per-test results, the compiler
    output, and the pre-normalisation agent diff (the true agent delta, before
    CLAUDE.md is pinned back and the acceptance tests are reset). Plus a run
    provenance manifest (model, harness SHA, tool versions).

  * DERIVE (harness/metrics.py + analyze) — everything else. Erosion,
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

import hashlib
import json
import os
import shutil
import subprocess
import sys

from . import agent

# External files that govern the agent's tools/permissions (user + machine level;
# project-level `.claude`/`.mcp.json` already travel in the checkpoint commits).
_SETTINGS_PATHS = (
    "~/.claude/settings.json",
    "~/.claude/settings.local.json",
    "/etc/claude-code/managed-settings.json",
)
_MCP_PATHS = ("~/.claude.json", "~/.mcp.json")


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


def _sha256(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _mcp_server_names(path: str) -> list[str] | None:
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    servers = data.get("mcpServers")
    return sorted(servers.keys()) if isinstance(servers, dict) else None


def agent_env(cfg: dict) -> dict:
    """The effective agent environment that governs tool/permission availability —
    the experiment's *control*, which is otherwise unrecorded. Captures HASHES and
    NAMES only (never file contents or env values), so it proves the control was
    held constant across arms/checkpoints and is safe to commit (no secrets)."""
    model = cfg.get("model", "")
    settings = []
    for p in _SETTINGS_PATHS:
        fp = os.path.expanduser(p)
        ex = os.path.isfile(fp)
        settings.append({"path": p, "exists": ex, "sha256": _sha256(fp) if ex else None})
    mcp = {}
    for p in _MCP_PATHS:
        fp = os.path.expanduser(p)
        if os.path.isfile(fp):
            names = _mcp_server_names(fp)
            if names is not None:
                mcp[p] = names
    return {
        "invocation": {
            "cli": "claude",
            "model": model,
            "main_flags": agent.invocation_flags(model),
            "probe_flags": agent.invocation_flags(model, agent.PROBE_TOOLS),
        },
        "settings_files": settings,          # path + exists + sha256 (no contents)
        "mcp_servers": mcp,                  # server NAMES only (no configs/tokens)
        "env_var_names": sorted(k for k in os.environ
                                if k.startswith(("CLAUDE", "ANTHROPIC"))),  # names, no values
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
        "agent_env": agent_env(cfg),
    }
    if extra:
        prov.update(extra)
    return prov


def checkpoint_record(k: int, cp_id: str, phase: str, shas: dict, agent_result,
                      outcome, probe: dict | None, pinned_touched: list[str],
                      acceptance_touched: list[str], stream_file: str | None,
                      diff_file: str | None, build_log_file: str | None = None,
                      attempts: list[dict] | None = None, spec: str | None = None,
                      prompt: str | None = None, ckpt_type: str = "additive",
                      mutates: list | None = None, impact_gate: dict | None = None) -> dict:
    """Assemble the raw, irreproducible record for one checkpoint. `outcome` is a
    correctness.TestOutcome (its RAW results map + detail are what matter here —
    every set-based correctness metric is re-derivable from them).

    `request` makes the checkpoint self-describing (the spec + rendered prompt, so
    it does not depend on the harness repo being committed). `agent.attempts`
    records EVERY attempt including failed/rate-limited ones (final entry is the
    successful turn), so true wall-clock and total cost — including retries and
    quota waits — are recoverable, not just the winning attempt."""
    ar = agent_result
    return {
        "checkpoint": k,
        "checkpoint_id": cp_id,
        "phase": phase,
        "type": ckpt_type,          # additive | mutative
        "mutates": mutates or [],   # prior checkpoint numbers a mutation changes
        "request": {"spec": spec, "prompt": prompt},
        "commit_sha": shas.get("commit"),   # the AGENT commit ("" for a no-op)
        "reset_sha": shas.get("reset"),      # the RESET commit (harness normalisation)
        "preagent_sha": shas.get("preagent"),
        "prev_sha": shas.get("prev"),
        "base_sha": shas.get("base"),
        "agent": {
            "ok": ar.ok,
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
            "attempts": attempts or [],   # all tries incl. failed/limited; last = success
        },
        "agent_stream_file": stream_file,
        "agent_diff_file": diff_file,
        "build_log_file": build_log_file,
        "tests": {
            "build_ok": outcome.build_ok,
            "build_output": outcome.build_output,
            "total_selected": outcome.total_selected,
            "results": outcome.results,     # {test_id: passed} — the atom
            "detail": outcome.detail,       # per-test time + failure text
            "error": outcome.error,
            # A gate that ABORTED (Surefire fork crash) after `gate_attempts` tries
            # carries no verdict; analyze must treat it as missing data, never as a
            # suite-wide regression. Persisted so the hole survives into re-analysis.
            "gate_invalid": outcome.gate_invalid,
            "gate_attempts": outcome.gate_attempts,
        },
        "probe": probe,
        "pinned_touched": pinned_touched,
        "acceptance_touched": acceptance_touched,
        # impact_gated strategy only: the ImpactGate verdict per implement/refactor
        # attempt for this checkpoint, plus the refactor agent turns (irreproducible
        # cost/tokens). None for ungated strategies. See harness/impact_gate.py.
        "impact_gate": impact_gate,
    }


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)


def snapshot_config(config_path: str | None, checkpoints_path: str | None,
                    astgrep_rules_dir: str | None, dest_dir: str) -> None:
    """Copy the analysis-shaping config INTO the results commit, so a run is
    self-contained: the metrics a run's globs / thresholds / entry-handler regex /
    ast-grep rules define are pinned to the run, not read from whatever config
    happens to be live when analyze runs later. Writes `<dest_dir>/config/`."""
    dest = os.path.join(dest_dir, "config")
    os.makedirs(dest, exist_ok=True)
    for src, name in ((config_path, "config.yaml"), (checkpoints_path, "checkpoints.yaml")):
        if src and os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
    if astgrep_rules_dir and os.path.isdir(astgrep_rules_dir):
        rules_dest = os.path.join(dest, "astgrep-rules")
        shutil.rmtree(rules_dest, ignore_errors=True)
        shutil.copytree(astgrep_rules_dir, rules_dest)


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
