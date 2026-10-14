#!/usr/bin/env python3
"""Self-test for the data-flow columns (harness/dataflow.py). Every expected value is
worked by hand from the source below.

  * Tramp: Ctl.handle(Owner o, Pet p, int id) calls svc(o, p, id). o is only handed on,
    p is read (p.getName()) as well as handed on, id is only handed on. Of its three
    parameters two are tramp. Svc.svc(Owner o, Pet p, int id) calls repo(o, id) and
    reads p; o and id are tramp again. Repo.repo(Owner o, int id) reads both. Unused:
    Util.log(Owner o) never mentions o. Dto.make(Owner o) passes o to `new Dto(o)`,
    which is a use. Totals: 3 + 3 + 2 + 1 + 1 = 10 parameters, 4 tramp, 1 unused.
  * Tramp chain: Owner is tramp in handle and in svc and taken by repo, so it is handed
    down handle -> svc -> repo: 2 edges.
  * Carried: handle passes o, p, id to svc (3); svc passes o, id to repo (2). Both
    edges carry, share 1.0, mean 2.5 (make -> Dto is a constructor, not an edge).
  * Co-travel: edges handle->svc (shares Owner, Pet) and svc->repo (shares Owner).
    Domain types per edge 2 and 1, mean 1.5; both edges share, share 1.0.
  * Type spans: Owner is taken by handle, svc, repo, log and make. handle-svc-repo is
    connected, so span 3. Pet: handle and svc, span 2. Mean 2.5.
  * Type overlap: Owner's edges {h->s, s->r}, Pet's {h->s}. Jaccard 1/2.
  * Data clumps: (o Owner, p Pet, id int) recurs in handle and svc, one clump.
  * Signature churn, prev -> cur: Repo.repo gains `int id` (changed, 1 parameter
    added), Repo.extra is new, Repo.keep unchanged. Share 1 / (1 + 1) = 0.5.

Run standalone:

    python -m harness.dataflow_selftest
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from . import dataflow
from .metrics import _call_index, _is_prod_java, call_adjacency, functions

CUR = {
    "Ctl": """package t;
public class Ctl {
    private Svc s;
    public String handle(Owner o, Pet p, int id) {
        System.out.println(p.getName());
        return s.svc(o, p, id);
    }
}
""",
    "Svc": """package t;
public class Svc {
    private Repo r;
    public String svc(Owner o, Pet p, int id) {
        if (p.getName() == null) { return "none"; }
        return r.repo(o, id);
    }
}
""",
    "Repo": """package t;
public class Repo {
    public String repo(Owner o, int id) { return o.getName() + id; }
    public int extra() { return 1; }
    public int keep() { return 2; }
}
""",
    "Util": """package t;
public class Util {
    public void log(Owner o) { System.out.println("x"); }
}
""",
    "Dto": """package t;
public class Dto {
    private final Owner owner;
    public Dto(Owner owner) { this.owner = owner; }
    public static Dto make(Owner o) { return new Dto(o); }
}
""",
}
PREV_REPO = """package t;
public class Repo {
    public String repo(Owner o) { return o.getName(); }
    public int keep() { return 2; }
}
"""

# The Dto constructor's own parameter is read (this.owner = owner), so it adds 1
# parameter and no tramp: 11 parameters in all.
EXPECTED = {
    "df_params": 11, "df_tramp_params": 4, "df_unused_params": 1,
    "df_tramp_ratio": round(4 / 11, 4),
    "df_tramp_chain_max": 2,
    "df_edge_carry_share": 1.0, "df_edge_carry_mean": 2.5,
    "df_edge_shared_share": 1.0, "df_edge_shared_mean": 1.5,
    "df_type_span_max": 3,
    "df_type_overlap_mean": 0.5,
    "df_data_clumps": 1,
    "sig_changed_fns": 1, "sig_new_fns": 1, "sig_params_added": 1,
    "sig_churn_share": 0.5,
}


def _git(root, *args):
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)


def run() -> bool:
    root = tempfile.mkdtemp(prefix="dataflow_selftest_")
    try:
        src = os.path.join(root, "src", "main", "java", "t")
        os.makedirs(src)
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "t@t")
        _git(root, "config", "user.name", "t")
        for name, body in CUR.items():
            with open(os.path.join(src, f"{name}.java"), "w") as fh:
                fh.write(PREV_REPO if name == "Repo" else body)
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "prev")
        with open(os.path.join(src, "Repo.java"), "w") as fh:
            fh.write(CUR["Repo"])
        _git(root, "commit", "-qam", "cur")

        fns = functions(root, ["src/main/java/**/*.java"])
        adj = call_adjacency(*_call_index(root, fns))
        out = dataflow.dataflow_all(root, fns, adj, "HEAD~1", "HEAD", _is_prod_java)
        ok = True
        for k, want in EXPECTED.items():
            got = out.get(k)
            good = got == want
            ok = ok and good
            print(f"  [{'PASS' if good else 'FAIL'}] {k}: {got} (expected {want})")
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    print("Data-flow coupling self-test (tramp data, co-travel, clumps, signature churn)\n")
    ok = run()
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
