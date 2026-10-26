"""``factory.py plan check --increment <INC>`` (T7.4): lint a plan before the Planning PR.

S05 runs it after writing ``05-stories.md`` and embeds its output, unedited, in the
Planning PR. It reads the target's **working tree** only (no git, no GitHub):

* the increment's ``02-requirements.md`` and ``05-stories.md``;
* every increment's ``02-requirements.md``: an earlier increment's requirement bullets are
  the text of the requirements that are already Done;
* ``docs/factory/traceability.md``: a requirement is Done for this check when its row says
  ``Implemented``. A row reaches the default branch, which the plan branch starts from,
  only together with its merged story PR (S11), so no GitHub call is needed;
* ``.factory/config.json``: ``limits.max_diff_lines``.

**Problems** (each one fails the check, naming the file, the story or requirement, the
line where known, and the rule):

* the Story Contract, from ``stories.check`` (the format, 1–5 ACs, an ``Out of scope``
  section on every story, where ``None`` is valid, and ``Blocked by`` cycles);
* ``ac-form``: every AC reads ``Given …, when …, then …``;
* ``coverage``, both ways: every in-scope requirement of this increment is in some story's
  ``Traces to``, and every REQ a story traces to is an in-scope requirement of this
  increment, or an earlier one named under ``## Changed or retired requirements``. When
  a story breaks the contract, the first direction is not checked (a note says so);
* ``size``: the story's ``- Files:`` estimates (lockfiles left out, as Q7 does) add up to
  at most ``max_diff_lines``. A story without the bullet is a problem: its size cannot
  be checked, and it is never counted as zero;
* ``requirements``: no in-scope requirement, or one defined twice.

**Overlap** (a *potential* overlap, never a verdict that the work is duplicated). Each
in-scope requirement of this increment is scored against each Done requirement:

* A requirement's statement is its bullet's text without the ``(PRD §…):`` citation and
  without ``REQ-``/``STORY-`` IDs. Its *words* are the set of its letter-and-digit runs,
  case-folded, made singular by one rule (``-ies`` → ``-y``; else a final ``-s`` is dropped,
  except after ``s``, ``u`` or ``i``; only for words over 3 letters), less one-letter
  words, numbers and the English function words in ``STOPWORDS``. No domain words are
  listed anywhere: how common a word is comes from the Done requirements themselves.
* A word's weight is ``1 + ln((M + 1) / (d + 1))``, where ``M`` is the number of Done
  requirements compared and ``d`` how many of them use the word: the standard smoothed
  inverse document frequency (as scikit-learn computes it). Every word weighs at least 1,
  so a word every Done requirement uses still counts (with one Done requirement, the
  score is plain word containment); the fewer Done requirements use a word, the more it
  weighs, and a word none of them uses weighs the most.
* ``score(new, done)`` = the weight of the words both share ÷ the weight of all the new
  requirement's words, rounded to 3 decimals: the share of what the new requirement says
  that the Done one already says. It is 0 when the new requirement has no weight.
* ``score >= OVERLAP`` (0.5: at least half) is a **potential overlap**. It fails the check
  until this increment records the pair explicitly (``resolution``): an entry
  ``- <done>: changed by <new> (<how>)`` under ``## Changed or retired requirements``, or
  a question (a list item with ``?``) under ``## Open questions`` that names both IDs.
  Merely naming both IDs, as in "REQ-003 stays unchanged; REQ-022 is new", is not enough.
* ``NEAR <= score < OVERLAP`` (0.4) is **related**: reported for the reviewer, never failing.

Every candidate shows both statements and the shared words, so the reviewer sees why it
was flagged. The parsing and scoring are pure; ``collect`` does the reading.
"""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory import manifests
from factory import stories as stories_mod
from factory.config import load_config
from factory.errors import FactoryError
from factory.increments import INCREMENTS_DIR, REQUIREMENTS_FILE, increment_number, is_increment
from factory.issues import STORIES_FILE
from factory.status import TRACEABILITY, parse_traceability

SCHEMA = 1
OVERLAP = 0.5  # at least half of the new requirement's word weight is in one Done requirement
NEAR = 0.4  # within 0.1 of OVERLAP: reported as related, never failing
IMPLEMENTED = "Implemented"  # the traceability matrix's Status (templates/traceability.md)
OPEN_QUESTIONS = "Open questions"
CHANGED = "Changed or retired requirements"
OUT_OF_SCOPE = "Out of scope"
MAX_QUOTE = 160

# English function words only, never domain words (success criterion 8).
STOPWORDS = frozenset("""
a about after again all also an and any are as at be been before being both but by can
could did do does done each either else for from had has have having he her here his how
if in into is it its just may me might more most must my neither no nor not of off on once
one only onto or other our out over own per same shall she should so some such than that
the their them then there these they this those to under up us very via was we were what
when whenever where which while who whom whose why will with without would you your
""".split())

RULES = {
    "ac-form": "every AC reads `Given ..., when ..., then ...`",
    "coverage": "every in-scope REQ is traced by a story, and every traced REQ is one of "
                "this increment's or an earlier one named under Changed or retired requirements",
    "size": "the story's `- Files:` estimate is present and at most max_diff_lines",
    "requirements": "02-requirements.md defines each REQ once, at least one in scope",
}

_SECTION = re.compile(r"^##\s+(?P<name>.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_REQ_BULLET = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+\*\*(?P<id>REQ-\d{3,})\*\*\s*(?P<rest>.*)$")
_CITATION = re.compile(r"^(?:\(.*?\)\s*)?:\s*")  # `(PRD §…): ` or a bare `: `
_ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s")
_IDS = re.compile(r"\bREQ-\d{3,}\b")
_ID_LIST = r"REQ-\d{3,}(?:\s*(?:,|and)\s*REQ-\d{3,})*"
# `- REQ-005[, REQ-006]: changed by REQ-022[, REQ-023] (<how>)` (templates/README.md)
_CHANGED_ENTRY = re.compile(rf"^\s{{0,3}}(?:[-*+]|\d+[.)])\s+(?P<old>{_ID_LIST})\s*:\s*"
                            rf"changed\s+by\s+(?P<new>{_ID_LIST})\b", re.I)
_ID = re.compile(r"\b(?:REQ|STORY)-\d+\b")
_WORD = re.compile(r"[^\W_]+")
_GIVEN_WHEN_THEN = re.compile(r"^given\b.*?\bwhen\b.*?\bthen\b", re.I | re.S)


class PlanError(FactoryError):
    """The plan cannot be checked at all (no such increment, or a file is missing)."""


# ----------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Requirement:
    id: str
    statement: str  # the bullet's text without its `(PRD §…):` citation
    line: int
    increment: str


@dataclass(frozen=True)
class RequirementsDoc:
    """One ``02-requirements.md``: its in-scope requirement bullets and its sections."""

    increment: str
    defined: dict[str, Requirement]
    duplicates: tuple[tuple[str, int, int], ...]  # (REQ, first line, repeated line)
    sections: dict[str, list[tuple[int, str]]]  # case-folded `##` name -> lines


@dataclass(frozen=True)
class Problem:
    file: str
    subject: str | None  # STORY-### or REQ-###, or None for the whole file
    rule: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = self.file + (f" line {self.line}" if self.line is not None else "")
        if self.subject:
            where += f", {self.subject}"
        return f"{where} [{self.rule}]: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "subject": self.subject, "rule": self.rule,
                "message": self.message, "line": self.line}


@dataclass(frozen=True)
class StorySize:
    id: str
    acs: int
    estimate: int | None  # None: no `- Files:` bullet
    files: int
    lockfiles: tuple[str, ...]  # declared, but left out of the estimate

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "acs": self.acs, "estimate": self.estimate,
                "files": self.files, "lockfiles": list(self.lockfiles)}


@dataclass(frozen=True)
class Overlap:
    new: Requirement
    done: Requirement
    score: float
    shared: tuple[str, ...]  # heaviest first
    resolved_by: str | None  # where both IDs are named, e.g. "Open questions, line 74"

    @property
    def potential(self) -> bool:
        return self.score >= OVERLAP

    @property
    def unresolved(self) -> bool:
        return self.potential and self.resolved_by is None

    def to_dict(self) -> dict[str, Any]:
        return {"new": self.new.id, "done": self.done.id, "done_increment": self.done.increment,
                "score": self.score, "kind": "potential" if self.potential else "related",
                "shared": list(self.shared), "resolved_by": self.resolved_by,
                "new_statement": self.new.statement, "done_statement": self.done.statement}


@dataclass
class Result:
    increment: str
    max_diff_lines: int
    stories: list[StorySize] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    overlaps: list[Overlap] = field(default_factory=list)
    compared: int = 0  # Done requirements the new ones were scored against
    notes: list[str] = field(default_factory=list)

    @property
    def unresolved(self) -> list[Overlap]:
        return [o for o in self.overlaps if o.unresolved]

    @property
    def ok(self) -> bool:
        return not self.problems and not self.unresolved

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "increment": self.increment, "ok": self.ok,
                "max_diff_lines": self.max_diff_lines,
                "thresholds": {"overlap": OVERLAP, "near": NEAR},
                "stories": [s.to_dict() for s in self.stories],
                "problems": [p.to_dict() for p in self.problems],
                "compared": self.compared,
                "overlaps": [o.to_dict() for o in self.overlaps],
                "notes": list(self.notes)}


# ----------------------------------------------------------------------------- parsing


def parse_requirements(text: str, increment: str) -> RequirementsDoc:
    """The in-scope ``- **REQ-###**`` bullets (any ``##`` section but ``Out of scope``) and
    the lines of every ``##`` section. Headings and bullets inside code fences are content;
    an indented line continues the bullet above it."""
    defined: dict[str, Requirement] = {}
    duplicates: list[tuple[str, int, int]] = []
    sections: dict[str, list[tuple[int, str]]] = {}
    section: str | None = None
    current: list | None = None  # [id, line, statement] of the bullet being read
    fenced = False

    def finish() -> None:
        if current is None:
            return
        req, line, statement = current
        if req in defined:
            duplicates.append((req, defined[req].line, line))
        else:
            defined[req] = Requirement(req, " ".join(statement.split()), line, increment)

    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _SECTION.match(line)
        if heading:
            finish()
            current = None
            section = heading["name"].casefold()
            sections.setdefault(section, [])
            continue
        if not fenced and line.startswith("# "):  # the title: before any section
            finish()
            current, section = None, None
            continue
        if section is not None:
            sections[section].append((number, line))
        bullet = None if fenced else _REQ_BULLET.match(line)
        if bullet:
            finish()
            current = None
            if section != OUT_OF_SCOPE.casefold():
                current = [bullet["id"], number, _CITATION.sub("", bullet["rest"].strip(), 1)]
            continue
        if current is not None and line.strip() and line[:1].isspace():
            current[2] += " " + line.strip()
        elif current is not None:
            finish()
            current = None
    finish()
    return RequirementsDoc(increment, defined, tuple(duplicates), sections)


def words(text: str) -> frozenset[str]:
    """The comparable words of a statement (see the module docstring)."""
    found = set()
    for word in _WORD.findall(_ID.sub(" ", text).casefold()):
        if len(word) < 2 or word.isdigit() or word in STOPWORDS:
            continue
        found.add(_singular(word))
    return frozenset(found)


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def section_items(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """A section cut into items, as ``(first line, text)``: each list item with its indented
    continuation lines, and each paragraph. An unindented line after a list item starts a
    new item, so a paragraph can never lend its words (or its ``?``) to the item above it."""
    items: list[list] = []
    current: list | None = None
    in_list = False
    for number, text in lines:
        if not text.strip():
            current = None
        elif current is None or _ITEM.match(text) or (in_list and not text[:1].isspace()):
            current = [number, text.strip()]
            items.append(current)
            in_list = bool(_ITEM.match(text))
        else:
            current[1] += " " + text.strip()
    return [(number, text) for number, text in items]


# ----------------------------------------------------------------------------- scoring


def score_all(new: list[Requirement], done: list[Requirement]) -> list[Overlap]:
    """Every (new, done) pair scoring at least ``NEAR``, unresolved, sorted by new ID, then
    highest score, then done ID."""
    if not done:
        return []
    done_words = {d.id: words(d.statement) for d in done}
    frequency: dict[str, int] = {}
    for found in done_words.values():
        for word in found:
            frequency[word] = frequency.get(word, 0) + 1
    m = len(done)

    def weight(word: str) -> float:
        return 1 + math.log((m + 1) / (frequency.get(word, 0) + 1))

    found: list[Overlap] = []
    for requirement in new:
        mine = words(requirement.statement)
        total = sum(weight(w) for w in sorted(mine))
        for other in done:
            shared = mine & done_words[other.id]
            score = round(sum(weight(w) for w in sorted(shared)) / total, 3) if total else 0.0
            if score >= NEAR:
                heaviest = tuple(sorted(shared, key=lambda w: (-weight(w), w)))
                found.append(Overlap(requirement, other, score, heaviest, None))
    return sorted(found, key=lambda o: (_id_number(o.new.id), -o.score, _id_number(o.done.id)))


def resolution(doc: RequirementsDoc, new: str, done: str) -> str | None:
    """Where this increment explicitly records the pair. Naming both IDs is not enough:

    * ``## Changed or retired requirements``: a list item in the documented form
      (templates/README.md) ``- <done>[, …]: changed by <new>[, …] (<how>)``, the earlier
      requirement first;
    * ``## Open questions``: a list item that names both IDs and asks a question (``?``).
    """
    for number, text in section_items(doc.sections.get(CHANGED.casefold(), [])):
        entry = _CHANGED_ENTRY.match(text)
        if entry and done in _IDS.findall(entry["old"]) and new in _IDS.findall(entry["new"]):
            return f"{CHANGED}, line {number}"
    both = (re.compile(rf"\b{re.escape(new)}\b"), re.compile(rf"\b{re.escape(done)}\b"))
    for number, text in section_items(doc.sections.get(OPEN_QUESTIONS.casefold(), [])):
        if _ITEM.match(text) and "?" in text and all(p.search(text) for p in both):
            return f"{OPEN_QUESTIONS}, line {number}"
    return None


def _id_number(req: str) -> int:
    return int(req.split("-", 1)[1])


# ----------------------------------------------------------------------------- the check


def check_plan(*, increment: str, requirements: dict[str, str], stories_text: str,
               traceability: str | None, max_diff_lines: int) -> Result:
    """The whole check, pure. ``requirements`` maps every increment folder (this one
    included) to its ``02-requirements.md`` text."""
    result = Result(increment, max_diff_lines)
    req_file = f"{increment}/{REQUIREMENTS_FILE}"
    stories_file = f"{increment}/{STORIES_FILE}"
    doc = parse_requirements(requirements[increment], increment)

    for req, first, again in doc.duplicates:
        result.problems.append(Problem(req_file, req, "requirements",
                                       f"{req} is defined on line {first} and again", again))
    if not doc.defined:
        result.problems.append(Problem(req_file, None, "requirements",
                                       "no `- **REQ-###**` requirement bullet outside "
                                       f"`## {OUT_OF_SCOPE}`"))

    parsed, contract = stories_mod.check(stories_text)
    result.problems += [Problem(stories_file, p.story, p.rule, p.message, p.line)
                        for p in contract]
    for story in parsed:
        result.stories.append(_size(story))
        _ac_form(story, stories_file, result)
        _size_problem(story, stories_file, max_diff_lines, result)
    _coverage(doc, parsed, bool(contract), req_file, stories_file, result)
    _overlaps(doc, requirements, traceability, result)
    return result


def _ac_form(story: stories_mod.Story, file: str, result: Result) -> None:
    bad = [f"AC{n}" for n, text in enumerate(story.acceptance_criteria, 1)
           if not _GIVEN_WHEN_THEN.match(text)]
    if bad:
        result.problems.append(Problem(file, story.id, "ac-form", f"{', '.join(bad)} "
                                       "is not in the form `Given ..., when ..., then ...`",
                                       story.line))


def _size(story: stories_mod.Story) -> StorySize:
    if story.files is None:
        return StorySize(story.id, len(story.acceptance_criteria), None, 0, ())
    counted = [lines for path, lines in story.files if not manifests.is_lockfile(path)]
    locks = tuple(path for path, _ in story.files if manifests.is_lockfile(path))
    return StorySize(story.id, len(story.acceptance_criteria), sum(counted), len(story.files),
                     locks)


def _size_problem(story: stories_mod.Story, file: str, limit: int, result: Result) -> None:
    size = result.stories[-1]
    if size.estimate is None:
        result.problems.append(Problem(
            file, story.id, "size", "no `- Files:` estimate, so its size cannot be checked "
            f"against max_diff_lines ({limit}); add `- Files: <path> (~<lines>), ...` after "
            "`- Milestone:`", story.line))
    elif size.estimate > limit:
        result.problems.append(Problem(
            file, story.id, "size", f"the estimate is {size.estimate} changed lines in "
            f"{size.files} file(s), over max_diff_lines ({limit}); split the story",
            story.line))


def _coverage(doc: RequirementsDoc, parsed: list[stories_mod.Story], contract_broken: bool,
              req_file: str, stories_file: str, result: Result) -> None:
    changed = " ".join(text for _, text in doc.sections.get(CHANGED.casefold(), []))
    out_of_scope = " ".join(text for _, text in doc.sections.get(OUT_OF_SCOPE.casefold(), []))
    for story in parsed:
        for req in story.traces_to:
            if req in doc.defined or re.search(rf"\b{req}\b", changed):
                continue
            where = (f"it is listed under `## {OUT_OF_SCOPE}`"
                     if re.search(rf"\b{req}\b", out_of_scope) else
                     f"it is not a `- **{req}**` bullet of {REQUIREMENTS_FILE}, nor named "
                     f"under `## {CHANGED}`")
            result.problems.append(Problem(stories_file, story.id, "coverage",
                                           f"traces to {req}, but {where}", story.line))
    if contract_broken:
        result.notes.append("Whether every requirement is traced by a story was not checked: "
                            f"fix the {STORIES_FILE} problems first.")
        return
    traced = {req for story in parsed for req in story.traces_to}
    for req in sorted(doc.defined, key=_id_number):
        if req not in traced:
            result.problems.append(Problem(req_file, req, "coverage", f"{req} is not in any "
                                           "story's `Traces to`", doc.defined[req].line))


def _overlaps(doc: RequirementsDoc, requirements: dict[str, str], traceability: str | None,
              result: Result) -> None:
    if traceability is None:
        result.notes.append(f"No {TRACEABILITY}: there are no Done requirements to compare.")
        return
    implemented = {req for req, status, _ in parse_traceability(traceability)
                   if status == IMPLEMENTED}
    current = increment_number(doc.increment)
    definitions: dict[str, Requirement] = {}
    elsewhere: set[str] = set()  # defined by this increment or a later one
    for name in sorted(requirements):
        parsed = parse_requirements(requirements[name], name)
        if increment_number(name) < current:
            for req, requirement in parsed.defined.items():
                definitions.setdefault(req, requirement)
        else:
            elsewhere |= set(parsed.defined)
    done = [definitions[req] for req in sorted(implemented, key=_id_number)
            if req in definitions]
    missing = sorted((implemented - set(definitions)) - elsewhere, key=_id_number)
    if missing:
        result.notes.append(f"Implemented in {TRACEABILITY}, but defined by no earlier "
                            f"increment's {REQUIREMENTS_FILE}, so not compared: "
                            + ", ".join(missing) + ".")
    result.compared = len(done)
    new = [doc.defined[req] for req in sorted(doc.defined, key=_id_number)]
    for requirement in new:
        if not words(requirement.statement):
            result.notes.append(f"{requirement.id} has no words to compare; check it for "
                                "overlap by hand.")
    result.overlaps = [Overlap(o.new, o.done, o.score, o.shared,
                               resolution(doc, o.new.id, o.done.id) if o.potential else None)
                       for o in score_all(new, done)]


# ----------------------------------------------------------------------------- I/O


def collect(target: Path, increment: str) -> Result:
    """Read the plan from the target's working tree and check it."""
    if not is_increment(increment):
        raise PlanError(f"{increment!r} is not an increment folder name (NNN-slug)")
    root = Path(target) / INCREMENTS_DIR
    folder = root / increment
    if not folder.is_dir():
        raise PlanError(f"no increment folder {(INCREMENTS_DIR / increment).as_posix()}")
    requirements: dict[str, str] = {}
    for path in sorted(root.iterdir()):
        if path.is_dir() and is_increment(path.name) and (path / REQUIREMENTS_FILE).is_file():
            requirements[path.name] = _read(path / REQUIREMENTS_FILE)
    for name in (REQUIREMENTS_FILE, STORIES_FILE):
        if not (folder / name).is_file():
            raise PlanError(f"{(INCREMENTS_DIR / increment / name).as_posix()} not found")
    matrix = Path(target) / TRACEABILITY
    return check_plan(increment=increment, requirements=requirements,
                      stories_text=_read(folder / STORIES_FILE),
                      traceability=_read(matrix) if matrix.is_file() else None,
                      max_diff_lines=load_config(target).limits.max_diff_lines)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise PlanError(f"cannot read {path}: {err}") from None


# ----------------------------------------------------------------------------- output


def render(result: Result) -> str:
    unresolved = len(result.unresolved)
    if result.ok:
        verdict = "PASS"
    else:
        verdict = f"FAIL: {len(result.problems)} problem(s), {unresolved} unresolved overlap(s)"
    lines = [f"Plan check: {result.increment}", f"Result: {verdict}", "",
             f"Stories (max_diff_lines {result.max_diff_lines}):"]
    for s in result.stories:
        size = ("no Files estimate" if s.estimate is None else
                f"estimate {s.estimate} changed lines in {s.files} file(s)")
        if s.lockfiles:
            size += f" (lockfiles not counted: {', '.join(s.lockfiles)})"
        lines.append(f"- {s.id}: {s.acs} AC(s), {size}")
    if not result.stories:
        lines.append("- None parsed")
    lines += ["", "Problems:"]
    lines += [f"- {p}" for p in result.problems] or ["- None"]
    lines += ["", f"Overlap with Done requirements ({result.compared} compared; a potential "
                  f"overlap from score {OVERLAP:.3f}, related from {NEAR:.3f}):"]
    for o in result.overlaps:
        if o.potential:
            state = f"resolved in {o.resolved_by}" if o.resolved_by else "UNRESOLVED"
            kind = f"potential overlap, {state}"
        else:
            kind = "related, reported for the reviewer, not failing"
        lines += [f"- {o.new.id} ~ {o.done.id} ({o.done.increment}): score {o.score:.3f}, {kind}",
                  f"  shared words: {', '.join(o.shared)}",
                  f"  {o.new.id}: {_quote(o.new.statement)}",
                  f"  {o.done.id}: {_quote(o.done.statement)}"]
        if o.unresolved:
            lines.append(f"  To resolve: add a question to `## {OPEN_QUESTIONS}` in "
                         f"{REQUIREMENTS_FILE}, a list item that names {o.new.id} and "
                         f"{o.done.id} and asks it (for example: Is {o.new.id} new work, or "
                         f"does {o.done.id} already cover it?), or stop and ask the human "
                         "(rule H6) if it restates finished work. Naming both IDs without "
                         "a question does not resolve it.")
    if not result.overlaps:
        lines.append(f"- None scoring {NEAR:.3f} or more")
    if result.notes:
        lines += ["", "Notes:"] + [f"- {n}" for n in result.notes]
    lines += ["", "Score: the share of the new requirement's word weight that the Done one "
                  "also has. Words are case-folded and singular, without English function "
                  "words; a word's weight is 1 + ln((M+1)/(d+1)), M = Done requirements "
                  "compared, d = how many of them use it."]
    return "\n".join(lines)


def _quote(text: str) -> str:
    return text if len(text) <= MAX_QUOTE else text[:MAX_QUOTE - 3].rstrip() + "..."
