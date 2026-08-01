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
    return fn["cc"] * math.sqrt(max(fn["nloc"], 1))


def function_mass(fn: dict) -> float:
    """Public: complexity mass CC * sqrt(SLOC) for one function (Eq. 2)."""
    return _mass(fn)


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
        "hotspot_fn": f"{worst['file'].split('/')[-1]}::{worst['name'].split('::')[-1]}",
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
    for dup in data.get("duplicates", []):
        for side in ("firstFile", "secondFile"):
            f = dup.get(side, {})
            name = f.get("name")
            start = (f.get("start") or {}).get("line") or f.get("startLoc", {}).get("line")
            end = (f.get("end") or {}).get("line") or f.get("endLoc", {}).get("line")
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
        stat = subprocess.run(
            ["git", "-C", worktree, "diff", "--shortstat", prev_ref, cur_ref, *pathspec],
            capture_output=True, text=True, timeout=60).stdout.strip()
        names = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-only", prev_ref, cur_ref, *pathspec],
            capture_output=True, text=True, timeout=60).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"diff_added": None, "diff_removed": None, "files_touched": None}
    import re
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
    import re
    txt = subprocess.run(
        ["git", "-C", worktree, "diff", "-U0", prev_ref, cur_ref, "--", path],
        capture_output=True, text=True, timeout=60).stdout
    ranges: list[tuple[int, int]] = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", txt, re.M):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else 1
        if b == 0:  # pure deletion anchors to one line
            b = 1
        ranges.append((a, a + b - 1))
    return ranges


def _funcs_touched(worktree: str, cur_ref: str, path: str,
                   ranges: list[tuple[int, int]]) -> int:
    """How many functions in `path`@cur_ref overlap any changed line range."""
    if not ranges:
        return 0
    try:
        code = subprocess.run(
            ["git", "-C", worktree, "show", f"{cur_ref}:{path}"],
            capture_output=True, text=True, timeout=60).stdout
    except subprocess.SubprocessError:
        return 0
    try:
        analysis = lizard.analyze_file.analyze_source_code(path, code)
    except Exception:
        return 0
    n = 0
    for fn in analysis.function_list:
        s, e = fn.start_line, fn.end_line
        if any(not (e < a or s > b) for a, b in ranges):
            n += 1
    return n


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
        ns = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-status", "-M", prev_ref, cur_ref],
            capture_output=True, text=True, timeout=60).stdout
        numstat = subprocess.run(
            ["git", "-C", worktree, "diff", "--numstat", prev_ref, cur_ref],
            capture_output=True, text=True, timeout=60).stdout
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
        "entry_fn": f"{h['file'].split('/')[-1]}::{h['name'].split('::')[-1]}",
    }


# ---------------------------------------------------------------------------
# #3 Change spread: how many packages a rule's diff reaches into.
# ---------------------------------------------------------------------------

def change_spread(worktree: str, prev_ref: str, cur_ref: str = "HEAD") -> dict:
    """Architectural reach: distinct packages (source directories) the checkpoint's
    production-Java diff touches. A sibling to blast radius that measures spread
    across the package tree rather than count of functions."""
    try:
        names = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-only", prev_ref, cur_ref],
            capture_output=True, text=True, timeout=60).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"packages_touched": None}
    pkgs = {os.path.dirname(f) for f in names.splitlines() if _is_prod_java(f)}
    return {"packages_touched": len(pkgs)}


# ---------------------------------------------------------------------------
# #2 Re-edit rate (temporal coupling): does a new rule reopen prior rules' code?
# ---------------------------------------------------------------------------

def _blame_line_commits(worktree: str, ref: str, path: str) -> dict[int, str]:
    """line number -> commit sha that last touched it, as of `ref`."""
    out = subprocess.run(
        ["git", "-C", worktree, "blame", "--line-porcelain", ref, "--", path],
        capture_output=True, text=True, timeout=120).stdout
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
    spread = change_spread(worktree, prev_ref, cur_ref)
    reedit = reedit_stats(worktree, base_commit, prev_ref, cur_ref)  # temporal coupling vs base

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
    row.update(spread)
    row.update(reedit)

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
        "change_spread": spread,
        "reedit": reedit,
        "functions": [{**f, "mass": round(function_mass(f), 4)} for f in fns],
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
        ns = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-status", "-M", prev_ref, cur_ref],
            capture_output=True, text=True, timeout=60).stdout
        cur_sha = subprocess.run(
            ["git", "-C", worktree, "rev-parse", cur_ref],
            capture_output=True, text=True, timeout=60).stdout.strip()
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
        if not ranges:
            continue
        try:
            code = subprocess.run(["git", "-C", worktree, "show", f"{cur_ref}:{f}"],
                                  capture_output=True, text=True, timeout=60).stdout
            fns = lizard.analyze_file.analyze_source_code(f, code).function_list
        except Exception:
            continue
        edited = [fn for fn in fns
                  if any(not (fn.end_line < a or fn.start_line > b) for a, b in ranges)]
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
