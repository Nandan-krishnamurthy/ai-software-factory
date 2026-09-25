"""``factory.py pick`` and ``factory.py label`` (T3.1).

* **pick** starts exactly one story. Only ``/factory-continue`` may do that (D2, rule
  S2), so ``pick`` refuses unless it is passed ``--authorized-by-continue``, and only
  that command's station (S06) passes it. It also refuses while another story is still
  in flight (``status:in-progress``, ``status:in-review`` or
  ``status:changes-requested``): one story at a time.
* **The unblocked rule** (requirements §4): a story can be picked if its issue is open,
  labelled ``status:ready`` (and not ``factory:needs-human``), and every issue on its
  ``Blocked by:`` line is **closed**. A blocker the factory cannot see counts as open,
  so in doubt nothing is picked. Among the unblocked stories the factory takes the
  lowest milestone, then the lowest issue number. Milestones are numbered per increment
  (M1 of one increment is not M1 of the next), so the oldest increment comes first.
  Issue numbers are unique, so the order is total and ties always break the same way.
* **Picking** assigns the issue to the account the factory runs as, then moves its
  status label to ``status:in-progress``. The label is the lock, so it is set last: if
  a run stops after the assignment, running ``pick`` again picks the same story.
* **label** makes sure an issue has exactly one ``status:*`` label. It adds the new one
  before removing the others, so the issue is never left without a status, and it
  changes nothing when the label is already right.

``choose()`` is pure; ``pick()`` and ``set_status()`` do the GitHub I/O.
"""

import re
from dataclasses import dataclass
from urllib.parse import quote

from factory.errors import FactoryError
from factory.gh import Gh
from factory.issues import blocked_by_numbers, fetch_all_issues
from factory.labels import REQUIRED_LABELS
from factory.markers import StoryMarker, find

STATUS_PREFIX = "status:"
STATUSES = tuple(spec.name[len(STATUS_PREFIX):] for spec in REQUIRED_LABELS
                 if spec.name.startswith(STATUS_PREFIX))
IN_FLIGHT = frozenset({"status:in-progress", "status:in-review", "status:changes-requested"})
NEEDS_HUMAN = "factory:needs-human"
_MILESTONE = re.compile(r"·\s*Milestone\s+M(?P<n>\d+)\b")


class PickError(FactoryError):
    """``pick`` refused, or found nothing it may start."""


class LabelError(FactoryError):
    """``label`` refused."""


@dataclass(frozen=True)
class StoryIssue:
    number: int
    story_id: str
    increment: str
    title: str
    open: bool
    labels: frozenset[str]
    milestone: int | None  # the N of "Milestone MN" in the issue body, if present
    blocked_by: tuple[int, ...]

    @property
    def milestone_name(self) -> str:
        return f"M{self.milestone}" if self.milestone is not None else "no milestone"

    def sort_key(self) -> tuple:
        # No milestone sorts after every numbered one; the issue number decides the rest.
        missing = self.milestone is None
        return (self.increment, missing, self.milestone or 0, self.number)


@dataclass(frozen=True)
class Choice:
    picked: StoryIssue
    unblocked: tuple[StoryIssue, ...]  # every unblocked story, in picking order
    blocked: dict[int, tuple[int, ...]]  # ready story -> its blockers that are still open


# ----------------------------------------------------------------------------- pure


def parse_issues(items: list[dict]) -> tuple[list[StoryIssue], dict[int, bool]]:
    """Story issues (those with a ``factory:story`` marker) and, for every issue seen,
    whether it is open."""
    stories: list[StoryIssue] = []
    is_open: dict[int, bool] = {}
    for item in items:
        opened = (item.get("state") or "open").lower() == "open"
        is_open[item["number"]] = opened
        body = item.get("body") or ""
        marker = find(body, StoryMarker)
        if marker is None:
            continue
        milestone = _MILESTONE.search(body)
        stories.append(StoryIssue(
            number=item["number"], story_id=marker.id, increment=marker.increment,
            title=item.get("title") or "", open=opened,
            labels=frozenset(label["name"] for label in item.get("labels") or []),
            milestone=int(milestone["n"]) if milestone else None,
            blocked_by=blocked_by_numbers(body)))
    return stories, is_open


def choose(stories: list[StoryIssue], is_open: dict[int, bool]) -> Choice:
    """Apply the unblocked rule. Raises ``PickError`` when nothing may be picked."""
    in_flight = sorted((s for s in stories if s.open and s.labels & IN_FLIGHT),
                       key=lambda s: s.number)
    if in_flight:
        busy = ", ".join(f"#{s.number} ({s.story_id}, {sorted(s.labels & IN_FLIGHT)[0]})"
                         for s in in_flight)
        raise PickError(f"a story is already in flight: {busy}. The factory works on one "
                        "story at a time; finish it first")

    by_story: dict[str, list[int]] = {}
    for s in stories:
        by_story.setdefault(s.story_id, []).append(s.number)
    duplicates = {k: v for k, v in by_story.items() if len(v) > 1}

    ready = [s for s in stories if s.open and "status:ready" in s.labels
             and NEEDS_HUMAN not in s.labels and s.story_id not in duplicates]
    blocked: dict[int, tuple[int, ...]] = {}
    unblocked: list[StoryIssue] = []
    for s in ready:
        still_open = tuple(n for n in s.blocked_by if is_open.get(n, True))
        if still_open:
            blocked[s.number] = still_open
        else:
            unblocked.append(s)
    unblocked.sort(key=StoryIssue.sort_key)

    if not unblocked:
        reasons = [f"#{n} waits for " + ", ".join(f"#{b}" for b in bs)
                   for n, bs in sorted(blocked.items())]
        if duplicates:
            reasons += [f"{k} has several issues ({', '.join(f'#{n}' for n in v)})"
                        for k, v in sorted(duplicates.items())]
        detail = "; ".join(reasons) if reasons else "no open story is labelled status:ready"
        raise PickError(f"no story can be picked: {detail}")
    return Choice(unblocked[0], tuple(unblocked), blocked)


def label_changes(current: frozenset[str], status: str) -> tuple[list[str], list[str]]:
    """Pure: the labels to add and to remove so ``status:<status>`` is the only one."""
    wanted = STATUS_PREFIX + status
    add = [] if wanted in current else [wanted]
    remove = sorted(label for label in current
                    if label.startswith(STATUS_PREFIX) and label != wanted)
    return add, remove


# ----------------------------------------------------------------------------- GitHub


def set_status(gh: Gh, repo: str, number: int, status: str) -> tuple[list[str], list[str]]:
    """Make ``status:<status>`` the only status label on story issue ``number``."""
    if status not in STATUSES:
        raise LabelError(f"unknown status {status!r}; use one of: {', '.join(STATUSES)}")
    issue = gh.api(f"repos/{repo}/issues/{number}")
    if "pull_request" in issue:
        raise LabelError(f"#{number} is a pull request; status labels go on the story issue")
    if find(issue.get("body"), StoryMarker) is None:
        raise LabelError(f"#{number} is not a factory story issue (no factory:story marker)")
    current = frozenset(label["name"] for label in issue.get("labels") or [])
    add, remove = label_changes(current, status)
    if add:
        gh.api(f"repos/{repo}/issues/{number}/labels", method="POST",
               json_body={"labels": add})
    for name in remove:
        gh.api(f"repos/{repo}/issues/{number}/labels/{quote(name, safe='')}",
               method="DELETE")
    return add, remove


def pick(gh: Gh, repo: str, *, authorized_by_continue: bool) -> tuple[Choice, str]:
    """Choose the next story, assign it, and mark it ``status:in-progress``."""
    if not authorized_by_continue:
        raise PickError("refused: only /factory-continue may start a story (D2, rule S2). "
                        "It passes --authorized-by-continue; nothing else may")
    stories, is_open = parse_issues(fetch_all_issues(gh, repo))
    choice = choose(stories, is_open)
    login = gh.api("user")["login"]
    story = choice.picked
    gh.api(f"repos/{repo}/issues/{story.number}/assignees", method="POST",
           json_body={"assignees": [login]})
    set_status(gh, repo, story.number, "in-progress")
    return choice, login


def render_pick(choice: Choice, login: str) -> str:
    s = choice.picked
    lines = [f"Picked #{s.number} {s.story_id}: {s.title}",
             f"  increment {s.increment}, {s.milestone_name}; assigned to {login}; "
             "label status:in-progress"]
    others = choice.unblocked[1:]
    if others:
        lines.append("Also unblocked, for later: "
                     + ", ".join(f"#{o.number} ({o.milestone_name})" for o in others))
    return "\n".join(lines)


def pick_to_dict(choice: Choice, login: str) -> dict:
    s = choice.picked
    return {"picked": {"number": s.number, "story_id": s.story_id, "title": s.title,
                       "increment": s.increment, "milestone": s.milestone_name,
                       "assignee": login, "status": "status:in-progress"},
            "also_unblocked": [o.number for o in choice.unblocked[1:]],
            "blocked": {str(n): list(bs) for n, bs in sorted(choice.blocked.items())}}
