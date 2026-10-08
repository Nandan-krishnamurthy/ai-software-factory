"""The deterministic PR body: ``factory.py pr render`` and ``pr check`` (T6.3).

Facts in a story PR come from the factory's code, never from model-written text (rule H1).
``pr render --issue N`` fills ``templates/pr.md`` from:

* the story issue: its ``factory:story`` marker and its **Traces to** REQs;
* the checkpoint: the evidence ledger (``verify run``), the AC-to-test map (``verify
  map``) and the AC verifier's lines (S10), copied unchanged (rule H5);
* git, at the commit the evidence ran on: the diff against the default branch on
  ``origin``, the file stats, the commit bodies and the changed manifests;
* the approved ``.factory/config.json`` on ``origin`` (``limits``, ``ci.required``), and
  the commit's check runs when CI is required.

**Only Summary, Risks and Follow-ups are the model's.** They come from ``--notes F``
(``## Summary``, ``## Risks``, ``## Follow-ups``) and are checked: no headings, no HTML
comments or markers, and no closing keywords (``Fixes #12``) that would close an issue
on merge. Every other section is the factory's.

The quality gates, computed:

* **Q1 Build, Q2 Lint & types, Q4 Full suite:** the ledger's commands and their real
  results; a ``null`` command is ``Skipped`` (rule H4).
* **Q3 New tests:** every AC has a test named ``#N AC<n>`` in the diff (the map), or the
  verifier marked it ``not-verifiable`` with manual steps.
* **Q5 AC evidence:** the verdict passes ``verdict check``'s rules, held against the map.
* **Q6 Scope:** ``Not checked``. The story contract declares no areas to check the diff
  against, so the gate lists the files touched and claims nothing more.
* **Q7 Size:** the changed lines against ``limits.max_diff_lines``, without lockfiles
  and generated files (``linguist-generated`` in ``.gitattributes``, or an
  ``@generated`` / ``Code generated … DO NOT EDIT`` header).
* **Q8 CI:** ``Not configured`` unless ``ci.required``; then the check runs of the commit.

**Changed tests and new dependencies.** A removed or modified line in a test file that
existed at the base is a change to the test that encloses it (found by indentation in the
base file), or to the file when no test encloses it. Each must be named by a
``Changed test:`` line in a commit body, or it is flagged (rule H3). A dependency that a
changed manifest adds must have a ``New dependency:`` line, and every such line must name
a dependency a manifest adds (rule S9). Only removed or modified lines count: a test
that only gains lines is not a changed test.

``pr check <P>`` reads the open PR, takes its three model sections, renders the body
again from the facts as they are now, and fails on any other difference: a test result,
a gate or a fact that disagrees with the ledger fails the check.
"""

import difflib
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from factory import acmap, comments, evidence, manifests, templates, verdict
from factory.errors import FactoryError, GitError
from factory.gh import Gh
from factory.git import Git
from factory.markers import StoryMarker, find

TEMPLATE = "pr.md"
TRACEABILITY = "docs/factory/traceability.md"
PLANNING_DOCS = "docs/factory/increments/"
# The model-owned placeholders and the --notes headings that supply them.
MODEL_SECTIONS = {"summary": "Summary", "risks": "Risks", "follow_ups": "Follow-ups"}
_STORY_BRANCH = re.compile(r"^story/(\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_REQ = re.compile(r"\bREQ-\d+\b")
_CLOSING = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[\s:]*"
                      r"(?:[\w.-]+/[\w.-]+)?#\d+")
_SEPARATOR = re.compile(r"\s+(?:—|–|--?)\s+")
_GENERATED_HEADER = re.compile(r"@generated\b|^\W*Code generated .* DO NOT EDIT\.?\s*$")
GATE_FAILING = ("Fail", "Pending")


class PrBodyError(FactoryError):
    """The PR body could not be rendered or checked."""


# ----------------------------------------------------------------------------- facts


@dataclass(frozen=True)
class FileStat:
    path: str
    old_path: str  # the path at the base; differs from path for a rename
    added: int
    deleted: int
    binary: bool = False


@dataclass(frozen=True)
class Commit:
    sha: str
    body: str


@dataclass
class GitFacts:
    merge_base: str
    diff: str
    files: list[FileStat]
    commits: list[Commit]
    base_texts: dict[str, str | None]  # old path -> text at the merge base (None: new)
    head_texts: dict[str, str | None]  # path -> text at the head (manifests only)
    generated: set[str]


@dataclass
class Facts:
    issue: int
    story_id: str
    increment: str
    requirements: list[str]
    evidence: evidence.Evidence
    acmap: acmap.AcMap
    verdict: verdict.Verdict
    max_diff_lines: int
    ci_required: bool
    ci_runs: list[dict] | None
    git: GitFacts


def collect(gh: Gh, git: Git, repo: str, issue: int) -> Facts:
    """Every fact the body is built from. Raises ``PrBodyError`` when the facts cannot be
    trusted: no story marker, no or stale evidence, no map for that evidence, no verdict."""
    item = gh.api(f"repos/{repo}/issues/{issue}")
    if "pull_request" in item:
        raise PrBodyError(f"#{issue} is a pull request, not a story issue")
    body = (item.get("body") or "").replace("\r\n", "\n")
    story = find(body, StoryMarker)
    if story is None:
        raise PrBodyError(f"issue #{issue} has no factory:story marker; it is not a story")
    found = comments.find_checkpoint(comments.list_comments(gh, repo, issue))
    if found is None:
        raise PrBodyError(f"issue #{issue} has no checkpoint comment")
    note_body = (found[0].get("body") or "").replace("\r\n", "\n")
    recorded = evidence.from_body(note_body)
    if recorded is None:
        raise PrBodyError(f"issue #{issue}'s checkpoint has no evidence; run `verify run`")
    head = evidence.remote_head(git, recorded.branch)
    failures = set(recorded.failures())
    stale = [p for p in evidence.check(recorded, issue=issue, branch_head=head,
                                       expected_branch=found[1].branch)
             if p not in failures]
    if stale:
        raise PrBodyError("the evidence cannot be used: " + "; ".join(stale))
    mapped = acmap.from_body(note_body)
    if mapped is None or mapped.sha != recorded.sha:
        raise PrBodyError(f"issue #{issue}'s checkpoint has no AC-to-test map for commit "
                          f"{recorded.sha[:7]}; run `verify map`")
    note = verdict.checkpoint_note(gh, repo, issue, note_body)
    parsed = verdict.parse(note, verdict.issue_acs(body))
    if not parsed.acs:
        raise PrBodyError(f"issue #{issue}'s checkpoint note has no AC verifier lines (S10)")
    parsed.problems += verdict.cross_check(
        parsed, mapped, issue=issue, evidence_sha=recorded.sha,
        checkpoint_branch=found[1].branch, branch_head=head)
    config, _ = evidence.approved_config(git)
    facts = git_facts(git, evidence.default_ref(git), recorded.sha)
    return Facts(
        issue=issue, story_id=story.id, increment=story.increment,
        requirements=_REQ.findall(_section(body, "Traces to")), evidence=recorded,
        acmap=mapped, verdict=parsed, max_diff_lines=config.limits.max_diff_lines,
        ci_required=config.ci_required,
        ci_runs=check_runs(gh, repo, recorded.sha) if config.ci_required else None,
        git=facts)


def _section(body: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m[1] if m else ""


def git_facts(git: Git, base_ref: str, sha: str) -> GitFacts:
    """What the story branch changes, as of ``sha``, against ``base_ref``."""
    try:
        merge_base = git.run(["merge-base", base_ref, sha]).strip()
        numstat = git.run(["-c", "core.quotepath=false", "diff", "--numstat", "-z",
                           "--no-color", "--find-renames", f"{base_ref}...{sha}"])
        log = git.run(["log", "--no-color", "--format=%H%x1f%B%x1e", f"{base_ref}..{sha}"])
    except GitError as err:
        raise PrBodyError(f"cannot read the branch's changes: {err.stderr.strip() or err}"
                          ) from None
    diff = acmap.branch_diff(git, base_ref, sha)
    files = parse_numstat(numstat)
    hunks = parse_hunks(diff)
    base_texts: dict[str, str | None] = {}
    head_texts: dict[str, str | None] = {}
    for f in files:
        removed = hunks.get(f.path, FileHunks()).removed
        if acmap.is_test_file(f.old_path) and removed:
            base_texts[f.old_path] = _show(git, merge_base, f.old_path)
        if manifests.is_manifest(f.path) or manifests.is_manifest(f.old_path):
            base_texts[f.old_path] = _show(git, merge_base, f.old_path)  # None: new
            head_texts[f.path] = _show(git, sha, f.path)  # None: deleted
    paths = [f.path for f in files]
    generated = _generated_attr(git, sha, paths) if paths else set()
    generated |= {path for path, h in hunks.items()
                  if any(n <= 5 and _GENERATED_HEADER.search(text) for n, text in h.added)}
    return GitFacts(merge_base, diff, files, parse_log(log), base_texts, head_texts, generated)


def _show(git: Git, rev: str, path: str) -> str | None:
    try:
        return git.run(["show", f"{rev}:{path}"])
    except GitError:
        return None


def _generated_attr(git: Git, sha: str, paths: list[str]) -> set[str]:
    """The paths ``.gitattributes`` at ``sha`` marks ``linguist-generated``."""
    try:
        out = git.run(["check-attr", "-z", "--source", sha, "linguist-generated", "--",
                       *paths])
    except GitError as err:
        raise PrBodyError(f"cannot read .gitattributes: {err.stderr.strip() or err}") from None
    parts = out.split("\0")
    return {parts[i] for i in range(0, len(parts) - 2, 3)
            if parts[i + 2] in ("set", "true")}


def parse_numstat(out: str) -> list[FileStat]:
    """``git diff --numstat -z`` output. A rename is ``a\\td\\t\\0old\\0new\\0``."""
    parts = out.split("\0")
    files, i = [], 0
    while i < len(parts) and parts[i].strip():
        added, deleted, path = parts[i].lstrip("\n").split("\t", 2)
        old = path
        if not path:  # a rename or copy: the two paths follow
            old, path = parts[i + 1], parts[i + 2]
            i += 2
        i += 1
        binary = added == "-"
        files.append(FileStat(path, old, 0 if binary else int(added),
                              0 if binary else int(deleted), binary))
    return files


@dataclass
class FileHunks:
    old_path: str | None = None
    removed: list[tuple[int, str]] = field(default_factory=list)  # old line numbers
    added: list[tuple[int, str]] = field(default_factory=list)  # new line numbers
    new_file: bool = False
    deleted_file: bool = False


_HUNK = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<oldn>\d+))? \+(?P<new>\d+)(?:,(?P<newn>\d+))? @@")


def parse_hunks(diff: str) -> dict[str, FileHunks]:
    """The removed and added lines of a ``--unified=0`` diff, by new path (old path for a
    deleted file), read hunk by hunk."""
    found: dict[str, FileHunks] = {}
    current: FileHunks | None = None
    old_path = new_path = None
    old_left = new_left = old_no = new_no = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("-"):
                current.removed.append((old_no, line[1:]))
                old_no, old_left = old_no + 1, old_left - 1
            elif line.startswith("+"):
                current.added.append((new_no, line[1:]))
                new_no, new_left = new_no + 1, new_left - 1
            elif not line.startswith("\\"):
                old_no, new_no = old_no + 1, new_no + 1
                old_left, new_left = old_left - 1, new_left - 1
            continue
        if line.startswith("diff --git "):
            current, old_path, new_path = None, None, None
        elif line.startswith("--- "):
            path = line[4:].rstrip("\t")
            old_path = None if path == "/dev/null" else path.removeprefix("a/")
        elif line.startswith("+++ "):
            path = line[4:].rstrip("\t")
            new_path = None if path == "/dev/null" else path.removeprefix("b/")
            key = new_path or old_path
            current = found.setdefault(key, FileHunks(old_path, new_file=old_path is None,
                                                      deleted_file=new_path is None))
        elif (m := _HUNK.match(line)) and current is not None:
            old_no, new_no = int(m["old"]), int(m["new"])
            old_left = int(m["oldn"]) if m["oldn"] is not None else 1
            new_left = int(m["newn"]) if m["newn"] is not None else 1
    return found


def parse_log(out: str) -> list[Commit]:
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if "\x1f" in record:
            sha, body = record.split("\x1f", 1)
            commits.append(Commit(sha.strip(), body.replace("\r\n", "\n")))
    return commits


def check_runs(gh: Gh, repo: str, sha: str) -> list[dict]:
    data = gh.api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100")
    runs = data.get("check_runs") if isinstance(data, dict) else None
    return [r for r in runs or [] if isinstance(r, dict)]


# ----------------------------------------------------------------------------- changed tests

_JS_TEST = re.compile(r"""^\s*(?:it|test|specify)(?:\.(?:only|skip|todo|concurrent|fails))*"""
                      r"""\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""")
_PY_TEST = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_GO_TEST = re.compile(r"^func\s+(Test\w*)\s*\(")
_ANNOTATION = re.compile(r"^\s*(?:@Test\b|@ParameterizedTest\b|#\[(?:\w+::)*test\b|"
                         r"\[(?:Fact|Theory|Test|TestMethod)\b)")
_ANNOTATED = re.compile(r"^\s*(?:[\w<>\[\],.?]+\s+)*?(?:fn\s+|fun\s+|def\s+)?(\w+)\s*\(")


def _indent(line: str) -> int:
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


def _declaration(lines: list[str], index: int) -> str | None:
    """The name of the test declared on ``lines[index]``, or ``None``."""
    line = lines[index]
    for pattern, group in ((_JS_TEST, 2), (_PY_TEST, 1), (_GO_TEST, 1)):
        if m := pattern.match(line):
            return re.sub(r"\\(.)", r"\1", m[group])
    previous = next((lines[i] for i in range(index - 1, -1, -1) if lines[i].strip()), "")
    if _ANNOTATION.match(previous) and (m := _ANNOTATED.match(line)):
        return m[1]
    return None


def enclosing_test(lines: list[str], number: int) -> str | None:
    """The test whose body holds line ``number`` (1-based) of a test file, or ``None``
    when the line belongs to no test (imports, helpers, setup)."""
    index = number - 1
    if not 0 <= index < len(lines):
        return None
    if name := _declaration(lines, index):
        return name
    threshold = _indent(lines[index]) if lines[index].strip() else 10 ** 6
    for i in range(index - 1, -1, -1):
        line = lines[i]
        if not line.strip() or _indent(line) >= threshold:
            continue
        if name := _declaration(lines, i):
            return name
        threshold = _indent(line)
        if threshold == 0:
            return None
    return None


@dataclass(frozen=True)
class ChangedTest:
    file: str
    name: str | None  # None: a change outside any test (setup, helpers)
    declared: str | None  # the `Changed test:` text that names it


def commit_lines(commits: list[Commit], prefix: str) -> list[str]:
    """The text after ``prefix`` on every commit-body line that starts with it."""
    return [line.strip()[len(prefix):].strip() for c in commits for line in c.body.splitlines()
            if line.strip().startswith(prefix)]


def changed_tests(facts: GitFacts) -> tuple[list[ChangedTest], list[str]]:
    """Every existing test the branch changes, with the ``Changed test:`` line naming it,
    and the declared lines that name no change found."""
    declared = commit_lines(facts.commits, "Changed test:")
    used: set[str] = set()
    found: list[ChangedTest] = []
    hunks = parse_hunks(facts.diff)
    for f in facts.files:
        h = hunks.get(f.path)
        if not h or not h.removed or not acmap.is_test_file(f.old_path):
            continue
        lines = (facts.base_texts.get(f.old_path) or "").replace("\r\n", "\n").split("\n")
        names = list(dict.fromkeys(enclosing_test(lines, n) for n, _ in h.removed))
        for name in names:
            key = name if name is not None else f.old_path
            match = next((d for d in declared if key in d), None)
            if match is not None:
                used.add(match)
            found.append(ChangedTest(f.old_path, name, match))
    return found, [d for d in declared if d not in used]


# ----------------------------------------------------------------------------- dependencies


@dataclass(frozen=True)
class NewDependency:
    name: str
    manifest: str | None  # None: declared in a commit, but no manifest adds it
    declared: str | None  # the `New dependency:` text that names it


def new_dependencies(facts: GitFacts) -> tuple[list[NewDependency], list[str]]:
    """The dependencies the changed manifests add, each with its ``New dependency:``
    line, then each declared line no manifest adds; and the manifests that could not be
    read."""
    declared = commit_lines(facts.commits, "New dependency:")
    names = {manifests.normalize(_SEPARATOR.split(d, 1)[0]): d for d in declared}
    found: list[NewDependency] = []
    errors: list[str] = []
    for f in facts.files:
        if f.path not in facts.head_texts:
            continue
        try:
            before = manifests.dependencies(f.old_path, facts.base_texts.get(f.old_path))
            after = manifests.dependencies(f.path, facts.head_texts[f.path])
        except manifests.ManifestError as err:
            errors.append(str(err))
            continue
        old = {manifests.normalize(n) for n in before}
        for name in sorted(after, key=str.lower):
            if manifests.normalize(name) not in old:
                found.append(NewDependency(name, f.path,
                                           names.pop(manifests.normalize(name), None)))
    found += [NewDependency(_SEPARATOR.split(d, 1)[0].strip().strip("`"), None, d)
              for d in names.values()]
    return found, errors


# ----------------------------------------------------------------------------- the body


@dataclass(frozen=True)
class Gate:
    key: str  # the template placeholder
    label: str
    status: str  # Pass | Fail | Skipped | Pending | Not checked | Not configured | Over limit
    text: str

    @property
    def value(self) -> str:
        return f"{self.status}: {self.text}" if self.text else self.status


@dataclass
class Rendered:
    body: str
    gates: list[Gate]
    problems: list[str]
    warnings: list[str]


def render(facts: Facts, sections: dict[str, str]) -> Rendered:
    """Fill ``templates/pr.md`` from ``facts`` and the model's ``sections``. Pure: the same
    facts and sections give the same body, byte for byte."""
    problems: list[str] = []
    warnings: list[str] = []
    for key, text in sections.items():
        problems += [f"{MODEL_SECTIONS[key]}: {p}" for p in model_text_problems(text)]
    gates = compute_gates(facts)
    problems += [f"{g.label}: {g.value}" for g in gates if g.status in GATE_FAILING]
    warnings += [f"{g.label}: {g.value}" for g in gates if g.status == "Over limit"]

    changed, unmatched = changed_tests(facts.git)
    problems += [f"rule H3: {_test_name(c)} in `{c.file}` changed without a `Changed test:` "
                 "line" for c in changed if c.declared is None]
    warnings += [f"`Changed test: {d}` names no change found in an existing test"
                 for d in unmatched]
    deps, errors = new_dependencies(facts.git)
    problems += errors
    problems += [f"rule S9: `{d.name}` added to `{d.manifest}` without a `New dependency:` "
                 "line" for d in deps if d.manifest and d.declared is None]
    problems += [f"rule S9: `New dependency: {d.declared}` names no dependency a manifest "
                 "adds" for d in deps if d.manifest is None]

    values = {
        "story_id": facts.story_id,
        "issue": str(facts.issue),
        "summary": sections.get("summary", "").strip() or "None",
        "requirements": ", ".join(dict.fromkeys(facts.requirements)) or "None",
        "traceability_rows": _traceability(facts.git),
        "ac_verification": "\n".join(a.line for a in facts.verdict.acs),
        "tests_added": _tests_added(facts),
        "tests_changed": _tests_changed(changed, unmatched),
        "test_command": _command(facts.evidence, "test") or "commands.test is null",
        "test_result": _result(facts.evidence.command("test")),
        "new_dependencies": _dependencies(deps),
        "doc_changes": _doc_changes(facts.git),
        "risks": sections.get("risks", "").strip() or "None",
        "follow_ups": sections.get("follow_ups", "").strip() or "None",
        **{g.key: g.value for g in gates},
    }
    body = templates.render(templates.load(TEMPLATE), values)
    return Rendered(body, gates, problems, warnings)


def compute_gates(facts: Facts) -> list[Gate]:
    ev = facts.evidence
    return [
        _command_gate("gate_build", "Q1 Build", ev, "build"),
        _lint_gate(ev),
        _tests_gate(facts),
        _command_gate("gate_full_suite", "Q4 Full suite", ev, "test"),
        _evidence_gate(facts),
        Gate("gate_scope", "Q6 Scope", "Not checked",
             "the story contract declares no areas. Files touched "
             f"({len(facts.git.files)}): " + ", ".join(f"`{f.path}`" for f in facts.git.files)),
        _size_gate(facts),
        _ci_gate(facts),
    ]


def _command(ev: evidence.Evidence, name: str) -> str | None:
    c = ev.command(name)
    return c.command if c is not None else None


def _outcome(c: evidence.CommandEvidence | None, name: str) -> str:
    """What a recorded command did, in words, without its status word."""
    if c is None or c.status == "skipped":
        return f"commands.{name} is null"
    if c.status == "timeout":
        return f"`{c.command}` timed out ({c.detail})"
    if c.status == "error":
        return f"`{c.command}` could not run ({c.detail})"
    text = f"`{c.command}` exited {c.exit_code}"
    if c.summary:
        text += f": {evidence.summary_text(c.summary)}"
    return f"{text} ({c.detail})" if c.detail else text


def _result(c: evidence.CommandEvidence | None) -> str:
    """The test command's recorded result, after the command the template already names."""
    if c is None or c.status == "skipped":
        return "skipped (commands.test is null)"
    words = {"pass": f"passed (exit {c.exit_code})", "fail": f"failed (exit {c.exit_code})",
             "timeout": f"timed out ({c.detail})", "error": f"could not run ({c.detail})"}
    text = words[c.status]
    if c.summary:
        text += f": {evidence.summary_text(c.summary)}"
    return f"{text}; {c.detail}" if c.detail and c.status in ("pass", "fail") else text


def _status(c: evidence.CommandEvidence | None) -> str:
    if c is None or c.status == "skipped":
        return "Skipped"
    return "Pass" if c.status == "pass" else "Fail"


def _command_gate(key: str, label: str, ev: evidence.Evidence, name: str) -> Gate:
    c = ev.command(name)
    return Gate(key, label, _status(c), _outcome(c, name))


def _lint_gate(ev: evidence.Evidence) -> Gate:
    parts = [(name, ev.command(name)) for name in ("lint", "typecheck")]
    statuses = {_status(c) for _, c in parts}
    status = "Fail" if "Fail" in statuses else "Skipped" if statuses == {"Skipped"} else "Pass"
    text = "; ".join(f"{name}: {_status(c).lower()}, {_outcome(c, name)}" for name, c in parts)
    return Gate("gate_lint", "Q2 Lint & types", status, text)


def _tests_gate(facts: Facts) -> Gate:
    stated = {a.number: a for a in facts.verdict.acs}
    parts, missing = [], []
    for m in facts.acmap.acs:
        if m.tests:
            parts.append(f"AC{m.ac} {len(m.tests)} test{'s' if len(m.tests) != 1 else ''}")
        elif (a := stated.get(m.ac)) and a.verdict == "not-verifiable" and \
                a.kind == "manual steps":
            parts.append(f"AC{m.ac} manual steps")
        else:
            parts.append(f"AC{m.ac} no test")
            missing.append(f"AC{m.ac}")
    text = ", ".join(parts) + f" (named `#{facts.issue} AC<n>`)"
    if missing:
        text += "; no test and no manual steps for " + ", ".join(missing)
    return Gate("gate_new_tests", "Q3 New tests", "Fail" if missing else "Pass", text)


def _evidence_gate(facts: Facts) -> Gate:
    v = facts.verdict
    counts = {k: sum(a.verdict == k for a in v.acs) for k in verdict.VERDICTS}
    text = (f"{counts['pass']} pass, {counts['fail']} fail, {counts['not-verifiable']} "
            f"not-verifiable, held against the AC-to-test map @ `{facts.acmap.sha[:7]}`")
    if v.problems:
        return Gate("gate_ac_evidence", "Q5 AC evidence", "Fail",
                    f"{text}; the verdict is invalid: " + "; ".join(v.problems))
    if v.failing:
        return Gate("gate_ac_evidence", "Q5 AC evidence", "Fail", f"{text}; an AC failed")
    return Gate("gate_ac_evidence", "Q5 AC evidence", "Pass",
                f"{text}; every pass has a passing mapped test")


def _size_gate(facts: Facts) -> Gate:
    counted, excluded = [], []
    for f in facts.git.files:
        if manifests.is_lockfile(f.path):
            excluded.append(f"`{f.path}` (lockfile)")
        elif f.path in facts.git.generated:
            excluded.append(f"`{f.path}` (generated)")
        else:
            counted.append(f)
    lines = sum(f.added + f.deleted for f in counted)
    text = (f"{lines} changed lines in {len(counted)} file{'s' if len(counted) != 1 else ''}"
            f" (limit {facts.max_diff_lines})")
    if excluded:
        text += "; not counted: " + ", ".join(excluded)
    if lines > facts.max_diff_lines:
        return Gate("gate_size", "Q7 Size", "Over limit",
                    f"{text}; the reason belongs under Risks")
    return Gate("gate_size", "Q7 Size", "Pass", text)


_CI_BAD = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}


def _ci_gate(facts: Facts) -> Gate:
    if not facts.ci_required:
        return Gate("gate_ci", "Q8 CI", "Not configured", "ci.required is false")
    runs = facts.ci_runs or []
    sha = facts.evidence.sha[:7]
    if not runs:
        return Gate("gate_ci", "Q8 CI", "Pending", f"no check runs yet for `{sha}`")
    failed = sorted(r.get("name") or "?" for r in runs if r.get("conclusion") in _CI_BAD)
    waiting = sorted(r.get("name") or "?" for r in runs if r.get("status") != "completed")
    if failed:
        return Gate("gate_ci", "Q8 CI", "Fail", f"failed on `{sha}`: " + ", ".join(failed))
    if waiting:
        return Gate("gate_ci", "Q8 CI", "Pending", f"running on `{sha}`: " + ", ".join(waiting))
    return Gate("gate_ci", "Q8 CI", "Pass", f"{len(runs)} check run(s) passed on `{sha}`")


def _test_name(c: ChangedTest) -> str:
    return f"`{c.name}`" if c.name is not None else "a line outside any test"


def _tests_added(facts: Facts) -> str:
    files: dict[str, int] = {}
    seen = set()
    for m in facts.acmap.acs:
        for t in m.tests:
            if (t.file, t.line, t.name) not in seen:
                seen.add((t.file, t.line, t.name))
                files[t.file] = files.get(t.file, 0) + 1
    if not seen:
        return "None"
    return (f"{len(seen)} test{'s' if len(seen) != 1 else ''} named `#{facts.issue} AC<n>` in "
            f"{len(files)} file{'s' if len(files) != 1 else ''}: "
            + ", ".join(f"`{f}` ({n})" for f, n in files.items()))


def _tests_changed(changed: list[ChangedTest], unmatched: list[str]) -> str:
    if not changed and not unmatched:
        return "None"
    lines = [str(len(changed))]
    for c in changed:
        if c.declared is not None:
            lines.append(f"  - `{c.file}`: {c.declared}")
        else:
            lines.append(f"  - `{c.file}`: {_test_name(c)} — **not declared**: no "
                         "`Changed test:` line names it (rule H3)")
    lines += [f"  - Declared, but no change to it was found: {d}" for d in unmatched]
    return "\n".join(lines)


def _dependencies(deps: list[NewDependency]) -> str:
    if not deps:
        return "None"
    lines = []
    for d in deps:
        if d.manifest is None:
            lines.append(f"- `{d.name}` — **declared in a commit, but no manifest adds it**: "
                         f"{d.declared}")
        elif d.declared is None:
            lines.append(f"- `{d.name}` (`{d.manifest}`) — **not declared**: no "
                         "`New dependency:` line names it (rule S9)")
        else:
            reason = _SEPARATOR.split(d.declared, 1)
            lines.append(f"- `{d.name}` (`{d.manifest}`) — "
                         f"{reason[1] if len(reason) == 2 else d.declared}")
    return "\n".join(lines)


def _traceability(facts: GitFacts) -> str:
    h = parse_hunks(facts.diff).get(TRACEABILITY)
    reqs = list(dict.fromkeys(r for _, text in (h.added if h else []) for r in _REQ.findall(text)))
    return ", ".join(reqs) + " updated" if reqs else "None"


def _doc_changes(facts: GitFacts) -> str:
    docs = [f for f in facts.files if f.path.startswith(PLANNING_DOCS)]
    return "; ".join(f"`{f.path}` (+{f.added} -{f.deleted})" for f in docs) or "None"


# ----------------------------------------------------------------------------- model text


def model_text_problems(text: str) -> list[str]:
    """Why model-written text cannot go into the body: it would add or hide a section,
    carry a marker, or close an issue on merge."""
    problems = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            problems.append(f"a heading is not allowed here: {line.strip()[:60]!r}")
        if "<!--" in line:
            problems.append("HTML comments and markers are not allowed")
    if m := _CLOSING.search(text):
        problems.append(f"a closing keyword would close an issue on merge: {m[0]!r}")
    return list(dict.fromkeys(problems))


def parse_notes(text: str) -> dict[str, str]:
    """The model's sections from a ``--notes`` file: ``## Summary`` (required),
    ``## Risks`` and ``## Follow-ups``. Anything else is refused."""
    headings = {v: k for k, v in MODEL_SECTIONS.items()}
    sections: dict[str, list[str]] = {}
    current = None
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            title = line[3:].strip()
            if title not in headings:
                raise PrBodyError(f"--notes: unknown section {line.strip()!r}; use ## Summary, "
                                  "## Risks and ## Follow-ups")
            current = headings[title]
            if current in sections:
                raise PrBodyError(f"--notes: {line.strip()!r} appears twice")
            sections[current] = []
        elif current is None:
            if line.strip():
                raise PrBodyError("--notes: text before the first section heading")
        else:
            sections[current].append(line)
    found = {k: "\n".join(v).strip() for k, v in sections.items()}
    if not found.get("summary"):
        raise PrBodyError("--notes: ## Summary is required and may not be empty")
    return found


def template_sections(body: str) -> dict[str, str]:
    """The model's sections as they are in a PR body: the text under each model-owned
    heading of the template, up to the next ``## `` heading."""
    lines = normalize(body)
    found = {}
    for key, heading in _model_headings().items():
        try:
            start = lines.index(heading) + 1
        except ValueError:
            raise PrBodyError(f"the PR body has no {heading!r} section") from None
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")),
                   len(lines))
        found[key] = "\n".join(lines[start:end]).strip()
    return found


def _model_headings() -> dict[str, str]:
    """The template heading above each model-owned placeholder."""
    lines = templates.load(TEMPLATE).split("\n")
    headings = {}
    for key in MODEL_SECTIONS:
        index = lines.index(f"{{{{{key}}}}}")
        headings[key] = next(lines[i] for i in range(index - 1, -1, -1)
                             if lines[i].startswith("## "))
    return headings


# ----------------------------------------------------------------------------- check


def normalize(body: str) -> list[str]:
    lines = [line.rstrip() for line in body.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


@dataclass
class CheckResult:
    number: int
    issue: int
    differences: list[str]
    problems: list[str]
    rendered: Rendered | None = None

    @property
    def ok(self) -> bool:
        return not self.differences and not self.problems


def check(gh: Gh, git: Git, repo: str, number: int) -> CheckResult:
    """Hold open PR ``number`` against a fresh render from the facts as they are now."""
    pr = gh.api(f"repos/{repo}/pulls/{number}")
    branch = (pr.get("head") or {}).get("ref") or ""
    m = _STORY_BRANCH.match(branch)
    if m is None:
        raise PrBodyError(f"PR #{number}'s branch {branch!r} is not a story branch "
                          "(story/<issue>-<slug>)")
    issue = int(m[1])
    facts = collect(gh, git, repo, issue)
    problems = []
    if pr.get("state") != "open":
        problems.append(f"PR #{number} is {pr.get('state')}, not open")
    head = (pr.get("head") or {}).get("sha")
    if head != facts.evidence.sha:
        problems.append(f"PR #{number}'s head is {str(head)[:7]}, but the evidence is for "
                        f"{facts.evidence.sha[:7]}; run `verify run` and `verify map` again")
    body = pr.get("body") or ""
    try:
        sections = template_sections(body)
    except PrBodyError as err:
        return CheckResult(number, issue, [], problems + [str(err)])
    rendered = render(facts, sections)
    problems += rendered.problems
    diff = list(difflib.unified_diff(normalize(rendered.body), normalize(body),
                                     "fresh render", f"PR #{number}", lineterm="", n=0))
    differences = [line for line in diff[2:] if not line.startswith("@@")]
    return CheckResult(number, issue, differences, problems, rendered)


# ----------------------------------------------------------------------------- output


def default_path(issue: int) -> Path:
    """``<SCRATCH>/pr-<N>.md``, where S11 keeps the body it passes to ``factory.py pr``."""
    return Path(tempfile.gettempdir()) / f"pr-{issue}.md"


def write(rendered: Rendered, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered.body.encode("utf-8"))  # bytes: no newline translation
    return path


def report(rendered: Rendered, issue: int, path: Path | None = None) -> str:
    lines = [f"PR body for #{issue}" + (f" written to {path}" if path else "")]
    lines += [f"  {g.label:<16} {g.value}" for g in rendered.gates]
    lines += [f"  warning: {w}" for w in rendered.warnings]
    lines += [f"  problem: {p}" for p in rendered.problems]
    lines.append("NOT READY: fix the problems above; the body states them as they are."
                 if rendered.problems else "OK: every gate passed and every fact is declared.")
    return "\n".join(lines)


def report_check(result: CheckResult, limit: int = 40) -> str:
    lines = [f"PR #{result.number} (#{result.issue}) against a fresh render"]
    if result.differences:
        lines.append("  the PR body differs outside Summary, Risks and Follow-ups:")
        lines += [f"    {d}" for d in result.differences[:limit]]
        if len(result.differences) > limit:
            lines.append(f"    ... {len(result.differences) - limit} more")
    lines += [f"  problem: {p}" for p in result.problems]
    lines.append("OK: the PR body is the factory's render, and every gate passed."
                 if result.ok else "FAILED: the PR body does not match the facts, or a "
                                   "gate failed; render it again with `pr render`.")
    return "\n".join(lines)
