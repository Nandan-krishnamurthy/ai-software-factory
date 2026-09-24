"""Unit tests for the git wrapper (T1.1), using real throwaway repositories (offline)."""

import tempfile
import unittest
from pathlib import Path

from factory.errors import GitError
from factory.gh import ProcessResult
from factory.git import Git

IDENTITY = ["-c", "user.name=Factory Test", "-c", "user.email=test@example.invalid"]


class GitWrapperTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.git = Git(self.repo, timeout=30)
        self.git.run(["init", "-b", "main"])

    def commit(self, name, content="x"):
        (self.repo / name).write_text(content, encoding="utf-8")
        self.git.run(["add", name])
        self.git.run([*IDENTITY, "commit", "-m", f"add {name}"])

    def test_runs_against_repo_dir_not_cwd(self):
        self.assertEqual(self.git.current_branch(), "main")

    def test_is_clean_and_rev_parse(self):
        self.commit("a.txt")
        self.assertTrue(self.git.is_clean())
        (self.repo / "b.txt").write_text("untracked", encoding="utf-8")
        self.assertFalse(self.git.is_clean())
        self.assertRegex(self.git.rev_parse("HEAD"), r"^[0-9a-f]{40}$")

    def test_detached_head_has_no_branch(self):
        self.commit("a.txt")
        self.git.run(["checkout", "--detach"])
        self.assertIsNone(self.git.current_branch())

    def test_remote_url(self):
        self.assertIsNone(self.git.remote_url())
        self.git.run(["remote", "add", "origin", "https://github.com/o/r.git"])
        self.assertEqual(self.git.remote_url(), "https://github.com/o/r.git")

    def test_error_is_typed_and_shows_stderr(self):
        with self.assertRaises(GitError) as ctx:
            self.git.run(["rev-parse", "--verify", "no-such-ref"])
        err = ctx.exception
        self.assertNotEqual(err.returncode, 0)
        self.assertTrue(err.stderr.strip())
        self.assertIn(err.stderr.strip()[:20], str(err))
        self.assertIn("git -C", str(err))


class GitTransportTest(unittest.TestCase):
    def test_always_uses_dash_c_timeout_and_no_prompt(self):
        calls = []

        def transport(argv, *, timeout, cwd=None, env=None, input=None):
            calls.append((argv, timeout, env))
            return ProcessResult(list(argv), 0, "", "")

        Git("some/dir", timeout=9, transport=transport).run(["status"])
        argv, timeout, env = calls[0]
        self.assertEqual(argv[:3], ["git", "-C", str(Path("some/dir"))])
        self.assertEqual(timeout, 9)
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")

    def test_non_positive_timeout_rejected(self):
        with self.assertRaises(ValueError):
            Git(".", timeout=0)


if __name__ == "__main__":
    unittest.main()
