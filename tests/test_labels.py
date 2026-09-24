"""T1.4: label planning and `labels ensure` idempotency (FakeGh)."""

import json
import unittest

from factory.gh_fixtures import FakeGh, UnexpectedCall, load_cassette
from factory.labels import REQUIRED_LABELS, LabelSpec, ensure_labels, plan_labels
from tests import REPO_ROOT

REPO = "owner/app"
LIST_ARGS = ["label", "list", "--repo", REPO, "--limit", "1000",
             "--json", "name,color,description"]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gh" / "doctor_real.json"


def real_sandbox_labels() -> list[dict]:
    """GitHub's default labels, as recorded from the real (fresh) sandbox repo."""
    first = load_cassette(FIXTURE)[0]
    assert first["args"][:2] == ["label", "list"]
    return json.loads(first["stdout"])


def as_existing(specs):
    return [{"name": s.name, "color": s.color, "description": s.description} for s in specs]


def list_call(labels):
    return {"args": LIST_ARGS, "input": None, "returncode": 0,
            "stdout": json.dumps(labels), "stderr": ""}


def write_call(args):
    return {"args": args, "input": None, "returncode": 0, "stdout": "", "stderr": ""}


class RequiredLabelsTest(unittest.TestCase):
    def test_required_set_matches_requirements(self):
        names = {s.name for s in REQUIRED_LABELS}
        self.assertEqual(names, {
            "factory:story", "factory:planning", "factory:needs-human",
            "status:ready", "status:blocked", "status:in-progress", "status:in-review",
            "status:changes-requested", "status:done",
        })

    def test_specs_are_valid_for_github(self):
        for spec in REQUIRED_LABELS:
            with self.subTest(spec.name):
                self.assertRegex(spec.color, r"^[0-9a-f]{6}$")
                self.assertLessEqual(len(spec.description), 100)  # GitHub's limit
                self.assertLessEqual(len(spec.name), 50)


class PlanLabelsTest(unittest.TestCase):
    def test_fresh_repo_needs_every_label(self):
        plan = plan_labels(real_sandbox_labels())
        self.assertEqual(plan.create, list(REQUIRED_LABELS))
        self.assertEqual((plan.update, plan.unchanged), ([], []))

    def test_everything_present_is_a_noop(self):
        plan = plan_labels(real_sandbox_labels() + as_existing(REQUIRED_LABELS))
        self.assertTrue(plan.is_noop)
        self.assertEqual(len(plan.unchanged), len(REQUIRED_LABELS))

    def test_color_compared_case_insensitively(self):
        existing = as_existing(REQUIRED_LABELS)
        existing[0]["color"] = existing[0]["color"].upper()
        self.assertTrue(plan_labels(existing).is_noop)

    def test_changed_color_or_description_is_updated(self):
        existing = as_existing(REQUIRED_LABELS)
        existing[0]["color"] = "000000"
        existing[1]["description"] = "edited by hand"
        plan = plan_labels(existing)
        self.assertEqual([spec.name for _, spec in plan.update],
                         [REQUIRED_LABELS[0].name, REQUIRED_LABELS[1].name])
        self.assertEqual(plan.create, [])

    def test_different_case_name_is_renamed_not_duplicated(self):
        existing = as_existing(REQUIRED_LABELS)
        existing[-1]["name"] = "Status:Done"
        plan = plan_labels(existing)
        self.assertEqual(plan.create, [])
        self.assertEqual(plan.update, [("Status:Done", REQUIRED_LABELS[-1])])


class EnsureLabelsTest(unittest.TestCase):
    def test_first_run_creates_all_then_second_run_changes_nothing(self):
        """AC: running `labels ensure` twice gives the same result."""
        creates = [
            write_call(["label", "create", s.name, "--repo", REPO,
                        "--color", s.color, "--description", s.description])
            for s in REQUIRED_LABELS
        ]
        first = FakeGh([list_call(real_sandbox_labels()), *creates])
        plan = ensure_labels(first, REPO)
        first.assert_all_used()
        self.assertEqual(len(plan.create), len(REQUIRED_LABELS))

        # Second run: the repo now has the labels. Only the list call is allowed;
        # FakeGh raises UnexpectedCall on any create/edit.
        second = FakeGh([list_call(real_sandbox_labels() + as_existing(REQUIRED_LABELS))])
        plan = ensure_labels(second, REPO)
        second.assert_all_used()
        self.assertTrue(plan.is_noop)
        self.assertEqual([c["args"][:2] for c in second.replay.calls], [["label", "list"]])

    def test_update_and_rename_arguments(self):
        existing = as_existing(REQUIRED_LABELS)
        existing[-1].update(name="Status:Done", color="ffffff")
        spec = REQUIRED_LABELS[-1]
        gh = FakeGh([
            list_call(existing),
            write_call(["label", "edit", "Status:Done", "--repo", REPO, "--color", spec.color,
                        "--description", spec.description, "--name", spec.name]),
        ])
        ensure_labels(gh, REPO)
        gh.assert_all_used()

    def test_other_labels_are_never_touched(self):
        gh = FakeGh([list_call(real_sandbox_labels() + as_existing(REQUIRED_LABELS))])
        ensure_labels(gh, REPO)
        for call in gh.replay.calls:
            self.assertNotIn("delete", call["args"])

    def test_write_failure_propagates(self):
        spec = REQUIRED_LABELS[0]
        gh = FakeGh([list_call([])])
        with self.assertRaises(UnexpectedCall):
            ensure_labels(gh, REPO)  # the create call is not in the cassette
        self.assertEqual(gh.replay.calls[-1]["args"][:3], ["label", "create", spec.name])


class LabelSpecTest(unittest.TestCase):
    def test_frozen(self):
        with self.assertRaises(AttributeError):
            LabelSpec("a", "000000", "b").name = "c"


if __name__ == "__main__":
    unittest.main()
