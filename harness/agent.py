"""Wrapper around headless Claude Code (`claude -p`), streaming its output.

Each call is an independent session, so no conversation context carries between
checkpoints. This is deliberate: SlopCodeBench's core condition is that "the
agent must reason about changes solely from the code's current structure". That
is exactly the condition under which a self-describing architecture (the
OfficeFloor YAML index) can pay off, so we reproduce it here.

To make that guarantee airtight we also isolate Claude's *config* per call: each
invocation runs under a throwaway ``CLAUDE_CONFIG_DIR`` seeded with only the login
credentials (see ``_seed_clean_config_dir``). Without this, Claude Code's
auto-memory writes project "learnings" into ``~/.claude/projects/<repo>/memory/``
keyed by the git common dir -- which for all of an arm's worktrees is the ONE base
repo. That memory would then be recalled by later checkpoints (breaking the
context-free condition) and shared across chains and, asymmetrically, between the
two arms (contaminating the safety signal we measure). A fresh login-only config
dir per call means every checkpoint sees a pristine, stateless Claude; the real
``~/.claude`` is never read or written.

We run with `--output-format stream-json --verbose` and read the event stream
line by line, printing Claude's text and tool calls to the console so a long run
shows live progress instead of looking hung. stdin is DEVNULL so the child can
never block waiting on the terminal (e.g. a trust prompt); a watchdog kills it
if it produces no completion within `timeout` seconds.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional

from . import landlock


# Read-only toolset the cold-reader probe is restricted to.
PROBE_TOOLS = "Read,Grep,Glob,Bash"

# The one file inside a Claude config dir that constitutes "login". Seeding a
# fresh config dir with only this gives a pristine, stateless, still-authenticated
# Claude -- no memory, no history, no accumulated project state.
_LOGIN_FILE = ".credentials.json"


def _source_config_dir() -> str:
    """The real config dir to copy login from -- honouring an already-set
    CLAUDE_CONFIG_DIR, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def _seed_clean_config_dir() -> Optional[str]:
    """Create a throwaway config dir seeded with only the login credentials, and
    return its path (caller sets CLAUDE_CONFIG_DIR to it and removes it after).

    Returns None if the login file can't be found, in which case the caller runs
    under the inherited config (a loud warning is printed) rather than failing the
    whole run over an environment quirk."""
    src = os.path.join(_source_config_dir(), _LOGIN_FILE)
    if not os.path.isfile(src):
        print(f"    [isolation] WARNING: no {_LOGIN_FILE} at {src}; "
              f"running under inherited ~/.claude (memory NOT isolated)", flush=True)
        return None
    cfg = tempfile.mkdtemp(prefix="pe-claude-cfg-")
    dst = os.path.join(cfg, _LOGIN_FILE)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o600)
    return cfg


def invocation_flags(model: str, allowed_tools: Optional[str] = None) -> list[str]:
    """The `claude` flags (excluding the prompt) for one headless turn. Single
    source of truth, so the run and the captured agent-env profile can't drift."""
    flags = ["--output-format", "stream-json", "--verbose", "--model", model,
             "--dangerously-skip-permissions"]
    if allowed_tools:
        flags += ["--allowedTools", allowed_tools]
    return flags


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
    error: str = ""
    limit_reached: bool = False  # usage/session limit OR auth expiry; caller waits (quota reset / re-login) then retries
    retryable: bool = False      # transient failure (network/overload/no-completion); short backoff then retry


# Specific to the quota message ("You've hit your session limit · resets 6am ..."),
# so it won't false-match agent/test output. Matched only against the terminal
# result / stderr, never against streamed tool output.
_LIMIT_PHRASES = ("session limit", "usage limit", "you've hit your", "hit your session",
                  "limit · resets", "limit resets")


def _matches(text: str, phrases) -> bool:
    t = (text or "").lower()
    return any(p in t for p in phrases)


def looks_like_limit(text: str) -> bool:
    return _matches(text, _LIMIT_PHRASES)


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
    return _matches(text, _RETRYABLE_PHRASES)


# Auth/session expiry that needs a (possibly manual) re-login before the run can
# continue. Treated like a quota LIMIT (wait and poll the SAME checkpoint until it
# works again) rather than a transient failure, so an OAuth expiry mid-run pauses
# and resumes on the next successful `/login` instead of silently burning the chain
# as a no-op turn. Distinctive phrases, so they can't match a healthy build's output.
# Kept DISTINCTIVE to the CLI's own auth plumbing -- deliberately NOT generic tokens
# like "401"/"unauthorized", which a security-feature checkpoint's own test output
# could emit and which would then trigger an endless auth-wait on an unrelated failure.
_AUTH_PHRASES = (
    "oauth session expired", "session expired and could not be refreshed",
    "could not be refreshed", "failed to authenticate", "failed to refresh",
    "authentication_error", "invalid api key", "invalid x-api-key",
    "please run /login", "run `claude login`", "credentials could not be refreshed",
)


def looks_like_auth(text: str) -> bool:
    return _matches(text, _AUTH_PHRASES)


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
    )


_TOOL_KEYS = ("file_path", "path", "command", "pattern", "url", "query", "notebook_path")


def _fmt_tool(name: str, inp: object) -> str:
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
              label: str = "claude", capture_path: Optional[str] = None,
              confine: Optional[dict] = None) -> AgentResult:
    """Run one fresh headless agent turn in `cwd`, streaming events to the
    console. No session is resumed. Returns the parsed terminal result, or an
    error result on timeout / missing completion.

    If `capture_path` is set, every raw stream event is written there verbatim
    (overwritten per call, so a retried checkpoint keeps only the successful
    attempt's stream). This is the agent's full behaviour trace — tool calls,
    files read, commands run — which is irreproducible and lost otherwise.

    If `confine` is set (dict from `isolation.agent_confinement`), the agent — and
    every child it spawns — is Landlock-restricted to the sandbox + toolchain, so it
    cannot read the withheld tests/specs anywhere on the filesystem. Fails CLOSED:
    if Landlock is unavailable or the sentinel self-check finds withheld material
    still readable, the turn is refused (no agent runs) rather than run un-blinded."""
    cmd = ["claude", "-p", prompt, *invocation_flags(model, allowed_tools)]

    # Isolate Claude's config/memory to a fresh login-only dir for this one call,
    # so nothing (memory, history, session state) leaks across checkpoints, chains
    # or arms. Removed in `finally`; the real ~/.claude is untouched.
    cfg_dir = _seed_clean_config_dir()
    child_env = os.environ.copy()
    if cfg_dir:
        child_env["CLAUDE_CONFIG_DIR"] = cfg_dir

    # Filesystem confinement (see landlock.py). Built here so the sandbox (=cwd) and
    # the throwaway cfg_dir are in the allowlist; refused if it can't be enforced.
    preexec = None
    if confine and confine.get("enabled", True):
        if landlock.abi_version() < 1:
            if cfg_dir:
                shutil.rmtree(cfg_dir, ignore_errors=True)
            return AgentResult(ok=False, error="agent_confinement enabled but Landlock "
                               "unavailable on this host; refusing to run agent unconfined")
        ro, rw = landlock.default_allowlist(cwd, cfg_dir)
        ro += list(confine.get("ro", []))
        rw += list(confine.get("rw", []))
        sentinels = list(confine.get("sentinels", []))
        if sentinels:
            try:
                leaked = landlock.verify_denied(ro, rw, sentinels)
            except Exception as e:
                if cfg_dir:
                    shutil.rmtree(cfg_dir, ignore_errors=True)
                return AgentResult(ok=False, error=f"confinement self-check could not run "
                                   f"({e}); refusing to run agent unconfined")
            if leaked:
                if cfg_dir:
                    shutil.rmtree(cfg_dir, ignore_errors=True)
                return AgentResult(ok=False, error="confinement LEAK — withheld material "
                                   f"still readable, refusing to run: {leaked}")
        preexec = landlock.make_preexec(ro, rw)

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True,
            env=child_env, preexec_fn=preexec)
    except FileNotFoundError:
        if cfg_dir:
            shutil.rmtree(cfg_dir, ignore_errors=True)
        return AgentResult(ok=False, error="`claude` CLI not found on PATH")
    except Exception as e:
        if cfg_dir:
            shutil.rmtree(cfg_dir, ignore_errors=True)
        return AgentResult(ok=False, error=f"failed to launch confined agent: {e}")

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
                result_obj = ev  # session_id extracted by _result_from_obj; model from `captured`
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
        if cfg_dir:
            shutil.rmtree(cfg_dir, ignore_errors=True)

    if timed_out["v"]:
        # No completion within the timeout — often an overloaded/unresponsive API.
        return AgentResult(ok=False, error=f"agent timed out after {timeout}s (no completion)",
                           retryable=True)
    err_tail = "".join(stderr_buf)[-2000:].strip()
    if result_obj is None:
        # Process ended without a result: crash, network cut mid-stream, or an auth
        # expiry that killed the process before any result event.
        lim = looks_like_limit(err_tail) or looks_like_auth(err_tail)
        return AgentResult(ok=False, error=f"no result from agent (exit {proc.returncode}): {err_tail}",
                           limit_reached=lim, retryable=not lim)
    res = _result_from_obj(result_obj)
    res.model = res.model or captured["model"] or model
    res.session_id = res.session_id or captured["session_id"]
    # An auth/session expiry can arrive as an is_error result whose message is only on
    # stderr (result_text empty), so classification must inspect the stderr tail too --
    # but ONLY for a failed turn, so a healthy build's stderr can't false-match. Auth is
    # mapped to limit_reached: the caller waits and polls the SAME checkpoint (allowing a
    # manual /login) instead of committing an empty no-op turn and marching on.
    fail_txt = "" if res.ok else (res.result_text + "\n" + err_tail)
    res.limit_reached = looks_like_limit(fail_txt) or looks_like_auth(fail_txt)
    if (not res.ok) and (not res.error) and looks_like_auth(fail_txt):
        res.error = "authentication failed / session expired (needs re-login); waiting to retry"
    # Only an actual error result can be transient; a SUCCESSFUL completion never is
    # (its summary text may contain "503"/"timeout"/etc. from the agent's test runs).
    res.retryable = (not res.ok) and (not res.limit_reached) and looks_retryable(res.result_text)
    return res


def probe(question: str, cwd: str, model: str, expected: Optional[list[str]] = None,
          timeout: int = 900, capture_path: Optional[str] = None,
          confine: Optional[dict] = None) -> dict:
    """Cold-reader comprehension probe (read-only).

    Re-asked verbatim at each phase boundary. As the Spring hotspot method
    bloats this should get pricier and less complete; the OfficeFloor pipeline
    should stay cheap and complete because it enumerates its functions.
    Recall is a crude keyword hit-rate; grade properly offline for the paper.
    """
    res = run_agent(question, cwd=cwd, model=model, timeout=timeout,
                    allowed_tools=PROBE_TOOLS, label="probe",
                    capture_path=capture_path, confine=confine)
    recall = None
    if expected:
        text = res.result_text.lower()
        hits = sum(1 for e in expected if e.lower() in text)
        recall = hits / len(expected)
    return {
        "probe_cost_usd": res.cost_usd,
        "probe_input_tokens": res.input_tokens,
        "probe_cache_read_tokens": res.cache_read_tokens,
        "probe_recall": recall,
        "probe_text": res.result_text,
    }
