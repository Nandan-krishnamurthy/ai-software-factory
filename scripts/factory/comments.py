"""Posting factory comments on issues and PRs (``factory.py comment``).

Every comment the factory posts goes through this module, so every one carries a
``factory:`` marker (architecture §5.5, rule S14). That is how the factory's comments are
told apart from the human's when both use the same GitHub account (D5).

* ``post_reply`` adds a new comment that starts with ``<!-- factory:reply -->``, or
  ``<!-- factory:reply to=<id> -->`` when it answers one feedback item (T4.2).
* ``upsert_checkpoint`` keeps exactly **one** checkpoint comment per issue: it edits the
  existing one in place, or creates it if there is none. An evidence block
  (``set_checkpoint_evidence``, T6.1) or an AC-to-test map block (``set_checkpoint_map``,
  T6.2) already in the note is always carried over. A note may never supply one of its
  own (T6.2): only ``verify run`` and ``verify map`` write these blocks, so ``verdict
  check`` can trust them.

Comments go through the REST issue-comments API, which covers PRs as well (every PR is
an issue). Bodies are sent as JSON on stdin, never as command-line arguments.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from factory.errors import FactoryError
from factory.gh import Gh
from factory.markers import CheckpointMarker, ReplyMarker, build, find, has_factory_marker

# GitHub rejects comment bodies over 65,536 characters.
MAX_BODY = 65536

# The evidence ledger (``verify run``, T6.1) lives in the checkpoint note between these
# delimiters. They are not factory markers: the state engine never reads them.
EVIDENCE_START = "<!-- evidence:start -->"
EVIDENCE_END = "<!-- evidence:end -->"
# The AC-to-test map (``verify map``, T6.2) lives there too, between its own delimiters.
MAP_START = "<!-- acmap:start -->"
MAP_END = "<!-- acmap:end -->"
# The blocks a later checkpoint carries over from the previous note.
CARRIED_BLOCKS = ((EVIDENCE_START, EVIDENCE_END), (MAP_START, MAP_END))
# A station's note may contain none of these: each one alone could end, fake or shift a
# block the factory wrote.
NOTE_DELIMITERS = (EVIDENCE_START, EVIDENCE_END, MAP_START, MAP_END)


class CommentError(FactoryError):
    """The comment could not be posted as requested."""


@dataclass(frozen=True)
class Posted:
    action: str  # "created" | "updated"
    id: int
    url: str
    body: str


def compose(marker: ReplyMarker | CheckpointMarker, text: str) -> str:
    """The marker on the first line, then the human-readable text."""
    text = text.strip()
    return build(marker) + ("\n" + text if text else "")


def check_target_kind(gh: Gh, repo: str, number: int, *, expect_pr: bool) -> None:
    """Make sure ``--issue N`` really is an issue and ``--pr N`` really is a PR."""
    item = gh.api(f"repos/{repo}/issues/{number}")
    is_pr = "pull_request" in item
    if is_pr != expect_pr:
        wanted, actual = (
            ("a pull request", "an issue") if expect_pr else ("an issue", "a pull request")
        )
        raise CommentError(f"#{number} in {repo} is {actual}, not {wanted}")


def list_comments(gh: Gh, repo: str, number: int) -> list[dict]:
    return gh.api(f"repos/{repo}/issues/{number}/comments", paginate=True)


def post_reply(gh: Gh, repo: str, number: int, text: str, *, to: str | None = None) -> Posted:
    """Add a new comment marked ``<!-- factory:reply -->`` (``to=<id>`` if it answers one)."""
    if not text.strip():
        raise CommentError("a reply needs a non-empty body")
    try:
        marker = ReplyMarker(to=to)
    except ValueError as err:
        raise CommentError(f"invalid --to: {err}") from None
    body = _checked_body(marker, text)
    created = gh.api(f"repos/{repo}/issues/{number}/comments", method="POST",
                     json_body={"body": body})
    return Posted("created", created["id"], created["html_url"], body)


def find_checkpoint(comments: list[dict]) -> tuple[dict, CheckpointMarker] | None:
    """The checkpoint comment: the oldest comment whose *first* marker is a checkpoint."""
    for comment in comments:
        marker = find(comment.get("body"), CheckpointMarker)
        if marker is not None and comment.get("body", "").lstrip().startswith(
                "<!-- factory:checkpoint"):
            return comment, marker
    return None


def upsert_checkpoint(
    gh: Gh,
    repo: str,
    number: int,
    *,
    station: str,
    next_station: str,
    branch: str,
    sha: str,
    fix_attempts: int | None = None,
    review_round: int | None = None,
    note: str = "",
    now: datetime | None = None,
) -> Posted:
    """Create or edit-in-place the single checkpoint comment on issue ``number``.

    ``fix_attempts`` / ``review_round`` default to the values in the existing checkpoint,
    so a station that does not mention them never resets them by accident.

    ``note`` may not contain an evidence or AC-to-test map delimiter: those blocks come
    only from ``verify run`` and ``verify map``, and the ones already stored are carried.
    """
    found = [d for d in NOTE_DELIMITERS if d in (note or "")]
    if found:
        raise CommentError("a checkpoint note may not contain " + ", ".join(found)
                           + ": evidence and AC-to-test map blocks are written only by "
                             "`verify run` and `verify map`, and the stored ones are "
                             "carried over")
    existing = find_checkpoint(list_comments(gh, repo, number))
    previous = existing[1] if existing else None
    try:
        marker = CheckpointMarker(
            station=station,
            next=next_station,
            branch=branch,
            sha=sha,
            fix_attempts=_carry(fix_attempts, previous, "fix_attempts"),
            review_round=_carry(review_round, previous, "review_round"),
            ts=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        )
    except ValueError as err:
        raise CommentError(f"invalid checkpoint: {err}") from None

    line = (f"**Factory checkpoint:** {station} complete. Next: {next_station}. "
            f"Branch: `{branch}` @ `{sha[:7]}`.")
    for start, end in CARRIED_BLOCKS if existing is not None else ():
        # The evidence ledger (``verify run``) and the AC-to-test map (``verify map``)
        # outlive a station's note, such as S10's verdict; ``verify check`` and
        # ``verdict check`` decide whether they are still current.
        carried = note_block(existing[0].get("body") or "", start, end)
        if carried:
            note = f"{note.strip()}\n\n{carried}"
    text = line + (f"\n\n{note.strip()}" if note.strip() else "")
    body = _checked_body(marker, text)

    if existing is None:
        created = gh.api(f"repos/{repo}/issues/{number}/comments", method="POST",
                         json_body={"body": body})
        return Posted("created", created["id"], created["html_url"], body)
    comment = existing[0]
    updated = gh.api(f"repos/{repo}/issues/comments/{comment['id']}", method="PATCH",
                     json_body={"body": body})
    return Posted("updated", updated["id"], updated["html_url"], body)


def note_block(body: str, start_mark: str, end_mark: str) -> str | None:
    """The block from ``start_mark`` to ``end_mark`` in a comment body, or ``None``."""
    body = (body or "").replace("\r\n", "\n")
    start = body.find(start_mark)
    end = body.find(end_mark, start + 1) if start >= 0 else -1
    return body[start:end + len(end_mark)] if start >= 0 and end >= 0 else None


def evidence_block(body: str) -> str | None:
    """The evidence block (``EVIDENCE_START`` … ``EVIDENCE_END``) in a comment body."""
    return note_block(body, EVIDENCE_START, EVIDENCE_END)


def map_block(body: str) -> str | None:
    """The AC-to-test map block (``MAP_START`` … ``MAP_END``) in a comment body."""
    return note_block(body, MAP_START, MAP_END)


def set_checkpoint_evidence(gh: Gh, repo: str, number: int, block: str) -> Posted:
    """Put ``block`` into the note of issue ``number``'s checkpoint comment, replacing an
    earlier evidence block. The marker and the rest of the note stay exactly as they are,
    so the state engine's view of the story does not change."""
    return _set_block(gh, repo, number, block, EVIDENCE_START, EVIDENCE_END, "evidence")


def set_checkpoint_map(gh: Gh, repo: str, number: int, block: str) -> Posted:
    """Put the AC-to-test map ``block`` into the checkpoint note, the way
    ``set_checkpoint_evidence`` does for the evidence."""
    return _set_block(gh, repo, number, block, MAP_START, MAP_END, "AC-to-test map")


def _set_block(gh: Gh, repo: str, number: int, block: str, start: str, end: str,
               what: str) -> Posted:
    article = "an" if what[0] in "aeiouAEIOU" else "a"
    if not (block.startswith(start) and block.endswith(end)):
        raise CommentError(f"{article} {what} block must start and end with its delimiters")
    if has_factory_marker(block):
        raise CommentError(f"the {what} block must not contain '<!-- factory:' markers")
    existing = find_checkpoint(list_comments(gh, repo, number))
    if existing is None:
        raise CommentError(f"issue #{number} has no checkpoint comment yet (S07 writes the "
                           f"first one); the {what} has nowhere to go")
    comment = existing[0]
    body = (comment.get("body") or "").replace("\r\n", "\n").rstrip()
    old = note_block(body, start, end)
    body = body.replace(old, block) if old else f"{body}\n\n{block}"
    if len(body) > MAX_BODY:
        raise CommentError(f"checkpoint body would be {len(body)} characters; GitHub's limit "
                           f"is {MAX_BODY}")
    updated = gh.api(f"repos/{repo}/issues/comments/{comment['id']}", method="PATCH",
                     json_body={"body": body})
    return Posted("updated", updated["id"], updated["html_url"], body)


def _carry(value: int | None, previous: CheckpointMarker | None, name: str) -> int:
    if value is not None:
        return value
    return getattr(previous, name) if previous is not None else 0


def _checked_body(marker, text: str) -> str:
    # The caller's text must not carry markers of its own: only this module adds them,
    # otherwise a reply could masquerade as a checkpoint (or quote one) and confuse
    # the state engine.
    if has_factory_marker(text):
        raise CommentError("the body must not contain '<!-- factory:' markers; "
                           "`factory.py comment` adds the marker itself")
    body = compose(marker, text)
    if len(body) > MAX_BODY:
        raise CommentError(f"comment body is {len(body)} characters; GitHub's limit is "
                           f"{MAX_BODY}")
    return body

