"""T5.3: the /factory-status report. Snapshot tests of the rendered output, one per state.

The expected reports are in ``tests/fixtures/status/<state>.txt``. After an intended change
to the report, regenerate them with ``FACTORY_UPDATE_SNAPSHOTS=1 python -m unittest
tests.test_status`` and review the diff of those files like any other change.
"""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, status, target
from factory import state as st
from factory.gh import Gh
from factory.markers import PlanningMarker, ReplyMarker, build
from factory.state import derive_state
from tests.test_state import (
    CONFIG,
    INC,
    PLAN,
    REJECTED_ROW,
    STATE_TABLE,
    FakeRepo,
    ts,
)

SNAPSHOTS = Path(__file__).resolve().parent / "fixtures" / "status"
UPDATE = os.environ.get("FACTORY_UPDATE_SNAPSHOTS") == "1"
# Every Done case of requirements §11, against the story PRs of STATE_TABLE (#20, maybe #21).
TRACEABILITY = """# Traceability

| REQ | Stories | PRs | Tests | Status |
|---|---|---|---|---|
| REQ-001 | STORY-001 (#10) | #20 | `a.test.ts › #10 AC1` | Implemented |
| REQ-002 | STORY-001 (#10), STORY-002 (#11) | #20, #21 | `b.test.ts` | Implemented |
| REQ-003 | STORY-002 (#11) | #21 | — | In progress |
| REQ-004 | STORY-002 | — | — | Not started |
| REQ-005 | — | — | — | Deferred |
| REQ-006 | STORY-001 (#10) | — | — | Implemented |
"""
STORY_PHASE = {st.IDLE_AT_GATE_C, st.STORY_IN_PROGRESS, st.GATE_B_WAITING_REVIEW,
               st.GATE_B_CHANGES_REQUESTED, st.GATE_B_APPROVED_UNMERGED, st.CLOSEOUT_PENDING,
               st.INCREMENT_COMPLETE, st.NEEDS_HUMAN, st.INCONSISTENT}


def slug(row: str) -> str:
    return "REJECTED_STORY_PR" if row == REJECTED_ROW else row


def report_for(row: str) -> status.Report:
    """The report for one STATE_TABLE row. Review states get 2 comments without /changes;
    story-phase states get the sample traceability matrix (planning has none yet)."""
    snapshot, state, _, _ = STATE_TABLE[row]
    result = derive_state(snapshot).to_dict()
    assert result["state"] == state, (row, result["state"])
    matrix = TRACEABILITY if state in STORY_PHASE else None
    comments = 2 if state in (st.GATE_A_WAITING, st.GATE_B_WAITING_REVIEW) else 0
    return status.build(result, snapshot, matrix, comments)


class RenderedSnapshotTest(unittest.TestCase):
    """The rendered report for every state of the architecture §6 table."""

    def test_every_state_matches_its_snapshot(self):
        for row in STATE_TABLE:
            with self.subTest(state=row):
                text = status.render(report_for(row)) + "\n"
                path = SNAPSHOTS / f"{slug(row)}.txt"
                if UPDATE:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8", newline="\n")
                self.assertTrue(path.is_file(), f"missing snapshot {path.name}; run with "
                                                "FACTORY_UPDATE_SNAPSHOTS=1")
                self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_no_stale_snapshots(self):
        expected = {f"{slug(row)}.txt" for row in STATE_TABLE}
        self.assertEqual({p.name for p in SNAPSHOTS.glob("*.txt")}, expected)

    def test_every_state_is_covered(self):
        covered = {derive_state(STATE_TABLE[row][0]).state for row in STATE_TABLE}
        self.assertEqual(covered, set(st.STATES))


class NextLineTest(unittest.TestCase):
    """Acceptance criterion: "what do I do next?" in a single line at the top."""

    def test_the_first_line_is_the_next_action_for_every_state(self):
        for row in STATE_TABLE:
            with self.subTest(state=row):
                report = report_for(row)
                first = status.render(report).splitlines()[0]
                self.assertEqual(first, f"Next: {report.next_action}")
                self.assertNotIn("\n", report.next_action)
                self.assertNotIn("None", first)  # every detail it names was filled in
                self.assertRegex(first, r"/factory-|by hand")

    def test_it_names_the_pr_or_issue_to_act_on(self):
        cases = {"GATE_A_WAITING": "Review Planning PR #5: merge it yourself",
                 "GATE_B_WAITING_REVIEW": "Review PR #20 (STORY-001)",
                 "STORY_IN_PROGRESS": "finish story #10 (STORY-001) from S09",
                 "CLOSEOUT_PENDING": "close out story #10 (PR #20 is merged)",
                 "IDLE_AT_GATE_C": "run /factory-continue to start the next story (2 ready)",
                 "NEEDS_HUMAN": "Decide on issue #11"}
        for row, text in cases.items():
            with self.subTest(state=row):
                self.assertIn(text, report_for(row).next_action)

    def test_json_has_the_same_next_line(self):
        report = report_for("GATE_B_WAITING_REVIEW")
        data = report.to_dict()
        self.assertEqual((data["schema"], data["next"]), (1, report.next_action))
        self.assertEqual(data["state"]["state"], st.GATE_B_WAITING_REVIEW)


class CommentsHintTest(unittest.TestCase):
    """The "N comments, no /changes" hint."""

    def test_only_for_a_pr_waiting_for_review_with_comments(self):
        result = derive_state(STATE_TABLE["GATE_B_WAITING_REVIEW"][0]).to_dict()
        self.assertIsNone(status.build(result, None, None, 0).hint)
        one = status.build(result, None, None, 1).hint
        self.assertTrue(one.startswith("PR #20 has 1 comment from you in this round but no "
                                       "/changes"))
        self.assertIn("3 comments", status.build(result, None, None, 3).hint)
        rendered = status.render(status.build(result, None, None, 3)).splitlines()
        self.assertTrue(rendered[1].startswith("Hint: PR #20 has 3 comments"))
        for row in ("GATE_A_CHANGES", "GATE_B_CHANGES_REQUESTED", "IDLE_AT_GATE_C"):
            with self.subTest(state=row):
                other = derive_state(STATE_TABLE[row][0]).to_dict()
                self.assertIsNone(status.build(other, None, None, 3).hint)


class RequirementStatusTest(unittest.TestCase):
    """Requirements §11: Done = Implemented and every listed PR merged."""

    def test_rules(self):
        rows = status.parse_traceability(TRACEABILITY)
        found = status.requirement_status(rows, {20: "MERGED", 21: "OPEN"})
        self.assertEqual([(r.req, r.done, r.why) for r in found], [
            ("REQ-001", True, "merged"),
            ("REQ-002", False, "PR #21 open"),
            ("REQ-003", False, "in progress"),
            ("REQ-004", False, "not started"),
            ("REQ-005", False, "deferred"),
            ("REQ-006", False, "implemented, but no PR listed"),
        ])
        missing = status.requirement_status(rows[:1], {})
        self.assertEqual((missing[0].done, missing[0].why), (False, "PR #20 not found"))

    def test_parse_ignores_everything_but_requirement_rows(self):
        text = ("| REQ | Stories | PRs | Tests | Status |\n|---|---|---|---|---|\n"
                "| REQ-007 | too | few |\n"
                "Text mentioning | REQ-008 | in a sentence\n"
                "  | REQ-009 | STORY-001 | #3,#4 | x | Implemented |  \n")
        self.assertEqual(status.parse_traceability(text),
                         [("REQ-009", "Implemented", (3, 4))])


class CollectTest(unittest.TestCase):
    """``collect`` reads the matrix and counts the comments from GitHub (fake)."""

    def gate_a(self, comments, config_on_main=False):
        fake = FakeRepo()
        fake.put(PLAN, ".factory/config.json", CONFIG)
        if config_on_main:
            fake.put("main", ".factory/config.json", CONFIG)
        fake.prs = [{"number": 5, "state": "OPEN", "headRefName": PLAN, "labels": [],
                     "body": build(PlanningMarker(INC))}]
        fake.pr_views[5] = {"number": 5, "state": "OPEN", "mergedAt": None, "headRefName": PLAN,
                            "reviews": [], "commits": [{"oid": "a" * 40, "committedDate": ts(0)}],
                            "comments": comments}
        return fake

    def test_gate_a_hint_counts_human_comments_with_the_config_only_on_the_plan_branch(self):
        comments = [  # an earlier round, closed by the factory's reply, then this round
            {"id": "1", "author": {"login": "me"}, "body": "Old remark", "createdAt": ts(2)},
            {"id": "2", "author": {"login": "me"}, "body": build(ReplyMarker()) + "\nNoted",
             "createdAt": ts(3)},
            {"id": "3", "author": {"login": "me"}, "body": "Why two stories?", "createdAt": ts(4)},
            {"id": "4", "author": {"login": "me"}, "body": "Rename M2", "createdAt": ts(5)},
            {"id": "5", "author": {"login": "someone"}, "body": "drive-by", "createdAt": ts(6)},
        ]
        report = status.collect(Gh(transport=self.gate_a(comments)), "owner/app")
        self.assertEqual(report.state["state"], st.GATE_A_WAITING)
        # Only this round's comments by a reviewer count: not #1 (older), not #5 (not one).
        self.assertTrue(report.hint.startswith("PR #5 has 2 comments from you in this round"))
        self.assertIsNone(report.requirements)
        self.assertIn("Requirements: no docs/factory/traceability.md on the default branch yet.",
                      status.render(report))

    def test_no_hint_once_changes_is_requested(self):
        comments = [{"id": "1", "author": {"login": "me"}, "body": "/changes split it",
                     "createdAt": ts(3)}]
        report = status.collect(Gh(transport=self.gate_a(comments, config_on_main=True)),
                                "owner/app")
        self.assertEqual(report.state["state"], st.GATE_A_CHANGES)
        self.assertIsNone(report.hint)

    def test_reads_the_matrix_on_the_default_branch(self):
        fake = FakeRepo()
        fake.put("main", ".factory/config.json", CONFIG)
        fake.put("main", "docs/factory/traceability.md", TRACEABILITY)
        report = status.collect(Gh(transport=fake), "owner/app")
        self.assertEqual([r.req for r in report.requirements],
                         [f"REQ-00{n}" for n in range(1, 7)])
        self.assertTrue(all(not r.done for r in report.requirements))  # no PR exists


class StatusCliTest(unittest.TestCase):
    def test_json_and_text(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "factory" / ".factory-local").mkdir(parents=True)
        (root / "app").mkdir()
        (root / "factory" / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(root / "app"), "repo": "owner/app"}), encoding="utf-8")
        report = report_for("INCREMENT_COMPLETE")
        # Text: the Target banner first (rule T2), then the report's "Next:" line.
        for argv, check in ((["status", "--json"], lambda out: json.loads(out)["next"]),
                            (["status"], lambda out: out.splitlines()[1])):
            out = io.StringIO()
            with self.subTest(argv=argv), \
                    mock.patch.object(target, "FACTORY_ROOT", root / "factory"), \
                    mock.patch.object(status, "collect", lambda gh, repo: report), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(argv), 0)
                self.assertTrue(re.search(r"run /factory-start", check(out.getvalue())))
                if argv == ["status"]:
                    lines = out.getvalue().splitlines()
                    self.assertTrue(lines[0].startswith("Target: "))
                    self.assertTrue(lines[1].startswith("Next: "))


if __name__ == "__main__":
    unittest.main()
