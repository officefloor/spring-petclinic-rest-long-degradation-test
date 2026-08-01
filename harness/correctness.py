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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

CLASS_RE = re.compile(r"Cp0*(\d+)Tests", re.IGNORECASE)
CAT_RE = re.compile(r"(core|error|functionality)", re.IGNORECASE)


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
        except ET.ParseError:
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


def run_tests(worktree: str, checkpoint_k: int, cfg: dict) -> TestOutcome:
    """Run the accumulated suite cp01..cpK and score by category. The full build +
    test console is retained on the outcome (`console`) so it can be captured — a
    test that errors before producing a Surefire report (e.g. context startup)
    would otherwise leave no trace beyond a lower selected-count."""
    ok, build_out = build(worktree, cfg)
    console = f"$ {' '.join(cfg['build']['cmd'])}\n{build_out}"
    if not ok:
        return TestOutcome(build_ok=False, error=f"build failed:\n{build_out[-1600:]}",
                           build_output=build_out[-1600:], console=console)

    _clear_surefire(worktree, cfg)
    tags = ",".join(f"cp{str(i).zfill(2)}" for i in range(1, checkpoint_k + 1))
    tmpl = cfg["build"]["test_cmd_template"]
    cmd = [part.replace("{tags}", tags) for part in tmpl]
    try:
        tproc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                               timeout=cfg["build"].get("test_timeout", 3600))
        console += f"\n$ {' '.join(cmd)}\n{(tproc.stdout or '') + (tproc.stderr or '')}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return TestOutcome(build_ok=True, error=f"test run failed to launch/timed out: {exc}",
                           console=console + f"\n$ {' '.join(cmd)}\n[launch/timeout] {exc}")

    results, detail = _parse_surefire(worktree, cfg)
    outcome = score_results(results, checkpoint_k)
    outcome.detail = detail
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
