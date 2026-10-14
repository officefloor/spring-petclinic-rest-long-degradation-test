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

Third scenario, COLLABORATORS vs DATA and DEPENDENCY SURPLUS (the classes in DEP_SRC):

  * Collaborators: Store (@Service), Clock2 and MailNotifier (@Component), Notifier
    (an interface MailNotifier implements), Ctl (@RestController). Owner is data. Fn is
    an OfficeFloor function wired by fn.yml. Ctl injects store, clock and notifier as
    @Autowired fields and has one data field, region.
  * Functions: Store.put(o), Clock2.now(), MailNotifier.send(o) [other]; Ctl.create(o),
    Ctl.stamp(), Fn.service(o, store, notifier) [entry]; Ctl.save(o, s), Ctl.tag(),
    Fn.keep(o, store, notifier) [helper].
  * Data parameters: the six Owner o's. create, save, service and keep only hand o on:
    tramp 4/6. By role: entry create, service 2/2; helper save, keep 2/2; other 0/2.
  * Collaborator parameters: save.s, service.store, service.notifier, keep.store,
    keep.notifier = 5. service hands both on (tramp); keep reads store, never mentions
    notifier: tramp 2/5.
  * Call edges: create->save, save->put, stamp->now, stamp->tag, service->keep,
    keep->put = 6. Four hand a data parameter on (all but stamp's): share and mean 4/6.
    Only service->keep hands a collaborator on: 1/6.
  * Tramp chain of data: Owner is tramp in create and save and taken by put, 2 edges.
  * Data clumps: service and keep share (o, store, notifier), one clump in all; minus
    the collaborators only o is left, no data clump. Types: Owner's call subgraph is
    create-save-put-service-keep (5); Owner is the only data type, so there is no data
    overlap (blank). Over all types the overlap is 0.5 (Owner/Store 1/4, Owner/Notifier
    1/4, Store/Notifier 1).
  * Reach (CK): create reaches store; stamp reaches clock, and region through tag; tag
    reaches region. Data fields reached 2 (stamp, tag), collaborators 2 (create, stamp),
    over 9 methods. Data implicit share 2 / (2 + 6) = 0.25; by role entry 1 / (1 + 2),
    helper 1 / (1 + 2), other 0 / (0 + 2). Field spans: region 2 (data), store 1 and
    clock 1 (collaborators).
  * Surplus. Ctl's methods have its 3 collaborator fields in scope: create uses 1
    (surplus 2), save also has s and uses only s (4 in scope, surplus 3), stamp uses
    clock (2), tag none (3). Fn.service has store and notifier and hands both on
    (surplus 0); keep uses store, not notifier (1). Scope 17, used 6, surplus 11, over
    9 methods. By role: entry 4/8, helper 7/9, other no scope (blank).

Fourth scenario, REACH and SHORTCUT UPTAKE (REACH_SRC, then two changes):

  * System types: Owner, Pet, Visit, Audit, Repo (@Repository), Ctl (@RestController)
    = 6; collaborators Repo and Ctl, data the other 4. Navigation: Owner -> Pet
    (getPet), Repo -> Owner, Visit (find, visit), so Repo reaches Owner, Pet, Visit.
    Private fields do not navigate.
  * Available / used, own class left out: getPet {Pet} / {Pet} (the field it
    returns); getName, log {} / {}; find, visit {Owner, Visit, Pet} / {} (they return
    null); name {Repo, Owner, Pet, Visit} / {Repo, Owner, Pet} (the field, then find,
    getPet, getName resolved); count same available / {Audit} (a static call: from
    outside reach).
  * Shares over 7 methods, |T| = 6: available (1+0+0+3+3+4+4)/6/7 = 15/42; used
    (1+0+0+0+0+3+1)/6/7 = 5/42; use of available over the 5 with something available
    (1 + 0 + 0 + 3/4 + 0)/5 = 0.35; outside 1 of 5 used. Collaborators (2): available
    (1/2 + 1/2)/7, used (1/2)/7. Data (4): available (1+3+3+3+3)/4/7 = 13/28, used
    (1+2+1)/4/7 = 1/7. Entry (name, count): available 4/6, use of available 3/8;
    other: available 7/30, use of available 1/3.
  * Change 1: count starts calling repo.visit (Repo and Visit, both available since the
    first state: 2 shortcuts, latency 1 each); name gains a parameter `Ticker t` and
    calls t.tick() (Ticker: a new type, explicit; Ticker is newly available to name).
    3 new uses, 2 shortcuts; collaborators 1/1 (Repo), data 1/2 (Visit, not Ticker).
    Ticker.tick is a new method in a new class and uses nothing.
    Ctl also gains a field `Mailer mailer` it does not use yet: Mailer arrives in Ctl's
    ambient reach (1 arrival) and is newly available to name and count (with Ticker for
    name, 3 newly available).
  * Change 2: count calls mailer.send(): Mailer, in reach since change 1, used one
    checkpoint later (shortcut, latency 1; the arrival is used, lag 1). name also declares `Visit v = repo.visit(id)`: Visit, available since the
    first state, used two checkpoints later (shortcut, latency 2). A new helper
    Ctl.first() calls repo.find: Repo and Owner, both in Ctl's reach since the first
    state (shortcuts, latency 2). 4 new uses, all shortcuts, latency (1+2+2+2)/4;
    collaborators 1/1 (Repo), data 3/3; new methods 2/2. Over the chain: 1 arrival,
    used later, median lag 1.

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
    # no collaborators here, so the data-only measures equal the totals
    "dfdata_params": 11, "dfcol_params": 0, "dfdata_tramp_ratio": round(4 / 11, 4),
    "dfdata_tramp_chain_max": 2, "dfdata_edge_carry_share": 1.0, "dfdata_clumps": 1,
    "dfdata_type_span_max": 3,
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


DEP_SRC = {
    "Store": """package t;
@Service
public class Store {
    public void put(Owner o) { String s = o.toString(); }
}
""",
    "Clock2": """package t;
@Component
public class Clock2 {
    public int now() { return 1; }
}
""",
    "Notifier": """package t;
public interface Notifier {
    void send(Owner o);
}
""",
    "MailNotifier": """package t;
@Component
public class MailNotifier implements Notifier {
    public void send(Owner o) { String s = o.getName(); }
}
""",
    "Ctl": """package t;
@RestController
public class Ctl {
    @Autowired
    private Store store;
    @Autowired
    private Clock2 clock;
    @Autowired
    private Notifier notifier;
    private String region = "x";
    public void create(Owner o) { save(o, store); }
    private void save(Owner o, Store s) { s.put(o); }
    public int stamp() { return clock.now() + tag(); }
    private int tag() { return region.length(); }
}
""",
    "Fn": """package t;
public class Fn {
    public void service(@Val Owner o, Store store, Notifier notifier) { keep(o, store, notifier); }
    private void keep(Owner o, Store store, Notifier notifier) { store.put(o); }
}
""",
}
DEP_WIRING = """fn:
  class: t.Fn
"""
DEP_EXPECTED = {
    "df_collab_types": 5,
    "dfdata_params": 6, "dfcol_params": 5,
    "dfdata_tramp_ratio": round(4 / 6, 4), "dfcol_tramp_ratio": 0.4,
    "dfdata_tramp_ratio_entry": 1.0, "dfdata_tramp_ratio_helper": 1.0,
    "dfdata_tramp_ratio_other": 0.0,
    "df_edges": 6,
    "dfdata_edge_carry_share": round(4 / 6, 4), "dfdata_edge_carry_mean": round(4 / 6, 4),
    "dfcol_edge_carry_share": round(1 / 6, 4),
    "dfdata_tramp_chain_max": 2,
    "df_data_clumps": 1, "dfdata_clumps": 0,
    "dfdata_type_span_max": 5, "df_type_overlap_mean": 0.5, "dfdata_type_overlap_mean": None,
}
DEP_REACH_EXPECTED = {
    "dr_methods": 9,
    "drdata_implicit_share": 0.25,
    "drdata_implicit_share_entry": round(1 / 3, 4),
    "drdata_implicit_share_helper": round(1 / 3, 4),
    "drdata_implicit_share_other": 0.0,
    "drdata_reached_mean": round(2 / 9, 4), "drcol_reached_mean": round(2 / 9, 4),
    "drdata_field_span_max": 2, "drcol_field_span_max": 1,
    "dep_scope_mean": round(17 / 9, 4), "dep_used_mean": round(6 / 9, 4),
    "dep_surplus_mean": round(11 / 9, 4), "dep_surplus_share": round(11 / 17, 4),
    "dep_surplus_share_entry": 0.5, "dep_surplus_share_helper": round(7 / 9, 4),
    "dep_surplus_share_other": None,
}


REACH_SRC = {
    "Owner": """package t;
public class Owner {
    private Pet pet;
    public Pet getPet() { return pet; }
}
""",
    "Pet": """package t;
public class Pet {
    private String name;
    public String getName() { return name; }
}
""",
    "Visit": """package t;
public class Visit {
}
""",
    "Audit": """package t;
public class Audit {
    public static void log(String s) { }
}
""",
    "Repo": """package t;
@Repository
public class Repo {
    public Owner find(int id) { return null; }
    public Visit visit(int id) { return null; }
}
""",
    "Ctl": """package t;
@RestController
public class Ctl {
    @Autowired
    private Repo repo;
    public String name(int id) { return repo.find(id).getPet().getName(); }
    public int count(int id) { Audit.log("x"); return id; }
}
""",
}
REACH_CHANGE1 = {
    "Ticker": """package t;
public class Ticker {
    public void tick() { }
}
""",
    "Mailer": """package t;
public class Mailer {
    public void send() { }
}
""",
    "Ctl": """package t;
@RestController
public class Ctl {
    @Autowired
    private Repo repo;
    private Mailer mailer;
    public String name(int id, Ticker t) { t.tick(); return repo.find(id).getPet().getName(); }
    public int count(int id) { Audit.log("x"); return repo.visit(id) == null ? 0 : id; }
}
""",
}
REACH_CHANGE2 = {
    "Ctl": """package t;
@RestController
public class Ctl {
    @Autowired
    private Repo repo;
    private Mailer mailer;
    public String name(int id, Ticker t) {
        t.tick();
        Visit v = repo.visit(id);
        return repo.find(id).getPet().getName();
    }
    public int count(int id) {
        Audit.log("x");
        mailer.send();
        return repo.visit(id) == null ? 0 : id;
    }
    private Owner first() { return repo.find(1); }
}
""",
}
UPTAKE_EXPECTED = [
    {   # the first state: no previous checkpoint, so no uptake
        "reach_types": 6, "reach_methods": 7,
        "reach_avail_share": round(15 / 42, 4), "reach_used_share": round(5 / 42, 4),
        "reach_use_of_avail": 0.35, "reach_outside_share": 0.2,
        "reach_avail_share_col": round(1 / 7, 4), "reach_used_share_col": round(0.5 / 7, 4),
        "reach_avail_share_data": round(13 / 28, 4), "reach_used_share_data": round(1 / 7, 4),
        "reach_avail_share_entry": round(4 / 6, 4), "reach_use_of_avail_entry": 0.375,
        "reach_avail_share_other": round(7 / 30, 4),
        "reach_use_of_avail_other": round(1 / 3, 4),
        "reach_avail_share_helper": None,
        "reach_new_uses": None, "reach_shortcut_share": None,
    },
    {
        "reach_types": 8,
        "reach_new_avail": 3, "reach_new_uses": 3,
        "reach_class_arrivals": 1, "reach_arrived_uses": 0, "reach_arrival_lag_mean": None,
        "reach_shortcut_share": round(2 / 3, 4), "reach_shortcut_share_col": 1.0,
        "reach_shortcut_share_data": 0.5, "reach_shortcut_latency_mean": 1.0,
        "reach_shortcut_share_newfns": None,
    },
    {
        "reach_new_avail": 0, "reach_new_uses": 4, "reach_shortcut_share": 1.0,
        "reach_shortcut_share_newfns": 1.0,
        "reach_shortcut_share_col": 1.0, "reach_shortcut_share_data": 1.0,
        "reach_shortcut_latency_mean": 1.75,
        "reach_class_arrivals": 0, "reach_arrived_uses": 1, "reach_arrival_lag_mean": 1.0,
    },
]


def run_reach() -> bool:
    root = tempfile.mkdtemp(prefix="dataflow_reach_")
    ok = True
    try:
        src = os.path.join(root, "src", "main", "java", "t")
        os.makedirs(src)
        prev, since = None, {}
        for k, (change, expected) in enumerate(
                zip((REACH_SRC, REACH_CHANGE1, REACH_CHANGE2), UPTAKE_EXPECTED), 1):
            for name, body in change.items():
                with open(os.path.join(src, f"{name}.java"), "w") as fh:
                    fh.write(body)
            fns = functions(root, ["src/main/java/**/*.java"])
            adj = call_adjacency(*_call_index(root, fns))
            table = dataflow.type_table(root)
            collab = dataflow.collaborator_types(root, table=table)
            out, sets = dataflow.reach_metrics(root, fns, adj, table, collab)
            out.update(dataflow.reach_uptake(prev, sets, since, k))
            prev = sets
            print(f"  -- reach, state {k}")
            ok = _check(out, expected) and ok
        print("  -- reach, end of chain")
        summ = dataflow.reach_chain_summary(since)
        ok = _check(summ, {"arrivals": 1, "used_same": 0, "used_later": 1, "never_used": 0,
                           "later_lag_median": 1}) and ok
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # Lead-lag on a known series: s is a moved one checkpoint later, so a leads s at
    # lag 1 exactly (rho 1.0) and s does not lead a.
    a = [3, 0, 0, 1, 0, 0, 2, 0, 0, 0]
    s = [0] + a[:-1]
    fwd, rev = dataflow.lead_lag(a, s, (1,))[1]
    good = fwd == 1.0 and rev is not None and rev < fwd
    print(f"  [{'PASS' if good else 'FAIL'}] lead-lag: reach->use {fwd}, use->reach {rev} "
          f"(expected 1.0 and lower)")
    return ok and good


def run_tramp_chains() -> bool:
    """Longest tramp chain through a cycle, in both visiting orders. B and C call each other;
    X enters the cycle at C and A at B. The true chains are X-C-B-D-E (4) and A-B-D-E (3).
    Caching C's depth while it was cut short at B (reached from A) gave X only 1."""
    ok = True
    edges = {"A": ["B"], "B": ["C", "D"], "C": ["B"], "D": ["E"], "X": ["C"]}
    sig = {k: [("t", "T")] for k in "ABCDEX"}
    want = {"A": 3, "B": 2, "C": 3, "D": 1, "X": 4}
    for order in ("ABCDX", "XDCBA"):
        tramp = {k: {"T"} for k in order}
        got = {k: v for (k, _t), v in dataflow.tramp_chains(edges, sig, tramp).items()}
        good = got == want
        ok = ok and good
        print(f"  [{'PASS' if good else 'FAIL'}] tramp chains, visiting {order}: {got} "
              f"(expected {want})")
    return ok


def _check(out: dict, expected: dict) -> bool:
    ok = True
    for k, want in expected.items():
        got = out.get(k)
        good = got == want
        ok = ok and good
        print(f"  [{'PASS' if good else 'FAIL'}] {k}: {got} (expected {want})")
    return ok


def _run_ck_scenario(title: str, sources: dict, wiring: tuple[str, str], expected: dict,
                     reach_expected: dict, ck_jar: str, java_bin: str) -> bool:
    root = tempfile.mkdtemp(prefix="dataflow_ck_")
    try:
        src = os.path.join(root, "src", "main", "java", "t")
        os.makedirs(src)
        for name, body in sources.items():
            with open(os.path.join(src, f"{name}.java"), "w") as fh:
                fh.write(body)
        wdir = os.path.join(root, "src", "main", "resources", "officefloor")
        os.makedirs(wdir)
        with open(os.path.join(wdir, wiring[0]), "w") as fh:
            fh.write(wiring[1])
        fns = functions(root, ["src/main/java/**/*.java"])
        adj = call_adjacency(*_call_index(root, fns))
        print(f"  -- {title}")
        ok = _check(dataflow.dataflow_metrics(root, fns, adj), expected)
        print(f"  -- {title}: field reach (CK)")
        if not ck_jar or not os.path.isfile(ck_jar):
            print(f"  [FAIL] CK not found ({ck_jar!r}): pass --config config.yaml")
            return False
        out = placement.ck_metrics(root, ["src/main/java"], ck_jar, java_bin, fns=fns, adj=adj)
        if out is None:
            print("  [FAIL] CK did not run")
            return False
        return _check(out, reach_expected) and ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_roles(ck_jar: str, java_bin: str) -> bool:
    return _run_ck_scenario("roles and the split by role", ROLE_SRC,
                            ("step.yml", ROLE_WIRING), ROLE_EXPECTED, REACH_EXPECTED,
                            ck_jar, java_bin)


def run_collaborators(ck_jar: str, java_bin: str) -> bool:
    return _run_ck_scenario("collaborators vs data, dependency surplus", DEP_SRC,
                            ("fn.yml", DEP_WIRING), DEP_EXPECTED, DEP_REACH_EXPECTED,
                            ck_jar, java_bin)


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
          "roles, implicit data reach, collaborators vs data, dependency surplus, reach)\n")
    ok = run()
    ok = run_roles(tools.get("ck") or "", tools.get("java", "java")) and ok
    ok = run_collaborators(tools.get("ck") or "", tools.get("java", "java")) and ok
    ok = run_reach() and ok
    ok = run_tramp_chains() and ok
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
