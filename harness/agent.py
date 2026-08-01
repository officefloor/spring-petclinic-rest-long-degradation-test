"""Wrapper around headless Claude Code (`claude -p`), streaming its output.

Each call is an independent session, so no conversation context carries between
checkpoints. This is deliberate: SlopCodeBench's core condition is that "the
agent must reason about changes solely from the code's current structure". That
is exactly the condition under which a self-describing architecture (the
OfficeFloor YAML index) can pay off, so we reproduce it here.

We run with `--output-format stream-json --verbose` and read the event stream
line by line, printing Claude's text and tool calls to the console so a long run
shows live progress instead of looking hung. stdin is DEVNULL so the child can
never block waiting on the terminal (e.g. a trust prompt); a watchdog kills it
if it produces no completion within `timeout` seconds.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the child AND its descendants (they may hold the output pipe open)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


@dataclass
class AgentResult:
    ok: bool
    cost_usd: float = 0.0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    output_tokens: int = 0
    num_turns: int = 0
    duration_ms: int = 0        # wall: model + tools + approval waits
    duration_api_ms: int = 0    # API: model inference only (the clean metric)
    model: str = ""             # exact model id the run resolved to
    session_id: str = ""
    stop_reason: str = ""       # result subtype: success / error_max_turns / ...
    result_text: str = ""
    raw: dict = field(default_factory=dict)
    error: str = ""
    limit_reached: bool = False  # usage/session limit; caller waits for the quota reset then retries
    retryable: bool = False      # transient failure (network/overload/no-completion); short backoff then retry


# Specific to the quota message ("You've hit your session limit · resets 6am ..."),
# so it won't false-match agent/test output. Matched only against the terminal
# result / stderr, never against streamed tool output.
_LIMIT_PHRASES = ("session limit", "usage limit", "you've hit your", "hit your session",
                  "limit · resets", "limit resets")


def looks_like_limit(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _LIMIT_PHRASES)


# Transient failures that should be retried after a short wait (not a data outcome):
# API overload and network drops. Kept SPECIFIC — these are matched only against
# the terminal error message, never against streamed tool output (a Maven/test
# log is full of numbers and words like "503"/"timeout"/"network" that would
# otherwise trigger false positives on a successful run).
_RETRYABLE_PHRASES = (
    "overloaded", "service unavailable", "internal server error", "bad gateway",
    "gateway timeout", "temporarily unavailable", "rate_limit_error",
    "econnreset", "etimedout", "enotfound", "eai_again", "getaddrinfo",
    "connection reset by peer", "connection refused", "fetch failed",
    "socket hang up", "could not resolve host",
)


def looks_retryable(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in _RETRYABLE_PHRASES)


def _result_from_obj(data: dict) -> AgentResult:
    """Build an AgentResult from the stream's terminal `result` event."""
    usage = data.get("usage", {}) or {}
    return AgentResult(
        ok=not data.get("is_error", False),
        cost_usd=float(data.get("total_cost_usd", data.get("cost_usd", 0.0)) or 0.0),
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens", usage.get("cache_read_tokens", 0)) or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens", usage.get("cache_creation_tokens", 0)) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        num_turns=int(data.get("num_turns", 0) or 0),
        duration_ms=int(data.get("duration_ms", 0) or 0),
        duration_api_ms=int(data.get("duration_api_ms", 0) or 0),
        session_id=str(data.get("session_id", "") or ""),
        stop_reason=str(data.get("subtype", "") or ""),
        result_text=str(data.get("result", "") or ""),
        raw=data,
    )


_TOOL_KEYS = ("file_path", "path", "command", "pattern", "url", "query", "notebook_path")


def _fmt_tool(name: str, inp) -> str:
    if isinstance(inp, dict):
        for k in _TOOL_KEYS:
            if inp.get(k):
                v = str(inp[k]).replace("\n", " ")
                return f"{name}({v[:100] + '…' if len(v) > 100 else v})"
    return str(name)


def _print_event(ev: dict, prefix: str) -> None:
    """Render one stream event as a concise console line (Claude's decisions)."""
    t = ev.get("type")
    if t == "assistant":
        for c in ev.get("message", {}).get("content", []):
            if c.get("type") == "text":
                txt = c.get("text", "").strip()
                if txt:
                    print(f"{prefix} {txt.splitlines()[0][:160]}", flush=True)
            elif c.get("type") == "tool_use":
                print(f"{prefix} → {_fmt_tool(c.get('name', '?'), c.get('input'))}", flush=True)
    elif t == "user":
        # tool results — a short tail so long tool runs (e.g. mvnw) show they finished
        for c in ev.get("message", {}).get("content", []):
            if c.get("type") == "tool_result":
                content = c.get("content")
                if isinstance(content, list):
                    text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                else:
                    text = str(content or "")
                text = text.strip().replace("\n", " ")
                if text:
                    print(f"{prefix}   ← {text[:100]}", flush=True)
    elif t == "result":
        cost = ev.get("total_cost_usd", 0.0) or 0.0
        print(f"{prefix} done: {ev.get('num_turns', '?')} turns, ${cost:.4f}", flush=True)


def run_agent(prompt: str, cwd: str, model: str, timeout: int = 3600,
              allowed_tools: Optional[str] = None, stream: bool = True,
              label: str = "claude", capture_path: Optional[str] = None) -> AgentResult:
    """Run one fresh headless agent turn in `cwd`, streaming events to the
    console. No session is resumed. Returns the parsed terminal result, or an
    error result on timeout / missing completion.

    If `capture_path` is set, every raw stream event is written there verbatim
    (overwritten per call, so a retried checkpoint keeps only the successful
    attempt's stream). This is the agent's full behaviour trace — tool calls,
    files read, commands run — which is irreproducible and lost otherwise."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        "--dangerously-skip-permissions",
    ]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True)
    except FileNotFoundError:
        return AgentResult(ok=False, error="`claude` CLI not found on PATH")

    stderr_buf: list[str] = []
    drain = threading.Thread(target=lambda: stderr_buf.extend(proc.stderr), daemon=True)
    drain.start()

    timed_out = {"v": False}

    def _kill():
        timed_out["v"] = True
        _kill_group(proc)

    watchdog = threading.Timer(timeout, _kill)
    watchdog.start()

    prefix = f"    [{label}]"
    result_obj: Optional[dict] = None
    captured = {"model": "", "session_id": ""}
    cap_fh = None
    if capture_path:
        try:
            os.makedirs(os.path.dirname(capture_path) or ".", exist_ok=True)
            cap_fh = open(capture_path, "w")
        except OSError:
            cap_fh = None
    try:
        for raw in proc.stdout:
            if cap_fh:
                cap_fh.write(raw)
            line = raw.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = ev.get("type")
            if et == "system" and ev.get("subtype") == "init":
                captured["model"] = ev.get("model") or captured["model"]
                captured["session_id"] = ev.get("session_id") or captured["session_id"]
            elif et == "assistant":
                captured["model"] = (ev.get("message") or {}).get("model") or captured["model"]
            elif et == "result":
                result_obj = ev
                captured["session_id"] = ev.get("session_id") or captured["session_id"]
            if stream:
                _print_event(ev, prefix)
        proc.wait()
    except KeyboardInterrupt:
        _kill_group(proc)
        raise
    finally:
        watchdog.cancel()
        drain.join(timeout=2)
        if cap_fh:
            cap_fh.close()

    if timed_out["v"]:
        # No completion within the timeout — often an overloaded/unresponsive API.
        return AgentResult(ok=False, error=f"agent timed out after {timeout}s (no completion)",
                           retryable=True)
    if result_obj is None:
        # Process ended without a result: crash, or the network cut mid-stream.
        err = "".join(stderr_buf)[-1000:].strip()
        lim = looks_like_limit(err)
        return AgentResult(ok=False, error=f"no result from agent (exit {proc.returncode}): {err}",
                           limit_reached=lim, retryable=not lim)
    res = _result_from_obj(result_obj)
    res.model = res.model or captured["model"] or model
    res.session_id = res.session_id or captured["session_id"]
    res.limit_reached = looks_like_limit(res.result_text) or looks_like_limit(res.error)
    # Only an actual error result can be transient; a SUCCESSFUL completion never is
    # (its summary text may contain "503"/"timeout"/etc. from the agent's test runs).
    res.retryable = (not res.ok) and (not res.limit_reached) and (
        looks_retryable(res.result_text) or looks_retryable(res.error))
    return res


def probe(question: str, cwd: str, model: str, expected: Optional[list[str]] = None,
          timeout: int = 900, capture_path: Optional[str] = None) -> dict:
    """Cold-reader comprehension probe (read-only).

    Re-asked verbatim at each phase boundary. As the Spring hotspot method
    bloats this should get pricier and less complete; the OfficeFloor pipeline
    should stay cheap and complete because it enumerates its functions.
    Recall is a crude keyword hit-rate; grade properly offline for the paper.
    """
    res = run_agent(question, cwd=cwd, model=model, timeout=timeout,
                    allowed_tools="Read,Grep,Glob,Bash", label="probe",
                    capture_path=capture_path)
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
