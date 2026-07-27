"""Wrapper around headless Claude Code (`claude -p`).

Each call is an independent session, so no conversation context carries between
checkpoints. This is deliberate: SlopCodeBench's core condition is that "the
agent must reason about changes solely from the code's current structure". That
is exactly the condition under which a self-describing architecture (the
OfficeFloor YAML index) can pay off, so we reproduce it here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentResult:
    ok: bool
    cost_usd: float = 0.0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    num_turns: int = 0
    duration_ms: int = 0        # wall: model + tools + approval waits
    duration_api_ms: int = 0    # API: model inference only (the clean metric)
    result_text: str = ""
    raw: dict = field(default_factory=dict)
    error: str = ""


def _parse(stdout: str) -> AgentResult:
    """Parse the single JSON object emitted by `--output-format json`."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # Some versions stream several JSON lines; take the last complete one.
        last = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
        if last is None:
            return AgentResult(ok=False, error="could not parse agent JSON", raw={"stdout": stdout[-2000:]})
        data = last

    usage = data.get("usage", {}) or {}
    return AgentResult(
        ok=not data.get("is_error", False),
        cost_usd=float(data.get("total_cost_usd", data.get("cost_usd", 0.0)) or 0.0),
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens", usage.get("cache_read_tokens", 0)) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        num_turns=int(data.get("num_turns", 0) or 0),
        duration_ms=int(data.get("duration_ms", 0) or 0),
        duration_api_ms=int(data.get("duration_api_ms", 0) or 0),
        result_text=str(data.get("result", "") or ""),
        raw=data,
    )


def run_agent(prompt: str, cwd: str, model: str, timeout: int = 3600,
              allowed_tools: Optional[str] = None) -> AgentResult:
    """Run one fresh headless agent turn in `cwd`. No session is resumed."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--dangerously-skip-permissions",
    ]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return AgentResult(ok=False, error=f"agent timed out after {timeout}s")
    except FileNotFoundError:
        return AgentResult(ok=False, error="`claude` CLI not found on PATH")

    if proc.returncode != 0 and not proc.stdout.strip():
        return AgentResult(ok=False, error=f"agent exit {proc.returncode}: {proc.stderr[-1000:]}")
    res = _parse(proc.stdout)
    if not res.raw and proc.stderr:
        res.error = proc.stderr[-1000:]
    return res


def probe(question: str, cwd: str, model: str, expected: Optional[list[str]] = None,
          timeout: int = 900) -> dict:
    """Cold-reader comprehension probe (read-only).

    Re-asked verbatim at each phase boundary. As the Spring hotspot method
    bloats this should get pricier and less complete; the OfficeFloor pipeline
    should stay cheap and complete because it enumerates its functions.
    Recall is a crude keyword hit-rate; grade properly offline for the paper.
    """
    res = run_agent(question, cwd=cwd, model=model, timeout=timeout,
                    allowed_tools="Read,Grep,Glob,Bash")
    recall = None
    if expected:
        text = res.result_text.lower()
        hits = sum(1 for e in expected if e.lower() in text)
        recall = hits / len(expected) if expected else None
    return {
        "probe_cost_usd": res.cost_usd,
        "probe_input_tokens": res.input_tokens,
        "probe_cache_read_tokens": res.cache_read_tokens,
        "probe_recall": recall,
        "probe_text": res.result_text,
    }
