"""B-15, E3: the approved commands run in a cleaned environment.

``verify run`` gives every configured command ``evidence.verification_env``: no GitHub
token or authentication helper, no variable named like a secret, no inherited
command-line git config, an empty ``gh`` config folder, an empty global git config, no
system git config, and no prompts. Everything else is kept, because a project's tools
need it.

This is a speed bump, not a sandbox (ADR-0006): code running as the user can still read
the operating system's credential store or files in the user's home directly. The live
tests show that ``gh`` and git's credential helper are not logged in for the commands. They
never print a credential: they check exit codes and the absence of ``password=``, and
assert without echoing output.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import evidence
from factory.gh import run_command_line
from tests.test_evidence import run

REMOVED = {"GH_TOKEN": "ghp_test", "GITHUB_TOKEN": "t", "GH_ENTERPRISE_TOKEN": "t",
           "GITHUB_ENTERPRISE_TOKEN": "t", "GIT_ASKPASS": "askpass", "SSH_ASKPASS": "a",
           "SSH_AUTH_SOCK": "/tmp/agent", "NPM_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "s",
           "AWS_ACCESS_KEY_ID": "k", "MY_API_KEY": "k", "DB_PASSWORD": "p",
           "GOOGLE_APPLICATION_CREDENTIALS": "/c.json", "gh_token": "lower-case",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "credential.helper",
           "GIT_CONFIG_VALUE_0": "store", "GIT_CONFIG_PARAMETERS": "'credential.helper'='x'",
           "GIT_CONFIG": "/evil"}
KEPT = {"PATH": "/usr/bin", "HOME": "/home/u", "GIT_AUTHOR_NAME": "a", "CI": "1",
        "NODE_OPTIONS": "--max-old-space-size=4096", "LANG": "C.UTF-8"}
OVERRIDES = ("GH_CONFIG_DIR", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GCM_INTERACTIVE",
             "GIT_TERMINAL_PROMPT")


class VerificationEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_credentials_and_secrets_are_removed_and_the_rest_kept(self):
        env = evidence.verification_env({**REMOVED, **KEPT}, self.home)
        self.assertEqual(sorted(set(REMOVED) & set(env)), [])
        self.assertEqual({k: env[k] for k in KEPT}, KEPT)
        self.assertEqual(set(env), set(KEPT) | set(OVERRIDES))

    def test_gh_and_git_config_are_isolated(self):
        env = evidence.verification_env(KEPT, self.home)
        gh_dir, git_config = Path(env["GH_CONFIG_DIR"]), Path(env["GIT_CONFIG_GLOBAL"])
        self.assertTrue(gh_dir.is_dir())
        self.assertEqual(list(gh_dir.iterdir()), [])
        self.assertEqual(git_config.read_text(encoding="utf-8"), "")
        self.assertTrue(self.home in gh_dir.parents and self.home in git_config.parents)
        self.assertEqual((env["GIT_CONFIG_NOSYSTEM"], env["GCM_INTERACTIVE"],
                          env["GIT_TERMINAL_PROMPT"]), ("1", "never", "0"))

    def test_an_inherited_override_cannot_point_elsewhere(self):
        env = evidence.verification_env({**KEPT, "GH_CONFIG_DIR": "/real/gh",
                                         "GIT_CONFIG_GLOBAL": "/real/.gitconfig",
                                         "GIT_CONFIG_NOSYSTEM": "0"}, self.home)
        self.assertEqual(Path(env["GH_CONFIG_DIR"]).parent, self.home)
        self.assertEqual(Path(env["GIT_CONFIG_GLOBAL"]).parent, self.home)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")


class VerifyRunEnvTest(unittest.TestCase):
    def test_every_command_gets_the_cleaned_environment(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "ghp_inherited", "NPM_TOKEN": "x"}):
            result, runner = run()
        self.assertEqual(len(runner.envs), 3)  # build, typecheck, test (lint is null)
        for env in runner.envs:
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("NPM_TOKEN", env)
            self.assertTrue(all(name in env for name in OVERRIDES))
            self.assertEqual(env["PATH"], os.environ["PATH"])
        self.assertEqual(len({e["GH_CONFIG_DIR"] for e in runner.envs}), 1)  # one per run
        # The empty config folders are removed after the run.
        self.assertFalse(Path(runner.envs[0]["GH_CONFIG_DIR"]).parent.exists())
        self.assertEqual(result.failures(), [])

    def test_run_command_line_needs_an_environment(self):
        with self.assertRaises(TypeError):
            run_command_line("true", timeout=5, cwd=".")  # no env: never inherited silently


def logged_in(*command):
    """Whether the command reports success in the user's normal environment."""
    return subprocess.run(list(command), capture_output=True, text=True,
                          check=False).returncode == 0


class LiveIsolationTest(unittest.TestCase):
    """Run against the real ``gh`` and git of this machine. Skipped when there is nothing
    to isolate (not logged in, no credential helper): then they would prove nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = evidence.verification_env(os.environ, Path(self.tmp.name))

    def run_cleaned(self, command):
        return run_command_line(command, timeout=60, cwd=self.tmp.name, env=self.env)

    @unittest.skipUnless(shutil.which("gh"), "needs gh")
    def test_gh_is_not_logged_in_for_the_commands(self):
        if not logged_in("gh", "auth", "status"):
            self.skipTest("gh is not logged in here, so isolation would prove nothing")
        result = self.run_cleaned("gh auth status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not logged in", result.stdout.lower())

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_git_has_no_credential_helper_for_the_commands(self):
        if not logged_in("git", "config", "--get-all", "credential.helper"):
            self.skipTest("no credential helper is configured here, so nothing to isolate")
        helpers = self.run_cleaned("git config --get-all credential.helper")
        self.assertNotEqual(helpers.returncode, 0, "a credential helper is still configured")
        self.assertEqual(self.run_cleaned("git config --list --show-origin").stdout.strip(),
                         "", "a global or system git config is still read")
        # With no helper and no prompt, asking git for a credential must fail. The output
        # is never shown, so a regression could not print a token into the test log.
        asked = self.run_cleaned("printf 'protocol=https\\nhost=github.com\\n\\n' | "
                                 "git credential fill")
        self.assertNotEqual(asked.returncode, 0, "git produced a credential")
        self.assertFalse("password=" in asked.stdout, "git produced a credential")


if __name__ == "__main__":
    unittest.main()
