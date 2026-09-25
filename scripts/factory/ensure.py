"""Idempotent create-type actions: branches and PRs (T4.4, resume robustness).

A session can end at any point, and the next ``/factory-resume`` runs the same station
again from its start (requirements §8). Every action that *creates* something must
therefore look for it first:

* ``ensure_branch`` reuses the story's branch if it exists on ``origin`` (the station
  pushed it before the session ended) or only locally (it had not pushed yet), and
  creates it from ``origin/<default>`` only when neither exists. A story branch is
  matched by its issue number (``story/<I>-*``), so a second run that chose another slug
  still finds the first one. It refuses on a dirty working tree: uncommitted changes
  are reported and never discarded, whoever made them.
* ``ensure_pr`` edits the open PR of a head branch if there is one and creates it only
  otherwise. The body must carry its ``factory:pr`` or ``factory:planning`` marker, which
  is how the state engine finds the PR.

Issues (``issues sync``), checkpoints (``comment --kind checkpoint``), status labels
(``label``), picking (``pick``) and close-out (``closeout --finish``) were idempotent
already.
"""

import re
from dataclasses import dataclass

from factory.errors import FactoryError, GitError
from factory.gh import Gh
from factory.git import Git
from factory.markers import PlanningMarker, PrMarker, find

_STORY_BRANCH = re.compile(r"^story/(\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_PR_URL = re.compile(r"/pull/(\d+)\s*$")


class EnsureError(FactoryError):
    """The item could not be found or created safely."""


@dataclass(frozen=True)
class BranchResult:
    name: str
    action: str  # "created" | "reused-remote" | "reused-local"


@dataclass(frozen=True)
class PrResult:
    number: int
    url: str
    action: str  # "created" | "updated"
    is_draft: bool


# ----------------------------------------------------------------------------- git


def dirty_files(git: Git) -> list[str]:
    """``git status --porcelain`` lines: staged, unstaged and untracked changes."""
    return [line for line in git.run(["status", "--porcelain"]).splitlines() if line.strip()]


def uncommitted_message(files: list[str]) -> str:
    shown = "\n".join(f"  {line}" for line in files[:20])
    more = f"\n  … and {len(files) - 20} more" if len(files) > 20 else ""
    return ("the target has uncommitted changes, which the factory never discards:\n"
            f"{shown}{more}\nCommit them on their branch, or set them aside with "
            "`git stash`, then run the command again")


def family(name: str) -> str:
    """The branches that count as the same one: ``story/<I>-*`` for a story branch."""
    match = _STORY_BRANCH.match(name)
    return f"story/{match[1]}-" if match else name


def _matches(name: str, candidate: str) -> bool:
    fam = family(name)
    return candidate.startswith(fam) if fam != name else candidate == name


def _pattern(name: str) -> str:
    fam = family(name)
    return f"{fam}*" if fam != name else name


def remote_branches(git: Git, name: str) -> list[str]:
    out = git.run(["ls-remote", "--heads", "origin", _pattern(name)])
    heads = [line.split("\t", 1)[1].removeprefix("refs/heads/")
             for line in out.splitlines() if "\t" in line]
    return sorted(h for h in heads if _matches(name, h))


def local_branches(git: Git, name: str) -> list[str]:
    out = git.run(["branch", "--list", _pattern(name), "--format=%(refname:short)"])
    return sorted(b.strip() for b in out.splitlines() if _matches(name, b.strip()))


def ensure_branch(git: Git, name: str, base: str) -> BranchResult:
    """Switch to the branch ``name`` (or its story family), creating it only if needed."""
    if family(name) == name and name.startswith("story/"):
        raise EnsureError(f"invalid story branch name {name!r}: use story/<issue>-<slug>")
    files = dirty_files(git)
    if files:
        raise EnsureError(uncommitted_message(files))
    git.run(["fetch", "origin", "--prune"])

    remote = remote_branches(git, name)
    if len(remote) > 1:
        raise EnsureError("several branches on origin match " + _pattern(name) + ": "
                          + ", ".join(remote) + ". Keep one, then run the command again")
    local = local_branches(git, name)
    if remote:
        chosen = remote[0]
        if chosen in local:
            git.run(["switch", chosen])
            git.run(["pull", "--ff-only", "origin", chosen])
        else:
            git.run(["switch", "-c", chosen, "--track", f"origin/{chosen}"])
        return BranchResult(chosen, "reused-remote")
    if len(local) > 1:
        raise EnsureError("several local branches match " + _pattern(name) + ": "
                          + ", ".join(local) + ". Keep one, then run the command again")
    if local:  # created by an earlier run that stopped before its first push
        git.run(["switch", local[0]])
        return BranchResult(local[0], "reused-local")
    try:
        git.run(["switch", "--no-track", "-c", name, f"origin/{base}"])
    except GitError as err:
        raise EnsureError(f"cannot create {name} from origin/{base}: "
                          f"{err.stderr.strip() or err}") from None
    return BranchResult(name, "created")


# ----------------------------------------------------------------------------- GitHub


def ensure_pr(gh: Gh, repo: str, *, head: str, base: str, title: str, body: str,
              draft: bool = False, labels: tuple[str, ...] = ()) -> PrResult:
    """Edit the open PR of ``head``, or create it if there is none."""
    if find(body, PrMarker) is None and find(body, PlanningMarker) is None:
        raise EnsureError("the PR body has no <!-- factory:pr … --> or "
                          "<!-- factory:planning … --> marker; the state engine finds PRs "
                          "by it")
    found = gh.json(["pr", "list", "--repo", repo, "--head", head, "--state", "open"],
                    fields=["number", "url", "isDraft", "baseRefName"])
    if len(found) > 1:
        raise EnsureError(f"several open PRs for {head}: "
                          + ", ".join(f"#{p['number']}" for p in found)
                          + ". Close the extra ones, then run the command again")
    if found:
        pr = found[0]
        if pr.get("baseRefName") not in (None, base):
            raise EnsureError(f"PR #{pr['number']} for {head} targets "
                              f"{pr['baseRefName']!r}, not {base!r}")
        gh.run(["pr", "edit", str(pr["number"]), "--repo", repo, "--title", title,
                "--body-file", "-"], input=body)
        for label in labels:
            gh.run(["pr", "edit", str(pr["number"]), "--repo", repo, "--add-label", label])
        return PrResult(pr["number"], pr.get("url", ""), "updated", bool(pr.get("isDraft")))
    args = ["pr", "create", "--repo", repo, "--base", base, "--head", head, "--title", title,
            "--body-file", "-"]
    if draft:
        args.append("--draft")
    for label in labels:
        args += ["--label", label]
    url = gh.run(args, input=body).strip().splitlines()[-1].strip()
    match = _PR_URL.search(url)
    if match is None:
        raise EnsureError(f"gh pr create printed no PR URL: {url!r}")
    return PrResult(int(match[1]), url, "created", draft)
