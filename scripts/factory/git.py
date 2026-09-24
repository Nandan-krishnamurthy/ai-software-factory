"""Thin wrapper around ``git``, always run as ``git -C <repo_dir> …`` (rule T3).

Processes are started through ``gh.run_process`` so there is exactly one place that
calls ``subprocess``, with a mandatory timeout.
"""

import os
from collections.abc import Sequence
from pathlib import Path

from factory.errors import GitError
from factory.gh import DEFAULT_TIMEOUT, Transport, run_process


class Git:
    def __init__(
        self,
        repo_dir: str | Path,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport = run_process,
    ):
        if timeout is None or timeout <= 0:
            raise ValueError("Git timeout must be positive")
        self.repo_dir = Path(repo_dir)
        self.timeout = timeout
        self._transport = transport

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"  # fail instead of prompting for credentials
        return env

    def run(
        self, args: Sequence[str], *, input: str | None = None, timeout: float | None = None
    ) -> str:
        """Run ``git -C <repo_dir> <args>`` and return stdout. Raises ``GitError``."""
        result = self._transport(
            ["git", "-C", str(self.repo_dir), *[str(a) for a in args]],
            timeout=timeout or self.timeout,
            env=self._env(),
            input=input,
        )
        if result.returncode != 0:
            raise GitError(result.argv, result.returncode, result.stdout, result.stderr)
        return result.stdout

    def current_branch(self) -> str | None:
        """The checked-out branch name, or ``None`` when HEAD is detached."""
        try:
            return self.run(["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
        except GitError:
            return None

    def rev_parse(self, ref: str) -> str:
        return self.run(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]).strip()

    def is_clean(self) -> bool:
        """True when there are no staged, unstaged or untracked changes."""
        return self.run(["status", "--porcelain"]).strip() == ""

    def remote_url(self, name: str = "origin") -> str | None:
        try:
            return self.run(["remote", "get-url", name]).strip()
        except GitError:
            return None
