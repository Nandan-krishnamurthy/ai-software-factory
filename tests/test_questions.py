"""T5.1: the needs-human question issue (S01's red baseline) and the reviewer's answer."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, questions, target
from factory.gh import Gh, ProcessResult
from factory.markers import QuestionMarker, ReplyMarker, build, find, parse_all
from factory.questions import QuestionError, accepted_by, answer, ask

REPO = "owner/app"
KEY = "baseline-002-due-dates"
ME = "nandan"


class FakeIssues:
    """In-memory GitHub issues, issue comments and labels, behind the gh transport."""

    def __init__(self):
        self.issues: list[dict] = []
        self.comments: dict[int, list[dict]] = {}
        self.labels_added: list[tuple[int, list[str]]] = []
        self.clock = 0

    def tick(self) -> str:
        self.clock += 1
        return f"2026-10-07T10:{self.clock:02d}:00Z"

    def add_issue(self, body, *, state="open", pr=False, labels=(), title=None):
        number = len(self.issues) + 1
        item = {"number": number, "state": state, "body": body, "title": title or f"#{number}",
                "created_at": self.tick(), "labels": [{"name": n} for n in labels],
                "html_url": f"https://github.com/{REPO}/issues/{number}"}
        if pr:
            item["pull_request"] = {"url": "..."}
        self.issues.append(item)
        return item

    def add_comment(self, number, body, login=ME):
        comment = {"id": 100 + sum(map(len, self.comments.values())), "body": body,
                   "user": {"login": login}, "created_at": self.tick(),
                   "html_url": f"https://github.com/{REPO}/issues/{number}#c"}
        self.comments.setdefault(number, []).append(comment)
        return comment

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = argv[1:]
        assert args[0] == "api", args
        endpoint, method = args[1], args[args.index("--method") + 1]
        body = json.loads(input) if input else None
        if endpoint == f"repos/{REPO}/issues?state=all&per_page=100" and method == "GET":
            return self._ok([list(self.issues)])
        if endpoint == f"repos/{REPO}/issues" and method == "POST":
            return self._ok(self.add_issue(body["body"], labels=body["labels"],
                                           title=body["title"]))
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/comments", endpoint):
            number = int(m[1])
            if method == "GET":
                return self._ok([list(self.comments.get(number, []))])
            return self._ok(self.add_comment(number, body["body"]))
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/labels", endpoint):
            self.labels_added.append((int(m[1]), body["labels"]))
            return self._ok([{"name": n} for n in body["labels"]])
        raise AssertionError(f"unexpected call: {args}")

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")


class AskTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeIssues()
        self.gh = Gh(transport=self.fake)

    def test_creates_one_labelled_issue_found_by_its_marker(self):
        asked = ask(self.gh, REPO, KEY, "Baseline is red for increment 002-due-dates",
                    "npm test: 3 failed")
        self.assertEqual((asked.action, asked.number), ("created", 1))
        issue = self.fake.issues[0]
        self.assertEqual(issue["body"].splitlines()[0], build(QuestionMarker(key=KEY)))
        self.assertEqual([label["name"] for label in issue["labels"]], ["factory:needs-human"])
        self.assertEqual(issue["title"], "Baseline is red for increment 002-due-dates")

    def test_asking_again_while_open_adds_to_the_same_issue(self):
        """T4.4: a resumed or repeated S01 never opens a second issue."""
        ask(self.gh, REPO, KEY, "Baseline is red", "npm test: 3 failed")
        again = ask(self.gh, REPO, KEY, "Baseline is red", "npm test: 2 failed")
        self.assertEqual((again.action, again.number), ("updated", 1))
        self.assertEqual(len(self.fake.issues), 1)
        reply = self.fake.comments[1][0]["body"]
        self.assertEqual(parse_all(reply), [ReplyMarker()])
        self.assertIn("2 failed", reply)
        # The human may have removed the label: it is put back.
        self.assertEqual(self.fake.labels_added, [(1, ["factory:needs-human"])])

    def test_a_closed_question_is_not_reopened_a_new_one_is_asked(self):
        self.fake.add_issue(build(QuestionMarker(key=KEY)) + "\nold", state="closed")
        asked = ask(self.gh, REPO, KEY, "Baseline is red", "still red")
        self.assertEqual((asked.action, asked.number), ("created", 2))

    def test_other_keys_and_pull_requests_do_not_match(self):
        self.fake.add_issue(build(QuestionMarker(key="baseline-001-initial")) + "\nx")
        self.fake.add_issue(build(QuestionMarker(key=KEY)) + "\nx", pr=True)
        self.fake.add_issue(f"Pasted: factory:question key={KEY}")  # not a marker
        asked = ask(self.gh, REPO, KEY, "Baseline is red", "red")
        self.assertEqual((asked.action, asked.number), ("created", 4))

    def test_refusals(self):
        cases = [("Bad Key", "t", "x", "invalid --key"), (KEY, " ", "x", "--title"),
                 (KEY, "t", "  ", "non-empty body"),
                 (KEY, "t", build(ReplyMarker()) + " x", "must not contain factory markers")]
        for key, title, text, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(QuestionError, message):
                ask(self.gh, REPO, key, title, text)
        self.assertEqual(self.fake.issues, [])


class AnswerTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeIssues()
        self.gh = Gh(transport=self.fake)
        self.issue = self.fake.add_issue(build(QuestionMarker(key=KEY)) + "\nRed: npm test")

    def check(self, keyword="accept-baseline", reviewers=(ME,)):
        return answer(self.gh, REPO, KEY, keyword, list(reviewers))

    def test_never_asked(self):
        self.assertEqual(answer(self.gh, REPO, "baseline-009-x", "accept-baseline", [ME]),
                         questions.Answer(None, None, False))

    def test_a_reviewer_accepts(self):
        self.fake.add_comment(1, "/accept-baseline\nThe 3 failures are known flakes.")
        result = self.check()
        self.assertEqual((result.issue, result.state, result.accepted, result.by),
                         (1, "open", True, ME))

    def test_what_does_not_count_as_acceptance(self):
        cases = {
            "not a reviewer": ("/accept-baseline", "someone-else"),
            "not the first line": ("I think\n/accept-baseline", ME),
            "a longer word": ("/accept-baseline-later", ME),
            "a factory comment": (build(ReplyMarker()) + "\n/accept-baseline", ME),
            "no slash": ("accept-baseline", ME),
        }
        for why, (body, login) in cases.items():
            with self.subTest(why=why):
                self.fake.comments.clear()
                self.fake.add_comment(1, body, login=login)
                self.assertFalse(self.check().accepted)

    def test_an_answer_older_than_the_latest_question_does_not_count(self):
        self.fake.add_comment(1, "/accept-baseline")
        self.fake.add_comment(1, build(ReplyMarker()) + "\nStill red, now 4 failures.")
        self.assertFalse(self.check().accepted)
        self.fake.add_comment(1, "/accept-baseline 4 is fine")
        self.assertTrue(self.check().accepted)

    def test_reviewer_logins_are_case_insensitive_and_the_issue_may_be_closed(self):
        self.issue["state"] = "closed"
        self.fake.add_comment(1, "/accept-baseline", login="Nandan")
        result = self.check(reviewers=("NANDAN",))
        self.assertEqual((result.accepted, result.state), (True, "closed"))

    def test_invalid_keyword(self):
        with self.assertRaisesRegex(QuestionError, "without the leading slash"):
            self.check(keyword="/accept-baseline")

    def test_accepted_by_is_pure(self):
        issue = {"created_at": "2026-10-07T10:00:00Z"}
        comments = [{"body": "/accept-baseline", "user": {"login": ME},
                     "created_at": "2026-10-07T09:00:00Z"}]
        self.assertEqual(accepted_by(issue, comments, "accept-baseline", [ME]),
                         (False, None, None))


class QuestionCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.factory = root / "factory"
        (self.factory / ".factory-local").mkdir(parents=True)
        app = root / "app"
        (app / ".factory").mkdir(parents=True)
        config = json.loads((Path(__file__).parents[1] / "templates" / "config.json")
                            .read_text(encoding="utf-8"))
        config.update(project="app", repo=REPO, default_branch="main", reviewers=[ME])
        (app / ".factory" / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (self.factory / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(app), "repo": REPO}), encoding="utf-8")
        self.body = root / "baseline.md"
        self.body.write_text("npm test: 3 failed", encoding="utf-8")
        self.fake = FakeIssues()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=self.fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_ask_then_answer(self):
        code, out, _ = self.run_cli("question", "ask", "--key", KEY, "--title", "Baseline red",
                                    "--body-file", str(self.body), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["action"], "created")
        self.assertIsNotNone(find(self.fake.issues[0]["body"], QuestionMarker))

        code, out, _ = self.run_cli("question", "answer", "--key", KEY,
                                    "--keyword", "accept-baseline", "--json")
        self.assertEqual((code, json.loads(out)["accepted"]), (0, False))
        self.fake.add_comment(1, "/accept-baseline")
        code, out, _ = self.run_cli("question", "answer", "--key", KEY,
                                    "--keyword", "accept-baseline")
        self.assertEqual(code, 0)
        self.assertIn(f"/accept-baseline from {ME}", out)


if __name__ == "__main__":
    unittest.main()
