"""Load and validate a target repo's ``.factory/config.json`` (schema v1, architecture §5.3).

Validation is strict: unknown keys are rejected, so a typo or an unsupported option
(such as anything that would enable merging) can never be silently ignored. All
problems are collected and reported together.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory.errors import FactoryError

CONFIG_RELPATH = Path(".factory") / "config.json"
SCHEMA_VERSION = 1

COMMAND_NAMES = ("install", "build", "lint", "typecheck", "test")
DEFAULT_LIMITS = {"max_fix_attempts": 3, "max_review_rounds": 3, "max_diff_lines": 400}
IDENTITY_MODES_IMPLEMENTED = ("single-account",)
IDENTITY_MODES_PLANNED = ("bot",)

_TOP_LEVEL = {
    "schema", "project", "repo", "default_branch", "reviewers",
    "commands", "limits", "ci", "identity",
}
_REQUIRED = ("schema", "project", "repo", "default_branch", "reviewers")
_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_BRANCH = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]+(?<!/)(?<!\.lock)$")
# Values that look like credentials must never be stored in config (rule S6, S13).
_TOKEN_VALUE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)"
)
_SECRET_KEY = re.compile(r"(token|secret|password|passwd|credential|api[_-]?key)", re.I)
_SECRET_KEY_ALLOWED = {"bot_token_env"}  # names an env var; never holds the secret itself
_MERGE_KEY = re.compile(r"merge", re.I)


class ConfigError(FactoryError):
    """The config file is invalid. ``problems`` lists every issue found."""

    def __init__(self, path: Path | str, problems: list[str]):
        self.path = Path(path)
        self.problems = list(problems)
        bullet = "\n  - "
        super().__init__(f"invalid factory config {self.path}:{bullet}{bullet.join(problems)}")


class ConfigNotFound(ConfigError):
    """The target has no ``.factory/config.json`` yet (state UNCONFIGURED)."""

    def __init__(self, path: Path | str):
        super().__init__(path, ["file not found (run /factory-start to create it)"])


@dataclass(frozen=True)
class Limits:
    max_fix_attempts: int
    max_review_rounds: int
    max_diff_lines: int


@dataclass(frozen=True)
class Identity:
    mode: str
    bot_login: str | None
    bot_token_env: str | None


@dataclass(frozen=True)
class Config:
    schema: int
    project: str
    repo: str
    default_branch: str
    reviewers: tuple[str, ...]
    commands: dict[str, str | None]  # a missing command is None: that gate is skipped (H4)
    limits: Limits
    ci_required: bool
    identity: Identity


def config_path(target: str | Path) -> Path:
    return Path(target) / CONFIG_RELPATH


def load_config(target: str | Path) -> Config:
    """Read and validate ``<target>/.factory/config.json``."""
    path = config_path(target)
    if not path.is_file():
        raise ConfigNotFound(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(path, [f"not valid JSON: {exc}"]) from None
    return parse_config(data, path)


def parse_config(data: Any, path: str | Path = CONFIG_RELPATH) -> Config:
    """Validate an already-decoded config object. Raises ``ConfigError`` listing all problems."""
    problems: list[str] = []
    if not isinstance(data, dict):
        raise ConfigError(path, ["top level must be a JSON object"])

    _scan_forbidden(data, "", problems)

    for key in sorted(set(data) - _TOP_LEVEL):
        if not _MERGE_KEY.search(key):  # merge keys already reported by _scan_forbidden
            problems.append(f"unknown key {key!r}")
    for key in _REQUIRED:
        if key not in data:
            problems.append(f"missing required key {key!r}")

    schema = data.get("schema")
    if "schema" in data and schema != SCHEMA_VERSION:
        problems.append(f"schema must be {SCHEMA_VERSION}, got {schema!r}")

    project = data.get("project")
    if "project" in data and not _nonempty_str(project):
        problems.append("project must be a non-empty string")

    repo = data.get("repo")
    if "repo" in data and not (isinstance(repo, str) and _REPO.match(repo)):
        problems.append(f"repo must look like 'owner/name', got {repo!r}")

    branch = data.get("default_branch")
    if "default_branch" in data and not (isinstance(branch, str) and _BRANCH.match(branch)):
        problems.append(f"default_branch is not a valid branch name: {branch!r}")

    reviewers = data.get("reviewers")
    if "reviewers" in data:
        if not isinstance(reviewers, list) or not reviewers:
            problems.append("reviewers must be a non-empty list of GitHub logins")
            reviewers = []
        else:
            for login in reviewers:
                if not (isinstance(login, str) and _LOGIN.match(login)):
                    problems.append(f"reviewers: invalid GitHub login {login!r}")

    commands = _section(data, "commands", problems)
    for key in sorted(set(commands) - set(COMMAND_NAMES)):
        problems.append(f"commands: unknown command {key!r} (allowed: {', '.join(COMMAND_NAMES)})")
    for name in COMMAND_NAMES:
        value = commands.get(name)
        if value is not None and not _nonempty_str(value):
            problems.append(f"commands.{name} must be a non-empty string or null")

    limits_in = _section(data, "limits", problems)
    for key in sorted(set(limits_in) - set(DEFAULT_LIMITS)):
        problems.append(f"limits: unknown key {key!r}")
    limits = dict(DEFAULT_LIMITS)
    for key in DEFAULT_LIMITS:
        if key in limits_in:
            value = limits_in[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                problems.append(f"limits.{key} must be a positive integer, got {value!r}")
            else:
                limits[key] = value

    ci = _section(data, "ci", problems)
    for key in sorted(set(ci) - {"required"}):
        problems.append(f"ci: unknown key {key!r}")
    ci_required = ci.get("required", False)
    if not isinstance(ci_required, bool):
        problems.append("ci.required must be true or false")

    ident = _section(data, "identity", problems)
    for key in sorted(set(ident) - {"mode", "bot_login", "bot_token_env"}):
        problems.append(f"identity: unknown key {key!r}")
    mode = ident.get("mode", "single-account")
    bot_login = ident.get("bot_login")
    bot_token_env = ident.get("bot_token_env")
    if mode in IDENTITY_MODES_PLANNED:
        problems.append(
            f"identity.mode {mode!r} is not implemented yet; use 'single-account' "
            "(architecture §9.4)"
        )
    elif mode not in IDENTITY_MODES_IMPLEMENTED:
        problems.append(f"identity.mode must be 'single-account', got {mode!r}")
    if bot_login is not None and not (isinstance(bot_login, str) and _LOGIN.match(bot_login)):
        problems.append(f"identity.bot_login: invalid GitHub login {bot_login!r}")
    if bot_token_env is not None and not (
        isinstance(bot_token_env, str) and _ENV_NAME.match(bot_token_env)
    ):
        problems.append(
            "identity.bot_token_env must be the NAME of an environment variable "
            "(e.g. FACTORY_BOT_TOKEN), never the token itself"
        )

    if problems:
        raise ConfigError(path, problems)

    return Config(
        schema=schema,
        project=project,
        repo=repo,
        default_branch=branch,
        reviewers=tuple(reviewers),
        commands={name: commands.get(name) for name in COMMAND_NAMES},
        limits=Limits(**limits),
        ci_required=ci_required,
        identity=Identity(mode=mode, bot_login=bot_login, bot_token_env=bot_token_env),
    )


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _section(data: dict, key: str, problems: list[str]) -> dict:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(f"{key} must be an object")
        return {}
    return value


def _scan_forbidden(node: Any, where: str, problems: list[str]) -> None:
    """Reject merge options (D1) and stored secrets (S6/S13) anywhere in the document."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{where}.{key}" if where else str(key)
            if _MERGE_KEY.search(str(key)):
                problems.append(
                    f"{here}: merging cannot be configured; the factory never merges (D1, rule S1)"
                )
            elif _SECRET_KEY.search(str(key)) and key not in _SECRET_KEY_ALLOWED:
                problems.append(
                    f"{here}: secrets must not be stored in config; "
                    "use identity.bot_token_env to name an environment variable (rule S13)"
                )
            _scan_forbidden(value, here, problems)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _scan_forbidden(item, f"{where}[{index}]", problems)
    elif isinstance(node, str) and _TOKEN_VALUE.search(node):
        problems.append(f"{where or 'value'}: looks like a token or private key; "
                        "secrets must never be stored in config (rule S6)")
