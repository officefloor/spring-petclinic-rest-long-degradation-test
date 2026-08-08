#!/usr/bin/env python3
"""Standalone Landlock confinement self-test for PetClinic-Evolve.

Applies a Landlock ruleset that allows ONLY the agent toolchain + a scratch dir,
then checks that:
  (a) the toolchain paths stay readable / the scratch dir stays writable, and
  (b) the WITHHELD experiment material — the harness acceptance suite, its
      checkpoints.yaml, ~/pe-work, and the Trash — becomes UNREADABLE,
      including from a child process (cat / find), proving inheritance.

If this prints "OVERALL: PASS", the same confinement wired into agent.py will
blind the agent to everything outside ~/sandbox. No root, no bwrap, no system
change. Run in your normal shell:

    python3 harness/landlock_selftest.py

Exit codes: 0 = PASS, 1 = FAIL (something leaked), 2 = Landlock unavailable.
"""
import ctypes, glob, os, re, subprocess, sys

# ---- Landlock ABI plumbing (x86_64 syscall numbers) ----
NR_create_ruleset, NR_add_rule, NR_restrict_self = 444, 445, 446
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

FS = {  # LANDLOCK_ACCESS_FS_* bit positions
    "EXECUTE": 1 << 0, "WRITE_FILE": 1 << 1, "READ_FILE": 1 << 2, "READ_DIR": 1 << 3,
    "REMOVE_DIR": 1 << 4, "REMOVE_FILE": 1 << 5, "MAKE_CHAR": 1 << 6, "MAKE_DIR": 1 << 7,
    "MAKE_REG": 1 << 8, "MAKE_SOCK": 1 << 9, "MAKE_FIFO": 1 << 10, "MAKE_BLOCK": 1 << 11,
    "MAKE_SYM": 1 << 12, "REFER": 1 << 13, "TRUNCATE": 1 << 14, "IOCTL_DEV": 1 << 15,
}

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def abi_version() -> int:
    return libc.syscall(ctypes.c_long(NR_create_ruleset), ctypes.c_void_p(0),
                        ctypes.c_size_t(0), ctypes.c_uint(CREATE_RULESET_VERSION))


def handled_mask(abi: int) -> int:
    m = (1 << 13) - 1                 # ABI 1: bits 0..12
    if abi >= 2: m |= FS["REFER"]
    if abi >= 3: m |= FS["TRUNCATE"]
    if abi >= 5: m |= FS["IOCTL_DEV"]
    return m


def create_ruleset(handled: int) -> int:
    attr = RulesetAttr(handled_access_fs=handled)
    fd = libc.syscall(ctypes.c_long(NR_create_ruleset), ctypes.byref(attr),
                      ctypes.c_size_t(ctypes.sizeof(attr)), ctypes.c_uint(0))
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    return fd


def add_path(ruleset_fd: int, path: str, access: int) -> bool:
    try:
        pfd = os.open(path, os.O_PATH)
    except OSError:
        return False                  # path absent on this box — skip
    try:
        attr = PathBeneathAttr(allowed_access=access & handled, parent_fd=pfd)
        r = libc.syscall(ctypes.c_long(NR_add_rule), ctypes.c_int(ruleset_fd),
                         ctypes.c_int(RULE_PATH_BENEATH), ctypes.byref(attr), ctypes.c_uint(0))
        if r < 0:
            raise OSError(ctypes.get_errno(), f"landlock_add_rule {path}")
        return True
    finally:
        os.close(pfd)


def restrict_self(ruleset_fd: int) -> None:
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS)")
    if libc.syscall(ctypes.c_long(NR_restrict_self), ctypes.c_int(ruleset_fd), ctypes.c_uint(0)) < 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")


# ---- checks ----
def can_read(p: str) -> bool:
    try:
        with open(p, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


def can_list(p: str) -> bool:
    try:
        os.listdir(p)
        return True
    except OSError:
        return False


def main() -> int:
    HOME = os.path.expanduser("~")
    abi = abi_version()
    if abi < 1:
        print(f"Landlock UNAVAILABLE (abi={abi}, errno={ctypes.get_errno()}). "
              f"The no-sudo option won't work on this host.")
        return 2
    print(f"Landlock ABI v{abi} available.\n")

    global handled
    handled = handled_mask(abi)
    RO = (FS["EXECUTE"] | FS["READ_FILE"] | FS["READ_DIR"]) & handled
    RW = handled

    scratch = "/tmp/pe-landlock-selftest"
    os.makedirs(scratch, exist_ok=True)

    # Discover real withheld sample files BEFORE restricting (we won't be able to
    # walk those trees afterwards — that's the whole point).
    harness = os.path.join(HOME, "spring-petclinic-rest-long-degradation-test")
    ckpt = os.path.join(harness, "checkpoints.yaml")
    acc_glob = glob.glob(os.path.join(harness, "acceptance", "**", "Cp*Tests.java"), recursive=True)
    trash_glob = glob.glob(os.path.join(HOME, ".local/share/Trash/files", "**", "Cp*Tests.java"), recursive=True)
    acc_sample = acc_glob[0] if acc_glob else None
    trash_sample = trash_glob[0] if trash_glob else None
    pos_file = next((p for p in ("/usr/bin/env", "/bin/sh", "/usr/bin/java") if os.path.exists(p)), "/usr/bin/env")

    allow_ro = ["/usr", "/etc", "/opt", "/bin", "/lib", "/lib64", "/sbin",
                os.path.join(HOME, ".local/share/claude"), os.path.join(HOME, ".local/bin")]
    allow_rw = ["/tmp", "/dev", os.path.join(HOME, ".m2"), scratch]

    fd = create_ruleset(handled)
    granted = []
    for p in allow_ro:
        if add_path(fd, p, RO): granted.append(p)
    for p in allow_rw:
        if add_path(fd, p, RW): granted.append(p)
    add_path(fd, "/proc", RO)
    restrict_self(fd)
    os.close(fd)

    # ---- assertions (True = as-expected) ----
    checks = []
    checks.append(("ALLOW  read toolchain    " + pos_file, can_read(pos_file), True))
    checks.append(("ALLOW  list /usr", can_list("/usr"), True))
    try:
        with open(os.path.join(scratch, "probe"), "w") as f:
            f.write("ok")
        wrote = True
    except OSError:
        wrote = False
    checks.append(("ALLOW  write scratch dir", wrote, True))

    checks.append(("DENY   read checkpoints.yaml", can_read(ckpt), False))
    if acc_sample:
        checks.append((f"DENY   read acceptance {os.path.basename(acc_sample)}", can_read(acc_sample), False))
    if trash_sample:
        checks.append((f"DENY   read Trash {os.path.basename(trash_sample)}", can_read(trash_sample), False))
    checks.append(("DENY   list ~ (home)", can_list(HOME), False))
    checks.append(("DENY   list harness repo", can_list(harness), False))
    checks.append(("DENY   list ~/pe-work", can_list(os.path.join(HOME, "pe-work")), False))
    checks.append(("DENY   list Trash", can_list(os.path.join(HOME, ".local/share/Trash/files")), False))

    ok = True
    print("in-process filesystem checks:")
    for label, got, want in checks:
        good = (got == want)
        ok = ok and good
        print(f"  [{'PASS' if good else 'FAIL'}] {label:38} -> {'accessible' if got else 'denied'}")

    # ---- child-process inheritance proof ----
    print("\nchild-process inheritance (cat + find run under the same restriction):")
    tgt = acc_sample or trash_sample or ckpt
    out = subprocess.run(
        ["bash", "-c",
         f"cat {tgt!r} 2>&1 | head -1; echo '---'; "
         f"find {HOME!r} -maxdepth 5 -name 'Cp*Tests.java' 2>&1 | head -3"],
        capture_output=True, text=True)
    lines = (out.stdout + out.stderr).strip().splitlines()
    for line in lines:
        print("   " + line)
    # A leak looks like: `find` emitted a bare result path ending in Tests.java, or
    # `cat` printed real content (a line that is neither empty nor a "…: Permission
    # denied" / "cat: …" error). Denial looks like "Permission denied" messages only.
    leak_paths = [l for l in lines if re.match(r"\s*/.+Tests\.java\s*$", l)]
    cat_leaked = bool(lines) and ("Permission denied" not in lines[0]
                                  and lines[0].strip() not in ("", "---")
                                  and not lines[0].startswith("cat:"))
    child_denied = (not leak_paths) and (not cat_leaked)
    print(f"  [{'PASS' if child_denied else 'FAIL'}] child cat/find blocked from withheld material")
    ok = ok and child_denied

    print("\nOVERALL:", "PASS  (confinement holds — safe to wire into agent.py)" if ok
          else "FAIL  (something leaked — do NOT rely on this yet)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
