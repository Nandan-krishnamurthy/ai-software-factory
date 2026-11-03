"""T8.1: the headless runner — the loop with a fake Claude adapter, the adapter itself,
the preflight, the run log and the ``run`` command."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, runner, target
from factory import state as s
from factory.errors import CommandNotFound, CommandTimeout, FactoryError
from factory.gh import ProcessResult
from tests import REPO_ROOT, SCRIPTS_DIR

OK = {"type": "result", "subtype": "success", "is_error": False, "result": "done",
      "session_id": "sess-1", "num_turns": 3, "total_cost_usd": 0.25,
      "permission_denials": []}


def st(state, next_station=None, issue=None, pr=None, increment="001-initial"):
    """A ``state --json`` object, built by the real state engine's ``to_dict``."""
    details = {"message": f"{state} message"}
    if issue is not None:
        details["issue"] = issue
    if pr is not None:
        details["pr"] = pr
    return s.StateResult(state, increment, next_station, details=details).to_dict()


def ok(**extra):
    return runner.Invocation(0, {**OK, **extra})


IDLE = st(s.IDLE_AT_GATE_C, "S06")
ISSUES = st(s.ISSUES_PENDING, "S05b")
PLANNING = st(s.PLANNING, "S02")


def in_progress(issue=12, station="S09"):
    return st(s.STORY_IN_PROGRESS, station, issue=issue)


def gate_b(issue=12, pr=20):
    return st(s.GATE_B_WAITING_REVIEW, issue=issue, pr=pr)


class FakeFactory:
    """GitHub's state plus a scripted fake Claude adapter: each invocation moves the
    state to the next scripted step, a state or a ``(state, Invocation)`` pair."""

    def __init__(self, start, steps=(), dirty=()):
        self.current = start
        self.steps = list(steps)
        self.dirty = list(dirty)
        self.sent = []
        self.records = []

    def read_state(self):
        return self.current

    def invoke(self, command):
        self.sent.append(command)
        if not self.steps:
            raise AssertionError(f"unexpected invocation of /{command}")
        step = self.steps.pop(0)
        after, result = step if isinstance(step, tuple) else (step, ok())
        self.current = after
        return result

    def run(self, command, **limits):
        return runner.run_until_gate(
            command, read_state=self.read_state, read_dirty=lambda: self.dirty,
            invoke=self.invoke, log=self.records.append, limits=runner.Limits(**limits))


CONTINUE, RESUME = "factory-continue", "factory-resume"


class OneStoryTest(unittest.TestCase):
    """Acceptance criterion 1: a runner given continue stops at Gate B after exactly one
    story. ``--command continue`` is one human "continue" (D2)."""

    def test_continue_stops_at_gate_b_after_exactly_one_story(self):
        fake = FakeFactory(IDLE, [gate_b()])
        out = fake.run("continue")
        self.assertEqual((out.exit_code, out.invocations, out.stories_started),
                         (runner.EXIT_GATE, 1, (12,)))
        self.assertEqual(fake.sent, [CONTINUE])
        self.assertIn("GATE_B_WAITING_REVIEW", out.reason)

    def test_after_the_story_starts_the_runner_sends_resume(self):
        fake = FakeFactory(IDLE, [in_progress(station="S08"), in_progress(station="S10"),
                                  gate_b()])
        out = fake.run("continue")
        self.assertEqual(fake.sent, [CONTINUE, RESUME, RESUME])
        self.assertEqual((out.exit_code, out.stories_started), (runner.EXIT_GATE, (12,)))

    def test_continue_from_close_out_starts_exactly_one_story(self):
        closeout = st(s.CLOSEOUT_PENDING, "S12", issue=11, pr=19)
        fake = FakeFactory(closeout, [in_progress(issue=12), gate_b(issue=12, pr=21)])
        out = fake.run("continue")
        self.assertEqual(fake.sent, [CONTINUE, RESUME])
        self.assertEqual((out.exit_code, out.stories_started), (runner.EXIT_GATE, (12,)))

    def test_finishing_a_story_already_in_flight_starts_none(self):
        fake = FakeFactory(in_progress(issue=12), [gate_b(issue=12)])
        out = fake.run("continue")
        self.assertEqual((out.exit_code, out.stories_started), (runner.EXIT_GATE, ()))
        self.assertEqual(fake.sent, [CONTINUE])

    def test_continue_is_kept_while_no_story_has_started(self):
        # The first session created the issues and ended before picking: the human's one
        # continue has not started a story yet, so it is still continue.
        fake = FakeFactory(ISSUES, [IDLE, gate_b()])
        out = fake.run("continue")
        self.assertEqual(fake.sent, [CONTINUE, CONTINUE])
        self.assertEqual((out.exit_code, out.stories_started), (runner.EXIT_GATE, (12,)))

    def test_a_second_new_story_stops_the_run(self):
        fake = FakeFactory(IDLE, [in_progress(issue=12), in_progress(issue=13)])
        out = fake.run("continue")
        self.assertEqual(out.exit_code, runner.EXIT_NEEDS_HUMAN)
        self.assertEqual(out.stories_started, (12, 13))
        self.assertIn("#12, #13", out.reason)
        self.assertEqual(fake.sent, [CONTINUE, RESUME])

    def test_resume_never_sends_continue(self):
        fake = FakeFactory(in_progress(station="S08"),
                           [in_progress(station="S09"), in_progress(station="S11"), gate_b()])
        out = fake.run("resume")
        self.assertEqual(fake.sent, [RESUME, RESUME, RESUME])
        self.assertEqual(out.exit_code, runner.EXIT_GATE)

    def test_resume_does_not_start_a_story_at_gate_c(self):
        fake = FakeFactory(IDLE)
        out = fake.run("resume")
        self.assertEqual((out.exit_code, out.invocations, fake.sent), (runner.EXIT_GATE, 0, []))

    def test_a_story_started_under_resume_stops_the_run(self):
        closeout = st(s.CLOSEOUT_PENDING, "S12", issue=11, pr=19)
        fake = FakeFactory(closeout, [in_progress(issue=12)])
        out = fake.run("resume")
        self.assertEqual(out.exit_code, runner.EXIT_NEEDS_HUMAN)
        self.assertIn("resume may start 0", out.reason)

    def test_resume_closes_out_and_stops_at_gate_c(self):
        closeout = st(s.CLOSEOUT_PENDING, "S12", issue=12, pr=20)
        fake = FakeFactory(closeout, [IDLE])
        out = fake.run("resume")
        self.assertEqual((out.exit_code, fake.sent), (runner.EXIT_GATE, [RESUME]))
        self.assertIn("IDLE_AT_GATE_C", out.reason)


class StopConditionTest(unittest.TestCase):
    """Acceptance criteria 2 and 3: never past a gate, and a non-zero exit with the
    reason on NEEDS_HUMAN; plus every other stop."""

    GATES = [
        st(s.GATE_A_WAITING), gate_b(), st(s.GATE_B_APPROVED_UNMERGED, issue=12, pr=20),
        st(s.INCREMENT_COMPLETE), st(s.UNCONFIGURED, increment=None),
    ]

    def test_a_gate_stops_before_any_invocation(self):
        for start in self.GATES:
            for command in ("continue", "resume"):
                with self.subTest(state=start["state"], command=command):
                    fake = FakeFactory(start)
                    out = fake.run(command)
                    self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_GATE, 0))
                    self.assertEqual(fake.sent, [])

    def test_never_continues_past_a_gate_it_reaches(self):
        for reached in (st(s.GATE_A_WAITING), gate_b()):
            with self.subTest(gate=reached["state"]):
                fake = FakeFactory(PLANNING if reached["state"] == s.GATE_A_WAITING
                                   else in_progress(), [reached, gate_b()])
                out = fake.run("resume", max_invocations=10)
                self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_GATE, 1))
                self.assertEqual(len(fake.steps), 1)  # the next step was never taken

    def test_needs_human_and_inconsistent_exit_non_zero_with_the_reason(self):
        for bad in (s.NEEDS_HUMAN, s.INCONSISTENT):
            with self.subTest(state=bad, when="at the start"):
                fake = FakeFactory(st(bad))
                out = fake.run("continue")
                self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NEEDS_HUMAN, 0))
                self.assertNotEqual(out.exit_code, 0)
                self.assertIn(f"{bad} message", out.reason)
            with self.subTest(state=bad, when="after an invocation"):
                fake = FakeFactory(in_progress(), [st(bad, issue=12)])
                out = fake.run("resume", max_invocations=10)
                self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NEEDS_HUMAN, 1))
                self.assertIn(bad, out.reason)

    def test_uncommitted_changes_stop_without_invoking_claude(self):
        fake = FakeFactory(in_progress(), dirty=[" M src/app.ts"])
        out = fake.run("resume")
        self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NEEDS_HUMAN, 0))
        self.assertIn("uncommitted", out.reason)

    def test_no_progress_stops_after_n_unchanged_invocations(self):
        for n in (1, 2, 3):
            with self.subTest(max_no_progress=n):
                fake = FakeFactory(in_progress(), [in_progress()] * 5)
                out = fake.run("resume", max_no_progress=n)
                self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NO_PROGRESS, n))
                self.assertIn("No progress", out.reason)

    def test_the_default_no_progress_cut_off_is_two(self):
        fake = FakeFactory(in_progress(), [in_progress()] * 5)
        self.assertEqual(fake.run("resume").invocations, 2)

    def test_progress_resets_the_no_progress_count(self):
        fake = FakeFactory(in_progress(station="S09"),
                           [in_progress(station="S09"), in_progress(station="S10"),
                            in_progress(station="S10"), in_progress(station="S10")])
        out = fake.run("resume")
        self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NO_PROGRESS, 4))

    def test_the_invocation_cap_holds(self):
        steps = [in_progress(station="S10" if i % 2 == 0 else "S09") for i in range(20)]
        fake = FakeFactory(in_progress(station="S09"), steps)
        out = fake.run("resume", max_invocations=5)
        self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_NO_PROGRESS, 5))
        self.assertIn("limit", out.reason)

    def test_the_default_invocation_cap_is_twelve(self):
        steps = [in_progress(station="S10" if i % 2 == 0 else "S09") for i in range(20)]
        fake = FakeFactory(in_progress(station="S09"), steps)
        self.assertEqual(fake.run("resume").invocations, 12)

    def test_permission_denials_stop_and_say_what_was_denied(self):
        denied = ok(permission_denials=[
            {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "npm test"}},
            {"tool_name": "WebFetch", "tool_use_id": "t2", "tool_input": {"url": "x"}}])
        # Even though the state moved on, the runner stops after that invocation (R5).
        fake = FakeFactory(in_progress(station="S08"), [(in_progress(station="S09"), denied),
                                                        gate_b()])
        out = fake.run("resume")
        self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_DENIED, 1))
        self.assertIn("Bash 'npm test'", out.reason)
        self.assertIn("WebFetch", out.reason)

    def test_r5_holds_for_the_l4_closeout_run(self):
        # The real result of the L4 close-out run (20261103T091002Z): S12 completed and the
        # state reached Gate C, but the session had two recovered denials. R5 is unchanged:
        # the run stops with exit 6 and names both, though the state moved on.
        denied = ok(permission_denials=[
            {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {
                "command": 'python scripts/factory.py git status --porcelain; echo "rc=$?"; '
                           'echo "---"; python scripts/factory.py closeout --issue 2 --json; '
                           'echo "rc=$?"', "description": "status and close-out"}},
            {"tool_name": "Bash", "tool_use_id": "t2", "tool_input": {
                "command": 'python -c "import tempfile; print(tempfile.gettempdir())"'}}])
        closeout = st(s.CLOSEOUT_PENDING, "S12", issue=2, pr=7)
        fake = FakeFactory(closeout, [(IDLE, denied)])
        out = fake.run("resume")
        self.assertEqual((out.exit_code, out.invocations), (runner.EXIT_DENIED, 1))
        self.assertIn("closeout --issue 2 --json", out.reason)
        self.assertIn("tempfile.gettempdir", out.reason)
        self.assertEqual(fake.records[0]["after"]["state"], s.IDLE_AT_GATE_C)

    def test_claude_failures_stop_the_run(self):
        cases = {
            "timed out": runner.Invocation(None, None, "partial", timed_out=True),
            "no JSON result": runner.Invocation(0, None, "not json"),
            "non-zero exit": runner.Invocation(1, {**OK, "is_error": False}),
            "is_error": runner.Invocation(0, {**OK, "is_error": True,
                                              "subtype": "error_during_execution"}),
        }
        for label, result in cases.items():
            with self.subTest(label):
                fake = FakeFactory(in_progress(station="S08"),
                                   [(in_progress(station="S09"), result), gate_b()])
                out = fake.run("resume")
                self.assertEqual((out.exit_code, out.invocations),
                                 (runner.EXIT_CLAUDE_FAILED, 1))

    def test_a_state_read_error_propagates(self):
        fake = FakeFactory(in_progress(), [in_progress(station="S10")])
        calls = {"n": 0}

        def read_state():
            calls["n"] += 1
            if calls["n"] > 1:
                raise FactoryError("GitHub is down")
            return fake.current

        with self.assertRaisesRegex(FactoryError, "GitHub is down"):
            runner.run_until_gate("resume", read_state=read_state, read_dirty=list,
                                  invoke=fake.invoke, log=fake.records.append)

    def test_an_unknown_command_is_refused(self):
        with self.assertRaises(runner.RunnerError):
            FakeFactory(IDLE).run("start")


class RunLogRecordTest(unittest.TestCase):
    def test_one_record_per_invocation(self):
        fake = FakeFactory(IDLE, [in_progress(station="S08"), gate_b()])
        fake.run("continue")
        self.assertEqual([r["n"] for r in fake.records], [1, 2])
        first = fake.records[0]
        self.assertEqual(first["event"], "invocation")
        self.assertEqual(first["sent"], "/factory-continue")
        self.assertEqual(first["before"]["state"], s.IDLE_AT_GATE_C)
        self.assertEqual(first["after"], {"state": s.STORY_IN_PROGRESS, "increment":
                                          "001-initial", "next_station": "S08", "issue": 12,
                                          "pr": None})
        self.assertEqual((first["session_id"], first["exit_code"]), ("sess-1", 0))
        self.assertEqual(fake.records[1]["sent"], "/factory-resume")
        json.dumps(fake.records)  # serialisable as JSON Lines

    def test_run_log_writes_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = runner.RunLog(Path(tmp), "resume")
            log.write({"event": "start"})
            log.write({"event": "stop", "exit_code": 0})
            self.assertEqual(log.path.parent, Path(tmp) / ".factory-local" / "runs")
            self.assertTrue(log.path.name.endswith("-resume.jsonl"))
            lines = [json.loads(x) for x in log.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([x["event"] for x in lines], ["start", "stop"])
            self.assertTrue(all("time" in x for x in lines))


class AdapterTest(unittest.TestCase):
    """The one adapter function, and the flags it may never pass."""

    def test_the_exact_command_line(self):
        self.assertEqual(runner.claude_argv("claude", "factory-continue"),
                         ["claude", "-p", "/factory-continue", "--output-format", "json",
                          "--append-system-prompt", runner.HEADLESS_RULES,
                          "--allowedTools", "Edit", "Write", "MultiEdit",
                          "--disallowedTools", "PowerShell"])

    def test_the_headless_rules_name_every_l4_failure(self):
        # Each phrase answers a denial seen in the L4 runs (chains with `$?`, `-v` and
        # `discover` variants, `python -c` and heredocs, `printf >>`, `rm`, `$TEMP`,
        # tempfile probes, reading .claude/ settings).
        rules = runner.HEADLESS_RULES
        for phrase in ("S15", "S16", "own Bash call", "exactly as the station writes it",
                       "`;`", "`&&`", "`||`", "`|`", "cd <T> && <command>", "`echo`", "`$?`",
                       "`2>&1`", "`$TEMP`", "`python -c`", "heredoc", "Write and", "Edit tools",
                       "shell redirection", "`rm`", "`python scripts/factory.py scratch`",
                       "(.claude/settings.json and .claude/settings.local.json)",
                       "report it and stop"):
            with self.subTest(phrase):
                self.assertIn(phrase, rules)
        # S16 covers the settings files only: S10 must still see the verifier's agent file.
        self.assertNotIn("(.claude/)", rules)
        runner.check_argv(["claude", "--append-system-prompt", rules])  # nothing forbidden
        for bad in runner.FORBIDDEN_VALUES + runner.FORBIDDEN_FLAGS:
            self.assertNotIn(bad, rules)

    def test_the_rules_match_stations_rules_s15_and_s16(self):
        # The appended text restates the station rules; both must keep saying the same.
        rules_md = (REPO_ROOT / "stations" / "_rules.md").read_text(encoding="utf-8")
        for rule in ("| S15 | **One command per call", "| S16 | **Never read, change or "
                     "investigate Claude Code's settings"):
            self.assertIn(rule, rules_md)
        for phrase in ("`python -c`", "heredoc", "`rm`", "`$?`", "`2>&1`",
                       "`python scripts/factory.py scratch`", "`cd <T> && <command>`"):
            with self.subTest(phrase):
                self.assertIn(phrase, rules_md)

    def test_the_environment_keeps_the_shell_in_the_factory_root(self):
        self.assertEqual(runner.HEADLESS_ENV, {"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"})
        base = {"PATH": "x", "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "0"}
        env = runner.claude_env(base)
        self.assertEqual(env, {"PATH": "x", "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"})
        self.assertEqual(base["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"], "0")  # a copy
        with mock.patch.dict(os.environ, {"FACTORY_TEST_MARK": "kept"}):
            env = runner.claude_env()
            self.assertEqual(env["FACTORY_TEST_MARK"], "kept")
            self.assertNotIn("CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR", os.environ)

    def test_a_batch_file_shim_is_refused(self):
        # cmd.exe would interpret `|`, `&&` and `%VAR%` in the appended rules.
        for shim in ("C:/npm/claude.cmd", "C:/npm/claude.BAT"):
            with self.subTest(shim), mock.patch.object(runner.shutil, "which",
                                                       return_value=shim):
                with self.assertRaisesRegex(runner.RunnerError, "batch-file shim"):
                    runner.find_claude()
        with mock.patch.object(runner.shutil, "which", return_value="C:/bin/claude.EXE"):
            self.assertEqual(runner.find_claude(), "C:/bin/claude.EXE")

    def test_powershell_is_removed_and_r1_is_unchanged(self):
        # Live checks L2 and L3: PowerShell is Claude Code's primary shell on Windows, and
        # the factory's allow rules name only Bash forms, so a headless PowerShell call is
        # denied and stops the run. The runner removes the tool; it never allows it.
        self.assertEqual(runner.ALLOWED_TOOLS, ("Edit", "Write", "MultiEdit"))  # R1
        self.assertEqual(runner.DISALLOWED_TOOLS, ("PowerShell",))
        for command in runner.COMMANDS.values():
            with self.subTest(command):
                argv = runner.claude_argv("claude", command)
                allowed = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
                denied = argv[argv.index("--disallowedTools") + 1:]
                self.assertEqual(allowed, ["Edit", "Write", "MultiEdit"])
                self.assertEqual(denied, ["PowerShell"])
                self.assertEqual(argv.count("PowerShell"), 1)  # only ever as a denial
                self.assertNotIn("Bash", argv)  # Bash keeps the factory's own rules

    def test_no_bypass_or_skip_permissions_flag_is_ever_passed(self):
        for command in runner.COMMANDS.values():
            argv = runner.claude_argv("claude", command)
            joined = " ".join(argv)
            for bad in ("dangerously", "--permission-mode", "bypassPermissions",
                        "acceptEdits", "--permission-prompt-tool"):
                self.assertNotIn(bad, joined)

    def test_check_argv_refuses_every_forbidden_spelling(self):
        for bad in (["--dangerously-skip-permissions"], ["--allow-dangerously-skip-permissions"],
                    ["--permission-mode", "bypassPermissions"],
                    ["--permission-mode=acceptEdits"], ["--permission-mode", "plan"],
                    ["--permission-prompt-tool", "mcp__x"], ["--settings", "bypassPermissions"]):
            with self.subTest(bad):
                with self.assertRaises(runner.RunnerError):
                    runner.check_argv(["claude", "-p", "/factory-resume", *bad])

    def test_invoke_runs_the_adapter_command_in_the_given_folder(self):
        seen = {}

        def fake_run(argv, *, timeout, cwd=None, env=None, input=None):
            seen.update(argv=argv, timeout=timeout, cwd=cwd, env=env, input=input)
            return ProcessResult(argv, 0, json.dumps(OK), "")

        with mock.patch.object(runner, "run_process", fake_run):
            inv = runner.invoke_claude("factory-resume", cwd=Path("/f"), timeout_s=90,
                                       executable="claude-x")
        self.assertEqual(seen["argv"], runner.claude_argv("claude-x", "factory-resume"))
        self.assertEqual((seen["cwd"], seen["timeout"], seen["input"]), (Path("/f"), 90, None))
        self.assertEqual(seen["env"], runner.claude_env())
        self.assertEqual(seen["env"]["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"], "1")
        self.assertEqual(inv.result["session_id"], "sess-1")
        self.assertIsNone(inv.failure(90))

    def test_invoke_reports_a_timeout(self):
        def fake_run(argv, **_):
            raise CommandTimeout(argv, None, "half", "", detail="timed out")

        with mock.patch.object(runner, "run_process", fake_run):
            inv = runner.invoke_claude("factory-resume", cwd=Path("."), timeout_s=60,
                                       executable="claude")
        self.assertTrue(inv.timed_out)
        self.assertIn("1 minutes", inv.failure(60))

    def test_a_missing_claude_is_an_error(self):
        def fake_run(argv, **_):
            raise CommandNotFound(argv, None, "", "nope")

        with mock.patch.object(runner, "run_process", fake_run), \
                self.assertRaises(runner.RunnerError):
            runner.invoke_claude("factory-resume", cwd=Path("."), timeout_s=60,
                                 executable="claude")
        with mock.patch.object(runner.shutil, "which", return_value=None), \
                self.assertRaises(runner.RunnerError):
            runner.find_claude()

    def test_parse_result(self):
        self.assertEqual(runner.parse_result(json.dumps(OK)), OK)
        noisy = "warning: something\n" + json.dumps(OK) + "\n"
        self.assertEqual(runner.parse_result(noisy), OK)
        self.assertIsNone(runner.parse_result(""))
        self.assertIsNone(runner.parse_result('{"type": "assistant"}'))
        self.assertIsNone(runner.parse_result("[1, 2]"))

    def test_denials_tolerate_odd_shapes(self):
        self.assertEqual(runner.Invocation(0, {**OK, "permission_denials": None}).denials, [])
        self.assertEqual(runner.Invocation(0, {**OK, "permission_denials": "x"}).denials, [])
        self.assertEqual(runner.Invocation(0, None).denials, [])

    def test_the_runner_has_no_merge_path_and_never_sets_the_target(self):
        source = (SCRIPTS_DIR / "factory" / "runner.py").read_text(encoding="utf-8")
        # It reaches GitHub and git only through the state engine and `ensure.dirty_files`
        # (wired in cli._run), and Claude only through `invoke_claude`.
        for forbidden in ("set_target", "target set", "pr merge", "git push", "Gh(", "Git(",
                          "import subprocess", "run_command_line"):
            self.assertNotIn(forbidden, source)


class ScratchCommandTest(unittest.TestCase):
    """``factory.py scratch``: the literal <SCRATCH> path, so no session needs `$TEMP` or a
    tempfile script to find it (rule S15; the L4 runs)."""

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_prints_the_folder_the_factory_and_the_guard_use(self):
        code, out = self.run_cli("scratch")
        self.assertEqual((code, out), (0, str(Path(tempfile.gettempdir())) + "\n"))
        from factory import evidence
        self.assertEqual(Path(out.strip()), evidence.default_path(2).parent)

    def test_json(self):
        code, out = self.run_cli("scratch", "--json")
        folder = str(Path(tempfile.gettempdir()))
        self.assertEqual((code, json.loads(out)), (0, {"scratch": folder}))

    def test_needs_no_target_and_is_allowed_by_the_guard_in_both_modes(self):
        from factory import guard
        with mock.patch.object(target, "get_target", side_effect=AssertionError("no target")):
            self.assertEqual(self.run_cli("scratch")[0], 0)
        for target_root in (Path(tempfile.gettempdir()) / "app", None):
            ctx = guard.GuardContext(
                factory_root=Path(tempfile.gettempdir()) / "factory", target_root=target_root,
                cwd=Path(tempfile.gettempdir()) / "factory", default_branch="main",
                scratch_dirs=(Path(tempfile.gettempdir()),), extra_write_dirs=(),
                current_branch=lambda d: "main", is_reviewed=lambda b, d: None)
            call = {"command": "python scripts/factory.py scratch"}
            with self.subTest(target=target_root):
                self.assertTrue(guard.decide("Bash", call, ctx).allowed)


class PreflightTest(unittest.TestCase):
    """The static check that the factory's project settings still run the guard."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".claude").mkdir()
        self.settings = self.root / ".claude" / "settings.json"
        shutil.copy(REPO_ROOT / ".claude" / "settings.json", self.settings)

    def test_the_real_settings_pass(self):
        runner.check_hooks(REPO_ROOT)
        runner.check_hooks(self.root)

    def test_missing_or_broken_settings_fail(self):
        self.settings.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(runner.RunnerError, "missing or unreadable"):
            runner.check_hooks(self.root)
        self.settings.unlink()
        with self.assertRaisesRegex(runner.RunnerError, "missing or unreadable"):
            runner.check_hooks(self.root)

    def test_settings_without_the_guard_fail(self):
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        guard_hooks = data["hooks"]["PreToolUse"][0]["hooks"]
        for broken in ({}, {"PreToolUse": []},
                       {"PreToolUse": [{"matcher": "Bash", "hooks": guard_hooks}]},
                       {"PreToolUse": [{"matcher": "Bash|PowerShell|Edit|Write",
                                        "hooks": [{"type": "command", "command": "echo ok"}]}]}):
            with self.subTest(broken):
                self.settings.write_text(json.dumps({**data, "hooks": broken}), encoding="utf-8")
                with self.assertRaisesRegex(runner.RunnerError, "does not run the factory guard"):
                    runner.check_hooks(self.root)

    def test_disable_all_hooks_fails(self):
        for name in ("settings.json", "settings.local.json"):
            with self.subTest(name):
                path = self.root / ".claude" / name
                data = json.loads(self.settings.read_text(encoding="utf-8")) \
                    if name == "settings.json" else {}
                original = path.read_text(encoding="utf-8") if path.exists() else None
                path.write_text(json.dumps({**data, "disableAllHooks": True}), encoding="utf-8")
                with self.assertRaisesRegex(runner.RunnerError, "disableAllHooks"):
                    runner.check_hooks(self.root)
                if original is None:
                    path.unlink()
                else:
                    path.write_text(original, encoding="utf-8")


class RunCommandTest(unittest.TestCase):
    """``factory.py run``: who may start it (R2), and how it wires the loop."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.factory = self.root / "factory"
        (self.factory / ".claude").mkdir(parents=True)
        shutil.copy(REPO_ROOT / ".claude" / "settings.json", self.factory / ".claude")
        self.app = self.root / "app"
        self.app.mkdir()
        self.active = target.Target(self.app, "owner/app")

    def run_cli(self, *argv, stdin="y\n", claude=False, outcome=None):
        out, err = io.StringIO(), io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        if claude:
            env["CLAUDECODE"] = "1"
        self.loop = mock.Mock(return_value=outcome or runner.Outcome(0, "Stopped at Gate B.", 1,
                                                                     (12,)))
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                mock.patch.object(target, "get_target", return_value=self.active) as get, \
                mock.patch.object(runner, "find_claude", return_value="claude"), \
                mock.patch.object(runner, "run_until_gate", self.loop), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        self.get_target = get
        return code, out.getvalue(), err.getvalue()

    def logs(self):
        folder = self.factory / runner.RUNS_DIR
        return sorted(folder.glob("*.jsonl")) if folder.exists() else []

    def test_refused_inside_claude_code(self):
        for command in ("continue", "resume"):
            with self.subTest(command):
                code, _, err = self.run_cli("run", "--until-gate", "--command", command,
                                            claude=True)
                self.assertEqual(code, 2)
                self.assertIn("only by a human in a real terminal", err)
                self.get_target.assert_not_called()
                self.loop.assert_not_called()
        self.assertEqual(self.logs(), [])

    def test_continue_needs_the_terminal_confirmation(self):
        for answer in ("", "n\n", "no\n", "maybe\n"):
            with self.subTest(answer=answer):
                code, _, err = self.run_cli("run", "--until-gate", "--command", "continue",
                                            stdin=answer)
                self.assertEqual(code, 1)
                self.assertIn("aborted: nothing was started", err)
                self.loop.assert_not_called()
        self.assertEqual(self.logs(), [])

    def test_continue_confirmed_runs_the_loop_and_logs(self):
        code, out, _ = self.run_cli("run", "--until-gate", "--command", "continue")
        self.assertEqual(code, 0)
        self.assertIn("Target: ", out)
        self.assertIn("Stopped at Gate B.", out)
        self.loop.assert_called_once()
        self.assertEqual(self.loop.call_args.args, ("continue",))
        limits = self.loop.call_args.kwargs["limits"]
        self.assertEqual((limits.max_no_progress, limits.max_invocations, limits.timeout_s),
                         (2, 12, 3600.0))
        [log] = self.logs()
        records = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["event"] for r in records], ["start", "stop"])
        self.assertEqual(records[0]["argv"], runner.claude_argv("claude", "<command>"))
        self.assertEqual(records[0]["cwd"], str(self.factory))
        self.assertEqual(records[1]["stories_started"], [12])

    def test_resume_asks_nothing_and_passes_the_overrides(self):
        code, _, _ = self.run_cli("run", "--until-gate", "--command", "resume",
                                  "--max-no-progress", "3", "--max-invocations", "4",
                                  "--timeout-minutes", "1.5", stdin="")
        self.assertEqual(code, 0)
        limits = self.loop.call_args.kwargs["limits"]
        self.assertEqual((limits.max_no_progress, limits.max_invocations, limits.timeout_s),
                         (3, 4, 90.0))

    def test_a_non_zero_outcome_is_the_exit_code(self):
        code, _, err = self.run_cli("run", "--until-gate", "--command", "resume",
                                    outcome=runner.Outcome(runner.EXIT_NEEDS_HUMAN,
                                                           "NEEDS_HUMAN: help", 0))
        self.assertEqual(code, runner.EXIT_NEEDS_HUMAN)
        self.assertIn("NEEDS_HUMAN: help", err)

    def test_the_preflight_runs_before_anything_starts(self):
        (self.factory / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        code, _, err = self.run_cli("run", "--until-gate", "--command", "resume")
        self.assertEqual(code, 1)
        self.assertIn("does not run the factory guard", err)
        self.loop.assert_not_called()

    def test_until_gate_is_required_and_only_two_commands_exist(self):
        for argv in (["run", "--command", "resume"],
                     ["run", "--until-gate", "--command", "start"],
                     ["run", "--until-gate"]):
            with self.subTest(argv), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                cli.build_parser().parse_args(argv)


if __name__ == "__main__":
    unittest.main()
