"""T2.2: ``issues sync``: idempotent, dependencies translated, Gate A respected."""

import base64
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, issues, target, templates
from factory.errors import GhError
from factory.gh import Gh, ProcessResult
from factory.gh_fixtures import FakeGh
from factory.markers import PlanningMarker, StoryMarker, build, find, parse_all
from factory.stories import StoriesError, parse
from tests.test_stories import GOOD, STORY_3, with_story_3

REPO = "owner/app"
INC = "001-initial"
RELPATH = f"docs/factory/increments/{INC}/05-stories.md"
# STORY-003 first, although it depends on STORY-002 which is defined after it.
FORWARD = GOOD.replace("### STORY-001", STORY_3 + "\n### STORY-001", 1)
LABELS = [{"name": n, "color": "ededed", "description": ""}
          for n in ("factory:story", "status:ready", "status:done", "bug")]


class FakeGitHub:
    """In-memory GitHub: issues, labels, PRs and file contents, via the gh transport."""

    def __init__(self, stories=GOOD, merged_increments=(INC,), labels=LABELS):
        self.issues: list[dict] = []
        self.next_number = 1
        self.files = {("main", RELPATH): stories}
        self.merged_prs = [
            {"number": 90 + n, "body": build_planning(inc) + "\nPlanning"}
            for n, inc in enumerate(merged_increments)]
        self.labels = list(labels)
        self.creates = 0
        self.fail_on_create: int | None = None  # simulate a crash on the Nth create
        self.list_limit: int | None = None  # a stale list shows only the first N issues
        self.deleted: set[int] = set()  # numbers GitHub answers 410 Gone for

    def add_issue(self, body, title="human title", state="open", pull_request=False):
        item = {"number": self.next_number, "title": title, "body": body, "state": state,
                "labels": []}
        if pull_request:
            item["pull_request"] = {"url": "..."}
        self.next_number += 1
        self.issues.append(item)
        return item

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        assert timeout and timeout > 0
        args = argv[1:]
        if args[:2] == ["repo", "view"]:
            return self._ok({"defaultBranchRef": {"name": "main"}})
        if args[:2] == ["label", "list"]:
            return self._ok(self.labels)
        if args[:2] == ["pr", "list"]:
            assert args[args.index("--state") + 1] == "merged"
            return self._ok(self.merged_prs)
        assert args[0] == "api", args
        endpoint, method = args[1], args[args.index("--method") + 1]
        if endpoint == f"repos/{REPO}/issues?state=all&per_page=100":
            assert method == "GET" and "--paginate" in args
            listed = self.issues if self.list_limit is None else self.issues[:self.list_limit]
            return self._ok([[i for i in listed if i["number"] not in self.deleted]])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            assert method == "GET"
            number = int(m[1])
            if number in self.deleted:
                return ProcessResult(argv, 1, "", "gh: This issue was deleted (HTTP 410)")
            for item in self.issues:
                if item["number"] == number:
                    return self._ok(item)
            return ProcessResult(argv, 1, "", "gh: Not Found (HTTP 404)")
        if endpoint == f"repos/{REPO}/issues":
            assert method == "POST" and "--input" in args
            self.creates += 1
            if self.fail_on_create == self.creates:
                return ProcessResult(argv, 1, "", "HTTP 502: Bad Gateway")
            data = json.loads(input)
            item = self.add_issue(data["body"], title=data["title"])
            item["labels"] = [{"name": n} for n in data["labels"]]
            return self._ok(item)
        if m := re.fullmatch(rf"repos/{REPO}/contents/(.+)\?ref=(.+)", endpoint):
            text = self.files.get((m[2], m[1]))
            if text is None:
                return ProcessResult(argv, 1, "", "gh: Not Found (HTTP 404)")
            return self._ok({"type": "file",
                             "content": base64.b64encode(text.encode()).decode()})
        raise AssertionError(f"unexpected call: {args}")

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    def story_issues(self):
        return {find(i["body"], StoryMarker).id: i for i in self.issues
                if find(i["body"], StoryMarker)}


def build_planning(increment):
    return build(PlanningMarker(increment=increment))


class SyncTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.target = Path(tmp.name)
        self.write_local(GOOD)

    def write_local(self, text, increment=INC):
        path = self.target / "docs" / "factory" / "increments" / increment / "05-stories.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def sync(self, fake, **kwargs):
        return issues.sync(Gh(transport=fake), self.target, REPO, **kwargs)


class IdempotencyTest(SyncTestBase):
    def test_second_run_creates_nothing(self):
        fake = FakeGitHub(stories=with_story_3())
        first = self.sync(fake)
        self.assertEqual(first.created, ("STORY-001", "STORY-002", "STORY-003"))
        self.assertEqual(fake.creates, 3)

        second = self.sync(fake)
        self.assertEqual(second.created, ())
        self.assertEqual(fake.creates, 3, "the second run must not create anything")
        self.assertEqual(len(fake.issues), 3)
        self.assertIn("Done: 0 created, 3 already existed.", issues.render(second))

    def test_interrupted_run_finishes_without_duplicates(self):
        fake = FakeGitHub(stories=with_story_3())
        fake.fail_on_create = 2
        with self.assertRaisesRegex(GhError, "HTTP 502"):
            self.sync(fake)
        self.assertEqual(list(fake.story_issues()), ["STORY-001"])

        fake.fail_on_create = None
        result = self.sync(fake)
        self.assertEqual(result.created, ("STORY-002", "STORY-003"))
        by_id = fake.story_issues()
        self.assertEqual(sorted(by_id), ["STORY-001", "STORY-002", "STORY-003"])
        self.assertIn(f"Blocked by: #{by_id['STORY-001']['number']}",
                      by_id["STORY-002"]["body"])

    def test_second_run_right_after_the_first_sees_issues_the_list_lags_on(self):
        # Regression (seen in the sandbox): GitHub's issue list lagged behind, so a
        # second run a few seconds later did not see the new issues and duplicated them.
        fake = FakeGitHub(stories=with_story_3())
        fake.add_issue("an older, unrelated issue")
        self.sync(fake)
        fake.list_limit = 1  # the list still only shows the issue from before the run
        second = self.sync(fake)
        self.assertEqual(second.created, ())
        self.assertEqual(fake.creates, 3)
        self.assertEqual(sorted(second.numbers.values()), [2, 3, 4])

    def test_deleted_issue_numbers_are_skipped(self):
        fake = FakeGitHub()
        fake.add_issue("will be deleted")
        fake.add_issue(build(StoryMarker(id="STORY-001", increment=INC)))
        fake.deleted = {1}
        fake.list_limit = 0
        self.assertEqual(self.sync(fake).created, ("STORY-002",))

    def test_existing_issues_are_found_by_marker_not_title_or_label(self):
        fake = FakeGitHub()
        body = build(StoryMarker(id="STORY-001", increment=INC)) + "\nedited by a human"
        fake.add_issue(body, title="Renamed by a human")  # no labels at all
        fake.add_issue("unrelated issue")
        fake.add_issue(build(StoryMarker(id="STORY-002", increment=INC)), pull_request=True)
        result = self.sync(fake)
        self.assertEqual(result.created, ("STORY-002",))  # a PR is not a story issue
        self.assertIn("Blocked by: #1", fake.story_issues()["STORY-002"]["body"])

    def test_closed_issue_counts_as_existing(self):
        fake = FakeGitHub()
        fake.add_issue(build(StoryMarker(id="STORY-001", increment=INC)), state="closed")
        result = self.sync(fake)
        self.assertEqual(result.created, ("STORY-002",))
        self.assertIn("exists   #1 (closed)", issues.render(result))

    def test_duplicate_markers_refuse_to_act(self):
        fake = FakeGitHub()
        for _ in range(2):
            fake.add_issue(build(StoryMarker(id="STORY-001", increment=INC)))
        fake.add_issue(build(StoryMarker(id="STORY-001", increment=INC)), state="closed")
        with self.assertRaisesRegex(issues.SyncError, "STORY-001: #1, #2, #3.*remove it"):
            self.sync(fake)
        self.assertEqual(fake.creates, 0)

    def test_duplicate_dependency_refuses_to_act(self):
        text = with_story_3(**{"Blocked by: STORY-002": "Blocked by: STORY-000"})
        fake = FakeGitHub(stories=text)
        for _ in range(2):
            fake.add_issue(build(StoryMarker(id="STORY-000", increment="000-older")))
        with self.assertRaisesRegex(issues.SyncError, "STORY-000: #1, #2"):
            self.sync(fake)
        self.assertEqual(fake.creates, 0)

    def test_duplicates_of_unrelated_stories_do_not_block(self):
        # e.g. left over from an earlier increment; the state engine reports them.
        fake = FakeGitHub()
        for _ in range(2):
            fake.add_issue(build(StoryMarker(id="STORY-900", increment="000-older")))
        self.assertEqual(self.sync(fake).created, ("STORY-001", "STORY-002"))


class DependencyTest(SyncTestBase):
    def test_story_ids_become_issue_numbers(self):
        fake = FakeGitHub(stories=with_story_3())
        self.sync(fake)
        by_id = fake.story_issues()
        n1, n2 = by_id["STORY-001"]["number"], by_id["STORY-002"]["number"]
        self.assertIn("Blocked by: None", by_id["STORY-001"]["body"])
        self.assertIn(f"Blocked by: #{n1}\n", by_id["STORY-002"]["body"])
        self.assertIn(f"Blocked by: #{n2}\n", by_id["STORY-003"]["body"])

    def test_forward_references_are_created_dependencies_first(self):
        fake = FakeGitHub(stories=FORWARD)
        result = self.sync(fake)
        self.assertEqual(result.created, ("STORY-001", "STORY-002", "STORY-003"))
        self.assertEqual([s.id for s in parse(FORWARD)], ["STORY-003", "STORY-001", "STORY-002"])

    def test_dependency_on_an_earlier_increment(self):
        text = with_story_3(**{"Blocked by: STORY-002": "Blocked by: STORY-000"})
        fake = FakeGitHub(stories=text)
        fake.add_issue(build(StoryMarker(id="STORY-000", increment="000-older")), state="closed")
        self.sync(fake)
        self.assertIn("Blocked by: #1\n", fake.story_issues()["STORY-003"]["body"])

    def test_unknown_dependency_names_story_and_rule(self):
        text = with_story_3(**{"Blocked by: STORY-002": "Blocked by: STORY-404"})
        fake = FakeGitHub(stories=text)
        with self.assertRaises(StoriesError) as ctx:
            self.sync(fake)
        self.assertIn("STORY-003", str(ctx.exception))
        self.assertIn("[unknown-dependency]", str(ctx.exception))
        self.assertEqual(fake.creates, 0)

    def test_story_id_reused_from_another_increment(self):
        fake = FakeGitHub()
        fake.add_issue(build(StoryMarker(id="STORY-002", increment="000-older")))
        with self.assertRaises(StoriesError) as ctx:
            self.sync(fake)
        self.assertIn("STORY-002", str(ctx.exception))
        self.assertIn("[id-reused]", str(ctx.exception))
        self.assertEqual(fake.creates, 0)


class IssueContentTest(SyncTestBase):
    def test_issue_follows_the_story_template(self):
        fake = FakeGitHub(stories=with_story_3())
        self.sync(fake)
        issue = fake.story_issues()["STORY-002"]
        body = issue["body"]
        self.assertEqual(issue["title"], "STORY-002: Add tasks")
        self.assertEqual({label["name"] for label in issue["labels"]},
                         {"factory:story", "status:ready"})
        self.assertEqual(parse_all(body), [StoryMarker(id="STORY-002", increment=INC)])
        self.assertTrue(body.startswith("<!-- factory:story id=STORY-002 increment=001-initial"))
        headings = [line[3:] for line in body.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, [line[3:] for line in templates.load("story.md").splitlines()
                                    if line.startswith("## ")])
        self.assertIn("Milestone M2", body)
        self.assertIn("## Traces to\nREQ-002, REQ-003\n", body)
        self.assertIn("- [ ] AC1: Given the task list, when I add a task, then it appears "
                      "in the list.\n- [ ] AC2: Given an empty title", body)
        self.assertIn("## Out of scope\n- Editing tasks\n", body)
        # Values are inserted once, never expanded again.
        self.assertIn("key: {{value}}", body)

    def test_labels_must_exist_first(self):
        fake = FakeGitHub(labels=[{"name": "factory:story", "color": "x", "description": ""}])
        with self.assertRaisesRegex(issues.SyncError, "status:ready.*labels ensure"):
            self.sync(fake)
        self.assertEqual(fake.creates, 0)

    def test_oversized_body_fails_before_anything_is_created(self):
        huge = with_story_3(**{"#### Technical notes\nNone":
                               "#### Technical notes\n" + "x" * 70000})
        fake = FakeGitHub(stories=huge)
        with self.assertRaisesRegex(issues.SyncError, "STORY-003.*65536"):
            self.sync(fake)
        self.assertEqual(fake.creates, 0)


class GateATest(SyncTestBase):
    def test_real_run_refuses_before_the_planning_pr_is_merged(self):
        fake = FakeGitHub(merged_increments=("000-older",))
        with self.assertRaisesRegex(issues.SyncError, "not merged.*Gate A"):
            self.sync(fake)
        self.assertEqual(fake.creates, 0)

    def test_real_run_reads_the_approved_file_on_the_default_branch(self):
        # The local copy has an extra story that was never approved.
        self.write_local(with_story_3())
        fake = FakeGitHub(stories=GOOD)
        result = self.sync(fake)
        self.assertEqual(result.created, ("STORY-001", "STORY-002"))
        self.assertEqual(result.plan.source, f"{RELPATH} on main")

    def test_parse_error_creates_nothing(self):
        fake = FakeGitHub(stories=with_story_3(**{"Milestone: M2": "Milestone: soon"}))
        with self.assertRaises(StoriesError) as ctx:
            self.sync(fake)
        self.assertIn("STORY-003", str(ctx.exception))
        self.assertIn("[milestone]", str(ctx.exception))
        self.assertEqual(fake.creates, 0)

    def test_missing_file_on_default_branch(self):
        fake = FakeGitHub()
        fake.files.clear()
        with self.assertRaisesRegex(issues.SyncError, "is not on 'main'"):
            self.sync(fake)


class DryRunTest(SyncTestBase):
    def test_dry_run_changes_nothing_and_needs_no_gate_a(self):
        self.write_local(with_story_3())
        fake = FakeGitHub(merged_increments=())
        fake.add_issue(build(StoryMarker(id="STORY-001", increment=INC)))
        result = self.sync(fake, dry_run=True)
        self.assertEqual(fake.creates, 0)
        self.assertEqual(result.created, ())
        self.assertEqual(issues.render(result), "\n".join([
            f"issues sync --dry-run: increment {INC}, 3 stories, from {RELPATH} (local)",
            "  exists   #1       STORY-001: Walking skeleton  [blocked by: None]",
            "  create            STORY-002: Add tasks  [blocked by: #1]",
            "  create            STORY-003: Delete tasks  [blocked by: STORY-002 (new)]",
            "Plan: 2 to create, 1 already exist. Dry run: nothing was changed.",
        ]))

    def test_dry_run_plan_is_exactly_what_a_real_run_does(self):
        self.write_local(FORWARD)
        fake = FakeGitHub(stories=FORWARD)
        planned = [line.split()[1:] for line in
                   issues.render(self.sync(fake, dry_run=True)).splitlines()[1:-1]]
        real = self.sync(fake)
        done = [line.split()[2:] for line in issues.render(real).splitlines()[1:-1]]
        self.assertEqual([p[0] for p in planned], [d[0] for d in done])  # same order
        self.assertEqual(list(real.created), [p[0].rstrip(":") for p in planned])

    def test_default_increment_is_the_highest_local_folder(self):
        self.write_local(GOOD.replace("STORY-00", "STORY-10"), increment="002-more")
        self.write_local(GOOD, increment="010-later")
        (self.target / "docs/factory/increments/not-an-increment").mkdir()
        result = self.sync(FakeGitHub(merged_increments=()), dry_run=True)
        self.assertEqual(result.plan.increment, "010-later")

    def test_dry_run_reports_contract_errors(self):
        self.write_local(with_story_3(**{"- AC1: Given": "AC1 Given"}))
        with self.assertRaises(StoriesError) as ctx:
            self.sync(FakeGitHub(), dry_run=True)
        self.assertIn("STORY-003", str(ctx.exception))
        self.assertIn("[acceptance-criteria]", str(ctx.exception))

    def test_invalid_increment(self):
        with self.assertRaisesRegex(issues.SyncError, "invalid increment"):
            self.sync(FakeGitHub(), increment="../x", dry_run=True)

    def test_dry_run_gh_calls_are_read_only(self):
        # Replays a cassette: any call not listed (e.g. a POST) fails the test.
        labels = json.dumps(LABELS)
        existing = json.dumps([[{"number": 5, "state": "open", "body": build(
            StoryMarker(id="STORY-001", increment=INC))}]])
        gh = FakeGh([
            {"args": ["label", "list", "--repo", REPO, "--limit", "1000", "--json",
                      "name,color,description"], "input": None, "returncode": 0,
             "stdout": labels, "stderr": ""},
            {"args": ["api", f"repos/{REPO}/issues?state=all&per_page=100", "--method", "GET",
                      "--paginate", "--slurp"], "input": None, "returncode": 0,
             "stdout": existing, "stderr": ""},
            {"args": ["api", f"repos/{REPO}/issues/6", "--method", "GET"], "input": None,
             "returncode": 1, "stdout": "", "stderr": "gh: Not Found (HTTP 404)"},
        ])
        result = issues.sync(gh, self.target, REPO, dry_run=True)
        gh.assert_all_used()
        self.assertEqual(result.numbers, {"STORY-001": 5})
        self.assertIn("create            STORY-002: Add tasks  [blocked by: #5]",
                      issues.render(result))


class CliTest(SyncTestBase):
    def run_cli(self, fake, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(self.target, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["issues", "sync", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_then_real_run_then_again(self):
        fake = FakeGitHub()
        code, out, _ = self.run_cli(fake, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], f"Target: {self.target} ({REPO})")
        self.assertIn("Plan: 2 to create, 0 already exist.", out)
        self.assertEqual(fake.creates, 0)

        code, out, _ = self.run_cli(fake)
        self.assertEqual(code, 0)
        self.assertIn("created  #1       STORY-001: Walking skeleton", out)
        self.assertIn("Done: 2 created, 0 already existed.", out)

        code, out, _ = self.run_cli(fake, "--increment", INC)
        self.assertEqual(code, 0)
        self.assertIn("Done: 0 created, 2 already existed.", out)
        self.assertEqual(fake.creates, 2)

    def test_contract_error_exit_code_and_message(self):
        self.write_local(with_story_3(**{"REQ-004": "None"}))
        code, _, err = self.run_cli(FakeGitHub(), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("error: docs/factory/increments/001-initial/05-stories.md (local) does "
                      "not meet the story contract", err)
        self.assertIn("STORY-003 (line", err)
        self.assertIn("[traces-to]", err)


if __name__ == "__main__":
    unittest.main()
