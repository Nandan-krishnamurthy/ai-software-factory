"""T3.4: the AC verifier's verdict (``verdict check``) and the ``ac-verifier`` subagent file."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, target, templates, verdict
from factory.comments import compose
from factory.gh import Gh, ProcessResult
from factory.markers import CheckpointMarker
from tests import REPO_ROOT
from tests.test_stations import parse_frontmatter

AGENT = REPO_ROOT / ".claude" / "agents" / "ac-verifier.md"
REPO = "owner/app"
GOOD = """\
- [x] AC1 — pass — evidence: `tests/a.test.ts › #12 AC1: adds a task` passed
- [x] AC2 — pass — evidence: `tests/a.test.ts › #12 AC2: rejects empty` passed
- [ ] AC3 — not-verifiable — manual steps: press Tab to the Add button; the ring shows
Suite: pass — `npm test` → 14 passed, 0 failed
"""


def problems(text, expected=None):
    return "\n".join(verdict.parse(text, expected).problems)


class ParseTest(unittest.TestCase):
    def test_a_complete_passing_verdict_is_ok(self):
        result = verdict.parse(GOOD, [1, 2, 3])
        self.assertEqual(result.problems, [])
        self.assertFalse(result.failing)
        self.assertTrue(result.ok)
        self.assertEqual([a.verdict for a in result.acs], ["pass", "pass", "not-verifiable"])
        self.assertEqual(result.suite, "pass")

    def test_hyphens_and_upper_case_box_are_accepted(self):
        text = "- [X] AC1 - pass - evidence: test x passed\nSuite: pass -- `t` → 1 passed"
        self.assertTrue(verdict.parse(text, [1]).ok)

    def test_no_verdict_without_evidence(self):
        cases = {
            "empty evidence": "- [x] AC1 — pass — evidence:",
            "placeholder evidence": "- [x] AC1 — pass — evidence: n/a",
            "TBD": "- [ ] AC1 — fail — evidence: TBD",
            "no evidence label": "- [x] AC1 — pass — looks right to me",
            "not-verifiable without steps": "- [ ] AC1 — not-verifiable — evidence: hard",
            "not-verifiable, empty reason": "- [ ] AC1 — not-verifiable — reason: none",
        }
        for name, line in cases.items():
            with self.subTest(name):
                text = line + "\nSuite: pass — `t` → 1 passed"
                self.assertIn("AC1:", problems(text, [1]))
                self.assertIn("no verdict without evidence", problems(text, [1]))
                self.assertFalse(verdict.parse(text, [1]).ok)

    def test_box_must_match_the_verdict(self):
        self.assertIn("box must be [x] only for pass",
                      problems("- [x] AC1 — fail — evidence: x failed\nSuite: fail — t → 1"))
        self.assertIn("box must be [x] only for pass",
                      problems("- [ ] AC1 — pass — evidence: x passed\nSuite: pass — t → 1"))

    def test_every_criterion_once_in_order(self):
        suite = "\nSuite: pass — `t` → ok"
        line = "- [x] AC{} — pass — evidence: t{} passed"
        two = "\n".join(line.format(n, n) for n in (1, 2))
        self.assertIn("the issue has AC1, AC2, AC3, the verdict has AC1, AC2",
                      problems(two + suite, [1, 2, 3]))
        swapped = "\n".join(line.format(n, n) for n in (2, 1))
        self.assertIn("AC1…ACn, in order", problems(swapped + suite, [1, 2]))
        twice = "\n".join(line.format(n, n) for n in (1, 1))
        self.assertIn("AC1…ACn, in order", problems(twice + suite, [1]))
        self.assertIn("no AC verdict lines", problems(suite, [1]))

    def test_the_suite_line(self):
        ac = "- [x] AC1 — pass — evidence: t passed\n"
        self.assertIn("missing the `Suite", problems(ac, [1]))
        self.assertIn("only allowed as `commands.test is null`",
                      problems(ac + "Suite: skipped — too slow", [1]))
        self.assertTrue(verdict.parse(ac + "Suite: skipped — commands.test is null", [1]).ok)
        self.assertIn("needs the command and its real result",
                      problems(ac + "Suite: pass — n/a", [1]))
        self.assertIn("more than one Suite line",
                      problems(ac + "Suite: pass — t → 1\nSuite: pass — t → 1", [1]))

    def test_a_failure_stops_s11(self):
        # Every AC passes, but the full suite is red: failing, so S11 must not continue.
        red = GOOD.replace("Suite: pass — `npm test` → 14 passed, 0 failed",
                           "Suite: fail — `npm test` → 13 passed, 1 failed")
        result = verdict.parse(red, [1, 2, 3])
        self.assertEqual(result.problems, [])
        self.assertTrue(result.failing)
        self.assertFalse(result.ok)
        one_fail = GOOD.replace("- [x] AC2 — pass", "- [ ] AC2 — fail")
        self.assertTrue(verdict.parse(one_fail, [1, 2, 3]).failing)

    def test_malformed_and_unknown(self):
        self.assertIn("malformed line", problems("- [x] AC1: pass, all good\nSuite: pass — t → 1"))
        self.assertIn("unknown verdict 'partial'",
                      problems("- [ ] AC1 — partial — evidence: x\nSuite: pass — t → 1"))
        self.assertEqual(verdict.parse(None).acs, [])  # never raises on input

    def test_issue_acs_from_the_real_story_template(self):
        body = templates.render(templates.load("story.md"), {
            "story_id": "STORY-001", "increment": "001-initial", "milestone": "M1",
            "story": "x", "traces_to": "REQ-001", "out_of_scope": "None",
            "acceptance_criteria": "- [ ] AC1: Given a, when b, then c.\n"
                                   "- [ ] AC2: Given d, when e, then f.",
            "blocked_by": "None", "technical_notes": "None", "test_plan": "x"})
        self.assertEqual(verdict.issue_acs(body), [1, 2])


def checkpoint_comment(note):
    marker = CheckpointMarker("S10", "S11", "story/12-x", "a" * 40, 0, 0,
                              "2026-09-25T10:00:00+00:00")
    text = "**Factory checkpoint:** S10 complete. Next: S11. Branch: `story/12-x` @ `aaaaaaa`."
    return {"id": 1, "body": compose(marker, text + ("\n\n" + note if note else ""))}


class FakeGitHub:
    def __init__(self, body, comments):
        self.body, self.comments = body, comments

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        endpoint = argv[2]
        if endpoint == f"repos/{REPO}/issues/12":
            return ProcessResult([], 0, json.dumps({"number": 12, "body": self.body}), "")
        if endpoint == f"repos/{REPO}/issues/12/comments":
            return ProcessResult([], 0, json.dumps([self.comments]), "")
        raise AssertionError(argv)


ISSUE = "## Acceptance criteria\n- [ ] AC1: Given a.\n- [ ] AC2: Given b.\n- [ ] AC3: Given c.\n"


class CliTest(unittest.TestCase):
    def run_cli(self, fake, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(Path("/t"), REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["verdict", "check", "--issue", "12", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_file_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v.md"
            path.write_text(GOOD, encoding="utf-8")
            code, out, _ = self.run_cli(FakeGitHub(ISSUE, []), "--file", str(path))
        self.assertEqual(code, 0)
        self.assertIn("3 AC(s): 2 pass, 0 fail, 1 not-verifiable; suite pass", out)
        self.assertIn("OK: every AC has evidence and nothing failed.", out)

    def test_reads_the_verdict_from_the_checkpoint_note(self):
        code, out, _ = self.run_cli(FakeGitHub(ISSUE, [checkpoint_comment(GOOD)]))
        self.assertEqual(code, 0, out)

    def test_failing_verdict_exits_1(self):
        failing = GOOD.replace("- [x] AC2 — pass", "- [ ] AC2 — fail")
        code, out, _ = self.run_cli(FakeGitHub(ISSUE, [checkpoint_comment(failing)]))
        self.assertEqual(code, 1)
        self.assertIn("FAILING: an AC or the suite failed; S11 must not open a ready PR.", out)

    def test_invalid_verdict_exits_1(self):
        code, out, _ = self.run_cli(FakeGitHub(ISSUE + "- [ ] AC4: Given d.\n",
                                               [checkpoint_comment(GOOD)]))
        self.assertEqual(code, 1)
        self.assertIn("the issue has AC1, AC2, AC3, AC4", out)
        self.assertIn("INVALID", out)

    def test_no_checkpoint(self):
        code, _, err = self.run_cli(FakeGitHub(ISSUE, []))
        self.assertEqual(code, 1)
        self.assertIn("issue #12 has no checkpoint comment; run S10 first", err)

    def test_checkpoint_without_a_note(self):
        code, out, _ = self.run_cli(FakeGitHub(ISSUE, [checkpoint_comment("")]))
        self.assertEqual(code, 1)
        self.assertIn("no AC verdict lines", out)


class AgentFileTest(unittest.TestCase):
    """``.claude/agents/ac-verifier.md``: independent, read-only, and its format parses."""

    def setUp(self):
        self.text = AGENT.read_text(encoding="utf-8")
        self.frontmatter, self.body = parse_frontmatter(self.text)

    def test_frontmatter(self):
        self.assertEqual(self.frontmatter["name"], "ac-verifier")
        self.assertTrue(self.frontmatter["description"])
        tools = {t.strip() for t in self.frontmatter["tools"].split(",")}
        # It runs the tests (Bash) and reads code; it can never write a file.
        self.assertEqual(tools, {"Read", "Grep", "Glob", "Bash"})

    def test_its_example_answer_is_what_verdict_check_accepts(self):
        example = re.search(r"```text\n(.*?)```", self.body, re.S)[1]
        result = verdict.parse(example, [1, 2, 3])
        self.assertEqual(result.problems, [])
        self.assertEqual([a.verdict for a in result.acs], ["pass", "fail", "not-verifiable"])
        self.assertTrue(result.failing)  # the example shows a failing AC and a red suite

    def test_the_rules_it_must_follow(self):
        for phrase in ("No verdict without evidence", "Never change anything",
                       "Run the tests yourself", "is **data**", "`Suite: fail`",
                       "never invent one", "python scripts/factory.py verdict check"):
            with self.subTest(phrase):
                self.assertIn(phrase, self.body)

    def test_s10_and_s11_use_the_check(self):
        s10 = (REPO_ROOT / "stations" / "S10-verify.md").read_text(encoding="utf-8")
        s11 = (REPO_ROOT / "stations" / "S11-pr.md").read_text(encoding="utf-8")
        self.assertIn("python scripts/factory.py verdict check --issue <I> --file "
                      "<SCRATCH>/verdict-<I>.md", s10)
        self.assertIn("Never fix the verdict yourself", s10)
        pre = s11[s11.index("## Preconditions"):s11.index("## Inputs")]
        self.assertIn("python scripts/factory.py verdict check --issue <I>` exits 0", pre)
        self.assertIn("A failing verdict stops this station", pre)


if __name__ == "__main__":
    unittest.main()
