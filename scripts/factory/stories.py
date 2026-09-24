"""Parse ``05-stories.md`` and validate it against the Story Contract (T2.2).

The format is strict, so ``issues sync`` never has to guess (architecture §5.4)::

    ### STORY-007: Add due date to tasks
    - Traces to: REQ-003, REQ-007
    - Blocked by: STORY-005            (or "None")
    - Milestone: M2
    #### Story
    As a user, I want … so that ….
    #### Acceptance criteria
    - AC1: Given …, when …, then ….
    - AC2: …
    #### Out of scope
    - …                                (or "None")
    #### Technical notes
    …
    #### Test plan
    - Unit: …

Rules:

* Anything before the first story, and under ``#``/``##`` headings (e.g. one per
  milestone), is free text and is ignored. Every ``###`` heading must be a story heading.
  Headings inside fenced code blocks are content.
* The three metadata bullets come straight after the heading, each exactly once.
* The five ``####`` sections are all required, in this order, and none may be empty
  (write ``None``). Deeper headings inside a section are content.
* 1–5 acceptance criteria, numbered AC1, AC2, … in order. An indented line continues the
  AC above it.
* ``Blocked by`` uses STORY IDs, never issue numbers; ``issues sync`` translates them.
  A dependency on a story outside this file must already have an issue.
* No story may contain a ``<!-- factory:`` marker: only the factory adds markers.

Every problem is reported, each naming the story, the line and the rule it broke
(``RULES``). Parsing is pure: no I/O.
"""

import re
from dataclasses import dataclass

from factory.errors import FactoryError
from factory.markers import has_factory_marker

MIN_ACS, MAX_ACS = 1, 5
MAX_TITLE = 200  # the issue title is "STORY-###: <title>"; GitHub allows 256
SECTIONS = ("Story", "Acceptance criteria", "Out of scope", "Technical notes", "Test plan")
METADATA = ("Traces to", "Blocked by", "Milestone")

# Rule names used in problems (and in their messages).
RULES = {
    "no-stories": "the file must contain at least one story",
    "heading": "a story starts with `### STORY-###: <title>`",
    "duplicate-id": "each STORY ID appears once",
    "metadata": "Traces to, Blocked by and Milestone bullets, each once, before the sections",
    "traces-to": "a story traces to one or more REQ-### IDs",
    "blocked-by": "Blocked by is `None` or STORY-### IDs",
    "milestone": "Milestone is M<number>",
    "sections": f"the sections are {', '.join(SECTIONS)}, in that order, none empty",
    "acceptance-criteria": f"{MIN_ACS}–{MAX_ACS} ACs, `- AC<n>: …`, numbered from AC1",
    "markers": "stories must not contain `<!-- factory:` markers",
    "dependency-cycle": "dependencies must not form a cycle",
    "unknown-dependency": "every Blocked by story exists in this file or already has an issue",
    "id-reused": "STORY IDs are never reused across increments",
}

STORY_ID = re.compile(r"^STORY-\d{3,}$")
_REQ_ID = re.compile(r"^REQ-\d{3,}$")
_MILESTONE = re.compile(r"^M\d+$")
_STORY_HEADING = re.compile(r"^###\s+(?P<id>STORY-\d{3,})\s*:\s*(?P<title>.*?)\s*$")
_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$")
_BULLET = re.compile(r"^[-*]\s+(?P<key>[A-Za-z][A-Za-z ]*?)\s*:\s*(?P<value>.*?)\s*$")
_AC = re.compile(r"^[-*]\s+(?:\[[ xX]\]\s+)?AC(?P<n>\d+)\s*[:.]\s*(?P<text>.*?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Problem:
    story: str | None  # None for a file-level problem
    rule: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = self.story or "file"
        if self.line is not None:
            where += f" (line {self.line})"
        return f"{where} [{self.rule}]: {self.message}"


class StoriesError(FactoryError):
    """``05-stories.md`` breaks the format or the Story Contract. Lists every problem."""

    def __init__(self, source: str, problems: list[Problem]):
        self.source = source
        self.problems = list(problems)
        bullet = "\n  - "
        super().__init__(f"{source} does not meet the story contract "
                         f"({len(problems)} problem(s)):{bullet}"
                         + bullet.join(str(p) for p in problems))


@dataclass(frozen=True)
class Story:
    id: str
    title: str
    traces_to: tuple[str, ...]
    blocked_by: tuple[str, ...]  # STORY IDs
    milestone: str
    story: str
    acceptance_criteria: tuple[str, ...]  # AC texts, AC1 first
    out_of_scope: str
    technical_notes: str
    test_plan: str
    line: int = 0

    @property
    def issue_title(self) -> str:
        return f"{self.id}: {self.title}"


def parse(text: str, source: str = "05-stories.md") -> list[Story]:
    """Parse and validate. Returns the stories in file order, or raises ``StoriesError``."""
    problems: list[Problem] = []
    blocks = _split(text, problems)
    stories: list[Story] = []
    seen: dict[str, int] = {}
    for story_id, title, line, body in blocks:
        if story_id in seen:
            problems.append(Problem(story_id, "duplicate-id",
                                    f"{story_id} is already used on line {seen[story_id]}", line))
            continue
        seen[story_id] = line
        story = _parse_story(story_id, title, line, body, problems)
        if story is not None:
            stories.append(story)
    if not blocks and not problems:
        problems.append(Problem(None, "no-stories", "no `### STORY-###: <title>` heading found"))
    problems += dependency_cycles(stories)
    if problems:
        raise StoriesError(source, problems)
    return stories


def dependency_cycles(stories: list[Story]) -> list[Problem]:
    """A problem for each story that is part of a dependency cycle within the file."""
    graph = {s.id: [d for d in s.blocked_by] for s in stories}
    lines = {s.id: s.line for s in stories}
    problems: list[Problem] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    reported: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        path.append(node)
        for dep in graph[node]:
            if dep not in graph:
                continue  # outside this file: checked by issues sync
            if state.get(dep) == 1:
                cycle = path[path.index(dep):]
                key = min(cycle)
                if key not in reported:
                    reported.add(key)
                    problems.append(Problem(key, "dependency-cycle", " → ".join(
                        [*cycle, dep]) + " can never be unblocked", lines[key]))
            elif dep not in state:
                visit(dep, path)
        path.pop()
        state[node] = 2

    for story in stories:
        if story.id not in state:
            visit(story.id, [])
    return problems


# ----------------------------------------------------------------------------- internals


def _split(text: str, problems: list[Problem]) -> list[tuple[str, str, int, list[tuple[int, str]]]]:
    """Cut the file into story blocks: (id, title, heading line, [(line no., text)])."""
    blocks: list[tuple[str, str, int, list[tuple[int, str]]]] = []
    current: list[tuple[int, str]] | None = None
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _HEADING.match(line)
        if heading and len(heading["hashes"]) <= 3:
            current = None
            if len(heading["hashes"]) == 3:
                match = _STORY_HEADING.match(line)
                if match is None:
                    problems.append(Problem(None, "heading", f"{line.strip()!r}: level-3 "
                                            "headings are reserved for stories, written "
                                            "`### STORY-###: <title>`", number))
                    continue
                current = []
                blocks.append((match["id"], match["title"], number, current))
            continue
        if current is not None:
            current.append((number, line))
    return blocks


def _parse_story(story_id: str, title: str, line: int, body: list[tuple[int, str]],
                 problems: list[Problem]) -> Story | None:
    start = len(problems)

    def problem(rule: str, message: str, at: int | None = line) -> None:
        problems.append(Problem(story_id, rule, message, at))

    if not title:
        problem("heading", "the heading has no title after the colon")
    elif len(title) > MAX_TITLE:
        problem("heading", f"the title is {len(title)} characters; the limit is {MAX_TITLE}")
    if has_factory_marker(title) or any(has_factory_marker(text) for _, text in body):
        problem("markers", "remove the `<!-- factory:` marker; only the factory adds markers")

    # Metadata bullets, then #### sections.
    metadata: dict[str, tuple[str, int]] = {}
    sections: dict[str, tuple[int, list[tuple[int, str]]]] = {}
    order: list[str] = []
    current: list[tuple[int, str]] | None = None
    fenced = False
    for number, text in body:
        if _FENCE.match(text):
            fenced = not fenced
        heading = None if fenced else _HEADING.match(text)
        if heading and len(heading["hashes"]) == 4:
            name = _canonical(heading["text"], SECTIONS)
            if name is None:
                problem("sections", f"unknown section {heading['text']!r} (expected one of: "
                        f"{', '.join(SECTIONS)})", number)
                current = []  # swallow its content
            elif name in sections:
                problem("sections", f"section {name!r} appears twice", number)
                current = []
            else:
                current = []
                sections[name] = (number, current)
                order.append(name)
            continue
        if current is not None:
            current.append((number, text))
        elif text.strip():
            bullet = _BULLET.match(text.strip())
            key = _canonical(bullet["key"], METADATA) if bullet else None
            if key is None:
                problem("metadata", f"{text.strip()!r} is not one of the bullets "
                        f"{', '.join(f'`- {k}: …`' for k in METADATA)}", number)
            elif key in metadata:
                problem("metadata", f"`{key}` appears twice", number)
            else:
                metadata[key] = (bullet["value"], number)

    for key in METADATA:
        if key not in metadata:
            problem("metadata", f"missing the `- {key}: …` bullet")
    traces = _ids(metadata.get("Traces to"), _REQ_ID, "traces-to", "REQ-###", problem,
                  allow_none=False)
    blocked = _ids(metadata.get("Blocked by"), STORY_ID, "blocked-by", "STORY-###", problem,
                   allow_none=True)
    if story_id in blocked:
        problem("blocked-by", "a story cannot be blocked by itself",
                metadata["Blocked by"][1])
    milestone = ""
    if "Milestone" in metadata:
        milestone, at = metadata["Milestone"]
        if not _MILESTONE.match(milestone):
            problem("milestone", f"{milestone!r} is not a milestone like `M1`", at)

    for name in SECTIONS:
        if name not in sections:
            problem("sections", f"missing the `#### {name}` section")
    present = [s for s in SECTIONS if s in sections]
    if order != present:
        problem("sections", f"sections are out of order: {', '.join(order)} (expected "
                f"{', '.join(present)})")
    texts = {}
    for name, (at, lines) in sections.items():
        texts[name] = "\n".join(t for _, t in lines).strip()
        if not texts[name]:
            problem("sections", f"section {name!r} is empty (write `None` if there is "
                    "nothing to say)", at)

    acs = _acceptance_criteria(sections.get("Acceptance criteria"), problem)

    if len(problems) > start:
        return None
    return Story(
        id=story_id, title=title, traces_to=traces, blocked_by=blocked, milestone=milestone,
        story=texts["Story"], acceptance_criteria=acs, out_of_scope=texts["Out of scope"],
        technical_notes=texts["Technical notes"], test_plan=texts["Test plan"], line=line)


def _canonical(name: str, allowed: tuple[str, ...]) -> str | None:
    wanted = " ".join(name.split()).lower()
    return next((a for a in allowed if a.lower() == wanted), None)


def _ids(entry, pattern, rule, form, problem, *, allow_none) -> tuple[str, ...]:
    if entry is None:
        return ()
    value, at = entry
    if allow_none and value.lower() == "none":
        return ()
    items = [item.strip() for item in value.split(",")]
    if not value or any(not item for item in items):
        problem(rule, f"{value!r} must be a comma-separated list of {form} IDs"
                + (" or `None`" if allow_none else ""), at)
        return ()
    bad = [item for item in items if not pattern.match(item)]
    if bad:
        hint = " (use STORY IDs, not issue numbers)" if any(b.startswith("#") for b in bad) else ""
        problem(rule, f"not a {form} ID: {', '.join(bad)}{hint}", at)
        return ()
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        problem(rule, f"listed twice: {', '.join(duplicates)}", at)
    return tuple(dict.fromkeys(items))


def _acceptance_criteria(section, problem) -> tuple[str, ...]:
    if section is None:
        return ()
    _, lines = section
    acs: list[tuple[int, int, str]] = []  # (number, line, text)
    for number, text in lines:
        if not text.strip():
            continue
        match = _AC.match(text)
        if match:
            acs.append((int(match["n"]), number, match["text"]))
        elif text[:1].isspace() and acs:
            n, at, previous = acs[-1]
            acs[-1] = (n, at, f"{previous} {text.strip()}")
        else:
            problem("acceptance-criteria", f"{text.strip()!r} is not an acceptance "
                    "criterion; write `- AC<n>: …` (indent a line to continue one)", number)
            return ()
    if not MIN_ACS <= len(acs) <= MAX_ACS:
        problem("acceptance-criteria", f"has {len(acs)} acceptance criteria; the story "
                f"contract allows {MIN_ACS}–{MAX_ACS} (split the story if it needs more)",
                lines[0][0] if lines else None)
        return ()
    numbers = [n for n, _, _ in acs]
    if numbers != list(range(1, len(acs) + 1)):
        problem("acceptance-criteria", "ACs must be numbered AC1, AC2, … in order; found "
                + ", ".join(f"AC{n}" for n in numbers), acs[0][1])
        return ()
    empty = [f"AC{n}" for n, _, text in acs if not text]
    if empty:
        problem("acceptance-criteria", f"{', '.join(empty)} has no text", acs[0][1])
        return ()
    return tuple(text for _, _, text in acs)
