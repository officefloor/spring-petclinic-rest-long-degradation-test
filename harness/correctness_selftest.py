"""Deterministic unit tests for harness.correctness scoring (no build, no agents).
Run: .venv/bin/python -m harness.correctness_selftest
"""
from __future__ import annotations

from . import correctness as c

# The real id shape, taken from a capture rather than invented: the fully qualified acceptance
# class, '#', then the method. A plausible-looking "Cp02Tests.coreX" parses to None, which is how
# the first draft of these tests passed for the wrong reason.
PKG = "org.springframework.samples.petclinic.acceptance."


def tid(cls: str, method: str) -> str:
    return f"{PKG}{cls}#{method}"


def test_test_checkpoint_from_class():
    assert c.test_checkpoint(tid("Cp02Tests", "coreCreatesOwner")) == 2
    assert c.test_checkpoint(tid("Cp28Tests", "functionalityVisitSummary")) == 28
    assert c.test_checkpoint(tid("SomeOtherTests", "whatever")) is None
    # the shape matters: a bare ClassName.method does NOT parse
    assert c.test_checkpoint("Cp02Tests.coreCreatesOwner") is None


def test_replaced_prior_is_intended():
    """A mutative checkpoint's updated copy renames the prior's methods, so the prior test id is
    ABSENT from the run. That loss is intended."""
    prior = {tid("Cp02Tests", "coreOldRule")}
    results = {tid("Cp02Tests", "coreNewRule"): True, tid("Cp08Tests", "coreOwnRule"): True}
    now = {t for t, ok in results.items() if ok}
    assert c.count_regressions(prior, now) == 1
    assert c.count_true_regressions(prior, now, (2,), results) == 0


def test_failing_replacement_is_a_true_regression():
    """A replacement the updated copy still RUNS, and that fails, is a plain failure —
    `mutates` must not forgive it."""
    t = tid("Cp02Tests", "coreNewRule")
    prior, results = {t}, {t: False}
    assert c.count_true_regressions(prior, set(), (2, 3), results) == 1
    # without the results map the old, over-forgiving behaviour is retained for back-compat
    assert c.count_true_regressions(prior, set(), (2, 3)) == 0


def test_unmutated_prior_always_counts():
    t = tid("Cp11Tests", "coreSomething")
    assert c.count_true_regressions({t}, set(), (2, 3), {t: False}) == 1
    assert c.count_true_regressions({t}, set(), (), {}) == 1


def test_unsatisfied_replacement_counted():
    """cp36's shape: the updated Cp28Tests arrives failing. Never having passed it cannot be a
    regression, so this is the only measure that sees it."""
    repl = tid("Cp28Tests", "functionalityNewSummaryShape")
    old = tid("Cp28Tests", "functionalityOldSummaryShape")
    prior_selected = {old, tid("Cp35Tests", "coreX")}
    results = {old: True, repl: False, tid("Cp36Tests", "coreOwnRule"): True}
    assert c.count_unsatisfied_replacements(prior_selected, results, (28,)) == 1
    prior_passing = {old}
    now = {t for t, ok in results.items() if ok}
    assert c.count_regressions(prior_passing, now) == 0
    assert c.count_true_regressions(prior_passing, now, (28,), results) == 0


def test_unsatisfied_replacement_needs_prior_and_declaration():
    repl = tid("Cp28Tests", "functionalityNew")
    results = {repl: False}
    assert c.count_unsatisfied_replacements(None, results, (28,)) == 0   # no baseline
    assert c.count_unsatisfied_replacements(set(), results, (11,)) == 0  # not declared
    assert c.count_unsatisfied_replacements(set(), {repl: True}, (28,)) == 0  # satisfied


def test_outcome_row_reports_both():
    repl = tid("Cp28Tests", "functionalityNew")
    results = {repl: False, tid("Cp36Tests", "coreOwnRule"): True}
    o = c.score_results(results, 36)
    row = c.outcome_row(o, prior_passing=set(), mutated_cps=(28,),
                        prior_selected={tid("Cp28Tests", "functionalityOld")})
    assert row["unsatisfied_replacement"] == 1, row
    assert row["regressions"] == 0 and row["true_regressions"] == 0, row
    assert row["strict_pass"] is False, row


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"OK — {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
