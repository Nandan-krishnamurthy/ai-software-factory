"""T4.3: ``factory.py closeout``, the code-level gate of station S12.

Close-out runs only after a merge that the human made (D5); it never merges (D1) and
never picks a story (D2). ``status:done`` is set last, after the issue is closed.
"""

import contextlib
import io
import json
import re
import unittest
from unittest import mock

from factory import cli, closeout, target
from factory.gh import Gh, ProcessResult
from factory.markers import PrMarker, StoryMarker, build
from factory.pick import parse_issues

REPO = "owner/app"
MERGED_AT = "2026-09-25T11:41:18Z"


def story_issue(number, n, *, state="open", labels=("factory:story", "status:ready"),
                blocked_by="None"):
    body = (build(StoryMarker(f"STORY-{n:03d}", "001-initial"))
            + f"\n**STORY-{n:03d}** · Increment `001-initial` · Milestone M1\n\n"
            + f"## Dependencies\nBlocked by: {blocked_by}\n")
    return {"number": number, "title": f"STORY-{n:03d}: story {n}", "state": state,
            "labels": [{"name": x} for x in labels], "body": body}


def story_pr(number, n, *, merged=True, head="story/2-x", head_sha="a" * 40):
    return {"number": number, "state": "MERGED" if merged else "CLOSED",
            "body": build(PrMarker(f"STORY-{n:03d}")) + f"\nCloses #{number}",
            "headRefName": head, "headRefOid": head_sha,
            "mergeCommit": {"oid": "b" * 40} if merged else None,
            "mergedAt": MERGED_AT if merged else None, "url": f"https://x/pull/{number}"}


class FakeGitHub:
    """Issues, merged PRs and labels, served through the gh transport interface."""

    def __init__(self, issues, prs):
        self.issues = {i["number"]: i for i in issues}
        self.prs = prs
        self.writes: list[tuple[str, str]] = []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = list(argv[1:])
        if args[:2] == ["pr", "list"]:
            assert args[args.index("--state") + 1] == "merged"
            return self.ok([p for p in self.prs if p["mergedAt"]])
        assert args[0] == "api", args
        endpoint, method = args[1], args[args.index("--method") + 1]
        if endpoint == f"repos/{REPO}/issues?state=all&per_page=100":
            return self.ok([list(self.issues.values())])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            issue = self.issues.get(int(m[1]))
            if issue is None:
                return ProcessResult(list(argv), 1, "", "gh: Not Found (HTTP 404)")
            if method == "PATCH":
                self.writes.append(("PATCH", endpoint))
                issue["state"] = json.loads(input)["state"]
            return self.ok(issue)
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/labels(?:/(.+))?", endpoint):
            issue = self.issues[int(m[1])]
            self.writes.append((method, endpoint))
            if method == "POST":
                issue["labels"] += [{"name": x} for x in json.loads(input)["labels"]]
            else:
                name = m[2].replace("%3A", ":")
                issue["labels"] = [x for x in issue["labels"] if x["name"] != name]
            return self.ok(issue["labels"])
        raise AssertionError(f"unexpected call {args}")

    @staticmethod
    def ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    def labels(self, number):
        return {x["name"] for x in self.issues[number]["labels"]}


def repo_after_merge(issue_state="closed"):
    """#2 (STORY-001) merged via PR #14; #3 waits only for #2; #4 also waits for #3."""
    return FakeGitHub(
        [story_issue(2, 1, state=issue_state, labels=("factory:story", "status:in-review")),
         story_issue(3, 2, blocked_by="#2"),
         story_issue(4, 3, blocked_by="#2, #3")],
        [story_pr(14, 1)])


class PureTest(unittest.TestCase):
    def test_merged_pr_is_the_newest_merged_pr_of_the_story(self):
        prs = [story_pr(14, 1), story_pr(20, 1), story_pr(21, 1, merged=False),
               story_pr(22, 2), dict(story_pr(23, 1), body="no marker")]
        self.assertEqual(closeout.merged_pr("STORY-001", prs)["number"], 20)
        self.assertIsNone(closeout.merged_pr("STORY-009", prs))

    def test_newly_unblocked(self):
        stories, is_open = parse_issues([
            story_issue(2, 1, labels=("factory:story", "status:in-review")),
            story_issue(3, 2, blocked_by="#2"),                  # unblocked now
            story_issue(4, 3, blocked_by="#2, #3"),              # #3 is still open
            story_issue(5, 4, blocked_by="#2, #99"),             # #99 unknown: counts as open
            story_issue(6, 5, blocked_by="#2",
                        labels=("factory:story", "status:ready", "factory:needs-human")),
            story_issue(7, 6),                                   # never waited for #2
            story_issue(8, 7, blocked_by="#2", state="closed"),
        ])
        self.assertEqual([s.number for s in closeout.newly_unblocked(2, stories, is_open)],
                         [3])

    def test_plan_refuses_without_a_merge(self):
        issue = story_issue(2, 1)
        cases = [
            (dict(issue, pull_request={}), [story_pr(14, 1)], "is a pull request"),
            (dict(issue, body="no marker"), [story_pr(14, 1)], "not a factory story issue"),
            (issue, [story_pr(14, 1, merged=False), story_pr(15, 2)], "no merged PR for STORY-001"),
        ]
        for data, prs, message in cases:
            with self.subTest(message):
                with self.assertRaises(closeout.CloseoutError) as ctx:
                    closeout.plan(2, data, prs, [issue])
                self.assertIn(message, str(ctx.exception))


class GitHubTest(unittest.TestCase):
    def test_inspect_reports_and_changes_nothing(self):
        fake = repo_after_merge()
        result = closeout.inspect(Gh(transport=fake), REPO, 2)
        self.assertEqual(fake.writes, [])
        self.assertEqual(result.to_dict(), {
            "issue": 2, "story": "STORY-001", "issue_open": False, "done": False, "pr": 14,
            "pr_url": "https://x/pull/14", "branch": "story/2-x", "head_sha": "a" * 40,
            "merge_sha": "b" * 40, "merged_at": MERGED_AT,
            "unblocked": [{"number": 3, "story": "STORY-002", "title": "STORY-002: story 2"}]})

    def test_finish_closes_the_issue_first_and_sets_done_last(self):
        fake = repo_after_merge(issue_state="open")  # the PR had no "Closes #2"
        _, changes = closeout.finish(Gh(transport=fake), REPO, 2)
        self.assertEqual(changes, ["closed", "+status:done", "-status:in-review"])
        self.assertEqual(fake.writes[0], ("PATCH", f"repos/{REPO}/issues/2"))
        self.assertEqual(fake.issues[2]["state"], "closed")
        self.assertEqual(fake.labels(2), {"factory:story", "status:done"})

    def test_finish_after_the_merge_closed_the_issue(self):
        fake = repo_after_merge()
        _, changes = closeout.finish(Gh(transport=fake), REPO, 2)
        self.assertEqual(changes, ["+status:done", "-status:in-review"])
        self.assertNotIn(("PATCH", f"repos/{REPO}/issues/2"), fake.writes)

    def test_finish_twice_changes_nothing_the_second_time(self):
        fake = repo_after_merge(issue_state="open")
        closeout.finish(Gh(transport=fake), REPO, 2)
        fake.writes.clear()
        result, changes = closeout.finish(Gh(transport=fake), REPO, 2)
        self.assertEqual((changes, fake.writes, result.done), ([], [], True))

    def test_finish_without_a_merge_writes_nothing(self):
        fake = repo_after_merge(issue_state="open")
        fake.prs = [story_pr(14, 1, merged=False)]  # closed without merging
        with self.assertRaises(closeout.CloseoutError):
            closeout.finish(Gh(transport=fake), REPO, 2)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.labels(2), {"factory:story", "status:in-review"})


class CliTest(unittest.TestCase):
    def run_cli(self, fake, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target", lambda: target.Target(None, REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["closeout", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_json_then_finish(self):
        fake = repo_after_merge()
        code, out, _ = self.run_cli(fake, "--issue", "2", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out[out.index("{"):])["unblocked"][0]["number"], 3)
        self.assertEqual(fake.writes, [])
        code, out, _ = self.run_cli(fake, "--issue", "2", "--finish")
        self.assertEqual(code, 0)
        self.assertIn("now unblocked: #3 (STORY-002)", out)
        self.assertIn("#2: +status:done, -status:in-review", out)

    def test_refusal_is_reported(self):
        code, _, err = self.run_cli(repo_after_merge(), "--issue", "3", "--finish")
        self.assertEqual(code, 1)
        self.assertIn("no merged PR for STORY-002 (#3)", err)


if __name__ == "__main__":
    unittest.main()
