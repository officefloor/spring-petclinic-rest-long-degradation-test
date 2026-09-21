"""Placement metrics: where complexity sits, as distinct from how much there is.

WHY THIS MODULE EXISTS
----------------------
The experiment's thesis is NOT that one architecture is simpler. Measured four
ways (cyclomatic, cognitive, NPath, Halstead volume) the two arms carry the same
total — which is Tesler's conservation-of-complexity, and the single most
important NEGATIVE result the run produces. What differs is *placement*: whether
that fixed quantity is packed into a few large units or spread over many small
ones, and whether change activity keeps returning to the same places.

Everything here is therefore a DISTRIBUTION or LOCATION statistic over a quantity
measured elsewhere, and every one of them is a published measure or a textbook
concentration index — deliberately, because the bespoke `impact_*` score cannot
be used as evidence for a claim about the very phenomenon it was fitted to.
Sources are named per function.

All of it is pure-derive: computed from a materialised checkpoint worktree plus
git history, so `analyze --recompute` regenerates it for historical runs with no
agent involvement.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Concentration indices (textbook; no software-metric provenance needed)
# ---------------------------------------------------------------------------


def gini(values: Iterable[float]) -> Optional[float]:
    """Gini coefficient of inequality (Gini 1912), 0 = perfectly even.

    SCALE-FREE: it describes the SHAPE of the distribution and is insensitive to
    how many units it is spread over. That makes it the honest companion to `hhi`
    and `top_share` below, which are NOT scale-free: an arm that splits its code
    into 2.7x as many files scores better on those by construction. Publishing
    Gini beside them is what stops the file-count confound being used against a
    concentration claim -- if Gini is equal and HHI is not, the correct statement
    is 'the units are larger', not 'the distribution is more unequal'.
    """
    xs = sorted(x for x in values if x > 0)
    n = len(xs)
    if n < 2:
        return None
    total = sum(xs)
    if total <= 0:
        return None
    cum = sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1))
    return round(cum / (n * total), 4)


def hhi(values: Iterable[float]) -> Optional[float]:
    """Herfindahl-Hirschman index: sum of squared shares. 1/n = perfectly even,
    1 = everything in one unit. Standard concentration measure (Hirschman 1945)."""
    xs = [x for x in values if x > 0]
    total = sum(xs)
    if not xs or total <= 0:
        return None
    return round(sum((x / total) ** 2 for x in xs), 6)


def top_share(values: Iterable[float], k: int) -> Optional[float]:
    """Share of the total held by the heaviest k units (concentration ratio CRk)."""
    xs = [x for x in values if x > 0]
    total = sum(xs)
    if not xs or total <= 0:
        return None
    return round(sum(sorted(xs, reverse=True)[:k]) / total, 4)


def norm_entropy(values: Iterable[float]) -> Optional[float]:
    """Shannon entropy of the share distribution, normalised by log(n).

    1.0 = the quantity is spread perfectly evenly; low = concentrated. Normalising
    by log(n) is what makes it comparable between arms with different unit counts
    (it is the same normalisation Hassan 2009 uses for change entropy)."""
    xs = [x for x in values if x > 0]
    total = sum(xs)
    if len(xs) < 2 or total <= 0:
        return None
    h = -sum((x / total) * math.log(x / total) for x in xs)
    return round(h / math.log(len(xs)), 4)



def lorenz_points(values: Iterable[float], steps: int = 10) -> Optional[str]:
    """Cumulative share of the total held by the poorest i/steps of units.

    LINEARLY INTERPOLATED between unit boundaries, not cut at integer indices. With
    integer cuts a perfectly EQUAL distribution of 5 files does not come back as the
    straight line it is -- the curve wobbles purely from where the rounding lands,
    which would read as inequality that is not there. Interpolation makes the curve
    exact at every unit boundary and honest between them.
    """
    xs = sorted(x for x in values if x > 0)
    n = len(xs)
    total = sum(xs)
    if n < 2 or total <= 0:
        return None
    cum = [0.0]
    acc = 0.0
    for x in xs:
        acc += x
        cum.append(acc / total)                       # share after k units, k = 0..n
    out = []
    for i in range(steps + 1):
        pos = n * i / steps                           # fractional unit position
        lo = int(pos)
        if lo >= n:
            out.append(1.0)
            continue
        frac = pos - lo
        out.append(cum[lo] + frac * (cum[lo + 1] - cum[lo]))
    return ",".join(f"{v:.5g}" for v in out)


def distribution_block(values: list[float], prefix: str) -> dict:
    """The full concentration panel for one quantity, as flat CSV fields."""
    return {
        f"{prefix}_gini": gini(values),
        f"{prefix}_hhi": hhi(values),
        f"{prefix}_top1": top_share(values, 1),
        f"{prefix}_top5": top_share(values, 5),
        f"{prefix}_hnorm": norm_entropy(values),
        f"{prefix}_n": len([v for v in values if v > 0]) or None,
    }


# ---------------------------------------------------------------------------
# Amount, and its distribution over units (Tesler's conserved quantity)
# ---------------------------------------------------------------------------


def _package_of(rel_path: str) -> str:
    """Java package from the file path (directory), which is what `package` declares."""
    return os.path.dirname(rel_path)


def complexity_placement(fns: list[dict]) -> dict:
    """Total cyclomatic complexity and how it distributes over functions/files/packages.

    `total_cc` is the conservation quantity: if the arms agree here while the
    distribution blocks disagree, that is the whole thesis in two numbers.
    """
    if not fns:
        return {"total_cc": None, "total_fns": None, "total_files": None, "total_packages": None}
    per_fn = [float(f["cc"]) for f in fns]
    by_file: dict[str, float] = defaultdict(float)
    by_pkg: dict[str, float] = defaultdict(float)
    for f in fns:
        by_file[f["file"]] += float(f["cc"])
        by_pkg[_package_of(f["file"])] += float(f["cc"])
    row = {
        "total_cc": round(sum(per_fn), 2),
        "total_fns": len(fns),
        "total_files": len(by_file),
        "total_packages": len(by_pkg),
    }
    row.update(distribution_block(per_fn, "ccdist_fn"))
    file_cc = list(by_file.values())
    row.update(distribution_block(file_cc, "ccdist_file"))
    # Lorenz points for the FILE distribution: cumulative share of total CC held by
    # the poorest 10%, 20% ... of files. Eleven numbers is enough to draw the exact
    # curve, which is the canonical way to SHOW a Gini -- and the display that makes
    # the file-count confound visible, since two curves of similar shape drawn over
    # very different numbers of files is precisely the finding.
    row["ccdist_file_lorenz"] = lorenz_points(file_cc)
    row.update(distribution_block(list(by_pkg.values()), "ccdist_pkg"))
    return row


# ---------------------------------------------------------------------------
# Halstead (1977) and the Maintainability Index (Coleman et al. 1994)
# ---------------------------------------------------------------------------

_JAVA_KEYWORD_OPERATORS = {
    "if", "else", "while", "for", "do", "switch", "case", "default", "break",
    "continue", "return", "new", "throw", "throws", "try", "catch", "finally",
    "instanceof", "synchronized", "assert", "yield",
}
_JAVA_DECL_KEYWORDS = {
    "class", "interface", "enum", "record", "extends", "implements", "package",
    "import", "public", "private", "protected", "static", "final", "abstract",
    "native", "transient", "volatile", "strictfp", "sealed", "permits", "var",
    "void", "int", "long", "short", "byte", "char", "float", "double", "boolean",
    "this", "super", "null", "true", "false",
}
_OP_SYMBOLS = re.compile(
    r">>>=|<<=|>>=|>>>|\.\.\.|->|::|\+\+|--|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>"
    r"|[+\-*/%=<>!&|^~?:;,.\[\]{}()@]")
_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"0[xXbB][0-9a-fA-F_]+[lLfFdD]?|\d[\d_]*\.?[\d_]*([eE][+-]?\d+)?[lLfFdD]?")
_STRIP = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)


def halstead(source: str) -> dict:
    """Halstead (1977) vocabulary/volume/difficulty/effort for one Java source text.

    A deliberately conventional tokenisation: symbolic operators plus the control-flow
    KEYWORDS are operators; identifiers, literals and type keywords are operands.
    String and char literals are replaced by a single placeholder operand before
    tokenising, so an arm cannot move its Halstead score by changing message text.

    Halstead measures the SIZE OF THE VOCABULARY a reader must hold, which is an
    entirely different construct from control flow. It is here so the conservation
    claim does not rest on cyclomatic complexity alone -- if CC, cognitive, NPath
    and Halstead all agree the arms carry the same amount, that is four independent
    operationalisations, not one measure repeated.
    """
    literals = 0

    def _sub(m: re.Match) -> str:
        nonlocal literals
        t = m.group(0)
        if t.startswith(("//", "/*")):
            return " "
        literals += 1
        return " \x00LIT\x00 "

    text = _STRIP.sub(_sub, source)
    ops: Counter = Counter()
    operands: Counter = Counter()
    operands["\x00LIT\x00"] = literals
    pos, n = 0, len(text)
    while pos < n:
        ch = text[pos]
        if ch.isspace():
            pos += 1
            continue
        m = _IDENT.match(text, pos)
        if m:
            word = m.group(0)
            if word == "\x00LIT\x00":
                pass                                  # already counted
            elif word in _JAVA_KEYWORD_OPERATORS:
                ops[word] += 1
            else:
                operands[word] += 1                   # identifiers AND type keywords
            pos = m.end()
            continue
        m = _NUMBER.match(text, pos)
        if m:
            operands[m.group(0)] += 1
            pos = m.end()
            continue
        m = _OP_SYMBOLS.match(text, pos)
        if m:
            ops[m.group(0)] += 1
            pos = m.end()
            continue
        pos += 1
    n1, n2 = len(ops), len([k for k, v in operands.items() if v])
    N1, N2 = sum(ops.values()), sum(operands.values())
    vocab, length = n1 + n2, N1 + N2
    if vocab <= 0 or length <= 0:
        return {"n1": 0, "n2": 0, "N1": 0, "N2": 0, "volume": 0.0,
                "difficulty": 0.0, "effort": 0.0}
    volume = length * math.log2(vocab)
    difficulty = (n1 / 2) * (N2 / n2) if n2 else 0.0
    return {"n1": n1, "n2": n2, "N1": N1, "N2": N2,
            "volume": volume, "difficulty": difficulty, "effort": difficulty * volume}


def maintainability_index(volume: float, cc: float, loc: float) -> Optional[float]:
    """Coleman et al. (1994) MI, in the SEI/Visual-Studio 0-100 rescaling.

    MI = max(0, (171 - 5.2 ln(V) - 0.23 CC - 16.2 ln(LOC)) * 100/171)

    Included because it is the composite a reviewer expects to see and because it
    combines all three families (Halstead volume, control flow, size) -- so it is a
    useful single check on whether the arms' aggregate 'maintainability' differs at
    all before any placement argument is made. It is a whole-codebase average and
    is therefore location-blind BY CONSTRUCTION: it cannot see concentration, which
    is precisely why it must not be used as the thesis statistic.
    """
    if volume <= 0 or loc <= 0:
        return None
    mi = (171.0 - 5.2 * math.log(volume) - 0.23 * cc - 16.2 * math.log(loc)) * 100.0 / 171.0
    return round(max(0.0, mi), 3)


def halstead_placement(worktree: str, fns: list[dict]) -> dict:
    """Whole-arm Halstead totals, and the Maintainability Index computed PER FILE.

    MI is computed per file and then averaged (the SEI / Visual-Studio practice),
    never over whole-codebase totals: fed a 680-CC total it saturates the 0 floor
    for both arms and silently reports nothing. Per file it stays in range and is
    comparable. `mi_min` is the worst file, which is the only part of MI that can
    see concentration at all.
    """
    by_file: dict[str, list[dict]] = {}
    for f in fns:
        by_file.setdefault(f["file"], []).append(f)
    vols: list[float] = []
    mis: list[float] = []
    agg = {"n1": 0, "n2": 0, "N1": 0, "N2": 0, "volume": 0.0, "effort": 0.0}
    for rel, group in by_file.items():
        try:
            with open(os.path.join(worktree, rel), encoding="utf-8", errors="replace") as fh:
                h = halstead(fh.read())
        except OSError:
            continue
        vols.append(h["volume"])
        for k in ("n1", "n2", "N1", "N2", "volume", "effort"):
            agg[k] += h[k]
        file_loc = sum(float(g["nloc"]) for g in group)
        mean_cc = sum(float(g["cc"]) for g in group) / len(group)
        mi = maintainability_index(h["volume"], mean_cc, file_loc)
        if mi is not None:
            mis.append(mi)
    if not vols:
        return {"halstead_volume": None, "halstead_effort": None,
                "halstead_vocab": None, "mi_mean": None, "mi_min": None}
    row = {
        "halstead_volume": round(agg["volume"], 1),
        "halstead_effort": round(agg["effort"], 1),
        "halstead_vocab": agg["n1"] + agg["n2"],
        "mi_mean": round(sum(mis) / len(mis), 3) if mis else None,
        "mi_min": round(min(mis), 3) if mis else None,
    }
    row.update(distribution_block(vols, "voldist_file"))
    return row


# ---------------------------------------------------------------------------
# Indirection and propagation (the Brooks 'accidental complexity' tax)
# ---------------------------------------------------------------------------


def indirection_stats(roots: list[dict], adj: dict) -> dict:
    """How many call hops separate the endpoint from the code that does the work.

    THE OBJECTION THIS ANSWERS. A pipeline architecture can always claim a small
    entry function; the sceptic's reply is 'you did not remove the complexity, you
    buried it behind indirection'. Depth is that objection made numeric: BFS from
    the handling node(s) and report the median and maximum hop count to reach a
    method, plus the fraction of reachable methods more than 2 hops away.

    A HIGH number is a cost, not a win -- this metric is expected to favour the
    NON-pipeline arm, and is included so the tax is reported rather than discovered
    by a referee.

    IT UNDERSTATES A PIPELINE ARM, AND MUST BE PUBLISHED SAYING SO. Depth is measured
    from the handling NODES, so a pipeline's ~20 wired steps are all depth 0 while a
    single-handler arm has exactly one depth-0 method -- the same 1-node/N-node
    asymmetry that `node_cc_median` carries. Worse, a pipeline's hops between steps are
    declared in YAML and dispatched by the container, so they are not Java calls and do
    not appear here AT ALL. The honest reading of a pipeline arm's indirection is this
    depth PLUS `node_count` (its pipeline length); quoting this column alone would let
    the arm with the most indirection report the least.
    """
    if not roots or not adj:
        return {"indirection_median": None, "indirection_max": None,
                "indirection_deep_share": None, "indirection_reached": None}
    depth: dict[tuple[str, str], int] = {}
    frontier = [(r["_cls"], r["_meth"]) for r in roots]
    for k in frontier:
        depth[k] = 0
    while frontier:
        nxt = []
        for key in frontier:
            for callee in adj.get(key, ()):
                if callee not in depth:
                    depth[callee] = depth[key] + 1
                    nxt.append(callee)
        frontier = nxt
    ds = sorted(depth.values())
    if not ds:
        return {"indirection_median": None, "indirection_max": None,
                "indirection_deep_share": None, "indirection_reached": None}
    mid = len(ds) // 2
    median = float(ds[mid]) if len(ds) % 2 else (ds[mid - 1] + ds[mid]) / 2
    return {
        "indirection_median": round(median, 2),
        "indirection_max": ds[-1],
        "indirection_deep_share": round(sum(1 for d in ds if d > 2) / len(ds), 4),
        "indirection_reached": len(ds),
    }


def propagation_cost(fns: list[dict], adj: dict) -> dict:
    """MacCormack, Rusnak & Baldwin (2006) propagation cost over the FILE graph.

    Density of the transitive closure of the file-level dependency matrix: the
    expected fraction of the system reachable from a randomly chosen file, i.e.
    how far a change propagates. Lower = better modularised.

    TWO CAVEATS, both load-bearing, both to be published with the number:
      1. The n^2 denominator means an arm that splits the same code over more files
         scores lower for free. `propagation_fanout_median` / `_max` are the raw
         reachable-file counts and are NOT normalised, so they show whether the
         dependency structure really differs or only the packaging does.
      2. It inherits `call_adjacency`'s conservative resolution, which drops every
         call it cannot prove. MacCormack reports 10-60% for real systems; values
         an order of magnitude below that mean edges are missing, not that the
         design is exceptional. Read it as a BETWEEN-ARM comparison only.
    """
    files = sorted({f["file"] for f in fns})
    if not files:
        return {"propagation_cost": None, "propagation_fanout_median": None,
                "propagation_fanout_max": None, "propagation_files": None}
    idx = {f: i for i, f in enumerate(files)}
    file_of = {(f["_cls"], f["_meth"]): f["file"] for f in fns if "_cls" in f}
    n = len(files)
    fadj: list[set[int]] = [set() for _ in range(n)]
    for src_key, callees in adj.items():
        sf = file_of.get(src_key)
        if sf is None:
            continue
        s = idx[sf]
        for ck in callees:
            cf = file_of.get(ck)
            if cf is not None and idx[cf] != s:
                fadj[s].add(idx[cf])
    reach_counts = []
    total = 0
    for s in range(n):
        seen = {s}
        stack = [s]
        while stack:
            u = stack.pop()
            for v in fadj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        r = len(seen) - 1
        total += r
        reach_counts.append(r)
    reach_counts.sort()
    mid = n // 2
    median = float(reach_counts[mid]) if n % 2 else (reach_counts[mid - 1] + reach_counts[mid]) / 2
    return {
        "propagation_cost": round(total / (n * n), 6),
        "propagation_fanout_median": round(median, 2),
        "propagation_fanout_max": reach_counts[-1],
        "propagation_files": n,
    }


# ---------------------------------------------------------------------------
# Change-based placement (Hassan 2009) and framework-dispatch accounting
# ---------------------------------------------------------------------------



def _numstat(worktree: str, a: str, b: str, pathspec: str = "src/main") -> dict[str, int]:
    """file -> lines changed (added+removed) between two refs."""
    try:
        out = subprocess.run(["git", "-C", worktree, "diff", "--numstat", a, b, "--", pathspec],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    acc: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            acc[parts[2]] = acc.get(parts[2], 0) + int(parts[0]) + int(parts[1])
    return acc


def change_entropy(worktree: str, prev_ref: str, cur_ref: str,
                   base_ref: Optional[str] = None) -> dict:
    """Hassan (2009) change entropy: how this change spreads over files.

    H = -sum p_i log2 p_i over the files the change touches, p_i = that file's share
    of the changed lines; H_norm = H / log2(n) so arms with different file counts
    compare. High = the change is spread; low = it lands in one place.

    Reported twice. `change_entropy_*` is THIS checkpoint against the previous one
    -- a per-rule measure with a trajectory. `cum_change_*` is the whole chain so far
    (base -> here), which is the cumulative view: an architecture where every rule
    goes to the same file keeps a low cumulative entropy and a high top-5 share no
    matter how each individual rule looks.

    Pure git: no call resolution, no parse, nothing bespoke. It is the cleanest
    placement measure in the suite for exactly that reason.
    """
    row: dict = {}
    for prefix, a in (("change", prev_ref), ("cum_change", base_ref)):
        if a is None:
            continue
        acc = _numstat(worktree, a, cur_ref)
        vals = [float(v) for v in acc.values() if v > 0]
        total = sum(vals)
        if len(vals) < 2 or total <= 0:
            row.update({f"{prefix}_entropy": (0.0 if vals else None),
                        f"{prefix}_entropy_norm": (0.0 if vals else None),
                        f"{prefix}_files": len(vals) or None,
                        f"{prefix}_top1": (1.0 if vals else None),
                        f"{prefix}_top5": (1.0 if vals else None),
                        f"{prefix}_hhi": (1.0 if vals else None)})
            continue
        h = -sum((v / total) * math.log2(v / total) for v in vals)
        row.update({
            f"{prefix}_entropy": round(h, 4),
            f"{prefix}_entropy_norm": round(h / math.log2(len(vals)), 4),
            f"{prefix}_files": len(vals),
            f"{prefix}_top1": top_share(vals, 1),
            f"{prefix}_top5": top_share(vals, 5),
            f"{prefix}_hhi": hhi(vals),
        })
    return row


# Framework-dispatched classes: code the CONTAINER invokes, which is therefore
# invisible to every call-graph statistic in this harness. AGENTS.md requires this
# count beside any call-graph number for an intervention arm; automating it here
# turns a manual instruction into a column that cannot be forgotten.
_CONTAINER_PATTERNS = {
    "advice": re.compile(r"@(?:Rest)?ControllerAdvice"),
    "aspect": re.compile(r"@Aspect\b"),
    "filter": re.compile(r"\bOncePerRequestFilter\b|\bHandlerInterceptor\b"
                         r"|implements\s+(?:jakarta\.servlet\.)?Filter\b"),
    "entity_listener": re.compile(r"@PrePersist|@PreUpdate|@EntityListeners"),
    "validator": re.compile(r"\bConstraintValidator\b"),
    "body_advice": re.compile(r"\bRequestBodyAdvice\b|\bResponseBodyAdvice\b"),
}


def container_dispatch(worktree: str, files: list[str]) -> dict:
    """Count classes the FRAMEWORK dispatches, per mechanism, plus the total.

    A rule implemented as `@ControllerAdvice` / `@Aspect` / a `Filter` /
    `@PrePersist` / a `ConstraintValidator` is never CALLED by the handler, so it
    leaves `node_cc_median`, `node_path_cc` and every closure statistic entirely.
    On run blind-202609010045 three of ten Spring chains took that route and one
    reported `node_path_cc` = 3 for a codebase implementing all 60 rules.

    This is therefore a VALIDITY column, not a quality measure: if it moves off its
    baseline, the call-graph numbers for that chain are measuring a shrinking
    fraction of the code and must not be quoted without saying so.
    """
    counts = {k: 0 for k in _CONTAINER_PATTERNS}
    for rel in files:
        try:
            with open(os.path.join(worktree, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for name, rx in _CONTAINER_PATTERNS.items():
            if rx.search(text):
                counts[name] += 1
    row = {f"container_{k}": v for k, v in counts.items()}
    row["container_total"] = sum(counts.values())
    return row


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def placement_all(worktree: str, fns: list[dict], adj: dict, roots: list[dict],
                  base_commit: str, prev_ref: str, cur_ref: str,
                  pmd_row: Optional[dict] = None) -> dict:
    """Every placement metric for ONE checkpoint state, as flat CSV fields.

    Called from `metrics.compute_all`, which has already paid for the lizard parse
    and the call index -- so this adds arithmetic over data already in memory plus
    two git diffs, and is cheap enough to run on all 1200 checkpoints of a run.
    """
    files = sorted({f["file"] for f in fns})
    row: dict = {}
    row.update(complexity_placement(fns))
    row.update(halstead_placement(worktree, fns))
    row.update(indirection_stats(roots, adj))
    row.update(propagation_cost(fns, adj))
    row.update(change_entropy(worktree, prev_ref, cur_ref, base_commit))
    row.update(container_dispatch(worktree, files))
    if pmd_row:
        row.update(pmd_row)
    return row


# ---------------------------------------------------------------------------
# Chidamber & Kemerer suite via CK (Aniche 2015), and PMD's detectors
# ---------------------------------------------------------------------------

# Cohesion/coupling numbers worth an arm-level aggregate. Cohesion: lcom / lcom*
# (Chidamber & Kemerer 1994; Henderson-Sellers 1996), tcc / lcc (Bieman & Kang 1995).
# Coupling: cbo, fanin, fanout, rfc. Inheritance: dit. CK parses SOURCE with Eclipse
# JDT -- no compilation, so it runs on a materialised checkpoint tree exactly like
# lizard and PMD do. `tcc`/`lcc` are ratios in [0,1] where HIGH is cohesive; `lcom`
# is a count where LOW is cohesive -- they disagree by construction, which is why
# both are reported rather than one being chosen.
_CK_AGGREGATE = ["cbo", "rfc", "lcom", "lcom*", "tcc", "lcc", "dit", "fanin", "fanout"]


def ck_metrics(worktree: str, src_dirs: list[str], ck_jar: str,
               java_bin: str = "java", handler_class: Optional[str] = None,
               timeout: int = 900) -> Optional[dict]:
    """Per-class C&K metrics via the CK tool, aggregated to arm level.

    Returns None (never zeros) if CK did not run -- the "did not run reads as found
    nothing" failure mode that has already bitten the smell metric twice in this
    harness. A None propagates as a blank column, which `series_by_chain` drops,
    rather than as a 0 that would silently flatten a trajectory.

    Aggregates are reported as mean / max / and the handler class's own value, since
    an arm-wide mean over hundreds of small classes hides exactly the concentration
    this experiment is about.
    """
    if not ck_jar or not os.path.isfile(ck_jar):
        return None
    import csv as _csv
    import shutil
    import tempfile
    out_dir = tempfile.mkdtemp(prefix="ck_")
    rows: list[dict] = []
    try:
        for d in src_dirs:
            target = os.path.join(worktree, d)
            if not os.path.isdir(target):
                continue
            try:
                proc = subprocess.run(
                    [java_bin, "-jar", ck_jar, target, "false", "0", "false",
                     out_dir + os.sep],
                    capture_output=True, text=True, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired):
                return None
            cls_csv = os.path.join(out_dir, "class.csv")
            if proc.returncode != 0 or not os.path.isfile(cls_csv):
                return None
            with open(cls_csv, encoding="utf-8", errors="replace") as fh:
                rows.extend(list(_csv.DictReader(fh)))
            for leftover in ("class.csv", "method.csv", "field.csv", "variable.csv"):
                try:
                    os.remove(os.path.join(out_dir, leftover))
                except OSError:
                    pass
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    if not rows:
        return None

    def col(name: str) -> list[float]:
        vals = []
        for r in rows:
            try:
                v = float(r.get(name, ""))
            except (TypeError, ValueError):
                continue
            if v == v and v >= 0:          # drop NaN and CK's -1 "not applicable"
                vals.append(v)
        return vals

    out: dict = {"ck_classes": len(rows)}
    for name in _CK_AGGREGATE:
        vals = col(name)
        key = name.replace("*", "_star")
        out[f"ck_{key}_mean"] = round(sum(vals) / len(vals), 4) if vals else None
        out[f"ck_{key}_max"] = round(max(vals), 4) if vals else None
    # WMC distribution: an independent parser's view of the same god-class signal the
    # harness computes from lizard, plus its concentration across classes.
    wmc_vals = col("wmc")
    out["ck_wmc_total"] = round(sum(wmc_vals), 2) if wmc_vals else None
    out.update(distribution_block(wmc_vals, "wmcdist_class"))
    if handler_class:
        stem = handler_class.removesuffix(".java")
        for r in rows:
            if (r.get("class", "").split(".")[-1] == stem
                    or os.path.basename(r.get("file", "")) == f"{stem}.java"):
                for name in _CK_AGGREGATE + ["wmc"]:
                    key = name.replace("*", "_star")
                    try:
                        v = float(r.get(name, ""))
                    except (TypeError, ValueError):
                        v = float("nan")
                    # CK emits NaN for a ratio with no defined denominator (TCC of a
                    # class with fewer than two methods). It must become a BLANK, not
                    # a NaN string in the CSV: `_f()` would coerce it to a float NaN
                    # that survives into a fit and silently poisons the slope.
                    out[f"ck_handler_{key}"] = None if v != v else round(v, 4)
                break
    return out


# PMD reports its metric VALUES inside the violation message, so they are parsed out
# rather than counted. Thresholds in pmd-rules/java-metrics.xml are set to 1 precisely
# so every unit reports and these become value streams, not judgements.
_PMD_VALUE_RX = {
    "cognitive": re.compile(r"cognitive complexity of (\d+)"),
    "cyclo": re.compile(r"cyclomatic complexity of (\d+)"),
    "npath": re.compile(r"NPath complexity of (\d+)"),
}


def pmd_metrics(worktree: str, src_dirs: list[str], pmd_bin: str, ruleset: str,
                handler_class: Optional[str] = None, timeout: int = 900) -> Optional[dict]:
    """Cognitive complexity, NPath, and the published GOD-CLASS / DataClass verdicts.

    Two different kinds of number come back and they are used differently:
      * VALUES (cognitive, cyclo, npath) -- a third and fourth independent
        operationalisation of 'amount', for the conservation test. Cognitive
        complexity in particular penalises NESTING and forgives flat sequences, so
        it separates a deeply nested method from a long flat dispatch, which
        cyclomatic complexity cannot.
      * VERDICTS (`GodClass`, `DataClass`) -- PMD implements Lanza & Marinescu (2006)
        exactly: WMC >= 47 AND ATFD > 5 AND TCC < 1/3. The threshold is THEIRS. A
        binary published detector firing on one arm and not the other is the one
        structural claim in this suite that requires no metric of our own.

    Returns None if PMD did not run (see `ck_metrics` on why never zeros). PMD exits
    4 when it finds violations, hence --no-fail-on-violation; and the ruleset path is
    made absolute because PMD is spawned with cwd=<worktree>, where a config-relative
    path resolves against the wrong tree and silently disables the whole pass.
    """
    import json as _json
    if not pmd_bin or not ruleset or not os.path.isfile(ruleset):
        return None
    ruleset = os.path.abspath(ruleset)
    cmd = [pmd_bin, "check", "-f", "json", "-R", ruleset,
           "--no-fail-on-violation", "--no-progress", "--no-cache"]
    present = [d for d in src_dirs if os.path.isdir(os.path.join(worktree, d))]
    if not present:
        return None
    for d in present:
        cmd += ["-d", d]
    try:
        proc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        first = ((proc.stderr or "").strip().splitlines() or [""])[0]
        print(f"    ! pmd(metrics) exited {proc.returncode}; cohesion/cognitive metrics "
              f"DID NOT RUN ({first[:160]})", flush=True)
        return None
    try:
        report = _json.loads(proc.stdout or "{}")
    except ValueError:
        return None
    vals: dict[str, list[float]] = {k: [] for k in _PMD_VALUE_RX}
    verdicts: Counter = Counter()
    god_classes: list[str] = []
    for f in report.get("files", []):
        path = f.get("filename") or ""
        stem = os.path.basename(path).removesuffix(".java")
        for v in f.get("violations", []):
            rule = v.get("rule") or ""
            msg = v.get("description") or ""
            if rule in ("GodClass", "DataClass", "LawOfDemeter"):
                verdicts[rule] += 1
                if rule == "GodClass":
                    god_classes.append(stem)
                continue
            for key, rx in _PMD_VALUE_RX.items():
                m = rx.search(msg)
                if m:
                    # the class-level CyclomaticComplexity message also matches; keep
                    # method-level only so the stream is one value per method
                    if key == "cyclo" and "class" in msg[:24].lower():
                        break
                    vals[key].append(float(m.group(1)))
                    break
    out: dict = {}
    for key, xs in vals.items():
        out[f"pmd_{key}_total"] = round(sum(xs), 2) if xs else None
        out[f"pmd_{key}_max"] = round(max(xs), 2) if xs else None
        out[f"pmd_{key}_mean"] = round(sum(xs) / len(xs), 4) if xs else None
    out.update(distribution_block(vals["cognitive"], "cogdist_fn"))
    out["pmd_god_classes"] = verdicts.get("GodClass", 0)
    out["pmd_data_classes"] = verdicts.get("DataClass", 0)
    out["pmd_demeter_violations"] = verdicts.get("LawOfDemeter", 0)
    if handler_class:
        stem = handler_class.removesuffix(".java")
        out["pmd_handler_is_god_class"] = int(stem in god_classes)
    return out
