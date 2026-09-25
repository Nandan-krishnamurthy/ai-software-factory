"""``factory.py closeout``: the checks and GitHub changes of station S12 (T4.3).

Close-out runs only after the human's merge, which is their approval (D5). This module
is the code-level gate for that: it looks for a **merged** story PR (one whose
``factory:pr`` marker names the issue's story) and refuses without one. It never merges
anything and never picks a story (D1, D2).

* ``inspect()`` is read-only. It confirms the merge and reports what S12 needs: the PR,
  its branch, its final head commit (to delete the local branch safely), the merge
  commit, and the stories that close-out unblocks.
* ``finish()`` checks the merge again, closes the issue if the merge did not (a PR
  without ``Closes #<I>``), and then sets ``status:done``. The label is set **last**: it
  is what moves the state engine on from CLOSEOUT_PENDING, so an interrupted run is
  simply run again.

``plan()`` and ``newly_unblocked()`` are pure.
"""

from dataclasses import dataclass

from factory import pick as pick_mod
from factory.errors import FactoryError
from factory.gh import Gh
from factory.issues import fetch_all_issues
from factory.markers import PrMarker, StoryMarker, find

DONE = "status:done"
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

    def to_dict(self) -> dict:
        return {"issue": self.issue, "story": self.story_id, "issue_open": self.issue_open,
                "done": self.done, "pr": self.pr, "pr_url": self.pr_url,
                "branch": self.branch, "head_sha": self.head_sha,
                "merge_sha": self.merge_sha, "merged_at": self.merged_at,
                "unblocked": [{"number": s.number, "story": s.story_id, "title": s.title}
                              for s in self.unblocked]}


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


def plan(number: int, issue: dict, prs: list[dict], all_issues: list[dict]) -> Closeout:
    """What close-out of story issue ``number`` involves. Refuses without a merged PR."""
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
        unblocked=newly_unblocked(number, stories, is_open))


# ----------------------------------------------------------------------------- GitHub


def inspect(gh: Gh, repo: str, number: int) -> Closeout:
    """Read-only: confirm the merge and gather what S12 needs."""
    issue = gh.api(f"repos/{repo}/issues/{number}")
    prs = gh.json(["pr", "list", "--repo", repo, "--state", "merged", "--limit", "200"],
                  fields=_PR_FIELDS)
    return plan(number, issue, prs, fetch_all_issues(gh, repo))


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
    return "\n".join(lines)
