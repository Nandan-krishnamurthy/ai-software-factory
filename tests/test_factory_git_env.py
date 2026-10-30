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
from factory.git import NO_HOOKS, SAFE_CONFIG, Git, unopenable, with_config

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
        self.assertTrue(env["GIT_CONFIG_PARAMETERS"].endswith(
            f"'core.hooksPath={NO_HOOKS}' 'core.fsmonitor=false'"))

    def test_inherited_parameters_are_kept_and_ours_come_last(self):
        # G1: git reads GIT_CONFIG_PARAMETERS after GIT_CONFIG_COUNT, and the last value
        # of a key wins, so ours go at the end of both.
        env = with_config({"GIT_CONFIG_PARAMETERS": "'core.hookspath'='/x' 'user.name'='y'"},
                          SAFE_CONFIG)
        self.assertEqual(env["GIT_CONFIG_PARAMETERS"],
                         f"'core.hookspath'='/x' 'user.name'='y' 'core.hooksPath={NO_HOOKS}' "
                         "'core.fsmonitor=false'")

    def test_a_quote_in_a_value_is_quoted_as_git_does(self):
        env = with_config({}, (("user.name", "O'Neil"),))
        self.assertEqual(env["GIT_CONFIG_PARAMETERS"], "'user.name=O'\\''Neil'")

    def test_the_paths_are_absolute_and_keep_nothing(self):
        # G4: on Windows os.devnull is `nul`, so `nul\\x` would be looked up inside the
        # repository; the device-namespace form is absolute.
        for path in (NO_HOOKS, unopenable("factory-no-grafts")):
            with self.subTest(path=path):
                self.assertTrue(os.path.isabs(path))
                self.assertFalse(os.path.isdir(path))
                child = os.path.join(path, "post-checkout")
                try:
                    with open(child, "w", encoding="utf-8") as handle:
                        handle.write("#!/bin/sh\n")
                except OSError:
                    pass  # not a folder: nothing can be written there at all
                self.assertFalse(os.path.isfile(child))  # nothing written there is kept


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

    def plant_hook(self, folder, marker):
        folder.mkdir(parents=True, exist_ok=True)
        self.script(folder / "post-checkout", marker)

    def test_inherited_git_config_parameters_cannot_turn_hooks_back_on(self):
        # G1: `git -c core.hooksPath=…` passes GIT_CONFIG_PARAMETERS to child processes, and
        # a typed command can set it in front of `python scripts/factory.py …`.
        planted = Path(self.tmp.name) / "planted-hooks"
        self.plant_hook(planted, "planted")
        self.script(Path(self.tmp.name) / "monitor.sh", "planted-fsmonitor", exit_code=1)
        inherited = (f"'core.hookspath'='{planted.as_posix()}' 'core.fsmonitor'="
                     f"'{(Path(self.tmp.name) / 'monitor.sh').as_posix()}'")
        env = {**NO_GIT_CONFIG_ENV, "GIT_CONFIG_PARAMETERS": inherited}
        # Control: plain git with that variable runs the planted programs.
        for args in (["switch", "-q", "other"], ["switch", "-q", "main"], ["status"]):
            subprocess.run(["git", *args], cwd=self.clone, env=env, capture_output=True,
                           check=False)
        self.assertIn("planted", self.ran())
        for marker in self.markers.iterdir():
            marker.unlink()
        with mock.patch.dict(os.environ, env, clear=True):
            git = Git(self.clone)
            self.assertEqual(git.run(["config", "--get", "core.hooksPath"]).strip(), NO_HOOKS)
            self.operations(lambda *args: git.run(list(args)))
            ensure.ensure_branch(git, "story/2-x", "main")
        self.assertEqual(self.ran(), [])

    @unittest.skipUnless(os.name == "nt", "the relative `nul\\…` form is Windows-only")
    def test_a_folder_planted_at_the_old_relative_path_is_never_used(self):
        # G4: `nul\\factory-no-hooks` was relative to the repository. A folder of that name
        # (made through the \\?\ prefix, which allows device names) held a post-checkout
        # hook that git tried to run, and the factory's `git switch` failed.
        device_named = "\\\\?\\" + str(self.clone / "nul")
        old = device_named + "\\factory-no-hooks"
        os.makedirs(old, exist_ok=True)
        # Only the \\?\ form can delete a folder named after a device. This runs before the
        # temporary folder's own cleanup.
        self.addCleanup(shutil.rmtree, device_named, ignore_errors=True)
        with open(old + "\\post-checkout", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f'#!/bin/sh\necho ran >> "{(self.markers / "planted").as_posix()}"\n')
        git = Git(self.clone)
        with mock.patch.dict(os.environ, NO_GIT_CONFIG_ENV, clear=True):
            git.run(["switch", "-q", "other"])  # no "cannot spawn": it succeeds
            git.run(["switch", "-q", "main"])
        self.assertEqual(self.ran(), [])

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
