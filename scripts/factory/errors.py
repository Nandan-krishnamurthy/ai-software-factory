"""Typed errors shared by the factory's I/O layer and the modules built on it."""

import shlex
from collections.abc import Sequence

# Keep error messages readable: long stderr is truncated, not dropped.
STDERR_LIMIT = 2000


class FactoryError(Exception):
    """Base class for every error the factory raises on purpose."""


class CommandError(FactoryError):
    """An external command (gh or git) failed. ``str(err)`` always includes stderr."""

    def __init__(
        self,
        argv: Sequence[str],
        returncode: int | None,
        stdout: str = "",
        stderr: str = "",
        detail: str | None = None,
    ):
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.detail = detail
        super().__init__(self._message())

    def _message(self) -> str:
        cmd = shlex.join(self.argv)
        status = self.detail or f"exit {self.returncode}"
        stderr = self.stderr.strip()
        if len(stderr) > STDERR_LIMIT:
            stderr = stderr[:STDERR_LIMIT] + " …[truncated]"
        return f"`{cmd}` failed ({status}): {stderr or '<no stderr>'}"


class CommandTimeout(CommandError):
    """The command did not finish within its timeout and was killed."""


class CommandNotFound(CommandError):
    """The executable (e.g. ``gh`` or ``git``) is not installed or not on PATH."""


class GhError(CommandError):
    """``gh`` exited with a non-zero status."""


class GhJsonError(CommandError):
    """``gh`` succeeded but its output was not the JSON we asked for."""


class GhAuthError(FactoryError):
    """The configured auth token could not be supplied to ``gh``."""


class ForbiddenCommand(FactoryError):
    """The I/O layer refused to run a command the factory must never run (e.g. a merge)."""


class GitError(CommandError):
    """``git`` exited with a non-zero status."""
