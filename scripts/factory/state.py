"""The state engine: exactly one factory state from GitHub (architecture §6).

``collect_snapshot()`` reads GitHub (the source of truth; nothing is kept in memory or
in the local clone) into a ``Snapshot``. ``derive_state()`` is a **pure** function from
that snapshot to one ``StateResult``. ``factory.py state --json`` prints the result.

Output schema (``schema`` 1)::

    {
      "schema": 1,
      "state": "<one of STATES>",
      "increment": "001-initial" | null,
      "next_station": "S00" … "S12", "S05b" | null,
      "allowed_commands": ["/factory-…", …],   # commands that may act in this state
      "waiting_on": "factory" | "human" | "nobody",
      "details": {"message": "<one line for humans>", …state-specific keys…}
    }

States derived here: UNCONFIGURED, PLANNING, GATE_A_WAITING, GATE_A_CHANGES,
ISSUES_PENDING, IDLE_AT_GATE_C, NEEDS_HUMAN, INCONSISTENT (T1.8), and STORY_IN_PROGRESS,
GATE_B_WAITING_REVIEW, INCREMENT_COMPLETE (T3.2). The rest of the story phase
(GATE_B_CHANGES_REQUESTED, GATE_B_APPROVED_UNMERGED, CLOSEOUT_PENDING, a rejected story
PR) arrives in T4.1; until then such snapshots yield **UNSUPPORTED**, which allows only
``/factory-status``, so the factory never guesses.

Conventions this module relies on (later stations must follow them):

* A planning branch is named ``factory/plan-<increment>``, e.g. ``factory/plan-001-initial``.
* A story is in flight while its open issue has ``status:in-progress``,
  ``status:in-review`` or ``status:changes-requested`` (at most one, invariant 1). While
  it is in progress, the ``next`` of its checkpoint comment is the station to run; with
  no checkpoint yet, S06 has just picked it and S07 is next. A checkpoint that says
  ``GATE_B`` while the label still says in progress means S11 stopped between opening
  the PR and moving the label, so S11 runs again (it must be idempotent).
* A story is done when its issue is closed **and** labelled ``status:done`` (S12).
* Every commit the factory makes carries the trailer ``Factory-Station: <Sxx>``. A commit
  on the default branch with that trailer arrived through a merged PR if GitHub's merge
  account (``web-flow``) committed it (a squash or rebase merge), or if a ``web-flow``
  merge commit brought it in from the PR's branch (a normal merge). Any other such commit
  was pushed directly, and breaks invariant 4.
"""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any

from factory import comments as comments_mod
from factory.config import Config, ConfigError, parse_config
from factory.errors import GhError
from factory.gh import Gh
from factory.markers import PlanningMarker, PrMarker, StoryMarker, find
from factory.signals import Verdict, fetch_pr, signals_for

SCHEMA_VERSION = 1
PLAN_BRANCH_PREFIX = "factory/plan-"
FACTORY_COMMIT_TRAILER = "Factory-Station"
MERGE_COMMITTER = "web-flow"

UNCONFIGURED = "UNCONFIGURED"
PLANNING = "PLANNING"
GATE_A_WAITING = "GATE_A_WAITING"
GATE_A_CHANGES = "GATE_A_CHANGES"
ISSUES_PENDING = "ISSUES_PENDING"
IDLE_AT_GATE_C = "IDLE_AT_GATE_C"
STORY_IN_PROGRESS = "STORY_IN_PROGRESS"
GATE_B_WAITING_REVIEW = "GATE_B_WAITING_REVIEW"
INCREMENT_COMPLETE = "INCREMENT_COMPLETE"
NEEDS_HUMAN = "NEEDS_HUMAN"
INCONSISTENT = "INCONSISTENT"
UNSUPPORTED = "UNSUPPORTED"
STATES = (UNCONFIGURED, PLANNING, GATE_A_WAITING, GATE_A_CHANGES, ISSUES_PENDING,
          IDLE_AT_GATE_C, STORY_IN_PROGRESS, GATE_B_WAITING_REVIEW, INCREMENT_COMPLETE,
          NEEDS_HUMAN, INCONSISTENT, UNSUPPORTED)

RESUME, CONTINUE, START, STATUS = ("/factory-resume", "/factory-continue",
                                   "/factory-start", "/factory-status")
_ALLOWED = {
    UNCONFIGURED: [START, STATUS],
    PLANNING: [RESUME, CONTINUE, STATUS],
    GATE_A_WAITING: [STATUS],
    GATE_A_CHANGES: [RESUME, CONTINUE, STATUS],
    ISSUES_PENDING: [RESUME, CONTINUE, STATUS],
    IDLE_AT_GATE_C: [CONTINUE, STATUS],
    STORY_IN_PROGRESS: [RESUME, CONTINUE, STATUS],
    GATE_B_WAITING_REVIEW: [STATUS],
    INCREMENT_COMPLETE: [START, STATUS],
    NEEDS_HUMAN: [STATUS],
    INCONSISTENT: [STATUS],
    UNSUPPORTED: [STATUS],
}
_WAITING = {
    UNCONFIGURED: "human", PLANNING: "factory", GATE_A_WAITING: "human",
    GATE_A_CHANGES: "factory", ISSUES_PENDING: "factory", IDLE_AT_GATE_C: "human",
    STORY_IN_PROGRESS: "factory", GATE_B_WAITING_REVIEW: "human",
    INCREMENT_COMPLETE: "human", NEEDS_HUMAN: "human", INCONSISTENT: "human",
    UNSUPPORTED: "nobody",
}

# Planning documents in station order (architecture §5.1).
PLAN_DOCS = (
    ("S00", "00-prd.md"),
    ("S01", "01-codebase-analysis.md"),  # existing projects only
    ("S02", "02-requirements.md"),
    ("S03", "03-architecture.md"),
    ("S04", "04-implementation-plan.md"),
    ("S05", "05-stories.md"),
)
IN_PROGRESS, IN_REVIEW, CHANGES_REQUESTED, DONE = (
    "status:in-progress", "status:in-review", "status:changes-requested", "status:done")
_ACTIVE = {IN_PROGRESS, IN_REVIEW, CHANGES_REQUESTED}  # the same lock as ``pick``
_FIRST_STORY_STATION = "S07"  # S06 (pick) sets in-progress before any checkpoint exists
_STORY_STATION = re.compile(r"S(0[6-9]|1[0-2])")  # S06-S12: the story loop and close-out
_INCREMENT = re.compile(r"^\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
_STORY_HEADING = re.compile(r"^###\s+(STORY-\d{3,})\b", re.MULTILINE)


# ----------------------------------------------------------------------------- snapshot


@dataclass(frozen=True)
class IssueInfo:
    number: int
    state: str  # OPEN | CLOSED
    labels: frozenset[str]
    story: StoryMarker | None
    checkpoint_branch: str | None = None
    checkpoint_next: str | None = None  # e.g. "S09" or "GATE_B"; read for active stories

    @property
    def status_labels(self) -> set[str]:
        return {label for label in self.labels if label.startswith("status:")}


@dataclass(frozen=True)
class PrInfo:
    number: int
    state: str  # OPEN | CLOSED | MERGED
    head_ref: str
    labels: frozenset[str]
    planning_increment: str | None = None
    story_id: str | None = None


@dataclass(frozen=True)
class Snapshot:
    repo: str
    default_branch: str
    is_empty: bool = False
    branches: frozenset[str] = frozenset()
    config_error: str | None = None
    config_found: bool = False  # on the default branch or the current plan branch
    existing_project: bool = False
    plan_files: dict[str, frozenset[str]] = field(default_factory=dict)  # inc -> names
    plan_config: dict[str, bool] = field(default_factory=dict)  # inc -> config on branch
    prs: tuple[PrInfo, ...] = ()
    planning_verdicts: dict[int, str] = field(default_factory=dict)  # open PR no. -> Verdict
    story_verdicts: dict[int, str] = field(default_factory=dict)  # open story PR -> Verdict
    issues: tuple[IssueInfo, ...] = ()
    needs_human: tuple[str, ...] = ()  # e.g. ("issue #4", "PR #7")
    stories_on_default: dict[str, frozenset[str]] = field(default_factory=dict)
    direct_factory_commits: tuple[str, ...] = ()  # shas


@dataclass(frozen=True)
class StateResult:
    state: str
    increment: str | None = None
    next_station: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "state": self.state,
            "increment": self.increment,
            "next_station": self.next_station,
            "allowed_commands": list(_ALLOWED[self.state]),
            "waiting_on": _WAITING[self.state],
            "details": dict(self.details),
        }


# ----------------------------------------------------------------------------- derive


def derive_state(snap: Snapshot) -> StateResult:
    """Pure: exactly one state for any snapshot."""
    problems = check_invariants(snap)
    if problems:
        return StateResult(INCONSISTENT, details={
            "message": "The factory's GitHub state breaks its invariants; nothing will be "
                       "changed until a human fixes it.",
            "problems": problems})

    if snap.needs_human:
        return StateResult(NEEDS_HUMAN, details={
            "message": "Waiting for a human decision on " + ", ".join(snap.needs_human)
                       + ". Answer, remove the factory:needs-human label, then resume.",
            "items": list(snap.needs_human)})

    increment = current_increment(snap)
    if increment is None:
        return StateResult(UNCONFIGURED, details={
            "message": "No increment has been started. Run /factory-start."})

    planning_prs = sorted((p for p in snap.prs if p.planning_increment == increment),
                          key=lambda p: p.number)
    pr = planning_prs[-1] if planning_prs else None

    if pr is None or pr.state == "CLOSED":
        if pr is not None and f"{PLAN_BRANCH_PREFIX}{increment}" not in snap.branches:
            return StateResult(NEEDS_HUMAN, increment, details={
                "message": f"Planning PR #{pr.number} was closed without merging. Re-plan "
                           "with /factory-start, or delete the increment.",
                "items": [f"PR #{pr.number}"]})
        station = _next_planning_station(snap, increment)
        return StateResult(PLANNING, increment, station, details={
            "message": f"Planning increment {increment}: next is {station}.",
            "missing": _missing_docs(snap, increment)})

    if pr.state == "OPEN":
        verdict = snap.planning_verdicts.get(pr.number, Verdict.PENDING.value)
        if verdict == Verdict.CHANGES_REQUESTED.value:
            return StateResult(GATE_A_CHANGES, increment, "S05", details={
                "message": f"Changes requested on Planning PR #{pr.number}; revise the "
                           "planning docs and reply to each item.",
                "pr": pr.number})
        return StateResult(GATE_A_WAITING, increment, details={
            "message": f"Waiting for you to review Planning PR #{pr.number}: merge it to "
                       "approve, or comment /changes.",
            "pr": pr.number})

    # The Planning PR is merged: story phase.
    stories = snap.stories_on_default.get(increment, frozenset())
    if not stories:
        return StateResult(NEEDS_HUMAN, increment, details={
            "message": f"Planning PR #{pr.number} is merged but no stories were found in "
                       f"docs/factory/increments/{increment}/05-stories.md.",
            "items": [f"PR #{pr.number}"]})
    story_issues = [i for i in snap.issues
                    if i.story is not None and i.story.increment == increment]
    missing = sorted(stories - {i.story.id for i in story_issues})
    if missing:
        return StateResult(ISSUES_PENDING, increment, "S05b", details={
            "message": f"{len(missing)} story issue(s) to create.", "missing": missing})

    open_issues = [i for i in story_issues if i.state == "OPEN"]
    active = [i for i in open_issues if i.labels & _ACTIVE]  # at most one (invariant 1)
    if active:
        return _story_state(snap, increment, active[0])
    unclosed = sorted(i.number for i in story_issues
                      if i.state != "OPEN" and DONE not in i.labels)
    if unclosed:
        return StateResult(UNSUPPORTED, increment, details={
            "message": "Story issue(s) " + ", ".join(f"#{n}" for n in unclosed)
                       + " are closed but not status:done: close-out (CLOSEOUT_PENDING) "
                       "arrives in T4.1. Only /factory-status is available.",
            "issues": unclosed})
    if not open_issues:
        return StateResult(INCREMENT_COMPLETE, increment, details={
            "message": f"Increment {increment} is complete: all {len(story_issues)} "
                       "stories are done. Run /factory-start with new requirements.",
            "done": sorted(i.number for i in story_issues)})
    ready = sorted(i.number for i in open_issues if "status:ready" in i.labels)
    if not ready:
        return StateResult(NEEDS_HUMAN, increment, details={
            "message": "No story is ready: every open story is blocked.",
            "items": [f"issue #{i.number}" for i in open_issues]})
    return StateResult(IDLE_AT_GATE_C, increment, "S06", details={
        "message": f"{len(ready)} story(ies) ready. Say continue (/factory-continue) to "
                   "start the next one.",
        "ready": ready})


def _story_state(snap: Snapshot, increment: str, issue: IssueInfo) -> StateResult:
    """The state while ``issue`` (the one story in flight) is in progress or in review."""
    story_id = issue.story.id if issue.story else None
    base = {"issue": issue.number, "story": story_id}

    if IN_PROGRESS in issue.labels:
        nxt = issue.checkpoint_next
        if nxt is None:
            station = _FIRST_STORY_STATION
        elif nxt == "GATE_B":
            station = "S11"  # the PR is open, but S11 had not moved the label yet
        else:
            station = nxt  # a story station; check_invariants rejected anything else
        return StateResult(STORY_IN_PROGRESS, increment, station, details={
            **base, "branch": issue.checkpoint_branch,
            "message": f"Story #{issue.number} ({story_id}) is in progress: next is "
                       f"{station}."})

    if IN_REVIEW in issue.labels:
        prs = sorted((p for p in snap.prs if p.story_id == story_id and p.state == "OPEN"),
                     key=lambda p: p.number)
        if prs:
            pr = prs[0]  # one open PR per story (invariant 2)
            verdict = snap.story_verdicts.get(pr.number, Verdict.PENDING.value)
            if verdict == Verdict.PENDING.value:
                return StateResult(GATE_B_WAITING_REVIEW, increment, details={
                    **base, "pr": pr.number,
                    "message": f"Waiting for you to review PR #{pr.number} ({story_id}): "
                               "merge it to approve, or comment /changes."})
            return StateResult(UNSUPPORTED, increment, details={
                **base, "pr": pr.number, "verdict": verdict,
                "message": f"PR #{pr.number} ({story_id}) is {verdict}; that Gate B state "
                           "arrives in T4.1. Only /factory-status is available."})
        return StateResult(UNSUPPORTED, increment, details={
            **base, "message": f"Story #{issue.number} ({story_id}) is in review but has no "
                               "open PR (merged or closed): close-out arrives in T4.1. Only "
                               "/factory-status is available."})

    return StateResult(UNSUPPORTED, increment, details={
        **base, "message": f"Changes were requested on story #{issue.number} ({story_id}); "
                           "GATE_B_CHANGES_REQUESTED arrives in T4.1. Only /factory-status "
                           "is available."})


def check_invariants(snap: Snapshot) -> list[str]:
    """Architecture §6 invariants, plus basic data-integrity checks. [] if all hold."""
    problems: list[str] = []
    if snap.config_error:
        problems.append(f"config is invalid: {snap.config_error}")

    open_story_issues = [i for i in snap.issues if i.story is not None and i.state == "OPEN"]
    # 1. At most one story is in progress or in review (changes requested counts too).
    active = [i for i in open_story_issues if i.labels & _ACTIVE]
    if len(active) > 1:
        problems.append("more than one story is in progress or in review: "
                        + ", ".join(f"#{i.number}" for i in active))
    for issue in open_story_issues:
        if len(issue.status_labels) > 1:
            problems.append(f"issue #{issue.number} has several status labels: "
                            + ", ".join(sorted(issue.status_labels)))

    # Story ids must be unique across issues.
    by_story: dict[str, list[int]] = {}
    for issue in snap.issues:
        if issue.story is not None:
            by_story.setdefault(issue.story.id, []).append(issue.number)
    for story, numbers in sorted(by_story.items()):
        if len(numbers) > 1:
            problems.append(f"{story} has several issues: "
                            + ", ".join(f"#{n}" for n in numbers))

    # 2. Every story PR maps to exactly one issue (and one open PR per story).
    open_prs_by_story: dict[str, list[int]] = {}
    for pr in snap.prs:
        if pr.story_id is None:
            continue
        count = len(by_story.get(pr.story_id, []))
        if count != 1:
            problems.append(f"PR #{pr.number} is for {pr.story_id}, which has {count} issues "
                            "(expected exactly 1)")
        if pr.state == "OPEN":
            open_prs_by_story.setdefault(pr.story_id, []).append(pr.number)
    for story, numbers in sorted(open_prs_by_story.items()):
        if len(numbers) > 1:
            problems.append(f"{story} has several open PRs: "
                            + ", ".join(f"#{n}" for n in numbers))
    open_planning = [p.number for p in snap.prs
                     if p.planning_increment is not None and p.state == "OPEN"]
    if len(open_planning) > 1:
        problems.append("several Planning PRs are open: "
                        + ", ".join(f"#{n}" for n in open_planning))

    # 3. The branch named in a checkpoint exists on the remote.
    for issue in active:
        branch = issue.checkpoint_branch
        if branch and branch not in snap.branches:
            problems.append(f"issue #{issue.number}'s checkpoint names branch {branch!r}, "
                            "which does not exist on the remote")
        nxt = issue.checkpoint_next
        if (IN_PROGRESS in issue.labels and nxt is not None
                and not (nxt == "GATE_B" or _STORY_STATION.fullmatch(nxt))):
            problems.append(f"issue #{issue.number} is in progress, but its checkpoint "
                            f"points to {nxt}, which is not a story station")

    # 4. No unexpected factory commits on the default branch.
    for sha in snap.direct_factory_commits:
        problems.append(f"commit {sha[:7]} on {snap.default_branch!r} was made by the factory "
                        "but did not arrive through a merged PR")
    return problems


def current_increment(snap: Snapshot) -> str | None:
    increments = {b[len(PLAN_BRANCH_PREFIX):] for b in snap.branches
                  if b.startswith(PLAN_BRANCH_PREFIX)}
    increments |= {p.planning_increment for p in snap.prs if p.planning_increment}
    increments = {i for i in increments if _INCREMENT.match(i)}
    return max(increments, key=lambda i: (int(i[:3]), i)) if increments else None


def _required_docs(snap: Snapshot) -> list[tuple[str, str]]:
    return [(s, f) for s, f in PLAN_DOCS if s != "S01" or snap.existing_project]


def _missing_docs(snap: Snapshot, increment: str) -> list[str]:
    files = snap.plan_files.get(increment, frozenset())
    missing = [f for _, f in _required_docs(snap) if f not in files]
    if not snap.plan_config.get(increment, False):
        missing.insert(0, ".factory/config.json")
    return missing


def _next_planning_station(snap: Snapshot, increment: str) -> str:
    files = snap.plan_files.get(increment, frozenset())
    if not snap.plan_config.get(increment, False):
        return "S00"
    for station, name in _required_docs(snap):
        if name not in files:
            return station
    return "S05"  # every doc exists but no open Planning PR: S05 opens it


# ----------------------------------------------------------------------------- output


def validate_output(data: Any) -> list[str]:
    """Check a ``state --json`` object against the documented schema. [] if valid."""
    errors: list[str] = []
    expected = {"schema", "state", "increment", "next_station", "allowed_commands",
                "waiting_on", "details"}
    if not isinstance(data, dict):
        return ["output must be a JSON object"]
    if set(data) != expected:
        errors.append(f"keys must be exactly {sorted(expected)}, got {sorted(data)}")
    if data.get("schema") != SCHEMA_VERSION:
        errors.append("schema must be 1")
    if data.get("state") not in STATES:
        errors.append(f"unknown state {data.get('state')!r}")
    inc = data.get("increment")
    if inc is not None and not (isinstance(inc, str) and _INCREMENT.match(inc)):
        errors.append(f"bad increment {inc!r}")
    station = data.get("next_station")
    if station is not None and not (isinstance(station, str)
                                    and re.fullmatch(r"S\d{2}b?", station)):
        errors.append(f"bad next_station {station!r}")
    commands = data.get("allowed_commands")
    if not (isinstance(commands, list) and commands
            and all(isinstance(c, str) and c.startswith("/factory-") for c in commands)):
        errors.append("allowed_commands must be a non-empty list of /factory-* commands")
    if data.get("waiting_on") not in ("factory", "human", "nobody"):
        errors.append("waiting_on must be factory, human or nobody")
    details = data.get("details")
    if not (isinstance(details, dict) and isinstance(details.get("message"), str)
            and details["message"]):
        errors.append("details must be an object with a non-empty message")
    return errors


def render(result: StateResult) -> str:
    data = result.to_dict()
    lines = [f"State: {data['state']}"
             + (f" (increment {data['increment']})" if data["increment"] else "")]
    if data["next_station"]:
        lines.append(f"Next station: {data['next_station']}")
    lines.append(f"Waiting on: {data['waiting_on']}")
    lines.append("Allowed: " + ", ".join(data["allowed_commands"]))
    lines.append(data["details"]["message"])
    for problem in data["details"].get("problems", []):
        lines.append(f"  - {problem}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- collect


def _absent(err: GhError) -> bool:
    return any(code in err.stderr for code in ("HTTP 404", "HTTP 409"))


def _get(gh: Gh, endpoint: str) -> Any | None:
    """GET a REST endpoint; None if it does not exist (404) or the repo is empty (409)."""
    try:
        return gh.api(endpoint)
    except GhError as err:
        if _absent(err):
            return None
        raise


def _file_text(gh: Gh, repo: str, path: str, ref: str) -> str | None:
    data = _get(gh, f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, dict) or data.get("type") != "file":
        return None
    return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")


def _dir_names(gh: Gh, repo: str, path: str, ref: str) -> frozenset[str]:
    data = _get(gh, f"repos/{repo}/contents/{path}?ref={ref}")
    return frozenset(e["name"] for e in data) if isinstance(data, list) else frozenset()


def _parse_config_text(text: str | None) -> tuple[Config | None, str | None]:
    if text is None:
        return None, None
    try:
        return parse_config(json.loads(text)), None
    except (ValueError, ConfigError) as err:
        problems = getattr(err, "problems", None)
        return None, "; ".join(problems) if problems else str(err)


_BASE_FILES = {"readme.md", "readme", "license", "license.md", ".gitignore", ".gitattributes"}
_TRAILER = re.compile(rf"^{FACTORY_COMMIT_TRAILER}:", re.MULTILINE | re.IGNORECASE)


def direct_factory_commits(commits: list[dict]) -> tuple[str, ...]:
    """Pure: the factory commits in a ``repos/<r>/commits`` listing that no PR merged.

    A factory commit (one with the trailer) is fine if ``web-flow`` committed it (a
    squash or rebase merge), or if it is on the branch side of a ``web-flow`` merge
    commit: reachable from a non-first parent but not from the first one (a normal
    merge). A merge the human made locally is committed by them, not ``web-flow``, so it
    does not excuse the commits it brings in.
    """
    by_sha = {c["sha"]: c for c in commits}

    def parents(sha: str) -> list[str]:
        return [p["sha"] for p in by_sha.get(sha, {}).get("parents") or []]

    def reachable(starts: list[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(starts)
        while stack:
            sha = stack.pop()
            if sha in seen or sha not in by_sha:
                continue
            seen.add(sha)
            stack.extend(parents(sha))
        return seen

    def committer(c: dict) -> str | None:
        return (c.get("committer") or {}).get("login")

    merged: set[str] = set()
    for c in commits:
        ps = parents(c["sha"])
        if len(ps) > 1 and committer(c) == MERGE_COMMITTER:
            merged |= reachable(ps[1:]) - reachable(ps[:1])
    return tuple(c["sha"] for c in commits
                 if _TRAILER.search((c.get("commit") or {}).get("message", ""))
                 and committer(c) != MERGE_COMMITTER and c["sha"] not in merged)


def collect_snapshot(gh: Gh, repo: str) -> Snapshot:
    """Read everything ``derive_state`` needs from GitHub."""
    info = gh.json(["repo", "view", repo], fields=["defaultBranchRef", "isEmpty"])
    default = (info.get("defaultBranchRef") or {}).get("name") or "main"
    if info.get("isEmpty"):
        return Snapshot(repo=repo, default_branch=default, is_empty=True)

    branches = frozenset(b["name"] for b in gh.api(f"repos/{repo}/branches", paginate=True))
    prs = []
    for p in gh.json(["pr", "list", "--repo", repo, "--state", "all", "--limit", "200"],
                     fields=["number", "state", "headRefName", "body", "labels"]):
        planning = find(p.get("body"), PlanningMarker)
        story_pr = find(p.get("body"), PrMarker)
        prs.append(PrInfo(
            number=p["number"], state=p["state"], head_ref=p["headRefName"],
            labels=frozenset(label["name"] for label in p.get("labels") or []),
            planning_increment=planning.increment if planning else None,
            story_id=story_pr.story if story_pr else None))

    issues = []
    for i in gh.json(["issue", "list", "--repo", repo, "--state", "all", "--limit", "500",
                      "--label", "factory:story"], fields=["number", "state", "labels", "body"]):
        labels = frozenset(label["name"] for label in i.get("labels") or [])
        checkpoint = None
        if i["state"] == "OPEN" and labels & _ACTIVE:
            found = comments_mod.find_checkpoint(comments_mod.list_comments(gh, repo, i["number"]))
            checkpoint = found[1] if found else None
        issues.append(IssueInfo(i["number"], i["state"], labels, find(i.get("body"), StoryMarker),
                                checkpoint.branch if checkpoint else None,
                                checkpoint.next if checkpoint else None))

    needs_human = [f"issue #{i['number']}" for i in gh.json(
        ["issue", "list", "--repo", repo, "--state", "open", "--label", "factory:needs-human",
         "--limit", "100"], fields=["number"])]
    needs_human += [f"PR #{p.number}" for p in prs
                    if p.state == "OPEN" and "factory:needs-human" in p.labels]

    tree = _get(gh, f"repos/{repo}/git/trees/{default}?recursive=1") or {}
    paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
    existing = any(not (p.startswith(("docs/factory/", ".factory/")) or p.lower() in _BASE_FILES)
                   for p in paths)

    config_text = _file_text(gh, repo, ".factory/config.json", default)
    snapshot = Snapshot(repo=repo, default_branch=default, branches=branches, prs=tuple(prs),
                        issues=tuple(issues), needs_human=tuple(needs_human),
                        existing_project=existing)
    increment = current_increment(snapshot)

    plan_files: dict[str, frozenset[str]] = {}
    plan_config: dict[str, bool] = {}
    stories: dict[str, frozenset[str]] = {}
    verdicts: dict[int, str] = {}
    if increment is not None:
        branch = f"{PLAN_BRANCH_PREFIX}{increment}"
        merged = any(p.planning_increment == increment and p.state == "MERGED" for p in prs)
        if branch in branches and not merged:
            branch_config = _file_text(gh, repo, ".factory/config.json", branch)
            plan_config[increment] = branch_config is not None
            config_text = config_text or branch_config
            plan_files[increment] = _dir_names(
                gh, repo, f"docs/factory/increments/{increment}", branch)
        if merged:
            text = _file_text(gh, repo, f"docs/factory/increments/{increment}/05-stories.md",
                              default) or ""
            stories[increment] = frozenset(_STORY_HEADING.findall(text))

    config, config_error = _parse_config_text(config_text)
    open_planning = [p for p in prs if p.planning_increment == increment and p.state == "OPEN"]
    in_review = {i.story.id for i in issues
                 if i.story and i.state == "OPEN" and IN_REVIEW in i.labels}
    open_story = [p for p in prs if p.story_id in in_review and p.state == "OPEN"]
    story_verdicts: dict[int, str] = {}
    if (open_planning or open_story) and config is not None:
        signals = signals_for(config)
        for p in open_planning:
            verdicts[p.number] = signals.verdict(fetch_pr(gh, repo, p.number)).value
        for p in open_story:
            story_verdicts[p.number] = signals.verdict(fetch_pr(gh, repo, p.number)).value

    commits = _get(gh, f"repos/{repo}/commits?sha={default}&per_page=100") or []
    direct = direct_factory_commits(commits)

    return Snapshot(
        repo=repo, default_branch=default, branches=branches, config_error=config_error,
        config_found=config_text is not None, existing_project=existing,
        plan_files=plan_files, plan_config=plan_config, prs=tuple(prs),
        planning_verdicts=verdicts, story_verdicts=story_verdicts, issues=tuple(issues),
        needs_human=tuple(needs_human),
        stories_on_default=stories, direct_factory_commits=direct)
