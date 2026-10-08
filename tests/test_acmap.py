"""T6.2: the AC-to-test map (`verify map`) and the verdict cross-check.

The fixtures in ``tests/fixtures/acmap`` come from the real Task Tracker runs of stories
#27 and #28 (PRs #29 and #30): the branch diffs, exactly as ``verify map`` asks git for
them; the ``npm test`` output of each branch head; JUnit, Playwright JSON and Vitest JSON
reports of the same tests; a real run with #27 AC2's end-to-end test broken; and the
AC verifier's verdicts as the PRs quote them. The doctored cases change only what each
test names: a test removed, a test failing, a test that did not run, a forged "pass".
"""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import acmap, cli, comments, evidence, target, verdict
from factory.gh import Gh, ProcessResult
from factory.git import Git
from tests import REPO_ROOT
from tests.test_comments import REPO, FakeGitHub, checkpoint
from tests.test_evidence import (
    COMMANDS,
    SHA,
    FakeGitRepo,
    FakeRunner,
    config_json,
    run,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "acmap"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def issue_body(count: int) -> str:
    return "## Acceptance criteria\n" + "".join(
        f"- [ ] AC{n}: Given a, when b, then c.\n" for n in range(1, count + 1))


def build(issue=27, diff=None, output=None, reports=(), count=None):
    """The map of the real run of ``issue``, with any part swapped for a doctored one."""
    recorded, _ = run()
    count = count or {27: 5, 28: 4}[issue]
    output = fixture(f"{issue}.output.txt") if output is None else output
    return acmap.build(
        issue=issue, acs=list(range(1, count + 1)), evidence=recorded,
        base="origin/main@99caa27", diff=fixture(f"{issue}.diff") if diff is None else diff,
        output=output or None, output_note="the test command's full output",
        reports=list(reports))


def statuses(result):
    return {a.ac: a.status for a in result.acs}


def check(verdict_text, result, issue=27):
    parsed = verdict.parse(verdict_text, [a.ac for a in result.acs])
    parsed.problems += verdict.cross_check(parsed, result, issue=issue)
    return parsed


def without(issue: int, ac: int, text: str) -> str:
    """``text`` with the tag of ``#issue ACac`` taken out of every test name."""
    return text.replace(f"#{issue} AC{ac}: ", "")


# ----------------------------------------------------------------------------- real runs


class RealRunsTest(unittest.TestCase):
    """#27 and #28 as they really ran: every AC maps to a passing test."""

    def test_27_from_the_output_every_ac_passed(self):
        result = build(27)
        self.assertEqual(statuses(result), {n: "passed" for n in range(1, 6)})
        ac1 = result.status(1)
        self.assertEqual(len(ac1.tests), 5)  # 4 unit tests and 1 end-to-end test
        e2e = [t for t in ac1.tests if t.file == "tests/e2e/overdue.spec.ts"]
        self.assertEqual([(t.line, t.status, t.source) for t in e2e], [(29, "passed", "output")])
        self.assertEqual(e2e[0].name, '#27 AC1: an active task due before today is marked '
                                      '"Overdue"')
        # Vitest's default reporter lists no passing test by name: no result, never a pass.
        unit = [t for t in ac1.tests if t.file.startswith("src/")]
        self.assertEqual({t.status for t in unit}, {"no-result"})
        self.assertEqual(result.failed(), [])

    def test_27_the_docs_and_the_log_are_not_tests(self):
        files = {t.file for a in build(27).acs for t in a.tests}
        self.assertEqual(files, {"src/app/controller.test.ts", "src/domain/task.test.ts",
                                 "src/ui/render.test.ts", "tests/e2e/overdue.spec.ts"})
        self.assertIn("docs/factory/traceability.md", fixture("27.diff"))

    def test_27_with_its_json_report_the_unit_tests_pass_too(self):
        report = (FIXTURES / "27-unit.vitest.json").read_bytes()
        result = build(27, reports=[("reports/unit.json", report)])
        tests = [t for a in result.acs for t in a.tests]
        self.assertEqual({t.status for t in tests}, {"passed"})
        unit = next(t for t in tests if t.file == "src/domain/task.test.ts")
        self.assertEqual(unit.source, "report reports/unit.json")
        self.assertIn("report reports/unit.json (jest-style JSON, 117 cases)", result.sources)

    def test_28_from_the_output_every_ac_passed(self):
        result = build(28)
        self.assertEqual(statuses(result), {1: "passed", 2: "passed", 3: "passed",
                                            4: "passed"})
        self.assertEqual([t.line for a in result.acs for t in a.tests], [186, 214, 220, 228])

    def test_28_from_reports_alone(self):
        for name, kind in (("28-e2e.junit.xml", "JUnit XML"),
                           ("28-e2e.playwright.json", "Playwright JSON")):
            with self.subTest(report=name):
                result = build(28, output="",
                               reports=[(name, (FIXTURES / name).read_bytes())])
                self.assertEqual(set(statuses(result).values()), {"passed"})
                self.assertIn(f"report {name} ({kind}, 11 cases)", result.sources)

    def test_the_real_verdicts_agree_with_the_map(self):
        for issue in (27, 28):
            with self.subTest(issue=issue):
                parsed = check(fixture(f"{issue}.verdict.md"), build(issue), issue)
                self.assertEqual(parsed.problems, [])
                self.assertTrue(parsed.ok)


# ----------------------------------------------------------------------------- doctored


class DoctoredRunsTest(unittest.TestCase):
    def test_missing_test(self):
        """#27 with no test named for AC3: the verifier's pass is refused."""
        result = build(27, diff=without(27, 3, fixture("27.diff")),
                       output=without(27, 3, fixture("27.output.txt")))
        self.assertEqual(result.status(3).status, "missing")
        self.assertEqual(result.status(3).tests, [])
        parsed = check(fixture("27.verdict.md"), result)
        self.assertIn("AC3: the verifier says pass, but no test is named `#27 AC3` in the "
                      "branch diff", parsed.problems)
        self.assertEqual(len(parsed.problems), 1)
        self.assertIn("INVALID", verdict.render(parsed, result))

    def test_missing_test_needs_not_verifiable_with_manual_steps(self):
        result = build(27, diff=without(27, 3, fixture("27.diff")))
        lines = fixture("27.verdict.md").splitlines()
        cases = {
            "manual steps": ("- [ ] AC3 — not-verifiable — manual steps: complete an overdue "
                             "task, open Completed, reopen it", []),
            "a reason only": ("- [ ] AC3 — not-verifiable — reason: hard to automate",
                              ["not-verifiable needs written `manual steps: …`"]),
            "fail": ("- [ ] AC3 — fail — evidence: no test exists",
                     ["so the verdict must be not-verifiable"]),
        }
        for name, (line, wanted) in cases.items():
            with self.subTest(name):
                text = "\n".join(line if i == 2 else x for i, x in enumerate(lines))
                parsed = check(text, result)
                if not wanted:
                    self.assertEqual(parsed.problems, [])
                    self.assertTrue(parsed.ok)  # S10 may go on; the PR states the steps
                for phrase in wanted:
                    self.assertTrue(any(phrase in p for p in parsed.problems), parsed.problems)

    def test_failing_test(self):
        """The real run with #27 AC2's end-to-end test broken: AC2 is failed."""
        result = build(27, output=fixture("27-e2e-failed.output.txt"))
        self.assertEqual(statuses(result), {1: "passed", 2: "failed", 3: "passed",
                                            4: "passed", 5: "passed"})
        failed = [t for t in result.status(2).tests if t.status == "failed"]
        self.assertEqual([(t.file, t.line) for t in failed], [("tests/e2e/overdue.spec.ts", 34)])
        self.assertEqual(result.failed(), [2])
        self.assertIn("FAILING: a mapped test failed for AC2.", acmap.render(result))

    def test_false_pass_while_the_mapped_test_failed_is_invalid(self):
        """The forged verdict: the real #27 lines, all pass, over the failing run."""
        result = build(27, output=fixture("27-e2e-failed.output.txt"))
        parsed = check(fixture("27.verdict.md"), result)
        self.assertEqual(len(parsed.problems), 1)
        self.assertTrue(parsed.problems[0].startswith(
            "AC2: the verifier says pass, but its mapped test failed: `#27 AC2: tasks due "
            "today, tomorrow or never are not marked`"))
        self.assertFalse(parsed.ok)
        self.assertIn("INVALID", verdict.render(parsed, result))

    def test_a_failing_test_cannot_hide_behind_not_verifiable(self):
        result = build(27, output=fixture("27-e2e-failed.output.txt"))
        text = fixture("27.verdict.md").replace(
            fixture("27.verdict.md").splitlines()[1],
            "- [ ] AC2 — not-verifiable — manual steps: look at the list")
        parsed = check(text, result)
        self.assertTrue(any("so the verdict must be fail" in p for p in parsed.problems))

    def test_an_honest_fail_is_valid_but_failing(self):
        result = build(27, output=fixture("27-e2e-failed.output.txt"))
        text = fixture("27.verdict.md").replace(
            fixture("27.verdict.md").splitlines()[1],
            "- [ ] AC2 — fail — evidence: `#27 AC2` failed: expected 1, received 0")
        parsed = check(text, result)
        self.assertEqual(parsed.problems, [])
        self.assertTrue(parsed.failing)

    def test_false_pass_for_a_test_that_did_not_run(self):
        """#28 AC4's test is in the diff but not in the run: its pass is refused."""
        output = "\n".join(line for line in fixture("28.output.txt").splitlines()
                           if "#28 AC4" not in line)
        result = build(28, output=output)
        self.assertEqual(result.status(4).status, "missing")
        self.assertEqual([t.status for t in result.status(4).tests], ["no-result"])
        parsed = check(fixture("28.verdict.md"), result, 28)
        self.assertEqual(len(parsed.problems), 1)
        self.assertIn("AC4: the verifier says pass, but none of its mapped tests passed",
                      parsed.problems[0])

    def test_false_pass_for_a_skipped_test(self):
        output = re.sub(r"  ok 11 (\[chromium\].*#28 AC4)", r"  -  11 \1",
                        fixture("28.output.txt"))
        result = build(28, output=output)
        self.assertEqual([t.status for t in result.status(4).tests], ["skipped"])
        self.assertFalse(check(fixture("28.verdict.md"), result, 28).ok)

    def test_a_failure_in_a_report_wins_over_a_pass_in_the_output(self):
        junit = (FIXTURES / "28-e2e.junit.xml").read_text(encoding="utf-8")
        head = re.search(r'<testcase name="overdue label › #28 AC1[^>]*>', junit)[0]
        doctored = junit.replace(head, head + '<failure message="contrast 3.1"/>', 1)
        result = build(28, reports=[("r.xml", doctored.encode("utf-8"))])
        self.assertEqual(result.status(1).status, "failed")
        self.assertEqual(result.status(1).tests[0].source, "report r.xml")

    def test_the_real_vitest_failure_output_fails_the_unit_test(self):
        result = build(27, output=fixture("27-unit-failed.output.txt"))
        unit = next(t for t in result.status(3).tests if t.file == "src/domain/task.test.ts")
        self.assertEqual(unit.status, "failed")
        self.assertEqual(result.status(3).status, "failed")


# ----------------------------------------------------------------------------- parts


class DiffTest(unittest.TestCase):
    DIFF = """\
diff --git a/tests/a.test.js b/tests/a.test.js
--- a/tests/a.test.js
+++ b/tests/a.test.js
@@ -3,0 +4,3 @@ x
+++ not a header: it('#9 AC1: plus', () => {});
+it('#9 AC2: escaped \\'quote\\' here', () => {});
+// #9 AC3 is covered by hand
@@ -10,2 +12,0 @@
-it('#9 AC4: removed', () => {});
-
diff --git a/docs/notes.md b/docs/notes.md
--- a/docs/notes.md
+++ b/docs/notes.md
@@ -1 +1 @@
-old
+`#9 AC1: plus` is listed here
diff --git a/tests/gone.test.js b/tests/gone.test.js
--- a/tests/gone.test.js
+++ /dev/null
@@ -1 +0,0 @@
-it('#9 AC5: gone', () => {});
"""

    def test_added_lines_follow_the_hunks(self):
        self.assertEqual(acmap.added_lines(self.DIFF), [
            ("tests/a.test.js", 4, "++ not a header: it('#9 AC1: plus', () => {});"),
            ("tests/a.test.js", 5, "it('#9 AC2: escaped \\'quote\\' here', () => {});"),
            ("tests/a.test.js", 6, "// #9 AC3 is covered by hand"),
            ("docs/notes.md", 1, "`#9 AC1: plus` is listed here"),
        ])

    def test_find_tests(self):
        found = acmap.find_tests(self.DIFF, 9)
        self.assertEqual([(t.line, t.name, t.acs) for t in found], [
            (4, "#9 AC1: plus", (1,)),
            (5, "#9 AC2: escaped 'quote' here", (2,)),
            (6, None, (3,)),
        ])

    def test_tags(self):
        def names(line, issue=2):
            diff = f"+++ b/tests/x_test.py\n@@ -0,0 +1 @@\n+{line}\n"
            return [(t.name, t.acs) for t in acmap.find_tests(diff, issue)]

        self.assertEqual(names("test('#2 AC3 AC4: heading', f)"),
                         [("#2 AC3 AC4: heading", (3, 4))])
        self.assertEqual(names("test('#2 AC1, AC2: both', f)"), [("#2 AC1, AC2: both", (1, 2))])
        self.assertEqual(names("test('#20 AC1: another story', f)"), [])
        self.assertEqual(names("test('#2 AC10: tenth', f)"), [("#2 AC10: tenth", (10,))])
        self.assertEqual(names("def test_2_ac1_adds_a_line(self):"),
                         [("test_2_ac1_adds_a_line", (1,))])
        self.assertEqual(names("func Test2AC3Rejects(t *testing.T) {"),
                         [("Test2AC3Rejects", (3,))])
        self.assertEqual(names("def test_20_ac1_x(self):"), [])

    def test_template_placeholders_match_what_they_became(self):
        diff = ("+++ b/tests/e2e/p.spec.ts\n@@ -0,0 +1 @@\n"
                "+  test(`#6 AC2: a task added with priority ${p} shows it`, f);\n")
        tests = acmap.find_tests(diff, 6)
        output = ("  ok 27 [chromium] › p.spec.ts:34:3 › #6 AC2: a task added with priority "
                  "Low shows it (669ms)\n")
        self.assertEqual(acmap.output_results(output, tests), {0: ["passed"]})

    def test_test_files(self):
        for path, expected in {
            "src/domain/task.test.ts": True, "tests/e2e/overdue.spec.ts": True,
            "tests/test_invoices.py": True, "pkg/invoice_test.go": True,
            "src/test/java/InvoiceTest.java": True, "spec/models/user_spec.rb": True,
            "Invoices.Tests/InvoiceTests.cs": True, "src/__tests__/a.js": True,
            "src/domain/task.ts": False, "docs/factory/traceability.md": False,
            ".factory/log.md": False, "tests/fixtures/run.json": False,
            "tests/README.md": False, "src/contest.py": False,
        }.items():
            with self.subTest(path):
                self.assertEqual(acmap.is_test_file(path), expected)

    def test_tags_for_acs_the_issue_does_not_have_are_noted(self):
        diff = fixture("27.diff").replace("#27 AC5: the order", "#27 AC7: the order")
        result = build(27, diff=diff)
        self.assertTrue(any("tags AC7, which issue #27 does not have" in n
                            for n in result.notes))


class ResultLineTest(unittest.TestCase):
    """The result marks of each supported runner's output, with the name taken out."""

    CASES = {
        # Playwright `list`, UTF-8 terminal and Windows console
        "  ✓  1 [chromium] › a.spec.ts:3:1 › NAME (1.2s)": "passed",
        "  ✘  2 [chromium] › a.spec.ts:3:1 › NAME (1.2s)": "failed",
        "  ok 1 [chromium] › a.spec.ts:3:1 › NAME (1.2s)": "passed",
        "  x  2 [chromium] › a.spec.ts:3:1 › NAME (5.7s)": "failed",
        "  -  3 [chromium] › a.spec.ts:3:1 › NAME": "skipped",
        "  1) [chromium] › a.spec.ts:3:1 › NAME ───": None,
        "    [chromium] › tests\\e2e\\a.spec.ts:34:1 › NAME ": None,
        # Vitest / Jest
        " ✓ src/a.test.ts > suite > NAME 3ms": "passed",
        "     × NAME 18ms": "failed",
        " FAIL  src/a.test.ts > suite > NAME": "failed",
        "   ↓ NAME [skipped]": "skipped",
        "    ✕ NAME (5 ms)": "failed",
        "    218|   it('NAME', () => {": None,
        # pytest -v
        "tests/test_a.py::NAME PASSED                              [ 50%]": "passed",
        "tests/test_a.py::NAME FAILED                              [100%]": "failed",
        "tests/test_a.py::NAME SKIPPED (no db)                     [100%]": "skipped",
        "FAILED tests/test_a.py::NAME - assert 1 == 2": "failed",
        # unittest -v
        "NAME (tests.test_a.T.NAME) ... ok": "passed",
        "NAME (tests.test_a.T.NAME) ... FAIL": "failed",
        "NAME (tests.test_a.T.NAME) ... ERROR": "failed",
        "NAME (tests.test_a.T.NAME) ... skipped 'later'": "skipped",
        # go test -v
        "=== RUN   NAME": None,
        "--- PASS: NAME (0.00s)": "passed",
        "--- FAIL: NAME (0.00s)": "failed",
        "--- SKIP: NAME (0.00s)": "skipped",
        # cargo test
        "test tests::NAME ... ok": "passed",
        "test tests::NAME ... FAILED": "failed",
        "test tests::NAME ... ignored": "skipped",
    }

    def test_marks(self):
        tests = [acmap.FoundTest("t", 1, "NAME", (1,), acmap.name_pattern("NAME"))]
        for line, expected in self.CASES.items():
            with self.subTest(line):
                got = acmap.output_results(line, tests).get(0)
                self.assertEqual(got, None if expected is None else [expected])

    def test_a_name_in_the_title_does_not_fake_a_mark(self):
        tests = [acmap.FoundTest("t", 1, "#3 AC1: x marks ok PASSED", (1,),
                                 acmap.name_pattern("#3 AC1: x marks ok PASSED"))]
        line = "  1) [chromium] › a.spec.ts:3:1 › #3 AC1: x marks ok PASSED"
        self.assertEqual(acmap.output_results(line, tests), {})

    def test_the_longest_name_owns_the_line(self):
        names = ["#9 AC1: adds", "#9 AC1: adds twice"]
        tests = [acmap.FoundTest("t", i, n, (1,), acmap.name_pattern(n))
                 for i, n in enumerate(names)]
        output = "  ✘  1 [c] › #9 AC1: adds twice (1s)\n  ✓  2 [c] › #9 AC1: adds (1s)\n"
        self.assertEqual(acmap.output_results(output, tests), {1: ["failed"], 0: ["passed"]})

    def test_a_retried_failure_stays_failed(self):
        tests = [acmap.FoundTest("t", 1, "NAME", (1,), acmap.name_pattern("NAME"))]
        output = "  ✘  1 [c] › NAME (1s)\n  ✓  2 [c] › NAME (retry #1) (1s)\n"
        self.assertEqual(acmap._combine(acmap.output_results(output, tests)[0]), "failed")
        self.assertEqual(acmap.ac_status([acmap.MappedTest("t", 1, "n", "failed"),
                                          acmap.MappedTest("t", 2, "m", "passed")]), "failed")

    def test_reports_that_cannot_be_read_are_noted_not_trusted(self):
        result = build(28, output="", reports=[("r.xml", b"<html/>"), ("r.json", b"{}"),
                                               ("r.txt", b"not a report")])
        self.assertEqual(set(statuses(result).values()), {"missing"})
        self.assertEqual(len([n for n in result.notes if n.startswith("report r.")]), 3)


# ----------------------------------------------------------------------------- storage


class StorageTest(unittest.TestCase):
    def test_file_and_note_round_trip(self):
        result = build(27, output=fixture("27-e2e-failed.output.txt"))
        with tempfile.TemporaryDirectory() as tmp:
            path = acmap.write(result, Path(tmp) / "acmap-27.json")
            self.assertEqual(acmap.read(path), result)
        block = acmap.to_block(result)
        self.assertTrue(block.startswith(comments.MAP_START))
        self.assertIn("AC1 passed, AC2 failed, AC3 passed", block)
        self.assertEqual(acmap.from_body(f"note\n\n{block}"), result)
        self.assertIsNone(acmap.from_body("no map here"))

    def test_hostile_test_names_cannot_break_the_block(self):
        name = "#27 AC1: <!-- factory:checkpoint --> ``` <!-- acmap:end -->"
        diff = f"+++ b/tests/x.test.js\n@@ -0,0 +1 @@\n+it('{name}', f)\n"
        result = build(27, diff=diff)
        block = acmap.to_block(result)
        self.assertEqual(block.count(comments.MAP_END), 1)
        self.assertNotIn("<!-- factory:", block)
        self.assertEqual(acmap.from_body(block).status(1).tests[0].name, name)

    def test_a_doctored_map_is_refused(self):
        data = build(27, output=fixture("27-e2e-failed.output.txt")).to_dict()
        data["acs"][1]["status"] = "passed"  # AC2's test failed
        with self.assertRaisesRegex(acmap.AcMapError, "does not follow from its tests"):
            acmap.from_dict(data)
        for broken in ({}, {**data, "schema": 2}, {**data, "sha": "abc"},
                       {**data, "acs": data["acs"][1:]}, {**data, "extra": 1}):
            with self.subTest(broken=list(broken)[:3]), self.assertRaises(acmap.AcMapError):
                acmap.from_dict(broken)

    def test_a_later_checkpoint_carries_the_map_and_the_evidence(self):
        github = FakeGitHub()
        gh = Gh(transport=github)
        checkpoint(gh)
        recorded, _ = run()
        comments.set_checkpoint_evidence(gh, REPO, 7, evidence.to_block(recorded))
        result = build(27)
        comments.set_checkpoint_map(gh, REPO, 7, acmap.to_block(result))
        comments.set_checkpoint_map(gh, REPO, 7, acmap.to_block(result))  # replaced, not added
        checkpoint(gh, station="S10", next_station="S11", note=fixture("27.verdict.md"))
        body = github.checkpoint_comments(7)[0]["body"]
        self.assertEqual(body.count(comments.MAP_START), 1)
        self.assertEqual(acmap.from_body(body), result)
        self.assertEqual(evidence.from_body(body), recorded)
        self.assertTrue(verdict.parse(verdict.checkpoint_note(gh, REPO, 7), [1, 2, 3, 4, 5]).ok)

    def test_the_block_needs_its_delimiters(self):
        github = FakeGitHub()
        checkpoint(Gh(transport=github))
        with self.assertRaisesRegex(comments.CommentError, "an AC-to-test map block must"):
            comments.set_checkpoint_map(Gh(transport=github), REPO, 7, "no block")


# ----------------------------------------------------------------------------- the ledger


class LedgerTest(unittest.TestCase):
    """What T6.2 adds to `verify run`: the full test output and captured reports."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_the_full_test_output_is_kept_and_its_hash_recorded(self):
        output = fixture("27.output.txt")
        recorded, _ = run(runner=FakeRunner({"npm test": (0, output)}))
        test = recorded.command("test")
        self.assertEqual(test.output_lines, len(output.splitlines()))
        self.assertEqual(len(test.tail), evidence.TAIL_LINES)
        self.assertNotIn("outputs", recorded.to_dict())
        path = evidence.write(recorded, self.dir / "evidence-27.json")
        self.assertEqual(evidence.output_path(path).read_bytes(), output.encode("utf-8"))
        text, note = evidence.recorded_output(evidence.read(path), path)
        self.assertEqual(text, output)
        self.assertIn(f"full output ({test.output_lines} lines)", note)

    def test_an_edited_output_file_is_refused(self):
        recorded, _ = run(runner=FakeRunner({"npm test": (0, fixture("27-e2e-failed"
                                                                     ".output.txt"))}))
        path = evidence.write(recorded, self.dir / "evidence-27.json")
        log = evidence.output_path(path)
        log.write_bytes(log.read_bytes().replace(b"  x  50", b"  ok 50"))
        with self.assertRaisesRegex(evidence.EvidenceError, "SHA-256 differs"):
            evidence.recorded_output(recorded, path)

    def test_without_the_file_only_the_recorded_tail_is_used(self):
        recorded, _ = run(runner=FakeRunner({"npm test": (0, fixture("27.output.txt"))}))
        text, note = evidence.recorded_output(recorded, self.dir / "elsewhere.json")
        self.assertEqual(text, "\n".join(recorded.command("test").tail))
        self.assertIn("only the last 50 lines", note)

    def test_older_evidence_still_loads(self):
        recorded, _ = run()
        data = recorded.to_dict()
        del data["reports"]
        for c in data["commands"]:
            del c["output_sha256"], c["output_lines"]
        self.assertEqual(evidence.from_dict(data).reports, [])
        with self.assertRaisesRegex(evidence.EvidenceError, "unexpected outputs"):
            evidence.from_dict({**recorded.to_dict(), "outputs": {"test": "forged"}})

    def test_reports_are_captured_only_if_the_run_wrote_them(self):
        def writes_reports(command, *, cwd, timeout):
            if command == "npm test":
                (cwd / "out").mkdir(exist_ok=True)
                (cwd / "out" / "fresh.xml").write_text("<testsuites/>", encoding="utf-8")
                (cwd / "out" / "same.xml").write_text("<testsuites/>", encoding="utf-8")
            return ProcessResult([], 0, "ok\n", "")

        repo = FakeGitRepo()
        path = Path(tempfile.mkdtemp(dir=self.dir))
        (path / ".factory").mkdir()
        (path / ".factory" / "config.json").write_text(config_json(COMMANDS), encoding="utf-8")
        (path / "out").mkdir()
        (path / "out" / "same.xml").write_text("<testsuites/>", encoding="utf-8")
        (path / "out" / "planted.xml").write_text("<testsuites/>", encoding="utf-8")
        recorded = evidence.run_verification(
            path, issue=27, repo=REPO, git=Git(path, transport=repo), runner=writes_reports,
            reports=["out/fresh.xml", "out/same.xml", "out/planted.xml", "out/none.xml"])
        self.assertEqual([(r["path"], r["status"]) for r in recorded.reports], [
            ("out/fresh.xml", "captured"), ("out/same.xml", "unchanged"),
            ("out/planted.xml", "unchanged"), ("out/none.xml", "missing")])
        written = evidence.write(recorded, self.dir / "evidence-27.json")
        found, notes = evidence.recorded_reports(evidence.read(written), written)
        self.assertEqual(found, [("out/fresh.xml", b"<testsuites/>")])
        self.assertEqual(len(notes), 3)
        copy = evidence.report_copy_path(written, 1, "out/fresh.xml")
        self.assertEqual(copy.name, "evidence-27.report1.xml")
        copy.write_bytes(b"<testsuites><testcase name='forged'/></testsuites>")
        with self.assertRaisesRegex(evidence.EvidenceError, "SHA-256 differs"):
            evidence.recorded_reports(recorded, written)

    def test_report_paths_must_be_inside_the_target(self):
        for bad in ("/etc/x.xml", "../x.xml", "C:/x.xml", ".git/x.xml", "", "."):
            with self.subTest(bad), self.assertRaises(evidence.EvidenceError):
                run(reports=[bad])


# ----------------------------------------------------------------------------- the CLI


class IssueGitHub(FakeGitHub):
    """The comments API, plus the issue bodies (the ACs) ``verify map`` reads."""

    def __init__(self, bodies):
        super().__init__()
        self.bodies = bodies

    def __call__(self, argv, **kwargs):
        result = super().__call__(argv, **kwargs)
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", argv[2]):
            data = json.loads(result.stdout)
            data["body"] = self.bodies.get(int(m[1]), "")
            return ProcessResult([], 0, json.dumps(data), "")
        return result


class DiffingGitRepo(FakeGitRepo):
    """A target whose story branch adds ``diff`` to ``origin/main``."""

    def __init__(self, diff, **kwargs):
        super().__init__(**kwargs)
        self.diff, self.diffs = diff, []

    def __call__(self, argv, **kwargs):
        args = argv[3:]
        if args[:3] == ["-c", "core.quotepath=false", "diff"]:
            self.diffs.append(args[-1])
            return self._out(self.diff)
        return super().__call__(argv, **kwargs)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "target"
        (self.path / ".factory").mkdir(parents=True)
        (self.path / ".factory" / "config.json").write_text(config_json(COMMANDS),
                                                            encoding="utf-8")
        self.scratch = Path(self.tmp.name) / "scratch"
        self.scratch.mkdir()
        self.github = IssueGitHub({27: issue_body(5)})
        self.repo = DiffingGitRepo(fixture("27.diff"), remote={"refs/heads/story/27-x": SHA})
        checkpoint(Gh(transport=self.github), number=27, branch="story/27-x", sha=SHA)

    def cli(self, *argv, output=None):
        runner = FakeRunner({"npm test": (0 if output is None else 1,
                                          output or fixture("27.output.txt"))})
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               return_value=target.Target(self.path, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.github)), \
                mock.patch.object(cli, "Git", lambda p: Git(p, transport=self.repo)), \
                mock.patch.object(evidence, "run_command_line", runner), \
                mock.patch.object(evidence, "guard_vetter", lambda p: lambda c: None), \
                mock.patch.object(evidence, "default_path",
                                  lambda n: self.scratch / f"evidence-{n}.json"), \
                mock.patch.object(acmap, "default_path",
                                  lambda n: self.scratch / f"acmap-{n}.json"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def body(self):
        return self.github.checkpoint_comments(27)[0]["body"]

    def store_verdict(self, text):
        head, _, rest = self.body().partition("\n\n")
        self.github.checkpoint_comments(27)[0]["body"] = f"{head}\n\n{text}\n\n{rest}"

    def test_run_map_then_check_the_real_verdict(self):
        self.assertEqual(self.cli("verify", "run", "--issue", "27")[0], 0)
        code, out, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.repo.diffs, [f"origin/main...{SHA}"])
        self.assertIn("results from: the test command's full output (101 lines)", out)
        self.assertIn("OK: every AC has a mapped test that passed.", out)
        stored = acmap.from_body(self.body())
        self.assertEqual(acmap.read(self.scratch / "acmap-27.json"), stored)
        self.assertEqual(set(statuses(stored).values()), {"passed"})
        self.store_verdict(fixture("27.verdict.md"))
        code, out, _ = self.cli("verdict", "check", "--issue", "27")
        self.assertEqual(code, 0, out)
        self.assertIn("AC-to-test map @ 1111111: AC1 passed", out)
        self.assertIn("OK: every AC has evidence and nothing failed.", out)

    def test_a_failing_test_fails_the_map_and_the_forged_pass_is_invalid(self):
        self.cli("verify", "run", "--issue", "27", output=fixture("27-e2e-failed.output.txt"))
        code, out, _ = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("FAILING: a mapped test failed for AC2.", out)
        verdict_file = self.scratch / "verdict-27.md"
        verdict_file.write_text(fixture("27.verdict.md"), encoding="utf-8")
        code, out, _ = self.cli("verdict", "check", "--issue", "27", "--file", str(verdict_file))
        self.assertEqual(code, 1)
        self.assertIn("AC2: the verifier says pass, but its mapped test failed", out)
        self.assertIn("INVALID", out)

    def test_a_map_file_can_be_given(self):
        self.cli("verify", "run", "--issue", "27")
        self.repo.diff = without(27, 3, fixture("27.diff"))
        self.cli("verify", "map", "--issue", "27", "--out", str(self.scratch / "m.json"))
        verdict_file = self.scratch / "v.md"
        verdict_file.write_text(fixture("27.verdict.md"), encoding="utf-8")
        code, out, _ = self.cli("verdict", "check", "--issue", "27", "--file",
                                str(verdict_file), "--map", str(self.scratch / "m.json"))
        self.assertEqual(code, 1)
        self.assertIn("AC3: the verifier says pass, but no test is named `#27 AC3`", out)

    def test_stale_evidence_is_not_mapped(self):
        self.cli("verify", "run", "--issue", "27")
        self.repo.remote = {"refs/heads/story/27-x": "2" * 40}  # a new commit was pushed
        code, out, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("the evidence cannot be mapped", err)
        self.assertIsNone(acmap.from_body(self.body()))

    def test_a_map_for_other_evidence_is_refused(self):
        self.cli("verify", "run", "--issue", "27")
        self.cli("verify", "map", "--issue", "27")
        other = build(27)
        other.sha = "2" * 40
        self.store_verdict(fixture("27.verdict.md"))
        (self.scratch / "other.json").write_text(json.dumps(other.to_dict()), encoding="utf-8")
        code, out, _ = self.cli("verdict", "check", "--issue", "27", "--map",
                                str(self.scratch / "other.json"))
        self.assertEqual(code, 1)
        self.assertIn("the AC-to-test map is for commit 2222222, but the evidence is for "
                      "1111111", out)

    def test_without_a_map_the_verdict_is_checked_on_its_own(self):
        self.store_verdict(fixture("27.verdict.md"))
        code, out, _ = self.cli("verdict", "check", "--issue", "27")
        self.assertEqual(code, 0, out)
        self.assertIn("AC-to-test map: none stored", out)

    def test_map_needs_evidence(self):
        code, _, err = self.cli("verify", "map", "--issue", "27")
        self.assertEqual(code, 1)
        self.assertIn("checkpoint has no evidence", err)


if __name__ == "__main__":
    unittest.main()
