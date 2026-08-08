"""Landlock filesystem confinement for the agent turn (Linux, unprivileged).

The blind-agent design removes the withheld tests from the SANDBOX and from git
history, but the agent process still had read access to the whole filesystem — so
a `find /` reached the harness `acceptance/` suite, `checkpoints.yaml`, and a prior
run's tests sitting in Trash (observed: cp01 grepped generated sources out of
`~/.local/share/Trash`). This closes that by restricting the agent process — and
every child it spawns — to an allowlist via Landlock (kernel LSM, no root, no
user-namespace, no bwrap). Everything outside the allowlist returns EACCES, so
`find`/`cat`/`ls` physically cannot reach the withheld material. The restriction is
one-way (`landlock_restrict_self`) and inherited across exec, so the agent cannot
lift it.

Applied as a `preexec_fn` on the agent's Popen: it runs in the forked child just
before exec, builds the ruleset there (so it never depends on an inherited fd), and
`exec`s the confined `claude`. `verify_denied()` runs the SAME confinement over a
throwaway `sh` and confirms the sentinels are unreadable — the fail-closed check the
caller uses to refuse to run if isolation ever regresses."""
import ctypes
import os
import subprocess

# x86_64 syscall numbers (this harness runs on linux/amd64).
_NR_create_ruleset, _NR_add_rule, _NR_restrict_self = 444, 445, 446
_CREATE_RULESET_VERSION = 1
_RULE_PATH_BENEATH = 1
_PR_SET_NO_NEW_PRIVS = 38

_FS = {  # LANDLOCK_ACCESS_FS_* bit positions
    "EXECUTE": 1 << 0, "WRITE_FILE": 1 << 1, "READ_FILE": 1 << 2, "READ_DIR": 1 << 3,
    "REMOVE_DIR": 1 << 4, "REMOVE_FILE": 1 << 5, "MAKE_CHAR": 1 << 6, "MAKE_DIR": 1 << 7,
    "MAKE_REG": 1 << 8, "MAKE_SOCK": 1 << 9, "MAKE_FIFO": 1 << 10, "MAKE_BLOCK": 1 << 11,
    "MAKE_SYM": 1 << 12, "REFER": 1 << 13, "TRUNCATE": 1 << 14, "IOCTL_DEV": 1 << 15,
}
_RO = _FS["EXECUTE"] | _FS["READ_FILE"] | _FS["READ_DIR"]

_libc = ctypes.CDLL(None, use_errno=True)
_libc.syscall.restype = ctypes.c_long


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def abi_version() -> int:
    """Landlock ABI version (>=1 usable), or <=0 if unsupported/disabled."""
    try:
        return _libc.syscall(ctypes.c_long(_NR_create_ruleset), ctypes.c_void_p(0),
                             ctypes.c_size_t(0), ctypes.c_uint(_CREATE_RULESET_VERSION))
    except Exception:
        return -1


def _handled_mask(abi: int) -> int:
    m = (1 << 13) - 1                       # ABI 1: bits 0..12
    if abi >= 2: m |= _FS["REFER"]
    if abi >= 3: m |= _FS["TRUNCATE"]
    if abi >= 5: m |= _FS["IOCTL_DEV"]
    return m


def default_allowlist(sandbox: str, cfg_dir: str | None, home: str | None = None):
    """(ro, rw) path lists exposing ONLY the sandbox + the toolchain. Everything
    else (harness repo, checkpoints.yaml, pe-work, compare, Trash, the rest of
    $HOME) is absent from both lists and therefore denied. Missing paths are
    skipped at apply time, so the lists are safe supersets."""
    home = home or os.path.expanduser("~")
    ro = ["/usr", "/etc", "/opt", "/bin", "/lib", "/lib64", "/sbin", "/proc",
          "/run/systemd/resolve",             # stub-resolv.conf target — DNS for the API/Maven
          os.path.join(home, ".local/share/claude"),
          os.path.join(home, ".local/bin"),
          os.path.join(home, ".config"),
          os.path.join(home, ".sdkman")]
    rw = ["/tmp", "/dev",
          os.path.join(home, ".m2"),
          os.path.join(home, ".cache"),
          sandbox]
    if cfg_dir:
        rw.append(cfg_dir)
    return ro, rw


def _apply(ro_paths, rw_paths) -> None:
    """Build and enforce the ruleset IN THE CURRENT process (called in the Popen
    child via preexec_fn). Raises OSError on any hard failure so the launch
    fails closed. Opens every path fresh here, so nothing depends on an fd
    surviving subprocess's fd-closing."""
    abi = _libc.syscall(ctypes.c_long(_NR_create_ruleset), ctypes.c_void_p(0),
                        ctypes.c_size_t(0), ctypes.c_uint(_CREATE_RULESET_VERSION))
    if abi < 1:
        raise OSError(ctypes.get_errno(), "landlock unavailable")
    handled = _handled_mask(abi)

    attr = _RulesetAttr(handled_access_fs=handled)
    rs = _libc.syscall(ctypes.c_long(_NR_create_ruleset), ctypes.byref(attr),
                       ctypes.c_size_t(ctypes.sizeof(attr)), ctypes.c_uint(0))
    if rs < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")

    def add(path, access):
        try:
            pfd = os.open(path, os.O_PATH)
        except OSError:
            return                              # absent on this host — skip
        try:
            pa = _PathBeneathAttr(allowed_access=access & handled, parent_fd=pfd)
            r = _libc.syscall(ctypes.c_long(_NR_add_rule), ctypes.c_int(rs),
                              ctypes.c_int(_RULE_PATH_BENEATH), ctypes.byref(pa),
                              ctypes.c_uint(0))
            if r < 0:
                raise OSError(ctypes.get_errno(), "landlock_add_rule " + path)
        finally:
            os.close(pfd)

    for p in ro_paths:
        add(p, _RO)
    for p in rw_paths:
        add(p, handled)                         # full control within the subtree

    if _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS)")
    if _libc.syscall(ctypes.c_long(_NR_restrict_self), ctypes.c_int(rs), ctypes.c_uint(0)) < 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    os.close(rs)


def make_preexec(ro_paths, rw_paths):
    """Return a preexec_fn (runs in the child before exec) that confines it."""
    ro, rw = list(ro_paths), list(rw_paths)
    return lambda: _apply(ro, rw)


def verify_denied(ro_paths, rw_paths, sentinels, timeout: int = 30):
    """Fail-closed check: under the SAME confinement, try to read each sentinel
    (a withheld file or dir). Returns the list that stayed reachable — empty means
    confinement holds. Raises if the confinement itself can't be applied (caller
    must treat that as 'do not run')."""
    # Test ACTUAL read access, per type: a directory with `ls` (readdir — governed by
    # Landlock READ_DIR), a file with `cat` (open+read — governed by READ_FILE). NOT
    # `ls <file>`, which is only a stat() and Landlock does not restrict stat, so it
    # would false-positive on a denied file. `[ -d ]` itself is a stat and always works.
    script = ('leak=""; for p in "$@"; do '
              'if [ -d "$p" ]; then ok=$(ls "$p" >/dev/null 2>&1 && echo y); '
              'else ok=$(cat "$p" >/dev/null 2>&1 && echo y); fi; '
              '[ -n "$ok" ] && leak="$leak $p"; '
              'done; [ -z "$leak" ] || { printf "%s" "LEAK:$leak"; exit 3; }')
    r = subprocess.run(["/bin/sh", "-c", script, "sh", *sentinels],
                       preexec_fn=make_preexec(ro_paths, rw_paths),
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode == 3 and r.stdout.startswith("LEAK:"):
        return r.stdout[len("LEAK:"):].split()
    return []
