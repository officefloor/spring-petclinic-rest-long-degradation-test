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
# collaborators vs data
# ---------------------------------------------------------------------------
#
# Both frameworks detach COLLABORATORS (services, repositories, mappers) from the call
# graph: Spring injects them into fields, OfficeFloor passes them to `service` as
# parameters. Counting them as data would credit Spring's fields as "implicit data" and
# OfficeFloor's parameters as "data threaded". So every type is classed, the same way in
# both arms, from the source at the checkpoint:
#
#   collaborator - a class declared with a bean annotation (BEAN_ANNOTATIONS), an
#                  interface extending a Spring Data repository, every supertype of
#                  those (so ClinicService and OwnerRepository count through their
#                  @Service / @Repository implementations), and the framework services
#                  in FRAMEWORK_COLLABORATORS.
#   data         - everything else: entities, DTOs, ids, OfficeFloor's Out<T>/@Val values.
#
# A parameter or field is a collaborator when its OUTER type is (`ObjectResponse<X>` is
# the response facility; `Out<Owner>` and `List<Owner>` are data).

BEAN_ANNOTATIONS = frozenset(
    "Service Repository Component Controller RestController Mapper Configuration "
    "ControllerAdvice RestControllerAdvice".split())
SPRING_DATA_REPOS = frozenset(
    "Repository CrudRepository ListCrudRepository JpaRepository PagingAndSortingRepository "
    "ListPagingAndSortingRepository".split())
FRAMEWORK_COLLABORATORS = frozenset("""
    ServerHttpConnection ObjectResponse EntityManager JdbcTemplate NamedParameterJdbcTemplate
    JdbcClient DataSource ObjectMapper PasswordEncoder Clock ApplicationEventPublisher
    Validator ConversionService RestTemplate RestClient WebClient TransactionTemplate
    PlatformTransactionManager Environment MeterRegistry
""".split())
SOURCE_GLOB = "src/main/java/**/*.java"
_DECL = re.compile(
    r"((?:@[\w.]+(?:\s*\([^)]*\))?\s*)*)"
    r"(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*"
    r"\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)([^{;]*)\{")
_MODIFIERS = re.compile(
    r"\b(public|protected|private|static|final|transient|volatile)\b")


def _strip(text: str) -> str:
    return _STRIP.sub(lambda m: " " * len(m.group(0)), text)


def _sources(worktree: str) -> list[str]:
    out = []
    for path in sorted(glob.glob(os.path.join(worktree, SOURCE_GLOB), recursive=True)):
        try:
            out.append(_strip(open(path, encoding="utf-8", errors="replace").read()))
        except OSError:
            pass
    return out


def _no_generics(s: str) -> str:
    prev = None
    while prev != s:
        prev, s = s, re.sub(r"<[^<>]*>", "", s)
    return s


def type_head(typ: str) -> str:
    """The outer type's simple name: `java.util.List<Owner>` -> List, `Owner[]` -> Owner."""
    t = _no_generics(typ).replace("...", "").replace("[]", "").strip()
    return t.split(".")[-1]


def collaborator_types(worktree: str, sources: Optional[list[str]] = None) -> set[str]:
    """Simple names of the collaborator types at this checkpoint (see above)."""
    supers: dict = defaultdict(set)
    seeds: set = set()
    for text in sources if sources is not None else _sources(worktree):
        for m in _DECL.finditer(text):
            annots = {a.split(".")[-1] for a in re.findall(r"@([\w.]+)", m.group(1))}
            name, header = m.group(3), _no_generics(m.group(4))
            sup = set()
            for part in re.split(r"\b(?:extends|implements|permits)\b", header)[1:]:
                sup |= {w.strip().split(".")[-1] for w in part.split(",") if w.strip()}
            sup = {w for w in sup if re.fullmatch(r"[A-Za-z_$][\w$]*", w)}
            supers[name] |= sup
            if annots & BEAN_ANNOTATIONS or sup & SPRING_DATA_REPOS:
                seeds.add(name)
    out, stack = set(seeds), list(seeds)
    while stack:
        for s in supers.get(stack.pop(), ()):
            if s not in out:
                out.add(s)
                stack.append(s)
    return out | FRAMEWORK_COLLABORATORS


def field_types(worktree: str, sources: Optional[list[str]] = None) -> dict:
    """Top-level class simple name -> {instance field name: outer type}. Fields of nested
    classes are not read (their fields count as data downstream)."""
    out: dict = {}
    for text in sources if sources is not None else _sources(worktree):
        m = _DECL.search(text)
        if not m:
            continue
        cls, body = m.group(3), text[m.end():]
        fields: dict = {}
        depth, seg, init = 0, [], False
        for ch in body:
            if ch == "{":
                if depth == 0:
                    # an initializer (`= { ... }`, `= new X() {`), not an annotation's `=`
                    init = "=" in _ANNOT.sub(" ", "".join(seg))
                depth += 1
                continue
            if ch == "}":
                if depth == 0:
                    break
                depth -= 1
                if depth == 0 and not init:
                    seg = []                     # a method, nested class or init block ended
                continue
            if depth:
                continue
            if ch != ";":
                seg.append(ch)
                continue
            decl, seg, init = "".join(seg), [], False
            decl = _ANNOT.sub(" ", decl).split("=", 1)[0]
            if "(" in decl or re.search(r"\bstatic\b", decl):
                continue
            decl = _MODIFIERS.sub(" ", decl).strip()
            parts = _split_top(decl)
            if not parts:
                continue
            first = re.match(r"(.*?)\s*([A-Za-z_$][\w$]*)\s*$", parts[0].strip(), re.S)
            if not first or not first.group(1).strip():
                continue
            typ = type_head(first.group(1))
            fields[first.group(2)] = typ
            for extra in parts[1:]:
                n = extra.split("=", 1)[0].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", n):
                    fields[n] = typ
        out[cls] = fields
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


def _type_travel(by_key: dict, dom: dict, edges: list) -> tuple[list, list]:
    """Per domain type: the largest connected piece of the call subgraph of the
    functions taking it (spans), and the Jaccard overlap of the types' edge sets."""
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
    return spans, jac


def dataflow_metrics(worktree: str, fns: list[dict], adj: dict,
                     collab: Optional[set] = None) -> dict:
    """Tramp data, type co-travel and data clumps over one checkpoint, over all
    parameters (`df_*`) and again split into data (`dfdata_*`) and collaborator
    (`dfcol_*`) parameters (see `collaborator_types`).

    `fns` must have been through metrics._call_index (each carries `_key`), and `adj`
    is metrics.call_adjacency over the same records."""
    if collab is None:
        collab = collaborator_types(worktree)
    cache: dict = {}
    by_key = {f["_key"]: f for f in fns if "_key" in f}
    role = roles(worktree, fns)
    r_params: dict = defaultdict(int)
    r_tramp: dict = defaultdict(int)
    rd_params: dict = defaultdict(int)
    rd_tramp: dict = defaultdict(int)
    sig: dict = {}                      # key -> [(name, type)]
    dom: dict = {}                      # key -> domain types across all params
    dom_d: dict = {}                    # key -> domain types across data params
    tramp_types: dict = {}              # key -> set of full types that are tramp here
    passes: dict = {}                   # key -> {callee name: parameters passed to it}
    passes_d: dict = {}                 # the same, data parameters only
    passes_c: dict = {}                 # the same, collaborator parameters only
    n_params = n_tramp = n_unused = n_with = n_tramp_fns = 0
    nd = nd_tramp = nc = nc_tramp = 0
    for k, f in by_key.items():
        ps = params(f["long_name"])
        sig[k] = ps
        is_c = {n: type_head(t) in collab for n, t in ps}
        dom[k] = set().union(*(domain_types(t) for _, t in ps)) if ps else set()
        dom_d[k] = set().union(*(domain_types(t) for n, t in ps if not is_c[n])) if ps else set()
        if not ps:
            continue
        flow = param_flow(_source(worktree, f, cache), f["long_name"])
        cls = {n: kind for n, (kind, _c) in flow.items()}
        cnt: dict = defaultdict(int)
        cnt_d: dict = defaultdict(int)
        cnt_c: dict = defaultdict(int)
        for n, (_k, callees) in flow.items():
            for c in callees:
                cnt[c] += 1
                (cnt_c if is_c.get(n) else cnt_d)[c] += 1
        passes[k], passes_d[k], passes_c[k] = cnt, cnt_d, cnt_c
        n_with += 1
        n_params += len(ps)
        t = {typ for name, typ in ps if cls.get(name) == "tramp"}
        tramps = sum(1 for v in cls.values() if v == "tramp")
        n_tramp += tramps
        ro = role.get(k, "other")
        r_params[ro] += len(ps)
        r_tramp[ro] += tramps
        n_unused += sum(1 for v in cls.values() if v == "unused")
        for n, _t in ps:
            if is_c[n]:
                nc += 1
                nc_tramp += cls.get(n) == "tramp"
            else:
                nd += 1
                nd_tramp += cls.get(n) == "tramp"
                rd_params[ro] += 1
                rd_tramp[ro] += cls.get(n) == "tramp"
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
    chains = {(k, t): depth(k, t, {(k, t)}) for k, ts in tramp_types.items() for t in ts}
    chain_max = max(chains.values(), default=0)
    chain_max_d = max((v for (_k, t), v in chains.items() if type_head(t) not in collab),
                      default=0)

    # type co-travel on call edges
    edges = [(a, b) for a, bs in adj.items() for b in bs if a != b and a in by_key and b in by_key]
    shared = [len(dom[a] & dom[b]) for a, b in edges]

    def carried_by(p):
        # an edge CARRIES data when the caller passes one of its own parameters to the callee
        return [p.get(a, {}).get(by_key[b].get("_meth", ""), 0) for a, b in edges]
    carried, carried_d, carried_c = carried_by(passes), carried_by(passes_d), carried_by(passes_c)
    spans, jac = _type_travel(by_key, dom, edges)
    spans_d, jac_d = _type_travel(by_key, dom_d, edges)
    n_types = len(set().union(*dom.values())) if dom else 0

    # data clumps: >=3 (name, type) parameters shared by >=2 signatures
    def clumps(sigs):
        psets = [frozenset(ps) for ps in sigs if len(ps) >= 3]
        return len({a & b for a, b in combinations(psets, 2) if len(a & b) >= 3})
    n_clumps = clumps(sig.values())
    n_clumps_d = clumps([[(n, t) for n, t in ps if type_head(t) not in collab]
                         for ps in sig.values()])

    def r(x, n=4):
        return None if x is None else round(x, n)

    def share(xs):
        return r(sum(1 for c in xs if c) / len(xs)) if xs else None

    def mean(xs):
        return r(sum(xs) / len(xs)) if xs else None
    split = {}
    for ro in ROLES:
        ce = [c for (a, _b), c in zip(edges, carried) if role.get(a, "other") == ro]
        split[f"df_fns_{ro}"] = sum(1 for k in by_key if role.get(k, "other") == ro)
        split[f"df_params_{ro}"] = r_params[ro]
        split[f"df_tramp_ratio_{ro}"] = r(r_tramp[ro] / r_params[ro]) if r_params[ro] else None
        split[f"df_edge_carry_share_{ro}"] = share(ce)
        split[f"dfdata_tramp_ratio_{ro}"] = (r(rd_tramp[ro] / rd_params[ro])
                                             if rd_params[ro] else None)
    return split | {
        "df_params": n_params,
        "df_tramp_params": n_tramp,
        "df_tramp_ratio": r(n_tramp / n_params) if n_params else None,
        "df_tramp_fn_share": r(n_tramp_fns / n_with) if n_with else None,
        "df_unused_params": n_unused,
        "df_tramp_chain_max": chain_max,
        "df_edges": len(edges),
        "df_edge_carry_share": share(carried),
        "df_edge_carry_mean": mean(carried),
        "df_edge_shared_share": share(shared),
        "df_edge_shared_mean": mean(shared),
        "df_types": n_types,
        "df_type_span_max": max(spans, default=None),
        "df_type_span_mean": mean(spans),
        "df_type_overlap_mean": mean(jac),
        "df_type_overlap_max": r(max(jac)) if jac else None,
        "df_data_clumps": n_clumps,
        # data vs collaborator parameters
        "df_collab_types": len(collab - FRAMEWORK_COLLABORATORS),
        "dfdata_params": nd,
        "dfcol_params": nc,
        "dfdata_tramp_ratio": r(nd_tramp / nd) if nd else None,
        "dfcol_tramp_ratio": r(nc_tramp / nc) if nc else None,
        "dfdata_tramp_chain_max": chain_max_d,
        "dfdata_edge_carry_share": share(carried_d),
        "dfdata_edge_carry_mean": mean(carried_d),
        "dfcol_edge_carry_share": share(carried_c),
        "dfdata_type_span_max": max(spans_d, default=None),
        "dfdata_type_span_mean": mean(spans_d),
        "dfdata_type_overlap_mean": mean(jac_d),
        "dfdata_clumps": n_clumps_d,
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


# JDT modifier flags, as CK reports them in method.csv
_ABSTRACT, _BODY_IN_INTERFACE = 0x400, 0x2 | 0x8 | 0x10000     # private, static, default


def _bodyless(m: dict, class_type: str) -> bool:
    """An abstract method, or an interface method that is not default/static/private:
    it has no body, so no data reaches it."""
    try:
        mods = int(m.get("modifiers") or 0)
    except ValueError:
        mods = 0
    return bool(mods & _ABSTRACT) or (class_type == "interface"
                                      and not mods & _BODY_IN_INTERFACE)


DR_COLUMNS = (
    "dr_methods", "dr_explicit_mean", "dr_reached_mean", "dr_ambient_mean",
    "dr_implicit_share", "dr_field_span_max", "dr_field_span_mean",
    *(f"dr_implicit_share_{ro}" for ro in ROLES),
    "drdata_implicit_share", *(f"drdata_implicit_share_{ro}" for ro in ROLES),
    "drdata_reached_mean", "drcol_reached_mean",
    "drdata_field_span_max", "drcol_field_span_max",
    "dep_scope_mean", "dep_used_mean", "dep_surplus_mean", "dep_surplus_share",
    *(f"dep_surplus_share_{ro}" for ro in ROLES),
)


def data_reach(worktree: str, classes: list[dict], methods: list[dict],
               fields: list[dict], fns: list[dict], adj: dict,
               collab: Optional[set] = None) -> dict:
    """How much of a method's data arrives implicitly, through its class's fields,
    rather than explicitly as parameters; and how many collaborators a method has in
    scope that it does not use.

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
    receive data through them), and so are methods without a body (abstract and
    interface methods). Blank when CK gave no methods.

    DATA vs COLLABORATORS (see `collaborator_types`). Both frameworks inject
    collaborators; they differ in SCOPE. Spring injects per class, so every method has
    all of its class's collaborators in scope; OfficeFloor injects per function, so a
    function has exactly the ones it declares. Each field is classed by its declared
    type (`field_types`) and each parameter by its type (lizard's signature, through
    `ck_key_map`; a method CK lists but lizard does not counts its parameters as data):

      drdata_* / drcol_* - the reach measures over data fields and parameters only, and
                 collaborator fields reached.
      dep_scope    - collaborators in scope: the class's collaborator-typed instance
                     fields plus collaborator parameters.
      dep_used     - those reached (fields, by the closure above) or referenced
                     (parameters: read or handed on).
      dep_surplus  - scope - used: collaborators a method could reach but does not.
                     `dep_surplus_share` = sum(surplus) / sum(scope)."""
    from .placement import ck_key_map
    out: dict = {k: None for k in DR_COLUMNS}
    if not methods:
        return out
    srcs = _sources(worktree)
    if collab is None:
        collab = collaborator_types(worktree, srcs)
    ftypes = field_types(worktree, srcs)
    use: dict = defaultdict(set)
    for f in fields:
        v = f.get("variable", "")
        if v and not _CONSTANT.match(v):
            use[(f.get("class", ""), f.get("method", ""))].add(v)
    ambient: dict = {}
    kind = {c.get("class", ""): c.get("type", "") for c in classes}
    for c in classes:
        try:
            ambient[c.get("class", "")] = (int(float(c.get("totalFieldsQty") or 0))
                                           - int(float(c.get("staticFieldsQty") or 0)))
        except ValueError:
            pass
    key_of = ck_key_map(worktree, methods, fns)
    by_key = {f["_key"]: f for f in fns if "_key" in f}
    role = roles(worktree, fns)
    cache: dict = {}
    per_class: dict = defaultdict(list)
    for m in methods:
        per_class[m.get("class", "")].append(m)
    tot_reach = tot_expl = 0
    r_reach: dict = defaultdict(int)
    r_expl: dict = defaultdict(int)
    d_reach: dict = defaultdict(int)       # role -> data fields reached
    d_expl: dict = defaultdict(int)        # role -> data parameters
    sc: dict = defaultdict(int)            # role -> collaborators in scope
    su: dict = defaultdict(int)            # role -> collaborator surplus
    reach_n, expl_n, amb_n, n = [], [], [], 0
    reach_d_n, reach_c_n, scope_n, used_n = [], [], [], []
    span: dict = defaultdict(int)
    for cls, ms in per_class.items():
        simple = cls.split(".")[-1].split("$")[-1]
        ft = ftypes.get(simple, {}) if "$" not in cls else {}
        col_fields = {v for v, t in ft.items() if t in collab}
        ids = [(cls, m["method"]) for m in ms]
        node_to_id: dict = defaultdict(list)
        for i in ids:
            if i in key_of:
                node_to_id[key_of[i]].append(i)
        calls = {i: [c for callee in adj.get(key_of[i], ()) for c in node_to_id.get(callee, ())]
                 for i in ids if i in key_of}
        for m in ms:
            if m.get("constructor") == "true" or _bodyless(m, kind.get(cls, "")):
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
            fn = by_key.get(key_of.get(i))
            if fn is not None:
                ps = params(fn["long_name"])
                cps = [nm for nm, t in ps if type_head(t) in collab]
                flow = param_flow(_source(worktree, fn, cache), fn["long_name"]) if cps else {}
                c_used = sum(1 for nm in cps if flow.get(nm, ("used",))[0] != "unused")
                expl_d = len(ps) - len(cps)
            else:
                cps, c_used, expl_d = [], 0, expl
            acc_c = acc & col_fields
            acc_d = acc - col_fields
            ro = role.get(key_of.get(i), "other")
            scope = len(col_fields) + len(cps)
            used = len(acc_c) + c_used
            n += 1
            tot_reach += len(acc)
            tot_expl += expl
            r_reach[ro] += len(acc)
            r_expl[ro] += expl
            d_reach[ro] += len(acc_d)
            d_expl[ro] += expl_d
            sc[ro] += scope
            su[ro] += scope - used
            reach_n.append(len(acc))
            expl_n.append(expl)
            amb_n.append(ambient.get(cls, 0))
            reach_d_n.append(len(acc_d))
            reach_c_n.append(len(acc_c))
            scope_n.append(scope)
            used_n.append(used)
            for v in acc:
                span[(cls, v)] += 1
    if not n:
        return out

    def r(x):
        return round(x, 4)

    def ratio(a, b):
        return r(a / b) if b else None
    spans_c = {k: v for k, v in span.items()
               if k[1] in {f for f, t in ftypes.get(k[0].split(".")[-1], {}).items()
                           if t in collab} and "$" not in k[0]}
    spans_d = {k: v for k, v in span.items() if k not in spans_c}
    dr, de = sum(d_reach.values()), sum(d_expl.values())
    out.update({
        "dr_methods": n,
        "dr_explicit_mean": r(sum(expl_n) / n),
        "dr_reached_mean": r(sum(reach_n) / n),
        "dr_ambient_mean": r(sum(amb_n) / n),
        "dr_implicit_share": ratio(tot_reach, tot_reach + tot_expl),
        "dr_field_span_max": max(span.values(), default=0),
        "dr_field_span_mean": r(sum(span.values()) / len(span)) if span else None,
        "drdata_implicit_share": ratio(dr, dr + de),
        "drdata_reached_mean": r(sum(reach_d_n) / n),
        "drcol_reached_mean": r(sum(reach_c_n) / n),
        "drdata_field_span_max": max(spans_d.values(), default=0),
        "drcol_field_span_max": max(spans_c.values(), default=0),
        "dep_scope_mean": r(sum(scope_n) / n),
        "dep_used_mean": r(sum(used_n) / n),
        "dep_surplus_mean": r((sum(scope_n) - sum(used_n)) / n),
        "dep_surplus_share": ratio(sum(scope_n) - sum(used_n), sum(scope_n)),
    })
    for ro in ROLES:
        out[f"dr_implicit_share_{ro}"] = ratio(r_reach[ro], r_reach[ro] + r_expl[ro])
        out[f"drdata_implicit_share_{ro}"] = ratio(d_reach[ro], d_reach[ro] + d_expl[ro])
        out[f"dep_surplus_share_{ro}"] = ratio(su[ro], sc[ro])
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
    "df_collab_types", "dfdata_params", "dfcol_params", "dfdata_tramp_ratio",
    "dfcol_tramp_ratio", "dfdata_tramp_chain_max", "dfdata_edge_carry_share",
    "dfdata_edge_carry_mean", "dfcol_edge_carry_share", "dfdata_type_span_max",
    "dfdata_type_span_mean", "dfdata_type_overlap_mean", "dfdata_clumps",
    *(f"dfdata_tramp_ratio_{ro}" for ro in ROLES),
    *DR_COLUMNS,
]


def dataflow_all(worktree: str, fns: list[dict], adj: dict, prev_ref: Optional[str],
                 cur_ref: str, prod: callable) -> dict:
    out = dataflow_metrics(worktree, fns, adj)
    if prev_ref:
        out.update(signature_churn(worktree, prev_ref, cur_ref, prod))
    return out
