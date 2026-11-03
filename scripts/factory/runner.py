"""The headless runner: ``factory.py run --until-gate`` (T8.1, architecture §11).

The loop::

    state → route → claude -p "/factory-<command>" → state → route → …

It runs the factory unattended **between** gates, never past them. Before every Claude
invocation it asks the same pure ``commands.route`` the command files use, so it invokes
Claude only when that command would run a station. It stops:

* at any gate, or any state that waits on the human (exit 0, ``EXIT_GATE``);
* at ``NEEDS_HUMAN`` or ``INCONSISTENT``, or when route stops while the factory is the
  one waiting, such as on uncommitted changes (``EXIT_NEEDS_HUMAN``);
* when the state has not changed after ``max_no_progress`` invocations in a row, or after
  ``max_invocations`` invocations (``EXIT_NO_PROGRESS``);
* when Claude fails, times out or prints no JSON result (``EXIT_CLAUDE_FAILED``);
* when Claude's result lists permission denials: a headless session cannot ask the human,
  so anything it would have asked about is a stop, never a workaround (``EXIT_DENIED``).

**One story per continue** (D2). ``--command continue`` is one human "continue": the
runner sends ``/factory-continue`` only until a story that was not active at the start
becomes active, and ``/factory-resume`` after that. ``/factory-continue`` itself never
starts a second story within a session (``commands.route``), and ``/factory-resume``
never starts one. A second new story stops the run as a defence in depth.

**One adapter.** Every Claude invocation goes through ``invoke_claude`` (the executable,
the arguments and the working directory), so T9.9 can switch to target-root invocation in
one place. Its arguments never include a bypass or skip-permissions flag
(``check_argv``): the guard hook and the factory's permission rules stay in force, only
the file-editing tools are pre-allowed (``ALLOWED_TOOLS``, decision R1), and the
PowerShell tool is removed from the session (``DISALLOWED_TOOLS``), so Claude's shell is
Bash.

**Headless discipline.** A denial stops the run even when the session recovers from it
(R5), so the runner removes the reasons a session improvises (the L4 runs):

* ``HEADLESS_ENV`` returns the Bash tool to the factory root after every command, so
  ``python scripts/factory.py …`` always resolves, never from inside the target;
* ``HEADLESS_RULES`` is appended to every session's system prompt
  (``--append-system-prompt``): rules S15 and S16 of ``stations/_rules.md``, one command
  per call, no shell-made files, no scripts, the scratch folder from ``factory.py scratch``.

Who may start it is decided in ``cli._run`` (decision R2): a human in a terminal only.
"""

import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory import commands
from factory import state as state_mod
from factory.errors import CommandNotFound, CommandTimeout, FactoryError
from factory.gh import run_process

COMMANDS = {"continue": "factory-continue", "resume": "factory-resume"}
# R1: only the file-editing tools are pre-allowed. Everything else follows the factory's
# own permission rules (.claude/settings.json); a tool those rules would ask about is
# denied in a headless session, and the runner stops (R5).
ALLOWED_TOOLS = ("Edit", "Write", "MultiEdit")
# Removed from the headless session entirely (a bare-name deny, a restriction). On Windows
# with Git Bash, Claude Code makes PowerShell the primary shell, but the factory's allow
# rules name only Bash forms, so its PowerShell calls were denied and stopped the run
# (live checks L2, L3). Without PowerShell, Claude uses Bash, which the rules and the guard
# already cover.
DISALLOWED_TOOLS = ("PowerShell",)
# Never passed (R1): any of these would weaken or bypass the permission checks.
FORBIDDEN_FLAGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
                   "--permission-mode", "--permission-prompt-tool")
FORBIDDEN_VALUES = ("bypassPermissions", "acceptEdits")
# Set for the Claude process only. Claude Code keeps the Bash working directory between
# calls; after `cd <T> && <command>`, a relative `python scripts/factory.py` failed and
# the absolute form matched no allow rule (L4). This returns the main session's shell to
# the factory root after each command. It is not a permission.
HEADLESS_ENV = {"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"}
# Appended to the system prompt of every headless session: what rules S15 and S16 say, so
# the session reads it whatever station it runs. No session can ask the human, so every
# command it improvises is a denial, and a denial stops the run (R5).
HEADLESS_RULES = (
    "This is a headless factory run: nobody can answer a permission prompt, and any "
    "refused command stops the run. Follow rules S15 and S16 of stations/_rules.md "
    "strictly. Run each command as its own Bash call, exactly as the station writes it. "
    "Never chain commands with `;`, `&&`, `||` or `|`; the one exception is "
    "`cd <T> && <command>` for a command from .factory/config.json. Never add `echo`, "
    "`$?`, `2>&1`, or a variable such as `$TEMP` to a command: a failed command always "
    "shows its exit code, so an empty result means success. Never run `python -c`, a "
    "heredoc, or a script of your own. Create and change files only with the Write and "
    "Edit tools, never with shell redirection, and never delete files with `rm`. "
    "<SCRATCH> is the folder `python scripts/factory.py scratch` prints: use that literal "
    "path. Never read, change or investigate Claude Code's settings or permission files "
    "(.claude/settings.json and .claude/settings.local.json). If a command is refused, "
    "report it and stop; do not try another way.")

DEFAULT_MAX_NO_PROGRESS = 2  # R4
DEFAULT_MAX_INVOCATIONS = 12
DEFAULT_TIMEOUT_MINUTES = 60
RUNS_DIR = Path(".factory-local") / "runs"  # R3: Claude cannot write here (T1)

EXIT_GATE = 0
EXIT_NEEDS_HUMAN = 3
EXIT_NO_PROGRESS = 4
EXIT_CLAUDE_FAILED = 5
EXIT_DENIED = 6

# States in which a story is active: the one story in flight (invariant 1). A story in
# CLOSEOUT_PENDING was merged by the human, so closing it out starts nothing.
_ACTIVE_STORY_STATES = frozenset({
    state_mod.STORY_IN_PROGRESS, state_mod.GATE_B_WAITING_REVIEW,
    state_mod.GATE_B_CHANGES_REQUESTED, state_mod.GATE_B_APPROVED_UNMERGED,
})
_TAIL = 600  # characters of Claude's output kept for a failure message and the log


class RunnerError(FactoryError):
    """The runner cannot start, or cannot go on safely."""


# ----------------------------------------------------------------------------- adapter


@dataclass(frozen=True)
class Invocation:
    """What one ``claude -p`` invocation returned."""

    exit_code: int | None  # None when it timed out
    result: dict[str, Any] | None  # the JSON result message, None if there was none
    output_tail: str = ""  # the end of stdout and stderr, for a failure message
    timed_out: bool = False
    seconds: float = 0.0

    @property
    def denials(self) -> list[dict[str, Any]]:
        found = (self.result or {}).get("permission_denials") or []
        return [d for d in found if isinstance(d, dict)] if isinstance(found, list) else []

    def failure(self, timeout_s: float) -> str | None:
        if self.timed_out:
            return f"Claude did not finish within {timeout_s / 60:g} minutes and was stopped."
        if self.result is None:
            return (f"Claude printed no JSON result (exit code {self.exit_code}). "
                    f"Output: {self.output_tail or '(none)'}")
        if self.exit_code != 0 or self.result.get("is_error"):
            subtype = self.result.get("subtype", "?")
            text = str(self.result.get("result", ""))[-_TAIL:]
            return (f"Claude reported an error (exit code {self.exit_code}, {subtype}): "
                    f"{text or self.output_tail or '(no message)'}")
        return None


def claude_argv(executable: str, command: str) -> list[str]:
    """The whole command line for one headless invocation of ``/<command>``."""
    argv = [executable, "-p", f"/{command}", "--output-format", "json",
            "--append-system-prompt", HEADLESS_RULES,
            "--allowedTools", *ALLOWED_TOOLS, "--disallowedTools", *DISALLOWED_TOOLS]
    check_argv(argv)
    return argv


def claude_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The Claude process's environment: the runner's own, plus ``HEADLESS_ENV``."""
    env = dict(os.environ if base is None else base)
    env.update(HEADLESS_ENV)
    return env


def check_argv(argv: list[str]) -> None:
    """Refuse any bypass or skip-permissions flag (R1), however it is spelled."""
    for arg in argv[1:]:
        flag = arg.split("=", 1)[0]
        if flag in FORBIDDEN_FLAGS or any(v in arg for v in FORBIDDEN_VALUES):
            raise RunnerError(f"refusing to start Claude with {arg!r}: the runner never "
                              "bypasses or loosens the permission checks (T8.1).")


def find_claude() -> str:
    found = shutil.which("claude")
    if found is None:
        raise RunnerError("the `claude` command was not found on PATH; install Claude Code.")
    if Path(found).suffix.lower() in (".cmd", ".bat"):
        # cmd.exe would interpret `|`, `&&` and `%VAR%` in HEADLESS_RULES: fail closed.
        raise RunnerError(f"{found} is a batch-file shim; the runner needs the native "
                          "`claude` executable (claude.exe).")
    return found


def invoke_claude(command: str, *, cwd: Path, timeout_s: float,
                  executable: str | None = None) -> Invocation:
    """**The** adapter: every Claude invocation the runner makes goes through here.

    ``cwd`` is the factory root today, so Claude Code loads the factory's
    ``.claude/settings.json`` (its guard hook and permission rules) and its commands. T9.9
    changes this to the target root, here and nowhere else.
    """
    argv = claude_argv(executable or find_claude(), command)
    start = time.monotonic()
    try:
        done = run_process(argv, timeout=timeout_s, cwd=cwd,  # stdin is never inherited
                           env=claude_env())
    except CommandTimeout as err:
        return Invocation(None, None, _tail(err.stdout + err.stderr), timed_out=True,
                          seconds=time.monotonic() - start)
    except CommandNotFound:
        raise RunnerError(f"could not start Claude: {argv[0]!r} was not found.") from None
    return Invocation(done.returncode, parse_result(done.stdout),
                      _tail(done.stdout + done.stderr), seconds=time.monotonic() - start)


def parse_result(stdout: str) -> dict[str, Any] | None:
    """The ``result`` message of ``--output-format json`` (one JSON object), or the last
    such line if anything else was printed around it."""
    text = (stdout or "").strip()
    candidates = [text] + list(reversed(text.splitlines()))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("type") == "result":
            return data
    return None


def _tail(text: str) -> str:
    text = " ".join(text.split())
    return text[-_TAIL:]


# ----------------------------------------------------------------------------- loop


@dataclass(frozen=True)
class Limits:
    max_no_progress: int = DEFAULT_MAX_NO_PROGRESS
    max_invocations: int = DEFAULT_MAX_INVOCATIONS
    timeout_s: float = DEFAULT_TIMEOUT_MINUTES * 60.0


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    reason: str
    invocations: int
    stories_started: tuple[int, ...] = ()


def fingerprint(result: dict[str, Any]) -> dict[str, Any]:
    """What "progress" means: any change in the state, the increment, the next station,
    or the story or PR it is about."""
    details = result.get("details") or {}
    return {"state": result.get("state"), "increment": result.get("increment"),
            "next_station": result.get("next_station"), "issue": details.get("issue"),
            "pr": details.get("pr")}


def active_story(result: dict[str, Any]) -> int | None:
    if result.get("state") not in _ACTIVE_STORY_STATES:
        return None
    issue = (result.get("details") or {}).get("issue")
    return issue if isinstance(issue, int) else None


def run_until_gate(command: str, *, read_state: Callable[[], dict[str, Any]],
                   read_dirty: Callable[[], list[str]],
                   invoke: Callable[[str], Invocation],
                   log: Callable[[dict[str, Any]], None],
                   limits: Limits | None = None) -> Outcome:
    """The loop. ``command`` is ``continue`` or ``resume``; the callables do all I/O, so the
    loop is tested with a fake adapter."""
    limits = limits or Limits()
    if command not in COMMANDS:
        raise RunnerError(f"--command must be one of: {', '.join(COMMANDS)}")
    continue_left = command == "continue"  # the human's one "continue" (D2)
    allowed_new = 1 if continue_left else 0  # resume never starts a story
    current = read_state()
    initial_story = active_story(current)
    started: list[int] = []
    count = stale = 0

    def outcome(code: int, reason: str) -> Outcome:
        return Outcome(code, reason, count, tuple(started))

    while True:
        sent = COMMANDS["continue"] if continue_left else COMMANDS["resume"]
        decision = commands.route(f"/{sent}", current, dirty=read_dirty())
        if decision.action != "run":
            return outcome(_stop_code(current), decision.message)
        if count >= limits.max_invocations:
            return outcome(EXIT_NO_PROGRESS, f"Stopped after {count} Claude invocations, the "
                           f"limit for one run; the state is {current['state']}. Run it again "
                           "to go on, or raise --max-invocations.")
        count += 1
        before = current
        began = datetime.now(UTC)
        result = invoke(sent)
        current = read_state()
        story = active_story(current)
        if continue_left and story is not None and story != initial_story:
            continue_left = False  # the one story has started: from now on, resume
        if story is not None and story != initial_story and story not in started:
            started.append(story)
        log(_invocation_record(count, sent, began, before, current, result))

        if len(started) > allowed_new:
            return outcome(EXIT_NEEDS_HUMAN, f"{len(started)} new stories became active in "
                           f"one {command} run (issues {', '.join(f'#{n}' for n in started)}),"
                           f" but {command} may start {allowed_new} (D2). Stopped: check the "
                           "factory's state.")
        if result.denials:
            return outcome(EXIT_DENIED, "Claude needed a permission it does not have in a "
                           "headless run, so the runner stopped: "
                           + "; ".join(_describe_denial(d) for d in result.denials)
                           + ". Run the command interactively, or approve the rule yourself.")
        failure = result.failure(limits.timeout_s)
        if failure is not None:
            return outcome(EXIT_CLAUDE_FAILED, failure)
        if fingerprint(current) == fingerprint(before):
            stale += 1
            if stale >= limits.max_no_progress:
                return outcome(EXIT_NO_PROGRESS, f"No progress: the state is still "
                               f"{current['state']} (next station "
                               f"{current.get('next_station') or 'none'}) after {stale} "
                               "invocations in a row. Stopped: check the last station's "
                               "output and the run log.")
        else:
            stale = 0


def _stop_code(result: dict[str, Any]) -> int:
    if result["state"] in (state_mod.NEEDS_HUMAN, state_mod.INCONSISTENT):
        return EXIT_NEEDS_HUMAN
    if result.get("waiting_on") == "factory":
        return EXIT_NEEDS_HUMAN  # route stopped although the factory could act: a human fix
    return EXIT_GATE


def _describe_denial(denial: dict[str, Any]) -> str:
    tool = denial.get("tool_name", "?")
    tool_input = denial.get("tool_input") or {}
    shown = (tool_input.get("command") or tool_input.get("file_path")
             if isinstance(tool_input, dict) else None)
    return f"{tool} {shown!r}" if shown else str(tool)


def _invocation_record(n: int, sent: str, began: datetime, before: dict[str, Any],
                       after: dict[str, Any], inv: Invocation) -> dict[str, Any]:
    res = inv.result or {}
    return {
        "event": "invocation", "n": n, "sent": f"/{sent}", "started_at": _iso(began),
        "seconds": round(inv.seconds, 1), "before": fingerprint(before),
        "after": fingerprint(after), "exit_code": inv.exit_code, "timed_out": inv.timed_out,
        "subtype": res.get("subtype"), "is_error": res.get("is_error"),
        "session_id": res.get("session_id"), "num_turns": res.get("num_turns"),
        "total_cost_usd": res.get("total_cost_usd"),
        "permission_denials": [_describe_denial(d) for d in inv.denials],
        "result_tail": str(res.get("result", ""))[-_TAIL:] if res else inv.output_tail,
    }


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- preflight and log


def check_hooks(factory_root: Path) -> None:
    """Static preflight: the factory's project settings, which a headless session in the
    factory root loads, still run the guard hook. This is not a liveness check: user and
    managed settings are not read here, and a live canary is T9.5's."""
    settings = factory_root / ".claude" / "settings.json"
    data = _read_settings(settings)
    if data is None:
        raise RunnerError(f"{settings} is missing or unreadable: no guard hook, so the "
                          "runner will not start.")
    if not _has_guard(data):
        raise RunnerError(f"{settings} does not run the factory guard before Bash, "
                          "PowerShell, Edit and Write: the runner will not start.")
    for path in (settings, factory_root / ".claude" / "settings.local.json"):
        local = _read_settings(path)
        if local is not None and local.get("disableAllHooks"):
            raise RunnerError(f"{path} sets disableAllHooks: the guard would not run, so the "
                              "runner will not start.")


def _read_settings(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _has_guard(settings: dict[str, Any]) -> bool:
    entries = (settings.get("hooks") or {}).get("PreToolUse") or []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        tools = set(str(entry.get("matcher", "")).split("|"))
        if not {"Bash", "PowerShell", "Edit", "Write"} <= tools:
            continue
        for hook in entry.get("hooks") or []:
            command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
            if "factory.py" in command and command.rstrip().endswith(" guard"):
                return True
    return False


class RunLog:
    """The run log (R3): one JSON object per line in ``.factory-local/runs/``."""

    def __init__(self, factory_root: Path, command: str, now: datetime | None = None):
        moment = now or datetime.now(UTC)
        folder = factory_root / RUNS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{moment.strftime('%Y%m%dT%H%M%SZ')}-{command}.jsonl"

    def write(self, record: dict[str, Any]) -> None:
        line = {"time": _iso(datetime.now(UTC)), **record}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
