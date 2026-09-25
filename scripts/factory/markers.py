"""Machine-readable ``<!-- factory:* -->`` markers (architecture §5.5).

The state engine finds its GitHub objects by these markers, never by titles. Every
comment the factory posts carries one, which is how its comments are told apart from
the human's in single-account mode (D5).

    <!-- factory:story id=STORY-007 increment=001-initial -->
    <!-- factory:planning increment=001-initial -->
    <!-- factory:pr story=STORY-007 -->
    <!-- factory:checkpoint {"station":"S09","next":"S10",...} -->
    <!-- factory:reply -->
    <!-- factory:reply to=IC_kwDOabc -->     (answers one feedback item, T4.2)

``build`` is strict and raises ``ValueError`` on bad input (that is a factory bug).
``parse_all`` / ``find`` are tolerant of whitespace, line breaks and CRLF, and silently
ignore anything malformed: parsing never raises on input text. Whether a marker can be
*trusted* (e.g. a human pasting a fake one) is decided later, in ``signals.py`` (T1.7).
"""

import json
import re
from dataclasses import MISSING, asdict, dataclass, fields
from datetime import datetime
from typing import ClassVar, TypeVar

_STORY_ID = re.compile(r"^STORY-\d{3,}$")
_INCREMENT = re.compile(r"^\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
_STATION = re.compile(r"^S\d{2}b?$")
_NEXT = re.compile(r"^(?:S\d{2}b?|GATE_[ABC])$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_COMMENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")  # REST ids are numbers, GraphQL ids not

# One marker: "<!--", optional whitespace, "factory:<kind>", a body that never contains
# another comment opener or closer, then "-->". Excluding "<!--" from the body means an
# unterminated marker cannot swallow a valid marker that follows it.
_MARKER = re.compile(
    r"<!--\s*factory:(?P<kind>[a-z]+)(?P<body>(?:(?!<!--|-->).)*?)\s*-->",
    re.DOTALL,
)
_ANY_FACTORY_MARKER = re.compile(r"<!--\s*factory:", re.IGNORECASE)
_ATTR = re.compile(r"^(?P<key>[a-z_]+)=(?P<value>[A-Za-z0-9._-]+)$")
_MAX_BODY = 4096  # real markers are < 1 KB; anything larger is ignored, not parsed


def _check(pattern: re.Pattern, value: object, name: str) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(f"invalid {name}: {value!r}")


@dataclass(frozen=True)
class StoryMarker:
    """In a story issue's body."""

    KIND: ClassVar[str] = "story"
    id: str
    increment: str

    def __post_init__(self):
        _check(_STORY_ID, self.id, "story id")
        _check(_INCREMENT, self.increment, "increment")


@dataclass(frozen=True)
class PlanningMarker:
    """In a Planning PR's body."""

    KIND: ClassVar[str] = "planning"
    increment: str

    def __post_init__(self):
        _check(_INCREMENT, self.increment, "increment")


@dataclass(frozen=True)
class PrMarker:
    """In a story PR's body."""

    KIND: ClassVar[str] = "pr"
    story: str

    def __post_init__(self):
        _check(_STORY_ID, self.story, "story id")


@dataclass(frozen=True)
class CheckpointMarker:
    """In the single checkpoint comment on a story issue (edited in place)."""

    KIND: ClassVar[str] = "checkpoint"
    station: str
    next: str
    branch: str
    sha: str
    fix_attempts: int
    review_round: int
    ts: str

    def __post_init__(self):
        _check(_STATION, self.station, "station")
        _check(_NEXT, self.next, "next station")
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise ValueError(f"invalid branch: {self.branch!r}")
        _check(_SHA, self.sha, "commit sha")
        for name in ("fix_attempts", "review_round"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid {name}: {value!r}")
        if not isinstance(self.ts, str):
            raise ValueError(f"invalid ts: {self.ts!r}")
        try:
            datetime.fromisoformat(self.ts)
        except ValueError:
            raise ValueError(f"invalid ts: {self.ts!r}") from None


@dataclass(frozen=True)
class ReplyMarker:
    """On every other comment or reply the factory posts.

    ``to`` is the id of the human comment this reply answers (a rework reply, T4.2). A
    reply without ``to`` closes a review round (architecture §7.2).
    """

    KIND: ClassVar[str] = "reply"
    to: str | None = None

    def __post_init__(self):
        if self.to is not None:
            _check(_COMMENT_ID, self.to, "comment id")


Marker = StoryMarker | PlanningMarker | PrMarker | CheckpointMarker | ReplyMarker
_ATTR_KINDS = {cls.KIND: cls for cls in (StoryMarker, PlanningMarker, PrMarker, ReplyMarker)}


def build(marker: Marker) -> str:
    """The marker as an HTML comment (invisible when GitHub renders it)."""
    if isinstance(marker, CheckpointMarker):
        payload = json.dumps(asdict(marker), separators=(",", ":"))
        # Escape characters that could close or open the comment (a branch name may
        # legally contain ">"). The result is still valid JSON.
        payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
        return f"<!-- factory:checkpoint {payload} -->"
    if type(marker) in _ATTR_KINDS.values():
        attrs = "".join(f" {f.name}={getattr(marker, f.name)}" for f in fields(marker)
                        if getattr(marker, f.name) is not None)  # optional and unset
        return f"<!-- factory:{marker.KIND}{attrs} -->"
    raise TypeError(f"not a factory marker: {marker!r}")


def parse_all(text: str | None) -> list[Marker]:
    """Every well-formed marker in ``text``, in order. Malformed markers are skipped."""
    if not text:
        return []
    found: list[Marker] = []
    for match in _MARKER.finditer(text):
        marker = _parse_one(match["kind"], match["body"])
        if marker is not None:
            found.append(marker)
    return found


M = TypeVar("M")


def find(text: str | None, cls: type[M]) -> M | None:
    """The first well-formed marker of type ``cls`` in ``text``, or ``None``."""
    return next((m for m in parse_all(text) if isinstance(m, cls)), None)


def has_factory_marker(text: str | None) -> bool:
    """True if ``text`` contains anything that *starts* like a factory marker.

    Deliberately looser than ``parse_all``: even a malformed marker counts, so text is
    never mistaken for human feedback just because its marker is broken.
    """
    return bool(text) and bool(_ANY_FACTORY_MARKER.search(text))


def _parse_one(kind: str, body: str) -> Marker | None:
    body = body.strip()
    if len(body) > _MAX_BODY:
        return None
    try:
        if kind == "checkpoint":
            data = json.loads(body)
            if not isinstance(data, dict):
                return None
            names = [f.name for f in fields(CheckpointMarker)]
            if not all(name in data for name in names):
                return None
            # Unknown keys are ignored so a newer factory's checkpoints stay readable.
            return CheckpointMarker(**{name: data[name] for name in names})
        cls = _ATTR_KINDS.get(kind)
        if cls is None:
            return None
        attrs: dict[str, str] = {}
        for token in body.split():
            match = _ATTR.match(token)
            if match is None or match["key"] in attrs:
                return None
            attrs[match["key"]] = match["value"]
        required = {f.name for f in fields(cls) if f.default is MISSING}
        if not required <= set(attrs) <= {f.name for f in fields(cls)}:
            return None
        return cls(**attrs)
    except (ValueError, TypeError, RecursionError):
        return None
