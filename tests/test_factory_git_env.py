"""B-46, E2: no hook and no fsmonitor command runs in a git call the factory makes.

A repository can make git start a program: a hook (``switch`` runs post-checkout,
``pull`` post-merge, any ref update reference-transaction) or an fsmonitor command
(``status``, ``diff``). Every git call the factory makes goes through ``Git``, whose
environment points ``core.hooksPath`` at a path that cannot exist and turns
``core.fsmonitor`` off, as command-line config that outranks the repository's own.

The real-git tests plant hooks and an fsmonitor script that write marker files. A
control run with plain git shows the markers appear; the factory's own calls, including
``ensure.ensure_branch``, must leave none. This covers git calls made through ``Git``
only: git that model-written code runs by itself during verification is not covered
(ADR-0006, B-15, B-49).
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import ensure
from factory.git import NO_HOOKS, SAFE_CONFIG, Git, with_config

HOOKS = ("post-checkout", "post-merge", "reference-transaction")
NO_GIT_CONFIG_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}


class WithConfigTest(unittest.TestCase):
    def test_entries_already_there_are_kept_and_ours_appended(self):
        env = with_config({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name",
                           "GIT_CONFIG_VALUE_0": "from-env", "PATH": "p"}, SAFE_CONFIG)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "3")
        self.assertEqual((env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]),
                         ("user.name", "from-env"))
        self.assertEqual([(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"])
                          for i in (1, 2)], list(SAFE_CONFIG))
        self.assertEqual(env["PATH"], "p")

    def test_no_count_starts_at_zero(self):
        env = with_config({}, SAFE_CONFIG)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.hooksPath")

    def test_a_count_git_would_refuse_is_replaced(self):
        env = with_config({"GIT_CONFIG_COUNT": "two"}, SAFE_CONFIG)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "2")

    def test_every_factory_git_call_gets_the_safe_config(self):
        with mock.patch.dict(os.environ, NO_GIT_CONFIG_ENV, clear=True):
            env = Git("/t")._env()
        pairs = [(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"])
                 for i in range(int(env["GIT_CONFIG_COUNT"]))]
        self.assertEqual(pairs, [("core.hooksPath", NO_HOOKS), ("core.fsmonitor", "false")])
        self.assertFalse(os.path.exists(NO_HOOKS))


def plain_git(*args, cwd):
    """git without the factory's environment: what a repository's hooks normally see."""
    return subprocess.run(["git", *args], cwd=cwd, env=NO_GIT_CONFIG_ENV, capture_output=True,
                          text=True, check=False)


@unittest.skipUnless(shutil.which("git"), "needs git")
class FactoryGitRunsNoRepositoryProgramTest(unittest.TestCase):
    """A clone of a local remote with hooks and an fsmonitor script; the remote's main
    is one commit ahead, so a pull merges (post-merge)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.markers = root / "markers"
        self.markers.mkdir()
        src = root / "src"
        plain_git("init", "-q", "-b", "main", str(src), cwd=root)
        for key, value in (("user.email", "t@example.com"), ("user.name", "t"),
                           ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
            plain_git("config", key, value, cwd=src)
        self.commit(src, "one")
        plain_git("clone", "-q", "--bare", str(src), "remote.git", cwd=root)
        plain_git("clone", "-q", "remote.git", "clone", cwd=root)
        self.clone = root / "clone"
        for key, value in (("user.email", "t@example.com"), ("user.name", "t"),
                           ("core.autocrlf", "false")):
            plain_git("config", key, value, cwd=self.clone)
        plain_git("branch", "-q", "other", cwd=self.clone)
        self.commit(src, "two")  # the remote moves on: the clone's pull will merge
        plain_git("--git-dir", "remote.git", "fetch", "-q", str(src), "main:main", cwd=root)
        for hook in HOOKS:
            self.script(self.clone / ".git" / "hooks" / hook, hook)
        fsmonitor = root / "fsmonitor.sh"
        self.script(fsmonitor, "fsmonitor", exit_code=1)
        plain_git("config", "core.fsmonitor", fsmonitor.as_posix(), cwd=self.clone)

    def commit(self, repo, message):
        (repo / "f").write_text(message + "\n", encoding="utf-8")
        plain_git("add", "f", cwd=repo)
        plain_git("commit", "-q", "-m", message, cwd=repo)

    def script(self, path, marker, exit_code=0):
        path.write_text(f'#!/bin/sh\necho ran >> "{(self.markers / marker).as_posix()}"\n'
                        f"exit {exit_code}\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def ran(self):
        return sorted(p.name for p in self.markers.iterdir())

    def operations(self, run):
        run("status", "--porcelain")
        run("diff")
        run("switch", "-q", "other")
        run("switch", "-q", "main")
        run("fetch", "-q", "origin")
        run("pull", "-q", "--ff-only", "origin", "main")

    def test_control_plain_git_runs_the_repository_programs(self):
        # Without this, "no marker" below would prove nothing.
        self.operations(lambda *args: plain_git(*args, cwd=self.clone))
        self.assertEqual(self.ran(), sorted([*HOOKS, "fsmonitor"]))

    def test_the_factory_git_calls_run_none_of_them(self):
        git = Git(self.clone)
        with mock.patch.dict(os.environ, NO_GIT_CONFIG_ENV, clear=True):
            self.operations(lambda *args: git.run(list(args)))
            ensure.ensure_branch(git, "story/1-x", "main")  # fetch, then switch -c
        self.assertEqual(self.ran(), [])
        self.assertEqual(git.run(["rev-parse", "--abbrev-ref", "HEAD"]).strip(), "story/1-x")

    def test_config_already_in_the_environment_still_applies(self):
        # GIT_CONFIG_COUNT entries the factory inherits are kept, and still outrank the
        # repository's own config.
        env = {**NO_GIT_CONFIG_ENV, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name",
               "GIT_CONFIG_VALUE_0": "from-env"}
        with mock.patch.dict(os.environ, env, clear=True):
            git = Git(self.clone)
            self.assertEqual(git.run(["config", "--get", "user.name"]).strip(), "from-env")
            self.assertEqual(git.run(["config", "--get", "core.hooksPath"]).strip(), NO_HOOKS)
            self.operations(lambda *args: git.run(list(args)))
        self.assertEqual(self.ran(), [])


if __name__ == "__main__":
    unittest.main()
