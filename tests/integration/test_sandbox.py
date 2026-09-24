"""Integration tests against the real sandbox repo (plan prerequisite P2).

Skipped unless enabled, because they talk to GitHub and change the sandbox:

    FACTORY_SANDBOX_REPO=owner/factory-sandbox python -m unittest tests.integration.test_sandbox

* T1.4: clone the sandbox, run `labels ensure` twice (the second run must change
  nothing), then run doctor and expect no failed checks.
* T1.8: `state` against the sandbox (no increment yet) is UNCONFIGURED and valid.
* T1.5: on a throwaway issue, post a reply and a checkpoint twice; expect exactly one
  checkpoint comment and a marker on every comment. The issue is closed afterwards.
* T2.2: `issues sync` for two throwaway stories (unique IDs per run, the second
  blocked by the first): dry run, then two real runs. The second run must create
  nothing, and the dependency must be translated to `#N`. The issues are closed
  afterwards. The Gate A check is skipped here (the sandbox has no merged Planning PR);
  it is covered by the unit tests.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from factory import comments, doctor, issues
from factory import state as state_mod
from factory.gh import Gh
from factory.git import Git
from factory.labels import REQUIRED_LABELS, ensure_labels, list_labels
from factory.markers import CheckpointMarker, StoryMarker, find, has_factory_marker
from factory.stories import parse
from factory.target import validate_target

SANDBOX = os.environ.get("FACTORY_SANDBOX_REPO")


@unittest.skipUnless(SANDBOX, "set FACTORY_SANDBOX_REPO=owner/name to run against GitHub")
class SandboxIntegrationTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clone = Path(tmp.name) / "sandbox"
        Git(tmp.name, timeout=120).run(
            ["clone", "--quiet", f"https://github.com/{SANDBOX}.git", str(self.clone)])
        self.target = validate_target(self.clone)
        self.gh = Gh()

    def test_labels_ensure_twice_then_doctor(self):
        ensure_labels(self.gh, self.target.repo)
        second = ensure_labels(self.gh, self.target.repo)
        self.assertTrue(second.is_noop, "second `labels ensure` must change nothing")
        names = {label["name"] for label in list_labels(self.gh, self.target.repo)}
        self.assertTrue({s.name for s in REQUIRED_LABELS} <= names)

        checks = doctor.run_doctor(self.target, self.gh)
        print("\n" + doctor.render(checks))
        by_name = {c.name: c.status for c in checks}
        self.assertEqual(by_name["labels"], doctor.OK)
        self.assertEqual(by_name["gh auth"], doctor.OK)
        self.assertEqual(by_name["remote"], doctor.OK)
        self.assertEqual(doctor.exit_code(checks), 0)



@unittest.skipUnless(SANDBOX, "set FACTORY_SANDBOX_REPO=owner/name to run against GitHub")
class SandboxCommentTest(unittest.TestCase):
    def setUp(self):
        self.gh = Gh()
        url = self.gh.run(["issue", "create", "--repo", SANDBOX,
                           "--title", "factory integration test: comments (T1.5)",
                           "--body", "Throwaway issue created by tests/integration. "
                                     "It is closed automatically."]).strip()
        self.number = int(url.rstrip("/").rsplit("/", 1)[1])
        self.addCleanup(self.gh.run, ["issue", "close", str(self.number), "--repo", SANDBOX,
                                      "--reason", "completed"])

    def test_reply_and_checkpoint_twice(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        comments.post_reply(self.gh, SANDBOX, self.number, "Integration reply ✓")
        first = comments.upsert_checkpoint(self.gh, SANDBOX, self.number, station="S08",
                                           next_station="S09", branch="story/1-test", sha=sha)
        second = comments.upsert_checkpoint(self.gh, SANDBOX, self.number, station="S09",
                                            next_station="S10", branch="story/1-test", sha=sha,
                                            fix_attempts=1)
        self.assertEqual((first.action, second.action), ("created", "updated"))
        self.assertEqual(first.id, second.id)

        posted = comments.list_comments(self.gh, SANDBOX, self.number)
        self.assertEqual(len(posted), 2)  # one reply + one checkpoint
        self.assertTrue(all(has_factory_marker(c["body"]) for c in posted))
        checkpoints = [c for c in posted if find(c["body"], CheckpointMarker)]
        self.assertEqual(len(checkpoints), 1)
        marker = find(checkpoints[0]["body"], CheckpointMarker)
        self.assertEqual((marker.station, marker.next, marker.fix_attempts), ("S09", "S10", 1))
        print(f"\nsandbox issue #{self.number}: {second.url}")



STORY = """
### {id}: Integration story {n}
- Traces to: REQ-900
- Blocked by: {blocked}
- Milestone: M1
#### Story
As the factory's test suite, I want a throwaway story so that issues sync is exercised.
#### Acceptance criteria
- AC1: Given this story, when issues sync runs twice, then exactly one issue exists.
#### Out of scope
None
#### Technical notes
Created by tests/integration; closed automatically.
#### Test plan
- Integration: tests/integration/test_sandbox.py
"""


@unittest.skipUnless(SANDBOX, "set FACTORY_SANDBOX_REPO=owner/name to run against GitHub")
class SandboxIssuesSyncTest(unittest.TestCase):
    INCREMENT = "900-integration"

    def setUp(self):
        self.gh = Gh()
        base = 9_000_000 + int(time.time()) % 1_000_000  # unique per run: IDs are never reused
        self.first, self.second = f"STORY-{base}", f"STORY-{base + 1}"
        self.text = (STORY.format(id=self.first, n=1, blocked="None")
                     + STORY.format(id=self.second, n=2, blocked=self.first))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.target = Path(tmp.name)
        path = self.target / issues.INCREMENTS_DIR / self.INCREMENT / issues.STORIES_FILE
        path.parent.mkdir(parents=True)
        path.write_text(self.text, encoding="utf-8")
        self.created: list[int] = []
        self.addCleanup(self.close_created)

    def close_created(self):
        for number in self.created:
            self.gh.run(["issue", "close", str(number), "--repo", SANDBOX,
                         "--reason", "completed"])

    def real_run(self):
        # What `issues sync` does once Gate A has passed.
        plan = issues.plan_sync(parse(self.text), self.INCREMENT,
                                issues.list_story_issues(self.gh, SANDBOX))
        result = issues.apply_plan(self.gh, SANDBOX, plan)
        self.created += [result.numbers[story_id] for story_id in result.created]
        return result

    def test_sync_twice_creates_each_issue_once(self):
        dry = issues.sync(self.gh, self.target, SANDBOX, dry_run=True)
        print("\n" + issues.render(dry))
        self.assertEqual([s.id for s in dry.plan.to_create], [self.first, self.second])

        first = self.real_run()
        print(issues.render(first))
        self.assertEqual(first.created, (self.first, self.second))
        second = self.real_run()
        print(issues.render(second))
        self.assertEqual(second.created, ())

        found = issues.list_story_issues(self.gh, SANDBOX)
        self.assertEqual([len(found[self.first]), len(found[self.second])], [1, 1])
        n1, n2 = found[self.first][0].number, found[self.second][0].number
        body = self.gh.json(["issue", "view", str(n2), "--repo", SANDBOX],
                            fields=["body", "labels", "title"])
        self.assertIn(f"Blocked by: #{n1}", body["body"])
        self.assertEqual(find(body["body"], StoryMarker).id, self.second)
        self.assertEqual({label["name"] for label in body["labels"]},
                         {"factory:story", "status:ready"})
        self.assertEqual(body["title"], f"{self.second}: Integration story 2")


@unittest.skipUnless(SANDBOX, "set FACTORY_SANDBOX_REPO=owner/name to run against GitHub")
class SandboxStateTest(unittest.TestCase):
    def test_state_of_the_sandbox(self):
        result = state_mod.derive_state(state_mod.collect_snapshot(Gh(), SANDBOX))
        data = result.to_dict()
        print("\nsandbox state:", data["state"], "-", data["details"]["message"])
        self.assertEqual(state_mod.validate_output(data), [])
        self.assertEqual(data["state"], state_mod.UNCONFIGURED)


if __name__ == "__main__":
    unittest.main()
