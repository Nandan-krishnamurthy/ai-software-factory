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
  the highest *allocated* number (T7.1). Only structured records allocate:
  ``- **REQ-###**`` bullets in an increment's ``02-requirements.md`` and ``### STORY-###``
  headings in its ``05-stories.md``, both in the working tree and at the head commit of
  every Planning PR (open, merged or closed, so an abandoned plan's IDs are never handed
  out again), and story issues carrying both the ``factory:story`` label and the marker.
  If a Planning PR's records cannot be read, every ID in its body counts instead, with a
  warning: the fallback may count more IDs, never fewer.
* **Mentions are only warnings.** An ID written anywhere else (prose under
  ``docs/factory/``, a Planning PR body, the marker of an issue without the label) does
  not use up a number. If it is not allocated, ``increment show`` warns about it.
* **One increment at a time.** A new increment is refused while the current one is still
  in planning (Gate A not passed), still has stories without issues, or has an open
  story that is not blocked. A story is blocked if it has the ``status:blocked`` or
  ``factory:needs-human`` label, or an open story issue in its ``Blocked by`` line. (An
  issue number that is not a story issue counts as done, so in doubt a new increment is
  refused rather than allowed.)

``assess()`` is pure. ``scan_layout()`` reads the target on disk; ``collect_remote()``
reads GitHub.
"""

import base64
import binascii
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory import issues as issues_mod
from factory.errors import CommandError, FactoryError, GhError
from factory.gh import Gh
from factory.markers import PlanningMarker, find
from factory.state import PLAN_BRANCH_PREFIX

INCREMENTS_DIR = Path("docs") / "factory" / "increments"
DOCS_DIR = Path("docs") / "factory"
REQUIREMENTS_FILE = "02-requirements.md"
STORY_LABEL = "factory:story"
FIRST_SLUG = "initial"  # a new project's first increment is 001-initial (architecture §5.2)
MAX_SLUG = 40
_INCREMENT = re.compile(r"^(?P<number>\d{3})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_REQ = re.compile(r"\bREQ-(\d{3,})\b")  # a mention, anywhere
_STORY = re.compile(r"\bSTORY-(\d{3,})\b")
_REQ_BULLET = re.compile(r"^\s*-\s+\*\*REQ-(\d{3,})\*\*", re.MULTILINE)  # a record
_STORY_HEADING = re.compile(r"^###\s+(STORY-\d{3,})\b", re.MULTILINE)
_HTTP_STATUS = re.compile(r"HTTP \d{3}")
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
    req_numbers: frozenset[int] = frozenset()  # allocated: REQ bullets in 02-requirements.md
    story_numbers: frozenset[int] = frozenset()  # allocated: STORY headings in 05-stories.md
    stories: dict[str, frozenset[str]] = field(default_factory=dict)  # inc -> STORY ids
    mentions: dict[str, frozenset[str]] = field(default_factory=dict)  # ID -> relative paths


@dataclass(frozen=True)
class PlanRecords:
    """One Planning PR: the records in its increment's files at its head commit.

    ``error`` says why they could not be read; ``assess`` then counts every ID in ``body``.
    """

    pr: int
    increment: str
    head: str | None = None
    req_numbers: frozenset[int] = frozenset()
    story_numbers: frozenset[int] = frozenset()
    body: str = ""
    error: str | None = None


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
    plans: tuple[PlanRecords, ...] = ()  # every Planning PR, any state
    issues: tuple[StoryIssue, ...] = ()  # every issue with a story marker, any labels
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
    warnings: tuple[str, ...] = ()  # IDs mentioned but never allocated; unreadable plans

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "increments": list(self.increments),
            "can_start": not self.reasons,
            "next_increment": self.next_increment,
            "next_req": self.next_req,
            "next_story": self.next_story,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


# ----------------------------------------------------------------------------- pure


def is_increment(name: str) -> bool:
    return bool(_INCREMENT.match(name))


def increment_number(name: str) -> int:
    return int(name[:3])


def slugify(text: str) -> str:
    """``"Export to CSV!"`` → ``"export-to-csv"``. Raises ``ValueError`` if nothing is left."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_SLUG].strip("-")
    if not slug:
        raise ValueError(f"cannot make an increment slug from {text!r}")
    return slug


def format_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:03d}"


def requirement_ids(text: str) -> frozenset[int]:
    """The REQ numbers a ``02-requirements.md`` allocates: its ``- **REQ-###**`` bullets."""
    return frozenset(int(n) for n in _REQ_BULLET.findall(text))


def story_ids(text: str) -> frozenset[int]:
    """The STORY numbers a ``05-stories.md`` allocates: its ``### STORY-###`` headings."""
    return frozenset(int(s.split("-", 1)[1]) for s in _STORY_HEADING.findall(text))


def mentioned_ids(text: str) -> set[str]:
    """Every ``REQ-###``/``STORY-###`` written anywhere in ``text``, as ``format_id`` gives it."""
    return ({format_id("REQ", int(n)) for n in _REQ.findall(text)}
            | {format_id("STORY", int(n)) for n in _STORY.findall(text)})


def _labelled(issues: tuple[StoryIssue, ...]) -> list[StoryIssue]:
    """Story issues carrying the ``factory:story`` label, as the state engine lists them."""
    return [i for i in issues if STORY_LABEL in {label.lower() for label in i.labels}]


def _id_key(story_or_req: str) -> tuple[str, int]:
    prefix, number = story_or_req.split("-", 1)
    return prefix, int(number)


def _sorted(names) -> list[str]:
    return sorted((n for n in names if is_increment(n)), key=lambda n: (increment_number(n), n))


def planned_increments(layout: Layout, remote: Remote) -> list[str]:
    """Increments that went through (or are in) planning: the candidates for *current*."""
    return _sorted(set(layout.increments) | set(remote.plan_branches)
                   | set(remote.planning_prs))


def known_increments(layout: Layout, remote: Remote) -> list[str]:
    """Every increment name seen anywhere, including only in labelled story issue markers."""
    return _sorted(set(planned_increments(layout, remote))
                   | {i.increment for i in _labelled(remote.issues)})


def allocated(layout: Layout, remote: Remote) -> tuple[set[int], set[int]]:
    """The allocated REQ and STORY numbers: structured records and labelled story issues."""
    reqs = set(layout.req_numbers)
    stories = set(layout.story_numbers)
    for plan in remote.plans:
        if plan.error is None:
            reqs |= plan.req_numbers
            stories |= plan.story_numbers
        else:  # conservative fallback: count every ID in the body, never fewer
            reqs |= {int(n) for n in _REQ.findall(plan.body)}
            stories |= {int(n) for n in _STORY.findall(plan.body)}
    stories |= {int(i.story_id.split("-", 1)[1]) for i in _labelled(remote.issues)}
    return reqs, stories


def id_warnings(layout: Layout, remote: Remote, reqs: set[int], stories: set[int]) -> list[str]:
    """IDs mentioned but never allocated (by ID, naming every source), then unreadable plans."""
    sources: dict[str, list[tuple[int, int, str, str]]] = {}  # ID -> sortable sources

    def add(story_or_req: str, rank: int, number: int, name: str, label: str) -> None:
        sources.setdefault(story_or_req, []).append((rank, number, name, label))

    for found, paths in layout.mentions.items():
        for path in paths:
            add(found, 0, 0, path, path)
    for plan in remote.plans:
        for found in mentioned_ids(plan.body):
            add(found, 1, plan.pr, "", f"Planning PR #{plan.pr}")
    labelled = {i.number for i in _labelled(remote.issues)}
    for i in remote.issues:
        if i.number not in labelled:
            add(i.story_id, 2, i.number, "", f"issue #{i.number}")

    result = []
    for found in sorted(sources, key=_id_key):
        prefix, number = _id_key(found)
        if number in (reqs if prefix == "REQ" else stories):
            continue
        labels = [label for *_, label in sorted(set(sources[found]))]
        result.append(f"{found} is mentioned in {', '.join(labels)} but never allocated")
    for plan in remote.plans:
        if plan.error is not None:
            commit = plan.head[:7] if plan.head else "unknown commit"
            result.append(f"Planning PR #{plan.pr}: its records at {commit} could not be read "
                          f"({plan.error}); every ID in its body was counted instead")
    return result


def assess(layout: Layout, remote: Remote, slug: str | None = None) -> Assessment:
    """Pure: the current increment, the next one (or why not), the next IDs, and warnings."""
    increments = known_increments(layout, remote)
    planned = planned_increments(layout, remote)
    current = planned[-1] if planned else None

    reqs, stories = allocated(layout, remote)
    next_req = format_id("REQ", max(reqs, default=0) + 1)
    next_story = format_id("STORY", max(stories, default=0) + 1)
    notes = tuple(id_warnings(layout, remote, reqs, stories))

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
                      tuple(reasons), notes)


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
    """Read increments, allocated IDs, story lists and ID mentions from the working tree."""
    root = Path(target)
    inc_root = root / INCREMENTS_DIR
    increments = frozenset(p.name for p in inc_root.iterdir()
                           if p.is_dir() and is_increment(p.name)) if inc_root.is_dir() \
        else frozenset()
    reqs: set[int] = set()
    story_numbers: set[int] = set()
    stories: dict[str, frozenset[str]] = {}
    for inc in increments:
        path = inc_root / inc / REQUIREMENTS_FILE
        if path.is_file():
            reqs |= requirement_ids(_read(path))
        path = inc_root / inc / issues_mod.STORIES_FILE
        if path.is_file():
            text = _read(path)
            stories[inc] = frozenset(_STORY_HEADING.findall(text))
            story_numbers |= story_ids(text)
    mentions: dict[str, set[str]] = {}
    docs = root / DOCS_DIR
    for path in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        for found in mentioned_ids(_read(path)):
            mentions.setdefault(found, set()).add(path.relative_to(root).as_posix())
    return Layout(increments, frozenset(reqs), frozenset(story_numbers), stories,
                  {k: frozenset(v) for k, v in mentions.items()})


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class _Unreadable(Exception):
    """A Planning PR's records could not be read; the message says why."""


def read_plan(gh: Gh, repo: str, number: int, increment: str, head: str | None,
              body: str) -> PlanRecords:
    """The records of a Planning PR's increment at its head commit, by SHA only (so a
    deleted source branch does not matter). On any failure, ``error`` says why."""
    if not head:
        return PlanRecords(number, increment, None, body=body, error="no head commit")
    try:
        try:
            gh.api(f"repos/{repo}/commits/{head}")
        except CommandError as err:
            raise _Unreadable(f"commit {_failure(err)}") from None
        base = (INCREMENTS_DIR / increment).as_posix()
        reqs = requirement_ids(_read_file(gh, repo, head, f"{base}/{REQUIREMENTS_FILE}"))
        stories = story_ids(_read_file(gh, repo, head, f"{base}/{issues_mod.STORIES_FILE}"))
    except _Unreadable as err:
        return PlanRecords(number, increment, head, body=body, error=str(err))
    return PlanRecords(number, increment, head, reqs, stories, body)


def _read_file(gh: Gh, repo: str, head: str, path: str) -> str:
    """A file's text at ``head``; ``""`` if the commit has no such file."""
    try:
        data = gh.api(f"repos/{repo}/contents/{path}?ref={head}")
    except CommandError as err:
        if "HTTP 404" in err.stderr:
            return ""  # e.g. the plan was abandoned before S05 wrote its stories
        raise _Unreadable(f"{path}: {_failure(err)}") from None
    if not isinstance(data, dict) or data.get("type") != "file" \
            or data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise _Unreadable(f"{path}: the contents API returned no base64 file content")
    try:
        return base64.b64decode("".join(data["content"].split()), validate=True) \
            .decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        raise _Unreadable(f"{path}: its content could not be decoded") from None


def _failure(err: CommandError) -> str:
    """A short reason: the HTTP status if ``gh`` gave one, else the error's first line."""
    if m := _HTTP_STATUS.search(err.stderr):
        return m[0]
    lines = err.stderr.strip().splitlines()
    return err.detail or (lines[0][:120] if lines else f"exit {err.returncode}")


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
    plans: list[PlanRecords] = []
    for pr in gh.json(["pr", "list", "--repo", repo, "--state", "all", "--limit", "1000"],
                      fields=["number", "state", "body", "headRefOid"]):
        marker = find(pr.get("body"), PlanningMarker)
        if marker is not None:
            planning.setdefault(marker.increment, []).append(pr["state"])
            plans.append(read_plan(gh, repo, pr["number"], marker.increment,
                                   pr.get("headRefOid"), pr.get("body") or ""))
    plans.sort(key=lambda plan: plan.pr)

    story_issues: list[StoryIssue] = []
    open_numbers: set[int] = set()
    for found in issues_mod.list_story_issues(gh, repo).values():
        for i in found:
            is_open = i.state.lower() == "open"
            if is_open:
                open_numbers.add(i.number)
            story_issues.append(StoryIssue(i.number, i.story_id, i.increment, is_open,
                                           i.labels, i.blocked_by))
    return Remote(plan_branches, {k: tuple(v) for k, v in planning.items()}, tuple(plans),
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
    lines += [f"Warning: {warning}" for warning in result.warnings]
    return "\n".join(lines)
