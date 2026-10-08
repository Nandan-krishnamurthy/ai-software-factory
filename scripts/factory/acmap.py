"""The AC-to-test map: ``factory.py verify map`` (T6.2).

``verify map --issue N`` decides, from facts and not from model-written text, which
acceptance criteria of story ``#N`` have a test that really passed (rule H1):

1. **Tests from the branch diff.** Every line the story branch adds to a test file
   (``git diff <default>...<evidence SHA>``) is searched for the tag ``#N AC<k>``, the
   name S09 gives each test (``#N AC2: rejects an empty title``). The string literal
   that holds the tag is the test's name. ``#N AC3 AC4: …`` names a test for both
   criteria. An identifier such as ``test_N_ac2_rejects_empty`` counts too. A tag
   outside any literal (a comment) is listed, but such a test can never pass: name
   the test itself.
2. **Results from the recorded run.** The results come from the evidence ledger
   (``verify run``, T6.1), never from a new run, and from nothing the model wrote:

   * **Reports first.** JUnit XML and the JSON reports of jest-style runners (Vitest,
     Jest) and of Playwright, when the target's test command already writes one and
     ``verify run --report`` captured it.
   * **Otherwise the output.** Each line of the test command's full output that
     contains a test's name and a result mark: ``✓``/``ok``/``PASS``/``PASSED``/
     ``... ok`` passes, ``✘``/``×``/``x``/``FAIL``/``FAILED``/``ERROR`` fails, and
     ``-``/``↓``/``SKIP``/``SKIPPED``/``... skipped``/``... ignored`` is skipped. That
     covers Playwright's ``list`` reporter, Vitest/Jest verbose output, ``pytest -v``,
     ``unittest -v``, ``go test -v`` and ``cargo test``. A line that names a test but
     carries no mark (a code frame, a failure header) is ignored. The name must match
     whole, and a line belongs to the longest name it contains.

   A failure in any source wins over a pass: a flaky test that failed once is failed.
3. **The map.** Each test is ``passed``, ``failed``, ``skipped`` or ``no-result``; each
   AC is ``failed`` if any of its tests failed, ``passed`` if one passed, and
   ``missing`` otherwise (no test in the diff, or none with a passing result).

The evidence is read only from the checkpoint note, and the local output and reports
only if their SHA-256 is the one it recorded. The map is written to
``<SCRATCH>/acmap-<N>.json`` and into the checkpoint note, beside the evidence.
``verdict check`` requires it there, for the branch head on ``origin``, and refuses a
verifier ``pass`` for an AC without a passing mapped test, a ``not-verifiable`` that
hides a failing test, and an AC without a test that is not ``not-verifiable`` with
written manual steps.
"""

import json
import re
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from factory.comments import MAP_END, MAP_START, map_block
from factory.errors import FactoryError, GitError
from factory.evidence import Evidence, clean_lines
from factory.git import Git

SCHEMA = 1
TEST_STATUSES = ("passed", "failed", "skipped", "no-result")
AC_STATUSES = ("passed", "failed", "missing")
MAX_NAME = 300  # a longer test name is cut in the map
NOTE_BUDGET = 20000  # room for the map in the checkpoint comment


class AcMapError(FactoryError):
    """The AC-to-test map could not be built or read."""


@dataclass
class MappedTest:
    file: str
    line: int
    name: str | None  # None: the tag is not in a test name (a comment)
    status: str = "no-result"
    source: str = ""  # where the result came from: "output" or "report <path>"


@dataclass
class AcMapping:
    ac: int
    status: str
    tests: list[MappedTest] = field(default_factory=list)


@dataclass
class AcMap:
    issue: int
    repo: str
    branch: str
    sha: str  # the commit the evidence ran on
    base: str  # what the diff was taken against: origin/main@abc1234
    sources: list[str]
    acs: list[AcMapping]
    notes: list[str] = field(default_factory=list)
    schema: int = SCHEMA

    def status(self, ac: int) -> AcMapping | None:
        return next((m for m in self.acs if m.ac == ac), None)

    def failed(self) -> list[int]:
        return [m.ac for m in self.acs if m.status == "failed"]

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------- the diff

_HUNK = re.compile(r"^@@ -\d+(?:,(?P<old>\d+))? \+(?P<start>\d+)(?:,(?P<new>\d+))? @@")
# A path that holds tests in common layouts: a tests/spec/e2e folder, test_x.py, x_test.go,
# x.test.js, x.spec.rb, XTest.java, XTests.cs.
_TEST_DIR = re.compile(r"(?:^|/)(?:tests?|__tests__|specs?|e2e|integration)/", re.I)
_TEST_FILE = re.compile(r"(?:^test_[^/]*|[._-](?:test|spec)s?\.[^/.]+(?:\.[^/.]+)?)$", re.I)
_TEST_CLASS = re.compile(r"[a-z0-9]Tests?\.[^/.]+$")
# Data and documents: never test code, even in a test folder (fixtures, snapshots).
_DATA_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc", ".json", ".jsonl", ".yaml",
                  ".yml", ".toml", ".xml", ".html", ".htm", ".csv", ".snap", ".log",
                  ".lock", ".patch", ".diff", ".svg"}
_LITERAL = re.compile(r"""(?P<q>['"`])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)""")
_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    if PurePosixPath(path).suffix.lower() in _DATA_SUFFIXES:
        return False
    return bool(_TEST_DIR.search(path) or _TEST_FILE.search(name) or _TEST_CLASS.search(name))


def _tag(issue: int) -> re.Pattern:
    """``#N AC1``, ``#N AC3 AC4``, ``#N AC1, AC2``; never ``#N0 AC1`` or ``#N AC10`` as AC1."""
    return re.compile(rf"(?<![\w#])#{issue}(?!\d)(?P<acs>(?:\s*(?:,|&|/|\+|and)?\s*"
                      rf"AC\d+(?!\d))+)")


def _identifier(issue: int) -> re.Pattern:
    """``test_N_ac2_x``, ``testN_AC2``, ``TestN_AC2X``: a test function named after the AC."""
    return re.compile(rf"\b(?P<name>[Tt]est_?{issue}_?[Aa][Cc](?P<ac>\d+)(?!\d)\w*)")


def branch_diff(git: Git, base_ref: str, sha: str) -> str:
    """What the story branch adds: ``git diff <base>...<sha>`` without context lines."""
    try:
        return git.run(["-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff",
                        "--no-textconv", "--unified=0", "--src-prefix=a/", "--dst-prefix=b/",
                        f"{base_ref}...{sha}"])
    except GitError as err:
        raise AcMapError(f"cannot diff {sha[:7]} against {base_ref}: "
                         f"{err.stderr.strip() or err}") from None


def added_lines(diff: str) -> list[tuple[str, int, str]]:
    """``(file, line number, text)`` of every line the diff adds, read hunk by hunk, so
    an added line that starts with ``++`` is never taken for a file header."""
    found: list[tuple[str, int, str]] = []
    file: str | None = None
    old_left = new_left = 0
    number = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if file is not None:
                    found.append((file, number, line[1:]))
                number += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            elif line.startswith("\\"):
                pass  # "\ No newline at end of file"
            else:
                number += 1
                old_left -= 1
                new_left -= 1
            continue
        if line.startswith("diff --git "):
            file = None
        elif line.startswith("+++ "):
            path = line[4:].rstrip("\t")
            file = None if path == "/dev/null" else path[2:] if path.startswith("b/") else path
        elif m := _HUNK.match(line):
            old_left = int(m["old"]) if m["old"] is not None else 1
            new_left = int(m["new"]) if m["new"] is not None else 1
            number = int(m["start"])
    return found


@dataclass(frozen=True)
class FoundTest:
    """A test the branch adds, and the ACs its name tags."""
    file: str
    line: int
    name: str | None
    acs: tuple[int, ...]
    pattern: re.Pattern | None = None


def find_tests(diff: str, issue: int) -> list[FoundTest]:
    """Every test the diff adds whose name carries ``#<issue> AC<n>``, in diff order."""
    tag, ident = _tag(issue), _identifier(issue)
    found: list[FoundTest] = []
    seen: set[tuple[str, str | None, tuple[int, ...]]] = set()

    def add(file: str, number: int, name: str | None, acs: list[int], template=False):
        key = (file, name, tuple(sorted(set(acs))))
        if key in seen:
            return
        seen.add(key)
        found.append(FoundTest(file, number, name, key[2],
                               None if name is None else name_pattern(name, template)))

    for file, number, text in added_lines(diff):
        if not is_test_file(file):
            continue
        spans = []
        for lit in _LITERAL.finditer(text):
            spans.append(lit.span())
            body = lit["body"]
            if m := tag.search(body):
                template = lit["q"] == "`" and "${" in body
                add(file, number, _unescape(body), _acs(m), template)
        for m in ident.finditer(text):
            add(file, number, m["name"], [int(m["ac"])])
        for m in tag.finditer(text):
            if not any(start <= m.start() < end for start, end in spans):
                add(file, number, None, _acs(m))
    return found


def _acs(match: re.Match) -> list[int]:
    return [int(n) for n in re.findall(r"AC(\d+)", match["acs"])]


def _unescape(body: str) -> str:
    return re.sub(r"\\(.)", r"\1", body)


def name_pattern(name: str, template: bool = False) -> re.Pattern:
    """The test's name as it appears in results: whole, never as part of a longer word.
    A ``${…}`` placeholder of a template literal matches whatever it became."""
    parts = _PLACEHOLDER.split(name) if template else [name]
    body = r".+?".join(re.escape(p) for p in parts)
    return re.compile(rf"(?<!\w){body}(?!\w)")


# ----------------------------------------------------------------------------- results

# Result marks, looked for in a line once the test's name is taken out of it.
_FAIL_MARK = re.compile(r"^\s*(?:[✘✗×✕]|x)\s|\s[✘✗×✕]\s|\b(?:FAIL|FAILED|ERROR)\b")
_SKIP_MARK = re.compile(r"^\s*(?:-|↓|○)\s|\b(?:SKIP|SKIPPED)\b|\.\.\.\s*(?:skipped|ignored)\b")
_PASS_MARK = re.compile(r"^\s*(?:[✓✔√]|ok)\s|\s[✓✔√]\s|\b(?:PASS|PASSED)\b|\.\.\.\s*ok\s*$")


def line_mark(rest: str) -> str | None:
    """The result a line shows (with the test's name removed), or ``None``."""
    if _FAIL_MARK.search(rest):
        return "failed"
    if _SKIP_MARK.search(rest):
        return "skipped"
    if _PASS_MARK.search(rest):
        return "passed"
    return None


def _owners(text: str, tests: list[FoundTest]) -> tuple[list[int], tuple[int, int] | None]:
    """The tests whose name ``text`` contains, keeping only the longest match, and its
    span: ``#9 AC1: adds`` never takes the result of ``#9 AC1: adds twice``."""
    best: list[int] = []
    span, longest = None, -1
    for index, test in enumerate(tests):
        if test.pattern is None:
            continue
        m = test.pattern.search(text)
        if m is None:
            continue
        size = m.end() - m.start()
        if size > longest:
            best, span, longest = [index], m.span(), size
        elif size == longest:
            best.append(index)
    return best, span


def output_results(output: str, tests: list[FoundTest]) -> dict[int, list[str]]:
    """The result marks each test gets from the lines of the test command's output."""
    results: dict[int, list[str]] = {}
    for line in clean_lines(output):
        owners, span = _owners(line, tests)
        if not owners or span is None:
            continue
        mark = line_mark(line[:span[0]] + " " + line[span[1]:])
        if mark is None:
            continue
        for index in owners:
            results.setdefault(index, []).append(mark)
    return results


def report_cases(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    """The format of a test report and its ``(full test name, result)`` cases. Raises
    ``AcMapError`` for a file that is no report this module reads."""
    text = data.lstrip(b"\xef\xbb\xbf").lstrip()
    if text.startswith(b"<"):
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as err:
            raise AcMapError(f"not valid XML: {err}") from None
        if root.tag not in ("testsuites", "testsuite"):
            raise AcMapError(f"not a JUnit report (root <{root.tag}>)")
        return "JUnit XML", [(case.get("name") or "", _junit_status(case))
                             for case in root.iter("testcase")]
    try:
        report = json.loads(text.decode("utf-8"))
    except ValueError as err:
        raise AcMapError(f"neither JUnit XML nor JSON: {err}") from None
    if isinstance(report, dict) and isinstance(report.get("testResults"), list):
        return "jest-style JSON", _jest_cases(report)
    if isinstance(report, dict) and isinstance(report.get("suites"), list):
        return "Playwright JSON", _playwright_cases(report["suites"], [])
    raise AcMapError("an unknown JSON report (expected `testResults` or `suites`)")


def _junit_status(case: ElementTree.Element) -> str:
    tags = {child.tag for child in case}
    if tags & {"failure", "error"}:
        return "failed"
    if "skipped" in tags:
        return "skipped"
    return "passed"


_JEST_STATUS = {"passed": "passed", "failed": "failed", "pending": "skipped",
                "skipped": "skipped", "todo": "skipped", "disabled": "skipped"}


def _jest_cases(report: dict) -> list[tuple[str, str]]:
    cases = []
    for suite in report["testResults"]:
        for case in (suite or {}).get("assertionResults") or []:
            if not isinstance(case, dict):
                continue
            name = case.get("fullName") or " ".join(
                [*(case.get("ancestorTitles") or []), case.get("title") or ""])
            cases.append((str(name), _JEST_STATUS.get(case.get("status"), "failed")))
    return cases


def _playwright_cases(suites: list, parents: list[str]) -> list[tuple[str, str]]:
    cases = []
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        titles = [*parents, str(suite.get("title") or "")]
        for spec in suite.get("specs") or []:
            statuses = [result.get("status") for test in spec.get("tests") or []
                        for result in test.get("results") or []]
            outcomes = [test.get("status") for test in spec.get("tests") or []]
            if any(s in ("failed", "timedOut", "interrupted") for s in statuses) or any(
                    o in ("unexpected", "flaky") for o in outcomes):
                status = "failed"
            elif "passed" in statuses:
                status = "passed"
            else:
                status = "skipped"
            cases.append((" › ".join([*titles, str(spec.get("title") or "")]), status))
        cases += _playwright_cases(suite.get("suites") or [], titles)
    return cases


def report_results(cases: list[tuple[str, str]], tests: list[FoundTest]
                   ) -> dict[int, list[str]]:
    results: dict[int, list[str]] = {}
    for name, status in cases:
        owners, _ = _owners(name, tests)
        for index in owners:
            results.setdefault(index, []).append(status)
    return results


def _combine(marks: list[str]) -> str:
    for status in ("failed", "passed", "skipped"):
        if status in marks:
            return status
    return "no-result"


# ----------------------------------------------------------------------------- the map


def build(*, issue: int, acs: list[int], evidence: Evidence, base: str, diff: str,
          output: str | None, output_note: str, reports: list[tuple[str, bytes]],
          notes: list[str] | None = None) -> AcMap:
    """Map every AC of the issue to the tests the diff adds and their recorded results."""
    if not acs:
        raise AcMapError(f"issue #{issue} has no `- [ ] AC<n>: …` lines to map")
    tests = find_tests(diff, issue)
    notes = list(notes or [])
    sources: list[str] = []
    marks: dict[int, list[tuple[str, str]]] = {}
    for path, data in reports:
        try:
            kind, cases = report_cases(data)
        except AcMapError as err:
            notes.append(f"report {path} was not used: {err}")
            continue
        sources.append(f"report {path} ({kind}, {len(cases)} cases)")
        for index, found in report_results(cases, tests).items():
            marks.setdefault(index, []).extend((m, f"report {path}") for m in found)
    if output is not None:
        sources.append(output_note)
        for index, found in output_results(output, tests).items():
            marks.setdefault(index, []).extend((m, "output") for m in found)
    else:
        notes.append(f"no test output: {output_note}")

    mapped: dict[int, list[MappedTest]] = {ac: [] for ac in acs}
    for index, test in enumerate(tests):
        got = marks.get(index, [])
        status = _combine([m for m, _ in got])
        source = next((s for m, s in got if m == status), "")
        name = None if test.name is None else _cut(test.name)
        for ac in test.acs:
            if ac in mapped:
                mapped[ac].append(MappedTest(test.file, test.line, name, status, source))
            else:
                notes.append(f"{test.file}:{test.line} tags AC{ac}, which issue #{issue} "
                             "does not have")
        if test.name is None:
            notes.append(f"{test.file}:{test.line} has the tag outside a test name (a "
                         "comment?); only a test named `#N AC<n>: …` can pass")
    return AcMap(issue=issue, repo=evidence.repo, branch=evidence.branch, sha=evidence.sha,
                 base=base, sources=sources,
                 acs=[AcMapping(ac, ac_status(mapped[ac]), mapped[ac]) for ac in acs],
                 notes=list(dict.fromkeys(notes)))


def ac_status(tests: list[MappedTest]) -> str:
    statuses = {t.status for t in tests}
    if "failed" in statuses:
        return "failed"
    return "passed" if "passed" in statuses else "missing"


def _cut(name: str) -> str:
    return name if len(name) <= MAX_NAME else name[:MAX_NAME] + " …[cut]"


# ----------------------------------------------------------------------------- storage


def default_path(issue: int) -> Path:
    """``<SCRATCH>/acmap-<N>.json``, ``<SCRATCH>`` being the system temp directory."""
    return Path(tempfile.gettempdir()) / f"acmap-{issue}.json"


def write(acmap: AcMap, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(acmap.to_dict(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def read(path: Path) -> AcMap:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise AcMapError(f"cannot read {path}: {err}") from None
    except ValueError as err:
        raise AcMapError(f"{path} is not valid JSON: {err}") from None
    return from_dict(data)


def from_dict(data: Any) -> AcMap:
    """Rebuild a map from its JSON form, refusing anything malformed or inconsistent: an
    AC's status must be the one its tests give it."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise AcMapError(f"not an AC-to-test map of schema {SCHEMA}")
    try:
        acs = [AcMapping(a["ac"], a["status"], [MappedTest(**t) for t in a["tests"]])
               for a in data["acs"]]
        acmap = AcMap(**{**data, "acs": acs})
    except (KeyError, TypeError) as err:
        raise AcMapError(f"malformed AC-to-test map: {err}") from None
    if not isinstance(acmap.issue, int) or not re.fullmatch(r"[0-9a-f]{40}", str(acmap.sha)):
        raise AcMapError("the AC-to-test map does not name its issue and full commit SHA")
    numbers = [a.ac for a in acmap.acs]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        raise AcMapError("the AC-to-test map must list AC1…ACn in order")
    for a in acmap.acs:
        if any(t.status not in TEST_STATUSES for t in a.tests):
            raise AcMapError(f"AC{a.ac}: unknown test status")
        if a.status not in AC_STATUSES or a.status != ac_status(a.tests):
            raise AcMapError(f"AC{a.ac}: status {a.status!r} does not follow from its tests")
    return acmap


def to_block(acmap: AcMap) -> str:
    """The map as a block for the checkpoint note: a headline, then the JSON on one line,
    escaped like the evidence so no test name can end the block or fake a marker."""
    payload = json.dumps(acmap.to_dict(), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("`", "\\u0060")
    if len(payload) > NOTE_BUDGET:
        raise AcMapError(f"the AC-to-test map is {len(payload)} characters, more than the "
                         f"{NOTE_BUDGET} the checkpoint note has room for")
    return (f"{MAP_START}\n**AC-to-test map** (`verify map`) @ `{acmap.sha[:7]}`: "
            f"{headline(acmap)}\n\n```json\n{payload}\n```\n{MAP_END}")


def from_body(body: str) -> AcMap | None:
    """The map in a checkpoint comment body, or ``None`` if it has none."""
    block = map_block(body)
    if block is None:
        return None
    start, end = block.find("```json\n"), block.rfind("\n```")
    if start < 0 or end <= start:
        raise AcMapError("the checkpoint's AC-to-test map block has no JSON")
    try:
        data = json.loads(block[start + len("```json\n"):end])
    except ValueError as err:
        raise AcMapError(f"the checkpoint's AC-to-test map is not valid JSON: {err}") from None
    return from_dict(data)


# ----------------------------------------------------------------------------- rendering


def headline(acmap: AcMap) -> str:
    return ", ".join(f"AC{a.ac} {a.status}" for a in acmap.acs)


def _count(tests: list[MappedTest]) -> str:
    counts = {s: sum(t.status == s for t in tests) for s in TEST_STATUSES}
    parts = [f"{n} {s.replace('-', ' ')}" for s, n in counts.items() if n]
    return f"{len(tests)} test(s): " + ", ".join(parts) if tests else "no test in the diff"


def render(acmap: AcMap, path: Path | None = None) -> str:
    lines = [f"AC-to-test map for #{acmap.issue} on {acmap.branch} @ {acmap.sha[:7]} "
             f"(tests added since {acmap.base})"]
    lines += [f"  results from: {source}" for source in acmap.sources]
    for a in acmap.acs:
        lines.append(f"  AC{a.ac:<3} {a.status:<8} {_count(a.tests)}")
        for t in a.tests:
            name = t.name if t.name is not None else "(tag outside a test name)"
            lines.append(f"         {t.status:<10} {t.file}:{t.line}  {name}")
    lines += [f"  note: {note}" for note in acmap.notes]
    if path is not None:
        lines.append(f"Written to {path} and to the checkpoint note.")
    failed = acmap.failed()
    missing = [a.ac for a in acmap.acs if a.status == "missing"]
    if failed:
        lines.append("FAILING: a mapped test failed for " + _names(failed) + ".")
    if missing:
        lines.append("NO PASSING TEST: " + _names(missing) + ". The verdict may not say "
                     "pass for these: add a test named `#N AC<n>: ...`, or mark the AC "
                     "not-verifiable with written manual steps.")
    if not failed and not missing:
        lines.append("OK: every AC has a mapped test that passed.")
    return "\n".join(lines)


def _names(numbers: list[int]) -> str:
    return ", ".join(f"AC{n}" for n in numbers)
