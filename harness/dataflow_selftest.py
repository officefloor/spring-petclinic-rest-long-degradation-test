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

Second scenario, ROLES and IMPLICIT DATA REACH (the classes in ROLE_SRC):

  * Roles. Web is a @RestController: its public get() is entry, its private fmt() a
    helper. Step is named in the OfficeFloor wiring: service() is entry, check() and
    log() helpers. Svc and Repo are other.
  * Tramp by role. entry: get(id) hands id to fmt; service(o, repo) hands o to check
    and save and reads repo, so 2 tramp of 3 parameters. helper: fmt(id) hands id to
    svc.find; check(o) reads o, so 1 of 2. other: find(id) and save(o) read theirs, 0 of 2.
  * Carried edges by caller role. entry: get->fmt, service->check, service->save carry,
    service->log does not, 3 of 4. helper: fmt->find carries, 1 of 1.
  * Data reach (needs CK). Methods, constructors excluded: get, fmt, service, check,
    log, find, save = 7, with 1+1+2+1+0+1+1 = 7 parameters. Fields reached: fmt reads
    svc (MAX is a constant and does not count), get reaches svc through fmt, find reads
    prefix: 3. Implicit share 3 / (3 + 7) = 0.3. By role: entry 1 / (1 + 3) = 0.25,
    helper 1 / (1 + 2), other 1 / (1 + 2). Ambient instance fields per method: get, fmt
    and find have 1, the rest 0: mean 3/7. Field span: svc reached by get and fmt (2),
    prefix by find (1): max 2, mean 1.5.

Run standalone (the data-reach checks need CK, located through config.yaml):

    python -m harness.dataflow_selftest --config config.yaml
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

from . import dataflow, placement
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


ROLE_SRC = {
    "Web": """package t;
@RestController
public class Web {
    @Autowired
    private Svc svc;
    private static final int MAX = 3;
    public String get(int id) { return fmt(id); }
    private String fmt(int id) { return svc.find(id) + MAX; }
}
""",
    "Step": """package t;
public class Step {
    public void service(Owner o, Repo repo) { check(o); log(); repo.save(o); }
    private void check(Owner o) { if (o == null) { throw new IllegalStateException(); } }
    private void log() { System.out.println("step"); }
}
""",
    "Svc": """package t;
public class Svc {
    private String prefix = "x";
    public String find(int id) { return prefix + id; }
}
""",
    "Repo": """package t;
public class Repo {
    public void save(Owner o) { String s = o.toString(); }
}
""",
}
ROLE_WIRING = """step:
  class: t.Step
"""
ROLE_EXPECTED = {
    "df_fns_entry": 2, "df_fns_helper": 3, "df_fns_other": 2,
    "df_tramp_ratio_entry": round(2 / 3, 4), "df_tramp_ratio_helper": 0.5,
    "df_tramp_ratio_other": 0.0,
    "df_edge_carry_share_entry": 0.75, "df_edge_carry_share_helper": 1.0,
    "df_edge_carry_share_other": None,
}
REACH_EXPECTED = {
    "dr_methods": 7, "dr_explicit_mean": 1.0, "dr_reached_mean": round(3 / 7, 4),
    "dr_ambient_mean": round(3 / 7, 4), "dr_implicit_share": 0.3,
    "dr_implicit_share_entry": 0.25, "dr_implicit_share_helper": round(1 / 3, 4),
    "dr_implicit_share_other": round(1 / 3, 4),
    "dr_field_span_max": 2, "dr_field_span_mean": 1.5,
}


def _check(out: dict, expected: dict) -> bool:
    ok = True
    for k, want in expected.items():
        got = out.get(k)
        good = got == want
        ok = ok and good
        print(f"  [{'PASS' if good else 'FAIL'}] {k}: {got} (expected {want})")
    return ok


def run_roles(ck_jar: str, java_bin: str) -> bool:
    root = tempfile.mkdtemp(prefix="dataflow_roles_")
    try:
        src = os.path.join(root, "src", "main", "java", "t")
        os.makedirs(src)
        for name, body in ROLE_SRC.items():
            with open(os.path.join(src, f"{name}.java"), "w") as fh:
                fh.write(body)
        wiring = os.path.join(root, "src", "main", "resources", "officefloor")
        os.makedirs(wiring)
        with open(os.path.join(wiring, "step.yml"), "w") as fh:
            fh.write(ROLE_WIRING)
        fns = functions(root, ["src/main/java/**/*.java"])
        adj = call_adjacency(*_call_index(root, fns))
        print("  -- roles and the split by role")
        ok = _check(dataflow.dataflow_metrics(root, fns, adj), ROLE_EXPECTED)
        print("  -- implicit data reach (CK)")
        if not ck_jar or not os.path.isfile(ck_jar):
            print(f"  [FAIL] CK not found ({ck_jar!r}): pass --config config.yaml")
            return False
        out = placement.ck_metrics(root, ["src/main/java"], ck_jar, java_bin, fns=fns, adj=adj)
        if out is None:
            print("  [FAIL] CK did not run")
            return False
        return _check(out, REACH_EXPECTED) and ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


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
        print("  -- tramp data, call edges, co-travel, clumps, signature churn")
        return _check(out, EXPECTED)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml", help="config.yaml, for tools.ck")
    args = ap.parse_args()
    tools = {}
    if os.path.isfile(args.config):
        with open(args.config) as fh:
            tools = (yaml.safe_load(fh) or {}).get("tools") or {}
    print("Data-flow coupling self-test (tramp data, co-travel, clumps, signature churn,\n"
          "roles, implicit data reach)\n")
    ok = run()
    ok = run_roles(tools.get("ck") or "", tools.get("java", "java")) and ok
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
