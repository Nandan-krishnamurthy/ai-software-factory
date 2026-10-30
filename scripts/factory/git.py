"""Thin wrapper around ``git``, always run as ``git -C <repo_dir> …`` (rule T3).

Processes are started through ``gh.run_process`` so there is exactly one place that
calls ``subprocess``, with a mandatory timeout.
"""

import os
from collections.abc import Sequence
from pathlib import Path

from factory.errors import GitError
from factory.gh import DEFAULT_TIMEOUT, Transport, run_process

# Git settings that would make the factory's own git calls run a program the repository
# chose (B-46, E2; ADR-0006): hooks (`switch` runs post-checkout, `pull` post-merge, any
# ref update reference-transaction) and an fsmonitor command (`status`, `diff`). The
# hooks folder is a path that cannot exist (below the null device), so no hook is found.
NO_HOOKS = os.path.join(os.devnull, "factory-no-hooks")
SAFE_CONFIG = (("core.hooksPath", NO_HOOKS), ("core.fsmonitor", "false"))


def with_config(env: dict[str, str], pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    """``env`` with ``pairs`` added as command-line git config (``GIT_CONFIG_COUNT``),
    which outranks every config file, including the repository's own. Entries already in
    ``env`` are kept and the new ones appended after them, so they win. A count that is
    not a whole number is treated as none: git would refuse it anyway."""
    raw = env.get("GIT_CONFIG_COUNT", "0").strip()
    count = int(raw) if raw.isdigit() else 0
    out = dict(env)
    for i, (key, value) in enumerate(pairs, start=count):
        out[f"GIT_CONFIG_KEY_{i}"] = key
        out[f"GIT_CONFIG_VALUE_{i}"] = value
    out["GIT_CONFIG_COUNT"] = str(count + len(pairs))
    return out


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
        # The repository's real objects and history (B-28): local replace refs and a graft
        # file can make a commit read as another one, or change its parents, which would
        # change the approved config read and every diff against the default branch. The
        # graft file is a path that cannot exist (below the null device), so none is read.
        env["GIT_NO_REPLACE_OBJECTS"] = "1"
        env["GIT_GRAFT_FILE"] = os.path.join(os.devnull, "factory-no-grafts")
        # No hook and no fsmonitor command runs in any git call the factory makes (E2).
        return with_config(env, SAFE_CONFIG)

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
