"""Structural metrics, faithful to the paper definitions.

Erosion and Verbosity are from SlopCodeBench (arXiv:2603.24755):

  mass(f)  = CC(f) * sqrt(SLOC(f))                              (Eq. 2)
  Erosion  = sum_{CC(f)>10} mass(f) / sum_f mass(f)             (Eq. 3)
  Verbosity= |{ast-grep-flagged lines} ∪ {clone lines}| / LOC  (Eq. 4)

All structural metrics are computed over Java production source ONLY, using the
same tools and thresholds for both arms, so OfficeFloor's habit of spreading
code across more (smaller) files and YAML cannot distort the comparison. YAML
line counts are reported separately by the driver, never mixed into LOC.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
import subprocess
from collections import defaultdict
from typing import Optional

import lizard

from . import git_out

CC_THRESHOLD = 10  # Radon standard, as used by SlopCodeBench


def _git(worktree: str, args: list[str], timeout: int = 60) -> str:
    """Run ``git -C <worktree> <args>`` and return stdout. Raises on a missing git
    binary or timeout; callers that need a graceful sentinel wrap this in try/except
    (the shared git_out() swallows too much — several metrics must distinguish a
    real empty diff from a failed git call and return None, not zeros)."""
    return subprocess.run(["git", "-C", worktree, *args],
                          capture_output=True, text=True, timeout=timeout).stdout


def _java_files(root: str, globs: list[str]) -> list[str]:
    files: list[str] = []
    for g in globs:
        files += glob.glob(os.path.join(root, g), recursive=True)
    return sorted({f for f in files if f.endswith(".java") and os.path.isfile(f)})


def functions(root: str, globs: list[str]) -> list[dict]:
    """Per-function CC/SLOC across the given source globs (lizard)."""
    out: list[dict] = []
    for path in _java_files(root, globs):
        try:
            analysis = lizard.analyze_file(path)
        except Exception:
            continue
        rel = os.path.relpath(path, root)
        for fn in analysis.function_list:
            out.append({
                "file": rel,
                "name": fn.name,
                "long_name": fn.long_name,
                "cc": int(fn.cyclomatic_complexity),
                "nloc": int(fn.nloc),
                "start": int(fn.start_line),
                "end": int(fn.end_line),
            })
    return out


def _mass(fn: dict) -> float:
    """Complexity mass CC * sqrt(SLOC) for one function (Eq. 2)."""
    return fn["cc"] * math.sqrt(max(fn["nloc"], 1))


def _fn_label(fn: dict) -> str:
    """Short `File.java::method` label for a function record (basename only)."""
    return f"{fn['file'].split('/')[-1]}::{fn['name'].split('::')[-1]}"


def erosion(fns: list[dict], cc_threshold: int = CC_THRESHOLD) -> float:
    total = sum(_mass(f) for f in fns)
    if total <= 0:
        return 0.0
    high = sum(_mass(f) for f in fns if f["cc"] > cc_threshold)
    return high / total


def erosion_detail(fns: list[dict], cc_threshold: int = CC_THRESHOLD) -> dict:
    """Erosion plus the intermediate terms, so the ratio is reproducible:
    erosion = high_mass / total_mass over functions with CC > threshold."""
    total = high = 0.0
    over = 0
    for f in fns:
        m = _mass(f)
        total += m
        if f["cc"] > cc_threshold:
            high += m
            over += 1
    return {
        "erosion": round(high / total, 4) if total > 0 else 0.0,
        "high_mass": round(high, 4),
        "total_mass": round(total, 4),
        "over_threshold": over,
        "cc_threshold": cc_threshold,
        "n_functions": len(fns),
    }


def total_java_loc(fns: list[dict]) -> int:
    return sum(f["nloc"] for f in fns)


def hotspot_stats(fns: list[dict]) -> dict:
    """God-method indicator: the single highest-cyclomatic-complexity function in
    the given set, named so you can see WHERE complexity concentrates. Pass the
    dynamically-scoped subsystem (production-Java functions in files changed since
    base) so a new class the agent creates is included and can't hide."""
    if not fns:
        return {"hotspot_nloc": None, "hotspot_cc": None, "hotspot_fn": None}
    worst = max(fns, key=lambda f: (f["cc"], f["nloc"]))
    return {
        "hotspot_nloc": worst["nloc"],
        "hotspot_cc": worst["cc"],
        "hotspot_fn": _fn_label(worst),
    }


def function_package_stats(root: str, pkg_glob: Optional[str]) -> dict:
    """OfficeFloor's composed-function package: count and size distribution.

    The healthy growth signal: count rises while avg/max stay flat.
    """
    if not pkg_glob:
        return {"fn_count": None, "fn_nloc_avg": None, "fn_nloc_max": None, "fn_cc_max": None}
    fns = functions(root, [pkg_glob])
    if not fns:
        return {"fn_count": 0, "fn_nloc_avg": 0, "fn_nloc_max": 0, "fn_cc_max": 0}
    nlocs = [f["nloc"] for f in fns]
    return {
        "fn_count": len(fns),
        "fn_nloc_avg": round(sum(nlocs) / len(nlocs), 2),
        "fn_nloc_max": max(nlocs),
        "fn_cc_max": max(f["cc"] for f in fns),
    }


# ---------------------------------------------------------------------------
# Verbosity: clone lines ∪ ast-grep-flagged lines, over Java LOC.
# Both external tools degrade gracefully: if a tool is absent that component is
# skipped and a warning surfaced. If BOTH are absent verbosity is NaN.
# ---------------------------------------------------------------------------

def _clone_lines_jscpd(root: str, src_dirs: list[str], jscpd_bin: str) -> Optional[set[tuple[str, int]]]:
    out_dir = os.path.join(root, ".jscpd-report")
    cmd = [jscpd_bin, "--mode", "strict", "--reporters", "json",
           "--silent", "--output", out_dir, "--format", "java"] + \
          [os.path.join(root, d) for d in src_dirs]
    try:
        subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    report = os.path.join(out_dir, "jscpd-report.json")
    if not os.path.isfile(report):
        return None
    lines: set[tuple[str, int]] = set()
    try:
        with open(report) as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    def _line(fobj, base):
        # jscpd emits base ('start'/'end') as an int line number and baseLoc as
        # {line, column, position}; prefer the Loc.line, fall back to the int.
        loc = fobj.get(base + "Loc")
        if isinstance(loc, dict) and loc.get("line") is not None:
            return loc["line"]
        v = fobj.get(base)
        return v if isinstance(v, int) else None

    for dup in data.get("duplicates", []):
        for side in ("firstFile", "secondFile"):
            f = dup.get(side, {})
            name = f.get("name")
            start = _line(f, "start")
            end = _line(f, "end")
            if name and start and end:
                rel = os.path.relpath(name, root)
                for ln in range(int(start), int(end) + 1):
                    lines.add((rel, ln))
    return lines


def _pattern_lines_astgrep(root: str, src_dirs: list[str], sg_bin: str,
                           rules_dir: str) -> Optional[set[tuple[str, int]]]:
    if not rules_dir or not os.path.isdir(rules_dir):
        return None
    cmd = [sg_bin, "scan", "--json", "-r", rules_dir] + \
          [os.path.join(root, d) for d in src_dirs]
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    try:
        matches = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    lines: set[tuple[str, int]] = set()
    for m in matches:
        f = m.get("file")
        rng = m.get("range", {})
        start = (rng.get("start") or {}).get("line")
        end = (rng.get("end") or {}).get("line")
        if f and start is not None and end is not None:
            rel = os.path.relpath(f, root) if os.path.isabs(f) else f
            for ln in range(int(start), int(end) + 1):
                lines.add((rel, ln))
    return lines


def verbosity(root: str, src_dirs: list[str], loc: int, tools: dict) -> tuple[float, dict]:
    if loc <= 0:
        return float("nan"), {"reason": "no LOC"}
    clones = _clone_lines_jscpd(root, src_dirs, tools.get("jscpd", "jscpd"))
    patterns = _pattern_lines_astgrep(root, src_dirs, tools.get("astgrep", "sg"),
                                      tools.get("astgrep_rules", ""))
    if clones is None and patterns is None:
        return float("nan"), {"reason": "neither jscpd nor ast-grep produced output"}
    union: set[tuple[str, int]] = set()
    if clones:
        union |= clones
    if patterns:
        union |= patterns
    return len(union) / loc, {
        "clone_lines": len(clones) if clones is not None else None,
        "pattern_lines": len(patterns) if patterns is not None else None,
        "union_lines": len(union),
    }


# ---------------------------------------------------------------------------
# Blast radius (per checkpoint), from git.
# ---------------------------------------------------------------------------

def blast_radius(worktree: str, prev_ref: str, cur_ref: str = "HEAD",
                 exclude: str | None = None) -> dict:
    """Change size between two refs. `exclude` (a repo-relative path) is dropped
    via a git pathspec so the injected acceptance tests don't count as agent
    churn."""
    pathspec = ["--", ".", f":(exclude){exclude}"] if exclude else []
    try:
        stat = _git(worktree, ["diff", "--shortstat", prev_ref, cur_ref, *pathspec]).strip()
        names = _git(worktree, ["diff", "--name-only", prev_ref, cur_ref, *pathspec]).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"diff_added": None, "diff_removed": None, "files_touched": None}
    added = removed = 0
    m_ins = re.search(r"(\d+) insertion", stat)
    m_del = re.search(r"(\d+) deletion", stat)
    if m_ins:
        added = int(m_ins.group(1))
    if m_del:
        removed = int(m_del.group(1))
    files = [f for f in names.splitlines() if f.strip()]
    return {"diff_added": added, "diff_removed": removed, "files_touched": len(files)}


def _is_prod_java(path: str) -> bool:
    """Production Java only: excludes tests (so the injected acceptance suite and
    the app's own unit tests never count as blast radius)."""
    return path.endswith(".java") and "test" not in path.lower()


def _changed_ranges(worktree: str, prev_ref: str, cur_ref: str, path: str) -> list[tuple[int, int]]:
    """New-file line ranges the diff touched, from `git diff -U0` hunk headers."""
    txt = _git(worktree, ["diff", "-U0", prev_ref, cur_ref, "--", path])
    ranges: list[tuple[int, int]] = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", txt, re.M):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else 1
        if b == 0:  # pure deletion anchors to one line
            b = 1
        ranges.append((a, a + b - 1))
    return ranges


def _overlapping_functions(worktree: str, cur_ref: str, path: str,
                           ranges: list[tuple[int, int]]) -> list:
    """The lizard function objects in `path`@cur_ref whose body overlaps any changed
    line range. Empty if there are no ranges, or if the git show / lizard parse
    fails (the function is simply dropped from the metric — degrade gracefully)."""
    if not ranges:
        return []
    try:
        code = _git(worktree, ["show", f"{cur_ref}:{path}"])
        analysis = lizard.analyze_file.analyze_source_code(path, code)
    except Exception:
        return []
    return [fn for fn in analysis.function_list
            if any(not (fn.end_line < a or fn.start_line > b) for a, b in ranges)]


def _funcs_touched(worktree: str, cur_ref: str, path: str,
                   ranges: list[tuple[int, int]]) -> int:
    """How many functions in `path`@cur_ref overlap any changed line range."""
    return len(_overlapping_functions(worktree, cur_ref, path, ranges))


def blast_radius_detail(worktree: str, prev_ref: str, cur_ref: str = "HEAD") -> dict:
    """Isolation metric: how much PRE-EXISTING code a checkpoint disturbs.

    A new rule can land two ways. It can be inserted into functions that already
    exist (high blast radius, the change reaches into working code), or it can be
    added as a new wired unit (low blast radius, existing code is left alone).

    Returns, over production Java only:
      existing_fns_modified - functions in already-present files whose body the
                              diff touched (the blast radius proper),
      files_modified        - already-present files the diff touched,
      files_created         - new production files added to hold the rule,
      churn_added/removed   - production line churn.
    """
    try:
        ns = _git(worktree, ["diff", "--name-status", "-M", prev_ref, cur_ref])
        numstat = _git(worktree, ["diff", "--numstat", prev_ref, cur_ref])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"existing_fns_modified": None, "files_modified": None,
                "files_created": None, "churn_added": None, "churn_removed": None}
    modified, created = [], []
    for line in ns.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if not _is_prod_java(path):
            continue
        (created if status.startswith("A") else modified).append(path)  # M/R -> modified
    fns = sum(_funcs_touched(worktree, cur_ref, f,
                             _changed_ranges(worktree, prev_ref, cur_ref, f))
              for f in modified)
    added = removed = 0
    for line in numstat.splitlines():
        p = line.split("\t")
        if len(p) == 3 and _is_prod_java(p[2]) and p[0] != "-":
            added += int(p[0])
            removed += int(p[1])
    return {
        "existing_fns_modified": fns,
        "files_modified": len(modified),
        "files_created": len(created),
        "churn_added": added,
        "churn_removed": removed,
    }


# ---------------------------------------------------------------------------
# #1 Weighted Methods per Class (WMC): the god-CLASS metric.
# ---------------------------------------------------------------------------

def wmc_stats(fns: list[dict]) -> dict:
    """God-class indicator (Chidamber-Kemerer WMC = sum of method CC per class).

    Groups functions by file (one top-level class per Java file) and reports the
    single class with the highest WMC in the given set. This catches what erosion
    (a per-METHOD threshold) cannot: a controller that stays tidy method-by-method
    while accumulating twenty rules' worth of methods becomes a god class, and its
    WMC climbs even though no single method ever crosses CC 10. Pass the touched-
    file subsystem so a new class the agent creates is included."""
    if not fns:
        return {"wmc_max": None, "wmc_max_class": None,
                "wmc_max_methods": None, "wmc_max_nloc": None}
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in fns:
        by_file[f["file"]].append(f)
    worst_file = max(by_file, key=lambda p: sum(g["cc"] for g in by_file[p]))
    grp = by_file[worst_file]
    return {
        "wmc_max": sum(g["cc"] for g in grp),
        "wmc_max_class": worst_file.split("/")[-1],
        "wmc_max_methods": len(grp),
        "wmc_max_nloc": sum(g["nloc"] for g in grp),
    }


# ---------------------------------------------------------------------------
# #4 Entry-handler trajectory: does the endpoint's front door bloat?
# ---------------------------------------------------------------------------

def entry_handler_stats(fns: list[dict], pattern: Optional[str]) -> dict:
    """CC/NLOC over time of the ONE function the create endpoint routes through.

    `pattern` is an arm-specific regex matched against '<file>::<name>', because
    the entry point is architecture-specific: Spring routes POST /api/owners
    through a single handler (addOwner) that can bloat, whereas OfficeFloor routes
    it through a pipeline, so we track its designated create-entry function, which
    is expected to stay flat as new rules attach as new functions. A null/absent
    pattern (or no match) yields blanks."""
    if not pattern:
        return {"entry_cc": None, "entry_nloc": None, "entry_fn": None}
    rx = re.compile(pattern)
    hits = [f for f in fns if rx.search(f"{f['file']}::{f['name']}")]
    if not hits:
        return {"entry_cc": None, "entry_nloc": None, "entry_fn": None}
    h = max(hits, key=lambda f: (f["cc"], f["nloc"]))
    return {
        "entry_cc": h["cc"],
        "entry_nloc": h["nloc"],
        "entry_fn": _fn_label(h),
    }


def handler_scoped_erosion(fns: list[dict], pattern: Optional[str],
                           cc_threshold: int = CC_THRESHOLD) -> dict:
    """Erosion (Eq.3) restricted to the entry handler's OWN class file(s).

    Whole-app and touched-file erosion are both dominated by architecture-neutral
    leaf algorithms (soundex, phone/E.164 formatting, duplicate detection) that
    BOTH arms implement and that carry irreducible branching wherever they land, so
    they swamp the phenomenon this experiment is about: does the endpoint's handler
    surface itself erode? This scopes erosion to the file(s) containing the matched
    entry-handler function — the controller class for Spring (where addOwner and its
    sibling helpers concentrate) and BuildOwner for OfficeFloor (expected to stay
    flat as rules attach as separate wired functions). Because it is class-scoped it
    excludes the shared leaf-algorithm classes for both arms, isolating the concentration
    signal that `entry_cc`/`wmc_max` already show. A null/absent pattern (or no
    match — e.g. before the handler exists) yields blanks."""
    blank = {"erosion_handler": None, "erosion_handler_high_mass": None,
             "erosion_handler_total_mass": None, "erosion_handler_hot_fns": None,
             "erosion_handler_class": None, "erosion_handler_nfns": None}
    if not pattern:
        return dict(blank)
    # Scope by the handler's CLASS FILE. The entry_handler convention is
    # 'Class::method', and the class is what we want — every method that accreted
    # onto the handler's class, not just the one entry method. Matching the file is
    # also robust to lizard's checkpoint-to-checkpoint variation in whether it names
    # a function 'Class::method' or bare 'method'; matching the method name blanks
    # the metric exactly on the checkpoints where the handler bloats most.
    m = re.match(r"([A-Za-z_]\w*)::", pattern)
    files: set[str] = set()
    if m:
        stem = m.group(1) + ".java"
        files = {f["file"] for f in fns if f["file"].split("/")[-1] == stem}
    if not files:  # pattern not in Class::method form, or the class isn't present yet
        rx = re.compile(pattern)
        files = {f["file"] for f in fns if rx.search(f"{f['file']}::{f['name']}")}
    if not files:
        return dict(blank)
    ed = erosion_detail([f for f in fns if f["file"] in files], cc_threshold)
    return {
        "erosion_handler": ed["erosion"],
        "erosion_handler_high_mass": ed["high_mass"],
        "erosion_handler_total_mass": ed["total_mass"],
        "erosion_handler_hot_fns": ed["over_threshold"],
        "erosion_handler_class": ", ".join(sorted(p.split("/")[-1] for p in files)),
        "erosion_handler_nfns": ed["n_functions"],
    }


# ---------------------------------------------------------------------------
# Structural-impact score: how much a rule's diff DISTURBS existing structure,
# weighted by the complexity of the CONTEXT it touches. Unlike erosion (which is
# location-blind and charges for intrinsic branchiness wherever it lands), impact
# weights every change by the surrounding class's complexity, so mutating a method
# inside a heavy god-class costs far more than the same edit to an isolated unit.
#
# Per changed function the cost is a single uniform term:
#     max(WMC_other, 1) · CC(f) · max(1, Δlines(f))        summed per function,
# then the whole commit is multiplied by the number of production-Java files it
# touches (`files_changed`) -- a spread penalty so that scattering one rule across
# many classes (fragmentation without cohesion) is not free. WMC_other is the sum
# of CC of the OTHER methods in the function's class (the context you must hold to
# change it safely); a brand-new class has WMC_other = 0 -> floored to 1, so a new
# isolated unit still costs max(1)·CC·nloc·files (small, but non-zero -- closing the
# fragmentation loophole). Δlines is the changed-line count; for a new function that
# is its own size. Reported as two sub-scores plus their sum:
#     impact_mutation  = files · Σ(existing functions modified/renamed)
#     impact_godclass  = files · Σ(new functions: new files + methods fed into classes)
#     impact_composite = impact_mutation + impact_godclass   (both already commensurate)
# Intended for ADDITIVE checkpoints; mutative steps revise prior rules by design,
# so analyze discounts them (blanks these fields on mutative rows before slopes).
# ---------------------------------------------------------------------------

IMPACT_RENAME_JACCARD = 0.6  # body-line Jaccard above which a within-commit 'new' name is really a rename


def _parse_blob(worktree: str, ref: str, path: str) -> dict:
    """name -> {cc, nloc, s, e, body} for the functions in path@ref (body = frozenset
    of its stripped non-blank source lines, for within-commit rename matching)."""
    try:
        code = _git(worktree, ["show", f"{ref}:{path}"])
        fl = lizard.analyze_file.analyze_source_code(path, code).function_list
    except Exception:
        return {}
    L = code.splitlines()
    out = {}
    for f in fl:
        out[f.name] = {
            "cc": int(f.cyclomatic_complexity), "nloc": int(f.nloc),
            "s": f.start_line, "e": f.end_line,
            "body": frozenset(s.strip() for s in L[f.start_line - 1:f.end_line] if s.strip()),
        }
    return out


def _line_overlap(s: int, e: int, ranges: list[tuple[int, int]]) -> int:
    return sum(max(0, min(e, b) - max(s, a) + 1) for a, b in ranges)


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def impact_stats(worktree: str, prev_ref: str, cur_ref: str = "HEAD",
                 rename_j: float = IMPACT_RENAME_JACCARD) -> dict:
    """Per-checkpoint structural-impact score (see section header).

    A within-commit rename (a 'new' name whose body matches a disappeared prev
    function, Jaccard >= rename_j) is scored as a mutation, not a free addition, so
    edits can't hide behind renames. All refs share the worktree's object DB, so
    prev_ref (= the agent commit's parent) resolves exactly as it does for
    blast_radius_detail. The whole commit is scaled by `files_changed` (a spread
    penalty), so the two sub-scores are the per-file sums already multiplied by it."""
    blank = {"impact_mutation": None, "impact_godclass": None, "impact_composite": None,
             "impact_files_changed": None, "impact_new_files": None, "impact_new_fns": None,
             "impact_mut_fns": None, "impact_renames": None}
    try:
        ns = _git(worktree, ["diff", "--name-status", "-M", "-C", prev_ref, cur_ref])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return dict(blank)
    new_files, mod_files, all_files = [], [], set()
    for line in ns.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if not _is_prod_java(path):
            continue
        all_files.add(path)
        (new_files if status.startswith("A") else mod_files).append(path)
    files_changed = len(all_files)

    mutation = addition = 0.0
    n_newfn = n_mutfn = n_ren = 0
    # New files: every function is new, WMC_other = 0 -> floored to 1; Δ = its size.
    for path in new_files:
        for f in _parse_blob(worktree, cur_ref, path).values():
            addition += max(0, 1) * f["cc"] * max(1, f["nloc"])
            n_newfn += 1
    # Modified files: classify each touched function against the prev blob.
    for path in mod_files:
        ranges = _changed_ranges(worktree, prev_ref, cur_ref, path)
        if not ranges:
            continue
        cur = _parse_blob(worktree, cur_ref, path)
        prev = _parse_blob(worktree, prev_ref, path)
        wmc_prev = sum(v["cc"] for v in prev.values())
        disappeared = [n for n in prev if n not in cur]
        for name, f in cur.items():
            d = _line_overlap(f["s"], f["e"], ranges)
            if d == 0:
                continue
            if name in prev:              # modified existing function
                ctx = wmc_prev - prev[name]["cc"]
                mutation += max(ctx, 1) * f["cc"] * max(1, d)
                n_mutfn += 1
            else:
                best_dn = max(disappeared, key=lambda dn: _jaccard(f["body"], prev[dn]["body"]),
                              default=None)
                if best_dn is not None and _jaccard(f["body"], prev[best_dn]["body"]) >= rename_j:
                    ctx = wmc_prev - prev[best_dn]["cc"]  # within-commit rename -> mutation
                    mutation += max(ctx, 1) * f["cc"] * max(1, d)
                    n_ren += 1
                else:                     # genuinely new method into an existing class
                    addition += max(wmc_prev, 1) * f["cc"] * max(1, d)
                    n_newfn += 1
    impact_mutation = round(mutation * files_changed, 2)
    impact_godclass = round(addition * files_changed, 2)
    return {
        "impact_mutation": impact_mutation,
        "impact_godclass": impact_godclass,
        "impact_composite": round(impact_mutation + impact_godclass, 2),
        "impact_files_changed": files_changed,
        "impact_new_files": len(new_files),
        "impact_new_fns": n_newfn,
        "impact_mut_fns": n_mutfn,
        "impact_renames": n_ren,
    }


# ---------------------------------------------------------------------------
# #3 Change spread: how many packages a rule's diff reaches into.
# ---------------------------------------------------------------------------

def change_spread(worktree: str, prev_ref: str, cur_ref: str = "HEAD") -> dict:
    """Architectural reach: distinct packages (source directories) the checkpoint's
    production-Java diff touches. A sibling to blast radius that measures spread
    across the package tree rather than count of functions."""
    try:
        names = _git(worktree, ["diff", "--name-only", prev_ref, cur_ref])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"packages_touched": None}
    pkgs = {os.path.dirname(f) for f in names.splitlines() if _is_prod_java(f)}
    return {"packages_touched": len(pkgs)}


# ---------------------------------------------------------------------------
# #2 Re-edit rate (temporal coupling): does a new rule reopen prior rules' code?
# ---------------------------------------------------------------------------

def _blame_line_commits(worktree: str, ref: str, path: str) -> dict[int, str]:
    """line number -> commit sha that last touched it, as of `ref`."""
    out = _git(worktree, ["blame", "--line-porcelain", ref, "--", path], timeout=120)
    m: dict[int, str] = {}
    for line in out.splitlines():
        mt = re.match(r"^([0-9a-f]{40}) \d+ (\d+)", line)
        if mt:
            m[int(mt.group(2))] = mt.group(1)
    return m


def yaml_loc(root: str, globs: list[str]) -> int:
    """Non-blank, non-comment YAML lines under `globs` (reported separately from
    Java LOC — never mixed into the erosion/verbosity denominators)."""
    total = 0
    for g in globs or []:
        for path in glob.glob(os.path.join(root, g), recursive=True):
            if path.endswith((".yml", ".yaml")) and os.path.isfile(path):
                with open(path, errors="ignore") as fh:
                    total += sum(1 for line in fh
                                 if line.strip() and not line.strip().startswith("#"))
    return total


def compute_all(worktree: str, arm_cfg: dict, tools: dict, base_commit: str,
                prev_ref: str, cur_ref: str = "HEAD", exclude: str | None = None
                ) -> tuple[dict, dict]:
    """The complete structural-metric suite for ONE checkpoint state.

    This is a pure function of the worktree's files at `cur_ref` plus git history
    (`base_commit` = the chain's pre-feature base; `prev_ref` = the previous
    checkpoint commit). It is the single definition of every structural number,
    called BOTH by the runner at run time and by `analyze --recompute` over a
    checked-out historical commit — so a metric lives in one place and can be
    re-derived on OLD runs without re-invoking the (expensive) agent.

    Returns (row_updates, details): the flat CSV fields, and the full per-function
    raw inputs + intermediates so every number is reproducible by hand.
    """
    fns = functions(worktree, arm_cfg["source_globs"])
    loc = total_java_loc(fns)

    # Dynamic subsystem: production-Java functions in files changed since base.
    # A new class the agent creates shows up in this diff, so neither the scoped
    # erosion nor the hotspot can miss it.
    touched = set(git_out(worktree, ["diff", "--name-only", base_commit, cur_ref]).splitlines())
    touched_fns = [f for f in fns if f["file"] in touched]

    ed = erosion_detail(fns)            # whole app (SlopCodeBench-comparable)
    eds = erosion_detail(touched_fns)   # scoped to the evolving footprint
    vscore, vdetail = verbosity(worktree, arm_cfg.get("verbosity_dirs", ["src/main/java"]),
                                loc, tools)
    hs = hotspot_stats(touched_fns)                          # worst fn in the footprint
    fp = function_package_stats(worktree, arm_cfg.get("function_package_glob"))
    br = blast_radius(worktree, prev_ref, cur_ref, exclude=exclude)
    brd = blast_radius_detail(worktree, prev_ref, cur_ref)
    wmc = wmc_stats(touched_fns)                             # god-class over the subsystem
    eh = entry_handler_stats(fns, arm_cfg.get("entry_handler"))  # whole-app: found even if unchanged
    ehe = handler_scoped_erosion(fns, arm_cfg.get("entry_handler"))  # erosion of the handler's own class
    spread = change_spread(worktree, prev_ref, cur_ref)
    reedit = reedit_stats(worktree, base_commit, prev_ref, cur_ref)  # temporal coupling vs base
    imp = impact_stats(worktree, prev_ref, cur_ref)  # blast weighted by complexity disturbed

    row = {
        "erosion": ed["erosion"],
        "erosion_high_mass": ed["high_mass"],
        "erosion_total_mass": ed["total_mass"],
        "erosion_hot_fns": ed["over_threshold"],
        "erosion_scoped": eds["erosion"],
        "erosion_scoped_high_mass": eds["high_mass"],
        "erosion_scoped_total_mass": eds["total_mass"],
        "subsystem_nfns": eds["n_functions"],
        "verbosity": ("" if vscore != vscore else round(vscore, 4)),  # NaN -> blank
        "verbosity_clone_lines": vdetail.get("clone_lines", ""),
        "verbosity_pattern_lines": vdetail.get("pattern_lines", ""),
        "verbosity_union_lines": vdetail.get("union_lines", ""),
        "java_loc": loc,
        "yaml_loc": yaml_loc(worktree, arm_cfg.get("yaml_globs", [])),
    }
    row.update(hs)
    row.update(fp)
    row.update(br)
    row.update(brd)
    row.update(wmc)
    row.update(eh)
    row.update(ehe)
    row.update(spread)
    row.update(reedit)
    row.update(imp)

    details = {
        "erosion": ed,
        "erosion_scoped": eds,
        "subsystem_files": sorted({f["file"] for f in touched_fns}),
        "verbosity": {"value": (None if vscore != vscore else round(vscore, 4)),
                      **vdetail, "java_loc": loc},
        "hotspot": hs,
        "function_package": fp,
        "blast_radius": br,
        "blast_radius_detail": brd,
        "wmc": wmc,
        "entry_handler": eh,
        "erosion_handler": ehe,
        "change_spread": spread,
        "reedit": reedit,
        "impact": imp,
        "functions": [{**f, "mass": round(_mass(f), 4)} for f in fns],
    }
    return row, details


def reedit_stats(worktree: str, base_ref: str, prev_ref: str,
                 cur_ref: str = "HEAD") -> dict:
    """Temporal coupling: when this checkpoint edits an already-existing function,
    how much of that function's body was authored by EARLIER checkpoints?

    For every function the checkpoint modifies, blame its body at cur_ref and bin
    each line by author era: original app (ancestor of base_ref), an earlier
    checkpoint (post-base, not this commit), or this checkpoint (cur_ref itself).
    The rate = earlier-checkpoint lines / total body lines of the edited functions.

    High => new rules keep piling into functions that earlier rules grew (Spring's
    addOwner). Low/None => the checkpoint added new units instead of reopening
    accumulated ones (OfficeFloor). Counting whole bodies (not just changed lines)
    is deliberate: it catches a one-line insertion into a large shared method,
    which line-of-diff blame would miss because both arms are near-purely additive."""
    try:
        ns = _git(worktree, ["diff", "--name-status", "-M", prev_ref, cur_ref])
        cur_sha = _git(worktree, ["rev-parse", cur_ref]).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"reedit_body_lines": None, "reedit_prior_lines": None, "reedit_rate": None}
    modified = [p.split("\t")[-1] for p in ns.splitlines()
                if len(p.split("\t")) >= 2 and not p.split("\t")[0].startswith("A")
                and _is_prod_java(p.split("\t")[-1])]
    anc: dict[str, bool] = {}

    def is_original(sha: str) -> bool:
        if sha not in anc:
            rc = subprocess.run(
                ["git", "-C", worktree, "merge-base", "--is-ancestor", sha, base_ref],
                capture_output=True, text=True).returncode
            anc[sha] = (rc == 0)
        return anc[sha]

    body_total = prior = 0
    for f in modified:
        ranges = _changed_ranges(worktree, prev_ref, cur_ref, f)  # new-side edited regions
        edited = _overlapping_functions(worktree, cur_ref, f, ranges)
        if not edited:
            continue
        blame = _blame_line_commits(worktree, cur_ref, f)
        for fn in edited:
            for ln in range(fn.start_line, fn.end_line + 1):
                sha = blame.get(ln)
                if not sha:
                    continue
                body_total += 1
                if sha != cur_sha and not is_original(sha):
                    prior += 1
    rate = (prior / body_total) if body_total else None
    return {
        "reedit_body_lines": body_total,
        "reedit_prior_lines": prior,
        "reedit_rate": (round(rate, 4) if rate is not None else None),
    }
