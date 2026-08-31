#!/usr/bin/env python3
"""Fail-closed Java-parser self-test for both measurement stacks.

WHY THIS EXISTS. lizard 1.24.0 regressed its Java state machine: a *bare*
annotation immediately followed by a *parenthesised* annotation at class level
(``@Entity`` then ``@Table(name = "owners")``) loses the second ``@`` in
``JavaStates._state_post_decorator`` — it returns to ``_state_global`` without
re-dispatching the token — and the class declaration is then consumed as if it
were a method body. The file yields ZERO functions. Nothing errors; the file is
simply not there any more.

WHAT THAT COSTS. Every structural metric is function-based, so an unparsable file
silently reads as "no complexity, no change": in this experiment ``Owner.java``,
``Pet.java`` and all seven ``Jpa*RepositoryImpl.java`` disappeared (213 of 307
Spring production functions visible under 1.24). Measured over 178 Spring
checkpoints of the reference run, the blind parser hid 11% of the arm's impact
mass and let 6 of 78 changes that should have failed the gate pass instead —
including two whose true composite was ~2.5x the block line. OfficeFloor lost no
verdicts at all (its changes sit far below the line either way), so the error is
ASYMMETRIC BETWEEN ARMS and biases the gated arm toward "the gate could not hold
Spring" — the very claim the run is meant to test.

TWO STACKS, CHECKED SEPARATELY. They are two different installs and can drift
apart independently:

  * this harness's in-process lizard  -> every metric in ``metrics.py``/``analyze``
    (and therefore ``baselines/officefloor.json``, which was built from them);
  * the ``impact-gate`` CLI's own venv -> every verdict of the ``impact_gated``
    strategy. A gate graded against a baseline measured by a *different* parser is
    not comparing like with like, so both stacks must agree.

The check is a change of exactly the failing shape — a method added to an
annotated entity class — asserted end-to-end: the parser must see the new method,
and the gate must score that change above zero. Fails CLOSED (the run refuses to
start), like the Landlock self-check: a silently blind measure is worse than no
run at all.

Run standalone:

    python -m harness.parser_selftest --config config.yaml

Exit codes: 0 = PASS, 1 = FAIL (a parser is blind — do NOT run the experiment).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import lizard

from . import impact_gate

# The canonical failing shape: a bare annotation, then a parenthesised one, on a
# class that owns real method bodies (this is Owner.java in miniature).
_BEFORE = """package fixture;

import jakarta.persistence.*;

@Entity
@Table(name = "owners")
public class Fixture {

    @Column(name = "email")
    private String email;

    public String getEmail() {
        return this.email;
    }
}
"""

# ...and the change under test: a method accreted onto that class, exactly the
# move (cp04/cp07) the gate scored as free.
_AFTER = """package fixture;

import jakarta.persistence.*;

@Entity
@Table(name = "owners")
public class Fixture {

    @Column(name = "email")
    private String email;

    public String getEmail() {
        return this.email;
    }

    @PrePersist
    void normalise() {
        if (this.email != null) {
            this.email = this.email.toLowerCase();
        }
    }
}
"""

_FIXTURE_PATH = "src/main/java/fixture/Fixture.java"
_EXPECTED = {"Fixture::getEmail", "Fixture::normalise"}


class ParserBlind(RuntimeError):
    """A parser cannot see functions it must see. The experiment cannot be
    measured with it (a hard, fail-closed error)."""


def _lizard_version() -> str:
    return str(getattr(lizard, "version", "") or getattr(lizard, "__version__", ""))


def check_lizard() -> dict:
    """The harness's OWN in-process lizard — the one metrics.py/analyze use."""
    names = {f.name for f in
             lizard.analyze_file.analyze_source_code(_FIXTURE_PATH, _AFTER).function_list}
    return {"stack": "harness lizard", "version": _lizard_version(),
            "units_seen": sorted(names), "ok": _EXPECTED <= names}


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, text=True)


def check_gate(cmd: list[str], timeout: int = 120) -> dict:
    """The `impact-gate` CLI's stack, end to end: build a throwaway repo whose
    HEAD holds the annotated class, stage the added method, and score it. A
    healthy gate returns impact > 0 and names the new unit; a blind one returns 0
    (and would therefore pass every such change no matter how large)."""
    tmp = tempfile.mkdtemp(prefix="pe-parser-selftest-")
    try:
        os.makedirs(os.path.join(tmp, os.path.dirname(_FIXTURE_PATH)), exist_ok=True)
        path = os.path.join(tmp, _FIXTURE_PATH)
        _git(tmp, "init", "-q")
        with open(path, "w") as fh:
            fh.write(_BEFORE)
        _git(tmp, "add", "-A")
        _git(tmp, "-c", "user.email=selftest@petclinic-evolve", "-c", "user.name=selftest",
             "commit", "-q", "-m", "fixture base")
        with open(path, "w") as fh:
            fh.write(_AFTER)
        _git(tmp, "add", "-A")
        # No baseline / no curve prior: this asks only "is the change visible at
        # all", never "how does it grade" — thresholds are irrelevant here.
        ig = impact_gate.score(cmd, tmp, block_percentile=99, warn_percentile=95,
                               timeout=timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    units = [u.get("name") for u in (ig.get("top_units") or [])]
    impact = ig.get("impact") or 0
    return {"stack": "impact-gate CLI", "cmd": list(cmd),
            "lizard_version": gate_lizard_version(cmd),
            "impact": impact, "units_seen": units,
            "ok": impact > 0 and any(u == "Fixture::normalise" for u in units)}


def gate_lizard_version(cmd: list[str]) -> str:
    """Best-effort: the lizard version inside the gate CLI's own environment.
    Empty when the CLI is not a venv script (the probe in `check_gate` is the
    authoritative signal either way — it tests behaviour, not a version string)."""
    exe = cmd[0] if cmd else ""
    if os.sep not in exe:
        return ""
    py = os.path.join(os.path.dirname(os.path.abspath(exe)), "python")
    if not os.path.exists(py):
        return ""
    try:
        out = subprocess.run(
            [py, "-c", "import lizard; print(getattr(lizard,'version','') or "
                       "getattr(lizard,'__version__',''))"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip()


_ADVICE = (
    "A Java parser in this run is blind to annotated classes (the lizard 1.24.0 "
    "@Entity/@Table regression). Pin the SAME lizard in BOTH stacks — this harness's "
    ".venv (requirements.txt pins it) and the impact-gate CLI's own venv:\n"
    "    ./.venv/bin/pip install 'lizard==1.23.0'\n"
    "    <impact-gate venv>/bin/pip install 'lizard==1.23.0'\n"
    "then re-run:  python -m harness.parser_selftest --config config.yaml"
)


def require(cfg: dict, gated: bool) -> dict:
    """Fail-closed preflight for run_experiment/analyze. Checks the harness parser
    always, and the gate's parser when the impact_gated strategy is active.
    Returns the gate probe (for provenance) or {}. Raises ParserBlind when a parser
    is blind, or ImpactGateError when the gate CLI cannot be run at all — both are
    reasons not to start a gated run."""
    harness = check_lizard()
    if not harness["ok"]:
        raise ParserBlind(
            f"harness lizard {harness['version']} does not see "
            f"{sorted(_EXPECTED - set(harness['units_seen']))} in an @Entity/@Table "
            f"class — every structural metric would read 0 for such files.\n{_ADVICE}")
    if not gated:
        return {}
    cmd = (cfg.get("impact_gate") or {}).get("cmd")
    if not cmd:
        return {}
    gate = check_gate(cmd)
    if not gate["ok"]:
        raise ParserBlind(
            f"the impact-gate CLI ({' '.join(cmd)}) scored a method added to an "
            f"@Entity/@Table class as impact {gate['impact']} — it cannot see the "
            f"change, so no such change could ever fail the gate "
            f"(gate lizard {gate['lizard_version'] or 'unknown'}, harness lizard "
            f"{harness['version']}).\n{_ADVICE}")
    if gate["lizard_version"] and gate["lizard_version"] != harness["version"]:
        # Not fatal (both stacks see the fixture), but the gate is graded against a
        # baseline built by the harness stack, so a mismatch is worth stating aloud.
        print(f"  WARNING: gate lizard {gate['lizard_version']} != harness lizard "
              f"{harness['version']}; the gate and its baseline are measured by "
              f"different parsers.")
    return gate


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", help="config.yaml — also checks its impact_gate.cmd")
    args = ap.parse_args()

    print("Java parser self-test (annotated-class visibility)\n")
    ok = True
    harness = check_lizard()
    print(f"  [{'PASS' if harness['ok'] else 'FAIL'}] harness lizard "
          f"{harness['version']}: saw {harness['units_seen'] or 'NOTHING'}")
    ok = ok and harness["ok"]

    if args.config:
        import yaml
        from . import expand_path
        with open(args.config) as fh:
            cfg = yaml.safe_load(fh)
        cmd = (cfg.get("impact_gate") or {}).get("cmd")
        if cmd:
            cmd = [expand_path(c, "impact_gate.cmd") for c in cmd]
            try:
                gate = check_gate(cmd)
            except impact_gate.ImpactGateError as e:
                print(f"  [SKIP] impact-gate CLI not runnable: {e}")
            else:
                print(f"  [{'PASS' if gate['ok'] else 'FAIL'}] impact-gate CLI "
                      f"(lizard {gate['lizard_version'] or 'unknown'}): impact "
                      f"{gate['impact']}, saw {gate['units_seen'] or 'NOTHING'}")
                ok = ok and gate["ok"]
                if gate["ok"] and gate["lizard_version"] \
                        and gate["lizard_version"] != harness["version"]:
                    print(f"  [WARN] gate lizard {gate['lizard_version']} != harness "
                          f"lizard {harness['version']} — the gate and the baseline it "
                          f"grades against are measured by different parsers.")
        else:
            print("  [SKIP] no impact_gate.cmd in config (ungated run)")
    else:
        print("  [SKIP] impact-gate CLI (pass --config to check it too)")

    print("\nOVERALL:", "PASS  (both measures see annotated classes)" if ok
          else f"FAIL  (a measure is blind — do NOT run)\n\n{_ADVICE}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
