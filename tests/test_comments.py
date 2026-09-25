"""T1.5: `factory.py comment` — markers on every comment; exactly one checkpoint."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from factory import cli, target
from factory.comments import (
    MAX_BODY,
    CommentError,
    check_target_kind,
    find_checkpoint,
    post_reply,
    upsert_checkpoint,
)
from factory.gh import Gh, ProcessResult
from factory.gh_fixtures import FakeGh
from factory.git import Git
from factory.markers import (
    CheckpointMarker,
    ReplyMarker,
    build,
    find,
    has_factory_marker,
    parse_all,
)

REPO = "owner/app"
SHA = "a" * 40
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


class FakeGitHub:
    """In-memory GitHub issue-comments API, served through the gh transport interface."""

    def __init__(self, prs=()):
        self.comments: dict[int, list[dict]] = {}
        self.prs = set(prs)
        self.next_id = 1000
        self.writes: list[tuple[str, str]] = []

    def add_human_comment(self, number, body):
        return self._create(number, body)

    def _create(self, number, body):
        self.next_id += 1
        comment = {"id": self.next_id, "body": body,
                   "html_url": f"https://github.com/{REPO}/issues/{number}#c{self.next_id}"}
        self.comments.setdefault(number, []).append(comment)
        return comment

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        assert timeout and timeout > 0
        args = argv[1:]
        if args[:2] == ["pr", "view"]:  # read by `comment --to` to check the id
            number = int(args[2])
            return self._ok({"number": number, "state": "OPEN", "headRefName": "story/7-x",
                             "commits": [], "reviews": [], "comments": [
                                 {"id": str(c["id"]), "author": {"login": "me"},
                                  "body": c["body"], "createdAt": "2026-09-24T10:00:00Z"}
                                 for c in self.comments.get(number, [])]})
        assert args[0] == "api", args
        if re.fullmatch(rf"repos/{REPO}/pulls/\d+/comments", args[1]):
            return self._ok([[]])
        endpoint, method = args[1], args[args.index("--method") + 1]
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            number = int(m[1])
            item = {"number": number}
            if number in self.prs:
                item["pull_request"] = {"url": "..."}
            return self._ok(item)
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/comments", endpoint):
            number = int(m[1])
            if method == "GET":
                assert "--paginate" in args
                return self._ok([list(self.comments.get(number, []))])
            assert method == "POST" and "--input" in args
            self.writes.append(("POST", endpoint))
            return self._ok(self._create(number, json.loads(input)["body"]))
        if m := re.fullmatch(rf"repos/{REPO}/issues/comments/(\d+)", endpoint):
            assert method == "PATCH" and "--input" in args
            self.writes.append(("PATCH", endpoint))
            for comments in self.comments.values():
                for comment in comments:
                    if comment["id"] == int(m[1]):
                        comment["body"] = json.loads(input)["body"]
                        return self._ok(comment)
            return ProcessResult(list(argv), 1, "", "gh: Not Found (HTTP 404)")
        raise AssertionError(f"unexpected call: {args}")

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    def checkpoint_comments(self, number):
        return [c for c in self.comments.get(number, [])
                if find(c["body"], CheckpointMarker) is not None]


def checkpoint(gh, number=7, **overrides):
    kwargs = dict(station="S08", next_station="S09", branch="story/7-x", sha=SHA, now=NOW)
    kwargs.update(overrides)
    return upsert_checkpoint(gh, REPO, number, **kwargs)


class ReplyTest(unittest.TestCase):
    def test_reply_exact_request_with_fakegh(self):
        expected_body = "<!-- factory:reply -->\nAddressed: renamed `x` to `y`."
        gh = FakeGh([{
            "args": ["api", f"repos/{REPO}/issues/7/comments", "--method", "POST",
                     "--input", "-"],
            "input": json.dumps({"body": expected_body}),
            "returncode": 0, "stderr": "",
            "stdout": json.dumps({"id": 1, "html_url": "https://x/1", "body": expected_body}),
        }])
        posted = post_reply(gh, REPO, 7, "  Addressed: renamed `x` to `y`.\n")
        gh.assert_all_used()
        self.assertEqual((posted.action, posted.body), ("created", expected_body))

    def test_reply_marker_is_first_line_and_parses(self):
        fake = FakeGitHub()
        posted = post_reply(Gh(transport=fake), REPO, 7, "Line 1\n\nLine 2 with ünïcode ✓")
        first_line = posted.body.splitlines()[0]
        self.assertEqual(first_line, build(ReplyMarker()))
        self.assertEqual(parse_all(posted.body), [ReplyMarker()])
        self.assertIn("ünïcode ✓", posted.body)

    def test_empty_reply_refused(self):
        fake = FakeGitHub()
        with self.assertRaises(CommentError):
            post_reply(Gh(transport=fake), REPO, 7, "  \n ")
        self.assertEqual(fake.writes, [])


class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.gh = Gh(transport=self.fake)

    def test_twice_leaves_exactly_one_checkpoint_comment(self):
        """AC: running the checkpoint command twice leaves exactly one checkpoint."""
        first = checkpoint(self.gh, station="S08", next_station="S09")
        second = checkpoint(self.gh, station="S09", next_station="S10")
        self.assertEqual((first.action, second.action), ("created", "updated"))
        self.assertEqual(first.id, second.id)                       # edited in place
        cps = self.fake.checkpoint_comments(7)
        self.assertEqual(len(cps), 1)
        marker = find(cps[0]["body"], CheckpointMarker)
        self.assertEqual((marker.station, marker.next), ("S09", "S10"))
        self.assertEqual(self.fake.writes, [
            ("POST", f"repos/{REPO}/issues/7/comments"),
            ("PATCH", f"repos/{REPO}/issues/comments/{first.id}"),
        ])

    def test_many_runs_mixed_with_replies_and_human_comments(self):
        self.fake.add_human_comment(7, "Looks good so far.")
        for station, nxt in (("S07", "S08"), ("S08", "S09"), ("S09", "S10"), ("S10", "S11")):
            checkpoint(self.gh, station=station, next_station=nxt)
            post_reply(self.gh, REPO, 7, f"note after {station}")
        self.assertEqual(len(self.fake.checkpoint_comments(7)), 1)
        self.assertEqual(len(self.fake.comments[7]), 1 + 1 + 4)  # human + checkpoint + 4

    def test_every_factory_comment_carries_a_marker(self):
        """AC: every comment posted has a marker (only the human's does not)."""
        human = self.fake.add_human_comment(7, "please /changes something")
        checkpoint(self.gh)
        post_reply(self.gh, REPO, 7, "done")
        checkpoint(self.gh, station="S09", next_station="S10")
        post_reply(self.gh, REPO, 7, "done again")
        for comment in self.fake.comments[7]:
            with self.subTest(body=comment["body"][:40]):
                if comment["id"] == human["id"]:
                    self.assertFalse(has_factory_marker(comment["body"]))
                else:
                    self.assertTrue(has_factory_marker(comment["body"]))
                    self.assertTrue(comment["body"].startswith("<!-- factory:"))
                    self.assertEqual(len(parse_all(comment["body"])), 1)

    def test_counters_carry_over_unless_given(self):
        checkpoint(self.gh, fix_attempts=2, review_round=1)
        checkpoint(self.gh, station="S09", next_station="S10")        # not given
        marker = find(self.fake.checkpoint_comments(7)[0]["body"], CheckpointMarker)
        self.assertEqual((marker.fix_attempts, marker.review_round), (2, 1))
        checkpoint(self.gh, station="S10", next_station="S11", fix_attempts=0)
        marker = find(self.fake.checkpoint_comments(7)[0]["body"], CheckpointMarker)
        self.assertEqual((marker.fix_attempts, marker.review_round), (0, 1))

    def test_human_readable_line_and_note(self):
        posted = checkpoint(self.gh, note="Tests: 12 passed.")
        lines = posted.body.splitlines()
        self.assertTrue(lines[0].startswith("<!-- factory:checkpoint {"))
        self.assertEqual(lines[1], "**Factory checkpoint:** S08 complete. Next: S09. "
                                   "Branch: `story/7-x` @ `aaaaaaa`.")
        self.assertIn("Tests: 12 passed.", posted.body)
        self.assertEqual(find(posted.body, CheckpointMarker).ts, "2026-09-24T10:00:00+00:00")

    def test_quoted_checkpoint_in_a_human_comment_is_not_hijacked(self):
        quoted = "I saw this odd text:\n" + build(CheckpointMarker(
            station="S11", next="GATE_B", branch="evil", sha=SHA, fix_attempts=0,
            review_round=0, ts="2026-01-01T00:00:00+00:00"))
        human = self.fake.add_human_comment(7, quoted)
        posted = checkpoint(self.gh)
        self.assertEqual(posted.action, "created")
        self.assertNotEqual(posted.id, human["id"])
        self.assertEqual(self.fake.comments[7][0]["body"], quoted)  # untouched

    def test_invalid_checkpoint_is_refused_before_posting(self):
        for bad in (dict(station="S9"), dict(next_station="DONE"), dict(sha="zzz"),
                    dict(branch=" "), dict(fix_attempts=-1)):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(CommentError, "invalid checkpoint"):
                    checkpoint(self.gh, **bad)
        self.assertEqual(self.fake.writes, [])

    def test_find_checkpoint_prefers_the_oldest(self):
        cp1 = build(CheckpointMarker("S08", "S09", "b", SHA, 0, 0, "2026-01-01T00:00:00"))
        cp2 = build(CheckpointMarker("S09", "S10", "b", SHA, 0, 0, "2026-01-02T00:00:00"))
        found = find_checkpoint([{"id": 1, "body": cp1}, {"id": 2, "body": cp2}])
        self.assertEqual(found[0]["id"], 1)


class BodySafetyTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.gh = Gh(transport=self.fake)

    def test_body_with_its_own_marker_is_refused(self):
        for text in ("hi <!-- factory:checkpoint {} -->", "<!--factory:reply-->",
                     "text\n<!--\n FACTORY:story id=STORY-001 increment=001-a -->"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(CommentError, "must not contain"):
                    post_reply(self.gh, REPO, 7, text)
                with self.assertRaisesRegex(CommentError, "must not contain"):
                    checkpoint(self.gh, note=text)
        self.assertEqual(self.fake.writes, [])

    def test_oversized_body_refused(self):
        with self.assertRaisesRegex(CommentError, "limit"):
            post_reply(self.gh, REPO, 7, "x" * MAX_BODY)
        self.assertEqual(self.fake.writes, [])


class TargetKindTest(unittest.TestCase):
    def test_issue_vs_pr(self):
        gh = Gh(transport=FakeGitHub(prs={9}))
        check_target_kind(gh, REPO, 7, expect_pr=False)
        check_target_kind(gh, REPO, 9, expect_pr=True)
        with self.assertRaisesRegex(CommentError, "is a pull request, not an issue"):
            check_target_kind(gh, REPO, 9, expect_pr=False)
        with self.assertRaisesRegex(CommentError, "is an issue, not a pull request"):
            check_target_kind(gh, REPO, 7, expect_pr=True)


class CommentCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.factory = root / "factory"
        (self.factory / ".factory-local").mkdir(parents=True)
        self.app = root / "app"
        self.app.mkdir()
        git = Git(self.app)
        git.run(["init", "-b", "story/7-add-thing"])
        git.run(["remote", "add", "origin", f"https://github.com/{REPO}.git"])
        (self.app / "f.txt").write_text("x", encoding="utf-8")
        git.run(["add", "f.txt"])
        git.run(["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "c"])
        self.head = git.rev_parse("HEAD")
        (self.factory / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(self.app), "repo": REPO}), encoding="utf-8")
        self.fake = FakeGitHub(prs={9})
        self.body = root / "body.md"

    def run_cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        fake_stdin = mock.MagicMock()
        fake_stdin.buffer.read.return_value = (stdin or "").encode("utf-8")
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.fake)), \
                mock.patch.object(cli.sys, "stdin", fake_stdin), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_reply_from_file(self):
        self.body.write_text("Fixed the typo.", encoding="utf-8")
        code, out, _ = self.run_cli("comment", "--pr", "9", "--kind", "reply",
                                    "--body-file", str(self.body))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], f"Target: {self.app} ({REPO})")
        self.assertIn("created reply comment on #9", out)
        self.assertEqual(self.fake.comments[9][0]["body"],
                         "<!-- factory:reply -->\nFixed the typo.")

    def test_reply_from_stdin_utf8(self):
        code, _, _ = self.run_cli("comment", "--issue", "7", "--kind", "reply",
                                  "--body-file", "-", stdin="Grüße ✓")
        self.assertEqual(code, 0)
        self.assertTrue(self.fake.comments[7][0]["body"].endswith("Grüße ✓"))

    def test_checkpoint_twice_defaults_from_target_git(self):
        for station, nxt in (("S08", "S09"), ("S09", "S10")):
            code, out, err = self.run_cli("comment", "--issue", "7", "--kind", "checkpoint",
                                          "--station", station, "--next", nxt)
            self.assertEqual(code, 0, err)
        self.assertIn("updated checkpoint comment on #7", out)
        cps = self.fake.checkpoint_comments(7)
        self.assertEqual(len(cps), 1)
        marker = find(cps[0]["body"], CheckpointMarker)
        self.assertEqual((marker.branch, marker.sha, marker.station),
                         ("story/7-add-thing", self.head, "S09"))

    def test_reply_to_a_feedback_item(self):
        """T4.2: a rework reply names the comment it answers."""
        item = self.fake.add_human_comment(9, "/changes\nRename x")
        self.body.write_text("Renamed x to y in abc1234.", encoding="utf-8")
        code, out, err = self.run_cli("comment", "--pr", "9", "--kind", "reply",
                                      "--to", str(item["id"]), "--body-file", str(self.body))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.comments[9][-1]["body"],
                         f"<!-- factory:reply to={item['id']} -->\nRenamed x to y in abc1234.")

    def test_reply_to_refusals(self):
        self.fake.add_human_comment(9, "/changes\nRename x")
        self.body.write_text("text", encoding="utf-8")
        cases = [
            (("--pr", "9", "--kind", "reply", "--to", "555", "--body-file", str(self.body)),
             "has no comment with id 555"),
            (("--issue", "7", "--kind", "reply", "--to", "1", "--body-file", str(self.body)),
             "use it with --pr"),
            (("--issue", "7", "--kind", "checkpoint", "--station", "S08", "--next", "S09",
              "--to", "1"), "only for --kind reply"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                code, _, err = self.run_cli("comment", *extra)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertEqual(self.fake.writes, [])

    def test_cli_refusals(self):
        self.body.write_text("text", encoding="utf-8")
        cases = [
            (("--issue", "7", "--kind", "reply"), "needs --body-file"),
            (("--issue", "7", "--kind", "checkpoint", "--station", "S08"),
             "needs --station and --next"),
            (("--pr", "9", "--kind", "checkpoint", "--station", "S08", "--next", "S09"),
             "use --issue"),
            (("--issue", "9", "--kind", "reply", "--body-file", str(self.body)),
             "is a pull request"),
            (("--issue", "7", "--kind", "reply", "--body-file", str(self.body),
              "--station", "S08"), "only for --kind checkpoint"),
            (("--issue", "7", "--kind", "reply", "--body-file", "missing.md"),
             "cannot read --body-file"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                code, _, err = self.run_cli("comment", *extra)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertEqual(self.fake.writes, [])


class GhJsonBodyTest(unittest.TestCase):
    def test_json_body_goes_to_stdin_not_argv(self):
        gh = FakeGh([{"args": ["api", "x", "--method", "POST", "--input", "-"],
                      "input": json.dumps({"body": "long text"}), "returncode": 0,
                      "stdout": "{}", "stderr": ""}])
        gh.api("x", method="POST", json_body={"body": "long text"})
        self.assertNotIn("long text", " ".join(gh.replay.calls[0]["args"]))


if __name__ == "__main__":
    unittest.main()
