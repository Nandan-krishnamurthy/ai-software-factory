"""Claude Code PreToolUse hook adapter for the guard (``factory.py guard``).

Reads the hook's JSON from stdin, builds a ``GuardContext`` with real I/O (the active
target, git, gh), and asks the pure ``guard.decide``. Exit code 2 blocks the tool call and
shows the reason to Claude; exit code 0 lets it through to the normal permission checks.

The guard **fails closed**: if the input cannot be read or the guard itself errors on a
shell or write tool call, the call is blocked with the error as the reason.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from factory import target as target_mod
from factory.config import load_config
from factory.errors import FactoryError
from factory.gh import Gh
from factory.git import Git
from factory.guard import SHELL_TOOLS, WRITE_TOOLS, GuardContext, decide

BLOCK_EXIT = 2


def build_context(hook_input: dict) -> GuardContext:
    factory_root = target_mod.FACTORY_ROOT
    try:
        active = target_mod.get_target()
        target_root = active.path
    except FactoryError:
        active, target_root = None, None

    default_branch = "main"
    if active is not None:
        try:
            default_branch = load_config(active.path).default_branch
        except FactoryError:
            pass

    cwd = Path(hook_input.get("cwd") or os.getcwd())
    return GuardContext(
        factory_root=factory_root,
        target_root=target_root,
        cwd=cwd,
        default_branch=default_branch,
        scratch_dirs=(Path(tempfile.gettempdir()),),
        extra_write_dirs=(Path.home() / ".claude" / "projects",),
        current_branch=_current_branch,
        is_reviewed=_is_reviewed,
    )


def _current_branch(repo_dir: Path) -> str | None:
    try:
        return Git(repo_dir, timeout=15).current_branch()
    except FactoryError:
        return None


def _is_reviewed(branch: str, repo_dir: Path) -> bool | None:
    """True if ``branch`` has any PR (open, closed or merged): it has been submitted
    for review, so it must not be force-pushed. ``None`` if that cannot be determined."""
    try:
        remote = Git(repo_dir, timeout=15).remote_url("origin")
        repo = target_mod.parse_github_remote(remote or "")
        if repo is None:
            return None
        prs = Gh(timeout=20).json(
            ["pr", "list", "--repo", repo, "--head", branch, "--state", "all",
             "--limit", "1"], fields=["number"])
        return bool(prs)
    except FactoryError:
        return None


def run(stdin: bytes) -> tuple[int, str]:
    """Returns (exit code, message for stderr)."""
    try:
        hook_input = json.loads(stdin.decode("utf-8"))
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input") or {}
    except (ValueError, AttributeError) as err:
        return BLOCK_EXIT, f"factory guard: could not read the hook input ({err}); blocked."
    if tool_name not in SHELL_TOOLS and tool_name not in WRITE_TOOLS:
        return 0, ""
    try:
        decision = decide(tool_name, tool_input, build_context(hook_input))
    except Exception as err:  # fail closed on a guard bug
        return BLOCK_EXIT, f"factory guard error ({type(err).__name__}: {err}); blocked."
    if decision.allowed:
        return 0, ""
    return BLOCK_EXIT, f"Blocked by the factory guard: {decision.reason}"


def main() -> int:
    code, message = run(sys.stdin.buffer.read())
    if message:
        print(message, file=sys.stderr)
    return code
