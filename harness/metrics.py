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
import subprocess
from typing import Optional

import lizard

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


def hotspot_stats(fns: list[dict], hotspot_cfg: Optional[dict]) -> dict:
    """Track the "god-method" indicator for a subsystem: the single
    highest-cyclomatic-complexity function among the configured files, reported
    with its name so you can see WHERE behaviour is accreting.

    Config (per arm): {files: [path-substrings], methods: [names] (optional)}.
    `methods` matches on the method-name suffix, so it works with lizard's
    Java `Class::method` naming (the bug that previously left this always None).
    A legacy {file: "...", methods: [...]} shape is still accepted.
    """
    empty = {"hotspot_nloc": None, "hotspot_cc": None, "hotspot_fn": None}
    if not hotspot_cfg:
        return empty
    files = hotspot_cfg.get("files") or ([hotspot_cfg["file"]] if hotspot_cfg.get("file") else [])
    methods = hotspot_cfg.get("methods") or []
    cand = []
    for f in fns:
        if files and not any(sub in f["file"] for sub in files):
            continue
        if methods and f["name"].split("::")[-1] not in methods:
            continue
        cand.append(f)
    if not cand:
        return empty
    worst = max(cand, key=lambda f: (f["cc"], f["nloc"]))
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
