"""``factory.py issues sync``: one GitHub issue per story (station S05b, T2.2).

* **Idempotent.** Existing story issues are found by their ``factory:story`` marker
  (architecture §5.5), never by title, and among *all* issues, whatever their labels.
  Only the missing ones are created, so a second run creates nothing, and a run that was
  interrupted halfway finishes the job without duplicates. Issues too new to be in
  GitHub's (lagging) issue list are found one by one (``list_story_issues``).
* **Dependencies.** ``Blocked by: STORY-###`` becomes ``Blocked by: #N``. Issues are
  created in dependency order (file order otherwise), so every dependency already has
  its number when a story that needs it is created.
* **Gate A.** A real run only works once the increment's Planning PR is merged, and it
  reads ``05-stories.md`` from the default branch on GitHub: the version you approved.
  ``--dry-run`` reads the local file instead (so S05 can show the plan in the Planning
  PR), prints exactly what a real run would do, and changes nothing.

New issues are labelled ``factory:story`` and ``status:ready``: they were approved at
Gate A. Whether a story's dependencies are done is worked out when a story is picked.
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path

from factory import templates
from factory.errors import FactoryError, GhError
from factory.gh import Gh
from factory.labels import list_labels
from factory.markers import PlanningMarker, StoryMarker, find
from factory.stories import Problem, StoriesError, Story, parse

INCREMENTS_DIR = Path("docs") / "factory" / "increments"
STORIES_FILE = "05-stories.md"
STORY_LABELS = ("factory:story", "status:ready")
MAX_BODY = 65536  # GitHub's limit for an issue body
MAX_PROBE = 1000  # issues fetched one by one past the end of the (possibly stale) list


class SyncError(FactoryError):
    """``issues sync`` refused to run, or could not."""


@dataclass(frozen=True)
class ExistingIssue:
    number: int
    story_id: str
    increment: str
    state: str  # open | closed


@dataclass(frozen=True)
class SyncPlan:
    increment: str
    source: str
    order: tuple[Story, ...]  # creation order: dependencies first
    existing: dict[str, ExistingIssue] = field(default_factory=dict)  # by story id

    @property
    def to_create(self) -> list[Story]:
        return [s for s in self.order if s.id not in self.existing]


@dataclass(frozen=True)
class SyncResult:
    plan: SyncPlan
    numbers: dict[str, int]  # story id -> issue number, for every issue known afterwards
    created: tuple[str, ...]  # story ids created by this run
    dry_run: bool


# ----------------------------------------------------------------------------- pure


def plan_sync(stories: list[Story], increment: str,
              found: dict[str, list[ExistingIssue]],
              source: str = STORIES_FILE) -> SyncPlan:
    """Pure: which issues to create, and in which order.

    ``found`` is ``list_story_issues()``. Raises ``SyncError`` if a story this run
    touches (one of ``stories`` or a dependency) has several issues, because it cannot
    tell which one is real, and ``StoriesError`` for contract problems.
    """
    _check_increment(increment)
    ids = {s.id for s in stories}
    touched = ids | {d for s in stories for d in s.blocked_by}
    duplicates = {k: v for k, v in found.items() if k in touched and len(v) > 1}
    if duplicates:
        listed = "; ".join(f"{k}: " + ", ".join(f"#{i.number}" for i in v)
                           for k, v in sorted(duplicates.items()))
        raise SyncError(f"several issues carry the same story marker ({listed}). Only one "
                        "issue may carry each story's marker: a human must remove it from "
                        "the extra issue(s). Nothing was changed.")
    existing = {k: v[0] for k, v in found.items() if len(v) == 1}
    problems: list[Problem] = []
    for story in stories:
        found = existing.get(story.id)
        if found is not None and found.increment != increment:
            problems.append(Problem(story.id, "id-reused", f"{story.id} already has issue "
                                    f"#{found.number} in increment {found.increment}; "
                                    "give this story a new ID", story.line))
        unknown = [d for d in story.blocked_by if d not in ids and d not in existing]
        if unknown:
            problems.append(Problem(story.id, "unknown-dependency", f"blocked by "
                                    f"{', '.join(unknown)}, which is neither in this file nor "
                                    "an existing story issue", story.line))
    if problems:
        raise StoriesError(source, problems)
    return SyncPlan(increment, source, tuple(_creation_order(stories)), dict(existing))


def _creation_order(stories: list[Story]) -> list[Story]:
    """Dependencies first; otherwise file order. The stories have no cycles (parse)."""
    by_id = {s.id: s for s in stories}
    done: set[str] = set()
    order: list[Story] = []

    def add(story: Story) -> None:
        if story.id in done:
            return
        done.add(story.id)
        for dep in story.blocked_by:
            if dep in by_id:
                add(by_id[dep])
        order.append(story)

    for story in stories:
        add(story)
    return order


def blocked_by_text(story: Story, numbers: dict[str, int]) -> str:
    """``#12, #14``, or ``None``. Every dependency must already have a number."""
    if not story.blocked_by:
        return "None"
    return ", ".join(f"#{numbers[d]}" for d in story.blocked_by)


def issue_body(story: Story, increment: str, numbers: dict[str, int]) -> str:
    """The issue body: ``templates/story.md`` filled in for ``story``."""
    body = templates.render(templates.load("story.md"), {
        "story_id": story.id,
        "increment": increment,
        "milestone": story.milestone,
        "story": story.story,
        "traces_to": ", ".join(story.traces_to),
        "acceptance_criteria": "\n".join(
            f"- [ ] AC{n}: {text}" for n, text in enumerate(story.acceptance_criteria, 1)),
        "out_of_scope": story.out_of_scope,
        "blocked_by": blocked_by_text(story, numbers),
        "technical_notes": story.technical_notes,
        "test_plan": story.test_plan,
    })
    if len(body) > MAX_BODY:
        raise SyncError(f"{story.id}: the issue body is {len(body)} characters; GitHub's "
                        f"limit is {MAX_BODY}")
    return body


def render(result: SyncResult) -> str:
    """The plan (dry run) or what was done, one line per story, in creation order."""
    plan, numbers = result.plan, result.numbers
    lines = [f"issues sync{' --dry-run' if result.dry_run else ''}: increment "
             f"{plan.increment}, {len(plan.order)} stories, from {plan.source}"]
    for story in plan.order:
        if story.id in plan.existing:
            found = plan.existing[story.id]
            action = f"exists   #{found.number}" + (" (closed)" if found.state == "closed"
                                                     else "")
        elif story.id in result.created:
            action = f"created  #{numbers[story.id]}"
        else:
            action = "create"
        deps = ", ".join(f"#{numbers[d]}" if d in numbers else f"{d} (new)"
                         for d in story.blocked_by) or "None"
        lines.append(f"  {action:<18}{story.issue_title}  [blocked by: {deps}]")
    creating, existing = len(plan.to_create), len(plan.order) - len(plan.to_create)
    if result.dry_run:
        lines.append(f"Plan: {creating} to create, {existing} already exist. "
                     "Dry run: nothing was changed.")
    else:
        lines.append(f"Done: {len(result.created)} created, {existing} already existed.")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- GitHub


def list_story_issues(gh: Gh, repo: str) -> dict[str, list[ExistingIssue]]:
    """Every issue (open or closed, any labels) carrying a ``factory:story`` marker, by
    story id. There is normally one issue per story; ``plan_sync`` refuses to act on a
    story that has several.

    GitHub's issue *list* can lag behind for a while after issues are created (seen in
    the sandbox integration test: a second run seconds after the first did not see the
    new issues and created duplicates). Issue numbers only grow, and fetching a single
    issue is consistent, so every issue newer than the list is found by fetching
    numbers above the highest one listed until GitHub answers 404.
    """
    items = list(gh.api(f"repos/{repo}/issues?state=all&per_page=100", paginate=True))
    number = max((item["number"] for item in items), default=0)
    for _ in range(MAX_PROBE):
        number += 1
        try:
            items.append(gh.api(f"repos/{repo}/issues/{number}"))
        except GhError as err:
            if "HTTP 404" in err.stderr:
                break
            if "HTTP 410" in err.stderr:  # deleted issue: its number stays taken
                continue
            raise
    else:
        raise SyncError(f"more than {MAX_PROBE} issues are missing from GitHub's issue list; "
                        "try again in a minute")

    found: dict[str, list[ExistingIssue]] = {}
    seen: set[int] = set()
    for item in items:
        if "pull_request" in item or item["number"] in seen:
            continue
        seen.add(item["number"])
        marker = find(item.get("body"), StoryMarker)
        if marker is not None:
            found.setdefault(marker.id, []).append(ExistingIssue(
                item["number"], marker.id, marker.increment, item.get("state", "open")))
    return found


def apply_plan(gh: Gh, repo: str, plan: SyncPlan) -> SyncResult:
    """Create the missing issues, dependencies first."""
    numbers = {k: v.number for k, v in plan.existing.items()}
    created: list[str] = []
    for story in plan.to_create:
        body = issue_body(story, plan.increment, numbers)
        issue = gh.api(f"repos/{repo}/issues", method="POST", json_body={
            "title": story.issue_title, "body": body, "labels": list(STORY_LABELS)})
        numbers[story.id] = issue["number"]
        created.append(story.id)
    return SyncResult(plan, numbers, tuple(created), dry_run=False)


def sync(gh: Gh, target: Path, repo: str, *, increment: str | None = None,
         dry_run: bool = False) -> SyncResult:
    """``issues sync [--dry-run]`` for the active target."""
    increment = increment or latest_local_increment(target)
    _check_increment(increment)
    relpath = (INCREMENTS_DIR / increment / STORIES_FILE).as_posix()
    if dry_run:
        path = Path(target) / relpath
        if not path.is_file():
            raise SyncError(f"{relpath} does not exist in {target}")
        text, source = path.read_text(encoding="utf-8"), f"{relpath} (local)"
    else:
        default = _default_branch(gh, repo)
        _require_gate_a(gh, repo, increment)
        text = _file_on_github(gh, repo, relpath, default)
        if text is None:
            raise SyncError(f"{relpath} is not on {default!r}, although the Planning PR "
                            "is merged")
        source = f"{relpath} on {default}"

    stories = parse(text, source)
    _require_labels(gh, repo)
    plan = plan_sync(stories, increment, list_story_issues(gh, repo), source)
    # Render every body before creating anything, so a bad story fails the whole run
    # up front instead of halfway through.
    placeholder_numbers = {**{k: v.number for k, v in plan.existing.items()},
                           **{s.id: 0 for s in plan.to_create}}
    for story in plan.to_create:
        issue_body(story, increment, placeholder_numbers)
    if dry_run:
        return SyncResult(plan, {k: v.number for k, v in plan.existing.items()}, (), True)
    return apply_plan(gh, repo, plan)


def latest_local_increment(target: Path) -> str:
    root = Path(target) / INCREMENTS_DIR
    names = [p.name for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    valid = [n for n in names if _is_increment(n)]
    if not valid:
        raise SyncError(f"no increment folder found under {INCREMENTS_DIR.as_posix()}; "
                        "pass --increment")
    return max(valid, key=lambda n: (int(n[:3]), n))


def _is_increment(name: str) -> bool:
    try:
        PlanningMarker(increment=name)
    except ValueError:
        return False
    return True


def _check_increment(increment: str) -> None:
    if not _is_increment(increment):
        raise SyncError(f"invalid increment {increment!r} (expected e.g. 001-initial)")


def _default_branch(gh: Gh, repo: str) -> str:
    info = gh.json(["repo", "view", repo], fields=["defaultBranchRef"])
    return (info.get("defaultBranchRef") or {}).get("name") or "main"


def _require_gate_a(gh: Gh, repo: str, increment: str) -> None:
    merged = [p for p in gh.json(["pr", "list", "--repo", repo, "--state", "merged",
                                  "--limit", "200"], fields=["number", "body"])
              if (m := find(p.get("body"), PlanningMarker)) and m.increment == increment]
    if not merged:
        raise SyncError(f"the Planning PR for increment {increment} is not merged. Issues are "
                        "created only after you merge it (Gate A). Use --dry-run to preview.")


def _require_labels(gh: Gh, repo: str) -> None:
    names = {label["name"].lower() for label in list_labels(gh, repo)}
    missing = [label for label in STORY_LABELS if label.lower() not in names]
    if missing:
        raise SyncError(f"labels missing on {repo}: {', '.join(missing)}. Run "
                        "`python scripts/factory.py labels ensure` first.")


def _file_on_github(gh: Gh, repo: str, path: str, ref: str) -> str | None:
    try:
        data = gh.api(f"repos/{repo}/contents/{path}?ref={ref}")
    except GhError as err:
        if "HTTP 404" in err.stderr:
            return None
        raise
    if not isinstance(data, dict) or data.get("type") != "file":
        return None
    return base64.b64decode(data.get("content", "")).decode("utf-8")
