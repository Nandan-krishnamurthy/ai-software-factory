"""``factory.py trace <file>:<line>``: from a line of code to the PRD section it serves, in
one command (T6.4; requirements §11, success criterion 6). Read-only.

Each hop is found from the previous one, never by searching:

1. ``git blame`` of the line at ``--ref`` (default ``HEAD``) names the commit that last
   changed it.
2. The PR that brought that commit in. GitHub's commit-to-PR API
   (``repos/<R>/commits/<sha>/pulls``) knows squash, rebase and merge-commit merges. If it
   lists no merged PR, a deterministic fallback for merge commits: the first
   ``Merge pull request #<P>`` commit on the ancestry path from the commit to ``--ref``
   that brought it in through its second parent.
3. The PR body's ``Closes #<I>``.
4. The issue's ``factory:story`` marker (story and increment) and its **Traces to** REQs.
5. Each REQ's definition, ``- **REQ-###** (PRD §<section>, …): …``, in an increment's
   ``02-requirements.md`` (the story's own increment first).
6. Each cited section in that increment's ``00-prd.md``: the heading it names (and the line
   under it that the citation points at, such as ``FR-001``), or, in a PRD without
   headings, the line that is its text. Then the REQ's row in
   ``docs/factory/traceability.md``.

Files are read from git at ``--ref``, so every link points at exactly the text that was
traced. The result also gives the command's own elapsed time.

The parsers and ``match_prd`` are pure; ``trace`` does the I/O.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from factory.errors import FactoryError, GhError, GitError
from factory.gh import Gh
from factory.git import Git
from factory.markers import StoryMarker, find

INCREMENTS = "docs/factory/increments"
TRACEABILITY = "docs/factory/traceability.md"
REQUIREMENTS = "02-requirements.md"
PRD = "00-prd.md"
API = "the GitHub commit-to-PR API"
MERGE_COMMIT = "the merge commit's subject"

_SPEC = re.compile(r"^(?P<path>.+):(?P<line>\d+)$")
_CLOSES = re.compile(r"^\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I | re.M)
_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from ")
_REQ = re.compile(r"\bREQ-\d{3,}\b")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_QUOTES = "\"'“”‘’`"


class TraceError(FactoryError):
    """The line cannot be traced at all (bad spec, not in git at the ref)."""


# ----------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Location:
    path: str
    line: int
    text: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "text": self.text, "url": self.url}


@dataclass(frozen=True)
class PrdSection:
    section: str  # as the requirement cites it, without the "§"
    heading: Location | None  # the heading (or, in a PRD without headings, the line)
    detail: Location | None = None  # the line under the heading the citation points at

    def to_dict(self) -> dict[str, Any]:
        return {"section": self.section,
                "heading": self.heading.to_dict() if self.heading else None,
                "detail": self.detail.to_dict() if self.detail else None}


@dataclass(frozen=True)
class ReqTrace:
    req: str
    definition: Location | None
    prd: tuple[PrdSection, ...] = ()
    matrix: Location | None = None

    def gaps(self) -> list[str]:
        if self.definition is None:
            return [f"{self.req}: no `**{self.req}**` definition in any {REQUIREMENTS}"]
        if not self.prd:
            return [f"{self.req}: its definition cites no `PRD §<section>`"]
        return [f"{self.req}: PRD §{p.section} matches no heading or line in {PRD}"
                for p in self.prd if p.heading is None]

    def to_dict(self) -> dict[str, Any]:
        return {"req": self.req,
                "definition": self.definition.to_dict() if self.definition else None,
                "prd": [p.to_dict() for p in self.prd],
                "matrix": self.matrix.to_dict() if self.matrix else None}


@dataclass
class Trace:
    file: str
    line: int
    ref: str  # the commit --ref resolved to
    repo: str
    text: str = ""
    commit: str | None = None
    subject: str = ""
    pr: int | None = None
    pr_url: str = ""
    merged_at: str = ""
    merge_sha: str = ""
    found_by: str = ""  # API or MERGE_COMMIT
    issue: int | None = None
    story: str | None = None
    increment: str | None = None
    requirements: list[ReqTrace] = field(default_factory=list)
    broken: str | None = None  # the hop that could not be followed, and why
    elapsed_s: float = 0.0

    @property
    def base_url(self) -> str:
        return f"https://github.com/{self.repo}"

    def gaps(self) -> list[str]:
        if self.broken:
            return [self.broken]
        return [g for r in self.requirements for g in r.gaps()]

    @property
    def complete(self) -> bool:
        """Every hop was followed, to a PRD section for every REQ."""
        return not self.gaps()

    def to_dict(self) -> dict[str, Any]:
        base = self.base_url
        return {
            "file": self.file, "line": self.line, "ref": self.ref, "text": self.text,
            "commit": ({"sha": self.commit, "subject": self.subject,
                        "url": f"{base}/commit/{self.commit}"} if self.commit else None),
            "pr": ({"number": self.pr, "url": self.pr_url, "merged_at": self.merged_at,
                    "merge_commit": self.merge_sha, "found_by": self.found_by}
                   if self.pr else None),
            "issue": ({"number": self.issue, "url": f"{base}/issues/{self.issue}",
                       "story": self.story, "increment": self.increment}
                      if self.issue else None),
            "requirements": [r.to_dict() for r in self.requirements],
            "complete": self.complete, "gaps": self.gaps(),
            "elapsed_s": round(self.elapsed_s, 3),
        }


# ----------------------------------------------------------------------------- pure


def parse_spec(spec: str, root: Path) -> tuple[str, int]:
    """``<file>:<line>`` as a repo-relative POSIX path and a line number. The file may be
    absolute (inside the target) or relative to the target's root."""
    m = _SPEC.match(spec.strip())
    if not m or int(m["line"]) < 1:
        raise TraceError(f"expected <file>:<line> with a line number from 1, got {spec!r}")
    path = Path(m["path"])
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            raise TraceError(f"{m['path']} is not inside the target {root}") from None
    posix = PurePosixPath(path.as_posix().replace("\\", "/"))
    if ".." in posix.parts:
        raise TraceError(f"{m['path']} is not inside the target {root}")
    return str(posix).removeprefix("./"), int(m["line"])


def parse_blame(porcelain: str) -> tuple[str, str, str]:
    """``(sha, subject, line text)`` from ``git blame --porcelain`` of one line."""
    lines = porcelain.splitlines()
    if not lines or not re.match(r"^[0-9a-f]{40} ", lines[0]):
        raise TraceError("git blame gave no commit for the line")
    sha, subject, text = lines[0].split()[0], "", ""
    for line in lines[1:]:
        if line.startswith("summary "):
            subject = line[len("summary "):]
        elif line.startswith("\t"):
            text = line[1:]
    return sha, subject, text


def closes_issue(body: str) -> int | None:
    """The issue a PR body closes (``Closes #<I>``, or Fixes / Resolves), if any."""
    m = _CLOSES.search(body or "")
    return int(m[1]) if m else None


def traces_to(body: str) -> list[str]:
    """The REQs of a story issue's **Traces to** section, in order, each once."""
    m = re.search(r"^## Traces to\s*\n(.*?)(?=^## |\Z)", body or "", re.M | re.S)
    return list(dict.fromkeys(_REQ.findall(m[1]))) if m else []


def definition_line(text: str, req: str) -> tuple[int, str] | None:
    """The line that defines ``req`` (``**REQ-###**``), 1-based, or ``None``."""
    for number, line in enumerate(text.splitlines(), 1):
        if f"**{req}**" in line:
            return number, line
    return None


def prd_citations(line: str) -> list[str]:
    """The sections a REQ definition cites: ``(PRD §A, §B "quote"): …`` → ``[A, B "quote"]``."""
    m = re.search(r"\(PRD\s+(§.*?)\)\s*:", line)
    if not m:
        return []
    return [s for part in m[1].split("§") if (s := part.strip().rstrip(",;").strip())]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip(_QUOTES).strip()).casefold()


def match_prd(text: str, section: str) -> tuple[tuple[int, str] | None, tuple[int, str] | None]:
    """Where ``section`` is in a PRD: ``(heading, detail)``, each ``(line, text)`` or ``None``.

    The heading is the longest one whose title the citation starts with (``Functional
    requirements`` for ``Functional requirements FR-001``), or that starts with the citation
    and a colon (``Journey 1: Capture a new task`` for ``Journey 1``). What follows the
    title in the citation (``FR-001``, ``"Performance"``) is looked up in that heading's
    section, as the detail. A PRD without a matching heading (a one-line change request)
    matches on a line whose whole text is the citation."""
    lines = text.splitlines()
    want = _norm(section)
    headings = [(i, len(m[1]), m[2]) for i, line in enumerate(lines)
                if (m := _HEADING.match(line))]
    best = None
    for i, level, title in headings:
        t = _norm(title)
        if want == t or want.startswith(t + " ") or want.startswith(t + ":") \
                or t.startswith(want + ":"):
            if best is None or len(t) > len(_norm(best[2])):
                best = (i, level, title)
    if best is None:
        for i, line in enumerate(lines):
            if line.strip() and _norm(line.lstrip("#").strip()) == want:
                return (i + 1, line), None
        return None, None
    i, level, title = best
    heading = (i + 1, lines[i])
    rest = section.strip()[len(title.strip()):] if want.startswith(_norm(title)) else ""
    rest = _norm(rest.lstrip(" :"))
    if not rest:
        return heading, None
    end = next((j for j, lvl, _ in headings if j > i and lvl <= level), len(lines))
    for j in range(i + 1, end):
        if rest in _norm(lines[j]):
            return heading, (j + 1, lines[j])
    return heading, None


def matrix_line(text: str, req: str) -> tuple[int, str] | None:
    """The traceability matrix row of ``req``, 1-based, or ``None``."""
    row = re.compile(rf"^\|\s*{re.escape(req)}\s*\|")
    for number, line in enumerate(text.splitlines(), 1):
        if row.match(line.strip()):
            return number, line
    return None


def first_merged(prs: list[dict]) -> dict | None:
    """The PR that first merged the commit, among those GitHub lists for it."""
    merged = [p for p in prs if isinstance(p, dict) and p.get("merged_at")]
    return min(merged, key=lambda p: (p["merged_at"], p["number"])) if merged else None


# ----------------------------------------------------------------------------- I/O


def _show(git: Git, ref: str, path: str) -> str | None:
    try:
        return git.run(["show", f"{ref}:{path}"])
    except GitError:
        return None


def _is_ancestor(git: Git, a: str, b: str) -> bool:
    try:
        git.run(["merge-base", "--is-ancestor", a, b])
        return True
    except GitError as err:
        if err.returncode == 1:
            return False
        raise


def merge_commit_pr(git: Git, sha: str, ref: str) -> tuple[int, str] | None:
    """The fallback for merge commits: ``(PR number, merge commit)`` of the first
    ``Merge pull request #<P>`` commit from ``sha`` to ``ref`` that brought ``sha`` in
    through its second parent (or ``sha`` itself, when the line was written in the merge)."""
    out = git.run(["log", "--merges", "--ancestry-path", "--reverse", "--format=%H %P%x1f%s",
                   f"{sha}..{ref}"])
    own = git.run(["show", "-s", "--format=%H %P%x1f%s", sha])
    for row in [own.strip(), *out.splitlines()]:
        shas, _, subject = row.partition("\x1f")
        commit, *parents = shas.split()
        m = _MERGE_SUBJECT.match(subject)
        if not m or len(parents) < 2:
            continue
        if commit == sha or (_is_ancestor(git, sha, parents[1])
                             and not _is_ancestor(git, sha, parents[0])):
            return int(m[1]), commit
    return None


def _commit_prs(gh: Gh, repo: str, sha: str) -> list[dict]:
    try:
        found = gh.api(f"repos/{repo}/commits/{sha}/pulls")
    except GhError as err:
        if "HTTP 422" in err.stderr or "HTTP 404" in err.stderr:  # commit not on GitHub
            return []
        raise
    return found if isinstance(found, list) else []


def trace(gh: Gh, git: Git, repo: str, root: Path, spec: str, ref: str = "HEAD", *,
          clock: Callable[[], float] = time.perf_counter) -> Trace:
    """Follow the chain for ``spec`` (``<file>:<line>``). A hop that cannot be followed is
    recorded in ``broken``; only a line that cannot be blamed at all raises."""
    started = clock()
    path, number = parse_spec(spec, root)
    try:
        at = git.rev_parse(ref)
    except GitError:
        raise TraceError(f"--ref {ref} is not a commit in {root}") from None
    result = Trace(file=path, line=number, ref=at, repo=repo)
    try:
        porcelain = git.run(["blame", "--porcelain", "-L", f"{number},{number}", at, "--", path])
    except GitError as err:
        raise TraceError(f"cannot blame {path}:{number} at {at[:7]}: "
                         f"{err.stderr.strip() or err}") from None
    result.commit, result.subject, result.text = parse_blame(porcelain)
    try:
        _follow(gh, git, repo, result)
    finally:
        result.elapsed_s = clock() - started
    return result


def _follow(gh: Gh, git: Git, repo: str, t: Trace) -> None:
    pr = first_merged(_commit_prs(gh, repo, t.commit))
    t.found_by = API
    if pr is None:
        fallback = merge_commit_pr(git, t.commit, t.ref)
        if fallback is None:
            t.broken = (f"commit {t.commit[:7]}: {API} lists no merged PR for it, and no "
                        f"`Merge pull request #<P>` commit up to {t.ref[:7]} brought it in")
            return
        pr = gh.api(f"repos/{repo}/pulls/{fallback[0]}")
        t.found_by = MERGE_COMMIT
        if not pr.get("merged_at"):
            t.broken = f"PR #{fallback[0]} (from {MERGE_COMMIT}) is not merged on GitHub"
            return
    t.pr, t.pr_url = pr["number"], pr.get("html_url") or f"{t.base_url}/pull/{pr['number']}"
    t.merged_at, t.merge_sha = pr.get("merged_at") or "", pr.get("merge_commit_sha") or ""

    t.issue = closes_issue(pr.get("body") or "")
    if t.issue is None:
        t.broken = f"PR #{t.pr} closes no issue (no `Closes #<I>` in its body)"
        return
    issue = gh.api(f"repos/{repo}/issues/{t.issue}")
    marker = find(issue.get("body"), StoryMarker)
    if marker is None:
        t.broken = f"issue #{t.issue} is not a factory story (no factory:story marker)"
        return
    t.story, t.increment = marker.id, marker.increment
    reqs = traces_to(issue.get("body") or "")
    if not reqs:
        t.broken = f"issue #{t.issue} ({t.story}) has no REQ under **Traces to**"
        return

    increments = [t.increment] + sorted(
        PurePosixPath(p).name for p in git.run(
            ["ls-tree", "--name-only", t.ref, f"{INCREMENTS}/"]).splitlines()
        if PurePosixPath(p).name != t.increment)
    files: dict[str, str | None] = {}

    def read(path: str) -> str | None:  # each file once, however many REQs cite it
        if path not in files:
            files[path] = _show(git, t.ref, path)
        return files[path]

    for req in reqs:
        t.requirements.append(_requirement(read, t, req, increments))


def _location(t: Trace, path: str, found: tuple[int, str] | None) -> Location | None:
    if found is None:
        return None
    return Location(path, found[0], found[1], f"{t.base_url}/blob/{t.ref}/{path}#L{found[0]}")


def _requirement(read: Callable[[str], str | None], t: Trace, req: str,
                 increments: list[str]) -> ReqTrace:
    matrix = read(TRACEABILITY)
    matrix_at = _location(t, TRACEABILITY, matrix_line(matrix, req)) if matrix else None
    for inc in increments:
        path = f"{INCREMENTS}/{inc}/{REQUIREMENTS}"
        text = read(path)
        found = definition_line(text, req) if text else None
        if found is None:
            continue
        prd_path = f"{INCREMENTS}/{inc}/{PRD}"
        prd = read(prd_path) or ""
        sections = []
        for section in prd_citations(found[1]):
            heading, detail = match_prd(prd, section)
            sections.append(PrdSection(section, _location(t, prd_path, heading),
                                       _location(t, prd_path, detail)))
        return ReqTrace(req, _location(t, path, found), tuple(sections), matrix_at)
    return ReqTrace(req, None, (), matrix_at)


# ----------------------------------------------------------------------------- rendering


def _cut(text: str, limit: int = 160) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def render(t: Trace) -> str:
    base = t.base_url
    lines = [f"Trace of {t.file}:{t.line} at {t.ref[:7]}",
             f"  line     {_cut(t.text)}",
             f"  commit   {t.commit[:7]} {_cut(t.subject, 100)}",
             f"           {base}/commit/{t.commit}"]
    if t.pr:
        merged = f", merged {t.merged_at}" if t.merged_at else ""
        merged += f" as {t.merge_sha[:7]}" if t.merge_sha else ""
        lines += [f"  PR       #{t.pr}{merged} (found by {t.found_by})", f"           {t.pr_url}"]
    if t.issue and t.story:
        lines += [f"  issue    #{t.issue} {t.story}, increment {t.increment}",
                  f"           {base}/issues/{t.issue}"]
    for r in t.requirements:
        if r.definition is None:
            lines.append(f"  {r.req:<8} no definition found in any {REQUIREMENTS}")
        else:
            d = r.definition
            lines += [f"  {r.req:<8} {d.path}:{d.line}", f"           {_cut(d.text)}",
                      f"           {d.url}"]
        for p in r.prd:
            if p.heading is None:
                lines.append(f"    PRD    §{p.section}: no matching heading or line in {PRD}")
                continue
            h = p.heading
            lines += [f"    PRD    §{p.section} → {h.path}:{h.line} {_cut(h.text, 100)}",
                      f"           {h.url}"]
            if p.detail:
                lines += [f"           {p.detail.line}: {_cut(p.detail.text, 100)}",
                          f"           {p.detail.url}"]
        if r.matrix:
            lines += [f"    matrix {r.matrix.path}:{r.matrix.line} {_cut(r.matrix.text, 100)}",
                      f"           {r.matrix.url}"]
        else:
            lines.append(f"    matrix no row for {r.req} in {TRACEABILITY}")
    if t.complete:
        reqs = ", ".join(r.req for r in t.requirements)
        lines.append(f"Traced in {t.elapsed_s:.2f}s: line → commit {t.commit[:7]} → PR #{t.pr} "
                     f"→ issue #{t.issue} → {reqs} → PRD.")
    else:
        lines.append(f"Incomplete after {t.elapsed_s:.2f}s:")
        lines += [f"  - {g}" for g in t.gaps()]
    return "\n".join(lines)
