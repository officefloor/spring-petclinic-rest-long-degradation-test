"""Class-shape audit: WHAT KIND of class does an arm add to hold a new rule?

`cumulative_impact` answers how much complexity a run added and where it landed.
This answers what it was made of. The two arms are both Spring Boot applications,
so the same vocabulary applies to each, and the interesting differences are the
ones an experienced reader of that framework would notice in review:

  spring-bean     carries a stereotype (@Component/@Service/@RestController/
                  @ControllerAdvice/@Configuration/...). Container-managed, so it
                  can be injected, mocked, proxied and configured.
  static-util     every method is static. Scores beautifully on the structural
                  impact formula (a static method in a small class has near-zero
                  WMC_other) but is procedural: no injection, no seam for a test
                  double, no participation in transactions or AOP.
  instance-class  ordinary object with instance methods. OfficeFloor's wired
                  functions are these -- the framework instantiates them.
  exception       a domain exception, i.e. the rule reports failure by throwing
                  through the app's @ControllerAdvice rather than returning a
                  bare ResponseEntity status.
  entity / annotation / interface / other

The counts are per CHAIN, over classes the run CREATED (present at the tip and
absent from base_ref), excluding generated code (`rest/dto`, `rest/api`). What to
read: a shift between these categories is a shift in idiom, and idiom is the part
of "is this code a competent developer would recognise" that can be counted.
Report the SPREAD, not just the mean -- ten chains from one prompt choosing
different mechanisms is itself the finding.

Methods come from lizard (the harness's pinned parser), never a regex over the
source: a `private static final Map<..> X = Map.of(` line reads exactly like a
static method declaration to a grep, and counting those makes almost every class
look like a static utility.

Usage:
    python -m harness.class_shape --config config.yaml [--run-id ID] [--json OUT]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import statistics
import subprocess

import lizard
import yaml

from .cumulative_impact import evolve_branches, latest_run_id

# Generated sources. Regenerated wholesale from openapi.yml, so they say nothing
# about how the agent chose to express a rule.
GENERATED = re.compile(r"/rest/(dto|api)/")

_STEREOTYPE = re.compile(r"@(Component|Service|Repository|RestController|Controller|"
                         r"ControllerAdvice|RestControllerAdvice|Configuration|Bean)\b")
_ENTITY = re.compile(r"@(Entity|Embeddable|MappedSuperclass)\b")

# Order the summary lists categories in: idiom-carrying first, filler last.
CATEGORIES = ["spring-bean", "static-util", "instance-class", "exception",
              "entity", "annotation", "interface", "other", "unparsed"]


def _git(repo: str, args: list[str]) -> str:
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, timeout=120).stdout


def classify(path: str, code: str) -> str:
    """The category of the PRIMARY class in `path`.

    One label per file: a file whose top-level type is an annotation but which
    also declares its package-private validator counts once, as `annotation`.
    Splitting per declared type would double-count that idiomatic pairing.
    """
    try:
        fns = list(lizard.analyze_file.analyze_source_code(path, code).function_list)
    except Exception:
        return "unparsed"

    if _STEREOTYPE.search(code):
        return "spring-bean"
    if _ENTITY.search(code):
        return "entity"
    if "@interface" in code:
        return "annotation"

    cls = path.rsplit("/", 1)[-1][:-len(".java")]
    if path.endswith("Exception.java") or re.search(r"\bclass\s+\w*Exception\b", code):
        return "exception"
    if re.search(rf"\binterface\s+{re.escape(cls)}\b", code):
        return "interface"

    lines = code.splitlines()
    instance = static = 0
    for fn in fns:
        short = fn.name.split("::")[-1]
        if short == cls:
            # Constructor: neutral. A static-utility class conventionally has a
            # private one, so counting it as an instance method would misfile
            # every such class. (str.capitalize() cannot be used to detect this
            # -- it lowercases the tail, so "CityCodes" != "Citycodes".)
            continue
        # The signature line plus the one above it, so an annotation or a
        # modifier list wrapped onto its own line is still seen.
        sig = " ".join(lines[max(0, fn.start_line - 2):fn.start_line])
        if re.search(r"\bstatic\b", sig):
            static += 1
        else:
            instance += 1

    if static and not instance:
        return "static-util"
    if instance:
        return "instance-class"
    return "other"


def audit_branch(repo: str, base: str, tip: str) -> collections.Counter:
    """Category counts over the production classes this chain CREATED."""
    base_files = set(_git(repo, ["ls-tree", "-r", "--name-only", base]).split())
    changed = _git(repo, ["diff", "--name-only", f"{base}..{tip}",
                          "--", "src/main/java"]).split()
    counts: collections.Counter = collections.Counter()
    for path in changed:
        if not path.endswith(".java") or GENERATED.search(path) or path in base_files:
            continue
        code = _git(repo, ["show", f"{tip}:{path}"])
        if code:
            counts[classify(path, code)] += 1
    return counts


def run_audit(cfg: dict, run_id: str, verbose: bool = True) -> dict[str, list[dict]]:
    """arm -> [per-chain {category: count}]."""
    branches = evolve_branches(cfg, run_id)
    if not branches:
        raise SystemExit(f"no branches for run {run_id!r}")
    if verbose:
        print(f"class-shape audit: new classes over {len(branches)} chains")
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for repo, branch, arm, _strategy, chain in branches:
        counts = audit_branch(repo, cfg["arms"][arm]["base_ref"], branch)
        rec = {"chain": chain, "total": sum(counts.values()), **dict(counts)}
        out[arm].append(rec)
        if verbose:
            top = "  ".join(f"{k}={counts[k]}" for k in CATEGORIES if counts[k])
            print(f"  {arm:12s} chain{chain:<2d} total={rec['total']:3d}  {top}")
    return dict(out)


def _stats(rows: list[dict], key: str) -> tuple[float, float, int, int]:
    v = [r.get(key, 0) for r in rows]
    sd = statistics.stdev(v) if len(v) > 1 else 0.0
    return statistics.mean(v), sd, min(v), max(v)


def markdown_section(results: dict[str, list[dict]]) -> list[str]:
    arms = sorted(results)
    out = [
        "## Class shape (what kind of class holds a new rule)\n",
        "Per chain, over production classes the run CREATED (present at the tip, absent",
        "from `base_ref`), excluding generated `rest/dto` and `rest/api`. Category is",
        "decided from lizard's function list, not a regex — a `static final` FIELD",
        "initialiser reads like a static method to a grep, which makes nearly every class",
        "look like a utility.\n",
        "`static-util` is the one to watch: it scores well on the structural-impact",
        "formula (a static method in a small class has near-zero `WMC_other`) while giving",
        "up injection, test seams, proxying and transaction participation. A run that",
        "lowers impact by turning beans into statics has changed its score without",
        "improving the code. `exception` counts rules that report failure by throwing",
        "through the app's `@ControllerAdvice` rather than returning a bare status.\n",
        "Read the range as well as the mean: ten chains from ONE prompt picking different",
        "mechanisms means the prompt fixed the objective but not the idiom.\n",
        "| arm/category | " + " | ".join(f"{a} mean" for a in arms)
        + " | " + " | ".join(f"{a} range" for a in arms) + " |",
        "|---|" + "---:|" * len(arms) + "---:|" * len(arms),
    ]
    present = [c for c in CATEGORIES
               if any(any(r.get(c, 0) for r in results[a]) for a in arms)]
    for cat in ["total"] + present:
        means, ranges = [], []
        for a in arms:
            m, _sd, lo, hi = _stats(results[a], cat)
            means.append(f"{m:.1f}")
            ranges.append(f"{lo}–{hi}")
        label = "**total**" if cat == "total" else cat
        out.append(f"| {label} | " + " | ".join(means) + " | " + " | ".join(ranges) + " |")
    out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", help="which run to audit (default: latest)")
    ap.add_argument("--json", help="write the per-chain counts here")
    args = ap.parse_args()

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    run_id = args.run_id or latest_run_id(cfg)
    if not run_id:
        raise SystemExit("no evolve/ branches found in the arm repos")

    print(f"# Class-shape audit -- run {run_id}\n")
    results = run_audit(cfg, run_id)
    print()
    print("\n".join(markdown_section(results)))

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump({"run_id": run_id, "arms": results}, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
