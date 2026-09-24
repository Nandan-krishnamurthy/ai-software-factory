"""``factory.py doctor``: pre-flight checks for the active target.

Every check produces an ``ok``, ``warn``, ``fail`` or ``skip`` result, and all of them
are reported together. Doctor exits non-zero only if a check **fails**. Warnings (for
example, missing branch protection) never block the factory.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

from factory import labels as labels_mod
from factory.config import Config, ConfigError, ConfigNotFound, load_config
from factory.errors import CommandError, CommandNotFound, FactoryError
from factory.gh import Gh
from factory.git import Git
from factory.target import Target, validate_target

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
_WRITE_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}
_TAGS = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def run_doctor(target: Target, gh: Gh, factory_root: Path | None = None) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append(Check(name, status, detail))

    # 1. Target: re-validated, because the repo may have changed since `target set`.
    try:
        target = validate_target(target.path, factory_root)
        add("target", OK, f"{target.path} ({target.repo}); not the factory repo")
    except FactoryError as err:
        add("target", FAIL, str(err))
        for name in ("working tree", "config", "gh auth", "remote", "labels",
                     "branch protection"):
            add(name, SKIP, "target is invalid")
        return checks

    # 2. Working tree.
    try:
        status = Git(target.path).run(["status", "--porcelain"]).splitlines()
        if status:
            shown = "; ".join(line.strip() for line in status[:5])
            more = f" (+{len(status) - 5} more)" if len(status) > 5 else ""
            add("working tree", FAIL,
                f"{len(status)} uncommitted change(s): {shown}{more}. Commit or stash them.")
        else:
            add("working tree", OK, "clean")
    except CommandError as err:
        add("working tree", FAIL, str(err))

    # 3. Config.
    config: Config | None = None
    try:
        config = load_config(target.path)
        if config.repo.lower() != target.repo.lower():
            add("config", FAIL,
                f"config repo {config.repo!r} does not match the target's origin {target.repo!r}")
        else:
            add("config", OK,
                f"project {config.project!r}, default branch {config.default_branch!r}, "
                f"reviewers {', '.join(config.reviewers)}")
    except ConfigNotFound:
        add("config", WARN, "no .factory/config.json yet; /factory-start creates it")
    except ConfigError as err:
        add("config", FAIL, "; ".join(err.problems))

    # 4. gh authentication.
    try:
        login = gh.api("user")["login"]
    except CommandNotFound:
        add("gh auth", FAIL, "the gh CLI is not installed or not on PATH")
        login = None
    except (CommandError, KeyError, TypeError) as err:
        add("gh auth", FAIL, f"not authenticated; run `gh auth login`. ({_first_line(err)})")
        login = None
    if login is None:
        for name in ("remote", "labels", "branch protection"):
            add(name, SKIP, "gh is not authenticated")
        return checks
    if config is not None and config.identity.mode == "single-account" \
            and login.lower() not in {r.lower() for r in config.reviewers}:
        add("gh auth", WARN,
            f"logged in as {login}, who is not in config.reviewers: in single-account mode "
            "your /changes comments would be ignored (architecture §9.2)")
    else:
        add("gh auth", OK, f"logged in as {login}")

    # 5. Remote reachable, with write access.
    repo_info: dict = {}
    try:
        repo_info = gh.json(["repo", "view", target.repo],
                            fields=["nameWithOwner", "viewerPermission", "defaultBranchRef",
                                    "isEmpty"])
        permission = repo_info.get("viewerPermission")
        if permission not in _WRITE_PERMISSIONS:
            add("remote", FAIL, f"{target.repo} is reachable, but {login} has {permission} "
                                "access; the factory needs write access")
        else:
            add("remote", OK, f"{repo_info.get('nameWithOwner')} reachable ({permission})")
    except CommandError as err:
        add("remote", FAIL, f"cannot reach {target.repo}: {_first_line(err)}")
        for name in ("labels", "branch protection"):
            add(name, SKIP, "remote is not reachable")
        return checks

    # 6. Labels.
    try:
        plan = labels_mod.plan_labels(labels_mod.list_labels(gh, target.repo))
        if plan.create:
            add("labels", FAIL, "missing: " + ", ".join(s.name for s in plan.create)
                + ". Run `python scripts/factory.py labels ensure`.")
        elif plan.update:
            add("labels", WARN, "colour/description differ: "
                + ", ".join(spec.name for _, spec in plan.update)
                + ". Run `python scripts/factory.py labels ensure`.")
        else:
            add("labels", OK, f"all {len(plan.unchanged)} factory labels present")
    except CommandError as err:
        add("labels", FAIL, f"cannot list labels: {_first_line(err)}")

    # 7. Branch protection (warn only, architecture §9.3).
    branch = config.default_branch if config else \
        (repo_info.get("defaultBranchRef") or {}).get("name") or ""
    status, detail = _branch_protection(gh, target.repo, branch, repo_info.get("isEmpty"))
    add("branch protection", status, detail)
    return checks


def _branch_protection(gh: Gh, repo: str, branch: str, is_empty: bool | None) -> tuple[str, str]:
    if is_empty or not branch:
        return WARN, "repository is empty; protect the default branch after the first push"
    try:
        protection = gh.api(f"repos/{repo}/branches/{quote(branch, safe='')}/protection")
    except CommandError as err:
        message = err.stderr
        if "Branch not protected" in message:
            return WARN, (f"{branch!r} is not protected; recommended: require a pull request, "
                          "no required approvals, include administrators")
        if "Branch not found" in message:
            return WARN, f"branch {branch!r} does not exist yet"
        return WARN, f"could not read protection for {branch!r} (needs admin): " \
                     f"{_first_line(err)}"

    problems = []
    reviews = protection.get("required_pull_request_reviews")
    if not reviews:
        problems.append("pull requests are not required")
    elif (reviews.get("required_approving_review_count") or 0) > 0:
        problems.append("an approving review is required, which blocks your own merge in "
                        "single-account mode; set required approvals to 0")
    if (protection.get("allow_force_pushes") or {}).get("enabled"):
        problems.append("force pushes are allowed")
    if not (protection.get("enforce_admins") or {}).get("enabled"):
        problems.append("administrators can bypass it")
    if problems:
        return WARN, f"{branch!r} is protected, but: " + "; ".join(problems)
    return OK, f"{branch!r} requires a pull request; no force pushes; applies to admins"


def _first_line(err: Exception) -> str:
    stderr = getattr(err, "stderr", "") or ""
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return str(err).splitlines()[0] if str(err) else type(err).__name__


def render(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = [f"  {_TAGS[c.status]} {c.name.ljust(width)}  {c.detail}" for c in checks]
    fails = sum(c.status == FAIL for c in checks)
    warns = sum(c.status == WARN for c in checks)
    verdict = "FAILED" if fails else "PASSED"
    lines.append(f"Doctor {verdict}: {fails} failed, {warns} warning(s).")
    return "\n".join(["Factory doctor", *lines])


def to_json(checks: list[Check]) -> str:
    return json.dumps({"ok": not any(c.status == FAIL for c in checks),
                       "checks": [asdict(c) for c in checks]}, indent=2)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == FAIL for c in checks) else 0
