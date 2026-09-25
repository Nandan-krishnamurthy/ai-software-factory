"""T2.5: the slash-command files and ``factory.py route``.

* ``route()`` decides whether a command runs a station or stops. It is tested state by
  state, and by **driving each command's loop** the way the command files describe it:
  ``route`` → run the station (simulated by changing the snapshot) → ``route --continuing``.
  Each state comes from the real ``derive_state()``.
* The command files are linted with the same checker as the stations (T2.4).
"""

import contextlib
import dataclasses
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, commands, target
from factory import state as st
from factory.commands import COMMANDS, route
from tests import REPO_ROOT
from tests.test_state import (
    ALL_DOCS,
    INC,
    PLAN_BRANCH,
    issue,
    labelled,
    planning_pr,
    snap,
    story_pr,
)
from tests.test_stations import (
    FORBIDDEN,
    PENDING,
    guard_context,
    lint_command,
    load_stations,
    parse_frontmatter,
)
from tests.test_stations import (
    commands as command_spans,
)

COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
PLANNING_COMMANDS = {"factory-target.md", "factory-start.md", "factory-status.md",
                     "factory-resume.md"}
READ_ONLY = {  # command file -> the factory.py subcommands it may run
    "factory-target.md": {"target set", "doctor", "state"},
    "factory-status.md": {"target show", "state", "increment show", "feedback"},
}
MAX_LINES = 40  # command files are thin wrappers (architecture §4.2)


def result(snapshot) -> dict:
    return st.derive_state(snapshot).to_dict()


def planning(files=(), config=True, **kw):
    return snap(branches=PLAN_BRANCH, plan_config={INC: config},
                plan_files={INC: frozenset(files)}, **kw)


GATE_A_WAITING = planning(ALL_DOCS, prs=(planning_pr(5),), planning_verdicts={5: "PENDING"})
GATE_A_CHANGES = dataclasses.replace(GATE_A_WAITING, planning_verdicts={5: "CHANGES_REQUESTED"})
MERGED = dict(branches=frozenset({"main"}), prs=(planning_pr(5, "MERGED"),),
              stories_on_default={INC: frozenset({"STORY-001", "STORY-002"})})
ISSUES_PENDING = snap(**MERGED, issues=(issue(10, 1),))
IDLE = snap(**MERGED, issues=(issue(10, 1), issue(11, 2)))


def after_station(snapshot, station):
    """What the world looks like after ``station`` did its job (a simulated station)."""
    files = set(snapshot.plan_files.get(INC, frozenset()))
    doc = dict(st.PLAN_DOCS).get(station)
    if station == "S00":
        return planning({"00-prd.md"})
    if station in ("S02", "S03", "S04"):
        return dataclasses.replace(snapshot, plan_files={INC: frozenset(files | {doc})})
    if station == "S05":  # opens the Planning PR, or answers /changes: waiting for review
        return GATE_A_WAITING
    if station == "S05b":
        return IDLE
    raise AssertionError(f"no simulation for {station}")


def drive(command, snapshot, *, stuck=None, limit=20):
    """Run a command's loop as its file describes. Returns (stations run, final route)."""
    ran = []
    decision = route(command, result(snapshot))
    while decision.action == "run" and len(ran) < limit:
        ran.append(decision.station)
        if decision.station != stuck:
            snapshot = after_station(snapshot, decision.station)
        decision = route(command, result(snapshot), continuing=True, after=decision.station)
    return ran, decision


class RouteAcceptanceTest(unittest.TestCase):
    """The T2.5 acceptance criteria, through the real state engine."""

    def test_resume_at_gate_a_changes_revises_then_stops_at_gate_a(self):
        self.assertEqual(result(GATE_A_CHANGES)["state"], st.GATE_A_CHANGES)
        first = route("/factory-resume", result(GATE_A_CHANGES))
        self.assertEqual((first.action, first.station, first.station_file),
                         ("run", "S05", "stations/S05-stories.md"))
        ran, final = drive("/factory-resume", GATE_A_CHANGES)
        self.assertEqual(ran, ["S05"])
        self.assertEqual((final.action, final.state), ("stop", st.GATE_A_WAITING))

    def test_resume_at_issues_pending_runs_s05b_then_stops_at_gate_c(self):
        self.assertEqual(result(ISSUES_PENDING)["state"], st.ISSUES_PENDING)
        ran, final = drive("/factory-resume", ISSUES_PENDING)
        self.assertEqual(ran, ["S05b"])
        self.assertEqual((final.action, final.state), ("stop", st.IDLE_AT_GATE_C))
        self.assertIn("/factory-continue", final.message)

    def test_revision_station_is_the_one_that_replies_via_factory_comment(self):
        s05 = (REPO_ROOT / "stations" / "S05-stories.md").read_text(encoding="utf-8")
        revision = s05[s05.index("### Revision mode"):s05.index("## Outputs")]
        self.assertIn("python scripts/factory.py comment --pr <N> --kind reply", revision)
        self.assertIn("python scripts/factory.py feedback --pr <N>", revision)


class DriveTest(unittest.TestCase):
    def test_start_plans_a_new_project_up_to_gate_a(self):
        ran, final = drive("/factory-start", snap(is_empty=False))
        self.assertEqual(ran, ["S00", "S02", "S03", "S04", "S05"])
        self.assertEqual((final.action, final.state), ("stop", st.GATE_A_WAITING))

    def test_resume_finishes_interrupted_planning(self):
        ran, final = drive("/factory-resume", planning({"00-prd.md", "02-requirements.md"}))
        self.assertEqual(ran, ["S03", "S04", "S05"])
        self.assertEqual(final.state, st.GATE_A_WAITING)

    def test_start_from_unconfigured_begins_with_s00(self):
        first = route("/factory-start", result(snap()))
        self.assertEqual((first.state, first.action, first.station),
                         (st.UNCONFIGURED, "run", "S00"))
        # The entry station applies only at entry, never while continuing.
        again = route("/factory-start", result(snap()), continuing=True, after="S00")
        self.assertEqual(again.action, "stop")

    def test_resume_of_an_interrupted_s00(self):
        ran, _ = drive("/factory-resume", planning(config=False))
        self.assertEqual(ran[0], "S00")

    def test_a_station_that_does_not_complete_stops_the_loop(self):
        ran, final = drive("/factory-resume", planning({"00-prd.md"}), stuck="S02")
        self.assertEqual(ran, ["S02"])
        self.assertEqual(final.action, "stop")
        self.assertIn("S02 ran but the state engine still names it", final.message)

    def test_existing_project_stops_before_s01_until_it_exists(self):
        existing = dataclasses.replace(planning({"00-prd.md"}), existing_project=True)
        ran, final = drive("/factory-resume", existing)
        self.assertEqual(ran, [])
        self.assertIn("S01, which is not available yet", final.message)


class RouteTest(unittest.TestCase):
    def test_entry_requires_the_command_to_be_allowed(self):
        cases = [
            ("/factory-start", GATE_A_WAITING), ("/factory-start", GATE_A_CHANGES),
            ("/factory-start", planning({"00-prd.md"})),  # interrupted planning: resume
            ("/factory-start", IDLE), ("/factory-resume", snap()),  # UNCONFIGURED
            ("/factory-resume", GATE_A_WAITING), ("/factory-resume", IDLE),
        ]
        for command, snapshot in cases:
            with self.subTest(command=command, state=result(snapshot)["state"]):
                decision = route(command, result(snapshot))
                self.assertEqual(decision.action, "stop")
                self.assertIn("cannot act in state", decision.message)

    def test_resume_never_starts_a_story(self):
        # Even if the state engine someday names S06 in a state /factory-resume may act
        # in, the route refuses: only /factory-continue picks a story (rule S2).
        data = result(IDLE)
        data.update(next_station="S06", allowed_commands=["/factory-resume"],
                    waiting_on="factory")
        for continuing in (False, True):
            decision = route("/factory-resume", data, continuing=continuing)
            self.assertEqual(decision.action, "stop")
            self.assertIn("Only /factory-continue may start a story", decision.message)
        self.assertNotIn("S06", COMMANDS["/factory-resume"].stations)

    def test_resume_finishes_a_story_already_in_progress(self):
        # T3.3: /factory-resume continues a story from its checkpoint, through S11, and
        # stops at Gate B; it runs none of this from IDLE (no story picked).
        in_progress = snap(**{**MERGED, "branches": frozenset({"main", "story/10-x"})},
                           issues=(issue(10, 1, labels=labelled("in-progress"),
                                         checkpoint_branch="story/10-x",
                                         checkpoint_next="S09"), issue(11, 2)))
        decision = route("/factory-resume", result(in_progress))
        self.assertEqual((decision.action, decision.station, decision.station_file),
                         ("run", "S09", "stations/S09-test.md"))
        gate_b = snap(**{**MERGED, "prs": (*MERGED["prs"], story_pr(20, 1))},
                      issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)))
        decision = route("/factory-resume", result(gate_b), continuing=True, after="S11")
        self.assertEqual((decision.action, decision.state), ("stop", st.GATE_B_WAITING_REVIEW))
        self.assertEqual(route("/factory-resume", result(IDLE)).action, "stop")

    def test_needs_human_and_inconsistent_stop(self):
        needs = snap(**MERGED, issues=(issue(10, 1), issue(11, 2)), needs_human=("issue #11",))
        broken = snap(**MERGED, issues=(issue(10, 1), issue(11, 1)))  # STORY-001 twice
        for snapshot, name in ((needs, st.NEEDS_HUMAN), (broken, st.INCONSISTENT)):
            for command in COMMANDS:
                with self.subTest(command=command, state=name):
                    decision = route(command, result(snapshot))
                    self.assertEqual((decision.action, decision.state), ("stop", name))

    def test_continuing_stops_whenever_the_human_is_needed(self):
        for snapshot in (GATE_A_WAITING, IDLE, snap()):
            decision = route("/factory-start", result(snapshot), continuing=True, after="S05")
            self.assertEqual(decision.action, "stop")

    def test_commands_without_stations(self):
        self.assertEqual(route("/factory-status", result(IDLE)).action, "stop")

    def test_station_file(self):
        self.assertEqual(commands.station_file("S05b"), "stations/S05b-issues.md")
        self.assertEqual(commands.station_file("S05"), "stations/S05-stories.md")
        self.assertIsNone(commands.station_file("S01"))

    def test_scopes(self):
        ids = {s.id for s in load_stations()}
        for spec in COMMANDS.values():
            with self.subTest(command=spec.name):
                self.assertLessEqual(set(spec.stations), ids | set(PENDING))
                self.assertNotIn("S06", spec.stations)
        self.assertEqual(COMMANDS["/factory-start"].stations[0], "S00")
        self.assertNotIn("S05b", COMMANDS["/factory-start"].stations)  # start stops at Gate A
        # /factory-resume can run every station the state engine names in its states.
        planning_stations = {s for s, _ in st.PLAN_DOCS} | {"S05b"}
        self.assertLessEqual(planning_stations, set(COMMANDS["/factory-resume"].stations))


class RouteCliTest(unittest.TestCase):
    def run_cli(self, snapshot, *argv):
        out = io.StringIO()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(Path(tmp.name), "owner/app")), \
                mock.patch.object(st, "collect_snapshot", lambda gh, repo: snapshot), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["route", *argv])
        return code, out.getvalue()

    def test_json(self):
        code, out = self.run_cli(ISSUES_PENDING, "--command", "/factory-resume", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["station_file"], "stations/S05b-issues.md")

    def test_command_name_spellings(self):
        # Regression: Git Bash on Windows turned "/factory-resume" into
        # "C:/Program Files/Git/factory-resume" before Python saw it.
        for spelling in ("factory-resume", "/factory-resume",
                         "C:/Program Files/Git/factory-resume",
                         r"C:\Program Files\Git\factory-resume"):
            with self.subTest(spelling=spelling):
                code, out = self.run_cli(ISSUES_PENDING, "--command", spelling, "--json")
                self.assertEqual((code, json.loads(out)["station"]), (0, "S05b"))

    def test_unknown_command_name(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["route", "--command", "factory-status"])
        self.assertIn("is not one of: factory-resume, factory-start", err.getvalue())

    def test_text_and_continuing(self):
        code, out = self.run_cli(IDLE, "--command", "/factory-resume", "--continuing",
                                 "--after", "S05b")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Target: "))  # the banner comes first (rule T2)
        self.assertTrue(lines[1].startswith("Stop: Stopped at IDLE_AT_GATE_C"))


class CommandFileLintTest(unittest.TestCase):
    """Command files: thin, safe, and wired to the state engine (same checker as T2.4)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctx = guard_context(Path(tmp.name))
        self.files = {p.name: p.read_text(encoding="utf-8")
                      for p in sorted(COMMANDS_DIR.glob("factory-*.md"))}

    def test_planning_commands_exist(self):
        self.assertLessEqual(PLANNING_COMMANDS, set(self.files))
        runners = {f"/{name[:-3]}" for name in self.files} - {
            f"/{name[:-3]}" for name in READ_ONLY}
        self.assertEqual(runners, set(COMMANDS))

    def test_structure(self):
        for name, text in self.files.items():
            with self.subTest(command=name):
                front, body = parse_frontmatter(text)
                self.assertTrue(front.get("description"))
                self.assertIn("Read `stations/_rules.md`", body)
                self.assertLessEqual(len([line for line in body.splitlines() if line.strip()]),
                                     MAX_LINES)
                steps = [int(n) for n in re.findall(r"^(\d+)\. ", body, re.MULTILINE)]
                self.assertEqual(steps, list(range(1, len(steps) + 1)))

    def test_every_command_is_valid_and_allowed_by_the_guard(self):
        for name, text in self.files.items():
            spans = command_spans(text)
            with self.subTest(command=name):
                self.assertTrue(spans)
                for span in spans:
                    self.assertEqual(lint_command(span, self.ctx), [], span)
                for pattern, why in FORBIDDEN:
                    self.assertIsNone(re.search(pattern, text), why)

    def test_station_running_commands_loop_on_route(self):
        for command in COMMANDS:
            text = self.files[f"{command[1:]}.md"]
            with self.subTest(command=command):
                self.assertIn("python scripts/factory.py target show", text)
                self.assertIn("python scripts/factory.py state --json", text)
                name = command[1:]  # no leading slash: Git Bash would rewrite it
                self.assertIn(f"python scripts/factory.py route --command {name} --json", text)
                self.assertIn(f"route --command {name} --continuing --after <SXX>", text)
                self.assertIn("`station_file`", text)
                self.assertIsNone(re.search(r"stations/S\d", text),
                                  "the route names the station, not the command file")
                self.assertNotIn("S06", text)
                self.assertIn("Never merge anything", text)

    def test_read_only_commands_run_no_station_and_change_nothing(self):
        for name, allowed in READ_ONLY.items():
            text = self.files[name]
            with self.subTest(command=name):
                self.assertNotIn("route --command", text)
                self.assertIsNone(re.search(r"stations/S\d", text))
                for span in command_spans(text):
                    self.assertTrue(span.startswith("python scripts/factory.py "), span)
                    words = span.split()[2:4]
                    self.assertTrue(" ".join(words) in allowed or words[0] in allowed, span)

    def test_lint_rejects_arguments_that_git_bash_would_rewrite(self):
        problems = lint_command("python scripts/factory.py route --command /factory-start",
                                self.ctx)
        self.assertTrue(any("Git Bash" in p for p in problems), problems)

    def test_status_answers_what_to_do_next_first(self):
        text = self.files["factory-status.md"]
        self.assertIn("One line: what the human does next", text)

    def test_arguments_are_passed_through(self):
        self.assertIn('target set "$ARGUMENTS"', self.files["factory-target.md"])
        self.assertIn("$ARGUMENTS", self.files["factory-start.md"])
        self.assertIn("argument-hint", self.files["factory-start.md"])


if __name__ == "__main__":
    unittest.main()
