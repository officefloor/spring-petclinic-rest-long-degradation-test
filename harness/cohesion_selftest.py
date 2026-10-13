#!/usr/bin/env python3
"""Self-test for the class-cohesion columns: CK's `ck_tcc`/`ck_lcc` and the harness's
Bieman & Kang `bk_tcc`/`bk_lcc`.

WHY THIS EXISTS. For every run up to 2026-10-14, `ck_tcc_*` and `ck_lcc_*` read exactly
0.0. CK was called with its variablesAndFields switch off, and TCC/LCC are built from the
per-method field use that switch turns on. Nothing errored: the columns were just zero.
The CK check below fails if that ever happens again.

The `bk_*` checks pin down the two ways Bieman & Kang (1995) differ from CK. A field
reached through a call to another method of the same class counts as used, and
constructors are not among the methods compared. Every expected value was worked out by
hand from the definition:

  * Mixed: a(), b() read x; c(), d() read y; e() calls a(). Connected pairs: a-b, a-e
    (through a), b-e, c-d, so 4 of 10 pairs. TCC 0.4, and LCC is also 0.4, since no
    chain joins {a,b,e} to {c,d}. CK gives 0.2, because it cannot see e() reach x.
  * Getters: a constructor sets p, q and r; getP/getQ/getR each read one of them. No
    two getters share a field, so TCC = LCC = 0. CK connects them all through the
    constructor.
  * Helper: m1() and m2() reach z only through private h(); m3() reads nothing. The
    private helper is not compared itself. Only m1-m2 connect, so TCC = LCC = 1/3.
  * Chain: f1 reads u, f2 reads u and v, f3 reads v. f1-f2 and f2-f3 are direct
    connections, giving TCC 2/3. f1-f3 is joined through f2, giving LCC 1.

Run standalone:

    python -m harness.cohesion_selftest --config config.yaml
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

import yaml

from . import placement
from .metrics import _call_index, call_adjacency, functions

CLASSES = {
    "Mixed": """package t;
public class Mixed {
    private int x;
    private int y;
    public int a() { return x + 1; }
    public int b() { return x * 2; }
    public int c() { return this.y; }
    public int d() { return y - 1; }
    public int e() { return a() + 3; }
}
""",
    "Getters": """package t;
public class Getters {
    private final int p;
    private final int q;
    private final int r;
    public Getters(int p, int q, int r) { this.p = p; this.q = q; this.r = r; }
    public int getP() { return p; }
    public int getQ() { return q; }
    public int getR() { return r; }
}
""",
    "Helper": """package t;
public class Helper {
    private int z;
    private int h() { return z; }
    public int m1() { return h(); }
    public int m2() { return h() + 1; }
    public int m3() { return 0; }
}
""",
    "Chain": """package t;
public class Chain {
    private int u;
    private int v;
    public int f1() { return u; }
    public int f2() { return u + v; }
    public int f3() { return v; }
}
""",
}

# class -> (bk_tcc, bk_lcc), worked by hand in the module docstring
EXPECTED = {
    "Mixed": (0.4, 0.4),
    "Getters": (0.0, 0.0),
    "Helper": (round(1 / 3, 4), round(1 / 3, 4)),
    "Chain": (round(2 / 3, 4), 1.0),
}


def run(ck_jar: str, java_bin: str = "java") -> bool:
    root = tempfile.mkdtemp(prefix="cohesion_selftest_")
    ok = True
    try:
        src = os.path.join(root, "src", "t")
        os.makedirs(src)
        for name, body in CLASSES.items():
            with open(os.path.join(src, f"{name}.java"), "w") as fh:
                fh.write(body)
        fns = functions(root, ["src/**/*.java"])
        index = _call_index(root, fns)
        adj = call_adjacency(*index)
        for name, (tcc, lcc) in EXPECTED.items():
            out = placement.ck_metrics(root, ["src"], ck_jar, java_bin,
                                       handler_class=name, fns=fns, adj=adj)
            if out is None:
                print(f"  [FAIL] {name}: CK did not run ({ck_jar})")
                ok = False
                continue
            got = (out.get("bk_handler_tcc"), out.get("bk_handler_lcc"))
            good = got == (tcc, lcc)
            print(f"  [{'PASS' if good else 'FAIL'}] {name}: bk TCC/LCC {got}, "
                  f"expected {(tcc, lcc)}; CK reports "
                  f"{(out.get('ck_handler_tcc'), out.get('ck_handler_lcc'))}")
            ok = ok and good
        # CK's own TCC must not be the all-zero of the switched-off call. Mixed has two
        # directly connected pairs of ten, so CK's direct-only TCC is 0.2.
        out = placement.ck_metrics(root, ["src"], ck_jar, java_bin, handler_class="Mixed")
        ck_tcc = out.get("ck_handler_tcc") if out else None
        good = ck_tcc == 0.2
        print(f"  [{'PASS' if good else 'FAIL'}] CK field use is on: Mixed ck TCC "
              f"{ck_tcc}, expected 0.2")
        ok = ok and good
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml", help="config.yaml, for tools.ck")
    args = ap.parse_args()
    with open(args.config) as fh:
        tools = (yaml.safe_load(fh) or {}).get("tools") or {}
    ck_jar = tools.get("ck") or ""
    print("Class cohesion self-test (CK and Bieman & Kang TCC/LCC)\n")
    ok = run(ck_jar, tools.get("java", "java"))
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
