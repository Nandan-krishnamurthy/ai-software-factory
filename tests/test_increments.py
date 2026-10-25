"""T2.3: increment handling: current/next increment, global IDs, one at a time.
T7.1: IDs are allocated only by structured records and labelled story issues."""

import base64
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, increments, issues, target
from factory.gh import Gh, ProcessResult
from factory.increments import (
    Layout,
    PlanRecords,
    Remote,
    StoryIssue,
    assess,
    scan_layout,
    slugify,
)
from factory.markers import PlanningMarker, StoryMarker, build
from factory.stories import parse

REPO = "owner/app"
LABEL = "factory:story"


def story(n: int, blocked: str = "None") -> str:
    return f"""
### STORY-{n:03d}: Story {n}
- Traces to: REQ-{n:03d}
- Blocked by: {blocked}
- Milestone: M1
#### Story
As a user, I want {n} so that it works.
#### Acceptance criteria
- AC1: Given x, when y, then z.
#### Out of scope
None
#### Technical notes
None
#### Test plan
- Unit: {n}
"""


class TargetDir:
    """A target working tree on disk with ``docs/factory/increments/<inc>/`` files."""

    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, relpath: str, text: str) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def increment(self, name: str, reqs: range, stories: range) -> None:
        base = f"docs/factory/increments/{name}"
        self.write(f"{base}/00-prd.md", "# PRD\n")
        self.write(f"{base}/02-requirements.md", "".join(
            f"- **REQ-{n:03d}**: requirement {n}\n" for n in reqs))
        self.write(f"{base}/05-stories.md", "# Stories\n" + "".join(story(n) for n in stories))


def issue(n, story_id, inc="001-initial", open=True, labels=(), blocked_by=()):
    return StoryIssue(n, story_id, inc, open, frozenset(labels), tuple(blocked_by))


def merged(*incs, issues_=(), branches=()):
    open_numbers = frozenset(i.number for i in issues_ if i.open)
    return Remote(plan_branches=frozenset(branches),
                  planning_prs={inc: ("MERGED",) for inc in incs},
                  issues=tuple(issues_), open_numbers=open_numbers)


class ScanLayoutTest(unittest.TestCase):
    def test_empty_target(self):
        layout = scan_layout(TargetDir(self).root)
        self.assertEqual(layout, Layout())
        result = assess(layout, Remote())
        self.assertEqual((result.current, result.next_increment, result.next_req,
                          result.next_story), (None, "001-initial", "REQ-001", "STORY-001"))
        self.assertEqual(result.reasons, ())

    def test_first_increment_may_have_its_own_slug(self):
        self.assertEqual(assess(Layout(), Remote(), "Task Tracker MVP").next_increment,
                         "001-task-tracker-mvp")

    def test_reads_increments_ids_and_stories(self):
        t = TargetDir(self)
        t.increment("001-initial", range(1, 13), range(1, 6))
        t.write("docs/factory/traceability.md", "| REQ-013 | — | — | — | Deferred |\n")
        t.write("docs/factory/increments/not-an-increment/x.md", "REQ-500")  # a mention only
        t.write("docs/other/notes.md", "REQ-900 STORY-900")  # outside docs/factory: ignored
        layout = scan_layout(t.root)
        self.assertEqual(layout.increments, {"001-initial"})
        self.assertEqual(max(layout.req_numbers), 12)  # T7.1: records only
        self.assertEqual(max(layout.story_numbers), 5)
        self.assertEqual(layout.stories["001-initial"],
                         {f"STORY-{n:03d}" for n in range(1, 6)})
        self.assertEqual(layout.mentions["REQ-013"], {"docs/factory/traceability.md"})
        self.assertEqual(layout.mentions["REQ-500"],
                         {"docs/factory/increments/not-an-increment/x.md"})
        self.assertNotIn("REQ-900", layout.mentions)
        self.assertNotIn("STORY-900", layout.mentions)

    def test_ids_with_more_than_three_digits(self):
        t = TargetDir(self)
        t.increment("001-initial", range(998, 1001), range(999, 1001))
        result = assess(scan_layout(t.root), merged("001-initial"))
        self.assertEqual((result.next_req, result.next_story), ("REQ-1001", "STORY-1001"))

    def test_word_boundaries(self):
        t = TargetDir(self)
        t.write("docs/factory/x.md", "PREREQ-900 XSTORY-900 REQ-12 REQ-004a REQ-007.")
        layout = scan_layout(t.root)
        self.assertEqual(set(layout.mentions), {"REQ-007"})  # T7.1: prose only mentions
        self.assertEqual(layout.req_numbers, set())
        self.assertEqual(layout.story_numbers, set())

    def test_record_forms(self):
        t = TargetDir(self)
        base = "docs/factory/increments/001-initial"
        t.write(f"{base}/02-requirements.md",
                "- **REQ-001** (PRD §Goals): one\n  - **REQ-002**: nested\n"
                "**REQ-003** not a bullet\n- REQ-004 not bold\n- see **REQ-005**\n")
        t.write(f"{base}/05-stories.md",
                "### STORY-001: one\n#### STORY-002: too deep\n## STORY-003: too shallow\n")
        layout = scan_layout(t.root)
        self.assertEqual(layout.req_numbers, {1, 2})
        self.assertEqual(layout.story_numbers, {1})


class SlugTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Add due dates!"), "add-due-dates")
        self.assertEqual(slugify("  --API v2 -- "), "api-v2")
        self.assertEqual(slugify("x" * 60), "x" * 40)
        self.assertTrue(increments.is_increment("002-" + slugify("Ünïcode & more")))

    def test_slug_with_nothing_usable(self):
        with self.assertRaises(ValueError):
            slugify("!!!")


class NextIncrementTest(unittest.TestCase):
    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 4), range(1, 3))
        self.layout = scan_layout(self.t.root)
        self.done = [issue(1, "STORY-001", open=False), issue(2, "STORY-002", open=False)]

    def test_all_stories_done_allocates_the_next_increment(self):
        result = assess(self.layout, merged("001-initial", issues_=self.done), "due dates")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.current, "001-initial")
        self.assertEqual(result.next_increment, "002-due-dates")
        self.assertEqual((result.next_req, result.next_story), ("REQ-004", "STORY-003"))

    def test_second_increment_of_an_existing_project_continues_the_numbering(self):
        """T5.2 acceptance criterion, on the shape of Task Tracker after increment 001:
        21 requirements and 12 stories, all done. The next increment is 002-<slug>, and
        its REQ and STORY numbers continue from 001's (they are never reused)."""
        t = TargetDir(self)
        t.increment("001-initial", range(1, 22), range(1, 13))
        t.write("docs/factory/traceability.md", "| REQ-021 | STORY-012 (#13) | #25 | x | "
                                                "Implemented |\n")
        done = [issue(n + 1, f"STORY-{n:03d}", open=False, labels={"status:done"})
                for n in range(1, 13)]
        result = assess(scan_layout(t.root), merged("001-initial", issues_=done), "Due dates")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.current, "001-initial")
        self.assertEqual(result.next_increment, "002-due-dates")
        self.assertEqual((result.next_req, result.next_story), ("REQ-022", "STORY-013"))

    def test_without_a_slug_only_numbering_is_reported(self):
        result = assess(self.layout, merged("001-initial", issues_=self.done))
        self.assertEqual((result.next_increment, result.reasons), (None, ()))
        self.assertTrue(result.to_dict()["can_start"])

    def test_next_number_skips_abandoned_and_remote_only_increments(self):
        remote = Remote(planning_prs={"001-initial": ("MERGED",), "004-dropped": ("CLOSED",)},
                        issues=tuple(self.done))
        result = assess(self.layout, remote, "next")
        self.assertEqual(result.current, "004-dropped")
        self.assertEqual(result.next_increment, "005-next")
        self.assertEqual(result.increments, ("001-initial", "004-dropped"))

    def test_increment_seen_only_in_issue_markers_is_not_current(self):
        # Regression (seen in the sandbox): issues created by the T2.2 integration test
        # carry increment 900-integration, which has no folder, branch or Planning PR.
        # It must not become the current increment, but its number is never reused.
        # (T7.1: only while the issue keeps the factory:story label; see M4RegressionTest.)
        remote = Remote(issues=(issue(7, "STORY-9251315", inc="900-integration", open=False,
                                      labels={LABEL}),))
        result = assess(Layout(), remote)
        self.assertEqual(result.current, None)
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.next_increment, "901-initial")
        self.assertEqual(result.next_story, "STORY-9251316")
        self.assertEqual(result.increments, ("900-integration",))

    def test_numbers_used_up(self):
        remote = Remote(planning_prs={"999-last": ("CLOSED",)})
        self.assertIn("used up", assess(Layout(), remote, "x").reasons[0])


class RefusalTest(unittest.TestCase):
    """A new increment is refused while the current one has open, unblocked stories."""

    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 4), range(1, 4))
        self.layout = scan_layout(self.t.root)

    def check(self, remote, *expected):
        result = assess(self.layout, remote, "more")
        self.assertIsNone(result.next_increment)
        self.assertFalse(result.to_dict()["can_start"])
        text = " ".join(result.reasons)
        for fragment in expected:
            self.assertIn(fragment, text)
        return result

    def allowed(self, remote):
        result = assess(self.layout, remote, "more")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.next_increment, "002-more")

    def closed(self, *numbers):
        return [issue(n, f"STORY-{n:03d}", open=False) for n in numbers]

    def test_open_unblocked_story(self):
        remote = merged("001-initial", issues_=[
            *self.closed(1, 2), issue(3, "STORY-003", labels={"status:ready"})])
        self.check(remote, "open, unblocked stories: #3 (STORY-003)")

    def test_story_in_progress_or_in_review(self):
        for label in ("status:in-progress", "status:in-review", "status:changes-requested"):
            with self.subTest(label):
                remote = merged("001-initial", issues_=[
                    *self.closed(1, 2), issue(3, "STORY-003", labels={label})])
                self.check(remote, "#3 (STORY-003)")

    def test_blocked_by_label_or_needs_human_does_not_count(self):
        for label in ("status:blocked", "factory:needs-human"):
            with self.subTest(label):
                self.allowed(merged("001-initial", issues_=[
                    *self.closed(1, 2), issue(3, "STORY-003", labels={label})]))

    def test_blocked_by_an_open_story_does_not_count(self):
        # #2 is needs-human; #3 waits on #2. Nothing can move without a human.
        self.allowed(merged("001-initial", issues_=[
            *self.closed(1), issue(2, "STORY-002", labels={"factory:needs-human"}),
            issue(3, "STORY-003", labels={"status:ready"}, blocked_by=[2])]))

    def test_blocked_by_a_closed_or_unknown_issue_counts(self):
        for blocked_by in ([1], [77]):
            with self.subTest(blocked_by=blocked_by):
                remote = merged("001-initial", issues_=[
                    *self.closed(1, 2),
                    issue(3, "STORY-003", labels={"status:ready"}, blocked_by=blocked_by)])
                self.check(remote, "#3 (STORY-003)")

    def test_stories_without_issues(self):
        self.check(merged("001-initial", issues_=self.closed(1)),
                   "stories without issues (STORY-002, STORY-003)")

    def test_planning_not_merged(self):
        for remote in (Remote(planning_prs={"001-initial": ("OPEN",)}),
                       Remote(plan_branches=frozenset({"001-initial"})),
                       Remote(planning_prs={"001-initial": ("CLOSED",)},
                              plan_branches=frozenset({"001-initial"})),
                       Remote()):  # only the local folder exists (S00 not pushed yet)
            with self.subTest(remote=remote):
                self.check(remote, "has not passed Gate A")

    def test_refusal_says_how_to_abandon_the_current_plan(self):
        cases = [
            (Remote(planning_prs={"001-initial": ("OPEN",)},
                    plan_branches=frozenset({"001-initial"})),
             "close its Planning PR and delete branch factory/plan-001-initial"),
            (Remote(plan_branches=frozenset({"001-initial"})),
             "or delete branch factory/plan-001-initial to abandon it"),
            (Remote(), "or delete the local folder docs/factory/increments/001-initial"),
        ]
        for remote, advice in cases:
            with self.subTest(advice=advice):
                self.check(remote, "Finish it with /factory-resume", advice)

    def test_abandoned_planning_allows_a_new_increment(self):
        remote = Remote(planning_prs={"001-initial": ("CLOSED",)})
        self.allowed(remote)

    def test_replanned_after_a_closed_pr(self):
        remote = Remote(planning_prs={"001-initial": ("CLOSED", "MERGED")},
                        issues=tuple(self.closed(1, 2, 3)))
        self.allowed(remote)

    def test_local_clone_behind(self):
        remote = merged("001-initial", "002-more", issues_=self.closed(1, 2, 3))
        result = assess(self.layout, remote, "again")
        self.assertIn("002-more/05-stories.md is missing locally", result.reasons[0])

    def test_only_the_current_increment_is_checked(self):
        t = TargetDir(self)
        t.increment("001-initial", range(1, 2), range(1, 2))
        t.increment("002-more", range(2, 3), range(2, 3))
        remote = merged("001-initial", "002-more", issues_=[
            issue(1, "STORY-001", labels={"status:ready"}),  # left open in 001
            issue(2, "STORY-002", inc="002-more", open=False)])
        self.assertEqual(assess(scan_layout(t.root), remote, "x").next_increment, "003-x")


class IdsNeverReusedTest(unittest.TestCase):
    """Acceptance criterion: IDs are never reused across increments."""

    def test_ids_from_planning_records_and_labelled_issues_count(self):
        # T7.1: an abandoned plan's records (read at its head commit) and labelled story
        # issues allocate IDs; its PR body does not.
        t = TargetDir(self)
        t.increment("001-initial", range(1, 3), range(1, 3))
        remote = Remote(
            planning_prs={"001-initial": ("MERGED",), "002-dropped": ("CLOSED",)},
            plans=(PlanRecords(5, "002-dropped", "a" * 40, frozenset({30}), frozenset({40}),
                               body="| STORY-041 | x | M1 | None | REQ-031 |"),),
            issues=(issue(1, "STORY-001", open=False, labels={LABEL}),
                    issue(2, "STORY-002", open=False, labels={LABEL}),
                    issue(3, "STORY-055", inc="000-older", open=False, labels={LABEL})))
        result = assess(scan_layout(t.root), remote, "next")
        self.assertEqual((result.next_req, result.next_story), ("REQ-031", "STORY-056"))
        self.assertEqual(result.warnings, (
            "REQ-031 is mentioned in Planning PR #5 but never allocated",
            "STORY-041 is mentioned in Planning PR #5 but never allocated"))

    def test_three_increments_in_a_row(self):
        """Plan each increment with the allocated IDs; no ID is ever handed out twice."""
        t = TargetDir(self)
        remote_issues: list[StoryIssue] = []
        planning: dict[str, tuple[str, ...]] = {}
        seen_reqs: set[str] = set()
        seen_stories: set[str] = set()
        next_number = 1
        for slug, n_reqs, n_stories in (("initial", 3, 2), ("due-dates", 2, 3), ("tags", 4, 1)):
            result = assess(scan_layout(t.root), Remote(
                planning_prs=dict(planning), issues=tuple(remote_issues)), slug)
            self.assertEqual(result.reasons, ())
            inc = result.next_increment
            req0 = int(result.next_req.split("-")[1])
            story0 = int(result.next_story.split("-")[1])
            reqs = [f"REQ-{n:03d}" for n in range(req0, req0 + n_reqs)]
            stories = [f"STORY-{n:03d}" for n in range(story0, story0 + n_stories)]
            self.assertFalse(seen_reqs & set(reqs), "a REQ ID was reused")
            self.assertFalse(seen_stories & set(stories), "a STORY ID was reused")
            seen_reqs |= set(reqs)
            seen_stories |= set(stories)
            t.increment(inc, range(req0, req0 + n_reqs), range(story0, story0 + n_stories))
            # The stories file is valid, and issues sync accepts its IDs (no id-reused).
            parsed = parse((t.root / f"docs/factory/increments/{inc}/05-stories.md")
                           .read_text(encoding="utf-8"))
            existing = {i.story_id: [issues.ExistingIssue(i.number, i.story_id, i.increment,
                                                          "closed")] for i in remote_issues}
            issues.plan_sync(parsed, inc, existing)
            # Gate A passes, issues are created, and every story is finished.
            planning[inc] = ("MERGED",)
            for sid in stories:
                remote_issues.append(issue(next_number, sid, inc=inc, open=False))
                next_number += 1
        self.assertEqual(sorted(planning), ["001-initial", "002-due-dates", "003-tags"])
        self.assertEqual(len(seen_reqs), 9)
        self.assertEqual(len(seen_stories), 6)

    def test_reusing_an_id_is_caught_by_issues_sync(self):
        # The other half of the guarantee: a stories file that reuses an ID is rejected.
        t = TargetDir(self)
        t.increment("002-more", range(5, 6), range(1, 2))
        parsed = parse((t.root / "docs/factory/increments/002-more/05-stories.md")
                       .read_text(encoding="utf-8"))
        existing = {"STORY-001": [issues.ExistingIssue(1, "STORY-001", "001-initial",
                                                       "closed")]}
        with self.assertRaisesRegex(Exception, r"\[id-reused\]"):
            issues.plan_sync(parsed, "002-more", existing)


INC = "docs/factory/increments"


def done_issues(stories: range, inc="001-initial", first=2):
    """Closed, labelled story issues, one per story, numbered from ``first``."""
    return [issue(first + k, f"STORY-{n:03d}", inc=inc, open=False, labels={LABEL})
            for k, n in enumerate(stories)]


class ProseMentionRegressionTest(unittest.TestCase):
    """T7.1 AC1 and the other times a prose mention used up an ID (B-18)."""

    M5_NOTE = "- Next free IDs: REQ-022, STORY-013.\n"  # Task Tracker 8570dc3
    M6_NOTE = ("- The next free requirement and story IDs are REQ-027 and STORY-015 "
               "(`increment next`).\n")  # Task Tracker d8942ce

    def task_tracker_after_001(self) -> TargetDir:
        t = TargetDir(self)
        t.increment("001-initial", range(1, 22), range(1, 13))
        return t

    def test_m5_note_before_anything_is_allocated(self):
        t = self.task_tracker_after_001()
        note = f"{INC}/002-add-due-dates/01-codebase-analysis.md"
        t.write(f"{INC}/002-add-due-dates/00-prd.md", "# Due dates\n")
        t.write(note, self.M5_NOTE)
        result = assess(scan_layout(t.root), merged("001-initial", issues_=done_issues(
            range(1, 13))))
        self.assertEqual((result.next_req, result.next_story), ("REQ-022", "STORY-013"))
        self.assertEqual(result.warnings, (
            f"REQ-022 is mentioned in {note} but never allocated",
            f"STORY-013 is mentioned in {note} but never allocated"))

    def test_m5_note_no_longer_uses_up_story_013(self):
        """AC1: after S02 allocates REQ-022..026, the note still does not use STORY-013."""
        t = self.task_tracker_after_001()
        note = f"{INC}/002-add-due-dates/01-codebase-analysis.md"
        t.write(note, self.M5_NOTE)
        t.write(f"{INC}/002-add-due-dates/02-requirements.md", "".join(
            f"- **REQ-{n:03d}** (PRD §Goals): r\n" for n in range(22, 27)))
        result = assess(scan_layout(t.root), merged("001-initial", issues_=done_issues(
            range(1, 13))))
        self.assertEqual((result.next_req, result.next_story), ("REQ-027", "STORY-013"))
        self.assertEqual(result.warnings,
                         (f"STORY-013 is mentioned in {note} but never allocated",))

    def test_m6_note(self):
        t = self.task_tracker_after_001()
        t.increment("002-add-due-dates", range(22, 27), range(13, 15))
        note = f"{INC}/003-priority-filter/01-codebase-analysis.md"
        t.write(note, self.M6_NOTE)
        remote = merged("001-initial", "002-add-due-dates",
                        issues_=done_issues(range(1, 15)))
        result = assess(scan_layout(t.root), remote)
        self.assertEqual((result.next_req, result.next_story), ("REQ-027", "STORY-015"))
        self.assertEqual([w.split()[0] for w in result.warnings], ["REQ-027", "STORY-015"])

    def test_m2_forward_reference_in_the_plan(self):
        # M2 Problem 4: S04's plan named STORY-001 before S05 had written any story.
        t = TargetDir(self)
        t.write(f"{INC}/001-initial/02-requirements.md", "- **REQ-001** (PRD §x): r\n")
        plan = f"{INC}/001-initial/04-implementation-plan.md"
        t.write(plan, "M1 starts with STORY-001, the walking skeleton.\n")
        result = assess(scan_layout(t.root), Remote())
        self.assertEqual((result.next_req, result.next_story), ("REQ-002", "STORY-001"))
        self.assertEqual(result.warnings,
                         (f"STORY-001 is mentioned in {plan} but never allocated",))


class M4RegressionTest(unittest.TestCase):
    """T7.1 AC2: stale story markers on issues without the label (M4 follow-up 1)."""

    def stale(self, labels=()):
        return Remote(issues=(
            issue(3, "STORY-9251316", inc="900-initial", open=False, labels=labels),
            issue(4, "STORY-9251315", inc="900-initial", open=True, labels=labels)))

    def test_unlabelled_markers_do_not_move_the_numbering(self):
        result = assess(Layout(), self.stale())
        self.assertEqual((result.next_increment, result.next_req, result.next_story),
                         ("001-initial", "REQ-001", "STORY-001"))
        self.assertEqual(result.increments, ())
        self.assertEqual(result.warnings, (
            "STORY-9251315 is mentioned in issue #4 but never allocated",
            "STORY-9251316 is mentioned in issue #3 but never allocated"))

    def test_labelled_markers_still_count(self):
        for labels in ({LABEL}, {"Factory:Story"}):  # GitHub labels are case-insensitive
            with self.subTest(labels=labels):
                result = assess(Layout(), self.stale(labels))
                self.assertEqual((result.next_increment, result.next_story),
                                 ("901-initial", "STORY-9251317"))
                self.assertEqual(result.warnings, ())

    def test_end_to_end_from_github(self):
        fake = FakeGitHub(issues_=[gh_issue(3, "STORY-9251316", "900-initial", "closed"),
                                   gh_issue(4, "STORY-9251315", "900-initial")])
        result = increments.assess_target(Gh(transport=fake), TargetDir(self).root, REPO)
        self.assertEqual((result.next_increment, result.next_story),
                         ("001-initial", "STORY-001"))
        self.assertEqual(len(result.warnings), 2)

    def test_unlabelled_issues_still_count_as_open_stories(self):
        # Decision D3: the label filter is for numbering only; refusals are unchanged.
        t = TargetDir(self)
        t.increment("001-initial", range(1, 2), range(1, 2))
        result = assess(scan_layout(t.root), merged("001-initial", issues_=[
            issue(1, "STORY-001", labels={"status:ready"})]), "more")
        self.assertIn("#1 (STORY-001)", " ".join(result.reasons))


class ProseNeverAllocatesTest(unittest.TestCase):
    def test_only_records_allocate(self):
        t = TargetDir(self)
        t.increment("001-initial", range(1, 3), range(1, 2))
        base = f"{INC}/001-initial"
        t.write(f"{base}/00-prd.md", "- **REQ-100** the PRD's own numbering\n")
        t.write(f"{base}/01-codebase-analysis.md", "REQ-101 STORY-101\n")
        t.write(f"{base}/03-architecture.md", "- **REQ-102**: in a decision\n")
        t.write(f"{base}/04-implementation-plan.md", "### STORY-103: planned\n")
        t.write("docs/factory/traceability.md", "| REQ-104 | STORY-104 | — | — | — |\n")
        t.write(f"{INC}/not-an-increment/02-requirements.md", "- **REQ-105**: r\n")
        t.write(f"{INC}/not-an-increment/05-stories.md", "### STORY-105: s\n")
        remote = Remote(planning_prs={"001-initial": ("MERGED",)}, plans=(PlanRecords(
            1, "001-initial", "a" * 40, frozenset({1, 2}), frozenset({1}),
            body="## Summary\nAdds REQ-106 and STORY-106.\n"),))
        result = assess(scan_layout(t.root), remote)
        self.assertEqual((result.next_req, result.next_story), ("REQ-003", "STORY-002"))
        self.assertEqual([w.split()[0] for w in result.warnings], [
            "REQ-100", "REQ-101", "REQ-102", "REQ-104", "REQ-105", "REQ-106",
            "STORY-101", "STORY-103", "STORY-104", "STORY-105", "STORY-106"])

    def test_allocated_mentions_give_no_warning_and_sources_are_listed(self):
        t = TargetDir(self)
        t.increment("001-initial", range(1, 3), range(1, 2))
        t.write("docs/factory/traceability.md", "| REQ-001 | STORY-001 | — | — | — |\n")
        t.write("docs/factory/notes.md", "REQ-009\n")
        t.write("docs/factory/a.md", "REQ-0009\n")  # the same number, written differently
        remote = Remote(plans=(PlanRecords(7, "002-x", body="REQ-009"),
                               PlanRecords(3, "002-x", body="REQ-009 REQ-001")))
        result = assess(scan_layout(t.root), remote)
        self.assertEqual(result.warnings, (
            "REQ-009 is mentioned in docs/factory/a.md, docs/factory/notes.md, "
            "Planning PR #3, Planning PR #7 but never allocated",))


class PlanRecordsTest(unittest.TestCase):
    """Decision D1: records at every Planning PR's head commit allocate, in any state."""

    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 37), range(1, 18))
        self.layout = scan_layout(self.t.root)
        self.done = done_issues(range(1, 18))

    def test_abandoned_plan_ids_are_never_reused(self):
        remote = Remote(
            planning_prs={"001-initial": ("MERGED",), "002-tags": ("CLOSED",)},
            plans=(PlanRecords(40, "002-tags", "b" * 40, frozenset({37, 38, 39}),
                               frozenset({18, 19}), body="Also STORY-025 later."),),
            issues=tuple(self.done))
        result = assess(self.layout, remote, "tags again")
        self.assertEqual(result.reasons, ())  # the abandoned-plan rule still applies
        self.assertEqual(result.next_increment, "003-tags-again")
        self.assertEqual((result.next_req, result.next_story), ("REQ-040", "STORY-020"))
        self.assertEqual(result.warnings,
                         ("STORY-025 is mentioned in Planning PR #40 but never allocated",))

    def test_unreadable_plan_counts_every_id_in_its_body(self):
        remote = Remote(
            planning_prs={"001-initial": ("MERGED",), "002-tags": ("CLOSED",)},
            plans=(PlanRecords(40, "002-tags", "b" * 40, body="Adds REQ-045 and STORY-030.",
                               error="commit HTTP 404"),
                   PlanRecords(41, "003-x", None, body="STORY-031", error="no head commit")),
            issues=tuple(self.done))
        result = assess(self.layout, remote)
        self.assertEqual((result.next_req, result.next_story), ("REQ-046", "STORY-032"))
        self.assertEqual(result.warnings, (
            "Planning PR #40: its records at bbbbbbb could not be read (commit HTTP 404); "
            "every ID in its body was counted instead",
            "Planning PR #41: its records at unknown commit could not be read "
            "(no head commit); every ID in its body was counted instead"))

    def test_merged_plan_counts_even_if_the_local_clone_is_stale(self):
        remote = Remote(planning_prs={"001-initial": ("MERGED",), "002-x": ("MERGED",)},
                        plans=(PlanRecords(9, "002-x", "c" * 40, frozenset({37}),
                                           frozenset({18})),),
                        issues=tuple(self.done))
        result = assess(self.layout, remote)
        self.assertEqual((result.next_req, result.next_story), ("REQ-038", "STORY-019"))

    def test_open_plan_and_the_local_tree_are_merged(self):
        self.t.increment("002-x", range(37, 40), range(18, 19))  # S05 at work locally
        remote = Remote(planning_prs={"001-initial": ("MERGED",), "002-x": ("OPEN",)},
                        plans=(PlanRecords(9, "002-x", "c" * 40, frozenset({37}),
                                           frozenset({18, 19})),))
        result = assess(scan_layout(self.t.root), remote)
        self.assertEqual((result.next_req, result.next_story), ("REQ-040", "STORY-020"))


def file_response(text: str) -> dict:
    """A contents-API file object, base64 with line breaks as GitHub sends it."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    lines = [encoded[i:i + 60] for i in range(0, len(encoded), 60)]
    return {"type": "file", "encoding": "base64", "content": "\n".join(lines) + "\n"}


def plan_files(inc: str, reqs=(), stories=()) -> dict[str, dict]:
    """The two record files of a plan, as contents-API responses."""
    base = f"docs/factory/increments/{inc}"
    return {f"{base}/02-requirements.md": file_response(
                "".join(f"- **REQ-{n:03d}** (PRD §x): r\n" for n in reqs)),
            f"{base}/05-stories.md": file_response(
                "# Stories\n" + "".join(story(n) for n in stories))}


class FakeGitHub:
    """Branches, PRs (all states), issues, and commits by SHA, via the gh transport.

    ``commits`` maps a SHA to its files: a path maps to a contents-API response (a dict),
    or to a string, which is returned as gh's stderr with exit 1. A SHA in
    ``commit_errors`` fails with that stderr instead. Every endpoint called is recorded.
    """

    def __init__(self, branches=(), prs=(), issues_=(), commits=None, commit_errors=None):
        self.branches = [{"name": b} for b in branches]
        self.prs = list(prs)
        self.issues = list(issues_)
        self.commits = dict(commits or {})
        self.commit_errors = dict(commit_errors or {})
        self.empty = False
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = argv[1:]
        self.calls.append(args)
        if args[:2] == ["pr", "list"]:
            assert args[args.index("--state") + 1] == "all"
            assert "headRefOid" in args[args.index("--json") + 1].split(",")
            return self._ok(self.prs)
        assert args[0] == "api" and args[args.index("--method") + 1] == "GET", args
        endpoint = args[1]
        if m := re.fullmatch(rf"repos/{REPO}/commits/(\w+)", endpoint):
            if m[1] in self.commit_errors:
                return ProcessResult(argv, 1, "", self.commit_errors[m[1]])
            if m[1] in self.commits:
                return self._ok({"sha": m[1]})
            return ProcessResult(argv, 1, "", "gh: No commit found for SHA (HTTP 422)")
        if m := re.fullmatch(rf"repos/{REPO}/contents/(.+)\?ref=(\w+)", endpoint):
            found = self.commits.get(m[2], {}).get(m[1])
            if found is None:
                return ProcessResult(argv, 1, "", "gh: Not Found (HTTP 404)")
            if isinstance(found, str):
                return ProcessResult(argv, 1, "", found)
            return self._ok(found)
        if endpoint == f"repos/{REPO}/branches":
            if self.empty:
                return ProcessResult(argv, 1, "", "gh: This repository is empty. (HTTP 409)")
            return self._ok([self.branches])
        if endpoint == f"repos/{REPO}/issues?state=all&per_page=100":
            return self._ok([self.issues])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            for item in self.issues:
                if item["number"] == int(m[1]):
                    return self._ok(item)
            return ProcessResult(argv, 1, "", "gh: Not Found (HTTP 404)")
        raise AssertionError(f"unexpected call: {args}")

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")


def gh_issue(number, story_id, inc, state="open", labels=(), blocked="None"):
    return {"number": number, "state": state, "labels": [{"name": n} for n in labels],
            "body": build(StoryMarker(id=story_id, increment=inc))
            + f"\n## Dependencies\nBlocked by: {blocked}\n"}


class CollectRemoteTest(unittest.TestCase):
    def test_reads_branches_planning_prs_and_story_issues(self):
        fake = FakeGitHub(
            branches=["main", "factory/plan-002-more", "story/3-x"],
            prs=[{"number": 9, "state": "MERGED", "headRefOid": "a1",
                  "body": build(PlanningMarker(increment="001-initial")) + "\nSTORY-001"},
                 {"number": 10, "state": "OPEN", "headRefOid": "b2",
                  "body": build(PlanningMarker(increment="002-more"))},
                 {"number": 11, "state": "OPEN", "headRefOid": "c3", "body": "a story PR"}],
            issues_=[gh_issue(1, "STORY-001", "001-initial", "closed"),
                     gh_issue(2, "STORY-002", "001-initial", labels=["status:ready"],
                              blocked="#1"),
                     {"number": 3, "state": "open", "labels": [], "body": "not a story"}],
            commits={"a1": plan_files("001-initial", range(1, 3), range(1, 3)),
                     "b2": plan_files("002-more", range(3, 4))})
        remote = increments.collect_remote(Gh(transport=fake), REPO)
        self.assertEqual(remote.plan_branches, {"002-more"})
        self.assertEqual(remote.planning_prs, {"001-initial": ("MERGED",),
                                               "002-more": ("OPEN",)})
        self.assertEqual([(p.pr, p.increment, p.req_numbers, p.story_numbers, p.error)
                          for p in remote.plans],
                         [(9, "001-initial", {1, 2}, {1, 2}, None),
                          (10, "002-more", {3}, set(), None)])
        self.assertIn("\nSTORY-001", remote.plans[0].body)
        self.assertEqual(remote.open_numbers, {2})
        by_number = {i.number: i for i in remote.issues}
        self.assertEqual(sorted(by_number), [1, 2])
        self.assertEqual(by_number[2].labels, {"status:ready"})
        self.assertEqual(by_number[2].blocked_by, (1,))
        self.assertFalse(by_number[1].open)

    def test_empty_repository(self):
        fake = FakeGitHub()
        fake.empty = True
        self.assertEqual(increments.collect_remote(Gh(transport=fake), REPO), Remote())

    def test_blocked_by_numbers(self):
        self.assertEqual(issues.blocked_by_numbers("x\nBlocked by: #12, #14\ny"), (12, 14))
        self.assertEqual(issues.blocked_by_numbers("Blocked by: None"), ())
        self.assertEqual(issues.blocked_by_numbers("no such line"), ())


class ReadPlanFromGitHubTest(unittest.TestCase):
    """Decision D1 end to end: a Planning PR's records are read at its head commit."""

    HEAD = "d" * 40

    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 37), range(1, 18))
        self.merged_001 = {"number": 1, "state": "MERGED", "headRefOid": "a" * 40,
                           "body": build(PlanningMarker(increment="001-initial"))}
        self.story_issues = [gh_issue(n + 1, f"STORY-{n:03d}", "001-initial", "closed",
                                      labels=[LABEL]) for n in range(1, 18)]

    def abandoned(self, head=HEAD):
        return {"number": 40, "state": "CLOSED", "headRefOid": head,
                "body": build(PlanningMarker(increment="002-tags"))
                + "\n## Summary\nAdds REQ-037..REQ-039; STORY-025 comes later.\n"}

    def fake(self, branches, files=None, commit_errors=None, head=HEAD):
        commits = {"a" * 40: plan_files("001-initial", range(1, 37), range(1, 18))}
        if files is not None:
            commits[self.HEAD] = files
        return FakeGitHub(branches=branches, prs=[self.merged_001, self.abandoned(head)],
                          issues_=self.story_issues, commits=commits,
                          commit_errors=commit_errors)

    def run_assess(self, fake, slug="tags again"):
        return increments.assess_target(Gh(transport=fake), self.t.root, REPO, slug)

    def test_abandoned_plan_with_its_branch_still_listed(self):
        fake = self.fake(["main", "factory/plan-002-tags"],
                         plan_files("002-tags", range(37, 40), range(18, 20)))
        result = self.run_assess(fake)
        self.assertEqual((result.next_req, result.next_story), ("REQ-040", "STORY-020"))
        self.assertEqual(result.warnings,
                         ("STORY-025 is mentioned in Planning PR #40 but never allocated",))
        self.assertIn("has not passed Gate A", result.reasons[0])  # branch not deleted yet

    def test_abandoned_plan_after_its_source_branch_was_deleted(self):
        fake = self.fake(["main"], plan_files("002-tags", range(37, 40), range(18, 20)))
        remote = increments.collect_remote(Gh(transport=fake), REPO)
        self.assertEqual(remote.plan_branches, set())
        result = assess(scan_layout(self.t.root), remote, "tags again")
        self.assertEqual(result.reasons, ())  # abandoned: closed and branch deleted
        self.assertEqual(result.next_increment, "003-tags-again")
        self.assertEqual((result.next_req, result.next_story), ("REQ-040", "STORY-020"))
        endpoints = [" ".join(call) for call in fake.calls]
        self.assertFalse([e for e in endpoints if "plan-002-tags" in e], endpoints)
        self.assertIn(f"api repos/{REPO}/contents/docs/factory/increments/002-tags/"
                      f"05-stories.md?ref={self.HEAD} --method GET", endpoints)

    def test_readable_commit_without_record_files(self):
        # Abandoned before S02 and S05 wrote anything: no records, and no fallback.
        result = self.run_assess(self.fake(["main"], files={}))
        self.assertEqual((result.next_req, result.next_story), ("REQ-037", "STORY-018"))
        self.assertEqual([w.split()[0] for w in result.warnings], ["REQ-037", "REQ-039",
                                                                   "STORY-025"])

    def test_unreadable_records_fall_back_to_the_body(self):
        files = plan_files("002-tags", range(37, 40), range(18, 20))
        stories = "docs/factory/increments/002-tags/05-stories.md"
        no_base64 = f"{stories}: the contents API returned no base64 file content"
        undecodable = f"{stories}: its content could not be decoded"
        cases = [
            ("commit HTTP 404", dict(files=files,
                                     commit_errors={self.HEAD: "gh: Not Found (HTTP 404)"})),
            ("commit HTTP 422", dict(files=None)),  # the fake knows no such SHA
            ("no head commit", dict(files=files, head=None)),
            (no_base64, dict(files={**files, stories: {"type": "file", "encoding": "none",
                                                       "content": ""}})),  # too large
            (no_base64, dict(files={**files, stories: [{"type": "file", "name": "x"}]})),
            (undecodable, dict(files={**files, stories: {
                "type": "file", "encoding": "base64", "content": "!!!not base64"}})),
            (undecodable, dict(files={**files, stories: {
                "type": "file", "encoding": "base64",
                "content": base64.b64encode(b"\xff\xfe").decode()}})),  # not UTF-8
            (f"{stories}: HTTP 500", dict(files={**files,
                                                 stories: "gh: Server Error (HTTP 500)"})),
        ]
        for reason, kwargs in cases:
            with self.subTest(reason=reason):
                result = self.run_assess(self.fake(["main"], **kwargs))
                commit = "unknown commit" if "head" in kwargs else "ddddddd"
                self.assertEqual(result.warnings[-1], (
                    f"Planning PR #40: its records at {commit} could not be read "
                    f"({reason}); every ID in its body was counted instead"))
                # Only the body counts: REQ-037 and REQ-039 (a range is not expanded) and
                # STORY-025; the records' STORY-018 and STORY-019 are not seen.
                self.assertEqual((result.next_req, result.next_story),
                                 ("REQ-040", "STORY-026"))
                self.assertFalse([w for w in result.warnings if "never allocated" in w])

    def test_one_unreadable_plan_does_not_affect_the_others(self):
        result = self.run_assess(self.fake(["main"], files=None))
        self.assertEqual(sum("could not be read" in w for w in result.warnings), 1)
        self.assertIn("Planning PR #40", result.warnings[-1])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 3), range(1, 3))
        self.fake = FakeGitHub(
            prs=[{"number": 9, "state": "MERGED", "headRefOid": "a1",
                  "body": build(PlanningMarker(increment="001-initial"))}],
            issues_=[gh_issue(1, "STORY-001", "001-initial", "closed", labels=[LABEL]),
                     gh_issue(2, "STORY-002", "001-initial", labels=[LABEL, "status:ready"])],
            commits={"a1": plan_files("001-initial", range(1, 3), range(1, 3))})

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(self.t.root, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["increment", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_show(self):
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 0)
        self.assertIn(f"Target: {self.t.root} ({REPO})", out)
        self.assertIn("Current increment: 001-initial", out)
        self.assertIn("Next IDs: REQ-003, STORY-003", out)
        self.assertIn("open, unblocked stories: #2 (STORY-002)", out)

    def test_next_refused_exit_1(self):
        code, out, _ = self.run_cli("next", "--slug", "more")
        self.assertEqual(code, 1)
        self.assertIn("A new increment cannot be started yet:", out)
        self.assertIn("#2 (STORY-002)", out)

    def test_next_allowed_json(self):
        self.fake.issues[1]["state"] = "closed"
        code, out, err = self.run_cli("next", "--slug", "Due dates", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {
            "current": "001-initial", "increments": ["001-initial"], "can_start": True,
            "next_increment": "002-due-dates", "next_req": "REQ-003",
            "next_story": "STORY-003", "reasons": [], "warnings": []})
        self.assertIn("Target:", err)  # the banner goes to stderr with --json

    def test_next_needs_a_slug_after_the_first_increment(self):
        self.fake.issues[1]["state"] = "closed"
        code, _, err = self.run_cli("next")
        self.assertEqual(code, 1)
        self.assertIn("--slug is needed", err)

    def test_bad_slug(self):
        self.fake.issues[1]["state"] = "closed"
        code, _, err = self.run_cli("next", "--slug", "???")
        self.assertEqual(code, 1)
        self.assertIn("cannot make an increment slug", err)

    def test_show_reports_warnings(self):
        note = f"{INC}/001-initial/01-codebase-analysis.md"
        self.t.write(note, "Next free IDs: REQ-003, STORY-003.\n")
        self.fake.prs.append({"number": 12, "state": "CLOSED", "headRefOid": None,
                              "body": build(PlanningMarker(increment="002-x")) + "\nREQ-010"})
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 0)  # warnings never change the exit code
        self.assertIn("Next IDs: REQ-011, STORY-003", out)  # the fallback counts REQ-010
        self.assertEqual([line for line in out.splitlines() if line.startswith("Warning:")], [
            f"Warning: REQ-003 is mentioned in {note} but never allocated",
            f"Warning: STORY-003 is mentioned in {note} but never allocated",
            "Warning: Planning PR #12: its records at unknown commit could not be read "
            "(no head commit); every ID in its body was counted instead"])

    def test_show_json_has_warnings(self):
        note = f"{INC}/001-initial/01-codebase-analysis.md"
        self.t.write(note, "Next free IDs: REQ-003, STORY-003.\n")
        code, out, _ = self.run_cli("show", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["warnings"], [
            f"REQ-003 is mentioned in {note} but never allocated",
            f"STORY-003 is mentioned in {note} but never allocated"])

    def test_first_increment_on_a_new_project(self):
        empty = TargetDir(self)
        self.t = empty
        self.fake = FakeGitHub()
        code, out, _ = self.run_cli("next")
        self.assertEqual(code, 0)
        self.assertIn("Next increment: 001-initial", out)
        self.assertIn("Next IDs: REQ-001, STORY-001", out)


if __name__ == "__main__":
    unittest.main()
