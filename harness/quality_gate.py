"""Deterministic code-quality gate for the impact_gated REFACTOR step (design B).

WHY THIS EXISTS. The impact_gated pipeline gates each CHANGE on ImpactGate's structural
cost. An earlier design also told the agent that cost function; a Spring run then gamed it
exactly as Goodhart predicts, lowering the score by dispersing logic into greenfield classes
(WMC_other collapses to 1) and DUPLICATING code (reuse would mean editing a penalised large
class). The cost function is blind to duplication, so "minimise it" and "write clean code"
came apart. Design B removes the formula from the prompt and, instead, holds each REFACTOR's
own output to this gate, so a refactor cannot buy a lower impact score with slop.

WHAT IT CHECKS. A finding is a line the refactor ADDED (git diff HEAD..index, restricted to
the Java source dirs) that is EITHER part of a jscpd clone OR matches an ast-grep wasteful-
pattern rule. Scoping to added lines means pre-existing petclinic debt never blocks the
agent, and the signal points squarely at the refactor's own code. Empty findings => pass.
Non-empty => the findings render as review comments fed back for another turn.

LIMITATION (state it plainly). jscpd is token/line based, so this catches SYNTACTIC clones
only; semantic duplication (same behaviour, different tokens) slips through. The gate is a
guardrail against the specific cheap exploit, not a proof of good design.

DETERMINISM. Both tools are pinned (tools/package-lock.json) and asserted by
harness/quality_selftest.py (versions + golden fixtures, fail-closed). jscpd clone thresholds
are pinned in config (quality_gate.jscpd_min_tokens/min_lines) so a version-default change can
never silently move a verdict.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class Finding:
    path: str
    line: int
    kind: str        # "clone" | "smell"
    message: str


@dataclass
class QualityReview:
    passed: bool
    findings: list[Finding] = field(default_factory=list)
    added_lines: int = 0
    clone_finding_lines: int = 0
    smell_finding_lines: int = 0
    review_text: str = ""
    ran: bool = True          # False when NEITHER tool could run at all
    reason: str = ""          # why it could not run (ran is False)
    # Which halves actually ran. A PARTIAL gate still enforces on the half that worked
    # and never stops the run — but "clean" then means "clean as far as we could see",
    # and only these flags distinguish that from a genuinely clean change. They ride
    # into capture so a later analyze over the run branches can tell the difference
    # without re-running anything.
    clones_ran: bool = True
    smells_ran: bool = True


# --------------------------------------------------------------------------- #
# Added lines of the staged refactor (HEAD == the clean base, index == refactor)
# --------------------------------------------------------------------------- #
def _is_noncode(text: str) -> bool:
    """A line that must NOT be treated as duplicated CODE: blank, a comment (incl. the Apache
    license header every file in this repo carries verbatim), or a package/import declaration.
    WHY: jscpd tokenizes these, and the identical license header at the top of every file makes
    any NEW file's header a "clone" of every existing file's header — so a clean extract-a-class
    refactor (the move we WANT) would fail the gate on boilerplate it MUST include, not on any
    logic it duplicated. Observed at cp08 of blind-202609020135: 20/20 flagged lines were the
    license header + package/import, 0 real code. The gate is about duplicated logic, and
    duplicated headers/imports are neither slop nor the run-1 exploit, so they are excluded."""
    s = text.strip()
    if not s:
        return True
    if s.startswith(("//", "/*", "*")):   # line comment, block start /**, block body/end * ... */
        return True
    if s.startswith(("package ", "import ")):
        return True
    return False


def _added_lines(root: str, src_dirs: list[str]) -> set[tuple[str, int]]:
    """(relpath, new-line-number) for every CODE line the staged tree ADDS over HEAD, inside
    src_dirs. HEAD is the clean base the refactor was made on, so `git diff --cached` is exactly
    the refactor's delta. --unified=0 so hunk headers give exact new-line spans. Non-code lines
    (blank / comment / package / import — see `_is_noncode`) are excluded so the license header
    of a newly-created file cannot register as duplication."""
    argv = ["git", "-C", root, "diff", "--cached", "--unified=0", "--no-color", "--",
            *src_dirs]
    out = subprocess.run(argv, capture_output=True, text=True).stdout
    added: set[tuple[str, int]] = set()
    path: str | None = None
    new_ln = 0
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("@@"):
            # @@ -a,b +c,d @@  -> next added line is new-file line c
            try:
                plus = line.split("+", 1)[1]
                new_ln = int(plus.split(",", 1)[0].split(" ", 1)[0])
            except (IndexError, ValueError):
                new_ln = 0
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if path is not None and new_ln and not _is_noncode(line[1:]):
                added.add((path, new_ln))
            new_ln += 1
    return added


# --------------------------------------------------------------------------- #
# jscpd clones  (rich: line set + human-readable duplicate pairs for the review)
# --------------------------------------------------------------------------- #
_SCRATCH = ".jscpd-quality"


def _line(fobj, base):
    loc = fobj.get(base + "Loc")
    if isinstance(loc, dict) and loc.get("line") is not None:
        return loc["line"]
    v = fobj.get(base)
    return v if isinstance(v, int) else None


def _clone_lines(root: str, src_dirs: list[str], jscpd_bin: str,
                 min_tokens: int, min_lines: int) -> tuple[set[tuple[str, int]], list[str]] | None:
    """Return ({(repo-relative path, line) clone lines}, [pair descriptions]) or None if jscpd
    could not run for ANY dir. Thresholds are passed explicitly (never defaulted) so verdicts
    are version-stable. jscpd emits paths relative to the scanned dir, so each dir is scanned
    separately (cwd=root, relative arg) and its own prefix re-joined to get repo-relative paths.
    Clones spanning two different src_dirs are therefore not detected; src_dirs is normally one."""
    lines: set[tuple[str, int]] = set()
    pairs: list[str] = []
    ran = False
    for d in src_dirs:
        out_dir = os.path.join(root, _SCRATCH, d.replace(os.sep, "_"))
        cmd = [jscpd_bin, "--mode", "strict", "--reporters", "json", "--silent",
               "--min-tokens", str(min_tokens), "--min-lines", str(min_lines),
               "--output", out_dir, "--format", "java", d]
        try:
            subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        report = os.path.join(out_dir, "jscpd-report.json")
        if not os.path.isfile(report):
            continue
        try:
            with open(report) as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        ran = True
        for dup in data.get("duplicates", []):
            span = []
            for side in ("firstFile", "secondFile"):
                f = dup.get(side, {})
                name, start, end = f.get("name"), _line(f, "start"), _line(f, "end")
                if not (name and start and end):
                    span.append(None)
                    continue
                rel = os.path.normpath(os.path.join(d, name))  # jscpd name is relative to d
                for ln in range(int(start), int(end) + 1):
                    lines.add((rel, ln))
                span.append(f"{rel}:{start}-{end}")
            if span[0] and span[1]:
                pairs.append(f"{span[0]}  <=>  {span[1]}")
    return (lines, pairs) if ran else None


# --------------------------------------------------------------------------- #
# ast-grep smells  (rich: (line -> message))
# --------------------------------------------------------------------------- #
def _smell_lines(root: str, src_dirs: list[str], sg_bin: str,
                 rules_dir: str) -> dict[tuple[str, int], str] | None:
    """{(repo-relative path, line): message} for every ast-grep rule match, or None if it did
    not run. The pinned ast-grep takes `-r` as a single rule FILE, so a directory of (possibly
    multi-document) rule files is loaded via a generated project config (ruleDirs) and
    `scan -c`. Paths come back relative to cwd=root; line numbers are 0-based -> +1."""
    if not rules_dir or not os.path.isdir(rules_dir):
        return None
    import shutil
    import tempfile
    cfg_dir = tempfile.mkdtemp(prefix="pe-sgcfg-")
    try:
        with open(os.path.join(cfg_dir, "sgconfig.yml"), "w") as fh:
            fh.write("ruleDirs:\n  - " + os.path.abspath(rules_dir) + "\n")
        cmd = [sg_bin, "scan", "--json", "-c", os.path.join(cfg_dir, "sgconfig.yml"),
               *src_dirs]
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None
    finally:
        shutil.rmtree(cfg_dir, ignore_errors=True)
    # A non-zero exit is ast-grep REFUSING to scan, not a clean scan with no hits: it
    # writes the reason to stderr and leaves stdout empty, which parses as zero matches
    # and is indistinguishable from "this code is clean". One unparseable rule aborts
    # the WHOLE directory (exit 8), so a single bad pattern would silently switch the
    # smell half off — for the metric AND for this gate. None means "did not run"; the
    # caller must not read it as a pass.
    if proc.returncode != 0:
        first = ((proc.stderr or "").strip().splitlines() or [""])[0]
        print(f"    ! ast-grep exited {proc.returncode}; smell detection DID NOT RUN "
              f"({first[:160]})", flush=True)
        return None
    try:
        matches = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    out: dict[tuple[str, int], str] = {}
    for m in matches:
        f = m.get("file")
        rng = m.get("range", {})
        start = (rng.get("start") or {}).get("line")
        end = (rng.get("end") or {}).get("line")
        if not (f and start is not None and end is not None):
            continue
        rel = os.path.relpath(f, root) if os.path.isabs(f) else f
        msg = m.get("message") or m.get("ruleId") or m.get("rule") or "wasteful pattern"
        # ast-grep `range` lines are 0-based; +1 to match git/jscpd (1-based).
        for ln in range(int(start) + 1, int(end) + 2):
            out.setdefault((rel, ln), msg)
    return out


def _pmd_lines(root: str, src_dirs: list[str], pmd_bin: str,
               ruleset: str) -> dict[tuple[str, int], str] | None:
    """{(repo-relative path, 1-based line): message} for every PMD violation, or None if
    PMD did not run.

    PMD replaces ast-grep as the smell detector: SlopCodeBench's 137 Verbosity rules are
    `language: python` and cannot match these Java arms, while PMD ships a mature Java
    ruleset whose "unnecessary/useless/redundant" rules are the same construct. The
    curated subset lives in `pmd-rules/java-wasteful.xml` (committed; it decides verdicts,
    so it travels with the run like the ast-grep rules did).

    Two traps, both of the "did not run reads as found nothing" family that already bit
    this metric twice:
      * PMD exits 4 when it finds violations. Without --no-fail-on-violation a returncode
        check would treat every DIRTY scan as a failed one and report zero smells.
      * a ruleset naming an unknown rule still runs, reporting only the rules it resolved.
        `processingErrors` and the parse below are checked so a broken ruleset surfaces.
    Analysis is source-only (no --aux-classpath): checkpoint trees are materialised but
    never compiled, and type resolution is not needed by these rules.
    """
    if not ruleset or not os.path.isfile(ruleset):
        return None
    # ABSOLUTE, always. PMD is invoked with cwd=<arm worktree>, so a config-relative
    # ruleset ("pmd-rules/java-wasteful.xml") resolves against the WORKTREE and PMD
    # exits 1 with "Cannot resolve rule/ruleset reference" - smell detection silently
    # stops running. The isfile() guard above passes because it resolves against the
    # harness cwd, which is exactly what makes this fail only once PMD is spawned.
    ruleset = os.path.abspath(ruleset)
    cmd = [pmd_bin, "check", "-f", "json", "-R", ruleset,
           "--no-fail-on-violation", "--no-progress"]
    for d in src_dirs:
        cmd += ["-d", d]
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=900)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        first = ((proc.stderr or "").strip().splitlines() or [""])[0]
        print(f"    ! pmd exited {proc.returncode}; smell detection DID NOT RUN "
              f"({first[:160]})", flush=True)
        return None
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    out: dict[tuple[str, int], str] = {}
    for f in report.get("files", []):
        path = f.get("filename") or ""
        rel = os.path.relpath(path, root) if os.path.isabs(path) else path
        for v in f.get("violations", []):
            begin, end = v.get("beginline"), v.get("endline")
            if begin is None:
                continue
            msg = v.get("rule") or "wasteful pattern"
            # PMD lines are already 1-based. The curated ruleset deliberately excludes
            # class-level rules, so spans stay small (max 3 lines observed) and a single
            # finding cannot flood a LINE-counted metric.
            for ln in range(int(begin), int(end or begin) + 1):
                out.setdefault((rel, ln), msg)
    return out


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #
def review(root: str, src_dirs: list[str], tools: dict, qcfg: dict) -> QualityReview:
    """Run the quality gate over the staged refactor in `root`. Findings = added lines that
    are clones or smells.

    If NEITHER tool can run, `ran=False` — the gate cannot enforce at all, so it must not
    silently pass; the caller decides (run_experiment logs it and moves on rather than
    killing the chain).

    If ONE tool can run, the gate enforces on that half and sets `clones_ran`/`smells_ran`
    accordingly. This is deliberately NOT fail-closed: a run must never die because a
    detector broke, and every checkpoint is committed to the run branch, so a later
    `analyze` can recompute the missing half from the branches once the tooling is fixed.
    The flags are what make that recoverable — without them a partial pass is
    indistinguishable from a clean one."""
    added = _added_lines(root, src_dirs)

    clones = _clone_lines(root, src_dirs, tools.get("jscpd", "jscpd"),
                          int(qcfg.get("jscpd_min_tokens", 50)),
                          int(qcfg.get("jscpd_min_lines", 5)))
    # Smell detector: PMD when configured (Java rules that can actually fire on these
    # arms), else the legacy ast-grep path. Selecting on tools.pmd rather than a flag
    # keeps a run's config snapshot self-describing — an old run replays with ast-grep,
    # a new one with PMD, and neither silently changes meaning.
    if tools.get("pmd"):
        smells = _pmd_lines(root, src_dirs, tools["pmd"], tools.get("pmd_rules", ""))
    else:
        smells = _smell_lines(root, src_dirs, tools.get("astgrep", "sg"),
                              tools.get("astgrep_rules", ""))
    # Clean scratch so it can never leak into a commit.
    import shutil
    shutil.rmtree(os.path.join(root, ".jscpd-quality"), ignore_errors=True)

    if clones is None and smells is None:
        return QualityReview(passed=False, ran=False,
                             reason="neither jscpd nor ast-grep produced output "
                                    "(gate cannot enforce)",
                             clones_ran=False, smells_ran=False)

    if clones is None or smells is None:
        # Deliberately NOT fail-closed: a half-working gate must never stop a run that
        # is otherwise fine. Enforce on the half that works, record that the other did
        # not, and let post-hoc analysis over the branches decide what to trust.
        half = "ast-grep/smells" if smells is None else "jscpd/clones"
        print(f"    quality-gate: {half} did not run; enforcing on the other half only "
              f"(recorded in capture)", flush=True)

    clone_lines = clones[0] if clones else set()
    clone_pairs = clones[1] if clones else []
    smell_map = smells or {}

    findings: list[Finding] = []
    for key in sorted(added):
        if key in clone_lines:
            findings.append(Finding(key[0], key[1], "clone", "part of a duplicated code block"))
        elif key in smell_map:
            findings.append(Finding(key[0], key[1], "smell", smell_map[key]))

    clone_n = sum(1 for f in findings if f.kind == "clone")
    smell_n = sum(1 for f in findings if f.kind == "smell")
    return QualityReview(
        passed=not findings,
        findings=findings,
        added_lines=len(added),
        clone_finding_lines=clone_n,
        smell_finding_lines=smell_n,
        review_text=render(findings, clone_pairs),
        clones_ran=clones is not None,
        smells_ran=smells is not None,
    )


def render(findings: list[Finding], clone_pairs: list[str]) -> str:
    """Findings as review comments the refactor agent can act on. Clone lines are grouped
    into contiguous ranges per file; the duplicate PAIRS are listed so the agent knows what
    to consolidate. Smells are listed per rule message."""
    if not findings:
        return "No quality issues found."
    out: list[str] = []
    clones = [f for f in findings if f.kind == "clone"]
    smells = [f for f in findings if f.kind == "smell"]
    if clones:
        out.append("Duplicated code you introduced (consolidate instead of copying):")
        for r in _ranges(clones):
            out.append(f"  - {r}")
        for p in clone_pairs:
            out.append(f"    duplicate block: {p}")
    if smells:
        out.append("Static code smells you introduced:")
        seen = set()
        for f in smells:
            tag = (f.path, f.line, f.message)
            if tag in seen:
                continue
            seen.add(tag)
            out.append(f"  - {f.path}:{f.line} — {f.message}")
    return "\n".join(out)


def _ranges(findings: list[Finding]) -> list[str]:
    """Collapse per-file (path, line) findings into 'path:a-b' contiguous ranges."""
    by_path: dict[str, list[int]] = {}
    for f in findings:
        by_path.setdefault(f.path, []).append(f.line)
    out: list[str] = []
    for path in sorted(by_path):
        lns = sorted(set(by_path[path]))
        start = prev = lns[0]
        for ln in lns[1:] + [None]:
            if ln is not None and ln == prev + 1:
                prev = ln
                continue
            out.append(f"{path}:{start}" if start == prev else f"{path}:{start}-{prev}")
            if ln is not None:
                start = prev = ln
    return out


def summary(qr: QualityReview) -> dict:
    """Compact record for capture (one entry per refactor's quality outcome)."""
    return {
        "passed": qr.passed,
        "ran": qr.ran,
        "added_lines": qr.added_lines,
        "clone_finding_lines": qr.clone_finding_lines,
        "smell_finding_lines": qr.smell_finding_lines,
        "findings": [{"path": f.path, "line": f.line, "kind": f.kind, "message": f.message}
                     for f in qr.findings],
        "reason": qr.reason or None,
        # Which halves actually ran, so a later analyze over the run branches can tell a
        # genuinely clean refactor from one the gate could only half-check.
        "clones_ran": qr.clones_ran,
        "smells_ran": qr.smells_ran,
    }
