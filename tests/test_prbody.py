"""T6.3: the deterministic PR body (`pr render` / `pr check`).

Everything here is the real Task Tracker evidence of stories #27 and #28 (PRs #29 and
#30). ``tests/fixtures/prbody/<I>.git.json`` holds the answer to every git call
``pr render`` makes, recorded read-only from the real clone with ``origin/main`` pinned
to the base each story branched from; ``<I>.issue.json`` is the real issue;
``<P>.notes.md`` holds the real PR's Summary, Risks and Follow-ups; ``<I>.build.txt`` and
``<I>.typecheck.txt`` are the real command outputs. The test output, the AC-to-test map
inputs and the verifier lines are the T6.2 fixtures of the same runs. The snapshots
``<P>.md`` are what ``pr render`` makes from them.
"""

import contextlib
import dataclasses
import io
import json
import re
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from factory import acmap, cli, evidence, manifests, prbody, target, verdict
from factory.comments import compose
from factory.gh import Gh, ProcessResult
from factory.git import Git
from factory.markers import CheckpointMarker
from tests import REPO_ROOT
from tests.test_evidence import COMMANDS, Clock, FakeGitRepo, FakeRunner, working_tree

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "prbody"
ACMAP = REPO_ROOT / "tests" / "fixtures" / "acmap"
REPO = "Nandan-krishnamurthy/task-tracker-factory-test"
STORIES = {  # issue: (base, head, branch, PR)
    27: ("99caa27", "8b095c2e535d74f70d2894731dba599d9c180769", "story/27-overdue-label", 29),
    28: ("86916d4", "4b17f142098fb2db484430f3abd8e1353b2de562",
         "story/28-overdue-label-style", 30),
}
UPDATE = False  # True rewrites the snapshots; review them before committing


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- the story


class Story:
    """One real story, with every fact `pr render` reads, and knobs to doctor them."""

    def __init__(self, issue: int, test_output: str | None = None, test_exit: int = 0):
        self.issue = issue
        self.base, self.head, self.branch, self.pr = STORIES[issue]
        self.git_answers = json.loads(text(FIXTURES / f"{issue}.git.json"))
        self.remote_head = self.head
        self.generated: set[str] = set()
        self.issue_json = json.loads(text(FIXTURES / f"{issue}.issue.json"))
        self.verdict = text(ACMAP / f"{issue}.verdict.md")
        self.ci_runs: list[dict] = []
        output = test_output if test_output is not None else text(ACMAP / f"{issue}.output.txt")
        self.evidence = self._evidence(output, test_exit)
        self.acmap = acmap.build(
            issue=issue, acs=verdict.issue_acs(self.issue_json["body"]),
            evidence=self.evidence, base=f"origin/main@{self.base}",
            diff=text(ACMAP / f"{issue}.diff"), output=output,
            output_note=f"the test command's full output ({len(output.splitlines())} lines)",
            reports=[])
        self.pr_state, self.pr_head = "open", self.head
        self.pr_body: str | None = None

    def _evidence(self, output: str, test_exit: int) -> evidence.Evidence:
        outputs = {"npm run build": (0, text(FIXTURES / f"{self.issue}.build.txt")),
                   "npm run typecheck": (0, text(FIXTURES / f"{self.issue}.typecheck.txt")),
                   "npm test": (test_exit, output)}
        repo = FakeGitRepo(branch=self.branch, heads=(self.head,))
        path = working_tree(COMMANDS)
        return evidence.run_verification(
            path, issue=self.issue, repo=REPO, git=Git(path, transport=repo),
            runner=FakeRunner(outputs), clock=Clock(),
            now=lambda: datetime(2026, 10, 7, 10, 0, tzinfo=UTC))

    # -- git: the recorded answers, origin/main pinned to the story's base -------------
    def git(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = [a.replace("origin/main", self.base) for a in argv[3:]]
        if args == ["rev-parse", "--abbrev-ref", "origin/HEAD"]:
            return ProcessResult(argv, 0, "origin/main\n", "")
        if args[:2] == ["ls-remote", "--heads"]:
            return ProcessResult(argv, 0, f"{self.remote_head}\trefs/heads/{self.branch}\n", "")
        if args[:1] == ["check-attr"]:
            paths = args[args.index("--") + 1:]
            out = "".join(f"{p}\0linguist-generated\0"
                          f"{'set' if p in self.generated else 'unspecified'}\0" for p in paths)
            return ProcessResult(argv, 0, out, "")
        answer = self.git_answers.get(json.dumps(args))
        if answer is None:
            raise AssertionError(f"no recorded answer for git {args}")
        return ProcessResult(argv, answer["code"], answer["out"], "")

    def answer(self, args: list[str], out: str, code: int = 0):
        self.git_answers[json.dumps(args)] = {"code": code, "out": out}

    def key(self, prefix: list[str]) -> str:
        return next(k for k in self.git_answers if json.loads(k)[:len(prefix)] == prefix)

    def edit(self, prefix: list[str], change):
        """Doctor a recorded git answer: ``change(out) -> out``."""
        key = self.key(prefix)
        self.git_answers[key]["out"] = change(self.git_answers[key]["out"])

    # -- GitHub ------------------------------------------------------------------------
    def checkpoint_body(self) -> str:
        marker = CheckpointMarker("S10", "S11", self.branch, self.head, 0, 0,
                                  "2026-10-07T10:30:00+00:00")
        line = (f"**Factory checkpoint:** S10 complete. Next: S11. Branch: `{self.branch}` "
                f"@ `{self.head[:7]}`.")
        return compose(marker, "\n\n".join([line, self.verdict.strip(),
                                            evidence.to_block(self.evidence),
                                            acmap.to_block(self.acmap)]))

    def github(self, argv, *, timeout, cwd=None, env=None, input=None):
        endpoint = argv[2]
        if endpoint == f"repos/{REPO}/issues/{self.issue}":
            return self._ok(self.issue_json)
        if endpoint == f"repos/{REPO}/issues/{self.issue}/comments":
            return self._ok([[{"id": 1, "body": self.checkpoint_body()}]])
        if endpoint == f"repos/{REPO}/pulls/{self.pr}":
            return self._ok({"number": self.pr, "state": self.pr_state,
                             "head": {"ref": self.branch, "sha": self.pr_head},
                             "body": self.pr_body})
        if endpoint == f"repos/{REPO}/commits/{self.head}/check-runs?per_page=100":
            return self._ok({"check_runs": self.ci_runs})
        raise AssertionError(f"unexpected gh call: {argv}")

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    # -- the engine --------------------------------------------------------------------
    def facts(self) -> prbody.Facts:
        return prbody.collect(Gh(transport=self.github), Git("/t", transport=self.git),
                              REPO, self.issue)

    def notes(self) -> dict[str, str]:
        return prbody.parse_notes(text(FIXTURES / f"{self.pr}.notes.md"))

    def render(self, sections=None) -> prbody.Rendered:
        return prbody.render(self.facts(), sections or self.notes())

    def check(self, body: str) -> prbody.CheckResult:
        self.pr_body = body
        return prbody.check(Gh(transport=self.github), Git("/t", transport=self.git),
                            REPO, self.pr)


def snapshot(pr: int) -> str:
    return text(FIXTURES / f"{pr}.md")


def doctor_log(story: Story, change):
    """Rewrite the recorded commit bodies (``git log``)."""
    story.edit(["log"], change)


def add_file(story: Story, path: str, added: int, deleted: int, *, base_text=None,
             head_text=None, hunk_lines=()):
    """Add a file to the story's diff: its numstat entry, its hunk, and its contents."""
    story.edit(["-c", "core.quotepath=false", "diff", "--numstat"],
               lambda out: out + f"{added}\t{deleted}\t{path}\0")
    lines = "".join(f"+{line}\n" for line in hunk_lines)
    story.edit(["-c", "core.quotepath=false", "diff", "--no-color"],
               lambda out: out + f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
                                 f"@@ -1,0 +1,{len(hunk_lines)} @@\n{lines}")
    base_sha = story.git_answers[story.key(["merge-base"])]["out"].strip()
    if base_text is not None or head_text is not None:
        story.answer(["show", f"{base_sha}:{path}"], base_text or "",
                     0 if base_text is not None else 128)
        story.answer(["show", f"{story.head}:{path}"], head_text or "",
                     0 if head_text is not None else 128)


# ----------------------------------------------------------------------------- snapshots


class SnapshotTest(unittest.TestCase):
    """The real PRs #29 and #30, rendered from their recorded facts."""

    def check_snapshot(self, issue):
        story = Story(issue)
        rendered = story.render()
        if UPDATE:
            (FIXTURES / f"{story.pr}.md").write_bytes(rendered.body.encode("utf-8"))
        self.assertEqual(rendered.body, snapshot(story.pr))
        self.assertEqual((rendered.problems, rendered.warnings), ([], []))
        return rendered

    def test_pr_29_shows_its_two_changed_tests(self):
        body = self.check_snapshot(27).body
        self.assertIn("- Changed existing tests: 2\n"
                      "  - `src/app/controller.test.ts`: #3 AC3: an empty title adds nothing "
                      "and sets the validation message — the exact-state check now also "
                      "expects today", body)
        self.assertIn("  - `src/app/controller.test.ts`: #4 AC4: with nothing stored, the "
                      "controller starts with an empty list and no message — same reason",
                      body)
        self.assertIn("- Full suite: `npm test` → passed (exit 0): vitest: Tests  117 passed "
                      "(117); playwright: 70 passed (26.5s)", body)
        self.assertIn("| Q7 Size | Pass: 240 changed lines in 9 files (limit 400) |", body)

    def test_pr_30(self):
        body = self.check_snapshot(28).body
        self.assertIn("- Changed existing tests: None", body)
        self.assertIn("- Added: 4 tests named `#28 AC<n>` in 1 file: "
                      "`tests/e2e/accessibility.spec.ts` (4)", body)
        self.assertIn("Traceability matrix: REQ-026 updated", body)

    def test_every_gate_is_computed(self):
        gates = {g.label: g for g in Story(27).render().gates}
        self.assertEqual(list(gates), ["Q1 Build", "Q2 Lint & types", "Q3 New tests",
                                       "Q4 Full suite", "Q5 AC evidence", "Q6 Scope",
                                       "Q7 Size", "Q8 CI"])
        self.assertEqual({k: g.status for k, g in gates.items()}, {
            "Q1 Build": "Pass", "Q2 Lint & types": "Pass", "Q3 New tests": "Pass",
            "Q4 Full suite": "Pass", "Q5 AC evidence": "Pass", "Q6 Scope": "Not checked",
            "Q7 Size": "Pass", "Q8 CI": "Not configured"})

    def test_the_verifier_lines_are_copied_unchanged(self):
        body = Story(27).render().body
        lines = [line for line in text(ACMAP / "27.verdict.md").splitlines()
                 if line.startswith("- [")]
        self.assertIn("\n".join(lines), body)

    def test_the_same_facts_render_the_same_body(self):
        self.assertEqual(Story(28).render().body, Story(28).render().body)


# ----------------------------------------------------------------------------- Q6


class ScopeGateTest(unittest.TestCase):
    def test_q6_is_not_checked_and_lists_the_files(self):
        gate = next(g for g in Story(28).render().gates if g.label == "Q6 Scope")
        self.assertEqual(gate.value, "Not checked: the story contract declares no areas. "
                                     "Files touched (4): `.factory/log.md`, "
                                     "`docs/factory/traceability.md`, `index.html`, "
                                     "`tests/e2e/accessibility.spec.ts`")

    def test_q6_is_never_a_problem_and_never_the_models(self):
        rendered = Story(28).render()
        self.assertFalse(any("Q6" in p for p in rendered.problems + rendered.warnings))
        self.assertNotIn("gate_scope", prbody.MODEL_SECTIONS)

    def test_a_falsified_q6_fails_pr_check(self):
        for forged in ("| Q6 Scope | Pass: every file is in scope |",
                       "| Q6 Scope | Not checked: the story contract declares no areas. Files "
                       "touched (1): `index.html` |"):
            with self.subTest(forged):
                body = re.sub(r"^\| Q6 Scope \|.*$", forged, snapshot(30), flags=re.M)
                result = Story(28).check(body)
                self.assertFalse(result.ok)
                self.assertTrue(any(d.startswith("+| Q6 Scope") for d in result.differences))


# ----------------------------------------------------------------------------- pr check


class PrCheckTest(unittest.TestCase):
    def test_the_rendered_body_passes(self):
        for issue in (27, 28):
            with self.subTest(issue=issue):
                story = Story(issue)
                result = story.check(snapshot(story.pr))
                self.assertTrue(result.ok, prbody.report_check(result))

    def test_crlf_and_trailing_spaces_are_not_differences(self):
        body = "\n".join(line + "  " for line in snapshot(30).split("\n")).replace("\n", "\r\n")
        self.assertTrue(Story(28).check(body).ok)

    def test_editing_summary_risks_and_follow_ups_still_passes(self):
        body = snapshot(30)
        body = body.replace("## Summary\n", "## Summary\n- Reworded by the model.\n")
        body = body.replace("## Risks / notes for reviewer\n",
                            "## Risks / notes for reviewer\n- A new risk.\n")
        body = re.sub(r"(## Out of scope / follow-ups\n)(?:- .*\n)+", r"\1None\n", body)
        self.assertNotEqual(body, snapshot(30))
        result = Story(28).check(body)
        self.assertTrue(result.ok, prbody.report_check(result))

    def test_a_test_result_that_disagrees_with_the_ledger_fails(self):
        body = snapshot(30).replace("playwright: 74 passed (25.4s)",
                                    "playwright: 75 passed (25.4s)")
        result = Story(28).check(body)
        self.assertFalse(result.ok)
        self.assertIn("-- Full suite: `npm test` → passed (exit 0): vitest: Tests  117 passed "
                      "(117); playwright: 74 passed (25.4s)", result.differences)
        self.assertIn("FAILED", prbody.report_check(result))

    def test_a_ledger_that_failed_fails_the_old_passing_body(self):
        """The PR says pass; the run the ledger recorded failed (#27 AC2 broken)."""
        story = Story(27, test_output=text(ACMAP / "27-e2e-failed.output.txt"), test_exit=1)
        result = story.check(snapshot(29))
        self.assertFalse(result.ok)
        self.assertIn("+| Q4 Full suite | Pass: `npm test` exited 0: vitest: Tests  117 passed "
                      "(117); playwright: 70 passed (26.5s) |", result.differences)
        self.assertTrue(any(d.startswith("-| Q4 Full suite | Fail: `npm test` exited 1")
                            for d in result.differences))
        self.assertTrue(any("Q4 Full suite: Fail" in p for p in result.problems))
        self.assertTrue(any("Q5 AC evidence: Fail" in p for p in result.problems))

    def test_every_factual_edit_fails(self):
        edits = {
            "a gate": ("| Q1 Build | Pass: `npm run build` exited 0 |",
                       "| Q1 Build | Pass: `npm run build` exited 0 (fast) |"),
            "a verifier line": ("- [x] AC2 — pass", "- [x] AC2 — pass (re-checked)"),
            "the changed tests": ("- Changed existing tests: 2", "- Changed existing tests: 0"),
            "the requirements": ("Requirements: REQ-022", "Requirements: REQ-021"),
            "the dependencies": ("## New dependencies\nNone",
                                 "## New dependencies\n- `left-pad` — needed"),
            "the closing line": ("Closes #27", "Closes #27, #28"),
            "the marker": ("story=STORY-013", "story=STORY-099"),
            "the review instructions": ("The factory never merges.", "Merge when ready."),
            "an extra line": ("## Quality gates\n", "## Quality gates\nAll green.\n"),
        }
        for name, (old, new) in edits.items():
            with self.subTest(name):
                self.assertIn(old, snapshot(29))
                result = Story(27).check(snapshot(29).replace(old, new, 1))
                self.assertFalse(result.ok, name)
                self.assertTrue(result.differences, name)

    def test_model_sections_cannot_smuggle_facts_or_close_issues(self):
        cases = {
            "a heading": ("## Summary\n", "## Summary\n### Quality gates\n"),
            "a closing keyword": ("## Summary\n", "## Summary\nFixes #12\n"),
            "a marker": ("## Risks / notes for reviewer\n",
                         "## Risks / notes for reviewer\n<!-- factory:pr story=STORY-001 -->\n"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                result = Story(28).check(snapshot(30).replace(old, new, 1))
                self.assertFalse(result.ok, name)
                self.assertTrue(any(p.startswith(("Summary:", "Risks:"))
                                    for p in result.problems), result.problems)

    def test_a_missing_section_fails(self):
        result = Story(28).check(snapshot(30).replace("## Risks / notes for reviewer\n", ""))
        self.assertFalse(result.ok)
        self.assertIn("the PR body has no '## Risks / notes for reviewer' section",
                      result.problems)

    def test_the_pr_must_be_the_evidence_commit_and_open(self):
        story = Story(28)
        story.pr_head = "2" * 40
        story.pr_state = "closed"
        result = story.check(snapshot(30))
        self.assertIn("PR #30's head is 2222222, but the evidence is for 4b17f14; run "
                      "`verify run` and `verify map` again", result.problems)
        self.assertIn("PR #30 is closed, not open", result.problems)

    def test_not_a_story_branch(self):
        story = Story(28)
        story.pr_body = snapshot(30)
        real = story.github

        def github(argv, **kwargs):
            result = real(argv, **kwargs)
            if argv[2].endswith("/pulls/30"):
                data = json.loads(result.stdout)
                data["head"]["ref"] = "feature/x"
                return ProcessResult([], 0, json.dumps(data), "")
            return result

        with self.assertRaisesRegex(prbody.PrBodyError, "is not a story branch"):
            prbody.check(Gh(transport=github), Git("/t", transport=story.git), REPO, 30)


# ----------------------------------------------------------------------------- H3


class ChangedTestTest(unittest.TestCase):
    def test_a_changed_test_without_its_line_is_flagged(self):
        story = Story(27)
        doctor_log(story, lambda out: re.sub(r"Changed test: #4 AC4:[^\n]*\n", "", out))
        rendered = story.render()
        self.assertEqual(rendered.problems, [
            "rule H3: `#4 AC4: with nothing stored, the controller starts with an empty list "
            "and no message` in `src/app/controller.test.ts` changed without a "
            "`Changed test:` line"])
        self.assertIn("  - `src/app/controller.test.ts`: `#4 AC4: with nothing stored, the "
                      "controller starts with an empty list and no message` — **not "
                      "declared**: no `Changed test:` line names it (rule H3)", rendered.body)
        self.assertIn("  - `src/app/controller.test.ts`: #3 AC3:", rendered.body)

    def test_both_lines_missing_flags_both_and_pr_check_fails(self):
        story = Story(27)
        doctor_log(story, lambda out: re.sub(r"Changed test:[^\n]*\n", "", out))
        self.assertEqual(len([p for p in story.render().problems if "rule H3" in p]), 2)
        self.assertFalse(story.check(snapshot(29)).ok)

    def test_a_valid_changed_test_line_is_accepted(self):
        changed, unmatched = prbody.changed_tests(Story(27).facts().git)
        self.assertEqual([(c.file, c.name, c.declared is not None) for c in changed], [
            ("src/app/controller.test.ts",
             "#3 AC3: an empty title adds nothing and sets the validation message", True),
            ("src/app/controller.test.ts", "#4 AC4: with nothing stored, the controller "
                                           "starts with an empty list and no message", True)])
        self.assertEqual(unmatched, [])

    def test_a_declared_change_that_did_not_happen_is_a_warning(self):
        story = Story(28)
        doctor_log(story, lambda out: out.replace(
            "Factory-Station: S09", "Changed test: #12 AC1: axe — not really\n\n"
                                    "Factory-Station: S09"))
        rendered = story.render()
        self.assertEqual(rendered.problems, [])
        self.assertEqual(rendered.warnings, ["`Changed test: #12 AC1: axe — not really` names "
                                             "no change found in an existing test"])
        self.assertIn("  - Declared, but no change to it was found: #12 AC1: axe — not really",
                      rendered.body)

    def test_enclosing_test(self):
        js = ["describe('x', () => {", "  beforeEach(() => {", "    setup();", "  });",
              "  it('#3 AC1: adds', () => {", "    const a = 1;", "    for (const b of c) {",
              "      expect(b).toBe(a);", "    }", "  });", "});"]
        self.assertEqual(prbody.enclosing_test(js, 8), "#3 AC1: adds")
        self.assertEqual(prbody.enclosing_test(js, 5), "#3 AC1: adds")  # the declaration
        self.assertIsNone(prbody.enclosing_test(js, 3))  # setup, not a test
        self.assertIsNone(prbody.enclosing_test(js, 1))
        py = ["import x", "", "class T(TestCase):", "    def test_27_ac1_x(self):",
              "        self.assertTrue(x)", "", "    def helper(self):", "        return 1"]
        self.assertEqual(prbody.enclosing_test(py, 5), "test_27_ac1_x")
        self.assertIsNone(prbody.enclosing_test(py, 8))
        go = ["func TestAdd(t *testing.T) {", "\tif add(1, 2) != 3 {", "\t\tt.Fail()", "\t}",
              "}"]
        self.assertEqual(prbody.enclosing_test(go, 3), "TestAdd")
        rust = ["#[test]", "fn adds_two() {", "    assert_eq!(add(1, 1), 2);", "}"]
        self.assertEqual(prbody.enclosing_test(rust, 3), "adds_two")
        java = ["  @Test", "  void addsTwo() {", "    assertEquals(2, add(1, 1));", "  }"]
        self.assertEqual(prbody.enclosing_test(java, 3), "addsTwo")

    def test_a_change_outside_any_test_needs_the_file_named(self):
        story = Story(27)
        story.edit(["-c", "core.quotepath=false", "diff", "--no-color"], lambda out: out.replace(
            "@@ -30 +30,6 @@", "@@ -1 +1 @@\n-import { describe } from 'vitest';\n"
                               "+import { describe, it } from 'vitest';\n@@ -30 +30,6 @@"))
        changed, _ = prbody.changed_tests(story.facts().git)
        self.assertIn(("src/app/controller.test.ts", None, None),
                      [(c.file, c.name, c.declared) for c in changed])
        self.assertIn("rule H3: a line outside any test in `src/app/controller.test.ts` changed "
                      "without a `Changed test:` line", story.render().problems)
        doctor_log(story, lambda out: out.replace(
            "Factory-Station: S08", "Changed test: src/app/controller.test.ts — imports\n\n"
                                    "Factory-Station: S08", 1))
        self.assertFalse(any("rule H3" in p for p in story.render().problems))


# ----------------------------------------------------------------------------- dependencies


PACKAGE = {"name": "app", "dependencies": {"lit": "^3"}, "devDependencies": {"vite": "^8"}}


class DependencyTest(unittest.TestCase):
    def story_with(self, head_deps, *, line=None):
        story = Story(28)
        head = {**PACKAGE, "dependencies": {**PACKAGE["dependencies"], **head_deps}}
        add_file(story, "package.json", len(head_deps), 0, base_text=json.dumps(PACKAGE),
                 head_text=json.dumps(head), hunk_lines=[f'"{n}": "1"' for n in head_deps])
        if line:
            doctor_log(story, lambda out: out.replace(
                "Factory-Station: S08", f"New dependency: {line}\n\nFactory-Station: S08", 1))
        return story

    def test_a_declared_dependency_is_listed_with_its_reason(self):
        rendered = self.story_with({"date-fns": "^4"},
                                   line="date-fns — local dates without time zones").render()
        self.assertEqual(rendered.problems, [])
        self.assertIn("## New dependencies\n- `date-fns` (`package.json`) — local dates "
                      "without time zones\n", rendered.body)

    def test_an_undeclared_dependency_is_flagged(self):
        rendered = self.story_with({"left-pad": "^1"}).render()
        self.assertEqual(rendered.problems, ["rule S9: `left-pad` added to `package.json` "
                                             "without a `New dependency:` line"])
        self.assertIn("- `left-pad` (`package.json`) — **not declared**", rendered.body)

    def test_a_declared_dependency_no_manifest_adds_is_flagged(self):
        story = Story(28)
        doctor_log(story, lambda out: out.replace(
            "Factory-Station: S08", "New dependency: moment — dates\n\nFactory-Station: S08", 1))
        rendered = story.render()
        self.assertEqual(rendered.problems, ["rule S9: `New dependency: moment — dates` names "
                                             "no dependency a manifest adds"])
        self.assertIn("- `moment` — **declared in a commit, but no manifest adds it**",
                      rendered.body)

    def test_a_mismatched_name_is_flagged_both_ways(self):
        problems = self.story_with({"left-pad": "^1"}, line="leftpad — padding").render().problems
        self.assertEqual(problems, [
            "rule S9: `left-pad` added to `package.json` without a `New dependency:` line",
            "rule S9: `New dependency: leftpad — padding` names no dependency a manifest adds"])

    def test_a_dependency_mismatch_fails_pr_check(self):
        story = self.story_with({"left-pad": "^1"})
        result = story.check(story.render().body)
        self.assertFalse(result.ok)
        self.assertEqual(result.differences, [])  # the body tells the truth...
        self.assertIn("rule S9: `left-pad` added to `package.json` without a "
                      "`New dependency:` line", result.problems)  # ...but the fact fails

    def test_a_version_bump_is_not_a_new_dependency(self):
        story = Story(28)
        add_file(story, "package.json", 1, 1, base_text=json.dumps(PACKAGE),
                 head_text=json.dumps({**PACKAGE, "dependencies": {"lit": "^4"}}))
        self.assertEqual(story.render().problems, [])

    def test_manifest_formats(self):
        cases = {
            "requirements-dev.txt": ("requests==2.0\n# c\n-r base.txt\nFlask[async]>=3 ; x\n",
                                     {"requests", "Flask"}),
            "pyproject.toml": ('[project]\ndependencies = ["httpx>=0.27"]\n'
                               '[project.optional-dependencies]\ndev = ["pytest"]\n'
                               '[dependency-groups]\nlint = ["ruff"]\n'
                               '[tool.poetry.dependencies]\npython = "^3.12"\nrich = "*"\n',
                               {"httpx", "pytest", "ruff", "rich"}),
            "go.mod": ("module x\n\nrequire (\n\tgithub.com/a/b v1.0.0\n"
                       "\tgithub.com/c/d v1.0.0 // indirect\n)\nrequire golang.org/x/e v0.1.0\n",
                       {"github.com/a/b", "golang.org/x/e"}),
            "Cargo.toml": ('[dependencies]\nserde = "1"\n[dev-dependencies]\nproptest = "1"\n'
                           '[target.\'cfg(unix)\'.dependencies]\nnix = "0.29"\n',
                           {"serde", "proptest", "nix"}),
            "composer.json": ('{"require": {"php": ">=8"}, "require-dev": {"phpunit/phpunit": '
                              '"^11"}}', {"php", "phpunit/phpunit"}),
            "Gemfile": ("source 'https://rubygems.org'\ngem 'rails', '~> 8'\n", {"rails"}),
            "Pipfile": ('[packages]\nrequests = "*"\n[dev-packages]\nblack = "*"\n',
                        {"requests", "black"}),
        }
        for path, (content, expected) in cases.items():
            with self.subTest(path):
                self.assertTrue(manifests.is_manifest(path))
                self.assertEqual(manifests.dependencies(path, content), expected)
        self.assertFalse(manifests.is_manifest("Makefile"))
        with self.assertRaises(manifests.ManifestError):
            manifests.dependencies("package.json", "{broken")

    def test_an_unreadable_manifest_is_a_problem(self):
        story = Story(28)
        add_file(story, "package.json", 1, 0, base_text=json.dumps(PACKAGE),
                 head_text="{broken")
        self.assertTrue(any("package.json cannot be read" in p
                            for p in story.render().problems))


# ----------------------------------------------------------------------------- Q7


class SizeGateTest(unittest.TestCase):
    def gate(self, story):
        return next(g for g in story.render().gates if g.label == "Q7 Size")

    def test_lockfiles_and_generated_files_are_not_counted(self):
        story = Story(28)
        add_file(story, "package-lock.json", 1500, 300)
        add_file(story, "src/api/client.ts", 900, 0)  # generated, says .gitattributes
        story.generated.add("src/api/client.ts")
        add_file(story, "src/proto/msg.go", 700, 0,
                 hunk_lines=["// Code generated by protoc-gen-go. DO NOT EDIT."])
        add_file(story, "src/gen/schema.ts", 600, 0, hunk_lines=["// @generated by codegen"])
        gate = self.gate(story)
        self.assertEqual(gate.status, "Pass")
        self.assertEqual(gate.text, "91 changed lines in 4 files (limit 400); not counted: "
                                    "`package-lock.json` (lockfile), `src/api/client.ts` "
                                    "(generated), `src/proto/msg.go` (generated), "
                                    "`src/gen/schema.ts` (generated)")

    def test_counted_lines_over_the_limit_are_a_warning(self):
        story = Story(28)
        add_file(story, "src/big.ts", 400, 0)
        self.assertEqual(self.gate(story).status, "Over limit")
        rendered = story.render()
        self.assertEqual(rendered.problems, [])
        self.assertTrue(any("Q7 Size: Over limit: 491 changed lines" in w
                            for w in rendered.warnings))

    def test_lockfile_names(self):
        for name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                     "Cargo.lock", "go.sum", "sub/dir/uv.lock"):
            self.assertTrue(manifests.is_lockfile(name), name)
        self.assertFalse(manifests.is_lockfile("package.json"))


# ----------------------------------------------------------------------------- Q3, Q5, Q8


class OtherGateTest(unittest.TestCase):
    def gate(self, story, label, facts=None):
        rendered = prbody.render(facts or story.facts(), story.notes())
        return next(g for g in rendered.gates if g.label == label), rendered

    def test_q3_fails_for_an_ac_without_test_or_manual_steps(self):
        story = Story(28)
        facts = story.facts()
        facts.acmap.acs[3] = dataclasses.replace(facts.acmap.acs[3], status="missing",
                                                 tests=[])
        gate, rendered = self.gate(story, "Q3 New tests", facts)
        self.assertEqual(gate.status, "Fail")
        self.assertIn("no test and no manual steps for AC4", gate.text)
        self.assertIn("Q3 New tests: Fail", " ".join(rendered.problems))

    def test_q5_fails_on_a_forged_pass(self):
        story = Story(27, test_output=text(ACMAP / "27-e2e-failed.output.txt"), test_exit=1)
        gate, _ = self.gate(story, "Q5 AC evidence")
        self.assertEqual(gate.status, "Fail")
        self.assertIn("AC2: the verifier says pass, but its mapped test failed", gate.text)

    def test_q8_ci(self):
        story = Story(28)
        facts = story.facts()
        self.assertEqual(self.gate(story, "Q8 CI", facts)[0].value,
                         "Not configured: ci.required is false")
        facts.ci_required = True
        for runs, status in (([], "Pending"),
                             ([{"name": "test", "status": "completed",
                                "conclusion": "success"}], "Pass"),
                             ([{"name": "test", "status": "in_progress",
                                "conclusion": None}], "Pending"),
                             ([{"name": "lint", "status": "completed",
                                "conclusion": "failure"}], "Fail")):
            with self.subTest(status):
                facts.ci_runs = runs
                gate, rendered = self.gate(story, "Q8 CI", facts)
                self.assertEqual(gate.status, status)
                self.assertEqual(status != "Pass",
                                 any("Q8 CI" in p for p in rendered.problems))

    def test_ci_runs_are_read_when_required(self):
        story = Story(28)
        key = next(k for k in story.git_answers if ".factory/config.json" in k)
        story.git_answers[key]["out"] = story.git_answers[key]["out"].replace(
            '"required": false', '"required": true')
        story.ci_runs = [{"name": "build", "status": "completed", "conclusion": "success"}]
        facts = story.facts()
        self.assertTrue(facts.ci_required)
        self.assertEqual(facts.ci_runs, story.ci_runs)


# ----------------------------------------------------------------------------- the inputs


class InputTest(unittest.TestCase):
    def test_render_refuses_stale_evidence(self):
        story = Story(28)
        story.remote_head = "2" * 40
        with self.assertRaisesRegex(prbody.PrBodyError, "the evidence cannot be used"):
            story.facts()

    def test_render_needs_the_map_and_the_verdict(self):
        story = Story(28)
        story.checkpoint_body = lambda: compose(
            CheckpointMarker("S10", "S11", story.branch, story.head, 0, 0,
                             "2026-10-07T10:30:00+00:00"),
            "note\n\n" + evidence.to_block(story.evidence))
        with self.assertRaisesRegex(prbody.PrBodyError, "no AC-to-test map"):
            story.facts()
        story = Story(28)
        story.verdict = "S11 note without the verdict"
        with self.assertRaisesRegex(prbody.PrBodyError, "no AC verifier lines"):
            story.facts()

    def test_notes(self):
        self.assertEqual(prbody.parse_notes("## Summary\n- a\n\n## Follow-ups\n- b\n"),
                         {"summary": "- a", "follow_ups": "- b"})
        for bad, why in (("- a\n", "before the first section"),
                         ("## Summary\n\n## Risks\n- r\n", "Summary is required"),
                         ("## Summary\n- a\n## Testing\n- t\n", "unknown section"),
                         ("## Summary\n- a\n## Summary\n- b\n", "appears twice")):
            with self.subTest(why), self.assertRaisesRegex(prbody.PrBodyError, why):
                prbody.parse_notes(bad)

    def test_model_text_rules(self):
        self.assertEqual(prbody.model_text_problems("- fixes the #27 label\n- STORY-014 (#28)"),
                         [])
        self.assertTrue(prbody.model_text_problems("Closes #12"))
        self.assertTrue(prbody.model_text_problems("resolves owner/repo#3"))
        self.assertTrue(prbody.model_text_problems("### More"))
        self.assertTrue(prbody.model_text_problems("<!-- hidden -->"))

    def test_numstat_with_a_rename_and_a_binary(self):
        files = prbody.parse_numstat("3\t1\ta.ts\0-\t-\tlogo.png\0" "2\t2\t\0old/x.ts\0new/x.ts\0")
        self.assertEqual(files, [prbody.FileStat("a.ts", "a.ts", 3, 1),
                                 prbody.FileStat("logo.png", "logo.png", 0, 0, True),
                                 prbody.FileStat("new/x.ts", "old/x.ts", 2, 2)])


# ----------------------------------------------------------------------------- the CLI


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.story = Story(28)
        self.notes = self.dir / "notes.md"
        self.notes.write_bytes((FIXTURES / "30.notes.md").read_bytes())

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               return_value=target.Target(self.dir, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.story.github)), \
                mock.patch.object(cli, "Git", lambda p: Git(p, transport=self.story.git)), \
                mock.patch.object(prbody, "default_path", lambda n: self.dir / f"pr-{n}.md"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_render_then_check(self):
        code, out, err = self.cli("pr", "render", "--issue", "28", "--notes", str(self.notes))
        self.assertEqual(code, 0, out + err)
        self.assertIn("OK: every gate passed and every fact is declared.", out)
        self.assertIn("Q6 Scope         Not checked: the story contract declares no areas.", out)
        written = (self.dir / "pr-28.md").read_bytes().decode("utf-8")
        self.assertEqual(written, snapshot(30))
        self.story.pr_body = written
        code, out, _ = self.cli("pr", "check", "30")
        self.assertEqual(code, 0, out)
        self.assertIn("OK: the PR body is the factory's render", out)
        self.story.pr_body = written.replace("74 passed", "75 passed")
        code, out, _ = self.cli("pr", "check", "30", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["ok"])

    def test_render_exits_1_and_still_writes_on_a_problem(self):
        doctor_log(self.story, lambda out: out.replace(
            "Factory-Station: S08", "New dependency: moment — x\n\nFactory-Station: S08", 1))
        code, out, _ = self.cli("pr", "render", "--issue", "28", "--notes", str(self.notes),
                                "--json")
        self.assertEqual(code, 1)
        self.assertEqual(len(json.loads(out)["problems"]), 1)
        self.assertTrue((self.dir / "pr-28.md").is_file())

    def test_render_refuses_bad_notes(self):
        self.notes.write_text("## Summary\nCloses #3\n", encoding="utf-8")
        code, out, _ = self.cli("pr", "render", "--issue", "28", "--notes", str(self.notes))
        self.assertEqual(code, 1)
        self.assertIn("Summary: a closing keyword would close an issue on merge", out)

    def test_pr_without_an_action_still_needs_head_title_and_body(self):
        code, _, err = self.cli("pr", "--head", "story/28-x")
        self.assertEqual(code, 1)
        self.assertIn("`pr` needs --title, --body-file (or an action: `pr render`, "
                      "`pr check`)", err)


if __name__ == "__main__":
    unittest.main()
