"""T6.4: ``factory.py trace <file>:<line>``, from a line of code to its PRD section.

Offline: the histories are temporary git repositories, and GitHub's answers are recorded.

* ``TaskTrackerTest`` clones ``fixtures/trace/task-tracker.bundle``, the Task Tracker test
  project's real history up to PR #30, so its commits have their real SHAs, and replays
  ``fixtures/trace/task-tracker-github.json``, GitHub's recorded answers for those commits
  and their issues (trimmed to the fields ``trace`` reads). The bundle and the cassette
  were made from the real repo on 2026-10-21; re-record them only if that history changes.
* ``HistoryShapeTest`` builds a small repo for each way a PR can be merged (a merge
  commit, a squash, a rebase), with GitHub's answers written in the same shape.
"""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, target, trace
from factory.gh import Gh, ProcessResult
from factory.gh_fixtures import FakeGh, load_cassette
from factory.git import Git
from factory.markers import PrMarker, StoryMarker, build

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "trace"
TT_REPO = "Nandan-krishnamurthy/task-tracker-factory-test"
IDENTITY = ["-c", "user.name=factory", "-c", "user.email=factory@example.invalid"]
PR29_MERGE = "86916d4194c3ce71764c5e2e4b40d56193543fd3"
PR30_MERGE = "1661f6343c04e6c40bdb3cc95faddbcd9b79d2e5"
INC2 = "docs/factory/increments/002-add-due-dates"


def hunk_ends(git: Git, merge: str) -> list[tuple[str, int]]:
    """The first and last line of every hunk a merge added, in the merged tree."""
    found, path = [], None
    for line in git.run(["diff", "-U0", f"{merge}^1", merge]).splitlines():
        if line.startswith("+++ "):
            path = None if line == "+++ /dev/null" else line[len("+++ b/"):]
        elif (m := re.match(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)) and path:
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            if count:
                found += [(path, start), (path, start + count - 1)]
    return list(dict.fromkeys(found))


# ----------------------------------------------------------------------------- pure


class ParseTest(unittest.TestCase):
    def test_spec(self):
        root = Path(tempfile.gettempdir()) / "app"
        self.assertEqual(trace.parse_spec("src/ui/render.ts:12", root), ("src/ui/render.ts", 12))
        self.assertEqual(trace.parse_spec(r"src\ui\render.ts:3", root), ("src/ui/render.ts", 3))
        self.assertEqual(trace.parse_spec(f"{root / 'src' / 'a.py'}:7", root), ("src/a.py", 7))
        for bad in ("src/a.py", "src/a.py:0", "src/a.py:x", "../b/a.py:1",
                    f"{root.parent / 'other' / 'a.py'}:1"):
            with self.subTest(bad), self.assertRaises(trace.TraceError):
                trace.parse_spec(bad, root)

    def test_blame(self):
        porcelain = ("a" * 40 + " 3 5 1\nauthor x\nsummary feat: a thing (#27)\n"
                     "filename src/a.ts\n\tconst A = 1;\n")
        self.assertEqual(trace.parse_blame(porcelain),
                         ("a" * 40, "feat: a thing (#27)", "const A = 1;"))
        with self.assertRaises(trace.TraceError):
            trace.parse_blame("")

    def test_closes_issue(self):
        self.assertEqual(trace.closes_issue("<!-- factory:pr story=STORY-013 -->\nCloses #27\n"),
                         27)
        self.assertEqual(trace.closes_issue("Summary\n\nfixes #8 and more"), 8)
        self.assertIsNone(trace.closes_issue("Mentions #27, closes nothing"))

    def test_traces_to(self):
        body = "## Story\nREQ-001 here is prose\n\n## Traces to\nREQ-022, REQ-023\nREQ-022\n\n" \
               "## Acceptance criteria\n- [ ] AC1: REQ-099\n"
        self.assertEqual(trace.traces_to(body), ["REQ-022", "REQ-023"])
        self.assertEqual(trace.traces_to("no section"), [])

    def test_prd_citations(self):
        cases = {
            "- **REQ-022** (PRD §Add due dates to tasks): In the Active view, …":
                ["Add due dates to tasks"],
            "- **REQ-001** (PRD §Functional requirements FR-001, §Journey 1): When …":
                ["Functional requirements FR-001", "Journey 1"],
            '- **REQ-010** (PRD §Goals: "filtered by status: active and completed"): …':
                ['Goals: "filtered by status: active and completed"'],
            "- **REQ-030** (no citation): …": [],
        }
        for line, expected in cases.items():
            with self.subTest(line):
                self.assertEqual(trace.prd_citations(line), expected)

    def test_match_prd(self):
        prd = ("# PRD: App\n\n## Goals\n- Tasks filtered by status: active and completed.\n\n"
               "## Functional requirements\n| ID | Requirement |\n|---|---|\n"
               "| FR-001 | Create a task |\n| FR-002 | Due dates |\n\n"
               "### Journey 1: Capture a new task\nSteps.\n\n"
               "## Non-functional requirements\n- **Performance:** under 100 ms.\n"
               "## Decisions\n- FR-001 is final.\n")
        cases = {
            "Goals": ((3, "## Goals"), None),
            "Functional requirements FR-002": ((6, "## Functional requirements"),
                                               (10, "| FR-002 | Due dates |")),
            "Journey 1": ((12, "### Journey 1: Capture a new task"), None),
            'Non-functional requirements "Performance"': (
                (15, "## Non-functional requirements"), (16, "- **Performance:** under 100 ms.")),
            'Goals: "filtered by status: active and completed"': (
                (3, "## Goals"), (4, "- Tasks filtered by status: active and completed.")),
            # The detail is looked for only inside the heading's own section.
            "Non-functional requirements FR-001": ((15, "## Non-functional requirements"), None),
            "Nowhere": (None, None),
        }
        for section, expected in cases.items():
            with self.subTest(section):
                self.assertEqual(trace.match_prd(prd, section), expected)

    def test_match_prd_without_headings(self):
        # A change request of one line, like Task Tracker's increment 002.
        self.assertEqual(trace.match_prd("Add due dates to tasks\n", "Add due dates to tasks"),
                         ((1, "Add due dates to tasks"), None))

    def test_matrix_line(self):
        text = "| REQ | Stories |\n|---|---|\n| REQ-002 | x |\n| REQ-022 | STORY-013 (#27) |\n"
        self.assertEqual(trace.matrix_line(text, "REQ-022"), (4, "| REQ-022 | STORY-013 (#27) |"))
        self.assertIsNone(trace.matrix_line(text, "REQ-003"))

    def test_first_merged(self):
        prs = [{"number": 9, "merged_at": None},
               {"number": 7, "merged_at": "2026-10-02T00:00:00Z"},
               {"number": 5, "merged_at": "2026-10-01T00:00:00Z"}]
        self.assertEqual(trace.first_merged(prs)["number"], 5)
        self.assertIsNone(trace.first_merged([{"number": 9, "merged_at": None}]))


# ----------------------------------------------------------------------------- Task Tracker


class TaskTrackerTest(unittest.TestCase):
    """Acceptance criterion: ``trace`` on any line changed by PR #29 or PR #30 reaches the
    REQ and the PRD in one command."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "task-tracker"
        Git(cls._tmp.name).run(["clone", "-q", str(FIXTURES / "task-tracker.bundle"),
                                str(cls.root)])
        cls.git = Git(cls.root)
        cls.cassette = load_cassette(FIXTURES / "task-tracker-github.json")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_trace(self, spec, ref):
        return trace.trace(FakeGh(self.cassette), self.git, TT_REPO, self.root, spec, ref)

    def test_every_hunk_of_pr_29_and_pr_30(self):
        expected = {
            29: (PR29_MERGE, 27, "STORY-013", ["REQ-022", "REQ-023", "REQ-024", "REQ-025"]),
            30: (PR30_MERGE, 28, "STORY-014", ["REQ-026"]),
        }
        for pr, (merge, issue, story, reqs) in expected.items():
            lines = hunk_ends(self.git, merge)
            self.assertGreater(len(lines), 5)
            for path, number in lines:
                with self.subTest(pr=pr, line=f"{path}:{number}"):
                    t = self.run_trace(f"{path}:{number}", merge)
                    self.assertTrue(t.complete, t.gaps())
                    self.assertEqual((t.pr, t.issue, t.story, t.merge_sha),
                                     (pr, issue, story, merge))
                    self.assertEqual([r.req for r in t.requirements], reqs)
                    for r in t.requirements:
                        self.assertEqual(r.definition.path, f"{INC2}/02-requirements.md")
                        self.assertEqual([(p.section, p.heading.path, p.heading.line)
                                          for p in r.prd],
                                         [("Add due dates to tasks", f"{INC2}/00-prd.md", 1)])
                        self.assertTrue(r.matrix.text.startswith(f"| {r.req} | {story} "))

    def test_the_rendered_chain_has_a_link_for_every_hop(self):
        t = self.run_trace("index.html:13", PR30_MERGE)
        text = trace.render(t)
        base = f"https://github.com/{TT_REPO}"
        for link in (f"{base}/commit/{t.commit}", f"{base}/pull/30", f"{base}/issues/28",
                     f"{base}/blob/{PR30_MERGE}/{INC2}/02-requirements.md#L22",
                     f"{base}/blob/{PR30_MERGE}/{INC2}/00-prd.md#L1",
                     f"{base}/blob/{PR30_MERGE}/docs/factory/traceability.md#L36"):
            self.assertIn(link, text)
        self.assertRegex(text.splitlines()[-1], r"^Traced in \d+\.\d\ds: line → commit "
                                                r"\w{7} → PR #30 → issue #28 → REQ-026 → PRD\.$")


# ----------------------------------------------------------------------------- shapes


REPO = "owner/app"
INC = "001-initial"
DOCS = {
    f"docs/factory/increments/{INC}/00-prd.md":
        "# PRD: App\n\n## Goals\n- Fast.\n\n## Functional requirements\n| FR-001 | Greet |\n",
    f"docs/factory/increments/{INC}/02-requirements.md":
        "# Requirements\n\n- **REQ-001** (PRD §Functional requirements FR-001, §Goals): "
        "The app greets the user.\n- **REQ-002** (PRD §Nowhere): Unmatched.\n",
    "docs/factory/traceability.md":
        "| REQ | Stories | PRs | Tests | Status |\n|---|---|---|---|---|\n"
        "| REQ-001 | STORY-001 (#1) | #5 | — | Implemented |\n",
    "src/app.py": "def main():\n    pass\n",
}
STORY_BODY = (build(StoryMarker("STORY-001", INC)) + "\n**STORY-001**\n\n## Story\nGreet.\n\n"
              "## Traces to\nREQ-001\n\n## Acceptance criteria\n- [ ] AC1: greets\n")


class Repo:
    """A temporary target repo with the planning docs on ``main``."""

    def __init__(self, tmp: str):
        self.root = Path(tmp) / "app"
        self.root.mkdir()
        self.git = Git(self.root)
        self.git.run(["init", "-q", "-b", "main"])
        for path, text in DOCS.items():
            self.write(path, text)
        self.commit("docs: plan increment 001")

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message):
        self.git.run(["add", "-A"])
        self.git.run([*IDENTITY, "commit", "-qm", message])
        return self.git.rev_parse("HEAD")

    def story_commits(self, branch="story/1-greet"):
        """Two commits on a story branch: line 2 of src/app.py, then line 3."""
        self.git.run(["switch", "-q", "-c", branch])
        self.write("src/app.py", "def main():\n    print('hello')\n")
        first = self.commit("feat: greet (#1)")
        self.write("src/app.py", "def main():\n    print('hello')\n    return 0\n")
        second = self.commit("feat: return 0 (#1)")
        return first, second


class GitHub:
    """GitHub's answers, in the recorded shape: the PRs of each commit, PRs, issues."""

    def __init__(self, commit_prs: dict[str, list[dict]], prs=(), issues=None):
        self.commit_prs = commit_prs
        self.prs = {p["number"]: p for p in prs}
        self.issues = {1: {"number": 1, "state": "open", "body": STORY_BODY}} \
            if issues is None else issues
        self.calls: list[str] = []

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        endpoint = argv[2]
        self.calls.append(endpoint)
        if m := re.fullmatch(rf"repos/{REPO}/commits/(\w+)/pulls", endpoint):
            if m[1] not in self.commit_prs:
                return ProcessResult([], 1, "", "gh: No commit found for SHA (HTTP 422)")
            return self.ok(self.commit_prs[m[1]])
        if m := re.fullmatch(rf"repos/{REPO}/pulls/(\d+)", endpoint):
            return self.ok(self.prs[int(m[1])])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            return self.ok(self.issues[int(m[1])])
        raise AssertionError(f"unexpected call {argv}")

    @staticmethod
    def ok(data):
        return ProcessResult([], 0, json.dumps(data), "")


def pr(number=5, merge_sha="", body=None):
    return {"number": number, "state": "closed", "merged_at": "2026-10-07T10:00:00Z",
            "merge_commit_sha": merge_sha, "html_url": f"https://github.com/{REPO}/pull/{number}",
            "body": build(PrMarker("STORY-001")) + "\nCloses #1\n" if body is None else body}


class HistoryShapeTest(unittest.TestCase):
    """``trace`` on fixture history: a merge commit, a squash and a rebase."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Repo(tmp.name)

    def run_trace(self, github, spec="src/app.py:3", ref="HEAD"):
        return trace.trace(Gh(transport=github), self.repo.git, REPO, self.repo.root, spec, ref)

    def assert_reaches_the_prd(self, t, merge_sha, found_by):
        self.assertEqual((t.pr, t.issue, t.story, t.increment, t.merge_sha, t.found_by),
                         (5, 1, "STORY-001", INC, merge_sha, found_by))
        req1 = t.requirements[0]
        self.assertEqual(req1.req, "REQ-001")
        self.assertEqual(req1.definition.line, 3)
        self.assertEqual([(p.section, p.heading.text, p.detail and p.detail.text)
                          for p in req1.prd],
                         [("Functional requirements FR-001", "## Functional requirements",
                           "| FR-001 | Greet |"), ("Goals", "## Goals", None)])
        self.assertEqual(req1.matrix.line, 3)
        self.assertTrue(t.complete, t.gaps())

    def merge_commit(self):
        first, second = self.repo.story_commits()
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.git.run([*IDENTITY, "merge", "-q", "--no-ff", "-m",
                           "Merge pull request #5 from owner/story/1-greet", "story/1-greet"])
        return first, second, self.repo.git.rev_parse("HEAD")

    def test_merge_commit_found_by_the_api(self):
        first, second, merge = self.merge_commit()
        github = GitHub({second: [pr(merge_sha=merge)]})
        t = self.run_trace(github)
        self.assertEqual((t.commit, t.text), (second, "    return 0"))
        self.assert_reaches_the_prd(t, merge, trace.API)

    def test_merge_commit_found_by_the_fallback(self):
        # GitHub lists no PR for the commit: the merge commit's subject names it.
        first, second, merge = self.merge_commit()
        github = GitHub({}, prs=[pr(merge_sha=merge)])
        t = self.run_trace(github, "src/app.py:2")
        self.assertEqual(t.commit, first)
        self.assert_reaches_the_prd(t, merge, trace.MERGE_COMMIT)
        self.assertIn(f"repos/{REPO}/pulls/5", github.calls)

    def test_the_fallback_skips_merges_that_did_not_bring_the_commit_in(self):
        first, second, merge = self.merge_commit()
        # A later merge of another PR does not hold the commit in its second parent.
        self.repo.git.run(["switch", "-q", "-c", "story/2-other"])
        self.repo.write("README.md", "# app\n")
        self.repo.commit("docs: readme (#2)")
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.git.run([*IDENTITY, "merge", "-q", "--no-ff", "-m",
                           "Merge pull request #6 from owner/story/2-other", "story/2-other"])
        self.assertEqual(trace.merge_commit_pr(self.repo.git, second, "HEAD"), (5, merge))

    def test_squash(self):
        self.repo.story_commits()
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.git.run(["merge", "-q", "--squash", "story/1-greet"])
        squash = self.repo.commit("Greet the user (#5)")
        t = self.run_trace(GitHub({squash: [pr(merge_sha=squash)]}))
        self.assertEqual(t.commit, squash)
        self.assert_reaches_the_prd(t, squash, trace.API)

    def test_rebase(self):
        self.repo.story_commits()
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.write("README.md", "# app\n")  # main moved on, so the rebase rewrites
        self.repo.commit("docs: readme")
        self.repo.git.run(["switch", "-q", "story/1-greet"])
        self.repo.git.run([*IDENTITY, "rebase", "-q", "main"])
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.git.run(["merge", "-q", "--ff-only", "story/1-greet"])
        rebased = self.repo.git.rev_parse("HEAD")
        self.assertEqual(self.repo.git.run(["log", "-1", "--format=%s"]).strip(),
                         "feat: return 0 (#1)")
        t = self.run_trace(GitHub({rebased: [pr(merge_sha=rebased)]}))
        self.assertEqual(t.commit, rebased)
        self.assert_reaches_the_prd(t, rebased, trace.API)

    def test_a_squash_unknown_to_github_is_broken_at_the_pr(self):
        self.repo.story_commits()
        self.repo.git.run(["switch", "-q", "main"])
        self.repo.git.run(["merge", "-q", "--squash", "story/1-greet"])
        squash = self.repo.commit("Greet the user (#5)")
        t = self.run_trace(GitHub({}))
        self.assertFalse(t.complete)
        self.assertIsNone(t.pr)
        self.assertEqual(t.gaps(), [
            f"commit {squash[:7]}: {trace.API} lists no merged PR for it, and no `Merge pull "
            f"request #<P>` commit up to {t.ref[:7]} brought it in"])
        self.assertIn("Incomplete after", trace.render(t))

    def test_each_broken_hop_is_named(self):
        first, second, merge = self.merge_commit()
        no_marker = {1: {"number": 1, "body": "## Traces to\nREQ-001\n"}}
        no_reqs = {1: {"number": 1, "body": build(StoryMarker("STORY-001", INC)) + "\n"}}
        undefined = {1: {"number": 1, "body": STORY_BODY.replace("REQ-001", "REQ-009")}}
        unmatched = {1: {"number": 1, "body": STORY_BODY.replace("REQ-001", "REQ-002")}}
        cases = [
            (GitHub({second: [pr(merge_sha=merge, body="No issue here")]}),
             "PR #5 closes no issue (no `Closes #<I>` in its body)"),
            (GitHub({second: [pr(merge_sha=merge)]}, issues=no_marker),
             "issue #1 is not a factory story (no factory:story marker)"),
            (GitHub({second: [pr(merge_sha=merge)]}, issues=no_reqs),
             "issue #1 (STORY-001) has no REQ under **Traces to**"),
            (GitHub({second: [pr(merge_sha=merge)]}, issues=undefined),
             "REQ-009: no `**REQ-009**` definition in any 02-requirements.md"),
            (GitHub({second: [pr(merge_sha=merge)]}, issues=unmatched),
             "REQ-002: PRD §Nowhere matches no heading or line in 00-prd.md"),
        ]
        for github, gap in cases:
            with self.subTest(gap):
                t = self.run_trace(github)
                self.assertFalse(t.complete)
                self.assertEqual(t.gaps(), [gap])

    def test_the_line_as_it_is_at_ref(self):
        first, second, merge = self.merge_commit()
        github = GitHub({first: [pr(merge_sha=merge)]})
        t = self.run_trace(github, "src/app.py:2", ref=first)
        self.assertEqual((t.ref, t.commit), (first, first))
        with self.assertRaises(trace.TraceError):  # line 3 does not exist yet at that ref
            self.run_trace(github, "src/app.py:3", ref=first)
        with self.assertRaises(trace.TraceError):
            self.run_trace(github, "src/app.py:2", ref="no-such-ref")

    def test_the_elapsed_time_is_the_commands_own(self):
        first, second, merge = self.merge_commit()
        ticks = iter([10.0, 10.75])
        t = trace.trace(Gh(transport=GitHub({second: [pr(merge_sha=merge)]})), self.repo.git,
                        REPO, self.repo.root, "src/app.py:3", clock=lambda: next(ticks))
        self.assertEqual(t.elapsed_s, 0.75)
        self.assertTrue(trace.render(t).splitlines()[-1].startswith("Traced in 0.75s:"))
        self.assertEqual(t.to_dict()["elapsed_s"], 0.75)

    def test_cli(self):
        first, second, merge = self.merge_commit()
        github = GitHub({second: [pr(merge_sha=merge)]})
        for argv, code in ((["trace", "src/app.py:3", "--json"], 0),
                           (["trace", "src/app.py:3"], 0),
                           (["trace", "src/app.py:1"], 1)):  # line 1: the planning commit
            out = io.StringIO()
            with self.subTest(argv=argv), \
                    mock.patch.object(target, "get_target",
                                      lambda: target.Target(self.repo.root, REPO)), \
                    mock.patch.object(cli, "Gh", lambda: Gh(transport=github)), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(argv), code)
                text = out.getvalue()
                if "--json" in argv:
                    data = json.loads(text)
                    self.assertEqual((data["pr"]["number"], data["issue"]["number"],
                                      data["requirements"][0]["req"], data["complete"]),
                                     (5, 1, "REQ-001", True))
                elif code == 0:
                    self.assertTrue(text.startswith("Target: "))
                    self.assertIn("→ PR #5 → issue #1 → REQ-001 → PRD.", text)
                else:
                    self.assertIn("lists no merged PR", text)


if __name__ == "__main__":
    unittest.main()
