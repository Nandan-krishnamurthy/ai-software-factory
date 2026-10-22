"""``factory.py closeout``: the checks and GitHub changes of station S12 (T4.3).

Close-out runs only after the human's merge, which is their approval (D5). This module
is the code-level gate for that: it looks for a **merged** story PR (one whose
``factory:pr`` marker names the issue's story) and refuses without one. It never merges
anything and never picks a story (D1, D2).

* ``inspect()`` is read-only. It confirms the merge and reports what S12 needs: the PR,
  its branch, its final head commit (to delete the local branch safely), the merge
  commit, the stories that close-out unblocks, and whether it completes the increment.
* ``finish()`` checks the merge again, closes the issue if the merge did not (a PR
  without ``Closes #<I>``), and then sets ``status:done``. The label is set **last**: it
  is what moves the state engine on from CLOSEOUT_PENDING, so an interrupted run is
  simply run again.

``next_step`` is the line S12's close-out summary ends with. It is decided here, not by
the model. The increment is complete by the state engine's own rule for INCREMENT_COMPLETE:
every other story of the increment is closed **and** ``status:done``. Then the human's next
step is ``/factory-start`` (M5 follow-up 2); otherwise it is ``continue``. A story closed
without ``status:done`` (closed by hand, with no merged PR) keeps the increment open: the
state engine reports NEEDS_HUMAN for it, where ``/factory-start`` is not allowed.

``verify_after_merge`` (T6.5) says whether S12 must first run ``verify run`` on the
default branch: the story's PR introduced commands (the walking skeleton), which the
merge approved but nothing has run yet, or that run failed. It is read from the evidence
in the story's checkpoint, so a failed run is asked for again until one passes.

``plan()``, ``newly_unblocked()``, ``remaining_in_increment()`` and ``after_merge()`` are
pure.
"""

from dataclasses import dataclass

from factory import comments as comments_mod
from factory import evidence as evidence_mod
from factory import pick as pick_mod
from factory.errors import FactoryError
from factory.gh import Gh
from factory.issues import fetch_all_issues
from factory.markers import PrMarker, StoryMarker, find

DONE = "status:done"
CONTINUE = "Say continue (`/factory-continue`) to start the next story."
_PR_FIELDS = ["number", "state", "body", "headRefName", "headRefOid", "mergeCommit",
              "mergedAt", "url"]


class CloseoutError(FactoryError):
    """Close-out refused: no merge was observed, or the issue is not a story."""


@dataclass(frozen=True)
class Closeout:
    issue: int
    story_id: str
    issue_open: bool
    done: bool  # already labelled status:done
    pr: int
    pr_url: str
    branch: str
    head_sha: str  # the PR's final head commit: the work that was reviewed and merged
    merge_sha: str
    merged_at: str
    unblocked: tuple[pick_mod.StoryIssue, ...]  # ready stories this close-out unblocks
    increment: str = ""
    # The increment's other story issues that are not both closed and status:done.
    remaining: tuple[int, ...] = ()
    # Why `verify run` must run on the default branch before close-out, or None (T6.5).
    verify_after_merge: str | None = None

    @property
    def increment_complete(self) -> bool:
        """Every other story of the increment is closed and done: this close-out is its
        last (the state engine's INCREMENT_COMPLETE rule)."""
        return not self.remaining

    @property
    def next_step(self) -> str:
        """The line the close-out summary ends with: what the human does next."""
        if self.increment_complete:
            return (f"Increment {self.increment} is complete: every story is done. Run "
                    "`/factory-start` with new requirements to plan the next increment.")
        return CONTINUE

    def to_dict(self) -> dict:
        return {"issue": self.issue, "story": self.story_id, "issue_open": self.issue_open,
                "done": self.done, "pr": self.pr, "pr_url": self.pr_url,
                "branch": self.branch, "head_sha": self.head_sha,
                "merge_sha": self.merge_sha, "merged_at": self.merged_at,
                "unblocked": [{"number": s.number, "story": s.story_id, "title": s.title}
                              for s in self.unblocked],
                "increment": self.increment, "increment_complete": self.increment_complete,
                "remaining": list(self.remaining), "next_step": self.next_step,
                "verify_after_merge": self.verify_after_merge}


# ----------------------------------------------------------------------------- pure


def merged_pr(story_id: str, prs: list[dict]) -> dict | None:
    """The newest merged PR whose ``factory:pr`` marker names ``story_id``."""
    merged = [p for p in prs if p.get("mergedAt") and (marker := find(p.get("body"), PrMarker))
              and marker.story == story_id]
    return max(merged, key=lambda p: p["number"]) if merged else None


def newly_unblocked(number: int, stories: list[pick_mod.StoryIssue],
                    is_open: dict[int, bool]) -> tuple[pick_mod.StoryIssue, ...]:
    """Open ``status:ready`` stories blocked by ``number`` whose blockers are all closed
    once ``number`` is (a blocker the factory cannot see counts as open, as in ``pick``)."""
    closed = {**is_open, number: False}
    found = [s for s in stories
             if s.open and "status:ready" in s.labels and pick_mod.NEEDS_HUMAN not in s.labels
             and number in s.blocked_by and not any(closed.get(b, True) for b in s.blocked_by)]
    return tuple(sorted(found, key=pick_mod.StoryIssue.sort_key))


def remaining_in_increment(number: int, increment: str,
                           stories: list[pick_mod.StoryIssue]) -> tuple[int, ...]:
    """The story issues of ``increment`` other than ``number`` (the one being closed out)
    that are open, or closed without ``status:done``, in number order."""
    return tuple(sorted(s.number for s in stories
                        if s.increment == increment and s.number != number
                        and (s.open or DONE not in s.labels)))


def after_merge(recorded: evidence_mod.Evidence | None, story_branch: str) -> str | None:
    """Why the commands must run on the default branch before the story is done, from the
    latest evidence in its checkpoint, or ``None``."""
    if recorded is None:
        return None
    if recorded.branch == story_branch:
        if not recorded.pending:
            return None
        one = len(recorded.pending) == 1
        return (f"{evidence_mod.pending_text(recorded)} {'was' if one else 'were'} "
                "introduced by the story's PR and approved by the merge, and "
                f"{'has' if one else 'have'} not run yet")
    if failures := recorded.failures() + recorded.report_problems():
        return f"the last run on {recorded.branch} failed: " + "; ".join(failures)
    return None


def plan(number: int, issue: dict, prs: list[dict], all_issues: list[dict],
         recorded: evidence_mod.Evidence | None = None) -> Closeout:
    """What close-out of story issue ``number`` involves. Refuses without a merged PR.
    ``recorded``: the evidence in the story's checkpoint, if any."""
    if "pull_request" in issue:
        raise CloseoutError(f"#{number} is a pull request; close-out works on the story issue")
    marker = find(issue.get("body"), StoryMarker)
    if marker is None:
        raise CloseoutError(f"#{number} is not a factory story issue (no factory:story marker)")
    pr = merged_pr(marker.id, prs)
    if pr is None:
        raise CloseoutError(f"no merged PR for {marker.id} (#{number}): close-out runs only "
                            "after the human has merged the story PR (D5). The factory never "
                            "merges")
    stories, is_open = pick_mod.parse_issues(all_issues)
    labels = {label["name"] for label in issue.get("labels") or []}
    return Closeout(
        issue=number, story_id=marker.id,
        issue_open=(issue.get("state") or "open").lower() == "open", done=DONE in labels,
        pr=pr["number"], pr_url=pr.get("url", ""), branch=pr.get("headRefName", ""),
        head_sha=pr.get("headRefOid", ""),
        merge_sha=(pr.get("mergeCommit") or {}).get("oid", ""), merged_at=pr["mergedAt"],
        unblocked=newly_unblocked(number, stories, is_open), increment=marker.increment,
        remaining=remaining_in_increment(number, marker.increment, stories),
        verify_after_merge=after_merge(recorded, pr.get("headRefName", "")))


# ----------------------------------------------------------------------------- GitHub


def inspect(gh: Gh, repo: str, number: int) -> Closeout:
    """Read-only: confirm the merge and gather what S12 needs."""
    issue = gh.api(f"repos/{repo}/issues/{number}")
    prs = gh.json(["pr", "list", "--repo", repo, "--state", "merged", "--limit", "200"],
                  fields=_PR_FIELDS)
    found = comments_mod.find_checkpoint(comments_mod.list_comments(gh, repo, number))
    recorded = (evidence_mod.from_body(found[0].get("body") or "") if found is not None
                else None)
    return plan(number, issue, prs, fetch_all_issues(gh, repo), recorded)


def finish(gh: Gh, repo: str, number: int) -> tuple[Closeout, list[str]]:
    """Check the merge again, close the issue if needed, then set ``status:done`` last."""
    closeout = inspect(gh, repo, number)
    changes = []
    if closeout.issue_open:
        gh.api(f"repos/{repo}/issues/{number}", method="PATCH",
               json_body={"state": "closed", "state_reason": "completed"})
        changes.append("closed")
    add, remove = pick_mod.set_status(gh, repo, number, "done")
    changes += [f"+{name}" for name in add] + [f"-{name}" for name in remove]
    return closeout, changes


def render(closeout: Closeout) -> str:
    c = closeout
    lines = [f"#{c.issue} ({c.story_id}): PR #{c.pr} merged at {c.merged_at} "
             f"(merge commit {c.merge_sha[:7] or '?'}, branch {c.branch} @ {c.head_sha[:7]})",
             f"  issue {'open' if c.issue_open else 'closed'}"
             + (", already status:done" if c.done else "")]
    if c.unblocked:
        lines.append("  now unblocked: " + ", ".join(f"#{s.number} ({s.story_id})"
                                                     for s in c.unblocked))
    else:
        lines.append("  unblocks no other story")
    if c.increment_complete:
        lines.append(f"  last story of increment {c.increment}: every other story is done")
    else:
        lines.append(f"  increment {c.increment} has stories not done: "
                     + ", ".join(f"#{n}" for n in c.remaining))
    if c.verify_after_merge:
        lines.append(f"  run `verify run` on the default branch first: {c.verify_after_merge}")
    lines.append(f"Next step: {c.next_step}")
    return "\n".join(lines)
