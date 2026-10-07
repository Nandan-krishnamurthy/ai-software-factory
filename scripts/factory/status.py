"""The ``/factory-status`` report (``factory.py status``, T5.3). Read-only.

The first line always answers "what do I do next?" for the state the engine derived. Then:

* a **hint** when a PR waiting for review has human comments in its current round but no
  ``/changes``: the factory does not act on them until a reviewer comments ``/changes``
  (rule U3), which is easy to miss;
* the state, increment, next station, who it is waiting on and the commands allowed;
* the progress of the current increment's stories;
* the **Done** status of each requirement (requirements §11): a ``REQ`` is Done when its
  row in ``docs/factory/traceability.md`` on the default branch says ``Implemented`` and
  every PR listed for it is merged. This is worked out from GitHub, never written down;
* any ``problems`` or ``items`` of the state, as they are.

``build`` and ``render`` are pure; ``collect`` reads GitHub.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from factory import state as st
from factory.gh import Gh
from factory.signals import Verdict, fetch_pr, signals_for

SCHEMA_VERSION = 1
TRACEABILITY = "docs/factory/traceability.md"
_ROW = re.compile(r"^\|\s*(REQ-\d{3,})\s*\|(.*)\|\s*$")
_PR_REF = re.compile(r"#(\d+)")
_IMPLEMENTED, _DEFERRED = "Implemented", "Deferred"
_REVIEW_STATES = {st.GATE_A_WAITING, st.GATE_B_WAITING_REVIEW}
_IN_FLIGHT = {st.IN_PROGRESS, st.IN_REVIEW, st.CHANGES_REQUESTED}  # the story lock


# ----------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Requirement:
    req: str
    status: str  # the matrix's Status cell
    prs: tuple[int, ...]
    done: bool
    why: str  # why it is (not) Done, for humans

    def to_dict(self) -> dict[str, Any]:
        return {"req": self.req, "status": self.status, "prs": list(self.prs),
                "done": self.done, "why": self.why}


@dataclass(frozen=True)
class Progress:
    increment: str
    total: int
    done: int
    in_flight: tuple[int, ...]  # issue numbers in progress, in review or in rework
    not_started: int

    def to_dict(self) -> dict[str, Any]:
        return {"increment": self.increment, "total": self.total, "done": self.done,
                "in_flight": list(self.in_flight), "not_started": self.not_started}


@dataclass(frozen=True)
class Report:
    next_action: str
    state: dict[str, Any]  # the ``state --json`` object
    hint: str | None = None
    progress: Progress | None = None
    requirements: tuple[Requirement, ...] | None = None  # None: no traceability.md yet
    notes: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        reqs = self.requirements
        return {
            "schema": SCHEMA_VERSION,
            "next": self.next_action,
            "hint": self.hint,
            "state": self.state,
            "progress": self.progress.to_dict() if self.progress else None,
            "requirements": [r.to_dict() for r in reqs] if reqs is not None else None,
            "requirements_done": sum(r.done for r in reqs) if reqs is not None else None,
            "notes": list(self.notes),
        }


# ----------------------------------------------------------------------------- pure


def next_action(result: dict[str, Any]) -> str:
    """One line: what the human does next, for the state in ``result`` (``state --json``)."""
    state, details = result["state"], result["details"]
    inc = result.get("increment")
    pr, issue, story = details.get("pr"), details.get("issue"), details.get("story")
    station = result.get("next_station")
    review = "merge it yourself to approve, or comment /changes and run /factory-resume."
    actions = {
        st.UNCONFIGURED: "Run /factory-start <requirements-file> to plan the first increment.",
        st.PLANNING: f"Run /factory-resume to finish planning {inc} (next: {station}).",
        st.GATE_A_WAITING: f"Review Planning PR #{pr}: {review}",
        st.GATE_A_CHANGES: f"Run /factory-resume: the factory revises Planning PR #{pr} and "
                           "answers your feedback.",
        st.ISSUES_PENDING: f"Run /factory-resume to create the story issues of {inc}.",
        st.IDLE_AT_GATE_C: f"Say continue: run /factory-continue to start the next story "
                           f"({len(details.get('ready', []))} ready).",
        st.STORY_IN_PROGRESS: f"Run /factory-resume to finish story #{issue} ({story}) "
                              f"from {station}.",
        st.GATE_B_WAITING_REVIEW: f"Review PR #{pr} ({story}): {review}",
        st.GATE_B_CHANGES_REQUESTED: f"Run /factory-resume: the factory reworks PR #{pr} "
                                     f"({story}) and answers each point.",
        st.GATE_B_APPROVED_UNMERGED: f"Merge PR #{pr} ({story}) yourself (the factory never "
                                     "merges), then run /factory-resume.",
        st.CLOSEOUT_PENDING: f"Run /factory-resume to close out story #{issue} (PR #{pr} is "
                             "merged), or /factory-continue to also start the next story.",
        st.INCREMENT_COMPLETE: f"Increment {inc} is complete: run /factory-start "
                               "<change-request> to plan the next one.",
        st.NEEDS_HUMAN: "Decide on " + ", ".join(details.get("items") or ["the item below"])
                        + ", remove the factory:needs-human label if there is one, then run "
                          "/factory-resume.",
        st.INCONSISTENT: "Fix the problems listed below by hand; the factory changes nothing "
                         "until then.",
    }
    return actions[state]


def comments_hint(pr: int, count: int) -> str | None:
    """The "N comments, no /changes" hint for a PR waiting for review, or None."""
    if count <= 0:
        return None
    noun = "comment" if count == 1 else "comments"
    return (f"PR #{pr} has {count} {noun} from you in this round but no /changes, so the "
            "factory will not act on them. To request rework, comment /changes (first line) "
            "with your feedback, then run /factory-resume.")


def parse_traceability(text: str) -> list[tuple[str, str, tuple[int, ...]]]:
    """``(REQ, Status, PR numbers)`` for each row of the matrix, in file order."""
    rows = []
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        cells = [c.strip() for c in match[2].split("|")]
        if len(cells) != 4:  # Stories | PRs | Tests | Status
            continue
        prs = tuple(int(n) for n in _PR_REF.findall(cells[1]))
        rows.append((match[1], cells[3], prs))
    return rows


def requirement_status(rows: list[tuple[str, str, tuple[int, ...]]],
                       pr_states: dict[int, str]) -> tuple[Requirement, ...]:
    """Requirements §11: Done when ``Implemented`` and every listed PR is merged."""
    found = []
    for req, status, prs in rows:
        if status == _DEFERRED:
            found.append(Requirement(req, status, prs, False, "deferred"))
            continue
        if status != _IMPLEMENTED:
            found.append(Requirement(req, status, prs, False, status.lower() or "no status"))
            continue
        if not prs:
            found.append(Requirement(req, status, prs, False, "implemented, but no PR listed"))
            continue
        unmerged = [f"#{n} {pr_states.get(n, 'not found').lower()}" for n in prs
                    if pr_states.get(n) != "MERGED"]
        found.append(Requirement(req, status, prs, not unmerged,
                                 "PR " + ", ".join(unmerged) if unmerged else "merged"))
    return tuple(found)


def progress(snap: st.Snapshot, increment: str | None) -> Progress | None:
    stories = [i for i in snap.issues if i.story is not None and i.story.increment == increment]
    if increment is None or not stories:
        return None
    done = sum(1 for i in stories if i.state != "OPEN" and st.DONE in i.labels)
    flight = tuple(sorted(i.number for i in stories
                          if i.state == "OPEN" and i.labels & _IN_FLIGHT))
    return Progress(increment, len(stories), done, flight, len(stories) - done - len(flight))


def build(result: dict[str, Any], snap: st.Snapshot | None = None,
          traceability: str | None = None, comments_in_round: int = 0) -> Report:
    """Pure: the report for a ``state --json`` object and what ``collect`` read."""
    details = result["details"]
    hint = None
    if result["state"] in _REVIEW_STATES:
        hint = comments_hint(details["pr"], comments_in_round)
    reqs = None
    if traceability is not None:
        states = {p.number: p.state for p in snap.prs} if snap else {}
        reqs = requirement_status(parse_traceability(traceability), states)
    notes = tuple(f"Problem: {p}" for p in details.get("problems", ()))
    if result["state"] == st.PLANNING and details.get("missing"):
        notes += ("Planning documents still to write: " + ", ".join(details["missing"]),)
    return Report(next_action(result), result, hint,
                  progress(snap, result.get("increment")) if snap else None, reqs, notes)


def render(report: Report) -> str:
    data = report.state
    lines = [f"Next: {report.next_action}"]
    if report.hint:
        lines.append(f"Hint: {report.hint}")
    lines.append("")
    where = f"State: {data['state']}"
    if data["increment"]:
        where += f" (increment {data['increment']})"
    if data["next_station"]:
        where += f", next station {data['next_station']}"
    lines.append(where)
    lines.append("Waiting on: " + {"human": "you", "factory": "the factory",
                                   "nobody": "nobody"}[data["waiting_on"]])
    lines.append("Allowed: " + ", ".join(data["allowed_commands"]))
    lines.append(data["details"]["message"])
    for item in data["details"].get("items", ()):
        lines.append(f"  - {item}")
    lines.extend(report.notes)

    if report.progress:
        p = report.progress
        line = f"Stories in {p.increment}: {p.done} of {p.total} done"
        if p.in_flight:
            line += ", in flight " + ", ".join(f"#{n}" for n in p.in_flight)
        if p.not_started:
            line += f", {p.not_started} not started"
        lines += ["", line + "."]

    lines.append("")
    if report.requirements is None:
        lines.append(f"Requirements: no {TRACEABILITY} on the default branch yet.")
    elif not report.requirements:
        lines.append(f"Requirements: {TRACEABILITY} lists none yet.")
    else:
        reqs = report.requirements
        deferred = sum(r.status == _DEFERRED for r in reqs)
        summary = f"Requirements: {sum(r.done for r in reqs)} of {len(reqs)} Done"
        summary += f", {deferred} deferred" if deferred else ""
        lines.append(summary + ". Done = Implemented and every listed PR merged.")
        for r in reqs:
            prs = ", ".join(f"#{n}" for n in r.prs) or "-"
            mark = "Done" if r.done else "not done"
            lines.append(f"  {r.req:<8} {mark:<9} {prs:<12} {r.why}".rstrip())
    return "\n".join(lines)


# ----------------------------------------------------------------------------- I/O


def collect(gh: Gh, repo: str) -> Report:
    """Read the state, the traceability matrix on the default branch and, for a PR waiting
    for review, its human comments in the current round."""
    snap = st.collect_snapshot(gh, repo)
    result = st.derive_state(snap).to_dict()
    traceability = None
    if not snap.is_empty:
        traceability = st._file_text(gh, repo, TRACEABILITY, snap.default_branch)
    comments = 0
    if result["state"] in _REVIEW_STATES:
        # Before the first Planning PR is merged, the config exists only on its branch.
        refs = [snap.default_branch, f"{st.PLAN_BRANCH_PREFIX}{result['increment']}"]
        text = next((t for ref in refs
                     if (t := st._file_text(gh, repo, ".factory/config.json", ref))), None)
        config, _ = st._parse_config_text(text)
        if config is not None:
            pr = fetch_pr(gh, repo, result["details"]["pr"])
            gate = signals_for(config)
            if gate.verdict(pr) == Verdict.PENDING:
                comments = len(gate.feedback(pr))
    return build(result, snap, traceability, comments)
