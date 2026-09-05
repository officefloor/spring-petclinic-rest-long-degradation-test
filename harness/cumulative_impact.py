"""Cumulative change audit: base_ref -> chain tip, over EVERY changed file.

The per-checkpoint metrics in :mod:`harness.metrics` are deliberately scoped --
``source_globs`` (production Java), a hotspot subsystem, a wired-node closure.
That scoping is what makes them comparable between arms, but it also means an
agent can hold those numbers down by putting work where the scope does not
reach: YAML wiring, SQL, generated config, class fields, test code.

This module answers the blunt question instead. Diff the branch START against
its FINAL commit -- one diff for the whole run, so intermediate churn collapses
and only the surviving change is measured -- then, for every changed line in
every changed file:

  * find the function at the tip whose body contains it,
  * take that function's cyclomatic complexity,
  * sum CC over the DISTINCT functions touched.

A function is counted once no matter how many checkpoints touched it, because
the question is the complexity of the code that now exists, not the number of
edits that built it.

Lines that land nowhere are the point of the exercise and are reported, never
dropped:

  ``orphan``  - inside a file lizard parses, but outside every function body
                (class fields, static initialisers, annotations, enum bodies).
  ``opaque``  - inside a file lizard cannot parse at all (.yml, .xml, .json,
                .properties, .md). OfficeFloor's wiring lives here by design,
                so this bucket is a genuine architectural difference as well as
                a blind spot -- read it alongside the CC sum, not instead of it.

Both are reported per arm next to the CC sum, together with the same CC sum
restricted to ``source_globs``. The gap between the scoped sum and the full
sweep is the direct measure of how much a scoped metric cannot see.

Usage:
    python -m harness.cumulative_impact --config config.yaml [--run-id ID]
                                        [--json OUT.json] [--top N]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import statistics
import subprocess
from collections import defaultdict

import lizard
import yaml

from . import expand_path, git_out

# Harness bookkeeping committed onto every chain branch (raw capture, agent
# transcripts, build logs). Never application code -- excluded from the diff at
# the pathspec level so it cannot reach any bucket.
EXCLUDE_PATHSPECS = [":(exclude)evolve-results"]

_BRANCH_RE = re.compile(r"^evolve/([^/]+)/([^/]+)/([^/]+)/chain(\d+)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Extensions lizard 1.23 has a parser for. Anything else is `opaque`: we can
# count its changed lines but cannot attribute them to a function.
_LIZARD_EXTS = frozenset(
    e.lower() for lang in lizard.languages() for e in (getattr(lang, "ext", None) or [])
)


def _is_test(path: str) -> bool:
    """Mirror metrics._is_prod_java's test rule so the two agree on what is test
    code (the injected acceptance suite plus anything the agent added itself)."""
    return "test" in path.lower()


def _glob_to_re(glob: str) -> re.Pattern:
    """Translate a config source_glob to a regex. fnmatch cannot express `**`
    (it lets `*` cross `/`), which would make `src/main/java/**/*.java` match
    paths it must not."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif glob.startswith("**", i):
            out.append(r".*")
            i += 2
        elif glob[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _in_scope(path: str, globs: list[str]) -> bool:
    """Is this path inside the arm's configured source_globs -- i.e. can the
    existing per-checkpoint metrics see it at all?"""
    return any(_glob_to_re(g).match(path) for g in globs)


def evolve_branches(cfg: dict, run_id: str | None = None) -> list[tuple]:
    """(repo, branch, arm, strategy, chain) across the arm repos, newest run
    first. Same branch grammar analyze.py uses."""
    out = []
    for arm, arm_cfg in cfg["arms"].items():
        repo = expand_path(arm_cfg["repo"], f"arms.{arm}.repo")
        refs = git_out(repo, ["for-each-ref", "--format=%(refname:short)",
                              "refs/heads/evolve"]).splitlines()
        for br in (r.strip() for r in refs if r.strip()):
            m = _BRANCH_RE.match(br)
            if not m:
                continue
            rid, strat, br_arm, chain = m.groups()
            if run_id and rid != run_id:
                continue
            if br_arm != arm:
                continue
            out.append((repo, br, arm, strat, int(chain)))
    return sorted(out, key=lambda r: (r[2], r[4]))


def latest_run_id(cfg: dict) -> str | None:
    ids = {_BRANCH_RE.match(br).group(1) for _, br, *_ in evolve_branches(cfg)}
    return max(ids) if ids else None


def changed_ranges(repo: str, base: str, tip: str) -> tuple[dict, dict]:
    """Parse ONE `git diff -U0 base..tip` into per-file new-side line ranges.

    Returns (ranges, deleted) where ranges maps path -> [(start, end), ...] on
    the TIP side, and deleted maps path -> removed-line count for files that no
    longer exist at the tip. A single diff (rather than one per file) keeps this
    to one git invocation per branch and cannot disagree with itself about
    renames."""
    txt = subprocess.run(
        ["git", "-C", repo, "-c", "core.quotepath=false", "diff", "-U0",
         "--no-renames", f"{base}..{tip}", "--", *EXCLUDE_PATHSPECS],
        capture_output=True, text=True, timeout=300).stdout

    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    deleted: dict[str, int] = defaultdict(int)
    cur: str | None = None
    gone = False
    for line in txt.splitlines():
        if line.startswith("--- "):
            old = line[4:]
            cur = None if old == "/dev/null" else old[2:]
            continue
        if line.startswith("+++ "):
            new = line[4:]
            gone = new == "/dev/null"
            if not gone:
                cur = new[2:]
            continue
        if not line.startswith("@@") or cur is None:
            continue
        m = _HUNK_RE.match(line)
        if not m:
            continue
        if gone:
            deleted[cur] += int(m.group(2)) if m.group(2) is not None else 1
            continue
        start = int(m.group(3))
        count = int(m.group(4)) if m.group(4) is not None else 1
        if count == 0:
            # Pure deletion: the diff points at the line it was removed AFTER.
            # Anchor to that line so the surrounding function still counts.
            ranges[cur].append((start, start))
        else:
            ranges[cur].append((start, start + count - 1))
    return dict(ranges), dict(deleted)


def _blob(repo: str, ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def _functions_at(repo: str, ref: str, path: str) -> list | None:
    """lizard's function list for path@ref, or None if the extension has no
    parser or the parse fails. None and [] mean different things: None is
    `cannot see inside`, [] is `saw inside, found no functions`."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in _LIZARD_EXTS:
        return None
    code = _blob(repo, ref, path)
    if code is None:
        return None
    try:
        return list(lizard.analyze_file.analyze_source_code(path, code).function_list)
    except Exception:
        return None


def _lines_in(ranges: list[tuple[int, int]]) -> int:
    return sum(b - a + 1 for a, b in ranges)



# Java tokens that create a branch. lizard only counts them inside a function
# body, so the same token in a field initialiser, a static block or a nested
# anonymous class is real control flow that never reaches any CC number. Counting
# them in the orphan lines is the direct test for "logic hidden where CC cannot
# see it" -- as opposed to the package/import/brace boilerplate that dominates
# any newly created file and is not hiding anything.
_BRANCH_TOKENS = (
    r"\bif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b", r"\bcase\b",
    r"\bcatch\b", r"\bswitch\b", r"&&", r"\|\|", r"\?", r"->",
)
_BRANCH_RE_JAVA = re.compile("|".join(_BRANCH_TOKENS))

# Boilerplate an orphan line may be before it counts as "carrying content":
# blank, comment, package/import, a bare annotation, or a brace-only line.
_BOILERPLATE_RE = re.compile(
    r"^\s*(?:$|//|/\*|\*|package\b|import\b|@\w+[^;]*$|[{}();]+\s*$)")

# A string literal or comment can contain "?" or "->" without being control flow.
_STRIP_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|//.*$')


def classify_orphan(lines: list[str]) -> dict:
    """Split orphan (outside-any-function) lines into boilerplate vs content, and
    count the branch tokens among them. `branch_tokens` is the number that matters:
    it is control flow that exists in the shipped code and that no CC metric --
    this module's included -- attributes to any function."""
    boiler = content = branches = 0
    carriers: list[str] = []
    for raw in lines:
        if _BOILERPLATE_RE.match(raw):
            boiler += 1
            continue
        content += 1
        n = len(_BRANCH_RE_JAVA.findall(_STRIP_RE.sub("", raw)))
        if n:
            branches += n
            carriers.append(raw.strip()[:120])
    return {"boilerplate": boiler, "content": content,
            "branch_tokens": branches, "carriers": carriers}


# OfficeFloor expresses control flow as wiring: a `next:` is a sequential edge,
# a `flow:` a conditional branch, an `exception:`/`escalation:` an error edge.
# These are decisions the application really makes, in a file no CC tool parses.
# Counting them is not a CC number and must not be added to one -- it is the
# size of the arm's declarative control flow, reported alongside.
def _yaml_edges(text: str) -> int:
    """Control-flow edges declared by an OfficeFloor wiring file.

    Parsed as YAML rather than grepped, because the branch count is the whole
    point of the comparison and a regex miscounts it: `next:` is one sequential
    edge, but each entry under a node's `outputs:` is a separate CONDITIONAL
    edge, and those are nested one level deeper. `govern:` is a decorator, not a
    branch, and is excluded.

    This is NOT a cyclomatic complexity and must never be summed into one. It is
    the size of the arm's declarative control flow -- decisions the application
    really makes, in a file no CC tool parses -- reported beside the CC sum."""
    try:
        doc = yaml.safe_load(text)
    except Exception:
        return 0
    if not isinstance(doc, dict):
        return 0
    edges = 0
    for node in doc.values():
        if not isinstance(node, dict):
            continue
        if node.get("next"):
            edges += 1
        outs = node.get("outputs")
        if isinstance(outs, dict):
            edges += len(outs)
        elif isinstance(outs, list):
            edges += len(outs)
    return edges


def audit_branch(repo: str, base: str, tip: str, source_globs: list[str]) -> dict:
    """Full cumulative audit of one chain: base_ref -> branch tip."""
    ranges, deleted = changed_ranges(repo, base, tip)
    base_files = set(git_out(repo, ["ls-tree", "-r", "--name-only", base]).split())

    touched: dict[tuple[str, str, int], dict] = {}   # (file, name, start) -> fn record
    orphan_lines = orphan_lines_scoped = 0
    orphan_files: dict[str, int] = {}
    orphan_text: list[str] = []
    opaque_lines = 0
    opaque_files: dict[str, int] = {}
    yaml_edges = 0
    parsed_files = opaque_file_n = 0

    for path, rs in sorted(ranges.items()):
        n_lines = _lines_in(rs)
        fns = _functions_at(repo, tip, path)
        if fns is None:
            opaque_lines += n_lines
            opaque_files[path] = n_lines
            opaque_file_n += 1
            if path.endswith((".yml", ".yaml")):
                # Edges ADDED over the run = tip edges minus base edges. A hunk of
                # YAML is not itself valid YAML, so both ends are parsed whole.
                yaml_edges += (_yaml_edges(_blob(repo, tip, path) or "")
                               - _yaml_edges(_blob(repo, base, path) or ""))
            continue
        parsed_files += 1
        in_scope = _in_scope(path, source_globs)
        covered = 0
        for fn in fns:
            hit = [r for r in rs if not (fn.end_line < r[0] or fn.start_line > r[1])]
            if not hit:
                continue
            covered += sum(min(b, fn.end_line) - max(a, fn.start_line) + 1
                           for a, b in hit
                           if min(b, fn.end_line) >= max(a, fn.start_line))
            key = (path, fn.name, int(fn.start_line))
            if key not in touched:
                touched[key] = {
                    "file": path,
                    "name": fn.name,
                    "cc": int(fn.cyclomatic_complexity),
                    "nloc": int(fn.nloc),
                    "in_scope": in_scope,
                    "is_test": _is_test(path),
                    "new_file": path not in base_files,
                }
        missed = max(0, n_lines - covered)
        if missed:
            orphan_files[path] = missed
            if path.endswith(".java"):
                src = (_blob(repo, tip, path) or "").splitlines()
                inside = {i for fn in fns
                          for i in range(fn.start_line, fn.end_line + 1)}
                orphan_text += [src[i - 1] for a, b in rs
                                for i in range(a, min(b, len(src)) + 1)
                                if i not in inside]
        orphan_lines += missed
        if in_scope:
            orphan_lines_scoped += missed

    fns_all = list(touched.values())
    prod = [f for f in fns_all if not f["is_test"]]
    scoped = [f for f in prod if f["in_scope"]]

    def cc(rows):
        return sum(f["cc"] for f in rows)

    return {
        "cc_sum_full": cc(prod),
        "cc_sum_scoped": cc(scoped),
        "cc_sum_test": cc([f for f in fns_all if f["is_test"]]),
        "cc_sum_new_files": cc([f for f in prod if f["new_file"]]),
        "cc_sum_existing_files": cc([f for f in prod if not f["new_file"]]),
        "fns_touched_full": len(prod),
        "fns_touched_scoped": len(scoped),
        "orphan_lines": orphan_lines,
        "orphan_lines_scoped": orphan_lines_scoped,
        "orphan_files": orphan_files,
        "orphan_profile": classify_orphan(orphan_text),
        "yaml_edges": yaml_edges,
        "opaque_lines": opaque_lines,
        "opaque_files": opaque_files,
        "files_parsed": parsed_files,
        "files_opaque": opaque_file_n,
        "files_deleted": len(deleted),
        "deleted_lines": sum(deleted.values()),
        "functions": fns_all,
    }



def _agg(rows: list[dict], key) -> tuple[float, float]:
    v = [key(r) for r in rows]
    return (statistics.mean(v), statistics.stdev(v) if len(v) > 1 else 0.0)


# (label, accessor). Order is the reading order of the report: the number that was
# asked for first, then what it is made of, then the two buckets it cannot contain.
_REPORT_ROWS = [
    ("CC sum over touched fns", lambda r: r["cc_sum_full"]),
    ("  in new files", lambda r: r["cc_sum_new_files"]),
    ("  in pre-existing files", lambda r: r["cc_sum_existing_files"]),
    ("  restricted to source_globs", lambda r: r["cc_sum_scoped"]),
    ("distinct fns touched", lambda r: r["fns_touched_full"]),
    ("mean CC per touched fn",
     lambda r: r["cc_sum_full"] / max(1, r["fns_touched_full"])),
    ("files parsed", lambda r: r["files_parsed"]),
    ("files opaque to lizard", lambda r: r["files_opaque"]),
    ("orphan lines", lambda r: r["orphan_lines"]),
    ("  boilerplate", lambda r: r["orphan_profile"]["boilerplate"]),
    ("  content-bearing", lambda r: r["orphan_profile"]["content"]),
    ("  BRANCH TOKENS", lambda r: r["orphan_profile"]["branch_tokens"]),
    ("opaque lines", lambda r: r["opaque_lines"]),
    ("  YAML wiring edges added", lambda r: r["yaml_edges"]),
]


def print_report(results: dict[str, list[dict]], top: int = 15) -> None:
    """Per-arm aggregate, then the heaviest touched functions per arm."""
    arms = sorted(results)
    print("\n## Per-arm aggregate (mean +/- sd over chains)\n")
    print(f"{'':30s}" + "".join(f"{a:>24s}" for a in arms))
    for label, key in _REPORT_ROWS:
        line = f"{label:30s}"
        for a in arms:
            m, sd = _agg(results[a], key)
            line += f"{m:16.1f} +/-{sd:5.1f}"
        print(line)

    # Union ACROSS chains, keyed file::name, so the same logic solved differently by
    # different chains appears once per name it was given. Repeated stems here are
    # ten independent chains naming the same job, NOT duplication inside one chain.
    print("\n## Heaviest touched functions (union over chains, max CC per name)\n")
    for a in arms:
        best: dict[str, dict] = {}
        for r in results[a]:
            for fn in r["functions"]:
                k = f"{fn['file']}::{fn['name']}"
                if k not in best or fn["cc"] > best[k]["cc"]:
                    best[k] = fn
        top_fns = sorted(best.values(), key=lambda f: -f["cc"])[:top]
        print(f"  {a}:")
        for fn in top_fns:
            print(f"    CC={fn['cc']:4d} nloc={fn['nloc']:4d}  "
                  f"{fn['name']}  ({fn['file']})")
        print()


def run_audit(cfg: dict, run_id: str, verbose: bool = True) -> dict[str, list[dict]]:
    """Audit every chain of `run_id`. Returns arm -> [per-chain result].

    Callable from analyze.py (which passes the run's OWN config snapshot, so the
    `source_globs`/`base_ref` used here are the ones the run was configured with)
    as well as from this module's CLI."""
    branches = evolve_branches(cfg, run_id)
    if not branches:
        raise SystemExit(f"no branches for run {run_id!r}")
    if verbose:
        print(f"cumulative audit: base_ref .. chain tip over {len(branches)} chains")

    results: dict[str, list[dict]] = defaultdict(list)
    for repo, branch, arm, strategy, chain in branches:
        base = cfg["arms"][arm]["base_ref"]
        globs = cfg["arms"][arm].get("source_globs") or []
        r = audit_branch(repo, base, branch, globs)
        r.update(arm=arm, strategy=strategy, chain=chain, branch=branch)
        results[arm].append(r)
        if verbose:
            print(f"  {arm:12s} chain{chain:<2d} "
                  f"CC(all)={r['cc_sum_full']:6d}  CC(in-scope)={r['cc_sum_scoped']:6d}  "
                  f"fns={r['fns_touched_full']:4d}  "
                  f"orphan={r['orphan_lines']:5d}  opaque={r['opaque_lines']:5d}")
    return dict(results)


def markdown_section(results: dict[str, list[dict]]) -> list[str]:
    """The audit as summary.md lines, for analyze.py to append."""
    arms = sorted(results)
    out = [
        "## Cumulative change audit (base_ref -> chain tip)\n",
        "The per-checkpoint metrics are scoped (`source_globs`, a hotspot subsystem, a",
        "wired-node closure), which is what makes them comparable but also means an agent",
        "could hold them down by working where the scope does not reach. This section is",
        "the unscoped cross-check: ONE diff per chain from the branch start to its final",
        "commit, over EVERY changed file, with each changed line attributed to the function",
        "that contains it at the tip. `CC sum` adds the cyclomatic complexity of the",
        "DISTINCT functions touched — a function counts once however many checkpoints",
        "edited it, because the question is the complexity of the code that now exists.\n",
        "Lines that reach no function are reported, never dropped. `orphan` is inside a",
        "parsed file but outside every function body; `BRANCH TOKENS` counts the control",
        "flow among those lines (field initialisers, static blocks) and is the direct test",
        "for logic hidden where CC cannot see it — near zero means no such hiding.",
        "`opaque` is a file lizard cannot parse at all, where `YAML wiring edges` counts",
        "OfficeFloor's declared `next:`/`outputs:` control flow. That is a real branch count",
        "in a file no CC tool reads, but it is NOT a cyclomatic complexity and is never",
        "summed into one.\n",
        "| metric | " + " | ".join(arms) + " |",
        "|---|" + "---:|" * len(arms),
    ]
    for label, key in _REPORT_ROWS:
        cells = []
        for a in arms:
            m, sd = _agg(results[a], key)
            cells.append(f"{m:.1f} ± {sd:.1f}")
        out.append(f"| {label.replace('  ', '&nbsp;&nbsp;')} | " + " | ".join(cells) + " |")
    out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", help="which run to audit (default: latest)")
    ap.add_argument("--json", help="write the full per-chain result here")
    ap.add_argument("--top", type=int, default=15,
                    help="how many heaviest touched functions to list per arm")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    run_id = args.run_id or latest_run_id(cfg)
    if not run_id:
        raise SystemExit("no evolve/ branches found in the arm repos")

    print(f"# Cumulative change audit -- run {run_id}\n")
    results = run_audit(cfg, run_id)
    print_report(results, args.top)

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump({"run_id": run_id, "arms": results}, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
