"""Smoke test for Option A: the reviewed arm's independent reviewer runs under a
Landlock ruleset that makes the SANDBOX read-only, so the reviewer process (and any
child it spawns) can read the code for context but the KERNEL denies every write to
it. This is the enforcement that replaces the ineffective `--allowedTools` scoping
(which does not bind under `--dangerously-skip-permissions`, so a reviewer could --
and in 6/60 checkpoints of blind-202609290016 did -- reach for Bash).

It validates the OS-level guarantee WITHOUT spending an API call: it applies the SAME
allowlist `run_agent` builds for the reviewer -- `default_allowlist(..., sandbox_ro=True)`
-- over a throwaway `/bin/sh` and checks that reads of a sandbox file succeed while
writes, creates, and deletes are denied, and that the reviewer's own config dir stays
writable (or Claude could not run). The author/fix path (`sandbox_ro=False`) is checked
to still allow writes, so the relaxation is scoped to the reviewer alone.

The temp sandbox is created under $HOME (not /tmp), mirroring production topology
(`~/sandbox`): the sandbox is then a standalone subtree with no read-write ancestor
rule, so Landlock's most-specific-rule-wins resolution is unambiguous. (Under /tmp it
would sit beneath default_allowlist's rw `/tmp` entry, muddying the test.)

Run from the repo root with the harness venv:

    .venv/bin/python -m unittest tests.test_reviewer_sandbox_ro -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from harness import landlock

HOME = os.path.expanduser("~")


@unittest.skipIf(landlock.abi_version() < 1, "Landlock unavailable on this host")
class ReviewerSandboxReadOnlyTest(unittest.TestCase):
    def setUp(self):
        # Under $HOME, not /tmp: the sandbox must not sit beneath a read-write rule
        # (default_allowlist lists /tmp as rw), so the only rule covering it is the
        # ro sandbox rule itself -- exactly the production layout (~/sandbox).
        self.sandbox = tempfile.mkdtemp(prefix=".ro-sandbox-", dir=HOME)
        self.cfg = tempfile.mkdtemp(prefix=".ro-cfg-", dir=HOME)
        self.src = os.path.join(self.sandbox, "Owner.java")
        with open(self.src, "w") as fh:
            fh.write("class Owner {}\n")

    def tearDown(self):
        for d in (self.sandbox, self.cfg):
            shutil.rmtree(d, ignore_errors=True)

    def _sh(self, script, sandbox_ro):
        """Run `script` under the reviewer's (ro) or author's (rw) confinement."""
        ro, rw = landlock.default_allowlist(self.sandbox, self.cfg, sandbox_ro=sandbox_ro)
        return subprocess.run(
            ["/bin/sh", "-c", script],
            preexec_fn=landlock.make_preexec(ro, rw),
            capture_output=True, text=True, timeout=30,
        )

    # ---- reviewer (sandbox_ro=True): reads allowed, writes denied ----------
    def test_reviewer_can_read_sandbox(self):
        r = self._sh(f'cat "{self.src}"', sandbox_ro=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("class Owner", r.stdout)

    def test_reviewer_can_list_sandbox(self):
        r = self._sh(f'ls "{self.sandbox}"', sandbox_ro=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Owner.java", r.stdout)

    def test_reviewer_cannot_overwrite_existing_file(self):
        r = self._sh(f'echo tampered > "{self.src}"', sandbox_ro=True)
        self.assertNotEqual(r.returncode, 0, "overwrite must be denied under sandbox_ro")
        with open(self.src) as fh:
            self.assertEqual(fh.read(), "class Owner {}\n")  # unchanged on disk

    def test_reviewer_cannot_create_file(self):
        new = os.path.join(self.sandbox, "Evil.java")
        r = self._sh(f'echo x > "{new}"', sandbox_ro=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(new))

    def test_reviewer_cannot_delete_file(self):
        self._sh(f'rm -f "{self.src}"', sandbox_ro=True)
        self.assertTrue(os.path.exists(self.src),
                        "reviewer must not be able to delete sandbox files")

    def test_reviewer_config_dir_stays_writable(self):
        # Claude writes its session store to CLAUDE_CONFIG_DIR (the owned cfg dir),
        # never the code tree -- so a read-only sandbox must not block it.
        probe = os.path.join(self.cfg, "session.json")
        r = self._sh(f'echo ok > "{probe}"', sandbox_ro=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(probe))

    # ---- author / fix (sandbox_ro=False): existing behaviour is intact -----
    def test_author_can_write_sandbox(self):
        r = self._sh(f'echo edited >> "{self.src}"', sandbox_ro=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.src) as fh:
            self.assertIn("edited", fh.read())


if __name__ == "__main__":
    unittest.main()
