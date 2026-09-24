"""Increments: the current one, the next ``NNN-slug``, and global ID numbering (T2.3).

An increment is one pass through planning (architecture §5.2): one PRD or change request,
one Planning PR, one set of stories, in ``docs/factory/increments/<NNN-slug>/``.

* **Current increment**: the highest-numbered one with a folder in the target, a
  ``factory/plan-<inc>`` branch, or a Planning PR (open, merged or closed). These are the
  state engine's sources, plus the local folder.
* **Next increment**: one above the highest number known anywhere, including increments
  seen only in story issue markers (e.g. issues created by hand or by a test), so an
  increment number is never reused, even one whose planning was abandoned.
* **IDs are global and never reused.** The next ``REQ-###``/``STORY-###`` is one above
  the highest number mentioned in any file under ``docs/factory/``, in any story issue
  marker, or in any Planning PR body (which also covers abandoned plans).
* **One increment at a time.** A new increment is refused while the current one is still
  in planning (Gate A not passed), still has stories without issues, or has an open
  story that is not blocked. A story is blocked if it has the ``status:blocked`` or
  ``factory:needs-human`` label, or an open story issue in its ``Blocked by`` line. (An
  issue number that is not a story issue counts as done, so in doubt a new increment is
  refused rather than allowed.)

``assess()`` is pure. ``scan_layout()`` reads the target on disk; ``collect_remote()``
reads GitHub.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory import issues as issues_mod
from factory.errors import FactoryError, GhError
from factory.gh import Gh
from factory.markers import PlanningMarker, find
from factory.state import PLAN_BRANCH_PREFIX

INCREMENTS_DIR = Path("docs") / "factory" / "increments"
DOCS_DIR = Path("docs") / "factory"
FIRST_SLUG = "initial"  # a new project's first increment is 001-initial (architecture §5.2)
MAX_SLUG = 40
_INCREMENT = re.compile(r"^(?P<number>\d{3})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_REQ = re.compile(r"\bREQ-(\d{3,})\b")
_STORY = re.compile(r"\bSTORY-(\d{3,})\b")
_STORY_HEADING = re.compile(r"^###\s+(STORY-\d{3,})\b", re.MULTILINE)
_BLOCKING_LABELS = {"status:blocked", "factory:needs-human"}


class IncrementError(FactoryError):
    """A new increment cannot be started now. ``reasons`` lists why."""

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        bullet = "\n  - "
        super().__init__("a new increment cannot be started yet:" + bullet
                         + bullet.join(self.reasons))


# ----------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class Layout:
    """What the target's working tree says (``scan_layout``)."""

    increments: frozenset[str] = frozenset()
    req_numbers: frozenset[int] = frozenset()
    story_numbers: frozenset[int] = frozenset()
    stories: dict[str, frozenset[str]] = field(default_factory=dict)  # inc -> STORY ids


@dataclass(frozen=True)
class StoryIssue:
    number: int
    story_id: str
    increment: str
    open: bool
    labels: frozenset[str] = frozenset()
    blocked_by: tuple[int, ...] = ()


@dataclass(frozen=True)
class Remote:
    """What GitHub says (``collect_remote``)."""

    plan_branches: frozenset[str] = frozenset()  # increments with a factory/plan-<inc> branch
    planning_prs: dict[str, tuple[str, ...]] = field(default_factory=dict)  # inc -> states
    planning_bodies: tuple[str, ...] = ()
    issues: tuple[StoryIssue, ...] = ()
    open_numbers: frozenset[int] = frozenset()  # every open issue number seen


# ----------------------------------------------------------------------------- output


@dataclass(frozen=True)
class Assessment:
    current: str | None
    increments: tuple[str, ...]  # every known increment, in order
    next_increment: str | None  # None when refused, or when no slug was given
    next_req: str
    next_story: str
    reasons: tuple[str, ...] = ()  # why a new increment is refused (empty when allowed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "increments": list(self.increments),
            "can_start": not self.reasons,
            "next_increment": self.next_increment,
            "next_req": self.next_req,
            "next_story": self.next_story,
            "reasons": list(self.reasons),
        }


# ----------------------------------------------------------------------------- pure


def is_increment(name: str) -> bool:
    return bool(_INCREMENT.match(name))


def increment_number(name: str) -> int:
    return int(name[:3])


def slugify(text: str) -> str:
    """``"Add due dates!"`` → ``"add-due-dates"``. Raises ``ValueError`` if nothing is left."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_SLUG].strip("-")
    if not slug:
        raise ValueError(f"cannot make an increment slug from {text!r}")
    return slug


def format_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:03d}"


def _sorted(names) -> list[str]:
    return sorted((n for n in names if is_increment(n)), key=lambda n: (increment_number(n), n))


def planned_increments(layout: Layout, remote: Remote) -> list[str]:
    """Increments that went through (or are in) planning: the candidates for *current*."""
    return _sorted(set(layout.increments) | set(remote.plan_branches)
                   | set(remote.planning_prs))


def known_increments(layout: Layout, remote: Remote) -> list[str]:
    """Every increment name seen anywhere, including only in story issue markers."""
    return _sorted(set(planned_increments(layout, remote))
                   | {i.increment for i in remote.issues})


def assess(layout: Layout, remote: Remote, slug: str | None = None) -> Assessment:
    """Pure: the current increment, the next one (or why not), and the next IDs."""
    increments = known_increments(layout, remote)
    planned = planned_increments(layout, remote)
    current = planned[-1] if planned else None

    reqs = set(layout.req_numbers)
    stories = set(layout.story_numbers)
    for body in remote.planning_bodies:
        reqs |= {int(n) for n in _REQ.findall(body)}
        stories |= {int(n) for n in _STORY.findall(body)}
    stories |= {int(i.story_id.split("-", 1)[1]) for i in remote.issues}
    next_req = format_id("REQ", max(reqs, default=0) + 1)
    next_story = format_id("STORY", max(stories, default=0) + 1)

    reasons = _blockers(current, layout, remote) if current else []
    next_increment = None
    if not reasons and (slug or current is None):  # else only the numbering is reported
        number = max((increment_number(n) for n in increments), default=0) + 1
        if number > 999:
            reasons = ["increment numbers are used up (999)"]
        else:
            name_slug = slugify(slug) if slug else FIRST_SLUG
            next_increment = f"{number:03d}-{name_slug}"
    return Assessment(current, tuple(increments), next_increment, next_req, next_story,
                      tuple(reasons))


def _blockers(current: str, layout: Layout, remote: Remote) -> list[str]:
    states = remote.planning_prs.get(current, ())
    if "MERGED" not in states:
        abandoned = "CLOSED" in states and "OPEN" not in states \
            and current not in remote.plan_branches
        if abandoned:
            return []  # the Planning PR was closed and its branch deleted: re-plan is allowed
        branch = f"{PLAN_BRANCH_PREFIX}{current}"
        undo = []
        if "OPEN" in states:
            undo.append("close its Planning PR")
        if current in remote.plan_branches:
            undo.append(f"delete branch {branch}")
        if not undo:  # only the local folder exists: S00 has not pushed anything yet
            undo.append(f"delete the local folder {INCREMENTS_DIR.as_posix()}/{current}")
        return [f"increment {current} has not passed Gate A (its Planning PR is not merged). "
                f"Finish it with /factory-resume, or {' and '.join(undo)} to abandon it."]

    reasons: list[str] = []
    planned = layout.stories.get(current)
    story_issues = [i for i in remote.issues if i.increment == current]
    if planned is None:
        reasons.append(f"docs/factory/increments/{current}/05-stories.md is missing locally: "
                       "pull the default branch first.")
    else:
        missing = sorted(planned - {i.story_id for i in story_issues})
        if missing:
            reasons.append(f"increment {current} has stories without issues "
                           f"({', '.join(missing)}): run /factory-resume to create them.")
    active = sorted((i for i in story_issues if i.open and not _blocked(i, remote)),
                    key=lambda i: i.number)
    if active:
        reasons.append(f"increment {current} still has open, unblocked stories: "
                       + ", ".join(f"#{i.number} ({i.story_id})" for i in active)
                       + ". Finish them, or label them status:blocked.")
    return reasons


def _blocked(issue: StoryIssue, remote: Remote) -> bool:
    if issue.labels & _BLOCKING_LABELS:
        return True
    return any(n in remote.open_numbers for n in issue.blocked_by)


# ----------------------------------------------------------------------------- I/O


def scan_layout(target: Path) -> Layout:
    """Read increments, IDs and story lists from the target's working tree."""
    root = Path(target)
    inc_root = root / INCREMENTS_DIR
    increments = frozenset(p.name for p in inc_root.iterdir()
                           if p.is_dir() and is_increment(p.name)) if inc_root.is_dir() \
        else frozenset()
    reqs: set[int] = set()
    story_numbers: set[int] = set()
    docs = root / DOCS_DIR
    for path in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        text = path.read_text(encoding="utf-8", errors="replace")
        reqs |= {int(n) for n in _REQ.findall(text)}
        story_numbers |= {int(n) for n in _STORY.findall(text)}
    stories: dict[str, frozenset[str]] = {}
    for inc in increments:
        path = inc_root / inc / issues_mod.STORIES_FILE
        if path.is_file():
            stories[inc] = frozenset(_STORY_HEADING.findall(
                path.read_text(encoding="utf-8", errors="replace")))
    return Layout(increments, frozenset(reqs), frozenset(story_numbers), stories)


def collect_remote(gh: Gh, repo: str) -> Remote:
    """Plan branches, Planning PRs (all states) and story issues from GitHub."""
    try:
        branches = [b["name"] for b in gh.api(f"repos/{repo}/branches", paginate=True)]
    except GhError as err:
        if "HTTP 404" not in err.stderr and "HTTP 409" not in err.stderr:
            raise
        branches = []  # empty repository
    plan_branches = frozenset(b[len(PLAN_BRANCH_PREFIX):] for b in branches
                              if b.startswith(PLAN_BRANCH_PREFIX))

    planning: dict[str, list[str]] = {}
    bodies: list[str] = []
    for pr in gh.json(["pr", "list", "--repo", repo, "--state", "all", "--limit", "1000"],
                      fields=["number", "state", "body"]):
        marker = find(pr.get("body"), PlanningMarker)
        if marker is not None:
            planning.setdefault(marker.increment, []).append(pr["state"])
            bodies.append(pr.get("body") or "")

    story_issues: list[StoryIssue] = []
    open_numbers: set[int] = set()
    for found in issues_mod.list_story_issues(gh, repo).values():
        for i in found:
            is_open = i.state.lower() == "open"
            if is_open:
                open_numbers.add(i.number)
            story_issues.append(StoryIssue(i.number, i.story_id, i.increment, is_open,
                                           i.labels, i.blocked_by))
    return Remote(plan_branches, {k: tuple(v) for k, v in planning.items()}, tuple(bodies),
                  tuple(story_issues), frozenset(open_numbers))


def assess_target(gh: Gh, target: Path, repo: str, slug: str | None = None) -> Assessment:
    return assess(scan_layout(target), collect_remote(gh, repo), slug)


def render(result: Assessment, *, allocating: bool) -> str:
    lines = [f"Current increment: {result.current or 'none yet'}"]
    if result.increments:
        lines.append("All increments: " + ", ".join(result.increments))
    lines.append(f"Next IDs: {result.next_req}, {result.next_story}")
    if result.next_increment:
        lines.append(f"Next increment: {result.next_increment}")
    elif allocating or result.reasons:
        lines.append("A new increment cannot be started yet:")
        lines += [f"  - {reason}" for reason in result.reasons]
    return "\n".join(lines)
