"""Unit tests for the gh I/O layer (T1.1): FakeGh, recorder, errors, timeouts, auth."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import gh as gh_module
from factory.errors import (
    CommandError,
    CommandNotFound,
    CommandTimeout,
    ForbiddenCommand,
    GhAuthError,
    GhError,
    GhJsonError,
)
from factory.gh import DEFAULT_TIMEOUT, Gh, ProcessResult, run_process
from factory.gh_fixtures import (
    FakeGh,
    RecordingTransport,
    UnexpectedCall,
    load_cassette,
)
from tests import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "gh"


def interaction(args, stdout="", returncode=0, stderr="", input=None):
    return {"args": args, "input": input, "returncode": returncode, "stdout": stdout,
            "stderr": stderr}


class RecordedFixtureTest(unittest.TestCase):
    """Replays responses recorded from real gh against the sandbox repo."""

    def test_replay_success(self):
        gh = FakeGh.from_file(FIXTURES / "repo_view.json")
        data = gh.json(
            ["repo", "view", "Nandan-krishnamurthy/factory-sandbox"],
            fields=["nameWithOwner", "isEmpty", "visibility", "defaultBranchRef"],
        )
        self.assertEqual(data["nameWithOwner"], "Nandan-krishnamurthy/factory-sandbox")
        self.assertTrue(data["isEmpty"])

    def test_replay_real_error_shows_stderr(self):
        gh = FakeGh.from_file(FIXTURES / "repo_view.json")
        with self.assertRaises(GhError) as ctx:
            gh.json(["repo", "view", "Nandan-krishnamurthy/does-not-exist-factory-test"],
                    fields=["nameWithOwner"])
        self.assertEqual(ctx.exception.returncode, 1)
        self.assertIn("Could not resolve to a Repository", str(ctx.exception))


class FakeGhTest(unittest.TestCase):
    def test_json_appends_fields_and_parses(self):
        gh = FakeGh([interaction(["issue", "list", "--json", "number,title"],
                                 '[{"number": 1, "title": "a"}]')])
        self.assertEqual(gh.json(["issue", "list"], fields=["number", "title"]),
                         [{"number": 1, "title": "a"}])
        gh.assert_all_used()

    def test_identical_calls_replay_in_recorded_order(self):
        args = ["pr", "view", "1", "--json", "state"]
        gh = FakeGh([interaction(args, '{"state": "OPEN"}'),
                     interaction(args, '{"state": "MERGED"}')])
        self.assertEqual(gh.json(args)["state"], "OPEN")
        self.assertEqual(gh.json(args)["state"], "MERGED")
        with self.assertRaises(UnexpectedCall):
            gh.json(args)

    def test_unexpected_call_raises(self):
        gh = FakeGh([])
        with self.assertRaises(UnexpectedCall):
            gh.run(["issue", "list"])

    def test_unused_interactions_are_reported(self):
        gh = FakeGh([interaction(["label", "list"], "[]")])
        with self.assertRaises(AssertionError):
            gh.assert_all_used()

    def test_input_must_match(self):
        gh = FakeGh([interaction(["api", "graphql"], "{}", input="query-a")])
        with self.assertRaises(UnexpectedCall):
            gh.run(["api", "graphql"], input="query-b")
        self.assertEqual(gh.run(["api", "graphql"], input="query-a"), "{}")

    def test_invalid_json_raises_typed_error(self):
        gh = FakeGh([interaction(["repo", "view"], "not json")])
        with self.assertRaises(GhJsonError) as ctx:
            gh.json(["repo", "view"])
        self.assertIn("not json", str(ctx.exception))

    def test_nonzero_exit_is_gh_error_with_stderr(self):
        gh = FakeGh([interaction(["issue", "view", "9"], returncode=1,
                                 stderr="could not find issue 9")])
        with self.assertRaises(GhError) as ctx:
            gh.run(["issue", "view", "9"])
        err = ctx.exception
        self.assertIsInstance(err, CommandError)
        self.assertEqual(err.stderr, "could not find issue 9")
        self.assertIn("could not find issue 9", str(err))
        self.assertIn("gh issue view 9", str(err))

    def test_api_builds_args_and_merges_pages(self):
        gh = FakeGh([interaction(
            ["api", "repos/o/r/labels", "--method", "GET", "--paginate", "--slurp"],
            json.dumps([[{"name": "a"}], [{"name": "b"}]]))])
        self.assertEqual(gh.api("repos/o/r/labels", paginate=True),
                         [{"name": "a"}, {"name": "b"}])

    def test_api_fields(self):
        gh = FakeGh([interaction(
            ["api", "repos/o/r/labels", "--method", "POST", "-f", "name=x", "-f", "color=fff"],
            '{"name": "x"}')])
        self.assertEqual(gh.api("repos/o/r/labels", method="POST",
                                fields={"name": "x", "color": "fff"})["name"], "x")

    def test_repo_args(self):
        self.assertEqual(Gh(repo="o/r").repo_args(), ["--repo", "o/r"])
        self.assertEqual(Gh().repo_args(), [])


class TimeoutTest(unittest.TestCase):
    """AC: every call has a timeout."""

    def test_every_gh_call_passes_a_positive_timeout(self):
        gh = FakeGh([interaction(["a"], "1"), interaction(["b"], "2")], timeout=12)
        gh.run(["a"])
        gh.run(["b"], timeout=3)
        self.assertEqual([c["timeout"] for c in gh.replay.calls], [12, 3])

    def test_default_timeout(self):
        gh = FakeGh([interaction(["a"], "1")])
        gh.run(["a"])
        self.assertEqual(gh.replay.calls[0]["timeout"], DEFAULT_TIMEOUT)

    def test_non_positive_timeouts_rejected(self):
        for bad in (0, -1, None):
            with self.subTest(timeout=bad):
                with self.assertRaises(ValueError):
                    Gh(timeout=bad)
                with self.assertRaises(ValueError):
                    run_process([sys.executable, "-c", "pass"], timeout=bad)

    def test_run_process_always_passes_timeout_to_subprocess(self):
        fake = subprocess.CompletedProcess(["x"], 0, "out", "")
        with mock.patch.object(gh_module.subprocess, "run", return_value=fake) as run:
            run_process(["x"], timeout=7)
        self.assertEqual(run.call_args.kwargs["timeout"], 7)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)


class RunProcessTest(unittest.TestCase):
    """Real processes (the Python interpreter) — no network, no gh needed."""

    def test_success_captures_stdout_utf8(self):
        result = run_process([sys.executable, "-c", "print('ok ✓')"], timeout=30,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ok ✓")

    def test_nonzero_exit_is_returned_with_stderr(self):
        code = "import sys; sys.stderr.write('boom'); sys.exit(3)"
        result = run_process([sys.executable, "-c", code], timeout=30)
        self.assertEqual((result.returncode, result.stderr), (3, "boom"))

    def test_timeout_raises_command_timeout(self):
        with self.assertRaises(CommandTimeout) as ctx:
            run_process([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.5)
        self.assertIn("timed out after 0.5s", str(ctx.exception))

    def test_missing_executable_raises_not_found(self):
        with self.assertRaises(CommandNotFound) as ctx:
            run_process(["definitely-not-a-real-exe-xyz"], timeout=5)
        self.assertIn("not found", str(ctx.exception))

    def test_input_is_passed_on_stdin(self):
        code = "import sys; print(sys.stdin.read().upper())"
        result = run_process([sys.executable, "-c", code], timeout=30, input="hi")
        self.assertEqual(result.stdout.strip(), "HI")

    def test_long_stderr_is_truncated_in_message(self):
        err = GhError(["gh", "x"], 1, "", "e" * 5000)
        self.assertIn("[truncated]", str(err))
        self.assertLess(len(str(err)), 2200)


class AuthInjectionTest(unittest.TestCase):
    """The single place auth is injected (future bot mode, architecture §9.4)."""

    def capture(self, **kwargs):
        seen = {}

        def transport(argv, *, timeout, cwd=None, env=None, input=None):
            seen["env"] = env
            return ProcessResult(list(argv), 0, "{}", "")

        Gh(transport=transport, **kwargs).run(["api", "user"])
        return seen["env"]

    def test_token_injected_from_named_env_var(self):
        with mock.patch.dict(os.environ, {"FACTORY_BOT_TOKEN": "secret-value"}):
            env = self.capture(token_env="FACTORY_BOT_TOKEN")
        self.assertEqual(env["GH_TOKEN"], "secret-value")

    def test_missing_token_env_var_raises(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FACTORY_BOT_TOKEN", None)
            with self.assertRaises(GhAuthError):
                self.capture(token_env="FACTORY_BOT_TOKEN")

    def test_non_interactive_environment(self):
        env = self.capture()
        self.assertEqual(env["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(env["GH_PAGER"], "")


class MergeRefusalTest(unittest.TestCase):
    """Backstop for rule S1: the I/O layer refuses merge commands before running them."""

    def test_merge_paths_refused_without_running(self):
        refused = [
            ["pr", "merge", "5"],
            ["pr", "merge", "--squash", "5"],
            ["api", "repos/o/r/pulls/5/merge", "--method", "PUT"],
            ["api", "/repos/o/r/pulls/5/merge/"],
            ["api", "repos/o/r/merges", "--method", "POST"],
            ["api", "graphql", "-f", "query=mutation { mergePullRequest(input: {}) { x } }"],
            ["api", "graphql", "-f", "query=mutation { enablePullRequestAutoMerge(input:{}) }"],
        ]
        for args in refused:
            with self.subTest(args=args):
                gh = FakeGh([])
                with self.assertRaises(ForbiddenCommand):
                    gh.run(args)
                self.assertEqual(gh.replay.calls, [])  # never reached the process layer

    def test_harmless_mentions_of_merge_allowed(self):
        allowed = [
            ["pr", "view", "5", "--json", "mergedAt,state"],
            ["api", "repos/o/r/pulls/5", "--method", "GET"],
            ["api", "repos/o/r/issues/5/comments", "-f", "body=please /merge this later"],
        ]
        for args in allowed:
            with self.subTest(args=args):
                FakeGh([interaction(args, "{}")]).run(args)


class RecorderTest(unittest.TestCase):
    def test_record_then_replay_round_trip_with_redaction(self):
        token = "ghp_" + "A" * 36

        def inner(argv, *, timeout, cwd=None, env=None, input=None):
            return ProcessResult(list(argv), 0, json.dumps({"login": "me", "t": token}), "")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "c.json"
            rec = RecordingTransport(path, inner=inner)
            Gh(transport=rec).json(["api", "user"])
            rec.save()
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(token, text)
            self.assertIn("<redacted-token>", text)
            self.assertNotIn("GH_TOKEN", text)  # environment never recorded
            self.assertEqual(load_cassette(path)[0]["args"], ["api", "user"])
            replayed = FakeGh.from_file(path).json(["api", "user"])
        self.assertEqual(replayed["login"], "me")

    def test_unsupported_cassette_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text('{"version": 99, "interactions": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_cassette(path)


if __name__ == "__main__":
    unittest.main()
