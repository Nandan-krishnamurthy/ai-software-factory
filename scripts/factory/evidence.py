"""The evidence ledger: ``factory.py verify run`` and ``verify check`` (T6.1).

``verify run --issue N`` runs the target's quality commands itself, instead of trusting
model-written results (rule H1). It runs ``commands.build``, ``lint``, ``typecheck`` and
``test`` from ``.factory/config.json``, in that order, each exactly as written (rule H4),
and records for each one:

* the exact command text, or ``skipped`` when the command is ``null``;
* its status (``pass``, ``fail``, ``timeout`` or ``error``) and exit code;
* its duration, and the last 50 lines of its output (stdout and stderr merged);
* a parsed summary when the output has a known test-runner summary line (Vitest,
  Playwright, pytest, unittest, ``go test``, ``cargo test``), else ``null``.

Every command runs, even after an earlier one fails, so the evidence is complete. The
status comes from the exit code. A summary can only make it stricter: a command that
exits 0 while its summary reports failures is recorded as ``fail``. Success is never
inferred from anything but a zero exit.

The evidence names the exact commit it ran on. ``verify run`` refuses a dirty working
tree, so that commit is exactly what was tested, and records whether HEAD moved or
tracked files changed during the run.

**Only approved commands run.** The commands come from ``.factory/config.json`` on the
default branch on ``origin`` (``origin/HEAD``), which only a PR the human merged can
change, never from the story branch's working tree, which the model can edit. A
``commands.*`` value that differs on the branch is recorded, and ``verify check`` rejects
the evidence: the branch's change was not what ran.

**The guard checks the language that runs.** Commands run with bash on every platform
(``gh.run_command_line``), and before anything runs each one is checked by the factory
guard as a bash command, so a configured command can never become a merge path (rule
S1). A command written with cmd.exe-only syntax (``^``, ``%VAR%``, ``!VAR!``, ``call``)
is refused outright: it means something else to cmd.exe than to the guard.

The evidence is written to ``<SCRATCH>/evidence-<N>.json`` and into the issue's
checkpoint note (``comments.set_checkpoint_evidence``). ``verify check`` reads it back
and refuses evidence that is not for the story branch's current head on ``origin``,
that is malformed, or in which a command failed.

**What ``verify map`` needs (T6.2).** The test command's *full* output is kept beside the
evidence file (``evidence-<N>.test.log``), and its SHA-256 is recorded in the evidence,
so ``verify map`` can find every test's result and prove the file is the one that ran.
``--report PATH`` names a JUnit or JSON report the target's test command already writes:
it is copied beside the evidence (``evidence-<N>.report<k>.<ext>``) with its SHA-256, but
only if the run created or changed it, so a file written beforehand never counts.
"""

import hashlib
import json
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory.comments import EVIDENCE_END, EVIDENCE_START, evidence_block
from factory.config import COMMAND_NAMES, CONFIG_RELPATH, Config, load_config, parse_config
from factory.errors import CommandNotFound, CommandTimeout, FactoryError, GitError
from factory.gh import ProcessResult, run_command_line
from factory.git import Git

SCHEMA = 1
VERIFY_COMMANDS = ("build", "lint", "typecheck", "test")
TAIL_LINES = 50
MAX_LINE = 1000  # a longer output line is cut, so one huge line cannot flood the ledger
DEFAULT_TIMEOUT = 1800.0  # seconds per command
STATUSES = ("pass", "fail", "timeout", "error", "skipped")
# Room left in the checkpoint comment for the station line, the AC-to-test map and the
# S10 verdict.
NOTE_BUDGET = 40000
MAX_REPORT_BYTES = 20 * 1024 * 1024  # a larger report is not captured

Runner = Callable[..., ProcessResult]
Vetter = Callable[[str], str | None]  # returns the guard's reason to block, or None


class EvidenceError(FactoryError):
    """The evidence could not be produced or read."""


@dataclass
class CommandEvidence:
    name: str
    command: str | None
    status: str
    exit_code: int | None = None
    duration_s: float | None = None
    tail: list[str] = field(default_factory=list)
    summary: list[dict] | None = None
    detail: str = ""
    output_sha256: str | None = None  # of the full output, as UTF-8 (T6.2)
    output_lines: int | None = None


@dataclass
class Evidence:
    issue: int
    repo: str
    branch: str
    sha: str
    started_at: str
    finished_at: str
    commands: list[CommandEvidence]
    sha_after: str
    changed_files: list[str] = field(default_factory=list)
    config_source: str = ""  # the approved config the commands came from: origin/main@abc1234
    unapproved: list[str] = field(default_factory=list)  # commands.* changed on the branch
    tails_omitted: bool = False
    # Test reports the run wrote (``--report``): {"path", "status", "sha256", "bytes"}.
    reports: list[dict] = field(default_factory=list)
    schema: int = SCHEMA
    # Local only, never in the JSON or the note: the full outputs by command name, and the
    # captured reports' contents by path. ``write`` stores them beside the evidence file.
    outputs: dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    report_data: dict[str, bytes] = field(default_factory=dict, repr=False, compare=False)

    def failures(self) -> list[str]:
        """One line per command that did not pass (a skipped command is not a failure)."""
        return [f"commands.{c.name} {_describe(c)}" for c in self.commands
                if c.status not in ("pass", "skipped")]

    def command(self, name: str) -> CommandEvidence | None:
        return next((c for c in self.commands if c.name == name), None)

    def to_dict(self) -> dict:
        data = asdict(self)
        del data["outputs"], data["report_data"]
        return data


# ----------------------------------------------------------------------------- running


def run_verification(
    target_path: Path,
    *,
    issue: int,
    repo: str,
    git: Git,
    runner: Runner | None = None,
    vet: Vetter | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    reports: Sequence[str] = (),
) -> Evidence:
    """Run the approved quality commands on the target's current commit and record the
    results. Nothing runs if any check before the run fails. ``reports``: paths, relative
    to the target, of test reports the commands write; each is captured only if the run
    created or changed it."""
    report_paths = [_report_path(target_path, r) for r in reports]
    dirty = _status_lines(git)
    if dirty:
        raise EvidenceError("the target has uncommitted changes, so the evidence could not "
                            "name the commit that was tested; commit them first: "
                            + ", ".join(dirty))
    branch = git.current_branch()
    if not branch:
        raise EvidenceError("the target's HEAD is detached; check out the story branch")
    try:
        sha = git.rev_parse("HEAD")
    except GitError:
        raise EvidenceError("the target has no commits") from None
    commands, source = approved_commands(git)
    unapproved = unapproved_changes(target_path, commands)
    for name in VERIFY_COMMANDS:
        command = commands.get(name)
        if not command:
            continue
        if reason := cmd_syntax(command):
            raise EvidenceError(f"commands.{name} uses {reason}; configured commands run with "
                                "bash, the language the guard checks, so write it in bash "
                                "syntax; nothing was run")
        if vet is not None and (reason := vet(command)):
            raise EvidenceError(f"commands.{name} is refused by the factory guard: "
                                f"{reason}; nothing was run")

    before = {rel: _digest_file(path) for rel, path in report_paths}
    started = now()
    runner = runner or run_command_line
    outputs: dict[str, str] = {}
    results = [_run_one(name, commands.get(name), target_path, runner, timeout, clock,
                        outputs) for name in VERIFY_COMMANDS]
    captured, report_data = _capture_reports(report_paths, before)
    return Evidence(
        issue=issue, repo=repo, branch=branch, sha=sha,
        started_at=started.isoformat(timespec="seconds"),
        finished_at=now().isoformat(timespec="seconds"),
        commands=results, sha_after=git.rev_parse("HEAD"),
        changed_files=_status_lines(git), config_source=source, unapproved=unapproved,
        reports=captured, outputs=outputs, report_data=report_data,
    )


def _report_path(target_path: Path, rel: str) -> tuple[str, Path]:
    """A ``--report`` path: relative, inside the target, and not ``.git``."""
    path = Path(rel)
    if not rel.strip() or path.is_absolute() or path.drive:
        raise EvidenceError(f"--report {rel!r} must be a path relative to the target")
    root = target_path.resolve()
    full = (root / path).resolve()
    if full == root or root not in full.parents or ".git" in full.relative_to(root).parts:
        raise EvidenceError(f"--report {rel!r} is not a file inside the target")
    return full.relative_to(root).as_posix(), full


def _digest_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    except OSError:
        return None


def _capture_reports(paths: list[tuple[str, Path]], before: dict[str, str | None]
                     ) -> tuple[list[dict], dict[str, bytes]]:
    """Each report as the run left it. Only a file the run created or changed is
    ``captured``; one it left as it was is ``unchanged``, so a report written before the
    run (by anyone) is never taken for the run's."""
    captured, data = [], {}
    for rel, path in paths:
        entry: dict = {"path": rel, "status": "missing", "sha256": None, "bytes": None}
        try:
            content = path.read_bytes() if path.is_file() else None
        except OSError:
            content = None
        if content is not None and len(content) > MAX_REPORT_BYTES:
            entry["status"] = "too large"
        elif content is not None:
            digest = hashlib.sha256(content).hexdigest()
            entry.update(sha256=digest, bytes=len(content))
            if digest == before.get(rel):
                entry["status"] = "unchanged"
            else:
                entry["status"] = "captured"
                data[rel] = content
        captured.append(entry)
    return captured, data


def approved_commands(git: Git) -> tuple[dict[str, str | None], str]:
    """The ``commands`` of ``.factory/config.json`` on the default branch on ``origin``,
    and where they came from (``origin/main@abc1234``). Raises ``EvidenceError`` when
    there is no such config: nothing may run without approved commands."""
    config, source = approved_config(git)
    return {name: config.commands.get(name) for name in COMMAND_NAMES}, source


def approved_config(git: Git) -> tuple[Config, str]:
    """``.factory/config.json`` on the default branch on ``origin`` (only a merged PR
    changes it), and where it came from (``origin/main@abc1234``)."""
    ref = default_ref(git)
    path = f"{ref}:{CONFIG_RELPATH.as_posix()}"
    try:
        sha = git.rev_parse(ref)
        text = git.run(["show", f"{sha}:{CONFIG_RELPATH.as_posix()}"])
        config = parse_config(json.loads(text), path)
    except GitError:
        raise EvidenceError(f"{path} does not exist: there are no approved commands to "
                            "run (they reach the default branch only through a merged "
                            "PR)") from None
    except ValueError as err:
        raise EvidenceError(f"{path} is not valid JSON: {err}") from None
    except FactoryError as err:
        raise EvidenceError(f"{path} is not a valid config: {err}") from None
    return config, f"{ref}@{sha[:7]}"


def default_ref(git: Git) -> str:
    """The default branch on ``origin`` as a ref (``origin/main``), from ``origin/HEAD``."""
    try:
        ref = git.run(["rev-parse", "--abbrev-ref", "origin/HEAD"]).strip()
    except GitError:
        raise EvidenceError("origin/HEAD is not set, so the default branch's approved "
                            "config cannot be found; run `git remote set-head origin "
                            "--auto` in the target") from None
    if not ref.startswith("origin/") or ref == "origin/HEAD":
        raise EvidenceError(f"origin/HEAD does not name a branch on origin ({ref!r})")
    return ref


def unapproved_changes(target_path: Path, approved: Mapping[str, str | None]) -> list[str]:
    """The ``commands.*`` that the story branch's config changes from the approved ones."""
    try:
        branch = load_config(target_path).commands
    except FactoryError:
        return [f"{CONFIG_RELPATH.as_posix()} (missing or invalid on the branch)"]
    return [f"commands.{name}" for name in COMMAND_NAMES
            if branch.get(name) != approved.get(name)]


# cmd.exe syntax that bash, and so the guard, reads differently.
_CMD_SYNTAX = (
    (re.compile(r"\^"), "`^` (the cmd.exe escape character)"),
    (re.compile(r"%(?:[A-Za-z_]\w*%|[~*\d])"), "a `%...%` variable (cmd.exe syntax)"),
    (re.compile(r"![A-Za-z_]\w*!"), "a `!...!` variable (cmd.exe delayed expansion)"),
    (re.compile(r"(?i)(?:^|[;&|(])\s*call\s"), "`call` (a cmd.exe command)"),
)


def cmd_syntax(command: str) -> str | None:
    """Why ``command`` looks like cmd.exe syntax, or ``None``."""
    for pattern, why in _CMD_SYNTAX:
        if pattern.search(command):
            return why
    return None


def _run_one(name: str, command: str | None, cwd: Path, runner: Runner, timeout: float,
             clock: Callable[[], float], outputs: dict[str, str]) -> CommandEvidence:
    if not command:
        return CommandEvidence(name, None, "skipped", detail=f"commands.{name} is null")
    start = clock()
    try:
        result = runner(command, cwd=cwd, timeout=timeout)
    except CommandTimeout as err:
        output = outputs[name] = err.stdout + err.stderr
        return CommandEvidence(name, command, "timeout", None, _seconds(clock() - start),
                               tail_lines(output), parse_summary(output),
                               err.detail or f"timed out after {timeout:g}s",
                               *_fingerprint(output))
    except CommandNotFound as err:
        return CommandEvidence(name, command, "error", None, _seconds(clock() - start),
                               detail=err.detail or str(err))
    output = outputs[name] = result.stdout + (f"\n{result.stderr}" if result.stderr else "")
    summary = parse_summary(output)
    status, detail = ("pass", "") if result.returncode == 0 else ("fail", "")
    if status == "pass" and reports_failures(summary):
        status, detail = "fail", "exit 0, but the runner's summary reports failures"
    return CommandEvidence(name, command, status, result.returncode, _seconds(clock() - start),
                           tail_lines(output), summary, detail, *_fingerprint(output))


def _fingerprint(output: str) -> tuple[str, int]:
    """The SHA-256 of the full output (UTF-8) and its number of lines."""
    return hashlib.sha256(output.encode("utf-8")).hexdigest(), len(output.splitlines())


def _seconds(value: float) -> float:
    return round(max(value, 0.0), 3)


def _status_lines(git: Git) -> list[str]:
    return [line for line in git.run(["status", "--porcelain"]).splitlines() if line.strip()]


def guard_vetter(target_path: Path) -> Vetter:
    """Check each configured command with the PreToolUse guard's own rules, as if it were
    a Bash call in the target, because ``verify run`` starts it without the hook."""
    from factory import guard, guard_hook  # imported lazily: only ``verify run`` needs it

    ctx = guard_hook.build_context({"cwd": str(target_path)})

    def vet(command: str) -> str | None:
        decision = guard.decide("Bash", {"command": command}, ctx)
        return None if decision.allowed else decision.reason

    return vet


# ----------------------------------------------------------------------------- output

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def clean_lines(output: str) -> list[str]:
    """Output lines without colour codes; a line rewritten with ``\\r`` keeps its last
    version, as a terminal would show it."""
    text = _ANSI.sub("", (output or "").replace("\r\n", "\n"))
    return [line.rsplit("\r", 1)[-1].rstrip() for line in text.split("\n")]


def tail_lines(output: str, count: int = TAIL_LINES) -> list[str]:
    lines = clean_lines(output)
    while lines and not lines[-1]:
        lines.pop()
    return [line if len(line) <= MAX_LINE else line[:MAX_LINE] + " …[cut]"
            for line in lines[-count:]]


# ----------------------------------------------------------------------------- summaries

_VITEST = re.compile(r"^\s*Tests\s+(?P<parts>\d+ [a-z]+(?:\s*\|\s*\d+ [a-z]+)*)"
                     r"\s+\((?P<total>\d+)\)\s*$")
_PLAYWRIGHT = re.compile(r"^\s*(?P<n>\d+) (?P<word>passed|failed|flaky|skipped|did not run"
                         r"|interrupted)(?: \([^)]*\))?\s*$")
_PYTEST = re.compile(r"^=+ (?P<parts>.+?) in [\d.]+s(?: \([^)]*\))? =+$")
_UNITTEST_RAN = re.compile(r"^Ran (?P<n>\d+) tests? in [\d.]+s$")
_UNITTEST_RESULT = re.compile(r"^(?P<result>OK|FAILED)(?: \((?P<parts>[^)]*)\))?$")
_GO_OK = re.compile(r"^ok\s+\S+\s")
_GO_FAIL = re.compile(r"^FAIL\s+\S+\s+[\d.]+s")
_GO_NO_TESTS = re.compile(r"^\?\s+\S+\s+\[no test files\]")
_GO_FAILED_TEST = re.compile(r"^\s*--- FAIL: ")
_CARGO = re.compile(r"^test result: (?P<result>ok|FAILED)\. (?P<passed>\d+) passed; "
                    r"(?P<failed>\d+) failed; (?P<ignored>\d+) ignored; (?P<measured>\d+) "
                    r"measured; (?P<filtered>\d+) filtered out")
_COUNT = re.compile(r"^(?P<n>\d+) (?P<word>[a-z][a-z ]*?)s?$")
_FAILURE_KEYS = {"failed", "failure", "failures", "error", "errors", "interrupted",
                 "packages_failed", "tests_failed"}


def parse_summary(output: str) -> list[dict] | None:
    """The test-runner summaries found in ``output``, in order, or ``None`` if none is
    recognised. Each is ``{"runner", "counts", "text"}``, plus ``"result"`` where the
    runner prints one. A ``None`` summary is not a failure: the exit code decides."""
    lines = clean_lines(output)
    found: list[dict] = []
    playwright: dict[str, int] = {}
    playwright_text: list[str] = []
    go = {"packages_ok": 0, "packages_failed": 0, "tests_failed": 0, "no_test_files": 0}
    cargo: dict[str, int] = {}
    cargo_failed = False
    for index, line in enumerate(lines):
        if m := _VITEST.match(line):
            counts = {}
            for part in m["parts"].split("|"):
                n, word = part.strip().split(" ", 1)
                counts[word] = int(n)
            counts["total"] = int(m["total"])
            found.append({"runner": "vitest", "counts": counts, "text": line.strip()})
        elif m := _PLAYWRIGHT.match(line):
            playwright[m["word"]] = playwright.get(m["word"], 0) + int(m["n"])
            playwright_text.append(line.strip())
        elif m := _PYTEST.match(line):
            found.append({"runner": "pytest", "counts": _counts(m["parts"].split(", ")),
                          "text": line.strip()})
        elif m := _UNITTEST_RAN.match(line):
            entry = {"runner": "unittest", "counts": {"ran": int(m["n"])}, "text": line}
            result = next((r for r in lines[index + 1:] if r.strip()), "")
            if r := _UNITTEST_RESULT.match(result.strip()):
                entry["result"] = r["result"]
                entry["text"] = f"{line}; {result.strip()}"
                for pair in (r["parts"] or "").split(","):
                    if "=" in pair:
                        key, value = pair.strip().split("=", 1)
                        if value.isdigit():
                            entry["counts"][key] = int(value)
            found.append(entry)
        elif _GO_OK.match(line):
            go["packages_ok"] += 1
        elif _GO_FAIL.match(line):
            go["packages_failed"] += 1
        elif _GO_NO_TESTS.match(line):
            go["no_test_files"] += 1
        elif _GO_FAILED_TEST.match(line):
            go["tests_failed"] += 1
        elif m := _CARGO.match(line):
            cargo_failed |= m["result"] == "FAILED"
            for key in ("passed", "failed", "ignored", "measured", "filtered"):
                cargo[key] = cargo.get(key, 0) + int(m[key])
    if playwright:
        found.append({"runner": "playwright", "counts": playwright,
                      "text": "; ".join(playwright_text)})
    if go["packages_ok"] or go["packages_failed"]:
        found.append({"runner": "go test", "counts": go,
                      "text": f"go test: {go['packages_ok']} package(s) ok, "
                              f"{go['packages_failed']} failed"})
    if cargo:
        found.append({"runner": "cargo test", "counts": cargo,
                      "result": "FAILED" if cargo_failed else "ok",
                      "text": f"cargo test: {cargo['passed']} passed; {cargo['failed']} "
                              f"failed; {cargo['ignored']} ignored"})
    return found or None


def _counts(parts: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for part in parts:
        if m := _COUNT.match(part.strip()):
            counts[m["word"]] = counts.get(m["word"], 0) + int(m["n"])
    return counts


def reports_failures(summary: list[dict] | None) -> bool:
    for entry in summary or []:
        if entry.get("result") == "FAILED":
            return True
        if any(entry["counts"].get(key, 0) > 0 for key in _FAILURE_KEYS):
            return True
    return False


def summary_text(summary: list[dict] | None) -> str:
    return "; ".join(f"{s['runner']}: {s['text']}" for s in summary or [])


# ----------------------------------------------------------------------------- storage


def default_path(issue: int) -> Path:
    """``<SCRATCH>/evidence-<N>.json``, ``<SCRATCH>`` being the system temp directory."""
    return Path(tempfile.gettempdir()) / f"evidence-{issue}.json"


def write(evidence: Evidence, path: Path) -> Path:
    """Write the evidence JSON to ``path``, and beside it the test command's full output
    and the captured reports, the local files ``verify map`` reads (T6.2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if "test" in evidence.outputs:
        # Bytes, not text: no newline translation, so the file hashes as recorded.
        output_path(path).write_bytes(evidence.outputs["test"].encode("utf-8"))
    for index, report in enumerate(evidence.reports, start=1):
        if report["path"] in evidence.report_data:
            report_copy_path(path, index, report["path"]).write_bytes(
                evidence.report_data[report["path"]])
    return path


def output_path(evidence_path: Path) -> Path:
    """Where the test command's full output is kept: ``evidence-<N>.test.log``."""
    return evidence_path.with_suffix(".test.log")


def report_copy_path(evidence_path: Path, index: int, report: str) -> Path:
    """Where the ``index``-th captured report is kept: ``evidence-<N>.report<k>.<ext>``."""
    suffix = Path(report).suffix.lower()
    return evidence_path.with_suffix(f".report{index}{suffix if suffix.isascii() else ''}")


def recorded_output(evidence: Evidence, evidence_path: Path) -> tuple[str | None, str]:
    """The test command's full output from beside the evidence file, if its SHA-256 is
    the recorded one, and a note on where it came from. Without the file (another
    machine, or evidence from an older ledger) it falls back to the recorded tail.
    Raises ``EvidenceError`` if the file is not the output that was recorded."""
    test = evidence.command("test")
    if test is None or test.status in ("skipped", "error"):
        return None, f"the test command was {'not run' if test is None else test.status}"
    path = output_path(evidence_path)
    if test.output_sha256 and path.is_file():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != test.output_sha256:
            raise EvidenceError(f"{path} is not the test output the evidence recorded (its "
                                "SHA-256 differs); run `verify run` again")
        return data.decode("utf-8"), f"the test command's full output ({test.output_lines} lines)"
    lines = "\n".join(test.tail)
    return lines, (f"only the last {len(test.tail)} lines of the test output (the full "
                   f"output is not at {path})")


def recorded_reports(evidence: Evidence, evidence_path: Path
                     ) -> tuple[list[tuple[str, bytes]], list[str]]:
    """The captured reports from beside the evidence file whose SHA-256 is the recorded
    one, and a note for each report that cannot be used. Raises ``EvidenceError`` if a
    copy is not the report that was recorded."""
    found, notes = [], []
    for index, report in enumerate(evidence.reports, start=1):
        if report.get("status") != "captured":
            notes.append(f"report {report.get('path')} was not used: "
                         f"{report.get('status')} after the run")
            continue
        path = report_copy_path(evidence_path, index, report["path"])
        if not path.is_file():
            notes.append(f"report {report['path']} was not used: its copy {path} is missing")
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != report.get("sha256"):
            raise EvidenceError(f"{path} is not the report {report['path']} the evidence "
                                "recorded (its SHA-256 differs); run `verify run` again")
        found.append((report["path"], data))
    return found, notes


def read(path: Path) -> Evidence:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise EvidenceError(f"cannot read {path}: {err}") from None
    except ValueError as err:
        raise EvidenceError(f"{path} is not valid JSON: {err}") from None
    return from_dict(data)


def from_dict(data: Any) -> Evidence:
    """Rebuild evidence from its JSON form, refusing anything malformed."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise EvidenceError(f"not evidence of schema {SCHEMA}")
    local = {"outputs", "report_data"} & set(data)
    if local:
        raise EvidenceError(f"malformed evidence: unexpected {', '.join(sorted(local))}")
    try:
        commands = [CommandEvidence(**c) for c in data["commands"]]
        evidence = Evidence(**{**data, "commands": commands})
    except (KeyError, TypeError) as err:
        raise EvidenceError(f"malformed evidence: {err}") from None
    if not isinstance(evidence.reports, list) or not all(
            isinstance(r, dict) and isinstance(r.get("path"), str) for r in evidence.reports):
        raise EvidenceError("malformed evidence: reports must be a list of {path, …}")
    names = [c.name for c in evidence.commands]
    if names != list(VERIFY_COMMANDS):
        raise EvidenceError(f"evidence must cover {', '.join(VERIFY_COMMANDS)} in order; "
                            f"got {', '.join(map(str, names)) or 'nothing'}")
    for c in evidence.commands:
        if c.status not in STATUSES:
            raise EvidenceError(f"commands.{c.name}: unknown status {c.status!r}")
        if (c.status == "skipped") != (c.command is None):
            raise EvidenceError(f"commands.{c.name}: only a null command may be skipped")
    if not re.fullmatch(r"[0-9a-f]{40}", str(evidence.sha)):
        raise EvidenceError("the evidence does not name a full commit SHA")
    return evidence


def to_block(evidence: Evidence) -> str:
    """The evidence as a block for the checkpoint note: a headline, then the JSON on one
    line. ``<`` and backticks are escaped, so no output line can end the block, look like
    a factory marker, or break the Markdown fence. If the output tails would make the
    checkpoint comment too long, they are left out here; the JSON file keeps them."""
    data = evidence.to_dict()
    payload = _escape(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if len(payload) > NOTE_BUDGET:
        data = {**data, "tails_omitted": True,
                "commands": [{**c, "tail": []} for c in data["commands"]]}
        payload = _escape(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return (f"{EVIDENCE_START}\n**Evidence ledger** (`verify run`) @ `{evidence.sha[:7]}`: "
            f"{headline(evidence)}\n\n```json\n{payload}\n```\n{EVIDENCE_END}")


def from_body(body: str) -> Evidence | None:
    """The evidence in a checkpoint comment body, or ``None`` if it has none."""
    block = evidence_block(body)
    if block is None:
        return None
    start, end = block.find("```json\n"), block.rfind("\n```")
    if start < 0 or end <= start:
        raise EvidenceError("the checkpoint's evidence block has no JSON")
    try:
        data = json.loads(block[start + len("```json\n"):end])
    except ValueError as err:
        raise EvidenceError(f"the checkpoint's evidence is not valid JSON: {err}") from None
    return from_dict(data)


def _escape(payload: str) -> str:
    return payload.replace("<", "\\u003c").replace("`", "\\u0060")


# ----------------------------------------------------------------------------- checking


def remote_head(git: Git, branch: str) -> str | None:
    """The commit ``branch`` points at on ``origin`` (what its PR shows), or ``None``."""
    out = git.run(["ls-remote", "--heads", "origin", f"refs/heads/{branch}"])
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}":
            return sha.strip()
    return None


def check(evidence: Evidence, *, issue: int, branch_head: str | None,
          expected_branch: str | None = None) -> list[str]:
    """Why ``evidence`` cannot be trusted for the story as it is now; empty if it can."""
    problems = []
    if evidence.issue != issue:
        problems.append(f"the evidence is for issue #{evidence.issue}, not #{issue}")
    if expected_branch and evidence.branch != expected_branch:
        problems.append(f"the evidence is for branch {evidence.branch}, but the story's "
                        f"checkpoint names {expected_branch}")
    if branch_head is None:
        problems.append(f"branch {evidence.branch} is not on origin, so its head cannot be "
                        "compared; push it, then run `verify run` again")
    elif branch_head != evidence.sha:
        problems.append(f"the evidence is for commit {evidence.sha[:7]}, but the head of "
                        f"{evidence.branch} is {branch_head[:7]}; run `verify run` again")
    if evidence.sha_after != evidence.sha:
        problems.append(f"HEAD moved from {evidence.sha[:7]} to {evidence.sha_after[:7]} "
                        "while the commands ran")
    if evidence.changed_files:
        problems.append("the commands changed files in the working tree, so the tested "
                        "tree is not the commit: " + ", ".join(evidence.changed_files))
    if not evidence.config_source:
        problems.append("the evidence does not name the approved config its commands came "
                        "from")
    problems += [f"{name} differs on the branch from the approved config "
                 f"({evidence.config_source}); the approved command ran, so the branch's "
                 "change is not verified" for name in evidence.unapproved]
    problems += evidence.failures()
    return problems


# ----------------------------------------------------------------------------- rendering


def _describe(c: CommandEvidence) -> str:
    if c.status == "skipped":
        return "skipped (null)"
    if c.status == "timeout":
        return f"timed out ({c.detail})"
    if c.status == "error":
        return f"could not run ({c.detail})"
    text = f"{'passed' if c.status == 'pass' else 'failed'} (exit {c.exit_code})"
    return f"{text}: {c.detail}" if c.detail else text


def headline(evidence: Evidence) -> str:
    return ", ".join(
        f"{c.name} {c.status}" + (f" (exit {c.exit_code})" if c.status == "fail" else "")
        for c in evidence.commands)


def render(evidence: Evidence, path: Path | None = None) -> str:
    lines = [f"Evidence for #{evidence.issue} on {evidence.branch} @ {evidence.sha[:7]} "
             f"({evidence.started_at} to {evidence.finished_at})",
             f"  commands from the approved config: {evidence.config_source}"]
    for c in evidence.commands:
        if c.status == "skipped":
            lines.append(f"  {c.name:<10} skipped   {c.detail}")
            continue
        code = "-" if c.exit_code is None else str(c.exit_code)
        lines.append(f"  {c.name:<10} {c.status:<8}  exit {code:<4} {c.duration_s:>8.1f}s  "
                     f"`{c.command}`")
        if c.summary:
            lines.append(f"  {'':<10} {summary_text(c.summary)}")
        if c.detail:
            lines.append(f"  {'':<10} {c.detail}")
    if evidence.changed_files:
        lines.append("  changed during the run: " + ", ".join(evidence.changed_files))
    if evidence.unapproved:
        lines.append("  NOT run, changed on this branch: " + ", ".join(evidence.unapproved))
    if path is not None:
        lines.append(f"Written to {path} and to the checkpoint note.")
    failures = evidence.failures()
    if failures:
        lines.append("FAILING: " + "; ".join(failures))
    elif evidence.unapproved:
        lines.append("NOT ACCEPTED: the approved commands passed, but this branch changes "
                     + ", ".join(evidence.unapproved) + "; that change was not verified.")
    else:
        lines.append("OK: every configured command passed.")
    return "\n".join(lines)


def render_check(evidence: Evidence, problems: list[str]) -> str:
    lines = [f"Evidence for #{evidence.issue} on {evidence.branch} @ {evidence.sha[:7]}: "
             f"{headline(evidence)}"]
    lines += [f"  problem: {p}" for p in problems]
    lines.append("REJECTED: the evidence cannot be used for this story as it is now."
                 if problems else "OK: the evidence is for the branch head and every "
                                  "configured command passed.")
    return "\n".join(lines)
