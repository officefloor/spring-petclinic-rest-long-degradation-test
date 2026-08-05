"""PetClinic-Evolve: a long-horizon architecture-degradation harness.

Holds the coding agent fixed and makes *architecture* the independent variable
(Spring @RestController vs OfficeFloor YAML-composed functions), borrowing the
measurement methods of SlopCodeBench (arXiv:2603.24755) and SWE-CI
(arXiv:2603.03823).
"""

import os
import re
import subprocess

_UNEXPANDED = re.compile(r"\$\{?\w+\}?")


def git_out(cwd: str, args: list[str], check: bool = False, timeout: int = 60) -> str:
    """Run ``git -C <cwd> <args>`` and return stdout (unstripped). Swallows errors
    (returns "") unless ``check`` is set, in which case a non-zero exit raises. Used
    by the derive/analyze side, which needs graceful degradation on a missing repo;
    run_experiment keeps its own stricter ``git`` (raises by default, strips)."""
    try:
        proc = subprocess.run(["git", "-C", cwd, *args],
                              capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        if check:
            raise
        return ""
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def expand_path(value: str | None, key: str = "path") -> str | None:
    """Expand ``~`` and ``${VARS}`` in a config path.

    Fails LOUDLY if any variable is undefined, rather than leaving a literal
    ``${HOME}`` (which os.path.expandvars does) and silently misconfiguring the
    run. Undefined vars are never treated as blank.
    """
    if value is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(value))
    if _UNEXPANDED.search(expanded):
        raise SystemExit(
            f"config {key!r}: undefined environment variable in {value!r} "
            f"(expanded to {expanded!r}). Set the variable, or use an absolute path.")
    return expanded
