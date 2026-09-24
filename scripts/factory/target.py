"""The active target repository (architecture §3).

``target set <path>`` validates the path and records it in the gitignored
``.factory-local/target.json``. It also adds the path to Claude Code's
``permissions.additionalDirectories`` in the gitignored ``.claude/settings.local.json``,
so the factory can work in the target while running from this repo.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from factory.errors import FactoryError, GitError
from factory.git import Git

FACTORY_ROOT = Path(__file__).resolve().parents[2]
TARGET_FILE = Path(".factory-local") / "target.json"
SETTINGS_LOCAL = Path(".claude") / "settings.local.json"

_GITHUB_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)


class TargetError(FactoryError):
    """The target path is invalid, or no target is set."""


class NoTarget(TargetError):
    def __init__(self):
        super().__init__("no active target. Run /factory-target <path> first (rule T1).")


@dataclass(frozen=True)
class Target:
    path: Path
    repo: str  # owner/name on GitHub

    def banner(self) -> str:
        return f"Target: {self.path} ({self.repo})"


def parse_github_remote(url: str) -> str | None:
    """``owner/name`` for a GitHub remote URL, else ``None``."""
    match = _GITHUB_REMOTE.match(url.strip())
    return f"{match['owner']}/{match['name']}" if match else None


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_target(path: str | Path, factory_root: Path | None = None) -> Target:
    """Check that ``path`` is a git repo with a GitHub ``origin`` and is not the factory."""
    factory_root = factory_root or FACTORY_ROOT
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise TargetError(f"{candidate} is not an existing directory")
    try:
        toplevel = Git(candidate).run(["rev-parse", "--show-toplevel"]).strip()
    except GitError:
        raise TargetError(f"{candidate} is not inside a git repository") from None
    repo_root = Path(toplevel).resolve()
    factory_root = factory_root.resolve()

    if repo_root == factory_root:
        raise TargetError("the target cannot be the factory repository itself (D4, rule S3)")
    if _is_within(repo_root, factory_root) or _is_within(factory_root, repo_root):
        raise TargetError(
            f"the target {repo_root} and the factory {factory_root} must not be nested "
            "inside each other (D4)"
        )

    remote = Git(repo_root).remote_url("origin")
    if remote is None:
        raise TargetError(f"{repo_root} has no 'origin' remote; the target needs a GitHub remote")
    repo = parse_github_remote(remote)
    if repo is None:
        raise TargetError(f"origin remote {remote!r} is not a GitHub repository")
    return Target(path=repo_root, repo=repo)


def set_target(path: str | Path, factory_root: Path | None = None) -> Target:
    """Validate ``path``, record it as the active target, and allow Claude Code to access it."""
    factory_root = factory_root or FACTORY_ROOT
    target = validate_target(path, factory_root)
    previous = _read_target_file(factory_root)

    target_file = factory_root / TARGET_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "path": str(target.path),
        "repo": target.repo,
        "set_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    target_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    old_path = previous.get("path") if previous else None
    _update_additional_directories(factory_root, add=str(target.path), remove=old_path)
    return target


def get_target(factory_root: Path | None = None) -> Target:
    """The active target. Raises ``NoTarget`` or ``TargetError`` if it is missing or gone."""
    factory_root = factory_root or FACTORY_ROOT
    record = _read_target_file(factory_root)
    if not record:
        raise NoTarget()
    path = Path(record.get("path", ""))
    repo = record.get("repo", "")
    if not record.get("path") or not repo:
        raise TargetError(f"{factory_root / TARGET_FILE} is incomplete; run /factory-target again")
    if not path.is_dir():
        raise TargetError(f"the active target {path} no longer exists; run /factory-target again")
    return Target(path=path, repo=repo)


def _read_target_file(factory_root: Path) -> dict | None:
    target_file = factory_root / TARGET_FILE
    if not target_file.is_file():
        return None
    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise TargetError(f"{target_file} is corrupt; run /factory-target again") from None
    return data if isinstance(data, dict) else None


def _update_additional_directories(factory_root: Path, add: str, remove: str | None) -> None:
    """Add the target to ``permissions.additionalDirectories``, keeping all other settings."""
    settings_file = factory_root / SETTINGS_LOCAL
    settings: dict = {}
    if settings_file.is_file():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise TargetError(
                f"{settings_file} is not valid JSON; fix or delete it, then retry"
            ) from None
        if not isinstance(settings, dict):
            raise TargetError(f"{settings_file} must contain a JSON object")

    permissions = settings.setdefault("permissions", {})
    dirs = [d for d in permissions.get("additionalDirectories", []) if d != remove or d == add]
    if add not in dirs:
        dirs.append(add)
    permissions["additionalDirectories"] = dirs

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
