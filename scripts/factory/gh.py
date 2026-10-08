"""The factory's only gateway to external processes and to GitHub.

* ``run_process`` is the single place ``subprocess`` is called (``git.py`` reuses it).
  Every call has a timeout, never reads the parent's stdin, and decodes output as UTF-8.
  ``run_command_line`` is its sibling for the target's own configured commands
  (``verify run``), which are shell command lines by definition.
* ``Gh`` wraps the ``gh`` CLI: argument lists only, JSON parsing, typed errors.
  ``Gh._env`` is the one place auth is injected (``GH_TOKEN`` from a named env var),
  which is what the future bot mode needs (architecture §9.4).
* The process runner is swappable (``transport=``), which is how ``FakeGh`` and the
  fixture recorder in ``gh_fixtures.py`` work.
"""

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory.errors import (
    CommandNotFound,
    CommandTimeout,
    ForbiddenCommand,
    GhAuthError,
    GhError,
    GhJsonError,
)

DEFAULT_TIMEOUT = 60.0


@dataclass(frozen=True)
class ProcessResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


Transport = Callable[..., ProcessResult]


def run_process(
    argv: Sequence[str],
    *,
    timeout: float,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
) -> ProcessResult:
    """Run ``argv`` (a list, never a shell string) and capture its output.

    Raises ``CommandTimeout`` / ``CommandNotFound``. A non-zero exit is *returned*,
    not raised: callers decide which error type it becomes.
    """
    if timeout is None or timeout <= 0:
        raise ValueError("every external command needs a positive timeout")
    argv = [str(a) for a in argv]
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=input,
            stdin=None if input is not None else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandTimeout(
            argv,
            None,
            _as_text(exc.stdout),
            _as_text(exc.stderr),
            detail=f"timed out after {timeout:g}s",
        ) from None
    except FileNotFoundError as exc:
        raise CommandNotFound(
            argv, None, "", str(exc), detail=f"executable {argv[0]!r} not found"
        ) from None
    return ProcessResult(argv, completed.returncode, completed.stdout or "", completed.stderr or "")


def run_command_line(
    command: str,
    *,
    timeout: float,
    cwd: str | Path,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run one of the target's configured commands (``commands.*`` in its config) through
    the platform shell, exactly as written (rule H4), and capture stdout and stderr merged
    in order, as ``stdout``.

    This is the one deliberate exception to "argument lists, never shell strings": the
    command *is* a shell command line, declared by the project. On POSIX it runs as
    ``/bin/sh -c <command>``; on Windows as ``cmd.exe /d /s /c "<command>"``. On a timeout
    the whole process tree is killed (a test runner's child processes would otherwise keep
    the pipe open) and ``CommandTimeout`` carries the output captured so far.
    """
    if timeout is None or timeout <= 0:
        raise ValueError("every external command needs a positive timeout")
    if os.name == "nt":
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        # A string, not a list: with /s, cmd removes exactly the outer quotes and runs the
        # rest verbatim, which list quoting would break for commands containing quotes.
        args: str | list[str] = f'"{comspec}" /d /s /c "{command}"'
        argv = [comspec, "/d", "/s", "/c", command]
        options: dict[str, Any] = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        args = argv = ["/bin/sh", "-c", command]
        options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **options,
        )
    except FileNotFoundError as exc:
        raise CommandNotFound(argv, None, "", str(exc),
                              detail=f"shell {argv[0]!r} not found") from None
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # a stray grandchild still holds the pipe
            output = ""
        raise CommandTimeout(argv, None, output or "", "",
                             detail=f"timed out after {timeout:g}s") from None
    return ProcessResult(argv, process.returncode, output or "", "")


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill ``process`` and every process it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
    else:
        try:
            os.killpg(process.pid, 9)  # its own session (start_new_session=True)
        except ProcessLookupError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def _as_text(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


# Defence in depth for D1/S1: the I/O layer itself refuses every merge path it can
# recognise. The PreToolUse guard (T1.6) is the main enforcement; this is a backstop.
_MERGE_ENDPOINT = re.compile(r"/merges?/?$", re.I)  # pulls/N/merge, repos/o/r/merges
_MERGE_MUTATION = re.compile(r"\b(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)\b")


def _refuse_merge(args: Sequence[str]) -> None:
    if len(args) >= 2 and args[0] == "pr" and args[1] == "merge":
        raise ForbiddenCommand("the factory never merges PRs (rule S1): `gh pr merge` refused")
    if args and args[0] == "api":
        endpoint = args[1].split("?", 1)[0] if len(args) > 1 else ""
        queries = [a for a in args if a.startswith("query=")]
        if _MERGE_ENDPOINT.search(endpoint) or any(_MERGE_MUTATION.search(q) for q in queries):
            raise ForbiddenCommand("the factory never merges PRs (rule S1): merge API refused")


class Gh:
    """Thin wrapper around the ``gh`` CLI."""

    def __init__(
        self,
        *,
        repo: str | None = None,
        cwd: str | Path | None = None,
        token_env: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport = run_process,
    ):
        if timeout is None or timeout <= 0:
            raise ValueError("Gh timeout must be positive")
        self.repo = repo
        self.cwd = cwd
        self.token_env = token_env
        self.timeout = timeout
        self._transport = transport

    # -- auth / environment: the single injection point ---------------------------
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            GH_PROMPT_DISABLED="1",  # never block waiting for input
            GH_NO_UPDATE_NOTIFIER="1",
            NO_COLOR="1",
            GH_PAGER="",
            PAGER="",
        )
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token:
                raise GhAuthError(
                    f"environment variable {self.token_env!r} (identity.bot_token_env) is not set"
                )
            env["GH_TOKEN"] = token
        return env

    def repo_args(self) -> list[str]:
        """``["--repo", owner/name]`` when a repo is configured, else ``[]``."""
        return ["--repo", self.repo] if self.repo else []

    # -- execution ----------------------------------------------------------------
    def run(
        self, args: Sequence[str], *, input: str | None = None, timeout: float | None = None
    ) -> str:
        """Run ``gh <args>`` and return stdout. Raises ``GhError`` on a non-zero exit."""
        args = [str(a) for a in args]
        _refuse_merge(args)
        result = self._transport(
            ["gh", *args],
            timeout=timeout or self.timeout,
            cwd=self.cwd,
            env=self._env(),
            input=input,
        )
        if result.returncode != 0:
            raise GhError(result.argv, result.returncode, result.stdout, result.stderr)
        return result.stdout

    def json(
        self,
        args: Sequence[str],
        *,
        fields: Sequence[str] | None = None,
        input: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Run ``gh <args> [--json f1,f2]`` and parse stdout as JSON."""
        args = list(args)
        if fields:
            args += ["--json", ",".join(fields)]
        stdout = self.run(args, input=input, timeout=timeout)
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise GhJsonError(
                ["gh", *args], 0, stdout, stdout[:500], detail=f"invalid JSON output: {exc}"
            ) from None

    def api(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        fields: Mapping[str, str] | None = None,
        json_body: Any = None,
        paginate: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Call ``gh api``. With ``paginate`` the pages are merged into one list.

        ``json_body`` is sent on stdin (``--input -``), which avoids command-line length
        limits (about 32K characters on Windows) and quoting problems for long text.
        """
        args = ["api", endpoint, "--method", method]
        for key, value in (fields or {}).items():
            args += ["-f", f"{key}={value}"]
        stdin = None
        if json_body is not None:
            args += ["--input", "-"]
            stdin = json.dumps(json_body)
        if paginate:
            args += ["--paginate", "--slurp"]
        data = self.json(args, input=stdin, timeout=timeout)
        if paginate and isinstance(data, list) and all(isinstance(p, list) for p in data):
            return [item for page in data for item in page]
        return data
