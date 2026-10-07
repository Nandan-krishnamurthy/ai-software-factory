"""Asking the human a question on an issue (``factory.py question``, T5.1).

A station that must stop for a human decision before any story or Planning PR exists (S01
on a red baseline) asks it on an issue labelled ``factory:needs-human``. The state engine
then reports NEEDS_HUMAN until the human removes the label (architecture §6).

* ``ask`` is idempotent (T4.4). It finds the question by the ``<!-- factory:question
  key=<key> -->`` marker in an issue body, never by its title. If that issue is open, it
  posts the new text as a marked reply and puts the label back; otherwise it creates one
  issue. A resumed station therefore never opens a second issue for an open question.
* ``answer`` reports whether a reviewer gave an explicit answer: a comment whose first
  line is ``/<keyword>`` (e.g. ``/accept-baseline``), by an author in ``config.reviewers``,
  with no ``factory:`` marker (rule U2), posted **after** the factory's latest post on the
  issue. An older answer does not count for a question asked again since.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from factory import comments as comments_mod
from factory.errors import FactoryError
from factory.gh import Gh
from factory.markers import QuestionMarker, build, find, has_factory_marker

NEEDS_HUMAN_LABEL = "factory:needs-human"
_KEYWORD = re.compile(r"^[a-z][a-z0-9-]*$")


class QuestionError(FactoryError):
    """The question could not be asked or read as requested."""


@dataclass(frozen=True)
class Asked:
    action: str  # "created" | "updated"
    number: int
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "number": self.number, "url": self.url}


@dataclass(frozen=True)
class Answer:
    issue: int | None
    state: str | None  # "open" | "closed", or None when the question was never asked
    accepted: bool
    by: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"issue": self.issue, "state": self.state, "accepted": self.accepted,
                "by": self.by, "url": self.url}


def marker(key: str) -> QuestionMarker:
    try:
        return QuestionMarker(key=key)
    except ValueError as err:
        raise QuestionError(f"invalid --key: {err}") from None


def find_question(gh: Gh, repo: str, key: str) -> dict | None:
    """The newest issue (open or closed, never a PR) whose body has this question marker."""
    wanted = marker(key)
    found = [item for item in gh.api(f"repos/{repo}/issues?state=all&per_page=100",
                                     paginate=True)
             if "pull_request" not in item and find(item.get("body"), QuestionMarker) == wanted]
    return max(found, key=lambda item: item["number"]) if found else None


def ask(gh: Gh, repo: str, key: str, title: str, text: str) -> Asked:
    if not title.strip():
        raise QuestionError("a question needs a non-empty --title")
    if not text.strip():
        raise QuestionError("a question needs a non-empty body")
    if has_factory_marker(text):
        raise QuestionError("the body must not contain factory markers; the helper adds them")
    existing = find_question(gh, repo, key)
    if existing is not None and existing.get("state") == "open":
        number = existing["number"]
        comments_mod.post_reply(gh, repo, number, text)
        gh.api(f"repos/{repo}/issues/{number}/labels", method="POST",
               json_body={"labels": [NEEDS_HUMAN_LABEL]})
        return Asked("updated", number, existing["html_url"])
    body = build(marker(key)) + "\n" + text.strip()
    created = gh.api(f"repos/{repo}/issues", method="POST",
                     json_body={"title": title.strip(), "body": body,
                                "labels": [NEEDS_HUMAN_LABEL]})
    return Asked("created", created["number"], created["html_url"])


def answer(gh: Gh, repo: str, key: str, keyword: str, reviewers: list[str]) -> Answer:
    if not _KEYWORD.match(keyword):
        raise QuestionError(f"invalid --keyword {keyword!r}: lower-case letters, digits and "
                            "dashes, without the leading slash")
    issue = find_question(gh, repo, key)
    if issue is None:
        return Answer(None, None, False)
    comments = comments_mod.list_comments(gh, repo, issue["number"])
    return Answer(issue["number"], issue.get("state"),
                  *accepted_by(issue, comments, keyword, reviewers))


def accepted_by(issue: dict, comments: list[dict], keyword: str,
                reviewers: list[str]) -> tuple[bool, str | None, str | None]:
    """Pure: ``(accepted, author, url)`` for the newest valid ``/<keyword>`` answer."""
    allowed = {r.lower() for r in reviewers}
    trigger = re.compile(rf"^/{re.escape(keyword)}(?=\s|$)")
    asked = [_ts(issue["created_at"])]
    asked += [_ts(c["created_at"]) for c in comments if has_factory_marker(c.get("body"))]
    since = max(asked)
    for comment in sorted(comments, key=lambda c: _ts(c["created_at"]), reverse=True):
        body = comment.get("body") or ""
        author = ((comment.get("user") or {}).get("login") or "")
        if (_ts(comment["created_at"]) > since and author.lower() in allowed
                and not has_factory_marker(body)
                and trigger.match(body.strip().splitlines()[0].strip() if body.strip() else "")):
            return True, author, comment.get("html_url")
    return False, None, None


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
