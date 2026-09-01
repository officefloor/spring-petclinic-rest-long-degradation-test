#!/usr/bin/env python3
"""Fail-closed self-test for the design-B code-quality gate (jscpd clones + ast-grep smells).

WHY THIS EXISTS. The impact_gated pipeline's quality gate (harness/quality_gate.py) is what
stops a refactor from buying a lower impact score with duplicated/greenfield slop. Its verdict
is decided entirely by two external binaries. If either drifts in version or stops matching,
the gate silently weakens — the same failure class as the lizard 1.24.0 regression that turned
the impact gate off for @Entity classes (see parser_selftest.py). A silently blind gate is
worse than no gate, so this check runs BEFORE any agent turn and refuses the run on failure.

WHAT IT CHECKS, both fail-closed when the impact_gated strategy is active and the gate enabled:
  1. VERSIONS. jscpd and ast-grep report exactly the versions pinned in tools/package.json
     (the committed lockfile), when that pin can be located. A version bump must be a
     deliberate, re-baselined change, never an accident of PATH.
  2. BEHAVIOUR (authoritative). An end-to-end golden fixture: a throwaway git repo whose
     staged change adds a verbatim duplicate method AND a `x == true` comparison. The gate
     must FAIL it, reporting at least one clone finding and one smell finding. This catches
     config/rule drift a version string cannot (a valid-but-wrong ast-grep, a jscpd whose
     defaults moved), exactly as parser_selftest asserts a parse, not a version.

Run standalone:
    python -m harness.quality_selftest --config config.yaml

Exit codes: 0 = PASS, 1 = FAIL (the gate is blind — do NOT run the experiment).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

from . import quality_gate


class QualityGateBlind(RuntimeError):
    """The quality gate cannot see clones/smells it must see, or a pinned tool drifted.
    A hard, fail-closed error: the impact_gated experiment cannot be measured with it."""


# The golden fixture proves BOTH detectors independently, so the clone and the smell live in
# SEPARATE files: a staged change (a) duplicates a whole method verbatim in Fixture.java and
# (b) adds a new Extra.java with a redundant boolean-literal comparison. (In one file jscpd can
# greedily extend a clone over an adjacent smell line; the gate still fails then, but the self-
# test wants to observe each detector on its own.) A healthy gate fails with >=1 clone AND >=1
# smell finding.
_BASE = """package fixture;
public class Fixture {
    public int total(int n) {
        int sum = 0;
        for (int i = 0; i < n; i++) { sum += i; }
        if (sum == n) { return 1; }
        return sum;
    }
}
"""
_CHANGED = """package fixture;
public class Fixture {
    public int total(int n) {
        int sum = 0;
        for (int i = 0; i < n; i++) { sum += i; }
        if (sum == n) { return 1; }
        return sum;
    }
    public int total2(int n) {
        int sum = 0;
        for (int i = 0; i < n; i++) { sum += i; }
        if (sum == n) { return 1; }
        return sum;
    }
}
"""
_SMELL_FILE = "src/main/java/fixture/Extra.java"
_SMELL = """package fixture;
public class Extra {
    boolean flag(boolean b) {
        return b == true;
    }
}
"""
_FIXTURE_PATH = "src/main/java/fixture/Fixture.java"


def _ver(bin_: str) -> str:
    """The version token from `<bin> --version` (e.g. 'cpd 5.0.14' -> '5.0.14')."""
    try:
        out = subprocess.run([bin_, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"\d+\.\d+\.\d+", (out.stdout + " " + out.stderr))
    return m.group(0) if m else ""


def _pinned_versions(tools: dict) -> dict:
    """Expected versions from the committed tools/package.json, located from the jscpd bin
    path (.../tools/node_modules/.bin/jscpd -> .../tools/package.json). {} if not locatable
    (a bare PATH binary) — then only the behavioural check applies."""
    jbin = tools.get("jscpd", "")
    if os.sep not in jbin:
        return {}
    parts = os.path.abspath(jbin).split(os.sep)
    if "node_modules" not in parts:
        return {}
    tools_dir = os.sep.join(parts[: parts.index("node_modules")])
    pj = os.path.join(tools_dir, "package.json")
    try:
        with open(pj) as fh:
            deps = json.load(fh).get("dependencies", {})
    except (OSError, json.JSONDecodeError):
        return {}
    return {"jscpd": deps.get("jscpd", ""), "astgrep": deps.get("@ast-grep/cli", "")}


def check_versions(tools: dict) -> dict:
    pinned = _pinned_versions(tools)
    jver, sver = _ver(tools.get("jscpd", "jscpd")), _ver(tools.get("astgrep", "sg"))
    ok = True
    detail = {"jscpd": jver, "astgrep": sver, "pinned": pinned}
    if pinned:
        ok = (jver == pinned.get("jscpd")) and (sver == pinned.get("astgrep"))
    detail["ok"] = ok
    detail["checked"] = bool(pinned)
    return detail


def check_gate(tools: dict, rules_dir: str, qcfg: dict, src_dirs: list[str]) -> dict:
    """End-to-end golden fixture through quality_gate.review. A healthy gate returns
    passed=False with >=1 clone finding and >=1 smell finding on a duplicate + boolean-compare."""
    tmp = tempfile.mkdtemp(prefix="pe-quality-selftest-")
    try:
        path = os.path.join(tmp, _FIXTURE_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(["git", "-C", tmp, "init", "-q"], check=True,
                       capture_output=True, text=True)
        with open(path, "w") as fh:
            fh.write(_BASE)
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", tmp, "-c", "user.email=selftest@petclinic-evolve",
                        "-c", "user.name=selftest", "commit", "-q", "-m", "base"],
                       check=True, capture_output=True, text=True)
        with open(path, "w") as fh:
            fh.write(_CHANGED)
        with open(os.path.join(tmp, _SMELL_FILE), "w") as fh:
            fh.write(_SMELL)
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=True, capture_output=True, text=True)
        qr = quality_gate.review(tmp, src_dirs, tools, qcfg)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ran": qr.ran, "passed": qr.passed,
            "clone_lines": qr.clone_finding_lines, "smell_lines": qr.smell_finding_lines,
            "ok": (qr.ran and not qr.passed
                   and qr.clone_finding_lines > 0 and qr.smell_finding_lines > 0),
            "reason": qr.reason}


_ADVICE = (
    "The design-B quality gate is blind or a pinned tool drifted. Install the PINNED clone/\n"
    "smell binaries and re-run the check:\n"
    "    (cd tools && npm ci)        # jscpd + @ast-grep/cli at the locked versions\n"
    "    python -m harness.quality_selftest --config config.yaml\n"
    "If you intend a version bump, update tools/package.json + package-lock.json AND the\n"
    "golden expectations, and re-baseline: clone thresholds and rule matching decide verdicts."
)


def require(cfg: dict, gated: bool) -> dict:
    """Fail-closed preflight for run_experiment. No-op unless the impact_gated strategy is
    active AND its quality_gate is enabled. Returns the gate probe (for provenance) or {}.
    Raises QualityGateBlind on any failure."""
    igc = cfg.get("impact_gate") or {}
    qcfg = igc.get("quality_gate") or {}
    if not (gated and qcfg.get("enabled", False)):
        return {}
    tools = cfg.get("tools", {})
    rules_dir = tools.get("astgrep_rules", "")
    src_dirs = _src_dirs(cfg)

    ver = check_versions(tools)
    if ver["checked"] and not ver["ok"]:
        raise QualityGateBlind(
            f"pinned clone/smell tool drift: jscpd {ver['jscpd'] or 'missing'} / ast-grep "
            f"{ver['astgrep'] or 'missing'} != pinned {ver['pinned']}.\n{_ADVICE}")
    gate = check_gate(tools, rules_dir, qcfg, src_dirs)
    if not gate["ok"]:
        raise QualityGateBlind(
            f"the quality gate did not fail a verbatim-duplicate + boolean-compare fixture "
            f"(ran={gate['ran']}, passed={gate['passed']}, clone_lines={gate['clone_lines']}, "
            f"smell_lines={gate['smell_lines']}, reason={gate['reason']}). It cannot enforce "
            f"clean refactors, so a refactor could pass with slop.\n{_ADVICE}")
    return {"versions": {"jscpd": ver["jscpd"], "astgrep": ver["astgrep"]},
            "version_pinned": ver["checked"], "golden": gate}


def _src_dirs(cfg: dict) -> list[str]:
    for arm in (cfg.get("arms") or {}).values():
        vd = arm.get("verbosity_dirs")
        if vd:
            return list(vd)
    return ["src/main/java"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    import yaml
    from . import expand_path
    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)
    cfg_dir = os.path.dirname(os.path.abspath(args.config))

    def resolve(p):
        if not p:
            return p
        p = expand_path(p)
        return p if os.path.isabs(p) else os.path.join(cfg_dir, p)
    for tk in ("jscpd", "astgrep", "astgrep_rules"):
        if cfg.get("tools", {}).get(tk) and (os.sep in cfg["tools"][tk]):
            cfg["tools"][tk] = resolve(cfg["tools"][tk])

    print("Code-quality gate self-test (jscpd clones + ast-grep smells)\n")
    tools = cfg.get("tools", {})
    ver = check_versions(tools)
    vtag = "PASS" if (not ver["checked"] or ver["ok"]) else "FAIL"
    print(f"  [{vtag}] versions: jscpd {ver['jscpd'] or 'missing'}, ast-grep "
          f"{ver['astgrep'] or 'missing'}"
          + (f"  (pinned {ver['pinned']})" if ver["checked"] else "  (no pin located)"))
    qcfg = (cfg.get("impact_gate") or {}).get("quality_gate") or {}
    gate = check_gate(tools, tools.get("astgrep_rules", ""), qcfg, _src_dirs(cfg))
    gtag = "PASS" if gate["ok"] else "FAIL"
    print(f"  [{gtag}] golden fixture: ran={gate['ran']} passed={gate['passed']} "
          f"clone_lines={gate['clone_lines']} smell_lines={gate['smell_lines']}")
    ok = (not ver["checked"] or ver["ok"]) and gate["ok"]
    print("\nOVERALL:", "PASS  (gate sees clones and smells)" if ok
          else f"FAIL  (gate is blind — do NOT run)\n\n{_ADVICE}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
