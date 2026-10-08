"""The AC verifier's verdict, and ``factory.py verdict check`` (T3.4).

The ``ac-verifier`` subagent (``.claude/agents/ac-verifier.md``, architecture §4.5)
answers S10 with one line per acceptance criterion, then one line for the test suite::

    - [x] AC1 — pass — evidence: `tests/test_invoices.py::test_12_ac1_adds_a_line` passed
    - [ ] AC2 — fail — evidence: `test_12_ac2_rejects_a_negative_amount` failed: expected …
    - [ ] AC3 — not-verifiable — manual steps: print the invoice to PDF and check …
    Suite: fail — `python -m pytest` → 14 passed, 1 failed

S11 copies the AC lines into the PR unchanged (rule H5). ``check()`` makes the rules
objective instead of trusting the text:

* **No verdict without evidence.** ``pass`` and ``fail`` need ``evidence: …``;
  ``not-verifiable`` needs ``reason: …`` or ``manual steps: …``. Placeholders such as
  ``n/a`` or ``TBD`` do not count.
* **One line per criterion**, AC1…ACn in order, exactly the issue's criteria.
* **The box matches the verdict**: ``[x]`` only for ``pass``.
* **A failure stops S11**: a ``fail`` on any criterion, or ``Suite: fail``, makes the
  verdict failing. ``Suite: skipped`` is allowed only as ``commands.test is null``.

``cross_check()`` (T6.2) holds the verdict against the AC-to-test map that ``verify map``
built from the recorded run, so the verifier's word is no longer the only proof:

* a ``pass`` needs a mapped test that passed;
* a ``not-verifiable`` may not hide a mapped test that failed;
* an AC with no test in the diff must be ``not-verifiable`` with ``manual steps: …``.

Parsing is pure and never raises on input text; problems are returned as strings.
"""

import re
from dataclasses import dataclass, field

from factory.acmap import AcMap, AcMapping
from factory.comments import find_checkpoint, list_comments
from factory.errors import FactoryError
from factory.gh import Gh

VERDICTS = ("pass", "fail", "not-verifiable")
_DASH = r"\s+(?:—|–|--?)\s+"
_AC_LINE = re.compile(rf"^- \[(?P<box>[ xX])\] AC(?P<n>\d+){_DASH}(?P<verdict>[a-z-]+)"
                      rf"{_DASH}(?P<rest>.*)$")
_SUITE_LINE = re.compile(rf"^Suite:\s*(?P<result>pass|fail|skipped){_DASH}(?P<rest>.*)$")
_EVIDENCE = re.compile(r"^(?P<kind>evidence|reason|manual steps):\s*(?P<text>.*)$", re.I)
_EMPTY = re.compile(r"^(?:n/?a|none|tbd|todo|-+|\.+|\?+|unknown)?$", re.I)
_ISSUE_AC = re.compile(r"^- \[[ xX]\] AC(?P<n>\d+):", re.M)


class VerdictError(FactoryError):
    """The verdict could not be read."""


@dataclass(frozen=True)
class AcVerdict:
    number: int
    verdict: str
    checked: bool
    kind: str  # evidence | reason | manual steps
    text: str
    line: str


@dataclass
class Verdict:
    acs: list[AcVerdict] = field(default_factory=list)
    suite: str | None = None  # pass | fail | skipped
    suite_text: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def failing(self) -> bool:
        return self.suite == "fail" or any(a.verdict == "fail" for a in self.acs)

    @property
    def ok(self) -> bool:
        """Well-formed, complete and not failing: S11 may copy it into a ready PR."""
        return not self.problems and not self.failing


def parse(text: str, expected: list[int] | None = None) -> Verdict:
    """Read a verdict and check it against the rules. ``expected``: the issue's AC numbers."""
    result = Verdict()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if m := _AC_LINE.match(line):
            _add_ac(result, m, line)
        elif m := _SUITE_LINE.match(line):
            if result.suite is not None:
                result.problems.append("more than one Suite line")
            result.suite, result.suite_text = m["result"], m["rest"].strip()
        elif re.match(r"^- \[[ xX]\]\s*AC\d+", line) or line.startswith("Suite:"):
            result.problems.append(f"malformed line: {line!r} (expected "
                                   "`- [x] AC<n> — <verdict> — evidence: …` or "
                                   "`Suite: <pass|fail|skipped> — …`)")

    numbers = [a.number for a in result.acs]
    if not numbers:
        result.problems.append("no AC verdict lines")
    elif numbers != list(range(1, len(numbers) + 1)):
        result.problems.append("AC lines must be AC1…ACn, in order, each once; got "
                               + ", ".join(f"AC{n}" for n in numbers))
    if expected is not None and numbers and numbers != expected:
        result.problems.append("the verdict must cover exactly the issue's acceptance "
                               f"criteria: the issue has {_names(expected)}, the verdict "
                               f"has {_names(numbers)}")
    if result.suite is None:
        result.problems.append("missing the `Suite: <pass|fail|skipped> — …` line")
    elif result.suite == "skipped" and "commands.test is null" not in result.suite_text:
        result.problems.append("Suite: skipped is only allowed as `commands.test is null`")
    elif result.suite in ("pass", "fail") and _EMPTY.match(result.suite_text):
        result.problems.append("the Suite line needs the command and its real result")
    return result


def _names(numbers: list[int]) -> str:
    return ", ".join(f"AC{n}" for n in numbers) or "none"


def _add_ac(result: Verdict, m: re.Match, line: str) -> None:
    n, verdict, checked = int(m["n"]), m["verdict"], m["box"] in "xX"
    evidence = _EVIDENCE.match(m["rest"].strip())
    kind = evidence["kind"].lower() if evidence else ""
    text = evidence["text"].strip() if evidence else ""
    result.acs.append(AcVerdict(n, verdict, checked, kind, text, line))
    if verdict not in VERDICTS:
        result.problems.append(f"AC{n}: unknown verdict {verdict!r}; use one of "
                               + ", ".join(VERDICTS))
        return
    if checked != (verdict == "pass"):
        result.problems.append(f"AC{n}: the box must be [x] only for pass")
    wanted = ("evidence",) if verdict != "not-verifiable" else ("reason", "manual steps")
    if kind not in wanted or _EMPTY.match(text):
        result.problems.append(f"AC{n}: {verdict} needs " + " or ".join(
            f"`{w}: …`" for w in wanted) + " with concrete content (no verdict without "
            "evidence)")


def issue_acs(body: str) -> list[int]:
    """The AC numbers of a story issue body (``- [ ] AC<n>: …`` lines)."""
    return [int(n) for n in _ISSUE_AC.findall(body or "")]


def checkpoint_body(gh: Gh, repo: str, number: int) -> str | None:
    """The body of the issue's checkpoint comment, or ``None`` if it has none."""
    found = find_checkpoint(list_comments(gh, repo, number))
    return None if found is None else (found[0].get("body") or "").replace("\r\n", "\n")


def checkpoint_note(gh: Gh, repo: str, number: int, body: str | None = None) -> str:
    """The note of the issue's checkpoint comment: where S10 stores the verdict."""
    body = checkpoint_body(gh, repo, number) if body is None else body
    if body is None:
        raise VerdictError(f"issue #{number} has no checkpoint comment; run S10 first")
    # compose(): the marker and the "**Factory checkpoint:** …" line, a blank line, the note.
    parts = body.split("\n\n", 1)
    return parts[1] if len(parts) == 2 else ""


def cross_check(verdict: Verdict, acmap: AcMap, *, issue: int,
                evidence_sha: str | None = None) -> list[str]:
    """Why the verdict disagrees with the AC-to-test map of the recorded run; empty if
    it agrees. Every problem makes the verdict INVALID."""
    problems = []
    if acmap.issue != issue:
        return [f"the AC-to-test map is for issue #{acmap.issue}, not #{issue}; run "
                "`verify map` again"]
    if evidence_sha is not None and acmap.sha != evidence_sha:
        problems.append(f"the AC-to-test map is for commit {acmap.sha[:7]}, but the evidence "
                        f"is for {evidence_sha[:7]}; run `verify map` again")
    mapped = [m.ac for m in acmap.acs]
    stated = [a.number for a in verdict.acs]
    if stated and mapped != stated:
        problems.append(f"the AC-to-test map has {_names(mapped)}, the verdict has "
                        f"{_names(stated)}; run `verify map` again")
    for a in verdict.acs:
        m = acmap.status(a.number)
        if m is None:
            continue
        if a.verdict == "pass" and m.status != "passed":
            problems.append(f"AC{a.number}: the verifier says pass, but {_why(m, issue)}")
        elif not m.tests and a.verdict != "not-verifiable":
            problems.append(f"AC{a.number}: no test is named `#{issue} AC{a.number}` in the "
                            "branch diff, so the verdict must be not-verifiable with "
                            "written `manual steps: …`")
        if not m.tests and a.verdict == "not-verifiable" and a.kind != "manual steps":
            problems.append(f"AC{a.number}: it has no test, so not-verifiable needs written "
                            "`manual steps: …`, not only a reason")
        if m.status == "failed" and a.verdict == "not-verifiable":
            problems.append(f"AC{a.number}: a mapped test failed ({_listed(m, 'failed')}), "
                            "so the verdict must be fail, not not-verifiable")
    return problems


def _why(m: AcMapping, issue: int) -> str:
    if m.status == "failed":
        return f"its mapped test failed: {_listed(m, 'failed')}"
    if not m.tests:
        return f"no test is named `#{issue} AC{m.ac}` in the branch diff"
    return ("none of its mapped tests passed in the recorded run: "
            + "; ".join(f"`{t.name or t.file}` {t.status.replace('-', ' ')}"
                        for t in m.tests[:3]) + ("; …" if len(m.tests) > 3 else ""))


def _listed(m: AcMapping, status: str) -> str:
    return "; ".join(f"`{t.name or t.file}`" for t in m.tests if t.status == status)


def render(verdict: Verdict, acmap: AcMap | None = None, *, mapped: bool = False) -> str:
    """The verdict's summary. ``mapped``: say whether it was held against an AC-to-test
    map (``acmap``) or checked on its own, because none was stored yet."""
    counts = {v: sum(a.verdict == v for a in verdict.acs) for v in VERDICTS}
    lines = [f"Verdict: {len(verdict.acs)} AC(s): {counts['pass']} pass, {counts['fail']} "
             f"fail, {counts['not-verifiable']} not-verifiable; suite {verdict.suite or '?'}"]
    if acmap is not None:
        lines.append(f"  AC-to-test map @ {acmap.sha[:7]}: " + ", ".join(
            f"AC{a.ac} {a.status}" for a in acmap.acs))
    elif mapped:
        lines.append("  AC-to-test map: none stored; the verdict was checked on its own "
                     "(run `verify map` to hold it against the recorded tests)")
    lines += [f"  problem: {p}" for p in verdict.problems]
    if verdict.problems:
        lines.append("INVALID: the verdict breaks the rules above; S10 must obtain a new one.")
    elif verdict.failing:
        lines.append("FAILING: an AC or the suite failed; S11 must not open a ready PR.")
    else:
        lines.append("OK: every AC has evidence and nothing failed.")
    return "\n".join(lines)
