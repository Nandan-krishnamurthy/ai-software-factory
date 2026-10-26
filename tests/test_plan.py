"""T7.4: ``plan check``, plan lint and overlap detection.

Fixtures, in ``tests/fixtures/plan/``:

* ``task-tracker/``: the real plans of the Task Tracker test project, copied unchanged from
  ``Nandan-krishnamurthy/task-tracker-factory-test`` at ``e89fbb2`` (its ``main`` on
  2026-10-25): ``02-requirements.md`` and ``05-stories.md`` of ``001-initial``,
  ``002-add-due-dates`` and ``003-priority-filter``, and ``docs/factory/traceability.md``.
  These plans predate T7.4, so no story carries a ``- Files:`` estimate.
* ``m5-replay/002-add-due-dates/``: **authored for these tests, not history.** M5's change
  request was the one line "Add due dates to tasks", and S02 stopped and asked the human
  (rule H6) before writing any requirement for it (docs/progress.md, M5). The replay records
  the request as one requirement whose statement is the request itself, verbatim.

Each fixture target gets the real traceability matrix cut to the rows that existed for its
plan (M5 started with REQ-001..REQ-021 Done). The "mutated versions" the roadmap asks for are
built from these files in the tests.
"""

import contextlib
import io
import json
import math
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, plan, target
from factory.plan import (
    NEAR,
    OVERLAP,
    Requirement,
    check_plan,
    parse_requirements,
    score_all,
    words,
)
from tests import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "plan"
TT = FIXTURES / "task-tracker"
REPLAY = FIXTURES / "m5-replay" / "002-add-due-dates"
ESTIMATE = "src/app.py (~50), tests/test_app.py (~80)"


def fixture(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rows_up_to(matrix: str, last: int) -> str:
    """The traceability matrix without the rows of requirements after REQ-<last>."""
    return "\n".join(line for line in matrix.splitlines()
                     if not (m := re.match(r"^\|\s*REQ-(\d+)", line)) or int(m[1]) <= last)


def with_estimates(stories: str, files: str = ESTIMATE) -> str:
    """Every story with a ``- Files:`` bullet after its Milestone."""
    return re.sub(r"^(- Milestone: M\d+)$", rf"\1\n- Files: {files}", stories, flags=re.M)


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


# ----------------------------------------------------------------------------- a small plan

EARLIER = """\
# Requirements: 001-initial

## Functional
- **REQ-001** (PRD §Invoices): The user can create an invoice with a customer and an amount.
- **REQ-002** (PRD §Invoices): The invoice list shows every invoice, newest first.
- **REQ-003** (PRD §Invoices): The user can delete an invoice.
"""

REQUIREMENTS = """\
# Requirements: 002-export

## Functional
- **REQ-004** (PRD §Export): The user can export the invoice list as a CSV file.
- **REQ-005** (PRD §Export): The exported file names every column in its first row.

## Changed or retired requirements
None.

## Out of scope
- **REQ-006** (PRD §Export): PDF export. Dropped at Gate A.

## Open questions
None.
"""

MATRIX = """\
| REQ | Stories | PRs | Tests | Status |
|---|---|---|---|---|
| REQ-001 | STORY-001 (#2) | #5 | `t1` | Implemented |
| REQ-002 | STORY-002 (#3) | #6 | `t2` | Implemented |
| REQ-003 | STORY-003 (#4) | #7 | `t3` | Implemented |
"""

STORY = """\
### STORY-004: Export invoices as CSV
- Traces to: REQ-004, REQ-005
- Blocked by: None
- Milestone: M1
- Files: src/export.py (~120), tests/test_export.py (~150)
#### Story
As a user, I want to export my invoices so that I can use them in a spreadsheet.
#### Acceptance criteria
- AC1: Given three invoices, when the user exports the list, then the CSV file has three rows.
- AC2: Given an export, when the file is opened, then its first row names every column.
#### Out of scope
None
#### Technical notes
None
#### Test plan
- Unit: the CSV writer.
"""


def run(requirements: str = REQUIREMENTS, stories: str = STORY, matrix: str | None = MATRIX,
        limit: int = 400, earlier: str = EARLIER) -> plan.Result:
    return check_plan(increment="002-export",
                      requirements={"001-initial": earlier, "002-export": requirements},
                      stories_text=stories, traceability=matrix, max_diff_lines=limit)


def rules(result: plan.Result) -> list[str]:
    return [p.rule for p in result.problems]


def req(rid: str, statement: str, increment: str = "001-initial") -> Requirement:
    return Requirement(rid, statement, 1, increment)


# ----------------------------------------------------------------------------- words


class WordsTest(unittest.TestCase):
    def test_case_ids_numbers_and_function_words_are_dropped(self):
        self.assertEqual(words("The Users' tasks (REQ-009, STORY-002) are listed in 3 groups"),
                         {"user", "task", "listed", "group"})

    def test_the_one_singular_rule(self):
        self.assertEqual(words("dates categories status process analysis bus"),
                         {"date", "category", "status", "process", "analysis", "bus"})

    def test_letters_of_any_language(self):
        self.assertEqual(words("Café menüs"), {"café", "menü"})

    def test_no_domain_words_are_listed(self):
        # How common a word is comes from the Done requirements, never from a list.
        for word in ("task", "user", "invoice", "date", "show", "app"):
            self.assertNotIn(word, plan.STOPWORDS)


# ----------------------------------------------------------------------------- parsing


class ParseRequirementsTest(unittest.TestCase):
    def test_citation_is_dropped_and_lines_are_kept(self):
        doc = parse_requirements(REQUIREMENTS, "002-export")
        self.assertEqual(list(doc.defined), ["REQ-004", "REQ-005"])
        self.assertEqual(doc.defined["REQ-004"].statement,
                         "The user can export the invoice list as a CSV file.")
        self.assertEqual(doc.defined["REQ-004"].line, 4)
        self.assertEqual(doc.defined["REQ-004"].increment, "002-export")

    def test_out_of_scope_bullets_are_not_in_scope(self):
        self.assertNotIn("REQ-006", parse_requirements(REQUIREMENTS, "002-export").defined)

    def test_citation_with_brackets_inside(self):
        doc = parse_requirements("## Functional\n- **REQ-001** (PRD §FR-001 (create), §Journey "
                                 "1): Text here.\n", "001-initial")
        self.assertEqual(doc.defined["REQ-001"].statement, "Text here.")

    def test_continuation_lines_numbered_items_and_fences(self):
        text = ("## Functional\n1. **REQ-001** (PRD §A): First line\n   goes on here.\n"
                "```\n- **REQ-009** (PRD §A): inside a fence\n## Not a section\n```\n"
                "- **REQ-002**: No citation.\n")
        doc = parse_requirements(text, "001-initial")
        self.assertEqual(list(doc.defined), ["REQ-001", "REQ-002"])
        self.assertEqual(doc.defined["REQ-001"].statement, "First line goes on here.")
        self.assertEqual(doc.defined["REQ-002"].statement, "No citation.")
        self.assertEqual(list(doc.sections), ["functional"])

    def test_duplicates_are_recorded(self):
        doc = parse_requirements("## Functional\n- **REQ-001**: a\n- **REQ-001**: b\n", "x")
        self.assertEqual(doc.duplicates, (("REQ-001", 2, 3),))
        self.assertEqual(doc.defined["REQ-001"].statement, "a")


# ----------------------------------------------------------------------------- scoring


class ScoreTest(unittest.TestCase):
    """The scoring rule of the module docstring, number for number."""

    def test_the_formula(self):
        # M = 2; "alpha" is in both Done requirements (weight 1 + ln(3/3) = 1), "bravo" in
        # one (1 + ln(3/2)).
        found = score_all([req("REQ-010", "alpha bravo", "002-x")],
                          [req("REQ-001", "alpha bravo"), req("REQ-002", "alpha charlie")])
        bravo = 1 + math.log(3 / 2)
        self.assertEqual([(o.done.id, o.score) for o in found],
                         [("REQ-001", 1.0), ("REQ-002", round(1 / (1 + bravo), 3))])
        self.assertEqual(found[1].score, 0.416)
        self.assertEqual(found[0].shared, ("bravo", "alpha"))  # heaviest first

    def test_exactly_the_threshold_is_a_potential_overlap(self):
        found = score_all([req("REQ-010", "alpha bravo", "002-x")],
                          [req("REQ-001", "alpha"), req("REQ-002", "bravo")])
        self.assertEqual([o.score for o in found], [OVERLAP, OVERLAP])
        self.assertTrue(all(o.potential for o in found))

    def test_the_bands(self):
        # Each word of the new requirement is used by exactly one Done requirement, so all
        # five weigh the same and a score is the share of the words.
        new = [req("REQ-010", "alpha bravo charlie delta echo", "002-x")]
        done = [req("REQ-001", "alpha bravo charlie"), req("REQ-002", "delta echo golf"),
                req("REQ-003", "hotel")]
        scores = {o.done.id: o for o in score_all(new, done)}
        self.assertEqual(scores["REQ-001"].score, 0.6)
        self.assertTrue(scores["REQ-001"].potential)
        self.assertEqual(scores["REQ-002"].score, NEAR)  # 2 of 5 equal weights
        self.assertFalse(scores["REQ-002"].potential)  # related: reported, not failing
        self.assertNotIn("REQ-003", scores)  # 0: not reported

    def test_below_the_near_band_is_not_reported(self):
        found = score_all([req("REQ-010", "alpha bravo charlie", "002-x")],
                          [req("REQ-001", "alpha"), req("REQ-002", "bravo"),
                           req("REQ-003", "charlie")])
        self.assertEqual(found, [])  # each 1/3

    def test_one_done_requirement_still_compares(self):
        # With a single Done requirement every shared word is in all of them; the smoothed
        # weight keeps it at 1, so the score is plain containment (never always 0).
        found = score_all([req("REQ-002", "Export invoices as CSV", "002-x")],
                          [req("REQ-001", "The user can export invoices as CSV files")])
        self.assertEqual([(o.done.id, o.score) for o in found], [("REQ-001", 1.0)])

    def test_no_done_requirements(self):
        self.assertEqual(score_all([req("REQ-002", "anything", "002-x")], []), [])

    def test_order_is_deterministic(self):
        new = [req("REQ-011", "alpha bravo", "002-x"), req("REQ-010", "alpha charlie", "002-x")]
        done = [req("REQ-002", "alpha"), req("REQ-001", "alpha bravo charlie")]
        first = score_all(new, done)
        self.assertEqual(first, score_all(list(reversed(new)), list(reversed(done))))
        self.assertEqual([(o.new.id, o.done.id) for o in first],
                         [("REQ-010", "REQ-001"), ("REQ-010", "REQ-002"),
                          ("REQ-011", "REQ-001"), ("REQ-011", "REQ-002")])


# ----------------------------------------------------------------------------- the check


DUPLICATE = replace_once(REQUIREMENTS, "- **REQ-005** (PRD §Export): The exported file names "
                         "every column in its first row.",
                         "- **REQ-005** (PRD §Export): The exported file names every column "
                         "in its first row.\n- **REQ-007** (PRD §Export): The invoice list "
                         "shows every invoice, newest first, with its customer.")
DUPLICATE_STORY = replace_once(STORY, "Traces to: REQ-004, REQ-005",
                               "Traces to: REQ-004, REQ-005, REQ-007")


def open_question(requirements: str, item: str) -> str:
    return replace_once(requirements, "## Open questions\nNone.", f"## Open questions\n{item}")


class CheckTest(unittest.TestCase):
    def test_a_good_plan_passes(self):
        result = run()
        self.assertEqual(result.problems, [])
        self.assertEqual(result.overlaps, [])
        self.assertTrue(result.ok)
        self.assertEqual(result.compared, 3)
        self.assertIn("Result: PASS", plan.render(result))

    def test_ac_form(self):
        result = run(stories=replace_once(STORY, "AC2: Given an export, when the file is opened,"
                                          " then", "AC2: When the file is opened,"))
        self.assertEqual(rules(result), ["ac-form"])
        self.assertIn("AC2 is not in the form `Given ..., when ..., then ...`",
                      result.problems[0].message)
        self.assertFalse(result.ok)

    def test_ac_count_and_out_of_scope_come_from_the_story_contract(self):
        six = "\n".join(f"- AC{n}: Given a, when b, then c." for n in range(1, 7))
        result = run(stories=re.sub(r"(?s)- AC1:.*?(?=#### Out of scope)", six + "\n", STORY))
        self.assertEqual(rules(result), ["acceptance-criteria"])
        result = run(stories=replace_once(STORY, "#### Out of scope\nNone\n", ""))
        self.assertEqual(rules(result), ["sections"])
        self.assertEqual(result.problems[0].file, "002-export/05-stories.md")

    def test_an_untraced_requirement(self):
        result = run(stories=replace_once(STORY, "REQ-004, REQ-005", "REQ-004"))
        self.assertEqual(rules(result), ["coverage"])
        problem = result.problems[0]
        self.assertEqual((problem.file, problem.subject, problem.line),
                         ("002-export/02-requirements.md", "REQ-005", 5))

    def test_a_trace_to_an_unknown_or_dropped_requirement(self):
        result = run(stories=replace_once(STORY, "REQ-004, REQ-005", "REQ-004, REQ-005, REQ-009"))
        self.assertEqual(rules(result), ["coverage"])
        self.assertIn("traces to REQ-009, but it is not a `- **REQ-009**` bullet",
                      result.problems[0].message)
        result = run(stories=replace_once(STORY, "REQ-004, REQ-005", "REQ-004, REQ-005, REQ-006"))
        self.assertIn("listed under `## Out of scope`", result.problems[0].message)

    def test_a_trace_to_an_earlier_requirement_this_increment_changes(self):
        changed = replace_once(REQUIREMENTS, "## Changed or retired requirements\nNone.",
                               "## Changed or retired requirements\n- REQ-002: changed by "
                               "REQ-004 (the list can now be exported).")
        result = run(requirements=changed,
                     stories=replace_once(STORY, "REQ-004, REQ-005", "REQ-002, REQ-004, REQ-005"))
        self.assertEqual(result.problems, [])

    def test_untraced_is_not_checked_while_the_contract_is_broken(self):
        result = run(stories=replace_once(STORY, "Milestone: M1", "Milestone: one"))
        self.assertEqual(rules(result), ["milestone"])
        self.assertIn("not checked", result.notes[0])

    def test_a_missing_estimate_is_a_problem_never_zero(self):
        result = run(stories=replace_once(STORY, "- Files: src/export.py (~120), "
                                          "tests/test_export.py (~150)\n", ""))
        self.assertEqual(rules(result), ["size"])
        self.assertIn("no `- Files:` estimate, so its size cannot be checked",
                      result.problems[0].message)
        self.assertIsNone(result.stories[0].estimate)
        self.assertIsNone(result.to_dict()["stories"][0]["estimate"])
        self.assertIn("STORY-004: 2 AC(s), no Files estimate", plan.render(result))

    def test_the_estimate_against_the_limit(self):
        self.assertEqual(run(limit=270).problems, [])  # 120 + 150: at the limit passes
        result = run(limit=269)
        self.assertEqual(rules(result), ["size"])
        self.assertIn("the estimate is 270 changed lines in 2 file(s), over max_diff_lines "
                      "(269)", result.problems[0].message)

    def test_lockfiles_are_not_counted(self):
        result = run(stories=replace_once(STORY, "(~150)", "(~150), package-lock.json (~900)"))
        self.assertEqual(result.problems, [])
        self.assertEqual(result.stories[0].estimate, 270)
        self.assertEqual(result.stories[0].lockfiles, ("package-lock.json",))

    def test_a_dependency_cycle_fails(self):
        second = STORY.replace("STORY-004", "STORY-005").replace("Blocked by: None",
                                                                 "Blocked by: STORY-004")
        first = replace_once(STORY, "Blocked by: None", "Blocked by: STORY-005")
        result = run(stories=first + "\n" + second)
        self.assertEqual(rules(result), ["dependency-cycle"])
        self.assertFalse(result.ok)

    def test_requirements_problems(self):
        result = run(requirements="# Requirements\n\n## Functional\nNone.\n", stories=STORY)
        self.assertIn("requirements", rules(result))
        twice = replace_once(REQUIREMENTS, "## Changed", "- **REQ-005**: again.\n\n## Changed")
        self.assertEqual(rules(run(requirements=twice)), ["requirements"])

    def test_without_a_matrix_nothing_is_compared(self):
        result = run(matrix=None)
        self.assertTrue(result.ok)
        self.assertEqual(result.compared, 0)
        self.assertIn("there are no Done requirements to compare", result.notes[0])

    def test_implemented_but_never_defined_is_a_note(self):
        matrix = MATRIX + "| REQ-099 | STORY-099 | #9 | `t` | Implemented |\n"
        result = run(matrix=matrix)
        self.assertEqual(result.compared, 3)
        self.assertIn("so not compared: REQ-099.", result.notes[0])

    def test_this_increments_own_rows_are_not_done_for_it(self):
        matrix = MATRIX + "| REQ-004 | STORY-004 | #9 | `t` | Implemented |\n"
        result = run(matrix=matrix)
        self.assertEqual((result.compared, result.notes), (3, []))

    def test_a_requirement_with_no_words_is_a_note(self):
        empty = REQUIREMENTS + "\n## Functional, more\n- **REQ-008** (PRD §X): The 2 of 3.\n"
        result = run(requirements=empty,
                     stories=replace_once(STORY, "REQ-004, REQ-005", "REQ-004, REQ-005, REQ-008"))
        self.assertIn("REQ-008 has no words to compare", result.notes[0])

    def test_every_rule_is_documented(self):
        mutated = run(requirements=replace_once(REQUIREMENTS, "## Changed", "- **REQ-005**: "
                                                "again.\n\n## Changed"),
                      stories=replace_once(STORY, "AC2: Given an export, when", "AC2: When"),
                      limit=10)
        self.assertEqual(set(rules(mutated)), {"requirements", "ac-form", "size"})
        for rule in rules(mutated) + rules(run(stories=replace_once(STORY, "REQ-004, ", ""))):
            self.assertIn(rule, plan.RULES)

    def test_json_has_every_field(self):
        data = run().to_dict()
        self.assertEqual(set(data), {"schema", "increment", "ok", "max_diff_lines", "thresholds",
                                     "stories", "problems", "compared", "overlaps", "notes"})
        self.assertEqual(data["thresholds"], {"overlap": 0.5, "near": 0.4})


class OverlapResolutionTest(unittest.TestCase):
    """A potential overlap fails until an item of Open questions or Changed or retired
    requirements names both IDs."""

    def flagged(self, result: plan.Result) -> plan.Overlap:
        return next(o for o in result.overlaps if (o.new.id, o.done.id) == ("REQ-007", "REQ-002"))

    def test_a_planted_duplicate_is_flagged_with_its_reason(self):
        result = run(requirements=DUPLICATE, stories=DUPLICATE_STORY)
        overlap = self.flagged(result)
        self.assertTrue(overlap.unresolved)
        self.assertFalse(result.ok)
        self.assertEqual(result.problems, [])
        text = plan.render(result)
        self.assertIn("REQ-007 ~ REQ-002 (001-initial): score", text)
        self.assertIn("potential overlap, UNRESOLVED", text)
        self.assertIn("shared words:", text)
        self.assertIn("REQ-002: The invoice list shows every invoice, newest first.", text)
        self.assertIn("To resolve: add an item to `## Open questions` in 02-requirements.md "
                      "that names REQ-007 and REQ-002", text)

    def test_an_open_question_naming_both_resolves_it(self):
        requirements = open_question(DUPLICATE, "1. REQ-007 may restate REQ-002, which is Done. "
                                     "Is it new work? (Assumed: yes, it adds the customer.)")
        result = run(requirements=requirements, stories=DUPLICATE_STORY)
        self.assertEqual(self.flagged(result).resolved_by, "Open questions, line 15")
        self.assertTrue(result.ok)
        self.assertIn("resolved in Open questions, line 15", plan.render(result))

    def test_a_changed_requirement_naming_both_resolves_it(self):
        requirements = replace_once(DUPLICATE, "## Changed or retired requirements\nNone.",
                                    "## Changed or retired requirements\n- REQ-002: changed "
                                    "by REQ-007,\n  which adds the customer.")
        result = run(requirements=requirements, stories=DUPLICATE_STORY)
        self.assertEqual(self.flagged(result).resolved_by,
                         "Changed or retired requirements, line 9")

    def test_naming_only_one_or_naming_them_apart_does_not(self):
        for item in ("1. Is REQ-007 new work?",
                     "1. Is REQ-007 new work?\n2. REQ-002 is Done.",
                     "1. REQ-0070 and REQ-0020 are other IDs."):
            with self.subTest(item=item):
                result = run(requirements=open_question(DUPLICATE, item), stories=DUPLICATE_STORY)
                self.assertTrue(self.flagged(result).unresolved)

    def test_a_mention_in_another_section_does_not(self):
        requirements = replace_once(DUPLICATE, "PDF export. Dropped at Gate A.",
                                    "PDF export. Dropped at Gate A (REQ-007, REQ-002).")
        self.assertTrue(self.flagged(run(requirements=requirements,
                                         stories=DUPLICATE_STORY)).unresolved)


# ----------------------------------------------------------------------------- the fixtures


CONFIG = (REPO_ROOT / "templates" / "config.json").read_text(encoding="utf-8")


class Target:
    """A throwaway target with the given increments, matrix and config."""

    def __init__(self, test: unittest.TestCase, increments: dict[str, tuple[str, str]],
                 matrix: str | None):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, (requirements, stories) in increments.items():
            folder = self.root / "docs" / "factory" / "increments" / name
            folder.mkdir(parents=True)
            (folder / "02-requirements.md").write_text(requirements, encoding="utf-8")
            (folder / "05-stories.md").write_text(stories, encoding="utf-8")
        if matrix is not None:
            (self.root / "docs" / "factory" / "traceability.md").write_text(matrix,
                                                                           encoding="utf-8")
        config = self.root / ".factory" / "config.json"
        config.parent.mkdir()
        values = {"project": "app", "repo": "owner/app", "default_branch": "main",
                  "reviewer": "someone"}
        config.write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: values[m[1]], CONFIG),
                          encoding="utf-8")

    def check(self, increment: str) -> plan.Result:
        return plan.collect(self.root, increment)


def real(increment: str) -> tuple[str, str]:
    return (fixture(TT / increment / "02-requirements.md"),
            fixture(TT / increment / "05-stories.md"))


MATRIX_TT = fixture(TT / "traceability.md")


class M5ReplayTest(unittest.TestCase):
    """AC1: replaying the M5 change request against increment 001 flags the overlap with
    REQ-003, REQ-009, REQ-012 and REQ-014."""

    def replay(self, requirements: str | None = None) -> plan.Result:
        replayed = (requirements or fixture(REPLAY / "02-requirements.md"),
                    fixture(REPLAY / "05-stories.md"))
        return Target(self, {"001-initial": real("001-initial"), "002-add-due-dates": replayed},
                      rows_up_to(MATRIX_TT, 21)).check("002-add-due-dates")

    def test_flags_the_four_done_due_date_requirements(self):
        result = self.replay()
        potential = [o for o in result.overlaps if o.potential]
        self.assertEqual([o.done.id for o in potential],
                         ["REQ-003", "REQ-009", "REQ-012", "REQ-014"])
        self.assertTrue(all(o.new.id == "REQ-022" and o.unresolved for o in potential))
        self.assertEqual({o.score for o in potential}, {0.709})
        self.assertTrue(all({"due", "date"} <= set(o.shared) for o in potential))
        self.assertEqual(result.compared, 21)
        self.assertEqual(result.problems, [])
        self.assertFalse(result.ok)

    def test_the_add_task_form_requirements_are_only_related(self):
        related = [o for o in self.replay().overlaps if not o.potential]
        self.assertEqual([(o.done.id, o.score, o.shared) for o in related],
                         [(r, 0.419, ("add", "task"))
                          for r in ("REQ-001", "REQ-002", "REQ-015", "REQ-016")])

    def test_recording_the_open_question_resolves_it(self):
        requirements = open_question(
            fixture(REPLAY / "02-requirements.md"),
            "1. REQ-022 may restate REQ-003, REQ-009, REQ-012 and REQ-014, which are Done. "
            "What should this increment add? (Assumed: nothing until the human answers.)")
        result = self.replay(requirements)
        self.assertTrue(result.ok)
        self.assertEqual({o.resolved_by for o in result.overlaps if o.potential},
                         {"Open questions, line 32"})


class RealPlansTest(unittest.TestCase):
    """The real plans of increments 001, 002 and 003, and mutated versions of them."""

    def check_002(self, requirements: str | None = None, stories: str | None = None
                  ) -> plan.Result:
        real_req, real_stories = real("002-add-due-dates")
        return Target(self, {"001-initial": real("001-initial"),
                             "002-add-due-dates": (requirements or real_req,
                                                   stories or real_stories)},
                      rows_up_to(MATRIX_TT, 26)).check("002-add-due-dates")

    def test_002_overdue_highlighting_is_related_work_not_a_duplicate(self):
        # Increment 002 (overdue highlighting) talks about due dates throughout, and REQ-025
        # cites REQ-009, yet nothing scores even 0.4: its new words (overdue, label, today …)
        # carry most of its weight.
        result = self.check_002()
        self.assertEqual(result.overlaps, [])
        self.assertEqual(result.compared, 21)
        self.assertEqual([(p.subject, p.rule) for p in result.problems],
                         [("STORY-013", "size"), ("STORY-014", "size")])  # it predates T7.4

    def test_002_with_estimates_passes(self):
        result = self.check_002(stories=with_estimates(real("002-add-due-dates")[1]))
        self.assertTrue(result.ok, plan.render(result))

    def test_002_with_a_planted_duplicate_is_flagged(self):
        requirements, stories = real("002-add-due-dates")
        requirements = replace_once(
            requirements, "\n## Non-functional",
            "- **REQ-027** (PRD §Add due dates to tasks): The user can set, change or clear the "
            "due date of a task.\n\n## Non-functional")
        stories = replace_once(with_estimates(stories), "Traces to: REQ-026",
                               "Traces to: REQ-026, REQ-027")
        result = self.check_002(requirements, stories)
        # The duplicate matches REQ-009 completely. REQ-010 (the same edit, of the priority)
        # is over the threshold too: parallel wording scores high, and the plan must say
        # whether it is new work. The real 002 requirements are still not reported.
        self.assertEqual([(o.done.id, o.score) for o in result.unresolved],
                         [("REQ-009", 1.0), ("REQ-010", 0.687)])
        self.assertEqual({o.new.id for o in result.overlaps}, {"REQ-027"})
        self.assertFalse(result.ok)

    def test_002_with_a_planted_dependency_cycle_fails(self):
        # AC2: a planted dependency cycle fails.
        stories = replace_once(with_estimates(real("002-add-due-dates")[1]),
                               "Blocked by: None", "Blocked by: STORY-014")
        result = self.check_002(stories=stories)
        self.assertEqual([(p.subject, p.rule) for p in result.problems],
                         [("STORY-013", "dependency-cycle")])
        self.assertIn("STORY-013 → STORY-014 → STORY-013", result.problems[0].message)
        self.assertFalse(result.ok)

    def check_001(self, stories: str) -> plan.Result:
        return Target(self, {"001-initial": (real("001-initial")[0], stories)},
                      rows_up_to(MATRIX_TT, 21)).check("001-initial")

    def test_001_the_first_increment_has_nothing_to_compare(self):
        result = self.check_001(with_estimates(real("001-initial")[1]))
        self.assertTrue(result.ok, plan.render(result))
        self.assertEqual((result.compared, result.overlaps, result.notes), (0, [], []))

    def test_001_mutations(self):
        stories = with_estimates(real("001-initial")[1])
        mutations = {
            "ac-form": ("- AC1: Given a fresh clone, when the install command and then the "
                        "build command run, then",
                        "- AC1: Once the install command and then the build command run,"),
            "coverage": ("- Traces to: REQ-011\n", "- Traces to: REQ-010\n"),
            "sections": ("#### Out of scope\n", "#### Not in scope\n"),
            "size": ("- Files: " + ESTIMATE, "- Files: src/app.py (~300), tests/a.py (~200)"),
        }
        for rule, (old, new) in mutations.items():
            with self.subTest(rule=rule):
                self.assertIn(old, stories)
                result = self.check_001(stories.replace(old, new, 1))
                self.assertIn(rule, rules(result))
                self.assertFalse(result.ok)

    def test_003_a_related_requirement_over_the_threshold_needs_an_open_question(self):
        # A known false positive, kept rather than tuned away: REQ-034 (a filter choice is
        # shown within 100 ms) restates REQ-019's "reflected … within 100 ms of the user's
        # action" for a new action. It scores just over 0.5, so the plan must say so.
        requirements, stories = real("003-priority-filter")
        increments = {"001-initial": real("001-initial"),
                      "002-add-due-dates": real("002-add-due-dates"),
                      "003-priority-filter": (requirements, with_estimates(stories))}
        result = Target(self, increments, MATRIX_TT).check("003-priority-filter")
        self.assertEqual([(o.new.id, o.done.id, o.score, o.potential) for o in result.overlaps],
                         [("REQ-031", "REQ-025", 0.424, False),
                          ("REQ-034", "REQ-019", 0.529, True)])
        self.assertEqual(result.compared, 26)
        self.assertEqual(result.problems, [])  # every AC of 003 has the Given/when/then form
        self.assertFalse(result.ok)
        increments["003-priority-filter"] = (
            requirements.replace("## Open questions\n", "## Open questions\n- REQ-034 applies "
                                 "REQ-019's 100 ms budget to choosing a filter; it is new "
                                 "work, not a duplicate.\n", 1), with_estimates(stories))
        self.assertTrue(Target(self, increments, MATRIX_TT).check("003-priority-filter").ok)


class CollectTest(unittest.TestCase):
    def test_bad_increment_name_and_missing_files_are_errors(self):
        t = Target(self, {"001-initial": (REQUIREMENTS, STORY)}, MATRIX)
        for increment, message in (("1-initial", "is not an increment folder name"),
                                   ("002-other", "no increment folder")):
            with self.subTest(increment=increment):
                with self.assertRaisesRegex(plan.PlanError, message):
                    t.check(increment)
        (t.root / "docs/factory/increments/001-initial/05-stories.md").unlink()
        with self.assertRaisesRegex(plan.PlanError, "05-stories.md not found"):
            t.check("001-initial")

    def test_the_limit_comes_from_the_config(self):
        t = Target(self, {"001-initial": (EARLIER, STORY.replace("REQ-004, REQ-005",
                                                                 "REQ-001, REQ-002, REQ-003"))},
                   None)
        config = t.root / ".factory" / "config.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data["limits"]["max_diff_lines"] = 100
        config.write_text(json.dumps(data), encoding="utf-8")
        result = t.check("001-initial")
        self.assertEqual(result.max_diff_lines, 100)
        self.assertEqual(rules(result), ["size"])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.target = Target(self, {"001-initial": real("001-initial"),
                                    "002-add-due-dates": (fixture(REPLAY / "02-requirements.md"),
                                                          fixture(REPLAY / "05-stories.md"))},
                             rows_up_to(MATRIX_TT, 21))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(self.target.root, "owner/app")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["plan", "check", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_unresolved_overlap_is_exit_1_with_actionable_output(self):
        code, out, _ = self.run_cli("--increment", "002-add-due-dates")
        self.assertEqual(code, 1)
        self.assertIn("Result: FAIL: 0 problem(s), 4 unresolved overlap(s)", out)
        self.assertIn("To resolve:", out)

    def test_a_passing_plan_is_exit_0(self):
        stories = self.target.root / "docs/factory/increments/001-initial/05-stories.md"
        stories.write_text(with_estimates(fixture(stories)), encoding="utf-8")
        code, out, _ = self.run_cli("--increment", "001-initial")
        self.assertEqual(code, 0, out)
        self.assertIn("Result: PASS", out)

    def test_json_and_the_banner_on_stderr(self):
        code, out, err = self.run_cli("--increment", "002-add-due-dates", "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(len([o for o in data["overlaps"] if o["kind"] == "potential"]), 4)
        self.assertIn("Target:", err)

    def test_errors_are_exit_1(self):
        code, _, err = self.run_cli("--increment", "009-none")
        self.assertEqual(code, 1)
        self.assertIn("no increment folder", err)

    def test_increment_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["plan", "check"])


if __name__ == "__main__":
    unittest.main()
