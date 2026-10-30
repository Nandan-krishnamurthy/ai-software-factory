"""B-26: structured test reports named in the approved config's ``test_reports``.

Some runners print no passing test by name (Vitest's ``default`` and ``minimal``
reporters), so a unit-test-only acceptance criterion had no passing mapped test and its
``pass`` was refused. ``verify run`` now captures the reports the **approved** config
lists, and only fresh, readable ones count. Everything here uses the real Task Tracker
fixtures of story #27 (T6.2): its test output, whose Vitest part shows only totals, and
the Vitest JSON report of the same run.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import acmap, closeout, evidence, verdict
from factory.gh import Gh, ProcessResult
from factory.git import Git
from tests import test_acmap
from tests.test_acmap import (
    FIXTURES,
    DiffingGitRepo,
    IssueGitHub,
    fixture,
    issue_body,
    statuses,
)
from tests.test_comments import REPO, checkpoint
from tests.test_evidence import (
    COMMANDS,
    MAIN,
    SHA,
    ApprovedOnGitHub,
    Clock,
    FakeGitRepo,
    FakeRunner,
    config_json,
)

UNIT = "test-results/unit.json"
REPORT = (FIXTURES / "27-unit.vitest.json").read_bytes()


def config_with(commands, reports=None) -> str:
    data = json.loads(config_json(commands))
    if reports is not None:
        data["test_reports"] = list(reports)
    return json.dumps(data)


class ReportsRepo(FakeGitRepo):
    """``FakeGitRepo`` whose approved config (at ``MAIN``) lists ``reports``."""

    def __init__(self, reports=(UNIT,), **kwargs):
        super().__init__(**kwargs)
        self.reports = list(reports)

    def __call__(self, argv, **kwargs):
        if argv[3:] == ["show", f"{MAIN}:.factory/config.json"] and self.approved:
            return self._out(config_with(self.approved, self.reports))
        return super().__call__(argv, **kwargs)


def writes(files: dict[str, bytes], code: int = 0, output: str = "ok\n"):
    """A runner whose test command writes ``files`` into the target and exits ``code``."""
    def runner(command, *, cwd, timeout):
        if command == "npm test":
            for rel, data in files.items():
                (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
                (cwd / rel).write_bytes(data)
            return ProcessResult([], code, output, "")
        return ProcessResult([], 0, "ok\n", "")
    return runner


def without_e2e(diff: str) -> str:
    """#27's diff without its end-to-end test file: every AC is covered by unit tests only."""
    parts = re.split(r"(?=^diff --git )", diff, flags=re.M)
    return "".join(p for p in parts if "tests/e2e/" not in p.split("\n", 1)[0])


def failing(report: bytes, issue: int, ac: int) -> bytes:
    """The report with every unit test named ``#issue ACac`` marked failed."""
    data = json.loads(report)
    for suite in data["testResults"]:
        for case in suite["assertionResults"]:
            if f"#{issue} AC{ac}:" in case["fullName"]:
                case["status"] = "failed"
    return json.dumps(data).encode("utf-8")


class Target:
    """A target working tree (the story branch) with its own config."""

    def __init__(self, test, branch_reports=None, approved=COMMANDS, approved_reports=(UNIT,),
                 commands=COMMANDS):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        (self.path / ".factory").mkdir()
        (self.path / ".factory" / "config.json").write_text(
            config_with(commands, branch_reports), encoding="utf-8")
        self.repo = ReportsRepo(approved_reports, approved=approved)

    def run(self, runner, **kwargs) -> evidence.Evidence:
        return evidence.run_verification(
            self.path, issue=27, repo=REPO, git=Git(self.path, transport=self.repo),
            gh=Gh(transport=ApprovedOnGitHub(self.repo)), runner=runner, clock=Clock(),
            **kwargs)


def by_path(recorded):
    return {r["path"]: r for r in recorded.reports}


def link_folder(link: Path, to: Path) -> bool:
    """Make ``link`` a folder link to ``to``: a symlink, or on Windows without symlink
    rights a directory junction, which needs none. False if neither is possible."""
    try:
        link.symlink_to(to, target_is_directory=True)
        return True
    except OSError:
        pass
    try:
        import _winapi
        _winapi.CreateJunction(str(to), str(link))
        return True
    except (ImportError, OSError):
        return False


# ----------------------------------------------------------------------------- capture


class CaptureTest(unittest.TestCase):
    def test_a_configured_report_is_captured_without_report(self):
        recorded = Target(self).run(writes({UNIT: REPORT}))
        report = by_path(recorded)[UNIT]
        self.assertEqual((report["status"], report["configured"]), ("captured", True))
        self.assertEqual(report["sha256"], evidence.hashlib.sha256(REPORT).hexdigest())
        self.assertEqual(recorded.report_data, {UNIT: REPORT})
        self.assertEqual(evidence.check(recorded, issue=27, branch_head=SHA), [])
        self.assertIn(f"report     {UNIT} captured (from test_reports)",
                      evidence.render(recorded))

    def test_a_report_named_both_ways_is_recorded_once_as_configured(self):
        recorded = Target(self).run(writes({UNIT: REPORT}), reports=[UNIT])
        self.assertEqual([(r["path"], r["configured"]) for r in recorded.reports],
                         [(UNIT, True)])

    def test_the_configured_flag_survives_the_note(self):
        recorded = Target(self).run(writes({UNIT: REPORT}))
        back = evidence.from_body(evidence.to_block(recorded))
        self.assertEqual(back.reports, recorded.reports)
        data = recorded.to_dict()
        data["reports"][0]["configured"] = "yes"
        with self.assertRaisesRegex(evidence.EvidenceError, "malformed evidence: reports"):
            evidence.from_dict(data)


class TrustBoundaryTest(unittest.TestCase):
    """Only the approved config names the reports to trust (ADR-0004's boundary)."""

    def test_a_report_listed_only_on_the_branch_is_never_read(self):
        target = Target(self, branch_reports=[UNIT], approved_reports=())
        recorded = target.run(writes({UNIT: REPORT}))
        self.assertEqual((recorded.reports, recorded.report_data), ([], {}))
        self.assertEqual(recorded.unapproved, [])  # a report is no command
        self.assertEqual(evidence.check(recorded, issue=27, branch_head=SHA), [])

    def test_a_branch_cannot_swap_the_approved_report_for_its_own(self):
        forged = failing(REPORT, 27, 1).replace(b'"failed"', b'"passed"')
        target = Target(self, branch_reports=["forged.json"])
        recorded = target.run(writes({UNIT: REPORT, "forged.json": forged}))
        self.assertEqual(list(by_path(recorded)), [UNIT])

    def test_the_approved_commands_still_rule(self):
        changed = {**COMMANDS, "test": "npm test && echo all-green"}
        runner = FakeRunner()
        recorded = Target(self, branch_reports=[UNIT], commands=changed).run(runner)
        self.assertNotIn("echo all-green", " ".join(c[0] for c in runner.calls))
        self.assertEqual(recorded.unapproved, ["commands.test"])
        self.assertTrue(evidence.check(recorded, issue=27, branch_head=SHA))

    def test_a_pending_test_command_runs_nothing_and_needs_no_report(self):
        runner = FakeRunner()
        target = Target(self, approved={**COMMANDS, "test": None})
        recorded = target.run(runner)
        self.assertNotIn("npm test", [c[0] for c in runner.calls])
        self.assertEqual(recorded.pending, {"test": "npm test"})
        self.assertEqual(by_path(recorded)[UNIT]["status"], "missing")
        self.assertEqual(recorded.report_problems(), [])
        self.assertEqual(evidence.check(recorded, issue=27, branch_head=SHA), [])

    def test_a_configured_path_that_resolves_outside_the_target_runs_nothing(self):
        target = Target(self)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        if not link_folder(target.path / "test-results", Path(outside.name)):
            self.skipTest("neither symlinks nor junctions are available here")
        runner = FakeRunner()
        with self.assertRaisesRegex(evidence.EvidenceError,
                                    "test_reports entry .* not a file inside the target"):
            target.run(runner)
        self.assertEqual(runner.calls, [])

    def test_a_link_the_run_makes_is_not_followed_out_of_the_target(self):
        # The test command is branch code: it may replace the report's folder with a link
        # after the paths were checked. Nothing outside the target is read.
        target = Target(self)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "unit.json").write_bytes(REPORT)
        linked = []

        def redirects(command, *, cwd, timeout):
            if command == "npm test":
                linked.append(link_folder(cwd / "test-results", Path(outside.name)))
            return ProcessResult([], 0, "ok\n", "")

        recorded = target.run(redirects)
        if not linked[0]:
            self.skipTest("neither symlinks nor junctions are available here")
        self.assertEqual(by_path(recorded)[UNIT]["status"], "redirected")
        self.assertEqual(recorded.report_data, {})
        self.assertIn(f"{UNIT} was not captured: redirected",
                      " ".join(evidence.check(recorded, issue=27, branch_head=SHA)))


class FailClosedTest(unittest.TestCase):
    """A passing test command without its fresh, readable report is not accepted."""

    def check_not_accepted(self, recorded, status):
        self.assertEqual(by_path(recorded)[UNIT]["status"], status)
        self.assertNotIn(UNIT, recorded.report_data)
        problems = evidence.check(recorded, issue=27, branch_head=SHA)
        self.assertEqual(len(problems), 1)
        self.assertIn(f"the configured test report {UNIT} was not captured: {status}",
                      problems[0])
        self.assertIn("NOT ACCEPTED: the approved commands passed, but the configured test "
                      f"report {UNIT} was not captured", evidence.render(recorded))

    def test_missing(self):
        self.check_not_accepted(Target(self).run(writes({})), "missing")

    def test_unchanged_from_before_the_run(self):
        target = Target(self)
        (target.path / "test-results").mkdir()
        (target.path / UNIT).write_bytes(REPORT)  # left by an earlier run
        self.check_not_accepted(target.run(writes({UNIT: REPORT})), "unchanged")

    def test_malformed(self):
        for name, data in (("not JSON", b"Tests 117 passed"),
                           ("unknown JSON", b'{"results": []}'),
                           ("broken XML", b"<testsuites><testcase")):
            with self.subTest(name):
                recorded = Target(self).run(writes({UNIT: data}))
                self.check_not_accepted(recorded, "unreadable")
                self.assertTrue(by_path(recorded)[UNIT]["detail"])

    def test_too_large(self):
        with mock.patch.object(evidence, "MAX_REPORT_BYTES", len(REPORT) - 1):
            recorded = Target(self).run(writes({UNIT: REPORT}))
        self.check_not_accepted(recorded, "too large")

    def test_a_report_the_run_replaces_with_a_file_link_is_not_read(self):
        # The folder stays; the report itself becomes a link to a passing report elsewhere.
        target = Target(self)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "unit.json").write_bytes(REPORT)
        linked = []

        def links(command, *, cwd, timeout):
            if command == "npm test":
                (cwd / "test-results").mkdir(exist_ok=True)
                try:
                    (cwd / UNIT).symlink_to(Path(outside.name) / "unit.json")
                    linked.append(True)
                except OSError:
                    linked.append(False)
            return ProcessResult([], 0, "ok\n", "")

        recorded = target.run(links)
        if not linked[0]:
            self.skipTest("file symlinks are not available here")
        self.check_not_accepted(recorded, "redirected")

    def test_a_failing_test_command_reports_its_failure_not_the_report(self):
        recorded = Target(self).run(writes({}, code=1, output="1 failed\n"))
        self.assertEqual(recorded.report_problems(), [])
        self.assertEqual(evidence.check(recorded, issue=27, branch_head=SHA),
                         ["commands.test failed (exit 1)"])

    def test_close_out_asks_again_when_the_run_on_main_has_no_report(self):
        target = Target(self)
        target.repo.branch = "main"
        recorded = target.run(writes({}))
        self.assertIn("the last run on main failed: the configured test report "
                      f"{UNIT} was not captured: missing",
                      closeout.after_merge(recorded, "story/27-x"))


# ----------------------------------------------------------------------------- mapping


class UnitOnlyMappingTest(unittest.TestCase):
    """The B-26 regression: every AC of #27 covered by unit tests only."""

    def build(self, reports):
        recorded = Target(self).run(writes({UNIT: REPORT}, output=fixture("27.output.txt")))
        return acmap.build(issue=27, acs=[1, 2, 3, 4, 5], evidence=recorded,
                           base="origin/main@99caa27", diff=without_e2e(fixture("27.diff")),
                           output=fixture("27.output.txt"),
                           output_note="the test command's full output", reports=reports)

    def held(self, mapped):
        parsed = verdict.parse(fixture("27.verdict.md"), [1, 2, 3, 4, 5])
        parsed.problems += verdict.cross_check(
            parsed, mapped, issue=27, evidence_sha=mapped.sha,
            checkpoint_branch=mapped.branch, branch_head=mapped.sha)
        return parsed

    def test_from_the_output_alone_no_unit_test_passed(self):
        mapped = self.build([])
        self.assertEqual(set(statuses(mapped).values()), {"missing"})
        self.assertIn("AC1: the verifier says pass, but none of its mapped tests passed",
                      self.held(mapped).problems[0])

    def test_with_the_report_every_ac_passes(self):
        mapped = self.build([(UNIT, REPORT)])
        self.assertEqual(set(statuses(mapped).values()), {"passed"})
        self.assertTrue(all(t.source == f"report {UNIT}" for a in mapped.acs for t in a.tests))
        self.assertEqual(self.held(mapped).problems, [])

    def test_a_failing_unit_test_in_the_report_fails_its_ac(self):
        mapped = self.build([(UNIT, failing(REPORT, 27, 3))])
        self.assertEqual(mapped.status(3).status, "failed")
        self.assertIn("AC3: the verifier says pass, but its mapped test failed",
                      " ".join(self.held(mapped).problems))

    def test_a_report_failure_wins_over_a_passing_end_to_end_test(self):
        recorded = Target(self).run(writes({UNIT: REPORT}, output=fixture("27.output.txt")))
        mapped = acmap.build(issue=27, acs=[1, 2, 3, 4, 5], evidence=recorded,
                             base="origin/main@99caa27", diff=fixture("27.diff"),
                             output=fixture("27.output.txt"), output_note="output",
                             reports=[(UNIT, failing(REPORT, 27, 3))])
        e2e = [t for t in mapped.status(3).tests if t.file.startswith("tests/e2e/")]
        self.assertTrue(e2e)  # #27 AC3 also has a Playwright test, listed as passed
        self.assertEqual(mapped.status(3).status, "failed")


class EndToEndCliTest(unittest.TestCase):
    """`verify run` → `verify map` → `verdict check` through the CLI, as S09 and S10 run
    them: no station passes --report."""

    # The T6.2 CLI harness, without its tests.
    cli = test_acmap.CliTest.cli
    body = test_acmap.CliTest.body
    store_verdict = test_acmap.CliTest.store_verdict

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "target"
        (self.path / ".factory").mkdir(parents=True)
        (self.path / ".factory" / "config.json").write_text(config_with(COMMANDS, [UNIT]),
                                                            encoding="utf-8")
        self.scratch = Path(self.tmp.name) / "scratch"
        self.scratch.mkdir()
        self.github = IssueGitHub({27: issue_body(5)})
        self.repo = ReportsDiffRepo(without_e2e(fixture("27.diff")),
                                    remote={"refs/heads/story/27-x": SHA})
        checkpoint(Gh(transport=self.github), number=27, branch="story/27-x", sha=SHA)

    def runner(self, report):
        return writes({UNIT: report}, output=fixture("27.output.txt"))

    def test_a_unit_only_story_verifies(self):
        code, out, err = self.cli("verify", "run", "--issue", "27", runner=self.runner(REPORT))
        self.assertEqual(code, 0, out + err)
        code, out, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"report {UNIT} (jest-style JSON, 117 cases)", out)
        self.store_verdict(fixture("27.verdict.md"))
        code, out, _ = self.cli("verdict", "check", "--issue", "27")
        self.assertEqual(code, 0, out)
        self.assertIn("OK: every AC has evidence and nothing failed.", out)

    def test_a_missing_report_stops_verify_run_and_verify_check(self):
        code, out, _ = self.cli("verify", "run", "--issue", "27", runner=writes({}))
        self.assertEqual(code, 1)
        self.assertIn("NOT ACCEPTED", out)
        code, out, _ = self.cli("verify", "check", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn(f"the configured test report {UNIT} was not captured: missing", out)

    def test_a_forged_report_copy_is_refused_by_verify_map(self):
        self.cli("verify", "run", "--issue", "27", runner=self.runner(REPORT))
        copy = evidence.report_copy_path(self.scratch / "evidence-27.json", 1, UNIT)
        copy.write_bytes(failing(REPORT, 27, 1).replace(b'"failed"', b'"passed"') + b" ")
        code, _, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("SHA-256 differs", err)


class ReportsDiffRepo(DiffingGitRepo):
    """``DiffingGitRepo`` whose approved config lists the unit report."""

    def __call__(self, argv, **kwargs):
        if argv[3:] == ["show", f"{MAIN}:.factory/config.json"] and self.approved:
            return self._out(config_with(self.approved, [UNIT]))
        return super().__call__(argv, **kwargs)


class OtherReportsStillWorkTest(unittest.TestCase):
    """Playwright JSON and JUnit reports, configured, still map #28 as before."""

    def test_configured_playwright_and_junit_reports(self):
        for name in ("28-e2e.playwright.json", "28-e2e.junit.xml"):
            with self.subTest(report=name):
                rel = f"test-results/{name}"
                data = (FIXTURES / name).read_bytes()
                target = Target(self, approved_reports=(rel,))
                recorded = target.run(writes({rel: data}, output=""))
                self.assertEqual(by_path(recorded)[rel]["status"], "captured")
                mapped = acmap.build(issue=28, acs=[1, 2, 3, 4], evidence=recorded,
                                     base="origin/main@86916d4", diff=fixture("28.diff"),
                                     output=None, output_note="no output",
                                     reports=[(rel, data)])
                self.assertEqual(set(statuses(mapped).values()), {"passed"})


if __name__ == "__main__":
    unittest.main()
