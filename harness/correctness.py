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
    passing: set[str] = field(default_factory=set)     # "class#method" that passed
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
    cmd = cfg["build"]["cmd"]
    try:
        proc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                              timeout=cfg["build"].get("timeout", 1800))
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"build failed to launch/timed out: {exc}"
    if proc.returncode != 0:
        return False, f"build exit {proc.returncode}: {proc.stdout[-800:]}\n{proc.stderr[-800:]}"
    return True, ""


def _clear_surefire(worktree: str, cfg: dict) -> None:
    d = os.path.join(worktree, cfg["build"]["surefire_dir"])
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


def _parse_surefire(worktree: str, cfg: dict) -> dict[str, bool]:
    """Return {test_id: passed} across all TEST-*.xml reports."""
    results: dict[str, bool] = {}
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
            skipped = any(c.tag == "skipped" for c in case)
            if skipped:
                continue
            failed = any(c.tag in ("failure", "error") for c in case)
            results[test_id] = not failed
    return results


def run_tests(worktree: str, checkpoint_k: int, cfg: dict) -> TestOutcome:
    """Run the accumulated suite cp01..cpK and score by category."""
    ok, err = build(worktree, cfg)
    if not ok:
        return TestOutcome(build_ok=False, error=err)

    _clear_surefire(worktree, cfg)
    tags = ",".join(f"cp{str(i).zfill(2)}" for i in range(1, checkpoint_k + 1))
    tmpl = cfg["build"]["test_cmd_template"]
    cmd = [part.replace("{tags}", tags) for part in tmpl]
    try:
        subprocess.run(cmd, cwd=worktree, capture_output=True, text=True,
                       timeout=cfg["build"].get("test_timeout", 3600))
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return TestOutcome(build_ok=True, error=f"test run failed to launch/timed out: {exc}")

    results = _parse_surefire(worktree, cfg)
    outcome = TestOutcome(build_ok=True)
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
