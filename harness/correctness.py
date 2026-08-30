"""Build + acceptance-test gate and correctness scoring.

Tests are experimenter-owned and black-box (they hit the REST API), so Spring
and OfficeFloor are judged by identical externals. Test categories follow
SlopCodeBench: Core, Error, Functionality (hidden exhaustive), Regression (all
tests from prior checkpoints).

Contract with the repo (documented in README):
  * One test class per checkpoint, named Cp03Tests, tagged @Tag("cp03") so the
    harness can select only cp01..cpK at checkpoint K.
  * Category is encoded in the METHOD name: methods start with core*, error* or
    functionality* (Surefire XML records the method name but not JUnit tags, so
    the prefix is how we classify).
  * A test whose checkpoint < K counts as Regression at checkpoint K, whatever
    its own category prefix.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

CLASS_RE = re.compile(r"Cp0*(\d+)Tests", re.IGNORECASE)
CAT_RE = re.compile(r"(core|error|functionality)", re.IGNORECASE)

# Signatures of a gate run that ABORTED rather than ran: the Surefire fork died
# (JVM crash / SIGABRT / OOM-killer), so some or all classes produced no report.
# These are infrastructure faults, NOT the agent's code failing -- see
# `_gate_invalid`. Kept narrow and Surefire-specific so ordinary test-failure
# output (which the agent's own code can emit) can never match.
_CRASH_MARKERS = (
    "The forked VM terminated without properly saying goodbye",
    "Error occurred in starting fork",
    "Corrupted STDOUT by directly writing to native stream in forked JVM",
    "Crashed tests:",
)


@dataclass
class TestOutcome:
    build_ok: bool = False
    error: str = ""
    build_output: str = ""                             # compiler output tail (quick display)
    console: str = ""                                  # FULL build + test console (→ cpNN.build.log)
    passing: set[str] = field(default_factory=set)     # "class#method" that passed
    results: dict[str, bool] = field(default_factory=dict)  # RAW {test_id: passed} — the atom
    detail: list[dict] = field(default_factory=list)   # per-test time + failure text
    total_selected: int = 0                            # tests actually run
    gate_invalid: bool = False                         # run ABORTED -> results unusable (not a failure)
    gate_attempts: int = 0                             # test-command tries spent (>1 = a retry happened)
    # category pass/total at the *current* checkpoint
    core_pass: int = 0
    core_total: int = 0
    error_pass: int = 0
    error_total: int = 0
    func_pass: int = 0
    func_total: int = 0
    regr_pass: int = 0
    regr_total: int = 0

    @property
    def all_pass(self) -> bool:
        return self.total_selected > 0 and len(self.passing) == self.total_selected

    @property
    def iso_pass(self) -> bool:
        """Non-regression tests (this checkpoint's core+error+func) all green."""
        cur_total = self.core_total + self.error_total + self.func_total
        cur_pass = self.core_pass + self.error_pass + self.func_pass
        return cur_total > 0 and cur_pass == cur_total

    @property
    def core_all_pass(self) -> bool:
        return self.core_total > 0 and self.core_pass == self.core_total


def build(worktree: str, cfg: dict) -> tuple[bool, str]:
    """Returns (ok, full_combined_output). The caller keeps the whole console; a
    truncated tail is derived from it for quick display."""
    cmd = cfg["build"]["cmd"]
    try:
        proc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                              timeout=cfg["build"].get("timeout", 1800))
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"build failed to launch/timed out: {exc}"
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _clear_surefire(worktree: str, cfg: dict) -> None:
    d = os.path.join(worktree, cfg["build"]["surefire_dir"])
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


def _parse_surefire(worktree: str, cfg: dict) -> tuple[dict[str, bool], list[dict]]:
    """Return ({test_id: passed}, detail) across all TEST-*.xml reports, where
    detail carries per-test timing + failure text (captured because the XML is a
    build artifact that does not survive into the checkpoint commit)."""
    results: dict[str, bool] = {}
    detail: list[dict] = []
    pattern = os.path.join(worktree, cfg["build"]["surefire_dir"], "TEST-*.xml")
    for report in glob.glob(pattern):
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError as e:
            # An unparseable report would otherwise silently shrink total_selected
            # (the "test left no trace" failure run_tests wants to avoid). Record it
            # as a report-level error: passed=None keeps it OUT of `results`/scoring
            # but visible in the captured detail.
            detail.append({"test_id": os.path.basename(report), "passed": None,
                           "skipped": None, "time": 0.0,
                           "failure": f"unparseable surefire report: {e}"[:500],
                           "report_error": True})
            continue
        for case in root.iter("testcase"):
            cls = case.get("classname", "")
            name = case.get("name", "")
            test_id = f"{cls}#{name}"
            t = float(case.get("time", 0) or 0)
            if any(c.tag == "skipped" for c in case):
                # A skipped test is neither a pass nor a fail, so it stays OUT of
                # `results` (and thus out of scoring/total_selected) — but recorded
                # in `detail` so "skipped" is distinguishable from "never selected".
                detail.append({"test_id": test_id, "passed": None, "skipped": True,
                               "time": t, "failure": None})
                continue
            fail_el = next((c for c in case if c.tag in ("failure", "error")), None)
            passed = fail_el is None
            results[test_id] = passed
            detail.append({
                "test_id": test_id,
                "passed": passed,
                "skipped": False,
                "time": t,
                "failure": None if passed else
                (f"{fail_el.get('type', '')}: {fail_el.get('message', '')}".strip()[:500]),
            })
    return results, detail


def score_results(results: dict[str, bool], checkpoint_k: int) -> TestOutcome:
    """Categorise a raw {test_id: passed} map into a TestOutcome (Core/Error/Func/
    Regression), independent of HOW the map was obtained. Called by run_tests at
    run time AND by analyze --recompute from the captured raw results, so the
    scoring rule is defined once."""
    outcome = TestOutcome(build_ok=True)
    outcome.results = dict(results)
    outcome.total_selected = len(results)
    outcome.passing = {tid for tid, ok in results.items() if ok}
    for test_id, passed in results.items():
        cls_part, _, method = test_id.partition("#")
        cls = cls_part.split(".")[-1]
        m = CLASS_RE.search(cls)
        if not m:
            continue
        cp = int(m.group(1))
        cm = CAT_RE.match(method)
        cat = cm.group(1).lower() if cm else "functionality"
        if cp < checkpoint_k:
            outcome.regr_total += 1
            outcome.regr_pass += int(passed)
        elif cat == "core":
            outcome.core_total += 1
            outcome.core_pass += int(passed)
        elif cat == "error":
            outcome.error_total += 1
            outcome.error_pass += int(passed)
        else:
            outcome.func_total += 1
            outcome.func_pass += int(passed)
    return outcome


def _gate_invalid(results: dict[str, bool], test_console: str) -> str:
    """Reason this gate run is UNUSABLE, or "" if it is a valid measurement.

    The distinction that matters: a test that RAN and failed is the signal the
    experiment exists to capture and must never be retried away. A run that
    ABORTED produced no verdict at all, and scoring it silently reads the missing
    results as "every prior rule broke" (`count_regressions` is
    `prior_passing - now_passing`). Only the latter is retried.

    Two independent detectors, because a fork can die either before any class runs
    (no reports at all) or partway (some classes reported, the rest lost):
      * no results while the build compiled -- at checkpoint K the authored suite
        always holds at least cp01's test, so an empty map cannot be legitimate.
        (A *failed build* returns earlier, with build_ok=False; that IS the agent
        breaking compilation and stays scored.)
      * a Surefire fork-death marker in the console, which is the only way a
        partial run announces that the rest of the suite never got a verdict.
    """
    if not results:
        return "gate produced no test results (fork died before any class reported)"
    hit = next((m for m in _CRASH_MARKERS if m in test_console), None)
    return f"gate run aborted mid-suite: {hit!r}" if hit else ""


def run_tests(worktree: str, checkpoint_k: int, cfg: dict) -> TestOutcome:
    """Run the accumulated suite cp01..cpK and score by category. The full build +
    test console is retained on the outcome (`console`) so it can be captured — a
    test that errors before producing a Surefire report (e.g. context startup)
    would otherwise leave no trace beyond a lower selected-count.

    An ABORTED run (Surefire fork crash) is retried up to `build.test_attempts`
    times; a run whose tests merely FAIL is returned on the first attempt, always.
    If every attempt aborts the outcome is flagged `gate_invalid` and carries NO
    correctness verdict — the checkpoint becomes missing data rather than a
    fabricated mass regression."""
    ok, build_out = build(worktree, cfg)
    console = f"$ {' '.join(cfg['build']['cmd'])}\n{build_out}"
    if not ok:
        return TestOutcome(build_ok=False, error=f"build failed:\n{build_out[-1600:]}",
                           build_output=build_out[-1600:], console=console)

    tags = ",".join(f"cp{str(i).zfill(2)}" for i in range(1, checkpoint_k + 1))
    tmpl = cfg["build"]["test_cmd_template"]
    cmd = [part.replace("{tags}", tags) for part in tmpl]
    attempts = max(1, int(cfg["build"].get("test_attempts", 3)))
    backoff = int(cfg["build"].get("test_retry_seconds", 30))

    outcome = TestOutcome(build_ok=True)
    for attempt in range(1, attempts + 1):
        _clear_surefire(worktree, cfg)
        header = f"\n$ {' '.join(cmd)}" + (f"   [gate attempt {attempt}/{attempts}]"
                                           if attempt > 1 else "")
        try:
            tproc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                                   timeout=cfg["build"].get("test_timeout", 3600))
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            # Not retried: a missing command will not fix itself, and a timeout has
            # already burned test_timeout (retrying could multiply it by attempts).
            return TestOutcome(build_ok=True, gate_invalid=True, gate_attempts=attempt,
                               error=f"test run failed to launch/timed out: {exc}",
                               console=console + f"{header}\n[launch/timeout] {exc}")
        test_console = (tproc.stdout or "") + (tproc.stderr or "")
        console += f"{header}\n{test_console}"

        results, detail = _parse_surefire(worktree, cfg)
        reason = _gate_invalid(results, test_console)
        outcome = score_results(results, checkpoint_k)
        outcome.detail = detail
        outcome.gate_attempts = attempt
        if not reason:
            outcome.console = console
            return outcome
        outcome.gate_invalid = True
        outcome.error = f"{reason} (attempt {attempt}/{attempts}, exit {tproc.returncode})"
        if attempt < attempts:
            print(f"    ! {outcome.error} — retrying gate in {backoff}s")
            time.sleep(backoff)

    outcome.console = console
    return outcome


def normalized_change(prior_passing: set[str], now_passing: set[str],
                      target_total: int) -> float:
    """SWE-CI asymmetric Normalized Change in [-1, 1].

      improvement: (passed - baseline) / (target - baseline)
      regression:  (passed - baseline) / baseline
    """
    baseline = len(prior_passing)
    passed = len(now_passing)
    if passed >= baseline:
        denom = target_total - baseline
        return 1.0 if denom <= 0 else (passed - baseline) / denom
    return -1.0 if baseline <= 0 else (passed - baseline) / baseline


def count_regressions(prior_passing: set[str], now_passing: set[str]) -> int:
    """Tests green before this checkpoint that are red after it."""
    return len(prior_passing - now_passing)


def test_checkpoint(test_id: str) -> int | None:
    """The checkpoint number a test belongs to, from its class name CpNNTests."""
    cls = test_id.split("#", 1)[0].split(".")[-1]
    m = CLASS_RE.search(cls)
    return int(m.group(1)) if m else None


def count_true_regressions(prior_passing: set[str], now_passing: set[str],
                           mutated_cps) -> int:
    """Regressions on the surface a mutative checkpoint did NOT intend to change.

    A mutative checkpoint deliberately rewrites the rules in `mutated_cps`, so its
    prior tests are expected to change. A regression in one of THOSE classes is
    intended, not a fault. A regression in any OTHER prior checkpoint's tests is a
    true regression: the agent broke a rule it was not asked to touch. This is the
    safety signal a purely additive run cannot produce."""
    mut = set(mutated_cps or ())
    return sum(1 for t in (prior_passing - now_passing) if test_checkpoint(t) not in mut)


def outcome_row(outcome: "TestOutcome", prior_passing: set[str], mutated_cps=()) -> dict:
    """Map a scored TestOutcome to the flat correctness row fields (incl. Normalized
    Change + regressions vs prior_passing). One definition, called by both the
    runner (run time) and analyze (recompute), so the schema lives in one place.

    An aborted gate (`gate_invalid`) yields BLANK correctness fields: it has no
    verdict to report, and the empty result set would otherwise be scored as a
    regression on every prior rule. `gate_invalid` marks the hole so analyze can
    exclude it from the correctness aggregates instead of reading blanks as
    failures — and so it stays visible rather than becoming a quiet zero."""
    if outcome.gate_invalid:
        blanks = {f: "" for f in (
            "total_selected", "strict_pass", "iso_pass", "core_pass",
            "core_p", "core_t", "error_p", "error_t", "func_p", "func_t",
            "regr_p", "regr_t", "normalized_change", "regressions", "true_regressions")}
        return {"build_ok": outcome.build_ok, "gate_invalid": True, **blanks}
    return {
        "build_ok": outcome.build_ok,
        "gate_invalid": False,
        "total_selected": outcome.total_selected,
        "strict_pass": outcome.all_pass,
        "iso_pass": outcome.iso_pass,
        "core_pass": outcome.core_all_pass,
        "core_p": outcome.core_pass, "core_t": outcome.core_total,
        "error_p": outcome.error_pass, "error_t": outcome.error_total,
        "func_p": outcome.func_pass, "func_t": outcome.func_total,
        "regr_p": outcome.regr_pass, "regr_t": outcome.regr_total,
        "normalized_change": round(
            normalized_change(prior_passing, outcome.passing, outcome.total_selected), 4),
        "regressions": count_regressions(prior_passing, outcome.passing),
        "true_regressions": count_true_regressions(prior_passing, outcome.passing, mutated_cps),
    }
