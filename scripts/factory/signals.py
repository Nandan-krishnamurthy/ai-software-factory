"""Gate signals: how the factory reads a human decision on a PR (architecture §9).

The state machine and stations only ever see a normalised ``Verdict`` and a list of
``Feedback`` items. ``config.identity.mode`` picks the implementation; nothing outside this
module looks at the mode. Only ``single-account`` exists for the MVP (D5):

* **MERGED**: the PR is merged. That *is* the approval.
* **CLOSED_UNMERGED**: closed without merging, i.e. the story was rejected.
* **CHANGES_REQUESTED**: a human comment whose first line is ``/changes``, posted after
  the current review round started (a PR conversation comment or a review summary).
* **PENDING**: anything else. ``APPROVED`` is never returned in single-account mode.

A comment is **human** when its author is in ``config.reviewers`` and it carries no
``factory:`` marker. A comment is the **factory's** when it carries a marker *and* its
author is a reviewer (in single-account mode the factory posts as the reviewer's own
account). Marked comments from anyone else are ignored, so a stranger cannot fake a
factory reply to cancel a real ``/changes``.

A **review round** starts at the latest of: the newest commit on the PR, and the newest
factory comment on it. The rework station pushes commits and replies to every item, which
starts a new round, so the same ``/changes`` never triggers rework twice (§7.2).

**Rework items** (T4.2) do not move with each push: they are the human comments since the
factory's last **round summary** (a factory reply *without* ``to=``) that no factory reply
answers yet (a reply marked ``to=<comment id>``). A rework that is interrupted after its
push, or half-way through its replies, therefore finds exactly the items still open; a
finished round has none.

``SingleAccountSignals`` is pure: it works on a ``PrSnapshot``. ``fetch_pr`` builds one
from GitHub.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from factory.errors import FactoryError
from factory.gh import Gh
from factory.markers import ReplyMarker, find, has_factory_marker


class Verdict(Enum):
    PENDING = "PENDING"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"  # bot mode only (architecture §9.4); never in single-account
    MERGED = "MERGED"
    CLOSED_UNMERGED = "CLOSED_UNMERGED"


@dataclass(frozen=True)
class Comment:
    id: str
    author: str
    body: str
    created_at: datetime
    kind: str  # "conversation" | "review" (a review summary) | "inline" (on a diff line)
    url: str = ""
    path: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class PrSnapshot:
    number: int
    state: str  # "OPEN" | "CLOSED" | "MERGED"
    merged: bool
    head_ref: str
    last_commit_at: datetime | None
    comments: tuple[Comment, ...]


@dataclass(frozen=True)
class Feedback:
    comment: Comment
    text: str  # for the /changes comment itself: the text after "/changes"
    is_trigger: bool


class GateSignals(Protocol):
    def verdict(self, pr: PrSnapshot) -> Verdict: ...
    def feedback(self, pr: PrSnapshot, since: datetime | None = None) -> list[Feedback]: ...
    def rework_items(self, pr: PrSnapshot) -> list[Feedback]: ...
    def is_human(self, comment: Comment) -> bool: ...


_CHANGES = re.compile(r"^/changes(?=\s|$)")


def _first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


class SingleAccountSignals:
    """Merge = approval; ``/changes`` = rework (architecture §9.2)."""

    def __init__(self, reviewers: Iterable[str]):
        self.reviewers = frozenset(r.lower() for r in reviewers)
        if not self.reviewers:
            raise ValueError("at least one reviewer is required")

    # -- classification ---------------------------------------------------------------
    def _is_reviewer(self, comment: Comment) -> bool:
        return comment.author.lower() in self.reviewers

    def is_human(self, comment: Comment) -> bool:
        return self._is_reviewer(comment) and not has_factory_marker(comment.body)

    def is_factory(self, comment: Comment) -> bool:
        return self._is_reviewer(comment) and has_factory_marker(comment.body)

    def is_trigger(self, comment: Comment) -> bool:
        return (self.is_human(comment) and comment.kind in ("conversation", "review")
                and bool(_CHANGES.match(_first_line(comment.body))))

    # -- rounds -------------------------------------------------------------------------
    def round_start(self, pr: PrSnapshot) -> datetime | None:
        """When the current review round began: the newest commit or factory comment."""
        moments = [c.created_at for c in pr.comments if self.is_factory(c)]
        if pr.last_commit_at is not None:
            moments.append(pr.last_commit_at)
        return max(moments) if moments else None

    # -- the interface ------------------------------------------------------------------
    def verdict(self, pr: PrSnapshot) -> Verdict:
        if pr.merged or pr.state == "MERGED":
            return Verdict.MERGED
        if pr.state == "CLOSED":
            return Verdict.CLOSED_UNMERGED
        start = self.round_start(pr)
        if any(self.is_trigger(c) and _after(c.created_at, start) for c in pr.comments):
            return Verdict.CHANGES_REQUESTED
        return Verdict.PENDING

    def feedback(self, pr: PrSnapshot, since: datetime | None = None) -> list[Feedback]:
        """Every human comment in the current round (or since ``since``), oldest first."""
        return self._items(pr, since if since is not None else self.round_start(pr))

    # -- rework (T4.2) ------------------------------------------------------------------
    def answered(self, pr: PrSnapshot) -> set[str]:
        """Ids of the comments that a factory reply answers (``to=<id>``)."""
        ids = set()
        for comment in pr.comments:
            reply = find(comment.body, ReplyMarker) if self.is_factory(comment) else None
            if reply is not None and reply.to is not None:
                ids.add(reply.to)
        return ids

    def last_round_close(self, pr: PrSnapshot) -> datetime | None:
        """When the factory last closed a review round: its newest reply without ``to``."""
        moments = [c.created_at for c in pr.comments if self.is_factory(c)
                   and (reply := find(c.body, ReplyMarker)) is not None and reply.to is None]
        return max(moments) if moments else None

    def rework_items(self, pr: PrSnapshot) -> list[Feedback]:
        """The feedback items of the round being reworked that have no answer yet."""
        answered = self.answered(pr)
        return [f for f in self._items(pr, self.last_round_close(pr))
                if f.comment.id not in answered]

    def _items(self, pr: PrSnapshot, start: datetime | None) -> list[Feedback]:
        items = []
        for comment in sorted(pr.comments, key=lambda c: c.created_at):
            if not self.is_human(comment) or not _after(comment.created_at, start):
                continue
            trigger = self.is_trigger(comment)
            text = comment.body.strip()
            if trigger:
                text = _CHANGES.sub("", text, count=1).strip()
            items.append(Feedback(comment, text, trigger))
        return items


def _after(moment: datetime, start: datetime | None) -> bool:
    return start is None or moment > start


def signals_for(config) -> GateSignals:
    """The gate-signal implementation for ``config.identity.mode``."""
    mode = config.identity.mode
    if mode == "single-account":
        return SingleAccountSignals(config.reviewers)
    raise FactoryError(f"identity.mode {mode!r} is not implemented yet (architecture §9.4)")


# ----------------------------------------------------------------------------- I/O

_PR_FIELDS = ["number", "state", "mergedAt", "headRefName", "commits", "comments", "reviews"]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_pr(gh: Gh, repo: str, number: int) -> PrSnapshot:
    """Read a PR's state, commits, conversation comments, review summaries and inline
    review comments from GitHub."""
    data = gh.json(["pr", "view", str(number), "--repo", repo], fields=_PR_FIELDS)
    inline = gh.api(f"repos/{repo}/pulls/{number}/comments", paginate=True)
    return snapshot_from_github(data, inline)


def snapshot_from_github(data: dict, inline: list[dict]) -> PrSnapshot:
    """Pure: build a ``PrSnapshot`` from ``gh pr view --json`` and the REST inline comments."""
    comments: list[Comment] = []
    for c in data.get("comments") or []:
        comments.append(Comment(
            id=str(c.get("id", "")), author=(c.get("author") or {}).get("login", ""),
            body=c.get("body") or "", created_at=_ts(c["createdAt"]), kind="conversation",
            url=c.get("url", "")))
    for r in data.get("reviews") or []:
        if not (r.get("body") or "").strip() or not r.get("submittedAt"):
            continue  # a review with no summary text has nothing to act on
        comments.append(Comment(
            id=str(r.get("id", "")), author=(r.get("author") or {}).get("login", ""),
            body=r["body"], created_at=_ts(r["submittedAt"]), kind="review"))
    for c in inline or []:
        comments.append(Comment(
            id=str(c.get("id", "")), author=(c.get("user") or {}).get("login", ""),
            body=c.get("body") or "", created_at=_ts(c["created_at"]), kind="inline",
            url=c.get("html_url", ""), path=c.get("path"),
            line=c.get("line") or c.get("original_line")))
    commit_times = [_ts(c["committedDate"]) for c in data.get("commits") or []
                    if c.get("committedDate")]
    state = data.get("state", "OPEN")
    return PrSnapshot(
        number=data["number"],
        state=state,
        merged=bool(data.get("mergedAt")) or state == "MERGED",
        head_ref=data.get("headRefName", ""),
        last_commit_at=max(commit_times) if commit_times else None,
        comments=tuple(comments),
    )
