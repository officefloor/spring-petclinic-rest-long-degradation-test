"""Data-flow coupling: does the data follow the call graph?

THE QUESTION. The "two graphs, not one" argument is that a Spring endpoint couples its
control flow (which function runs next) to its data flow (which values reach which
function): to get a value from step one to step four you thread it through steps two
and three, even when they never use it. OfficeFloor decouples the two by construction:
continuations sequence the functions, and each function names only the types it uses.
The prediction is that the Spring arm's data flow grows INTO its call graph change after
change, and that this accretion is the erosion. None of the established suites measures
it, so this module does, from three angles. Every number is a pure function of the
source at one ref (plus the previous ref for signature churn).

1. TRAMP DATA (Stevens, Myers & Constantine 1974): a parameter a function only passes
   on to another call, never reads itself. This is the "indirect use" grade of Offutt,
   Harrold & Kolte (1993). `df_tramp_ratio` is the share of all parameters that are
   tramp; `df_tramp_chain_max` the longest run of calls a type is handed down while
   tramp at every hop but the last.

2. DATA ON CALL EDGES. An edge carries data when the caller passes one of its own
   parameters to the callee (`df_edge_carry_*`), whatever its type: in PetClinic most
   of what is handed down is ids. TYPE CO-TRAVEL: per call edge, the domain parameter
   types caller and callee share (value types such as Integer and String excluded).
   Per type, the call subgraph of the functions that take it, and the largest
   connected piece of that subgraph (`df_type_span_*`, how far one type travels). The
   edge sets of different types overlapping (`df_type_overlap_*`, Jaccard) is the data
   graph collapsing onto the call graph.

3. SIGNATURE CHURN: is a change additive? Existing functions whose parameter list the
   checkpoint changed, against functions it added. `sig_churn_share` near 0 means rules
   arrive as new functions; near 1 means they arrive by widening existing signatures.

Also reported: `df_data_clumps` (Fowler's data clump: three or more parameters, by name
and type, recurring together in two or more signatures) and `df_unused_params`.

LIMITS, all symmetric across arms:
  * Parsing is lexical (lizard's long_name for signatures, regexes over bodies), not a
    type-resolved data-flow analysis. A parameter passed on AND read is "used"; a
    parameter reached only through a lambda or a field assignment is "used".
  * Call edges are the harness's conservative `call_adjacency` (a lower bound).
  * OfficeFloor's composition (YAML wiring) is NOT modelled. It decouples by design and
    is architectural constraint, not code the agent couples together.
  * Functions with no body (interface and abstract methods) are not in lizard's list,
    so they carry no parameters here.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
from collections import defaultdict
from itertools import combinations
from typing import Optional

import lizard

# Types that every layer passes and that therefore say nothing about coupling between
# two functions: primitives, their boxes, String, and the generic containers (the
# element type inside the container still counts).
VALUE_TYPES = frozenset("""
    byte short int long float double boolean char void
    Byte Short Integer Long Float Double Boolean Character Void Number
    String CharSequence Object BigDecimal BigInteger UUID
    LocalDate LocalDateTime LocalTime Instant OffsetDateTime ZonedDateTime Duration Period
    List Set Map Collection Iterable Optional Stream Collections ArrayList HashMap HashSet
    Supplier Function Consumer Predicate
""".split())

_KEYWORDS_BEFORE_PAREN = frozenset(
    "if while for switch return catch synchronized throw new assert case else do try "
    "this super".split())   # this(...)/super(...) delegate to a constructor: a use
_ANNOT = re.compile(r"@\s*[\w.]+(\s*\([^)]*\))?")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_STRIP = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)


# ---------------------------------------------------------------------------
# signatures
# ---------------------------------------------------------------------------

def _split_top(s: str) -> list[str]:
    """Split on commas outside <...> and (...)."""
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def params(long_name: str) -> list[tuple[str, str]]:
    """[(name, type)] from lizard's long_name, e.g.
    `A::f( final @ Valid Owner owner , Map<String,Pet> m)` -> [('owner','Owner'),
    ('m','Map<String,Pet>')]. Annotations and `final` are dropped, varargs kept as `T...`."""
    lo, hi = long_name.find("("), long_name.rfind(")")
    if lo < 0 or hi <= lo:
        return []
    out = []
    for p in _split_top(long_name[lo + 1:hi]):
        p = _ANNOT.sub(" ", p)
        p = re.sub(r"\bfinal\b", " ", p).strip()
        if not p:
            continue
        m = re.match(r"(.*?)\s*([A-Za-z_$][\w$]*)\s*$", p, re.S)
        if not m or not m.group(1).strip():
            continue
        typ = re.sub(r"\s+", "", m.group(1))
        out.append((m.group(2), typ))
    return out


def domain_types(typ: str) -> set[str]:
    """The non-value type names inside one parameter type: `Map<String,Pet>` -> {Pet},
    `org.x.Owner` -> {Owner}."""
    return {t.split(".")[-1] for t in _IDENT.findall(typ.replace("...", ""))
            if t.split(".")[-1] not in VALUE_TYPES and t[:1].isupper()}


# ---------------------------------------------------------------------------
# tramp parameters
# ---------------------------------------------------------------------------

def _body_after_signature(text: str) -> str:
    """The function body: everything after the first `{` outside the parameter parens."""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "{" and depth == 0:
            return text[i + 1:]
    return ""


def _enclosing_call(body: str, i: int) -> Optional[str]:
    """The method name whose argument list position i is directly inside, or None when
    it is not a method call (a constructor, an if/while/return parenthesis)."""
    depth = 0
    j = i - 1
    while j >= 0:
        ch = body[j]
        if ch in ")]}":
            depth += 1
        elif ch in "([{":
            if depth == 0:
                break
            depth -= 1
        j -= 1
    if j < 0 or body[j] != "(":
        return None
    k = j - 1
    while k >= 0 and body[k].isspace():
        k -= 1
    if k >= 0 and body[k] == ">":          # explicit generic call: this.<T>m(
        k = body.rfind("<", 0, k)
        k -= 1
        while k >= 0 and body[k].isspace():
            k -= 1
    e = k + 1
    while k >= 0 and (body[k].isalnum() or body[k] in "_$"):
        k -= 1
    word = body[k + 1:e]
    if not word or word in _KEYWORDS_BEFORE_PAREN:
        return None
    before = body[:k + 1].rstrip()
    return None if re.search(r"\bnew\s*$", before) else word


def param_flow(source: str, long_name: str) -> dict[str, tuple[str, set[str]]]:
    """name -> (kind, callees) for one function's parameters. kind is 'tramp' |
    'unused' | 'used'; callees the method names it is passed to as a whole argument.

    tramp: every reference is a whole argument of a method call (`g(x)`, `s.h(a, x)`),
    so the function only hands it on. Passing into a constructor (`new Dto(x)`) is a
    use, not tramp: the value is consumed into a structure. A parameter both read and
    passed on is 'used' but still lists its callees (the edge carries it)."""
    body = _STRIP.sub(lambda m: " " * len(m.group(0)), _body_after_signature(source))
    out = {}
    for name, _t in params(long_name):
        occ = [m.start() for m in re.finditer(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", body)]
        if not occ:
            out[name] = ("unused", set())
            continue
        callees = set()
        fwd = 0
        for i in occ:
            prev = body[:i].rstrip()[-1:]
            nxt = body[i + len(name):].lstrip()[:1]
            callee = _enclosing_call(body, i) if prev in "(," and nxt in ",)" else None
            if callee:
                fwd += 1
                callees.add(callee)
        out[name] = ("tramp" if fwd == len(occ) else "used", callees)
    return out


def classify_params(source: str, long_name: str) -> dict[str, str]:
    """name -> 'tramp' | 'unused' | 'used' (see `param_flow`)."""
    return {n: k for n, (k, _c) in param_flow(source, long_name).items()}


# ---------------------------------------------------------------------------
# function roles: where in the architecture a function sits
# ---------------------------------------------------------------------------
#
#   entry  - a function the framework calls with the request's data: an OfficeFloor
#            function's wired method (`service` of a class named in the YAML wiring),
#            or a public method of a Spring @RestController / @Controller.
#   helper - any other method of those same classes (code the entry calls in plain Java).
#   other  - everything else: services, repositories, mappers, models, utilities.
#
# The split exists because the parameter measures mean different things in each place.
# Between OfficeFloor functions, the data is matched by type and the wiring decides the
# order, so nothing is threaded. Inside one, the agent writes ordinary Java and can thread
# data like anywhere else. Splitting by role says which of the two a number comes from.

ROLES = ("entry", "helper", "other")
WIRING_GLOB = "src/main/resources/officefloor/**/*.yml"
WIRED_METHOD = "service"
_WIRED_CLASS = re.compile(r"class:\s*([\w.]+)")
_CONTROLLER = re.compile(r"@(Rest)?Controller\b")


def roles(worktree: str, fns: list[dict]) -> dict:
    """node key -> 'entry' | 'helper' | 'other' (see above). `fns` must have been
    through metrics._call_index."""
    wired: set[str] = set()
    for path in glob.glob(os.path.join(worktree, WIRING_GLOB), recursive=True):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        wired |= {c.split(".")[-1] for c in _WIRED_CLASS.findall(text)}
    controller_files: dict[str, bool] = {}
    lines: dict[str, list[str]] = {}
    out = {}
    for f in fns:
        if "_key" not in f:
            continue
        path = os.path.join(worktree, f["file"])
        if f["_cls"] in wired:
            out[f["_key"]] = "entry" if f["_meth"] == WIRED_METHOD else "helper"
            continue
        if path not in controller_files:
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                text = ""
            controller_files[path] = bool(_CONTROLLER.search(text))
            lines[path] = text.splitlines()
        if controller_files[path]:
            # the modifiers sit on the signature's own line (lizard's start line)
            sig_line = lines[path][f["start"] - 1] if f["start"] <= len(lines[path]) else ""
            out[f["_key"]] = "entry" if re.search(r"\bpublic\b", sig_line) else "helper"
        else:
            out[f["_key"]] = "other"
    return out


# ---------------------------------------------------------------------------
# whole-checkpoint metrics
# ---------------------------------------------------------------------------

def _source(worktree: str, fn: dict, cache: dict) -> str:
    path = f"{worktree}/{fn['file']}"
    if path not in cache:
        try:
            cache[path] = open(path, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            cache[path] = []
    return "\n".join(cache[path][fn["start"] - 1:fn["end"]])


def _components(nodes: set, edges: list[tuple]) -> list[int]:
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        parent[find(a)] = find(b)
    sizes: dict = defaultdict(int)
    for n in nodes:
        sizes[find(n)] += 1
    return list(sizes.values())


def dataflow_metrics(worktree: str, fns: list[dict], adj: dict) -> dict:
    """Tramp data, type co-travel and data clumps over one checkpoint.

    `fns` must have been through metrics._call_index (each carries `_key`), and `adj`
    is metrics.call_adjacency over the same records."""
    cache: dict = {}
    by_key = {f["_key"]: f for f in fns if "_key" in f}
    role = roles(worktree, fns)
    r_params: dict = defaultdict(int)
    r_tramp: dict = defaultdict(int)
    sig: dict = {}                      # key -> [(name, type)]
    dom: dict = {}                      # key -> domain types across all params
    tramp_types: dict = {}              # key -> set of full types that are tramp here
    passes: dict = {}                   # key -> {callee name: parameters passed to it}
    n_params = n_tramp = n_unused = n_with = n_tramp_fns = 0
    for k, f in by_key.items():
        ps = params(f["long_name"])
        sig[k] = ps
        dom[k] = set().union(*(domain_types(t) for _, t in ps)) if ps else set()
        if not ps:
            continue
        flow = param_flow(_source(worktree, f, cache), f["long_name"])
        cls = {n: kind for n, (kind, _c) in flow.items()}
        cnt: dict = defaultdict(int)
        for _n, (_k, callees) in flow.items():
            for c in callees:
                cnt[c] += 1
        passes[k] = cnt
        n_with += 1
        n_params += len(ps)
        t = {typ for name, typ in ps if cls.get(name) == "tramp"}
        n_tramp += sum(1 for v in cls.values() if v == "tramp")
        r_params[role.get(k, "other")] += len(ps)
        r_tramp[role.get(k, "other")] += sum(1 for v in cls.values() if v == "tramp")
        n_unused += sum(1 for v in cls.values() if v == "unused")
        if t:
            n_tramp_fns += 1
            tramp_types[k] = t

    # longest tramp chain: (f, T) -> (g, T) when f hands T on, g is a callee taking T
    memo: dict = {}

    def depth(k, typ, stack):
        if (k, typ) in memo:
            return memo[(k, typ)]
        best = 0
        for g in adj.get(k, ()):
            if g == k or (g, typ) in stack or typ not in {t for _, t in sig.get(g, [])}:
                continue
            nxt = depth(g, typ, stack | {(g, typ)}) if typ in tramp_types.get(g, ()) else 0
            best = max(best, 1 + nxt)
        memo[(k, typ)] = best
        return best
    chain_max = max((depth(k, t, {(k, t)}) for k, ts in tramp_types.items() for t in ts),
                    default=0)

    # type co-travel on call edges
    edges = [(a, b) for a, bs in adj.items() for b in bs if a != b and a in by_key and b in by_key]
    shared = [len(dom[a] & dom[b]) for a, b in edges]
    # an edge CARRIES data when the caller passes one of its own parameters to the callee
    carried = [passes.get(a, {}).get(by_key[b].get("_meth", ""), 0) for a, b in edges]
    by_type: dict = defaultdict(set)
    for k, ts in dom.items():
        for t in ts:
            by_type[t].add(k)
    spans, type_edges = [], {}
    for t, nodes in by_type.items():
        if len(nodes) < 2:
            continue
        te = [(a, b) for a, b in edges if a in nodes and b in nodes]
        spans.append(max(_components(nodes, te)))
        if te:
            type_edges[t] = frozenset(te)
    jac = [len(x & y) / len(x | y) for x, y in combinations(type_edges.values(), 2)]

    # data clumps: >=3 (name, type) parameters shared by >=2 signatures
    psets = [frozenset(ps) for ps in sig.values() if len(ps) >= 3]
    clumps = {a & b for a, b in combinations(psets, 2) if len(a & b) >= 3}

    def r(x, n=4):
        return None if x is None else round(x, n)
    split = {}
    for ro in ROLES:
        ce = [c for (a, _b), c in zip(edges, carried) if role.get(a, "other") == ro]
        split[f"df_fns_{ro}"] = sum(1 for k in by_key if role.get(k, "other") == ro)
        split[f"df_params_{ro}"] = r_params[ro]
        split[f"df_tramp_ratio_{ro}"] = r(r_tramp[ro] / r_params[ro]) if r_params[ro] else None
        split[f"df_edge_carry_share_{ro}"] = (r(sum(1 for c in ce if c) / len(ce))
                                             if ce else None)
    return split | {
        "df_params": n_params,
        "df_tramp_params": n_tramp,
        "df_tramp_ratio": r(n_tramp / n_params) if n_params else None,
        "df_tramp_fn_share": r(n_tramp_fns / n_with) if n_with else None,
        "df_unused_params": n_unused,
        "df_tramp_chain_max": chain_max,
        "df_edges": len(edges),
        "df_edge_carry_share": r(sum(1 for c in carried if c) / len(carried)) if carried else None,
        "df_edge_carry_mean": r(sum(carried) / len(carried)) if carried else None,
        "df_edge_shared_share": r(sum(1 for s in shared if s) / len(shared)) if shared else None,
        "df_edge_shared_mean": r(sum(shared) / len(shared)) if shared else None,
        "df_types": len(by_type),
        "df_type_span_max": max(spans, default=None),
        "df_type_span_mean": r(sum(spans) / len(spans)) if spans else None,
        "df_type_overlap_mean": r(sum(jac) / len(jac)) if jac else None,
        "df_type_overlap_max": r(max(jac)) if jac else None,
        "df_data_clumps": len(clumps),
    }


# ---------------------------------------------------------------------------
# signature churn (needs the previous checkpoint)
# ---------------------------------------------------------------------------

def _sigs_at(worktree: str, ref: str, path: str) -> dict[str, list[tuple[str, ...]]]:
    """method name -> [parameter-type tuple per overload] for path@ref."""
    try:
        code = subprocess.run(["git", "-C", worktree, "show", f"{ref}:{path}"],
                              capture_output=True, text=True, timeout=60).stdout
        fl = lizard.analyze_file.analyze_source_code(path, code).function_list
    except Exception:
        return {}
    out: dict = defaultdict(list)
    for f in fl:
        out[f.name.split("::")[-1]].append(tuple(t for _, t in params(f.long_name)))
    return out


def signature_churn(worktree: str, prev_ref: str, cur_ref: str,
                    prod: callable) -> dict:
    """Existing functions whose parameter types changed vs functions added, over the
    production Java this checkpoint touched. A method is 'existing' when its file (after
    rename detection) already had a method of that name; overloads are paired so that a
    re-signatured overload counts as changed and only the surplus counts as new."""
    blank = {"sig_changed_fns": None, "sig_new_fns": None, "sig_params_added": None,
             "sig_params_removed": None, "sig_churn_share": None}
    try:
        ns = subprocess.run(["git", "-C", worktree, "diff", "--name-status", "-M",
                             prev_ref, cur_ref], capture_output=True, text=True,
                            timeout=60).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return blank
    changed = new = added = removed = 0
    for line in ns.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not prod(parts[-1]):
            continue
        status, old, path = parts[0], parts[1], parts[-1]
        cur = _sigs_at(worktree, cur_ref, path)
        prev = {} if status.startswith("A") else _sigs_at(worktree, prev_ref, old)
        for name, cs in cur.items():
            ps = list(prev.get(name, []))
            gone = [p for p in ps if p not in cs]
            came = [c for c in cs if c not in ps]
            pairs = min(len(gone), len(came))
            changed += pairs
            new += len(came) - pairs
            for p, c in zip(sorted(gone, key=len), sorted(came, key=len)):
                added += max(0, len(c) - len(p))
                removed += max(0, len(p) - len(c))
    return {
        "sig_changed_fns": changed,
        "sig_new_fns": new,
        "sig_params_added": added,
        "sig_params_removed": removed,
        "sig_churn_share": round(changed / (changed + new), 4) if changed + new else None,
    }


# ---------------------------------------------------------------------------
# implicit data reach: data a method gets WITHOUT a parameter
# ---------------------------------------------------------------------------

_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*$")


def data_reach(worktree: str, classes: list[dict], methods: list[dict],
               fields: list[dict], fns: list[dict], adj: dict) -> dict:
    """How much of a method's data arrives implicitly, through its class's fields,
    rather than explicitly as parameters.

    In a Spring service the data a new rule needs is mostly already in scope: the
    injected repositories and collaborators are instance fields, so a new method reaches
    them without any signature saying so. An OfficeFloor function declares everything as
    a parameter. The parameter measures above cannot see the first kind, so this counts
    it from CK's per-method field use (`field.csv`):

      reached  - fields a method uses directly or through methods of its own class it
                 calls (the Bieman & Kang closure; `call_adjacency` restricted to the
                 class). Constants by naming convention (ALL_CAPS) are not data.
      explicit - its parameters (CK `parametersQty`).
      ambient  - instance fields of its class (CK totalFieldsQty - staticFieldsQty),
                 whether used or not: what a new method there would have in scope.

    `dr_implicit_share` = sum(reached) / sum(reached + explicit) over all methods.
    `dr_field_span_*` = methods that reach one field: how many functions one piece of
    ambient data ties together. Constructors are left out (they set fields, they do not
    receive data through them). Blank when CK gave no methods."""
    from .placement import ck_key_map
    keys = ("dr_methods", "dr_explicit_mean", "dr_reached_mean", "dr_ambient_mean",
            "dr_implicit_share", "dr_field_span_max", "dr_field_span_mean",
            *(f"dr_implicit_share_{ro}" for ro in ROLES))
    out: dict = {k: None for k in keys}
    if not methods:
        return out
    use: dict = defaultdict(set)
    for f in fields:
        v = f.get("variable", "")
        if v and not _CONSTANT.match(v):
            use[(f.get("class", ""), f.get("method", ""))].add(v)
    ambient: dict = {}
    for c in classes:
        try:
            ambient[c.get("class", "")] = (int(float(c.get("totalFieldsQty") or 0))
                                           - int(float(c.get("staticFieldsQty") or 0)))
        except ValueError:
            pass
    key_of = ck_key_map(worktree, methods, fns)
    role = roles(worktree, fns)
    per_class: dict = defaultdict(list)
    for m in methods:
        per_class[m.get("class", "")].append(m)
    tot_reach = tot_expl = 0
    r_reach: dict = defaultdict(int)
    r_expl: dict = defaultdict(int)
    reach_n, expl_n, amb_n, n = [], [], [], 0
    span: dict = defaultdict(int)
    for cls, ms in per_class.items():
        ids = [(cls, m["method"]) for m in ms]
        node_to_id: dict = defaultdict(list)
        for i in ids:
            if i in key_of:
                node_to_id[key_of[i]].append(i)
        calls = {i: [c for callee in adj.get(key_of[i], ()) for c in node_to_id.get(callee, ())]
                 for i in ids if i in key_of}
        for m in ms:
            if m.get("constructor") == "true":
                continue
            i = (cls, m["method"])
            seen, stack, acc = {i}, [i], set()
            while stack:
                u = stack.pop()
                acc |= use.get(u, set())
                for c in calls.get(u, ()):
                    if c not in seen:
                        seen.add(c)
                        stack.append(c)
            try:
                expl = int(float(m.get("parametersQty") or 0))
            except ValueError:
                expl = 0
            ro = role.get(key_of.get(i), "other")
            n += 1
            tot_reach += len(acc)
            tot_expl += expl
            r_reach[ro] += len(acc)
            r_expl[ro] += expl
            reach_n.append(len(acc))
            expl_n.append(expl)
            amb_n.append(ambient.get(cls, 0))
            for v in acc:
                span[(cls, v)] += 1
    if not n:
        return out

    def r(x):
        return round(x, 4)
    out.update({
        "dr_methods": n,
        "dr_explicit_mean": r(sum(expl_n) / n),
        "dr_reached_mean": r(sum(reach_n) / n),
        "dr_ambient_mean": r(sum(amb_n) / n),
        "dr_implicit_share": r(tot_reach / (tot_reach + tot_expl)) if tot_reach + tot_expl else None,
        "dr_field_span_max": max(span.values(), default=0),
        "dr_field_span_mean": r(sum(span.values()) / len(span)) if span else None,
    })
    for ro in ROLES:
        d = r_reach[ro] + r_expl[ro]
        out[f"dr_implicit_share_{ro}"] = r(r_reach[ro] / d) if d else None
    return out


DATAFLOW_COLUMNS = [
    "df_params", "df_tramp_params", "df_tramp_ratio", "df_tramp_fn_share",
    "df_unused_params", "df_tramp_chain_max", "df_edges", "df_edge_carry_share",
    "df_edge_carry_mean", "df_edge_shared_share",
    "df_edge_shared_mean", "df_types", "df_type_span_max", "df_type_span_mean",
    "df_type_overlap_mean", "df_type_overlap_max", "df_data_clumps",
    "sig_changed_fns", "sig_new_fns", "sig_params_added", "sig_params_removed",
    "sig_churn_share",
    *(f"df_{m}_{ro}" for m in ("fns", "params", "tramp_ratio", "edge_carry_share")
      for ro in ROLES),
    "dr_methods", "dr_explicit_mean", "dr_reached_mean", "dr_ambient_mean",
    "dr_implicit_share", "dr_field_span_max", "dr_field_span_mean",
    *(f"dr_implicit_share_{ro}" for ro in ROLES),
]


def dataflow_all(worktree: str, fns: list[dict], adj: dict, prev_ref: Optional[str],
                 cur_ref: str, prod: callable) -> dict:
    out = dataflow_metrics(worktree, fns, adj)
    if prev_ref:
        out.update(signature_churn(worktree, prev_ref, cur_ref, prod))
    return out
