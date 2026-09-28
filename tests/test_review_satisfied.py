"""Tests for harness.run_experiment._review_satisfied.

This function decides, in the `reviewed` strategy, whether a reviewer's reply
signals the change is already clean (skip the author fix turn) or has findings
(run the fix turn). Getting it wrong is costly in both directions:

  - a MISSED tag on a clean review runs a needless fix on an already-approved
    change (observed 4/60 in blind-202609281717 before the first-tag change);
  - a FALSE satisfied verdict drops a real finding and never fixes it, which is
    the failure the parser is designed never to commit.

Run from the repo root with the harness venv:

    .venv/bin/python -m unittest tests.test_review_satisfied -v
"""

import unittest

from harness.run_experiment import _review_satisfied as satisfied


class ReviewSatisfiedTest(unittest.TestCase):
    # ---- clean tag on the first line: the compliant case ------------------
    def test_clean_tag_first_line(self):
        self.assertTrue(satisfied("VERDICT: LGTM", "LGTM"))

    def test_changes_requested_first_line(self):
        self.assertFalse(satisfied("VERDICT: CHANGES REQUESTED", "LGTM"))

    def test_clean_tag_with_body_after(self):
        self.assertTrue(satisfied("VERDICT: LGTM\n\nThe change is minimal and well placed.", "LGTM"))

    # ---- reason-first replies: the bug this change fixes -------------------
    # The reviewer reasons, THEN concludes with the tag off line 1. These are
    # cp08/20/21/54 of blind-202609281717, which wrongly ran a fix under the
    # old first-line-only rule.
    def test_reason_first_then_lgtm_is_satisfied(self):
        v = "This is a minimal, well-placed change. Let me assess it against the codebase.\n\nVERDICT: LGTM"
        self.assertTrue(satisfied(v, "LGTM"))

    def test_reason_first_then_changes_requested_runs_fix(self):
        v = "I reviewed the change against the existing structure.\n\nVERDICT: CHANGES REQUESTED\n\nThe mapper duplicates logic."
        self.assertFalse(satisfied(v, "LGTM"))

    # ---- the substring trap the value-parse must never fall into ----------
    def test_prose_mentions_lgtm_without_tag_runs_fix(self):
        self.assertFalse(satisfied("This is not LGTM at all; here are the findings.", "LGTM"))

    def test_prose_negates_lgtm_before_tag(self):
        v = "This is not LGTM yet.\n\nVERDICT: CHANGES REQUESTED"
        self.assertFalse(satisfied(v, "LGTM"))

    # ---- first tag wins: a later stray approval cannot cancel a finding ----
    def test_first_tag_wins_changes_then_lgtm(self):
        v = "VERDICT: CHANGES REQUESTED\n\nOnce the duplication is removed it would be VERDICT: LGTM."
        self.assertFalse(satisfied(v, "LGTM"))

    def test_first_tag_wins_lgtm_then_stray_changes(self):
        # If the real verdict is first and clean, a later hypothetical is ignored.
        v = "VERDICT: LGTM\n\nI considered VERDICT: CHANGES REQUESTED but the change is sound."
        self.assertTrue(satisfied(v, "LGTM"))

    # ---- markdown / whitespace / punctuation normalisation ----------------
    def test_markdown_bold_tag(self):
        self.assertTrue(satisfied("**VERDICT: LGTM**", "LGTM"))

    def test_markdown_blockquote_tag(self):
        self.assertTrue(satisfied("> VERDICT: LGTM", "LGTM"))

    def test_bullet_tag(self):
        self.assertTrue(satisfied("- VERDICT: LGTM", "LGTM"))

    def test_trailing_punctuation_on_tag(self):
        self.assertTrue(satisfied("VERDICT: LGTM.", "LGTM"))

    def test_leading_blank_lines_before_tag(self):
        self.assertTrue(satisfied("\n\n   \nVERDICT: LGTM", "LGTM"))

    def test_case_insensitive_tag(self):
        self.assertTrue(satisfied("verdict: lgtm", "LGTM"))

    # ---- qualified LGTM is not a clean LGTM (conservative) -----------------
    def test_qualified_lgtm_runs_fix(self):
        self.assertFalse(satisfied("VERDICT: LGTM (with minor nits)", "LGTM"))

    # ---- empty review is clean -------------------------------------------
    def test_empty_is_satisfied(self):
        self.assertTrue(satisfied("", "LGTM"))

    def test_whitespace_only_is_satisfied(self):
        self.assertTrue(satisfied("   \n\t\n", "LGTM"))

    def test_none_verdict_is_satisfied(self):
        self.assertTrue(satisfied(None, "LGTM"))

    # ---- no-tag fallback: satisfied only if the WHOLE reply is the token ---
    def test_bare_token_only_is_satisfied(self):
        self.assertTrue(satisfied("LGTM", "LGTM"))

    def test_decorated_bare_token_is_satisfied(self):
        self.assertTrue(satisfied("**LGTM**", "LGTM"))

    def test_token_plus_prose_without_tag_runs_fix(self):
        self.assertFalse(satisfied("LGTM but consider renaming the helper.", "LGTM"))

    # ---- token handling ---------------------------------------------------
    def test_none_token_defaults_to_lgtm(self):
        self.assertTrue(satisfied("VERDICT: LGTM", None))
        self.assertFalse(satisfied("VERDICT: CHANGES REQUESTED", None))

    def test_custom_satisfied_token(self):
        self.assertTrue(satisfied("VERDICT: APPROVED", "APPROVED"))
        self.assertFalse(satisfied("VERDICT: LGTM", "APPROVED"))

    def test_custom_token_is_case_insensitive(self):
        self.assertTrue(satisfied("verdict: approved", "approved"))


if __name__ == "__main__":
    unittest.main()
