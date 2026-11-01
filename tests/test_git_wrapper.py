"""C2 (D-1 Option C): the secure git wrapper `factory.py git <sub> …` runs hook-running
git in the active target with hooks and fsmonitor disabled.

The permanent form of the earlier hook-matrix experiment: plant every hook git can run,
plus an fsmonitor script, and assert that each wrapper subcommand runs **none** of them,
while a control with plain git runs them. Also checks the wrapper's allow-list and the
``commit --amend`` refusal. These are real-git tests (skipped without git); they cover the
factory's own git only, not git that model-written code runs (ADR-0006, B-49).
"""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from factory import cli, target
from factory.git import WRAPPER_SUBCOMMANDS

BASE = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_CONFIG")}
ALL_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit",
             "pre-merge-commit", "post-merge", "post-checkout", "pre-push",
             "reference-transaction", "post-index-change")


@unittest.skipUnless(__import__("shutil").which("git"), "needs git")
class GitWrapperHookMatrixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nohooks = self.root / "nh"
        self.nohooks.mkdir()
        self.remote = self.root / "r.git"
        self.work = self.root / "w"
        self._git("init", "-q", "--bare", str(self.remote), cwd=self.root)
        self._git("init", "-q", "-b", "main", str(self.work), cwd=self.root)
        self._git("config", "user.email", "a@b.invalid", cwd=self.work)
        self._git("config", "user.name", "a", cwd=self.work)
        self._git("config", "core.fsmonitor", (self.root / "mon.sh").as_posix(), cwd=self.work)
        (self.work / "f.txt").write_text("one\n", encoding="utf-8")
        self._git("add", ".", cwd=self.work)
        self._git("commit", "-qm", "init", cwd=self.work)
        self._git("remote", "add", "origin", str(self.remote), cwd=self.work)
        self._git("push", "-q", "-u", "origin", "main", cwd=self.work)  # upstream for pull
        self.marker = self.root / "ran"
        self._plant()
        self.target = target.Target(path=self.work, repo="owner/app")

    def _git(self, *args, cwd):
        subprocess.run(["git", "-c", f"core.hooksPath={self.nohooks}", "-c",
                        "core.fsmonitor=false", "-C", str(cwd), *args],
                       env=BASE, check=True, capture_output=True)

    def _plant(self):
        for hook in ALL_HOOKS:
            p = self.work / ".git" / "hooks" / hook
            p.write_text(f'#!/bin/sh\necho {hook} >> "{self.marker.as_posix()}"\nexit 0\n',
                         encoding="utf-8", newline="\n")
            p.chmod(0o755)
        (self.root / "mon.sh").write_text(
            f'#!/bin/sh\necho fsmonitor >> "{self.marker.as_posix()}"\nexit 1\n',
            encoding="utf-8", newline="\n")

    def _fired(self):
        out = sorted(set(self.marker.read_text().split())) if self.marker.exists() else []
        self.marker.unlink(missing_ok=True)
        return out

    def wrapper(self, *gitargs):
        self.marker.unlink(missing_ok=True)
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target", lambda factory_root=None: self.target), \
                mock.patch.dict(os.environ, BASE, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["git", *gitargs])
        return code, self._fired(), err.getvalue()

    def plain(self, *gitargs):
        self.marker.unlink(missing_ok=True)
        subprocess.run(["git", "-C", str(self.work), *gitargs], env=BASE, capture_output=True)
        return self._fired()

    # ---- the matrix --------------------------------------------------------------------
    def test_control_plain_git_runs_hooks(self):
        (self.work / "f.txt").write_text("one\ntwo\n", encoding="utf-8")
        self.assertIn("post-index-change", self.plain("add", "f.txt"))
        self.assertTrue({"pre-commit", "post-commit"} <= set(self.plain("commit", "-m", "x")))
        self.assertIn("post-checkout", self.plain("switch", "-c", "other"))

    def test_wrapper_runs_no_hooks_for_each_subcommand(self):
        (self.work / "f.txt").write_text("one\ntwo\n", encoding="utf-8")
        steps = [
            ("add", "f.txt"), ("status", "--porcelain"), ("ls-files",),
            ("commit", "-m", "second"), ("branch", "--show-current"),
            ("switch", "-c", "story/1-x"), ("switch", "main"),
            ("fetch", "origin"), ("pull", "--ff-only"), ("push", "origin", "main"),
        ]
        for step in steps:
            with self.subTest(step=step[0]):
                code, fired, err = self.wrapper(*step)
                self.assertEqual(code, 0, err)
                self.assertEqual(fired, [], f"{step[0]} ran hooks: {fired}")

    def test_amend_is_refused(self):
        code, fired, err = self.wrapper("commit", "--amend", "-m", "x")
        self.assertEqual(code, 2)
        self.assertIn("amend", err)
        self.assertEqual(fired, [])

    def test_non_wrapper_subcommands_are_refused(self):
        for sub in ("rebase", "reset", "log", "stash", "merge"):
            with self.subTest(sub=sub):
                code, _, err = self.wrapper(sub)
                self.assertEqual(code, 2)
                self.assertNotIn(sub, WRAPPER_SUBCOMMANDS)

    def test_no_subcommand_errors(self):
        code, _, err = self.wrapper()
        self.assertEqual(code, 2)
        self.assertIn("subcommand", err)


class WrapperSubcommandSyncTest(unittest.TestCase):
    def test_guard_list_matches_git_list(self):
        from factory import guard
        self.assertEqual(guard._WRAPPER_GIT_SUBCOMMANDS, WRAPPER_SUBCOMMANDS)


if __name__ == "__main__":
    unittest.main()
