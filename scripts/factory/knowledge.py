"""The target's knowledge base, ``docs/factory/knowledge.md`` (T7.3): a durable record of
the stack, layout, conventions, commands, hotspots, architecture decisions and known risks,
kept across increments so S01 reuses it instead of rediscovering everything.

Station S01 is the only writer (K-A), and is itself the model, not this module: it reads
``knowledge check``'s result to see which sections (if any) must be rewritten, then writes
the file by hand, the same way it already writes ``01-codebase-analysis.md``. This module
never writes to the target; it only **checks**.

The file's first line is a ``factory:knowledge`` marker (``markers.py``) naming the commit
its sections were last checked against:

    <!-- factory:knowledge checked=<40-hex sha> -->

Its eight sections, as ``##`` headings, in this fixed order::

    Stack, Layout, Conventions, Commands, Hotspots, Architecture decisions,
    Known risks, Changes

A section is **stale** when something in its fixed scope changed since the recorded
commit (``staleness()``, pure):

* **Stack** and **Commands**: manifests, lockfiles, ``Makefile``, CI workflow files. Not
  ``.factory/config.json``: S00 and S01 write it themselves on the plan branch, so it would
  make every freshly written file stale at once (S01's Done check could never pass).
* **Conventions**: lint/format configuration, ``CLAUDE.md``, ``CONTRIBUTING*``,
  ``.editorconfig``.
* **Layout**: any top-level file or folder added or removed.
* **Hotspots** and **Known risks**: any change outside ``docs/factory/`` and ``.factory/``
  (the target's own risk surface, as opposed to the factory's planning artefacts).
* **Architecture decisions**: stale when a merged increment's ``03-architecture.md``
  is not linked from this section's text (by increment name).
* **Changes** is never flagged by a diff: S01 appends to it directly, every time.

**Fail-safe** (K-C): a missing file, a missing or malformed marker, an unresolvable commit,
or sections that are missing, duplicated or out of order make **every** section stale,
whatever the diff says.

``parse()``, ``well_formed()``, ``architecture_links()`` and ``staleness()`` are pure;
``collect()`` and ``check()`` do the (local, read-only) git I/O. Nothing here calls GitHub.
"""

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from factory import manifests
from factory.errors import GitError
from factory.git import Git
from factory.increments import is_increment
from factory.markers import KnowledgeMarker, find

KNOWLEDGE_FILE = Path("docs") / "factory" / "knowledge.md"
INCREMENTS_DIR = "docs/factory/increments"
SECTIONS = ("Stack", "Layout", "Conventions", "Commands", "Hotspots",
            "Architecture decisions", "Known risks", "Changes")

_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_ARCH_FILE = re.compile(rf"^{re.escape(INCREMENTS_DIR)}/([^/]+)/03-architecture\.md$")
_INCREMENT_NAME = re.compile(r"\b(\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*)\b")

# Beyond the dependency manifests and lockfiles manifests.py already knows across every
# stack (reused below, never duplicated here: T5.4 success criterion 8 keeps ecosystem
# names out of every file but discovery.py and manifests.py), a build file or CI workflow
# also changes what Stack or Commands records.
_STACK_COMMANDS_EXTRA = ("Makefile", "pom.xml", "build.gradle*")
_CONVENTIONS_GLOBS = (
    "CLAUDE.md", "CONTRIBUTING*", ".editorconfig", ".eslintrc*", ".prettierrc*",
    "ruff.toml", "pyproject.toml", ".flake8", "mypy.ini", ".stylelintrc*", "tslint.json",
    ".golangci*",
)


# ----------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class Diff:
    """What changed between the knowledge base's recorded commit and the ref being
    checked, as plain data (``collect()`` reads it; ``staleness()`` is pure over it)."""

    changed: frozenset[str] = frozenset()  # every path git diff reports, at either commit
    top_level_before: frozenset[str] = frozenset()
    top_level_after: frozenset[str] = frozenset()
    architecture_files: frozenset[str] = frozenset()  # increment names with 03-architecture.md


# ----------------------------------------------------------------------------- output


@dataclass(frozen=True)
class KnowledgeFile:
    """A parsed ``knowledge.md``. ``sections`` preserves heading order, so
    ``tuple(sections) == SECTIONS`` is the "present, once each, in order" check."""

    checked: str | None = None
    sections: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    missing: bool
    invalid: bool
    stale: tuple[str, ...] = ()
    checked: str | None = None
    reason: str | None = None  # why `invalid`; not otherwise used

    @property
    def ok(self) -> bool:
        return not self.missing and not self.invalid and not self.stale

    def to_dict(self) -> dict:
        if self.missing:
            status = "missing"
        elif self.invalid:
            status = "invalid"
        elif self.stale:
            status = "stale"
        else:
            status = "fresh"
        return {"status": status, "checked": self.checked, "stale": list(self.stale),
                "reason": self.reason, "ok": self.ok}


# ----------------------------------------------------------------------------- pure


def parse(text: str) -> KnowledgeFile:
    """The marker and the ``##`` sections of ``knowledge.md``'s text, in the order they
    appear. A heading seen again later keeps only its first body (so a duplicate cannot
    silently replace a section further down)."""
    marker = find(text, KnowledgeMarker)
    headings = list(_HEADING.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(headings):
        name = m[1].strip()
        if name in sections:
            continue
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        sections[name] = text[start:end].strip()
    return KnowledgeFile(marker.checked if marker else None, sections)


def well_formed(kf: KnowledgeFile) -> bool:
    """A readable marker, and exactly the eight sections, once each, in the fixed order."""
    return kf.checked is not None and tuple(kf.sections) == SECTIONS


def architecture_links(section_text: str) -> frozenset[str]:
    """The increment names (``NNN-slug``) mentioned in the "Architecture decisions"
    section's text, however they are written (a link, a bare name, a bullet)."""
    return frozenset(_INCREMENT_NAME.findall(section_text))


def staleness(sections: dict[str, str], diff: Diff) -> tuple[str, ...]:
    """Pure: which sections ``diff`` makes stale, in ``SECTIONS`` order. Assumes
    ``sections`` already passed ``well_formed()``; call only then (see ``check``)."""
    flagged: set[str] = set()
    if any(_is_stack_or_commands(p) for p in diff.changed):
        flagged |= {"Stack", "Commands"}
    if any(_matches_name(p, _CONVENTIONS_GLOBS) for p in diff.changed):
        flagged.add("Conventions")
    if diff.top_level_before != diff.top_level_after:
        flagged.add("Layout")
    if any(not _under_factory_docs(p) for p in diff.changed):
        flagged |= {"Hotspots", "Known risks"}
    linked = architecture_links(sections.get("Architecture decisions", ""))
    if diff.architecture_files - linked:
        flagged.add("Architecture decisions")
    return tuple(name for name in SECTIONS if name in flagged)


def _is_stack_or_commands(path: str) -> bool:
    if manifests.is_manifest(path) or manifests.is_lockfile(path):
        return True
    if path.startswith(".github/workflows/"):
        return True
    return _matches_name(path, _STACK_COMMANDS_EXTRA)


def _matches_name(path: str, globs: tuple[str, ...]) -> bool:
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(base, pattern) for pattern in globs)


def _under_factory_docs(path: str) -> bool:
    return path.startswith("docs/factory/") or path.startswith(".factory/")


# ----------------------------------------------------------------------------- I/O


def collect(git: Git, checked: str, ref: str) -> Diff:
    """What changed in the target between ``checked`` and ``ref``. Raises ``GitError`` if
    ``checked`` cannot be resolved (an unknown or unreadable commit).

    Top-level sets, for ``Layout``, are derived from the full tree with the factory's own
    paths removed first (``_under_factory_docs``): S01 committing ``docs/factory/`` for
    the first time must not, by itself, look like a new top-level ``docs`` folder.
    """
    # --no-renames: a rename lists both paths, whatever the user's diff.renames config, so
    # a manifest renamed to a non-manifest name still makes Stack and Commands stale.
    changed = frozenset(_lines(git.run(["diff", "--no-renames", "--name-only", checked,
                                        ref])))
    before = _ls_tree(git, checked)
    after = _ls_tree(git, ref)
    architecture_files = frozenset(
        m[1] for path in after if (m := _ARCH_FILE.match(path)) and is_increment(m[1]))
    return Diff(changed, _top_level(before), _top_level(after), architecture_files)


def _ls_tree(git: Git, ref: str) -> list[str]:
    return _lines(git.run(["ls-tree", "--name-only", "-r", ref]))


def _top_level(paths: list[str]) -> frozenset[str]:
    return frozenset(p.split("/", 1)[0] for p in paths if not _under_factory_docs(p))


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line]


def _read_file(git: Git, ref: str, path: str) -> str | None:
    """The file's text at ``ref``, or ``None`` if ``ref`` has no such path."""
    try:
        return git.run(["show", f"{ref}:{path}"])
    except GitError:
        return None


def check(git: Git, ref: str = "HEAD") -> CheckResult:
    """Read-only: is the target's ``knowledge.md`` fresh at ``ref``? Never writes anything."""
    text = _read_file(git, ref, KNOWLEDGE_FILE.as_posix())
    if text is None:
        return CheckResult(missing=True, invalid=False)
    kf = parse(text)
    if not well_formed(kf):
        return CheckResult(missing=False, invalid=True, checked=kf.checked,
                           reason="no factory:knowledge header, or its sections are "
                                  "missing, duplicated or out of order")
    try:
        diff = collect(git, kf.checked, ref)
    except GitError:
        return CheckResult(missing=False, invalid=True, checked=kf.checked,
                           reason=f"its recorded commit {kf.checked} could not be read")
    return CheckResult(missing=False, invalid=False, stale=staleness(kf.sections, diff),
                       checked=kf.checked)


def render(result: CheckResult) -> str:
    path = KNOWLEDGE_FILE.as_posix()
    if result.missing:
        return f"{path}: missing"
    if result.invalid:
        return f"{path}: invalid ({result.reason})"
    checked = result.checked[:7] if result.checked else "?"
    if result.stale:
        return f"{path}: stale ({checked}): " + ", ".join(result.stale)
    return f"{path}: fresh (checked {checked})"
