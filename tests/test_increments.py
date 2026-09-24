"""T2.3: increment handling: current/next increment, global IDs, one at a time."""

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
from factory.increments import Layout, Remote, StoryIssue, assess, scan_layout, slugify
from factory.markers import PlanningMarker, StoryMarker, build
from factory.stories import parse

REPO = "owner/app"


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
        t.write("docs/factory/increments/not-an-increment/x.md", "REQ-500")  # still an ID
        t.write("docs/other/notes.md", "REQ-900 STORY-900")  # outside docs/factory: ignored
        layout = scan_layout(t.root)
        self.assertEqual(layout.increments, {"001-initial"})
        self.assertEqual(max(layout.req_numbers), 500)
        self.assertEqual(max(layout.story_numbers), 5)
        self.assertEqual(layout.stories["001-initial"],
                         {f"STORY-{n:03d}" for n in range(1, 6)})

    def test_ids_with_more_than_three_digits(self):
        t = TargetDir(self)
        t.increment("001-initial", range(998, 1001), range(999, 1001))
        result = assess(scan_layout(t.root), merged("001-initial"))
        self.assertEqual((result.next_req, result.next_story), ("REQ-1001", "STORY-1001"))

    def test_word_boundaries(self):
        t = TargetDir(self)
        t.write("docs/factory/x.md", "PREREQ-900 XSTORY-900 REQ-12 REQ-004a REQ-007.")
        layout = scan_layout(t.root)
        self.assertEqual(layout.req_numbers, {7})
        self.assertEqual(layout.story_numbers, set())


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
        remote = Remote(issues=(issue(7, "STORY-9251315", inc="900-integration", open=False),))
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

    def test_ids_from_issue_markers_and_planning_pr_bodies_count(self):
        t = TargetDir(self)
        t.increment("001-initial", range(1, 3), range(1, 3))
        remote = Remote(
            planning_prs={"001-initial": ("MERGED",), "002-dropped": ("CLOSED",)},
            planning_bodies=("| STORY-040 | x | M1 | None | REQ-030 |",),
            issues=(issue(1, "STORY-001", open=False), issue(2, "STORY-002", open=False),
                    issue(3, "STORY-055", inc="000-older", open=False)))
        result = assess(scan_layout(t.root), remote, "next")
        self.assertEqual((result.next_req, result.next_story), ("REQ-031", "STORY-056"))

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


class FakeGitHub:
    """Branches, PRs (all states) and issues, via the gh transport interface."""

    def __init__(self, branches=(), prs=(), issues_=()):
        self.branches = [{"name": b} for b in branches]
        self.prs = list(prs)
        self.issues = list(issues_)
        self.empty = False

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = argv[1:]
        if args[:2] == ["pr", "list"]:
            assert args[args.index("--state") + 1] == "all"
            return self._ok(self.prs)
        assert args[0] == "api" and args[args.index("--method") + 1] == "GET", args
        endpoint = args[1]
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
            prs=[{"number": 9, "state": "MERGED",
                  "body": build(PlanningMarker(increment="001-initial")) + "\nSTORY-001"},
                 {"number": 10, "state": "OPEN",
                  "body": build(PlanningMarker(increment="002-more"))},
                 {"number": 11, "state": "OPEN", "body": "a story PR"}],
            issues_=[gh_issue(1, "STORY-001", "001-initial", "closed"),
                     gh_issue(2, "STORY-002", "001-initial", labels=["status:ready"],
                              blocked="#1"),
                     {"number": 3, "state": "open", "labels": [], "body": "not a story"}])
        remote = increments.collect_remote(Gh(transport=fake), REPO)
        self.assertEqual(remote.plan_branches, {"002-more"})
        self.assertEqual(remote.planning_prs, {"001-initial": ("MERGED",),
                                               "002-more": ("OPEN",)})
        self.assertEqual(len(remote.planning_bodies), 2)
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


class CliTest(unittest.TestCase):
    def setUp(self):
        self.t = TargetDir(self)
        self.t.increment("001-initial", range(1, 3), range(1, 3))
        self.fake = FakeGitHub(
            prs=[{"number": 9, "state": "MERGED",
                  "body": build(PlanningMarker(increment="001-initial"))}],
            issues_=[gh_issue(1, "STORY-001", "001-initial", "closed"),
                     gh_issue(2, "STORY-002", "001-initial", labels=["status:ready"])])

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
            "next_story": "STORY-003", "reasons": []})
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
