"""The state engine (T1.8, T3.2, T4.1): derive, the §6 state table, invariants, collect, CLI."""

import base64
import contextlib
import io
import json
import random
import re
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from factory import cli, target
from factory import state as st
from factory.gh import Gh, ProcessResult
from factory.git import Git
from factory.markers import (
    CheckpointMarker,
    PlanningMarker,
    PrMarker,
    ReplyMarker,
    StoryMarker,
    build,
)
from factory.signals import PrSnapshot, SingleAccountSignals, Verdict
from factory.state import IssueInfo, PrInfo, Snapshot, derive_state, validate_output

REPO = "owner/app"
INC = "001-initial"
ALL_DOCS = frozenset(name for _, name in st.PLAN_DOCS)


def story(n, inc=INC):
    return StoryMarker(id=f"STORY-{n:03d}", increment=inc)


def issue(number, n, labels=("factory:story", "status:ready"), state="OPEN", inc=INC,
          checkpoint_branch=None, checkpoint_next=None, blocked_by=()):
    return IssueInfo(number, state, frozenset(labels), story(n, inc), checkpoint_branch,
                     checkpoint_next, tuple(blocked_by))


def labelled(status):
    return ("factory:story", f"status:{status}")


def story_pr(number, n, state="OPEN"):
    return PrInfo(number, state, f"story/{n}-x", frozenset(), story_id=f"STORY-{n:03d}")


def planning_pr(number, state="OPEN", inc=INC):
    return PrInfo(number, state, f"factory/plan-{inc}", frozenset(), planning_increment=inc)


def snap(**kw):
    kw.setdefault("repo", REPO)
    kw.setdefault("default_branch", "main")
    return Snapshot(**kw)


PLAN_BRANCH = frozenset({"main", f"factory/plan-{INC}"})
MERGED_PLANNING = dict(branches=frozenset({"main"}), prs=(planning_pr(5, "MERGED"),),
                       stories_on_default={INC: frozenset({"STORY-001", "STORY-002"})})


def merged_snap(**overrides):
    """A snapshot after the Planning PR merged, with some fields replaced."""
    return snap(**{**MERGED_PLANNING, **overrides})


def rework_snap(checkpoint_next, verdict="PENDING"):
    """#10 under the rework lock (status:changes-requested), with its PR #20 open."""
    return merged_snap(
        branches=frozenset({"main", "story/10-x"}),
        issues=(issue(10, 1, labels=labelled("changes-requested"),
                      checkpoint_branch="story/10-x", checkpoint_next=checkpoint_next),
                issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1)), story_verdicts={20: verdict})

# (name, snapshot, expected state, expected next_station)
STATE_FIXTURES = [
    ("empty repository", snap(is_empty=True), st.UNCONFIGURED, None),
    ("repo with code but no increment", snap(existing_project=True), st.UNCONFIGURED, None),
    ("plan branch, nothing written yet", snap(branches=PLAN_BRANCH), st.PLANNING, "S00"),
    ("config + PRD written", snap(branches=PLAN_BRANCH, plan_config={INC: True},
                                  plan_files={INC: frozenset({"00-prd.md"})}),
     st.PLANNING, "S02"),
    ("existing project needs discovery", snap(
        branches=PLAN_BRANCH, existing_project=True, plan_config={INC: True},
        plan_files={INC: frozenset({"00-prd.md"})}), st.PLANNING, "S01"),
    ("up to architecture", snap(branches=PLAN_BRANCH, plan_config={INC: True}, plan_files={
        INC: frozenset({"00-prd.md", "02-requirements.md", "03-architecture.md"})}),
     st.PLANNING, "S04"),
    ("all docs written, PR not opened", snap(branches=PLAN_BRANCH, plan_config={INC: True},
                                             plan_files={INC: ALL_DOCS}), st.PLANNING, "S05"),
    ("planning PR closed, branch still there", snap(
        branches=PLAN_BRANCH, plan_config={INC: True}, plan_files={INC: ALL_DOCS},
        prs=(planning_pr(5, "CLOSED"),)), st.PLANNING, "S05"),
    ("planning PR open, pending", snap(branches=PLAN_BRANCH, prs=(planning_pr(5),),
                                       planning_verdicts={5: "PENDING"}),
     st.GATE_A_WAITING, None),
    ("planning PR open, no verdict recorded", snap(branches=PLAN_BRANCH,
                                                   prs=(planning_pr(5),)),
     st.GATE_A_WAITING, None),
    ("planning PR open, /changes", snap(branches=PLAN_BRANCH, prs=(planning_pr(5),),
                                        planning_verdicts={5: "CHANGES_REQUESTED"}),
     st.GATE_A_CHANGES, "S05"),
    ("merged, no issues yet", snap(**MERGED_PLANNING), st.ISSUES_PENDING, "S05b"),
    ("merged, one issue missing", snap(**MERGED_PLANNING, issues=(issue(10, 1),)),
     st.ISSUES_PENDING, "S05b"),
    ("merged, all issues, ready", snap(**MERGED_PLANNING, issues=(
        issue(10, 1), issue(11, 2, labels=("factory:story", "status:blocked")))),
     st.IDLE_AT_GATE_C, "S06"),
    ("needs-human label", snap(branches=PLAN_BRANCH, needs_human=("issue #3",)),
     st.NEEDS_HUMAN, None),
    ("planning PR closed and branch deleted", snap(prs=(planning_pr(5, "CLOSED"),)),
     st.NEEDS_HUMAN, None),
    ("merged but no stories in the file", snap(branches=frozenset({"main"}),
                                               prs=(planning_pr(5, "MERGED"),)),
     st.NEEDS_HUMAN, None),
    ("every open story blocked", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=("factory:story", "status:blocked")),
        issue(11, 2, labels=("factory:story", "status:blocked")))), st.NEEDS_HUMAN, None),
    ("two stories in progress", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=("factory:story", "status:in-progress")),
        issue(11, 2, labels=("factory:story", "status:in-review")))), st.INCONSISTENT, None),
    # T3.2: story states.
    ("story just picked, no checkpoint yet", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("in-progress")), issue(11, 2))),
     st.STORY_IN_PROGRESS, "S07"),
    ("story in progress: resume from checkpoint.next", merged_snap(
        branches=frozenset({"main", "story/10-x"}), issues=(
            issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                  checkpoint_next="S09"), issue(11, 2))),
     st.STORY_IN_PROGRESS, "S09"),
    ("story PR opened, label not yet moved: S11 again", merged_snap(
        branches=frozenset({"main", "story/10-x"}), issues=(
            issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                  checkpoint_next="GATE_B"), issue(11, 2))),
     st.STORY_IN_PROGRESS, "S11"),
    ("story PR open, waiting for review", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1)), story_verdicts={20: "PENDING"}),
     st.GATE_B_WAITING_REVIEW, None),
    ("story PR open, no verdict recorded", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1))),
     st.GATE_B_WAITING_REVIEW, None),
    ("all stories done", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("done"), state="CLOSED"),
        issue(11, 2, labels=labelled("done"), state="CLOSED"))),
     st.INCREMENT_COMPLETE, None),
    # T4.1: the rest of Gate B, close-out and a rejected story.
    ("story PR /changes", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1)),
        story_verdicts={20: "CHANGES_REQUESTED"}), st.GATE_B_CHANGES_REQUESTED, "S08"),
    ("changes-requested label, rework commit pushed", merged_snap(
        issues=(issue(10, 1, labels=labelled("changes-requested")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1)), story_verdicts={20: "PENDING"}),
     st.GATE_B_CHANGES_REQUESTED, "S08"),
    # T4.2: while the rework lock is held, the checkpoint says where the rework stands.
    ("rework lock taken, S08 checkpointed", rework_snap("S08"), st.GATE_B_CHANGES_REQUESTED, "S08"),
    ("rework: S08 done, tests next", rework_snap("S09"), st.GATE_B_CHANGES_REQUESTED, "S09"),
    ("rework: verified, S11 replies next", rework_snap("S11"), st.GATE_B_CHANGES_REQUESTED, "S11"),
    ("rework lock taken before S08's checkpoint", rework_snap("GATE_B", "CHANGES_REQUESTED"),
     st.GATE_B_CHANGES_REQUESTED, "S08"),
    ("rework replied, S11 stopped before the label", rework_snap("GATE_B", "PENDING"),
     st.GATE_B_CHANGES_REQUESTED, "S11"),
    ("story PR approved (bot mode only)", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1)), story_verdicts={20: "APPROVED"}),
     st.GATE_B_APPROVED_UNMERGED, None),
    ("story PR merged, issue closed by it", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review"), state="CLOSED"), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED"))),
     st.CLOSEOUT_PENDING, "S12"),
    ("story PR merged, issue still open", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED"))),
     st.CLOSEOUT_PENDING, "S12"),
    ("merged before S11 moved the label, branch deleted", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                      checkpoint_next="GATE_B"), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED"))),
     st.CLOSEOUT_PENDING, "S12"),
    ("last story merged: close-out before increment complete", merged_snap(
        issues=(issue(10, 1, labels=labelled("done"), state="CLOSED"),
                issue(11, 2, labels=labelled("in-review"), state="CLOSED")),
        prs=(planning_pr(5, "MERGED"), story_pr(21, 2, "MERGED"))),
     st.CLOSEOUT_PENDING, "S12"),
    ("story PR closed without merging", merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
        prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "CLOSED"))), st.NEEDS_HUMAN, None),
    ("in review but no PR at all", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("in-review")), issue(11, 2))), st.NEEDS_HUMAN, None),
    ("story closed without a merged PR", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("in-review"), state="CLOSED"), issue(11, 2))),
     st.NEEDS_HUMAN, None),
    ("all closed, one not done and never merged", snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("done"), state="CLOSED"),
        issue(11, 2, state="CLOSED"))), st.NEEDS_HUMAN, None),
]


class DeriveStateTest(unittest.TestCase):
    def test_each_fixture(self):
        for name, snapshot, expected, station in STATE_FIXTURES:
            with self.subTest(name):
                result = derive_state(snapshot)
                self.assertEqual(result.state, expected, result.details)
                self.assertEqual(result.next_station, station)

    def test_every_state_has_a_fixture(self):
        covered = {expected for _, _, expected, _ in STATE_FIXTURES}
        self.assertEqual(set(st.STATES) - covered, set())

    def test_story_state_details(self):
        result = derive_state(merged_snap(
            branches=frozenset({"main", "story/10-x"}), issues=(
                issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                      checkpoint_next="S09"), issue(11, 2))))
        self.assertEqual((result.details["issue"], result.details["story"],
                          result.details["branch"]), (10, "STORY-001", "story/10-x"))
        self.assertIn("Story #10 (STORY-001) is in progress: next is S09.",
                      result.details["message"])
        data = result.to_dict()
        self.assertEqual((data["waiting_on"], data["allowed_commands"]),
                         ("factory", [st.RESUME, st.CONTINUE, st.STATUS]))

        data = derive_state(merged_snap(
            issues=(issue(10, 1, labels=labelled("in-review")), issue(11, 2)),
            prs=(planning_pr(5, "MERGED"), story_pr(20, 1)))).to_dict()
        self.assertEqual((data["details"]["pr"], data["waiting_on"], data["allowed_commands"]),
                         (20, "human", [st.STATUS]))
        self.assertIn("review PR #20 (STORY-001)", data["details"]["message"])

        data = derive_state(snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=labelled("done"), state="CLOSED"),
            issue(11, 2, labels=labelled("done"), state="CLOSED")))).to_dict()
        self.assertEqual((data["details"]["done"], data["allowed_commands"]),
                         ([10, 11], [st.START, st.STATUS]))

    def test_every_state_output_matches_the_schema(self):
        for name, snapshot, _, _ in STATE_FIXTURES:
            with self.subTest(name):
                self.assertEqual(validate_output(derive_state(snapshot).to_dict()), [])

    def test_details_are_informative(self):
        result = derive_state(snap(**MERGED_PLANNING, issues=(issue(10, 1),)))
        self.assertEqual(result.details["missing"], ["STORY-002"])
        result = derive_state(snap(**MERGED_PLANNING, issues=(issue(10, 1), issue(11, 2))))
        self.assertEqual(result.details["ready"], [10, 11])
        result = derive_state(snap(branches=PLAN_BRANCH, plan_config={INC: True},
                                   plan_files={INC: frozenset({"00-prd.md"})}))
        self.assertEqual(result.details["missing"], ["02-requirements.md",
                                                     "03-architecture.md",
                                                     "04-implementation-plan.md",
                                                     "05-stories.md"])

    def test_latest_increment_wins(self):
        result = derive_state(snap(
            branches=frozenset({"main", "factory/plan-002-due-dates"}),
            prs=(planning_pr(5, "MERGED"),), stories_on_default={INC: frozenset({"STORY-001"})},
            issues=(issue(10, 1, state="CLOSED"),)))
        self.assertEqual((result.state, result.increment), (st.PLANNING, "002-due-dates"))

    def test_only_continue_may_act_at_gate_c(self):
        data = derive_state(snap(**MERGED_PLANNING, issues=(issue(10, 1), issue(11, 2))))
        self.assertNotIn(st.RESUME, data.to_dict()["allowed_commands"])
        self.assertIn(st.CONTINUE, data.to_dict()["allowed_commands"])

    def test_nothing_can_act_where_the_human_decides(self):
        for state in (st.INCONSISTENT, st.NEEDS_HUMAN, st.GATE_A_WAITING,
                      st.GATE_B_WAITING_REVIEW, st.GATE_B_APPROVED_UNMERGED):
            self.assertEqual(st.StateResult(state, details={"message": "x"})
                             .to_dict()["allowed_commands"], [st.STATUS])


ARCHITECTURE = Path(__file__).resolve().parents[1] / "docs" / "02-factory-architecture.md"
REJECTED_ROW = "*(→ NEEDS_HUMAN)*"  # the "Verdict CLOSED_UNMERGED" row
BOT_ONLY = {st.GATE_B_APPROVED_UNMERGED}  # single-account signals never return APPROVED


def architecture_state_rows() -> list[str]:
    """The first cell of every row of the architecture §6 state table."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    section = text[text.index("## 6. State machine"):text.index("## 7.")]
    table = section[section.index("| State | Detected when"):]
    rows = []
    for line in table.splitlines()[2:]:  # skip the header and the |---| line
        if not line.startswith("|"):
            break
        rows.append(line.split("|")[1].strip())
    return rows


GATE_B_ISSUES = (issue(10, 1, labels=labelled("in-review")), issue(11, 2))
MERGED_STORY_PRS = (planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED"))

# One case per row of the architecture §6 table:
# row -> (snapshot, state, next_station, commands allowed to act besides /factory-status)
STATE_TABLE = {
    "UNCONFIGURED": (snap(), st.UNCONFIGURED, None, {st.START}),
    "PLANNING": (snap(branches=PLAN_BRANCH, plan_config={INC: True},
                      plan_files={INC: frozenset({"00-prd.md"})}),
                 st.PLANNING, "S02", {st.RESUME, st.CONTINUE}),
    "GATE_A_WAITING": (snap(branches=PLAN_BRANCH, prs=(planning_pr(5),),
                            planning_verdicts={5: "PENDING"}), st.GATE_A_WAITING, None, set()),
    "GATE_A_CHANGES": (snap(branches=PLAN_BRANCH, prs=(planning_pr(5),),
                            planning_verdicts={5: "CHANGES_REQUESTED"}),
                       st.GATE_A_CHANGES, "S05", {st.RESUME, st.CONTINUE}),
    "ISSUES_PENDING": (snap(**MERGED_PLANNING, issues=(issue(10, 1),)),
                       st.ISSUES_PENDING, "S05b", {st.RESUME, st.CONTINUE}),
    "IDLE_AT_GATE_C": (snap(**MERGED_PLANNING, issues=(issue(10, 1), issue(11, 2))),
                       st.IDLE_AT_GATE_C, "S06", {st.CONTINUE}),
    "STORY_IN_PROGRESS": (merged_snap(
        branches=frozenset({"main", "story/10-x"}), issues=(
            issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                  checkpoint_next="S09"), issue(11, 2))),
        st.STORY_IN_PROGRESS, "S09", {st.RESUME, st.CONTINUE}),
    "GATE_B_WAITING_REVIEW": (merged_snap(
        issues=GATE_B_ISSUES, prs=(planning_pr(5, "MERGED"), story_pr(20, 1)),
        story_verdicts={20: "PENDING"}), st.GATE_B_WAITING_REVIEW, None, set()),
    "GATE_B_CHANGES_REQUESTED": (merged_snap(
        issues=GATE_B_ISSUES, prs=(planning_pr(5, "MERGED"), story_pr(20, 1)),
        story_verdicts={20: "CHANGES_REQUESTED"}), st.GATE_B_CHANGES_REQUESTED, "S08",
        {st.RESUME, st.CONTINUE}),
    "GATE_B_APPROVED_UNMERGED": (merged_snap(
        issues=GATE_B_ISSUES, prs=(planning_pr(5, "MERGED"), story_pr(20, 1)),
        story_verdicts={20: "APPROVED"}), st.GATE_B_APPROVED_UNMERGED, None, set()),
    "CLOSEOUT_PENDING": (merged_snap(
        issues=(issue(10, 1, labels=labelled("in-review"), state="CLOSED"), issue(11, 2)),
        prs=MERGED_STORY_PRS), st.CLOSEOUT_PENDING, "S12", {st.RESUME, st.CONTINUE}),
    REJECTED_ROW: (merged_snap(
        issues=GATE_B_ISSUES, prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "CLOSED"))),
        st.NEEDS_HUMAN, None, set()),
    "INCREMENT_COMPLETE": (snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("done"), state="CLOSED"),
        issue(11, 2, labels=labelled("done"), state="CLOSED"))),
        st.INCREMENT_COMPLETE, None, {st.START}),
    "NEEDS_HUMAN": (snap(**MERGED_PLANNING, issues=(issue(10, 1), issue(11, 2)),
                         needs_human=("issue #11",)), st.NEEDS_HUMAN, None, set()),
    "INCONSISTENT": (snap(**MERGED_PLANNING, issues=(
        issue(10, 1, labels=labelled("in-progress")),
        issue(11, 2, labels=labelled("in-review")))), st.INCONSISTENT, None, set()),
}


class StateTableTest(unittest.TestCase):
    """T4.1: every row of the architecture §6 state table is one test case."""

    def test_the_cases_are_exactly_the_rows_of_the_table(self):
        rows = architecture_state_rows()
        self.assertEqual(len(rows), 15)  # 14 states and the CLOSED_UNMERGED row
        self.assertEqual(sorted(rows), sorted(STATE_TABLE))

    def test_every_state_is_a_row_of_the_table(self):
        self.assertEqual(set(st.STATES), set(STATE_TABLE) - {REJECTED_ROW})
        self.assertEqual(len(st.STATES), 14)

    def test_each_row(self):
        for row, (snapshot, state, station, acts) in STATE_TABLE.items():
            with self.subTest(row):
                data = derive_state(snapshot).to_dict()
                self.assertEqual(validate_output(data), [])
                self.assertEqual((data["state"], data["next_station"]), (state, station),
                                 data["details"])
                self.assertEqual(set(data["allowed_commands"]), acts | {st.STATUS})
                if row == REJECTED_ROW:
                    self.assertIn("closed without merging", data["details"]["message"])

    def test_only_the_bot_only_state_needs_an_approved_verdict(self):
        """Bot-only states are reachable only from verdicts single-account never gives."""
        signals = SingleAccountSignals(["me"])
        verdicts = {signals.verdict(PrSnapshot(1, s, s == "MERGED", "h", None, ()))
                    for s in ("OPEN", "CLOSED", "MERGED")}
        self.assertNotIn(Verdict.APPROVED, verdicts)
        for row, (snapshot, state, _, _) in STATE_TABLE.items():
            with self.subTest(row):
                approved = Verdict.APPROVED.value in snapshot.story_verdicts.values()
                self.assertEqual(approved, state in BOT_ONLY)


class InvariantTest(unittest.TestCase):
    """Architecture §6: a broken invariant always yields INCONSISTENT."""

    CASES = [
        ("two stories active", snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=("factory:story", "status:in-progress")),
            issue(11, 2, labels=("factory:story", "status:in-progress")))),
         "more than one story"),
        ("story PR without an issue", merged_snap(
            issues=(issue(10, 1),),
            prs=(planning_pr(5, "MERGED"),
                 PrInfo(20, "OPEN", "story/9-x", frozenset(), story_id="STORY-009"))),
         "has 0 issues"),
        ("story with two issues", snap(**MERGED_PLANNING, issues=(issue(10, 1), issue(12, 1))),
         "several issues"),
        ("two open PRs for one story", merged_snap(
            issues=(issue(10, 1),),
            prs=(planning_pr(5, "MERGED"),
                 PrInfo(20, "OPEN", "a", frozenset(), story_id="STORY-001"),
                 PrInfo(21, "OPEN", "b", frozenset(), story_id="STORY-001"))),
         "several open PRs"),
        ("checkpoint branch missing", snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=("factory:story", "status:in-progress"),
                  checkpoint_branch="story/10-gone"), issue(11, 2))),
         "does not exist on the remote"),
        ("checkpoint branch missing, story resuming at S09", snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-gone",
                  checkpoint_next="S09"), issue(11, 2))),
         "names branch 'story/10-gone', which does not exist on the remote"),
        ("checkpoint branch missing while in review", snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=labelled("in-review"), checkpoint_branch="story/10-gone"),
            issue(11, 2))),
         "does not exist on the remote"),
        ("in progress, checkpoint points to a planning station", merged_snap(
            branches=frozenset({"main", "story/10-x"}), issues=(
                issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                      checkpoint_next="S03"), issue(11, 2))),
         "points to S03, which is not a story station"),
        ("in progress, checkpoint points to Gate C", merged_snap(
            branches=frozenset({"main", "story/10-x"}), issues=(
                issue(10, 1, labels=labelled("in-progress"), checkpoint_branch="story/10-x",
                      checkpoint_next="GATE_C"), issue(11, 2))),
         "points to GATE_C"),
        ("one story in progress, another with changes requested", snap(
            **MERGED_PLANNING, issues=(issue(10, 1, labels=labelled("in-progress")),
                                       issue(11, 2, labels=labelled("changes-requested")))),
         "more than one story"),
        ("a merged story awaits close-out while another is in progress", merged_snap(
            issues=(issue(10, 1, labels=labelled("in-review"), state="CLOSED"),
                    issue(11, 2, labels=labelled("in-progress"))),
            prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED"))),
         "more than one story is in flight"),
        ("rework checkpoint points outside the rework stations", rework_snap("S06"),
         "points to S06, which is not a rework station"),
        ("rework checkpoint points to close-out", rework_snap("S12"),
         "points to S12, which is not a rework station"),
        ("direct factory commit on main", snap(**MERGED_PLANNING,
                                               direct_factory_commits=("abcdef1234",)),
         "did not arrive through a merged PR"),
        ("several status labels", snap(**MERGED_PLANNING, issues=(
            issue(10, 1, labels=("factory:story", "status:ready", "status:done")),)),
         "several status labels"),
        ("two open planning PRs", snap(branches=PLAN_BRANCH, prs=(
            planning_pr(5), planning_pr(6, inc="002-more"))), "several Planning PRs"),
        ("invalid config", snap(config_error="schema must be 1"), "config is invalid"),
    ]

    def test_each_broken_invariant_is_inconsistent(self):
        for name, snapshot, text in self.CASES:
            with self.subTest(name):
                result = derive_state(snapshot)
                self.assertEqual(result.state, st.INCONSISTENT)
                self.assertTrue(any(text in p for p in result.details["problems"]),
                                result.details["problems"])

    def test_inconsistent_wins_over_needs_human(self):
        snapshot = snap(**MERGED_PLANNING, needs_human=("issue #3",),
                        direct_factory_commits=("abc1234",))
        self.assertEqual(derive_state(snapshot).state, st.INCONSISTENT)

    def test_branch_deleted_by_the_merge_is_fine(self):
        snapshot = merged_snap(
            issues=(issue(10, 1, labels=labelled("in-review"), checkpoint_branch="story/10-x"),
                    issue(11, 2)),
            prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED")))
        self.assertEqual(st.check_invariants(snapshot), [])
        self.assertEqual(derive_state(snapshot).state, st.CLOSEOUT_PENDING)

    def test_done_stories_are_not_in_flight(self):
        snapshot = merged_snap(
            issues=(issue(10, 1, labels=labelled("done"), state="CLOSED"),
                    issue(11, 2, labels=labelled("in-progress"))),
            prs=(planning_pr(5, "MERGED"), story_pr(20, 1, "MERGED")))
        self.assertEqual(st.check_invariants(snapshot), [])

    def test_existing_checkpoint_branch_is_fine(self):
        snapshot = merged_snap(
            branches=frozenset({"main", "story/10-x"}),
            issues=(issue(10, 1, labels=("factory:story", "status:in-progress"),
                          checkpoint_branch="story/10-x"), issue(11, 2)))
        self.assertEqual(st.check_invariants(snapshot), [])


class SchemaTest(unittest.TestCase):
    def test_every_fixture_output_matches_the_schema(self):
        for name, snapshot, _, _ in STATE_FIXTURES + [(n, s, None, None) for n, s, _ in
                                                      InvariantTest.CASES]:
            with self.subTest(name):
                data = json.loads(json.dumps(derive_state(snapshot).to_dict()))
                self.assertEqual(validate_output(data), [])

    def test_validator_rejects_bad_output(self):
        good = derive_state(snap(is_empty=True)).to_dict()
        bad_cases = [
            ("not an object", []),
            ("missing key", {k: v for k, v in good.items() if k != "details"}),
            ("extra key", {**good, "extra": 1}),
            ("wrong schema", {**good, "schema": 2}),
            ("unknown state", {**good, "state": "DANCING"}),
            ("bad station", {**good, "next_station": "S1"}),
            ("bad increment", {**good, "increment": "one"}),
            ("empty commands", {**good, "allowed_commands": []}),
            ("bad waiting_on", {**good, "waiting_on": "godot"}),
            ("no message", {**good, "details": {}}),
        ]
        for name, data in bad_cases:
            with self.subTest(name):
                self.assertTrue(validate_output(data))

    def test_random_snapshots_always_give_exactly_one_valid_state(self):
        """AC: exactly one state for every snapshot, never a crash."""
        rng = random.Random(8)
        labels = ["status:ready", "status:blocked", "status:in-progress", "status:in-review",
                  "status:changes-requested", "status:done", "factory:needs-human"]
        for _ in range(3000):
            incs = rng.sample(["001-initial", "002-more", "003-x"], rng.randint(0, 2))
            branches = {"main"} | {f"factory/plan-{i}" for i in incs if rng.random() < 0.7}
            prs = tuple(PrInfo(n, rng.choice(["OPEN", "CLOSED", "MERGED"]), "h", frozenset(),
                               planning_increment=rng.choice(incs + [None]) if incs else None,
                               story_id=rng.choice([None, "STORY-001", "STORY-002"]))
                        for n in range(rng.randint(0, 3)))
            issues = tuple(IssueInfo(10 + n, rng.choice(["OPEN", "CLOSED"]),
                                     frozenset(rng.sample(labels, rng.randint(0, 2))),
                                     story(rng.randint(1, 3), rng.choice(incs or [INC])),
                                     rng.choice([None, "story/x", "main"]))
                           for n in range(rng.randint(0, 4)))
            snapshot = snap(
                is_empty=rng.random() < 0.05, branches=frozenset(branches), prs=prs,
                issues=issues, existing_project=rng.random() < 0.5,
                plan_config={i: rng.random() < 0.8 for i in incs},
                plan_files={i: frozenset(rng.sample(sorted(ALL_DOCS), rng.randint(0, 6)))
                            for i in incs},
                planning_verdicts={p.number: rng.choice([v.value for v in Verdict])
                                   for p in prs},
                story_verdicts={p.number: rng.choice([v.value for v in Verdict])
                                for p in prs if p.state == "OPEN"},
                needs_human=("issue #1",) if rng.random() < 0.1 else (),
                stories_on_default={i: frozenset(rng.sample(
                    ["STORY-001", "STORY-002", "STORY-003"], rng.randint(0, 3))) for i in incs},
                direct_factory_commits=("abc1234",) if rng.random() < 0.05 else (),
            )
            data = derive_state(snapshot).to_dict()
            self.assertEqual(validate_output(data), [], data)


# ----------------------------------------------------------------------------- collect

def ts(minute):
    return datetime(2026, 9, 24, 10, minute, tzinfo=UTC).isoformat().replace("+00:00", "Z")


class FakeRepo:
    """A simulated GitHub repo that answers the exact gh calls collect_snapshot makes."""

    def __init__(self, *, empty=False, default="main"):
        self.empty, self.default = empty, default
        self.files: dict[tuple[str, str], str] = {}   # (ref, path) -> text
        self.branches = {default}
        self.prs: list[dict] = []
        self.issues: list[dict] = []
        self.needs_human: list[int] = []
        self.pr_views: dict[int, dict] = {}
        self.issue_comments: dict[int, list[dict]] = {}
        self.rest_issues: dict[int, dict] = {}  # issues that are not stories, by number
        self.commits: list[dict] = []
        self.calls: list[list[str]] = []

    def put(self, ref, path, text):
        self.branches.add(ref)
        self.files[(ref, path)] = text

    def __call__(self, argv, *, timeout, cwd=None, env=None, input=None):
        args = list(argv[1:])
        self.calls.append(args)
        return self.route(args)

    @staticmethod
    def ok(data):
        return ProcessResult([], 0, json.dumps(data), "")

    @staticmethod
    def not_found():
        return ProcessResult([], 1, "", "gh: Not Found (HTTP 404)")

    def route(self, a):
        if a[:3] == ["repo", "view", REPO]:
            return self.ok({"defaultBranchRef": {"name": "" if self.empty else self.default},
                            "isEmpty": self.empty})
        if a[:2] == ["pr", "list"]:
            return self.ok(self.prs)
        if a[:2] == ["issue", "list"]:
            if "factory:needs-human" in a:
                return self.ok([{"number": n} for n in self.needs_human])
            return self.ok(self.issues)
        if a[:2] == ["pr", "view"]:
            return self.ok(self.pr_views[int(a[2])])
        assert a[0] == "api", a
        endpoint = a[1]
        if endpoint == f"repos/{REPO}/branches":
            return self.ok([[{"name": b} for b in sorted(self.branches)]])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)/comments", endpoint):
            return self.ok([self.issue_comments.get(int(m[1]), [])])
        if m := re.fullmatch(rf"repos/{REPO}/issues/(\d+)", endpoint):
            found = self.rest_issues.get(int(m[1]))
            return self.ok(found) if found else self.not_found()
        if re.fullmatch(rf"repos/{REPO}/pulls/\d+/comments", endpoint):
            return self.ok([[]])
        if endpoint == f"repos/{REPO}/git/trees/{self.default}?recursive=1":
            if self.empty:
                return ProcessResult([], 1, "", "gh: Git Repository is empty. (HTTP 409)")
            return self.ok({"tree": [{"path": p, "type": "blob"} for (r, p) in self.files
                                     if r == self.default]})
        if endpoint.startswith(f"repos/{REPO}/commits?"):
            return self.ok(self.commits)
        if m := re.fullmatch(rf"repos/{REPO}/contents/(.+)\?ref=(.+)", endpoint):
            path, ref = m[1], m[2]
            if (ref, path) in self.files:
                text = self.files[(ref, path)]
                return self.ok({"type": "file", "name": path.rsplit("/", 1)[-1],
                                "content": base64.b64encode(text.encode()).decode()})
            children = sorted({p[len(path) + 1:].split("/")[0] for (r, p) in self.files
                               if r == ref and p.startswith(path + "/")})
            return self.ok([{"name": c} for c in children]) if children else self.not_found()
        raise AssertionError(f"unexpected call {a}")


CONFIG = json.dumps({"schema": 1, "project": "app", "repo": REPO, "default_branch": "main",
                     "reviewers": ["me"]})
PLAN = f"factory/plan-{INC}"
DOCS = f"docs/factory/increments/{INC}"


def collect(repo: FakeRepo):
    return st.collect_snapshot(Gh(transport=repo), REPO)


class CollectSnapshotTest(unittest.TestCase):
    def test_empty_repo(self):
        fake = FakeRepo(empty=True)
        result = derive_state(collect(fake))
        self.assertEqual(result.state, st.UNCONFIGURED)
        self.assertEqual(len(fake.calls), 1)  # nothing else to read

    def test_planning_in_progress(self):
        fake = FakeRepo()
        fake.put("main", "README.md", "# app")
        fake.put(PLAN, ".factory/config.json", CONFIG)
        fake.put(PLAN, f"{DOCS}/00-prd.md", "PRD")
        fake.put(PLAN, f"{DOCS}/02-requirements.md", "REQ")
        snapshot = collect(fake)
        self.assertFalse(snapshot.existing_project)  # a README alone is not a project
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.increment, result.next_station),
                         (st.PLANNING, INC, "S03"))

    def test_existing_project_needs_discovery(self):
        fake = FakeRepo()
        fake.put("main", "src/app.py", "print()")
        fake.put(PLAN, ".factory/config.json", CONFIG)
        fake.put(PLAN, f"{DOCS}/00-prd.md", "PRD")
        self.assertEqual(derive_state(collect(fake)).next_station, "S01")

    def open_planning_pr(self, comments):
        fake = FakeRepo()
        fake.put(PLAN, ".factory/config.json", CONFIG)
        fake.prs = [{"number": 5, "state": "OPEN", "headRefName": PLAN, "labels": [],
                     "body": build(PlanningMarker(INC)) + "\nPlanning PR"}]
        fake.pr_views[5] = {"number": 5, "state": "OPEN", "mergedAt": None,
                            "headRefName": PLAN, "reviews": [],
                            "commits": [{"oid": "a" * 40, "committedDate": ts(0)}],
                            "comments": comments}
        return fake

    def test_gate_a_waiting(self):
        fake = self.open_planning_pr([{"id": "1", "author": {"login": "me"},
                                       "body": "Looks good so far", "createdAt": ts(5)}])
        self.assertEqual(derive_state(collect(fake)).state, st.GATE_A_WAITING)

    def test_gate_a_changes(self):
        fake = self.open_planning_pr([{"id": "1", "author": {"login": "me"},
                                       "body": "/changes split STORY-003", "createdAt": ts(5)}])
        self.assertEqual(derive_state(collect(fake)).state, st.GATE_A_CHANGES)

    def test_gate_a_changes_answered_by_factory(self):
        fake = self.open_planning_pr([
            {"id": "1", "author": {"login": "me"}, "body": "/changes x", "createdAt": ts(5)},
            {"id": "2", "author": {"login": "me"}, "body": build(ReplyMarker()) + "\nDone",
             "createdAt": ts(7)}])
        self.assertEqual(derive_state(collect(fake)).state, st.GATE_A_WAITING)

    @staticmethod
    def merged():
        fake = FakeRepo()
        fake.put("main", ".factory/config.json", CONFIG)
        fake.put("main", f"{DOCS}/05-stories.md",
                 "# Stories\n\n### STORY-001: First\n...\n### STORY-002: Second\n")
        fake.prs = [{"number": 5, "state": "MERGED", "headRefName": PLAN, "labels": [],
                     "body": build(PlanningMarker(INC))}]
        return fake

    @staticmethod
    def story_issue(number, n, labels=("factory:story", "status:ready")):
        return {"number": number, "state": "OPEN", "labels": [{"name": x} for x in labels],
                "body": build(story(n)) + "\n## Story"}

    def test_issues_pending(self):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1)]
        result = derive_state(collect(fake))
        self.assertEqual((result.state, result.details["missing"]),
                         (st.ISSUES_PENDING, ["STORY-002"]))

    def test_idle_at_gate_c(self):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1), self.story_issue(11, 2)]
        self.assertEqual(derive_state(collect(fake)).state, st.IDLE_AT_GATE_C)

    def test_needs_human_from_label(self):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1), self.story_issue(11, 2)]
        fake.needs_human = [11]
        self.assertEqual(derive_state(collect(fake)).state, st.NEEDS_HUMAN)

    def test_checkpoint_branch_is_read_and_checked(self):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1, ("factory:story", "status:in-progress")),
                       self.story_issue(11, 2)]
        checkpoint = build(CheckpointMarker("S08", "S09", "story/10-gone", "a" * 40, 0, 0,
                                            "2026-09-24T10:00:00+00:00"))
        fake.issue_comments[10] = [{"id": 1, "body": checkpoint}]
        snapshot = collect(fake)
        self.assertEqual(snapshot.issues[0].checkpoint_branch, "story/10-gone")
        self.assertEqual(derive_state(snapshot).state, st.INCONSISTENT)

    def test_story_in_progress_resumes_from_the_checkpoint(self):
        fake = self.merged()
        fake.branches.add("story/10-first")
        fake.issues = [self.story_issue(10, 1, ("factory:story", "status:in-progress")),
                       self.story_issue(11, 2)]
        checkpoint = build(CheckpointMarker("S08", "S09", "story/10-first", "a" * 40, 0, 0,
                                            "2026-09-25T10:00:00+00:00"))
        fake.issue_comments[10] = [{"id": 1, "body": checkpoint}]
        snapshot = collect(fake)
        self.assertEqual((snapshot.issues[0].checkpoint_branch,
                          snapshot.issues[0].checkpoint_next), ("story/10-first", "S09"))
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.next_station),
                         (st.STORY_IN_PROGRESS, "S09"))

    def story_in_review(self, comments):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1, ("factory:story", "status:in-review")),
                       self.story_issue(11, 2)]
        fake.prs.append({"number": 20, "state": "OPEN", "headRefName": "story/10-first",
                         "labels": [], "body": build(PrMarker("STORY-001")) + "\nCloses #10"})
        fake.pr_views[20] = {"number": 20, "state": "OPEN", "mergedAt": None,
                             "headRefName": "story/10-first", "reviews": [],
                             "commits": [{"oid": "b" * 40, "committedDate": ts(0)}],
                             "comments": comments}
        return fake

    def test_gate_b_waiting_review(self):
        fake = self.story_in_review([{"id": "1", "author": {"login": "me"},
                                      "body": "Reading it now", "createdAt": ts(5)}])
        snapshot = collect(fake)
        self.assertEqual(snapshot.story_verdicts, {20: "PENDING"})
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.details["pr"]), (st.GATE_B_WAITING_REVIEW, 20))

    def test_gate_b_changes_requested(self):
        fake = self.story_in_review([{"id": "1", "author": {"login": "me"},
                                      "body": "/changes rename it", "createdAt": ts(5)}])
        snapshot = collect(fake)
        self.assertEqual(snapshot.story_verdicts, {20: "CHANGES_REQUESTED"})
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.next_station, result.details["pr"],
                          result.details["branch"]),
                         (st.GATE_B_CHANGES_REQUESTED, "S08", 20, "story/10-first"))

    def test_changes_requested_label_reads_the_verdict_too(self):
        fake = self.story_in_review([])
        fake.issues[0] = self.story_issue(10, 1, ("factory:story", "status:changes-requested"))
        snapshot = collect(fake)
        self.assertEqual(snapshot.story_verdicts, {20: "PENDING"})
        self.assertEqual(derive_state(snapshot).state, st.GATE_B_CHANGES_REQUESTED)

    def test_closeout_after_the_merge_closed_the_issue(self):
        # The M3 demo: merging PR #14 ("Closes #2") closed the issue, still in review, and
        # GitHub deleted the story branch.
        fake = self.story_in_review([])
        fake.issues[0] = dict(self.story_issue(10, 1, ("factory:story", "status:in-review")),
                              state="CLOSED")
        fake.prs[-1]["state"] = "MERGED"
        snapshot = collect(fake)
        self.assertEqual(snapshot.story_verdicts, {})  # nothing open to read
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.next_station), (st.CLOSEOUT_PENDING, "S12"))
        self.assertEqual({k: result.details[k] for k in ("issue", "story", "pr", "branch")},
                         {"issue": 10, "story": "STORY-001", "pr": 20,
                          "branch": "story/10-first"})
        self.assertEqual(result.to_dict()["allowed_commands"],
                         [st.RESUME, st.CONTINUE, st.STATUS])

    def test_rejected_story_pr_needs_a_human(self):
        fake = self.story_in_review([])
        fake.prs[-1]["state"] = "CLOSED"
        result = derive_state(collect(fake))
        self.assertEqual((result.state, result.details["items"]), (st.NEEDS_HUMAN, ["PR #20"]))

    def test_increment_complete(self):
        fake = self.merged()
        done = ("factory:story", "status:done")
        fake.issues = [dict(self.story_issue(10, 1, done), state="CLOSED"),
                       dict(self.story_issue(11, 2, done), state="CLOSED")]
        self.assertEqual(derive_state(collect(fake)).state, st.INCREMENT_COMPLETE)

    def test_direct_factory_commit_detected(self):
        fake = self.merged()
        fake.issues = [self.story_issue(10, 1), self.story_issue(11, 2)]
        fake.commits = [
            {"sha": "1" * 40, "commit": {"message": "Squash (#3)\n\nFactory-Station: S08"},
             "committer": {"login": "web-flow"}},          # merged through a PR: fine
            {"sha": "2" * 40, "commit": {"message": "hotfix\n\nFactory-Station: S08"},
             "committer": {"login": "me"}},                # pushed directly: not fine
            {"sha": "3" * 40, "commit": {"message": "human commit"},
             "committer": {"login": "me"}},                # not the factory's: fine
        ]
        snapshot = collect(fake)
        self.assertEqual(snapshot.direct_factory_commits, ("2" * 40,))
        self.assertEqual(derive_state(snapshot).state, st.INCONSISTENT)

    def test_planning_pr_merged_with_a_merge_commit_is_consistent(self):
        # Regression: the M2 demo merged Planning PR #1 with a normal merge commit, and
        # the state became INCONSISTENT because the branch's own commits (committed by
        # the human's account, not web-flow) were taken for direct pushes.
        fake = self.merged()
        fake.commits = merge_commit_history()
        snapshot = collect(fake)
        self.assertEqual(snapshot.direct_factory_commits, ())
        self.assertEqual(derive_state(snapshot).state, st.ISSUES_PENDING)

    def test_invalid_config_is_inconsistent(self):
        fake = self.merged()
        fake.put("main", ".factory/config.json", '{"schema": 2}')
        result = derive_state(collect(fake))
        self.assertEqual(result.state, st.INCONSISTENT)


def commit(sha, message, committer, *parents):
    """One entry of a ``repos/<r>/commits`` listing, as GitHub returns it."""
    return {"sha": sha, "commit": {"message": message}, "committer": {"login": committer},
            "parents": [{"sha": p} for p in parents]}


def merge_commit_history(merger="web-flow"):
    """The target's `main` after the M2 demo, newest first (shas shortened to letters).

    99e0ddf ─ 1e32681 ──────────────────────────────────── 2a5a64e (merge of PR #1)
          └─ c6b13c2 S00 ─ … ─ 01ef0d9 S04 ─ e2babf0 S05 ─┘
    """
    base, moved, merge = "0" * 40, "m" * 40, "x" * 40
    stations = ["S00", "S02", "S03", "S04", "S04", "S05"]
    branch = [f"{chr(ord('a') + i)}" * 40 for i in range(len(stations))]
    listing = [commit(merge, "Merge pull request #1 from o/factory/plan-001-initial",
                      merger, moved, branch[-1])]
    for i in reversed(range(len(stations))):
        parent = branch[i - 1] if i else base
        listing.append(commit(branch[i], f"{stations[i]}: step\n\nFactory-Station: {stations[i]}",
                              "me", parent))
    listing.append(commit(moved, "chore: move PRD under factory docs", "me", base))
    listing.append(commit(base, "chore: initialize factory test target", "me"))
    return listing


class DirectFactoryCommitsTest(unittest.TestCase):
    """Invariant 4: factory commits on the default branch must come from a merged PR."""

    def test_normal_merge_by_github_is_fine(self):
        self.assertEqual(st.direct_factory_commits(merge_commit_history()), ())

    def test_local_merge_does_not_excuse_the_branch_commits(self):
        history = merge_commit_history(merger="me")
        flagged = st.direct_factory_commits(history)
        self.assertEqual(len(flagged), 6)
        self.assertEqual(derive_state(merged_snap(direct_factory_commits=flagged)).state,
                         st.INCONSISTENT)

    def test_direct_push_after_a_merge_is_still_detected(self):
        history = merge_commit_history()
        pushed = commit("p" * 40, "fix\n\nFactory-Station: S08", "me", history[0]["sha"])
        self.assertEqual(st.direct_factory_commits([pushed, *history]), ("p" * 40,))

    def test_direct_push_that_a_later_merge_also_contains_is_detected(self):
        # A factory commit pushed straight to main, then a PR branched from after it and
        # merged: the commit is an ancestor of the merge's first parent, so the merge
        # did not bring it in.
        base, pushed, side, merge = "0" * 40, "p" * 40, "s" * 40, "x" * 40
        history = [
            commit(merge, "Merge pull request #2", "web-flow", pushed, side),
            commit(side, "S08: work\n\nFactory-Station: S08", "me", pushed),
            commit(pushed, "hotfix\n\nFactory-Station: S08", "me", base),
            commit(base, "init", "me"),
        ]
        self.assertEqual(st.direct_factory_commits(history), (pushed,))

    def test_squash_and_rebase_merges_are_fine(self):
        history = [commit("q" * 40, "Story (#3)\n\nFactory-Station: S08", "web-flow", "0" * 40),
                   commit("0" * 40, "init", "me")]
        self.assertEqual(st.direct_factory_commits(history), ())

    def test_listing_without_parents_keeps_the_committer_rule(self):
        history = [{"sha": "1" * 40, "commit": {"message": "x\n\nFactory-Station: S02"},
                    "committer": {"login": "me"}}]
        self.assertEqual(st.direct_factory_commits(history), ("1" * 40,))


class StateCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.factory = root / "factory"
        (self.factory / ".factory-local").mkdir(parents=True)
        app = root / "app"
        app.mkdir()
        Git(app).run(["init", "-b", "main"])
        (self.factory / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(app), "repo": REPO}), encoding="utf-8")
        self.banner = f"Target: {app} ({REPO})"

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        fake = FakeRepo()
        fake.put(PLAN, ".factory/config.json", CONFIG)
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                mock.patch.object(cli, "Gh", lambda: Gh(transport=fake)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_json_output_is_pure_and_valid(self):
        code, out, err = self.run_cli("state", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)  # stdout is only JSON
        self.assertEqual(validate_output(data), [])
        self.assertEqual((data["state"], data["next_station"]), (st.PLANNING, "S00"))
        self.assertIn(self.banner, err)

    def test_human_output(self):
        code, out, _ = self.run_cli("state")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], self.banner)
        self.assertIn("State: PLANNING (increment 001-initial)", out)
        self.assertIn("Next station: S00", out)



class ReadinessTest(unittest.TestCase):
    """Gate C "ready" follows the unblocked rule (requirements §4) exactly as ``pick`` does:
    labelled ``status:ready`` and every ``Blocked by`` issue closed. Regression: after the
    close-out of STORY-002 the state engine reported #4-#13 ready although #5-#13 were
    still blocked, because it looked at the label alone."""

    def stories(self, *numbers):
        return {INC: frozenset(f"STORY-{n:03d}" for n in numbers)}

    def test_demo_after_story_002_closeout(self):
        done = labelled("done")
        issues = (issue(2, 1, labels=done, state="CLOSED"),
                  issue(3, 2, labels=done, state="CLOSED", blocked_by=[2]),
                  issue(4, 3, blocked_by=[3]),
                  issue(5, 4, blocked_by=[4]), issue(6, 5, blocked_by=[4]),
                  issue(7, 6, blocked_by=[6]), issue(8, 7, blocked_by=[4]),
                  issue(9, 8, blocked_by=[8]), issue(10, 9, blocked_by=[7, 9]),
                  issue(11, 10, blocked_by=[8]), issue(12, 11, blocked_by=[7, 10, 11]),
                  issue(13, 12, blocked_by=[7, 10, 11]))
        result = derive_state(merged_snap(issues=issues,
                                          stories_on_default=self.stories(*range(1, 13))))
        self.assertEqual((result.state, result.next_station), (st.IDLE_AT_GATE_C, "S06"))
        self.assertEqual(result.details["ready"], [4])
        self.assertEqual(result.details["message"], "1 story(ies) ready. Say continue "
                                                    "(/factory-continue) to start the next one.")
        self.assertEqual(result.details["blocked"]["5"], [4])
        self.assertEqual(result.details["blocked"]["12"], [7, 10, 11])
        self.assertEqual(validate_output(result.to_dict()), [])

    def test_every_ready_story_blocked_is_needs_human(self):
        issues = (issue(10, 1, labels=labelled("blocked")), issue(11, 2, blocked_by=[10]))
        result = derive_state(merged_snap(issues=issues))
        self.assertEqual(result.state, st.NEEDS_HUMAN)
        self.assertEqual(result.details["blocked"], {"11": [10]})
        self.assertIn("#11 waits for #10", result.details["message"])

    def test_a_closed_blocker_unblocks(self):
        issues = (issue(10, 1, labels=labelled("done"), state="CLOSED"),
                  issue(11, 2, blocked_by=[10]))
        result = derive_state(merged_snap(issues=issues))
        self.assertEqual((result.state, result.details["ready"]), (st.IDLE_AT_GATE_C, [11]))

    def test_an_unseen_blocker_counts_as_open(self):
        issues = (issue(10, 1, blocked_by=[99]), issue(11, 2, labels=labelled("blocked")))
        self.assertEqual(derive_state(merged_snap(issues=issues)).state, st.NEEDS_HUMAN)
        closed = merged_snap(issues=issues, other_blockers={99: False})
        self.assertEqual(derive_state(closed).details["ready"], [10])
        still_open = merged_snap(issues=issues, other_blockers={99: True})
        self.assertEqual(derive_state(still_open).state, st.NEEDS_HUMAN)

    def test_state_and_pick_agree(self):
        """Random Gate C snapshots, collected the way the CLI does: the state engine's
        ready list is exactly the set of stories ``pick`` may start."""
        from factory import pick as pick_mod
        rng = random.Random(4)
        for _ in range(150):
            count = rng.randint(1, 6)
            fake = CollectSnapshotTest.merged()
            fake.put("main", f"{DOCS}/05-stories.md", "# Stories\n" + "".join(
                f"### STORY-{n:03d}: S{n}\n" for n in range(1, count + 1)))
            raw = []
            for n in range(1, count + 1):
                number = 9 + n
                status = rng.choice(["ready", "ready", "blocked", "done"])
                blockers = sorted(rng.sample(range(10, 10 + count + 2), rng.randint(0, 2)))
                body = (build(story(n)) + "\n## Dependencies\nBlocked by: "
                        + (", ".join(f"#{b}" for b in blockers) or "None") + "\n")
                raw.append({"number": number, "title": f"S{n}",
                            "state": "CLOSED" if status == "done" else "OPEN",
                            "labels": [{"name": "factory:story"},
                                       {"name": f"status:{status}"}], "body": body})
            fake.issues = raw
            result = derive_state(collect(fake))
            stories, is_open = pick_mod.parse_issues(raw)
            with self.subTest(issues=[(i["number"], i["labels"][1]["name"], i["state"],
                                       i["body"].rsplit("Blocked by: ", 1)[1].strip())
                                      for i in raw]):
                try:
                    choice = pick_mod.choose(stories, is_open)
                except pick_mod.PickError:
                    if any(i["state"] == "OPEN" for i in raw):
                        self.assertEqual(result.state, st.NEEDS_HUMAN)
                    else:
                        self.assertEqual(result.state, st.INCREMENT_COMPLETE)
                    continue
                self.assertEqual(result.state, st.IDLE_AT_GATE_C)
                self.assertEqual(result.details["ready"],
                                 sorted(s.number for s in choice.unblocked))
                self.assertIn(choice.picked.number, result.details["ready"])


class CollectBlockersTest(unittest.TestCase):
    def test_blocked_by_is_read_from_the_issue_body(self):
        fake = CollectSnapshotTest.merged()
        first = CollectSnapshotTest.story_issue(10, 1)
        second = CollectSnapshotTest.story_issue(11, 2)
        second["body"] += "\n## Dependencies\nBlocked by: #10\n"
        fake.issues = [first, second]
        snapshot = collect(fake)
        self.assertEqual([i.blocked_by for i in snapshot.issues], [(), (10,)])
        result = derive_state(snapshot)
        self.assertEqual((result.state, result.details["ready"]), (st.IDLE_AT_GATE_C, [10]))

    def test_a_blocker_that_is_not_a_story_is_read_too(self):
        fake = CollectSnapshotTest.merged()
        first = CollectSnapshotTest.story_issue(10, 1)
        first["body"] += "\nBlocked by: #50, #51\n"
        second = CollectSnapshotTest.story_issue(11, 2, ("factory:story", "status:blocked"))
        fake.issues = [first, second]
        fake.rest_issues[50] = {"number": 50, "state": "closed"}  # #51 does not exist
        snapshot = collect(fake)
        self.assertEqual(snapshot.other_blockers, {50: False})
        self.assertEqual(derive_state(snapshot).details["blocked"], {"10": [51]})
        fake.rest_issues[51] = {"number": 51, "state": "closed"}
        self.assertEqual(derive_state(collect(fake)).details["ready"], [10])


if __name__ == "__main__":
    unittest.main()
