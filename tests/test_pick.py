"""T3.1: ``pick`` (the unblocked rule, refusals) and ``label`` (exactly one status)."""

import contextlib
import io
import itertools
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, pick, target, templates
from factory.gh import Gh, ProcessResult
from factory.pick import PickError, choose, label_changes, parse_issues

REPO = "owner/app"
INC = "001-initial"


def body(n, milestone="M1", blocked_by="None", inc=INC):
    """A story issue body exactly as ``issues sync`` writes it (templates/story.md)."""
    return templates.render(templates.load("story.md"), {
        "story_id": f"STORY-{n:03d}", "increment": inc, "milestone": milestone,
        "story": "As a user, I want x so that y.", "traces_to": "REQ-001",
        "acceptance_criteria": "- [ ] AC1: Given a, when b, then c.",
        "out_of_scope": "None", "blocked_by": blocked_by,
        "technical_notes": "None", "test_plan": "- Unit: x"})


def item(number, story=None, milestone="M1", blocked_by="None", state="open",
         labels=("factory:story", "status:ready"), inc=INC):
    """One entry of ``repos/<r>/issues``. ``story=None`` is a plain, non-story issue."""
    text = "a human issue" if story is None else body(story, milestone, blocked_by, inc)
    return {"number": number, "title": f"STORY-{story or 0:03d}: title {number}",
            "state": state, "body": text, "labels": [{"name": n} for n in labels]}


def demo_graph():
    """The 12 issues S05b created in the M2 demo (task-tracker-factory-test #2-#13)."""
    spec = [(2, 1, "M1", "None"), (3, 2, "M1", "#2"), (4, 3, "M2", "#3"),
            (5, 4, "M2", "#4"), (6, 5, "M3", "#4"), (7, 6, "M3", "#6"),
            (8, 7, "M4", "#4"), (9, 8, "M5", "#8"), (10, 9, "M5", "#7, #9"),
            (11, 10, "M5", "#8"), (12, 11, "M6", "#7, #10, #11"),
            (13, 12, "M6", "#7, #10, #11")]
    return [item(n, s, m, b) for n, s, m, b in spec]


def close(items, *numbers):
    for i in items:
        if i["number"] in numbers:
            i["state"] = "closed"
            i["labels"] = [{"name": "factory:story"}, {"name": "status:done"}]
    return items


def chosen(items):
    return choose(*parse_issues(items)).picked.number


class UnblockedRuleTest(unittest.TestCase):
    """A table of dependency graphs: which story is picked, and why."""

    def test_graphs(self):
        cases = [
            ("demo: only the walking skeleton is unblocked", demo_graph(), 2),
            ("demo: after #2", close(demo_graph(), 2), 3),
            ("demo: after #2-#4, lowest milestone wins (#5 M2 over #6 M3, #8 M4)",
             close(demo_graph(), 2, 3, 4), 5),
            ("demo: after #2-#5, #6 (M3) before #8 (M4)", close(demo_graph(), 2, 3, 4, 5), 6),
            ("lower milestone beats lower number",
             [item(5, 1, "M2"), item(20, 2, "M1")], 20),
            ("same milestone: lowest issue number",
             [item(9, 1, "M1"), item(4, 2, "M1"), item(7, 3, "M1")], 4),
            ("milestones compare as numbers (M2 before M10)",
             [item(3, 1, "M10"), item(8, 2, "M2")], 8),
            ("one open blocker is enough to block",
             [item(1, 1), item(2, 2, blocked_by="#1, #3"), item(3, 3, state="closed")]
             + [item(4, 4, "M2")], 1),
            ("all blockers closed: unblocked",
             close([item(1, 1), item(3, 3), item(2, 2, blocked_by="#1, #3")], 1, 3), 2),
            ("a closed non-story blocker counts as done",
             [item(5, None, state="closed", labels=()), item(6, 1, blocked_by="#5"),
              item(7, 2, "M2")], 6),
            ("an open non-story blocker blocks",
             [item(5, None, labels=()), item(6, 1, blocked_by="#5"), item(7, 2, "M2")], 7),
            ("a blocker the factory cannot see blocks",
             [item(6, 1, blocked_by="#99"), item(7, 2, "M2")], 7),
            ("closed stories are never picked",
             [item(1, 1, state="closed"), item(2, 2, "M2")], 2),
            ("status:blocked is not ready",
             [item(1, 1, labels=("factory:story", "status:blocked")), item(2, 2, "M2")], 2),
            ("factory:needs-human is skipped",
             [item(1, 1, labels=("factory:story", "status:ready", "factory:needs-human")),
              item(2, 2, "M2")], 2),
            ("a story with no milestone comes after every milestone",
             [item(1, 1, milestone="?"), item(2, 2, "M9")], 2),
            ("the oldest increment first: its M3 before the next increment's M1",
             [item(10, 20, "M1", inc="002-due-dates"), item(4, 3, "M3")], 4),
            ("a story with two issues is not picked",
             [item(1, 1), item(2, 1), item(3, 2, "M2")], 3),
        ]
        for name, items, expected in cases:
            with self.subTest(name):
                self.assertEqual(chosen(items), expected)

    def test_ties_break_the_same_way_in_any_input_order(self):
        items = [item(4, 1, "M1"), item(2, 2, "M2"), item(3, 3, "M1"), item(9, 4, "M1")]
        orders = {tuple(o.number for o in choose(*parse_issues(list(p))).unblocked)
                  for p in itertools.permutations(items)}
        self.assertEqual(orders, {(3, 4, 9, 2)})

    def test_choice_reports_what_is_still_blocked(self):
        result = choose(*parse_issues(demo_graph()))
        self.assertEqual([s.number for s in result.unblocked], [2])
        self.assertEqual(result.blocked[3], (2,))
        self.assertEqual(result.blocked[10], (7, 9))

    def test_milestone_and_blockers_are_read_from_the_real_template(self):
        story = parse_issues([item(10, 9, "M5", "#7, #9")])[0][0]
        self.assertEqual((story.story_id, story.increment, story.milestone, story.blocked_by),
                         ("STORY-009", INC, 5, (7, 9)))


class PickRefusalTest(unittest.TestCase):
    def test_refuses_while_a_story_is_in_flight(self):
        for label in ("status:in-progress", "status:in-review", "status:changes-requested"):
            with self.subTest(label):
                items = demo_graph()
                items[3]["labels"] = [{"name": "factory:story"}, {"name": label}]
                with self.assertRaises(PickError) as ctx:
                    choose(*parse_issues(items))
                self.assertIn(f"#5 (STORY-004, {label})", str(ctx.exception))
                self.assertIn("one story at a time", str(ctx.exception))

    def test_a_closed_issue_with_a_stale_label_is_not_in_flight(self):
        items = demo_graph()
        items[0]["state"] = "closed"
        items[0]["labels"] = [{"name": "factory:story"}, {"name": "status:in-progress"}]
        self.assertEqual(chosen(items), 3)

    def test_nothing_unblocked_says_why(self):
        items = [item(1, 1, blocked_by="#2"), item(2, 2, blocked_by="#1")]
        with self.assertRaises(PickError) as ctx:
            choose(*parse_issues(items))
        self.assertIn("no story can be picked: #1 waits for #2; #2 waits for #1",
                      str(ctx.exception))

    def test_nothing_ready(self):
        with self.assertRaises(PickError) as ctx:
            choose(*parse_issues(close(demo_graph(), *range(2, 14))))
        self.assertIn("no open story is labelled status:ready", str(ctx.exception))

    def test_refuses_without_the_flag_before_touching_github(self):
        fake = FakeGitHub(demo_graph())
        with self.assertRaises(PickError) as ctx:
            pick.pick(Gh(transport=fake), REPO, authorized_by_continue=False)
        self.assertIn("only /factory-continue may start a story", str(ctx.exception))
        self.assertEqual(fake.calls, [])


class LabelChangesTest(unittest.TestCase):
    def test_changes(self):
        ready = frozenset({"factory:story", "status:ready"})
        self.assertEqual(label_changes(ready, "in-progress"),
                         (["status:in-progress"], ["status:ready"]))
        self.assertEqual(label_changes(ready, "ready"), ([], []))
        self.assertEqual(label_changes(frozenset({"factory:story"}), "blocked"),
                         (["status:blocked"], []))
        two = frozenset({"status:ready", "status:in-review", "bug"})
        self.assertEqual(label_changes(two, "in-review"), ([], ["status:ready"]))

    def test_statuses_are_the_factory_labels(self):
        self.assertEqual(pick.STATUSES, ("ready", "blocked", "in-progress", "in-review",
                                         "changes-requested", "done"))


class FakeGitHub:
    """Just enough of GitHub's REST API for pick and label, via the gh transport."""

    def __init__(self, items, login="factory-user"):
        self.items = {i["number"]: i for i in items}
        self.login = login
        self.calls: list[tuple[str, str]] = []  # (method, endpoint) of every call

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = argv[1:]
        assert args[0] == "api", args
        endpoint, method = args[1], args[args.index("--method") + 1]
        self.calls.append((method, endpoint))
        if endpoint == f"repos/{REPO}/issues?state=all&per_page=100":
            return self._ok([list(self.items.values())])
        if endpoint == "user":
            return self._ok({"login": self.login})
        m = re.fullmatch(rf"repos/{REPO}/issues/(\d+)(/.*)?", endpoint)
        if m is None:
            raise AssertionError(f"unexpected call: {args}")
        issue = self.items.get(int(m[1]))
        if issue is None:
            return ProcessResult(argv, 1, "", "gh: Not Found (HTTP 404)")
        rest = m[2] or ""
        names = [label["name"] for label in issue["labels"]]
        if rest == "" and method == "GET":
            return self._ok(issue)
        if rest == "/assignees" and method == "POST":
            issue["assignees"] = json.loads(input)["assignees"]
            return self._ok(issue)
        if rest == "/labels" and method == "POST":
            names += [n for n in json.loads(input)["labels"] if n not in names]
        elif rest.startswith("/labels/") and method == "DELETE":
            name = rest[len("/labels/"):].replace("%3A", ":")
            names.remove(name)
        else:
            raise AssertionError(f"unexpected call: {args}")
        issue["labels"] = [{"name": n} for n in names]
        return self._ok(issue["labels"])

    @staticmethod
    def _ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    def labels(self, number):
        return sorted(label["name"] for label in self.items[number]["labels"])


class PickGitHubTest(unittest.TestCase):
    def test_pick_assigns_then_locks_the_chosen_story(self):
        fake = FakeGitHub(demo_graph())
        choice, login = pick.pick(Gh(transport=fake), REPO, authorized_by_continue=True)
        self.assertEqual((choice.picked.number, login), (2, "factory-user"))
        self.assertEqual(fake.items[2]["assignees"], ["factory-user"])
        self.assertEqual(fake.labels(2), ["factory:story", "status:in-progress"])
        writes = [c for c in fake.calls if c[0] != "GET"]
        self.assertEqual(writes, [
            ("POST", f"repos/{REPO}/issues/2/assignees"),          # assign first
            ("POST", f"repos/{REPO}/issues/2/labels"),             # add the lock
            ("DELETE", f"repos/{REPO}/issues/2/labels/status%3Aready"),  # then drop ready
        ])
        self.assertEqual([n for n in fake.items if n != 2 and fake.labels(n)
                          != ["factory:story", "status:ready"]], [])

    def test_second_pick_is_refused_by_the_lock(self):
        fake = FakeGitHub(demo_graph())
        pick.pick(Gh(transport=fake), REPO, authorized_by_continue=True)
        with self.assertRaises(PickError) as ctx:
            pick.pick(Gh(transport=fake), REPO, authorized_by_continue=True)
        self.assertIn("#2 (STORY-001, status:in-progress)", str(ctx.exception))

    def test_nothing_is_written_when_nothing_can_be_picked(self):
        fake = FakeGitHub([item(1, 1, blocked_by="#9")])
        with self.assertRaises(PickError):
            pick.pick(Gh(transport=fake), REPO, authorized_by_continue=True)
        self.assertEqual([c for c in fake.calls if c[0] != "GET"], [])


class SetStatusTest(unittest.TestCase):
    def test_moves_to_exactly_one_status(self):
        fake = FakeGitHub([item(4, 1, labels=("factory:story", "status:ready",
                                              "status:in-progress", "bug"))])
        add, remove = pick.set_status(Gh(transport=fake), REPO, 4, "in-review")
        self.assertEqual((add, remove), (["status:in-review"],
                                         ["status:in-progress", "status:ready"]))
        self.assertEqual(fake.labels(4), ["bug", "factory:story", "status:in-review"])

    def test_already_right_changes_nothing(self):
        fake = FakeGitHub([item(4, 1)])
        self.assertEqual(pick.set_status(Gh(transport=fake), REPO, 4, "ready"), ([], []))
        self.assertEqual(fake.calls, [("GET", f"repos/{REPO}/issues/4")])

    def test_refusals(self):
        pr = item(6, 2)
        pr["pull_request"] = {"url": "..."}
        fake = FakeGitHub([item(5, None, labels=()), pr, item(7, 3)])
        gh = Gh(transport=fake)
        for number, status, message in [
                (5, "done", "#5 is not a factory story issue"),
                (6, "done", "#6 is a pull request"),
                (7, "merged", "unknown status 'merged'")]:
            with self.subTest(number), self.assertRaises(pick.LabelError) as ctx:
                pick.set_status(gh, REPO, number, status)
            self.assertIn(message, str(ctx.exception))
        self.assertEqual([c for c in fake.calls if c[0] != "GET"], [])


class CliTest(unittest.TestCase):
    def run_cli(self, fake, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(Path("/t"), REPO)), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_pick_without_the_flag_exits_1(self):
        fake = FakeGitHub(demo_graph())
        code, _, err = self.run_cli(fake, "pick")
        self.assertEqual(code, 1)
        self.assertIn("error: refused: only /factory-continue may start a story", err)
        self.assertEqual(fake.calls, [])

    def test_pick_with_the_flag(self):
        code, out, _ = self.run_cli(FakeGitHub(close(demo_graph(), 2, 3, 4)),
                                    "pick", "--authorized-by-continue")
        self.assertEqual(code, 0)
        self.assertIn("Picked #5 STORY-004: STORY-004: title 5", out)
        self.assertIn("increment 001-initial, M2; assigned to factory-user; "
                      "label status:in-progress", out)
        self.assertIn("Also unblocked, for later: #6 (M3), #8 (M4)", out)

    def test_pick_json(self):
        code, out, err = self.run_cli(FakeGitHub(demo_graph()),
                                      "pick", "--authorized-by-continue", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["picked"]["number"], 2)
        self.assertEqual(data["also_unblocked"], [])
        self.assertEqual(data["blocked"]["10"], [7, 9])
        self.assertIn("Target: ", err)

    def test_pick_refused_in_flight_exits_1(self):
        items = demo_graph()
        items[0]["labels"] = [{"name": "factory:story"}, {"name": "status:in-review"}]
        code, _, err = self.run_cli(FakeGitHub(items), "pick", "--authorized-by-continue")
        self.assertEqual(code, 1)
        self.assertIn("a story is already in flight: #2 (STORY-001, status:in-review)", err)

    def test_label(self):
        fake = FakeGitHub(demo_graph())
        code, out, _ = self.run_cli(fake, "label", "--issue", "3", "--status", "blocked")
        self.assertEqual((code, out.splitlines()[-1]),
                         (0, "#3: +status:blocked, -status:ready"))
        code, out, _ = self.run_cli(fake, "label", "--issue", "3", "--status", "blocked")
        self.assertEqual(out.splitlines()[-1],
                         "#3 already has only status:blocked; nothing changed")

    def test_label_rejects_unknown_status(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["label", "--issue", "3", "--status", "merged"])


if __name__ == "__main__":
    unittest.main()
