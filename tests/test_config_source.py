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
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import acmap, cli, comments, evidence, prbody, target
from factory.errors import CommandNotFound, CommandTimeout, GhAuthError
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


class LocalCommitTest(unittest.TestCase):
    """The diffs need GitHub's head in the clone: fetched by its SHA, or nothing."""

    def test_a_commit_the_clone_has_is_not_fetched(self):
        repo = FakeGitRepo()
        self.assertEqual(evidence.local_commit(Git("/t", transport=repo), MAIN), MAIN)
        self.assertEqual(repo.fetches, [])

    def test_a_missing_commit_is_fetched_by_its_sha(self):
        repo = FakeGitRepo(commits=(SHA,), fetchable=(MAIN,))
        self.assertEqual(evidence.local_commit(Git("/t", transport=repo), MAIN), MAIN)
        self.assertEqual(repo.fetches, [MAIN])

    def test_a_commit_that_cannot_be_fetched_fails(self):
        repo = FakeGitRepo(commits=(SHA,))
        with self.assertRaisesRegex(evidence.EvidenceError, "3333333"):
            evidence.local_commit(Git("/t", transport=repo), MAIN)
        self.assertEqual(repo.fetches, [MAIN])


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
