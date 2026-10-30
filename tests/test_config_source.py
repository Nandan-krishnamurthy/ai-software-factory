"""B-28: the approved config comes from GitHub's default branch, never from local refs.

``verify run`` runs only the commands a human merged (ADR-0004). Which commit holds them,
and the config in it, is what GitHub reports for the repository ``/factory-target``
recorded (ADR-0005): the default branch's name, its head commit, and
``.factory/config.json`` at that commit. The clone's ``origin/HEAD``, ``origin/main`` and
``origin`` URL never decide it. Every consumer of the evidence (``verify check``,
``verify map``, ``verdict check``, ``pr render`` and ``pr check``) checks the evidence's
recorded source against GitHub in the same way. Anything that cannot be confirmed fails
closed: nothing runs, and nothing is accepted.

The real-clone tests repoint the local refs with real git, the way a model or a project's
test code could, and show that the commands, the source and the diffs do not change.
"""

import ast
import base64
import contextlib
import io
import json
import os
import posixpath
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

from factory import acmap, cli, comments, evidence, prbody, target
from factory import config as config_mod
from factory.errors import CommandNotFound, CommandTimeout, GhAuthError, GitError
from factory.gh import Gh, ProcessResult
from factory.git import Git
from tests import REPO_ROOT
from tests.test_acmap import DiffingGitRepo, IssueGitHub, fixture, issue_body
from tests.test_comments import REPO, checkpoint
from tests.test_evidence import (
    COMMANDS,
    MAIN,
    NOT_FOUND,
    OTHER,
    SHA,
    ApprovedOnGitHub,
    FakeGitRepo,
    FakeRunner,
    config_json,
    run,
)
from tests.test_prbody import REPO as STORY_REPO
from tests.test_prbody import Story

NEW = "4" * 40  # a later head of the default branch
GH_502 = ProcessResult([], 1, "", "gh: Server Error (HTTP 502)")
APPROVED_RUN = ["npm run build", "npm run typecheck", "npm test"]


def ok(data):
    return ProcessResult([], 0, json.dumps(data), "")


def commands_run(runner):
    return [call[0] for call in runner.calls]


def config_with(**changes):
    return json.dumps({**json.loads(config_json(COMMANDS)), **changes})


# ----------------------------------------------------------------------------- the source


class GitHubSourceTest(unittest.TestCase):
    """The default branch, its head and the config are GitHub's (proposed AC1, AC2)."""

    def test_the_default_branch_its_head_and_the_config_come_from_github(self):
        github = ApprovedOnGitHub(FakeGitRepo())
        result, runner = run(github=github)
        self.assertEqual(github.calls, ["repo", "head", "config"])
        self.assertEqual(result.config_source, f"main@{MAIN}")
        self.assertEqual(commands_run(runner), APPROVED_RUN)

    def test_the_commands_are_githubs_not_the_clones(self):
        # The clone's copy of the default branch says `npm test`; GitHub's says `pytest`.
        github = ApprovedOnGitHub(config=config_json({**COMMANDS, "test": "pytest"}))
        result, runner = run(github=github, branch={**COMMANDS, "test": "pytest"})
        self.assertEqual(commands_run(runner), ["npm run build", "npm run typecheck", "pytest"])
        self.assertEqual(result.unapproved, [])

    def test_no_local_ref_is_read(self):
        class RefTrap(FakeGitRepo):
            def __call__(self, argv, **kwargs):
                if any("origin/" in a or "refs/remotes" in a for a in argv[3:]):
                    raise AssertionError(f"a local default-branch ref was read: {argv[3:]}")
                return super().__call__(argv, **kwargs)

        result, _ = run(repo=RefTrap())
        self.assertEqual(result.config_source, f"main@{MAIN}")

    def test_a_branch_name_the_config_does_not_share_runs_nothing(self):
        for github in (ApprovedOnGitHub(branch="trunk"),
                       ApprovedOnGitHub(config=config_with(default_branch="trunk"))):
            with self.subTest(github=github.branch):
                runner = FakeRunner()
                with self.assertRaisesRegex(evidence.EvidenceError,
                                            "default_branch.*nothing was run"):
                    run(github=github, runner=runner)
                self.assertEqual(runner.calls, [])

    def test_a_config_for_another_repository_runs_nothing(self):
        runner = FakeRunner()
        with self.assertRaisesRegex(evidence.EvidenceError, "someone/else.*nothing was run"):
            run(github=ApprovedOnGitHub(config=config_with(repo="someone/else")),
                runner=runner)
        self.assertEqual(runner.calls, [])

    def test_no_config_on_the_default_branch_runs_nothing(self):
        runner = FakeRunner()
        with self.assertRaisesRegex(evidence.EvidenceError, "no approved commands"):
            run(github=ApprovedOnGitHub(fail={"config": NOT_FOUND}), runner=runner)
        self.assertEqual(runner.calls, [])


class FailClosedTest(unittest.TestCase):
    """GitHub cannot be asked, or its answer is not what was asked for (proposed AC5)."""

    def assert_runs_nothing(self, github, pattern="nothing was run"):
        runner = FakeRunner()
        with self.assertRaisesRegex(evidence.EvidenceError, pattern):
            run(github=github, runner=runner)
        self.assertEqual(runner.calls, [])

    def test_each_failed_call_runs_nothing(self):
        failures = {"HTTP 502": GH_502,
                    "a timeout": CommandTimeout(["gh", "api"], None, detail="timed out"),
                    "no gh": CommandNotFound(["gh", "api"], None),
                    "no token": GhAuthError("GH_BOT_TOKEN is not set"),
                    "not JSON": ProcessResult([], 0, "<html>", "")}
        for kind in ("repo", "head", "config"):
            for why, outcome in failures.items():
                with self.subTest(kind=kind, why=why):
                    self.assert_runs_nothing(ApprovedOnGitHub(fail={kind: outcome}))

    def test_each_malformed_answer_runs_nothing(self):
        def content(text):
            return ok({"type": "file", "encoding": "base64",
                       "content": base64.b64encode(text.encode()).decode()})

        answers = {
            "repo": [ok({}), ok({"default_branch": ""}), ok({"default_branch": "a b"}),
                     ok({"default_branch": 7}), ok([])],
            "head": [ok({"ref": "refs/heads/main", "object": {"type": "tag", "sha": MAIN}}),
                     ok({"ref": "refs/heads/main", "object": {"type": "commit", "sha": "abc"}}),
                     ok({"ref": "refs/heads/other",
                         "object": {"type": "commit", "sha": MAIN}}),
                     ok({"ref": "refs/heads/main"}), ok([])],
            "config": [ok({"type": "dir"}), ok([{"type": "file"}]),
                       ok({"type": "file", "encoding": "none", "content": ""}),
                       ok({"type": "file", "encoding": "base64", "content": "!!!"}),
                       content("{not json"), content(json.dumps({"schema": 2})),
                       content("[]")],
        }
        for kind, outcomes in answers.items():
            for i, outcome in enumerate(outcomes):
                with self.subTest(kind=kind, case=i):
                    self.assert_runs_nothing(ApprovedOnGitHub(fail={kind: outcome}))


class OriginTest(unittest.TestCase):
    """The clone's ``origin`` must still be the repository ``/factory-target`` recorded:
    ``ls-remote`` and ``fetch`` use it (proposed AC1)."""

    def test_an_origin_that_is_not_the_targets_repository_runs_nothing(self):
        for url in ("https://github.com/evil/fork.git", "https://gitlab.com/owner/app.git",
                    "C:/elsewhere/app.git", ""):
            with self.subTest(url=url):
                runner = FakeRunner()
                with self.assertRaisesRegex(evidence.EvidenceError,
                                            "origin.*nothing was run"):
                    run(repo=FakeGitRepo(origin_url=url), runner=runner)
                self.assertEqual(runner.calls, [])

    def test_any_github_spelling_of_the_same_repository_is_accepted(self):
        for url in ("git@github.com:Owner/App.git", "https://github.com/owner/app",
                    "ssh://git@github.com/owner/app.git"):
            with self.subTest(url=url):
                result, _ = run(repo=FakeGitRepo(origin_url=url))
                self.assertEqual(result.config_source, f"main@{MAIN}")


# ----------------------------------------------------------------------------- the record


class SourceProblemsTest(unittest.TestCase):
    """The evidence's ``config_source`` must be a commit of GitHub's default branch
    (proposed AC4)."""

    def setUp(self):
        self.ev, _ = run()
        self.github = ApprovedOnGitHub(on_branch=[OTHER])

    def problems(self, source):
        self.ev.config_source = source
        gh = Gh(transport=self.github)
        approved = evidence.approved_config(Git("/t", transport=FakeGitRepo()), gh, REPO)
        return evidence.source_problems(gh, REPO, self.ev, approved)

    def test_the_current_head_is_accepted(self):
        self.assertEqual(self.problems(f"main@{MAIN}"), [])
        self.assertNotIn("compare", self.github.calls)

    def test_an_older_commit_of_the_default_branch_is_accepted(self):
        self.assertEqual(self.problems(f"main@{OTHER}"), [])
        self.assertIn("compare", self.github.calls)

    def test_a_commit_that_is_not_on_the_default_branch_is_rejected(self):
        problems = self.problems(f"main@{SHA}")  # e.g. the story's own commit
        self.assertEqual(len(problems), 1)
        self.assertIn("is not a commit of main on GitHub", problems[0])

    def test_another_branch_is_rejected(self):
        self.assertIn("not the default branch", self.problems(f"trunk@{MAIN}")[0])

    def test_evidence_from_before_b28_is_rejected(self):
        # The old form named a local ref and a short SHA: run `verify run` again.
        self.assertIn("run `verify run` again", self.problems("origin/main@3333333")[0])

    def test_a_failed_comparison_is_a_problem(self):
        self.github.fail = {"compare": GH_502}
        self.assertIn("could not confirm", self.problems(f"main@{OTHER}")[0])

    def test_no_source_is_left_to_check(self):
        # `check` already reports evidence that names no source; it is not reported twice.
        self.assertEqual(self.problems(""), [])
        self.assertIn("approved config", evidence.check(self.ev, issue=27, branch_head=SHA)[0])


TIGHTENED = {**COMMANDS, "test": "npm test && npm run test:e2e", "lint": "npm run lint"}


class SupersededConfigTest(unittest.TestCase):
    """Review finding B1: evidence recorded under an approved config that a later merge
    changed does not count, although its commit is still on the default branch."""

    def setUp(self):
        self.ev, runner = run()  # `verify run` while main is at MAIN, where test is npm test
        self.assertIn("npm test", commands_run(runner))
        self.github = ApprovedOnGitHub(head=NEW, on_branch={MAIN}, config=config_json(COMMANDS),
                                       configs={MAIN: config_json(COMMANDS)})

    def problems(self, ev=None):
        gh = Gh(transport=self.github)
        git = Git("/t", transport=FakeGitRepo(commits=(SHA, MAIN, NEW)))
        approved = evidence.approved_config(git, gh, REPO)
        return evidence.check_trusted(gh, REPO, ev or self.ev, approved, issue=27,
                                      branch_head=SHA)

    def test_the_review_scenario_is_rejected(self):
        # A merged PR (MAIN -> NEW) changes commands.test and sets commands.lint after the
        # evidence was recorded: before B1's fix, check_trusted returned no problem.
        self.github.config = config_json(TIGHTENED)
        problems = self.problems()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("commands.lint, commands.test changed on main after this evidence was "
                      "recorded (3333333 to 4444444)", problems[0])
        self.assertIn("run `verify run` again", problems[0])

    def test_a_changed_test_reports_entry_is_rejected(self):
        self.github.config = config_with(test_reports=["reports/junit.xml"])
        self.assertIn("test_reports changed on main", self.problems()[0])

    def test_a_command_that_was_pending_and_is_now_approved_is_rejected(self):
        ev, _ = run(branch={**COMMANDS, "lint": "npm run lint"})  # lint pending, not run
        self.assertEqual(ev.pending, {"lint": "npm run lint"})
        self.github.config = config_json({**COMMANDS, "lint": "npm run lint"})
        self.assertIn("commands.lint changed on main", self.problems(ev)[0])

    def test_a_changed_install_command_is_rejected(self):
        # verify run never runs install, but it sets up what the other commands run with.
        self.github.config = config_json({**COMMANDS, "install": "npm install --no-audit"})
        self.assertIn("commands.install changed on main", self.problems()[0])

    def test_an_unchanged_config_at_an_older_commit_is_accepted(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.github.calls.count("config"), 2)  # the head's, then MAIN's

    def test_an_older_config_that_cannot_be_read_is_rejected(self):
        self.github.configs = {MAIN: None}  # 404 at MAIN
        self.assertIn("could not be read", self.problems()[0])


class NormalizingGitHub:
    """A gh transport that resolves a request's path the way GitHub does. On 2026-10-30,
    ``git/ref/heads/x/../../../../pulls/42`` returned pull request #42 from the live API.
    This fake also decodes ``%2e`` to ``.`` first, as a worst case. It records each path
    it was sent, and answers branch refs from ``refs`` (name to response), the repository
    from ``repo``, and pull requests with a PR body."""

    def __init__(self, refs=None, repo=None):
        self.refs, self.repo, self.sent = dict(refs or {}), repo, []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        endpoint = argv[2]
        self.sent.append(endpoint)
        path = posixpath.normpath(re.sub(r"%2[eE]", ".", endpoint))
        if path == f"repos/{REPO}":
            return self.repo or ok({"full_name": REPO})
        if re.fullmatch(rf"repos/{REPO}/pulls/\d+", path):
            return ok({"number": int(path.rsplit("/", 1)[1]), "head": {"sha": SHA}})
        prefix = f"repos/{REPO}/git/ref/heads/"
        if path.startswith(prefix):
            answer = self.refs.get(unquote(path[len(prefix):]))
            return answer if answer is not None else NOT_FOUND
        return NOT_FOUND

    @staticmethod
    def branch(name, sha=SHA, kind="commit"):
        return ok({"ref": f"refs/heads/{name}", "object": {"type": kind, "sha": sha}})


class RemoteHeadTest(unittest.TestCase):
    """Second review: branch names checked before any request (F2), the exact ref and a
    commit required (F3), and a 404 that is a missing branch only in a reachable
    repository (F4)."""

    def head(self, github, name):
        return evidence.remote_head(Gh(transport=github), REPO, name)

    def test_a_name_git_rejects_is_never_sent(self):
        github = NormalizingGitHub()
        for name in ("x/../../../../pulls/42", "story/27-fake/../27-x", "../x", "a//b",
                     ".hidden/x", "a/.b", "a.lock", "a.lock/b", "-x", "HEAD", "@", "a@{1}",
                     "a b", "a~1", "a^", "a:b", "a?b", "a*b", "a[b", "a\\b", "a\x01b", "a/",
                     "/a", "a.", ""):
            with self.subTest(name=name):
                with self.assertRaisesRegex(evidence.EvidenceError,
                                            "not a valid git branch name"):
                    self.head(github, name)
        self.assertEqual(github.sent, [])  # nothing reached GitHub

    def test_a_legitimate_name_is_encoded_segment_by_segment(self):
        expected = {"story/41-due-today-label": "story/41-due-today-label",
                    "feature/x+y": "feature/x%2By", "release/1.2.3": "release/1.2.3",
                    "café": "caf%C3%A9", "a#b": "a%23b", "user@host": "user%40host",
                    "a{b}": "a%7Bb%7D", "%2e%2e/x": "%252e%252e/x"}
        for name, path in expected.items():
            with self.subTest(name=name):
                github = NormalizingGitHub(refs={name: NormalizingGitHub.branch(name)})
                self.assertEqual(self.head(github, name), SHA)
                self.assertEqual(github.sent, [f"repos/{REPO}/git/ref/heads/{path}"])

    def test_a_percent_encoded_dot_stays_literal(self):
        # `%2e%2e` is a legal branch name. Sent as `%252e%252e`, even a server that
        # decodes %2e before resolving the path sees no `..`.
        github = NormalizingGitHub()
        self.assertIsNone(self.head(github, "%2e%2e/%2e%2e/pulls/42"))
        self.assertEqual(github.sent, [
            f"repos/{REPO}/git/ref/heads/%252e%252e/%252e%252e/pulls/42", f"repos/{REPO}"])

    def test_only_the_exact_ref_counts(self):
        # Whatever GitHub resolved the request to, an answer for another ref is not it.
        github = NormalizingGitHub(refs={"story/27-y": NormalizingGitHub.branch("story/27-x")})
        self.assertIsNone(self.head(github, "story/27-y"))

    def test_a_ref_that_is_not_a_commit_is_refused(self):
        github = NormalizingGitHub(refs={"story/27-x": NormalizingGitHub.branch(
            "story/27-x", kind="tag")})
        with self.assertRaisesRegex(evidence.EvidenceError, "names no commit"):
            self.head(github, "story/27-x")

    def test_a_missing_branch_in_a_reachable_repository_is_none(self):
        github = NormalizingGitHub()
        self.assertIsNone(self.head(github, "story/9-z"))
        self.assertEqual(github.sent[-1], f"repos/{REPO}")  # the repository was confirmed

    def test_a_404_from_an_unreachable_repository_is_not_a_missing_branch(self):
        for why, answer in {"hidden (404)": NOT_FOUND,
                            "forbidden (403)": ProcessResult([], 1, "", "gh: Forbidden (HTTP 403)"),
                            "unavailable (502)": GH_502}.items():
            with self.subTest(why=why):
                with self.assertRaises(evidence.EvidenceError) as caught:
                    self.head(NormalizingGitHub(repo=answer), "story/27-x")
                message = str(caught.exception)
                self.assertIn("not shown to be a missing branch", message)
                self.assertIn("gh auth status", message)
                self.assertNotIn("push it", message)

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_the_rules_are_gits(self):
        # Parity with `git check-ref-format --branch`. One deliberate difference: git
        # accepts `@` there as shorthand for the current branch, which is no branch name.
        names = ["story/41-due-today-label", "feature/x+y", "release/1.2.3", "café", "a#b",
                 "user@host", "a{b}", "%2e%2e", "a@b", "a.b/c_d-e", "HEAD", "-x", "a@{b",
                 "a/../b", "../x", "a//b", "/a", "a/", "a.", "a.lock", "a/b.lock",
                 "a.lock/b", ".a", "a/.b", "a b", "a~1", "a^", "a:b", "a?b", "a*b", "a[b",
                 "a\\b", "a..b", "a\x7fb"]
        git = Git(tempfile.gettempdir())
        for name in names:
            with self.subTest(name=name):
                try:
                    git.run(["check-ref-format", "--branch", name])
                    by_git = True
                except GitError:
                    by_git = False
                self.assertEqual(config_mod.is_git_branch_name(name), by_git)
        self.assertFalse(config_mod.is_git_branch_name("@"))


class LocalCommitTest(unittest.TestCase):
    """The diffs need GitHub's head in the clone. The factory never fetches it (B-46, D2;
    ADR-0006): a missing commit stops with an instruction to fetch."""

    def test_a_commit_the_clone_has_is_used(self):
        repo = FakeGitRepo()
        self.assertEqual(evidence.local_commit(Git("/t", transport=repo), MAIN), MAIN)
        self.assertEqual(repo.fetches, [])

    def test_a_missing_commit_is_refused_with_a_fetch_instruction(self):
        # Even when a fetch would have worked, the factory does not make it.
        repo = FakeGitRepo(commits=(SHA,), fetchable=(MAIN,))
        with self.assertRaisesRegex(evidence.EvidenceError,
                                    r"3333333: run `git -C /t fetch origin`, then run this "
                                    r"command again; nothing was run or accepted"):
            evidence.local_commit(Git("/t", transport=repo), MAIN)
        self.assertEqual(repo.fetches, [])


# ----------------------------------------------------------------------------- consumers


class ConsumersTest(unittest.TestCase):
    """``verify check``, ``verify map`` and ``verdict check`` hold the recorded source
    against GitHub, and the map's diff base is GitHub's head (proposed AC3, AC4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "target"
        (self.path / ".factory").mkdir(parents=True)
        (self.path / ".factory" / "config.json").write_text(config_json(COMMANDS),
                                                            encoding="utf-8")
        self.scratch = Path(self.tmp.name) / "scratch"
        self.scratch.mkdir()
        self.issues = IssueGitHub({27: issue_body(5)})
        self.repo = DiffingGitRepo(fixture("27.diff"), remote={"refs/heads/story/27-x": SHA},
                                   commits=(SHA, MAIN, NEW))
        self.github = ApprovedOnGitHub(self.repo, inner=self.issues)
        checkpoint(Gh(transport=self.issues), number=27, branch="story/27-x", sha=SHA)
        runner = FakeRunner({"npm test": (0, fixture("27.output.txt"))})
        code, out, err = self.cli("verify", "run", "--issue", "27", runner=runner)
        self.assertEqual(code, 0, out + err)
        code, out, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 0, out + err)
        checkpoint(Gh(transport=self.issues), number=27, station="S10", next_station="S11",
                   branch="story/27-x", sha=SHA, note=fixture("27.verdict.md"))
        self.repo.diffs.clear()

    def cli(self, *argv, runner=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               return_value=target.Target(self.path, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.github)), \
                mock.patch.object(cli, "Git", lambda p: Git(p, transport=self.repo)), \
                mock.patch.object(evidence, "run_command_line", runner or FakeRunner()), \
                mock.patch.object(evidence, "guard_vetter", lambda p: lambda c: None), \
                mock.patch.object(evidence, "default_path",
                                  lambda n: self.scratch / f"evidence-{n}.json"), \
                mock.patch.object(acmap, "default_path",
                                  lambda n: self.scratch / f"acmap-{n}.json"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def forge_source(self, source):
        """Rewrite the recorded evidence's source, as evidence recorded through a
        repointed local ref would have it."""
        body = self.issues.checkpoint_comments(27)[0]["body"]
        recorded = evidence.from_body(body)
        recorded.config_source = source
        comments.set_checkpoint_evidence(Gh(transport=self.issues), REPO, 27,
                                         evidence.to_block(recorded))

    def test_the_genuine_source_is_accepted_by_every_consumer(self):
        self.assertEqual(self.cli("verify", "check", "--issue", "27")[0], 0)
        code, _, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.repo.diffs, [f"{MAIN}...{SHA}"])
        self.assertEqual(acmap.read(self.scratch / "acmap-27.json").base, "main@3333333")
        code, out, _ = self.cli("verdict", "check", "--issue", "27")
        self.assertEqual(code, 0, out)

    def test_a_forged_source_is_rejected_by_every_consumer(self):
        why = {f"main@{SHA}": "is not a commit of main on GitHub",  # a repointed origin/main
               "origin/main@3333333": "run `verify run` again",  # recorded before B-28
               f"story/27-x@{SHA}": "not the default branch"}  # a repointed origin/HEAD
        for source, reason in why.items():
            with self.subTest(source=source):
                self.forge_source(source)
                code, out, _ = self.cli("verify", "check", "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn("REJECTED", out)
                self.assertIn(reason, out)
                code, _, err = self.cli("verify", "map", "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn("the evidence cannot be mapped", err)
                self.assertIn(reason, err)
                code, out, _ = self.cli("verdict", "check", "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn(reason, out)

    def test_after_the_default_branch_moves_on_the_evidence_stays_valid(self):
        self.github.head, self.github.on_branch = NEW, {MAIN}
        self.assertEqual(self.cli("verify", "check", "--issue", "27")[0], 0)
        code, _, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.repo.diffs, [f"{NEW}...{SHA}"])  # against GitHub's new head

    def test_after_a_force_push_of_the_default_branch_the_evidence_is_rejected(self):
        self.github.head = NEW  # MAIN is no longer on the branch
        code, out, _ = self.cli("verify", "check", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("is not a commit of main on GitHub", out)

    def test_github_unreachable_accepts_nothing(self):
        self.github.fail = {"head": GH_502}
        for argv in (["verify", "check"], ["verify", "map"], ["verdict", "check"]):
            with self.subTest(argv=argv):
                code, _, err = self.cli(*argv, "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn("HTTP 502", err)

    def test_after_the_approved_commands_change_every_consumer_rejects(self):
        # Review finding B1, through the CLI: MAIN -> NEW changes the approved commands.
        self.github.configs = {MAIN: self.github.config_text()}
        self.github.config = config_json(TIGHTENED)
        self.github.head, self.github.on_branch = NEW, {MAIN}
        for argv in (["verify", "check"], ["verify", "map"], ["verdict", "check"]):
            with self.subTest(argv=argv):
                code, out, err = self.cli(*argv, "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn("commands.lint, commands.test changed on main", out + err)

    def test_a_missing_default_branch_head_stops_verify_map_with_a_fetch_instruction(self):
        self.github.head, self.github.on_branch = "5" * 40, {MAIN}  # not in the clone
        code, _, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("5555555: run `git -C ", err)
        self.assertIn(" fetch origin`, then run this command again", err)
        self.assertEqual(self.repo.fetches, [])

    def test_a_missing_branch_is_reported_as_missing(self):
        self.repo.remote = {}  # GitHub has no story/27-x; the repository is reachable
        code, out, _ = self.cli("verify", "check", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("story/27-x is not on GitHub (the repository is reachable", out)
        self.assertIn("push it", out)

    def test_an_unreachable_repository_is_not_reported_as_a_missing_branch(self):
        # approved_config reads the repository first; the second read, after the branch's
        # 404, fails: the credentials no longer see it.
        self.repo.remote = {}
        self.github.fail_on_call = {"repo": (2, NOT_FOUND)}
        for argv in (["verify", "check"], ["verify", "map"], ["verdict", "check"]):
            with self.subTest(argv=argv):
                self.github.calls.clear()
                code, out, err = self.cli(*argv, "--issue", "27")
                self.assertEqual(code, 1)
                self.assertIn("not shown to be a missing branch", err)
                self.assertNotIn("push it", out + err)

    def test_the_branch_head_is_githubs_not_gits(self):
        # Review finding B2: whatever `git ls-remote` would answer is never asked.
        self.github.heads = {"story/27-x": SHA}
        self.repo.remote = {"refs/heads/story/27-x": OTHER}  # git's answer, ignored
        for argv in (["verify", "check"], ["verify", "map"], ["verdict", "check"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv, "--issue", "27")[0], 0)
        self.github.heads = {"story/27-x": OTHER}  # GitHub moves on; git still says SHA
        self.repo.remote = {"refs/heads/story/27-x": SHA}
        code, out, _ = self.cli("verify", "check", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("but the head of story/27-x is 2222222", out)


class PrBodyTest(unittest.TestCase):
    """``pr render`` and ``pr check`` take the size limit, CI and the diff base from
    GitHub's default branch, and refuse evidence whose source is not on it (AC3, AC4)."""

    def test_the_size_limit_and_ci_come_from_githubs_config(self):
        story = Story(28)
        data = json.loads(story.github.config_text())
        story.github.config = json.dumps({**data, "limits": {"max_diff_lines": 50}})
        facts = story.facts()
        self.assertEqual((facts.max_diff_lines, facts.ci_required), (50, False))

    def test_the_diff_base_is_githubs_head(self):
        story, calls = Story(28), []
        replay = story.git

        def recording(argv, **kwargs):
            calls.append(argv[3:])
            return replay(argv, **kwargs)

        story.git = recording
        story.facts()
        self.assertIn(["merge-base", MAIN, story.head], calls)
        self.assertFalse([c for c in calls if any("origin/" in a for a in c)])

    def test_a_forged_source_is_refused(self):
        story = Story(28)
        story.evidence.config_source = f"main@{story.head}"
        with self.assertRaisesRegex(prbody.PrBodyError, "is not a commit of main on GitHub"):
            story.facts()
        story.pr_body = "x"
        with self.assertRaisesRegex(prbody.PrBodyError, "is not a commit of main on GitHub"):
            prbody.check(Gh(transport=story.github), Git("/t", transport=story.git),
                         STORY_REPO, story.pr)

    def test_github_unreachable_refuses(self):
        story = Story(28)
        story.github.fail = {"config": GH_502}
        with self.assertRaisesRegex(evidence.EvidenceError, "HTTP 502"):
            story.facts()

    def test_after_the_approved_commands_change_pr_render_refuses(self):
        # Review finding B1: the PR would otherwise show Q4 passing for replaced commands.
        story = Story(28)
        data = json.loads(story.github.config_text())
        story.github.configs = {MAIN: json.dumps(data)}
        story.github.config = json.dumps({**data, "commands": TIGHTENED})
        story.github.head, story.github.on_branch = NEW, {MAIN}
        with self.assertRaisesRegex(prbody.PrBodyError, "changed on main after this evidence"):
            story.facts()


# ----------------------------------------------------------------------------- real clones


@unittest.skipUnless(shutil.which("git"), "needs git")
class RealCloneTest(unittest.TestCase):
    """Real git repoints the clone's refs; nothing the factory trusts changes (AC3).

    ``main`` (``M``) holds the approved config. The story branch adds a test file (``S1``)
    and changes ``commands.test`` (``S2``). GitHub, faked, says ``main`` is at ``M``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "clone"
        self.path.mkdir()
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "t"), ("user.email", "t@example.com"),
                           ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
            self.git("config", key, value)
        self.write(".factory/config.json", config_json(COMMANDS))
        self.m = self.commit("approved config")
        self.git("switch", "-q", "-c", "story/27-x")
        self.write("tests/a.test.ts", "test('#27 AC1: x', () => {})\n")
        self.s1 = self.commit("add a test")
        self.write(".factory/config.json", config_json({**COMMANDS, "test": "echo forged"}))
        self.s2 = self.commit("forge the test command")
        self.git("remote", "add", "origin", f"https://github.com/{REPO}.git")
        self.git("update-ref", "refs/remotes/origin/main", self.m)
        self.git("update-ref", "refs/remotes/origin/story/27-x", self.s2)
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.github = ApprovedOnGitHub(head=self.m, config=config_json(COMMANDS))

    def git(self, *args):
        return Git(self.path).run(list(args)).strip()

    def write(self, rel, text):
        (self.path / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.path / rel).write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def verify_with(self, runner):
        return evidence.run_verification(self.path, issue=27, repo=REPO, git=Git(self.path),
                                         gh=Gh(transport=self.github), runner=runner)

    def verify(self):
        runner = FakeRunner()
        return self.verify_with(runner), runner

    def assert_approved_commands_ran(self):
        result, runner = self.verify()
        self.assertEqual(commands_run(runner), APPROVED_RUN)
        self.assertEqual(result.unapproved, ["commands.test"])
        self.assertEqual(result.config_source, f"main@{self.m}")
        self.assertTrue(evidence.check(result, issue=27, branch_head=result.sha))

    def assert_real_diff(self):
        """The story's whole change, against ``M``: the test file and the forged command."""
        diff = acmap.branch_diff(Git(self.path), self.m, self.s2)
        self.assertIn("tests/a.test.ts", diff)
        self.assertIn("echo forged", diff)
        facts = prbody.git_facts(Git(self.path), self.m, self.s2)
        self.assertEqual(sorted(f.path for f in facts.files),
                         [".factory/config.json", "tests/a.test.ts"])
        self.assertEqual(len(facts.commits), 2)

    def test_nothing_repointed(self):
        self.assert_approved_commands_ran()
        self.assert_real_diff()

    def test_update_ref_points_origin_main_at_the_story(self):
        self.git("update-ref", "refs/remotes/origin/main", self.s2)
        self.assert_approved_commands_ran()

    def test_set_head_names_the_story_branch(self):
        self.git("remote", "set-head", "origin", "story/27-x")
        self.assert_approved_commands_ran()

    def test_symbolic_ref_names_the_story_branch(self):
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/story/27-x")
        self.assert_approved_commands_ran()

    def test_a_forged_origin_main_that_is_not_on_the_remote(self):
        forged = self.git("commit-tree", f"{self.s2}^{{tree}}", "-p", self.m, "-m", "forged")
        self.git("update-ref", "refs/remotes/origin/main", forged)
        self.assert_approved_commands_ran()

    def test_a_replace_ref_cannot_swap_the_approved_commit(self):
        forged = self.git("commit-tree", f"{self.s2}^{{tree}}", "-m", "forged")
        self.git("replace", self.m, forged)
        self.assertIn("npm test", self.git("show", f"{self.m}:.factory/config.json"))
        self.assert_approved_commands_ran()
        self.assert_real_diff()

    def test_grafts_cannot_move_the_merge_base(self):
        # A root commit with S1's tree, made the parent of both M and S2: the merge base
        # would hide S1's test file from every diff.
        hiding = self.git("commit-tree", f"{self.s1}^{{tree}}", "-m", "hiding")
        for how in ("info/grafts", "replace --graft"):
            with self.subTest(how=how):
                if how == "info/grafts":
                    grafts = self.path / ".git" / "info" / "grafts"
                    grafts.parent.mkdir(exist_ok=True)
                    grafts.write_text(f"{self.s2} {hiding}\n{self.m} {hiding}\n",
                                      encoding="utf-8")
                else:
                    (self.path / ".git" / "info" / "grafts").unlink()
                    self.git("replace", "--graft", self.s2, hiding)
                    self.git("replace", "--graft", self.m, hiding)
                self.assert_real_diff()

    def test_an_origin_naming_another_repository_runs_nothing(self):
        evil, rewrite = "https://github.com/evil/fork.git", "url.https://github.com/evil/.insteadOf"
        changes = {"remote set-url": ["remote", "set-url", "origin", evil],
                   "remote.origin.url": ["config", "remote.origin.url", evil],
                   "insteadOf": ["config", rewrite, "https://github.com/owner/"]}
        for name, change in changes.items():
            with self.subTest(change=name):
                self.git(*change)
                runner = FakeRunner()
                with self.assertRaisesRegex(evidence.EvidenceError, "github.com/evil/"):
                    self.verify_with(runner)
                self.assertEqual(runner.calls, [])
                self.git("remote", "set-url", "origin", f"https://github.com/{REPO}.git")
                if name == "insteadOf":
                    self.git("config", "--unset", rewrite)
        self.assert_approved_commands_ran()  # and back again

    @unittest.skipIf(os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH"),
                     "GIT_SSH_COMMAND would override the clone's core.sshCommand")
    def test_a_fake_ssh_transport_cannot_fake_the_story_head(self):
        # Review finding B2. The clone's own config points git's ssh at a local repository
        # whose story/27-x is S2; the URL is still GitHub's owner/app, so check_origin
        # passes. GitHub says story/27-x is elsewhere: evidence for S2 must be rejected.
        fake = Path(self.tmp.name) / "fake.git"
        Git(self.tmp.name).run(["init", "-q", "--bare", str(fake)])
        self.git("push", "-q", str(fake), f"{self.s2}:refs/heads/story/27-x")
        script = Path(self.tmp.name) / "fake-ssh.sh"
        script.write_text(f'#!/bin/sh\nexec git upload-pack "{fake.as_posix()}"\n',
                          encoding="utf-8", newline="\n")
        self.git("remote", "set-url", "origin", f"git@github.com:{REPO}.git")
        self.git("config", "core.sshCommand", f'sh "{script.as_posix()}"')
        # The attack is live: git's own answer comes from the fake repository.
        self.assertIn(self.s2, self.git("ls-remote", "--heads", "origin",
                                        "refs/heads/story/27-x"))
        evidence.check_origin(Git(self.path), REPO)  # the URL alone looks right
        real = "5" * 40
        self.github.heads = {"story/27-x": real}
        recorded, _ = self.verify()  # evidence for S2, the fake head
        gh = Gh(transport=self.github)
        head = evidence.remote_head(gh, REPO, "story/27-x")
        self.assertEqual(head, real)
        approved = evidence.approved_config(Git(self.path), gh, REPO)
        problems = evidence.check_trusted(gh, REPO, recorded, approved, issue=27,
                                          branch_head=head)
        self.assertIn(f"the evidence is for commit {self.s2[:7]}, but the head of "
                      "story/27-x is 5555555", " ".join(problems))


# ----------------------------------------------------------------------------- the code


class NoLocalTrustRootTest(unittest.TestCase):
    """No factory code reads the default branch from local refs, and every consumer
    checks evidence through ``evidence.check_trusted`` (B-28)."""

    MODULES = sorted((REPO_ROOT / "scripts" / "factory").glob("*.py"))

    @staticmethod
    def code_strings(tree):
        """Every string in the code, not counting docstrings (which may explain B-28)."""
        docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                      if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
                      and node.body and isinstance(node.body[0], ast.Expr)
                      and isinstance(node.body[0].value, ast.Constant)}
        return [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings]

    def test_no_code_reads_origin_head_or_remote_tracking_refs(self):
        for path in self.MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            strings = " ".join(self.code_strings(tree))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
            with self.subTest(module=path.name):
                for needle in ("origin/HEAD", "refs/remotes", "origin/main"):
                    self.assertNotIn(needle, strings)
                self.assertNotIn("default_ref", names)

    def test_no_evidence_consumer_asks_git_for_a_remote_head(self):
        # B2: `ls-remote` follows the clone's own transport config.
        for name in ("evidence.py", "cli.py", "prbody.py", "acmap.py", "verdict.py",
                     "closeout.py"):
            tree = ast.parse((REPO_ROOT / "scripts" / "factory" / name).read_text(
                encoding="utf-8"))
            with self.subTest(module=name):
                self.assertNotIn("ls-remote", " ".join(self.code_strings(tree)))

    def test_only_the_evidence_module_calls_the_unchecked_check(self):
        for path in self.MODULES:
            if path.name != "evidence.py":
                with self.subTest(module=path.name):
                    self.assertNotIn("evidence.check(", path.read_text(encoding="utf-8"))

    def test_git_ignores_replace_refs_and_grafts(self):
        env = Git("/t")._env()
        self.assertEqual(env["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(Path(env["GIT_GRAFT_FILE"]).parent, Path(os.devnull))
        self.assertFalse(os.path.exists(env["GIT_GRAFT_FILE"]))


if __name__ == "__main__":
    unittest.main()
