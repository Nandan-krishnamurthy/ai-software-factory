"""Integration tests against the real sandbox repo (plan prerequisite P2).

Skipped unless enabled, because they talk to GitHub and change the sandbox:

    FACTORY_SANDBOX_REPO=owner/factory-sandbox python -m unittest tests.integration.test_sandbox

* T1.4: clone the sandbox, run `labels ensure` twice (the second run must change
  nothing), then run doctor and expect no failed checks.
* T1.5: on a throwaway issue, post a reply and a checkpoint twice; expect exactly one
  checkpoint comment and a marker on every comment. The issue is closed afterwards.
"""

import os
import tempfile
import unittest
from pathlib import Path

from factory import comments, doctor
from factory.gh import Gh
from factory.git import Git
from factory.labels import REQUIRED_LABELS, ensure_labels, list_labels
from factory.markers import CheckpointMarker, find, has_factory_marker
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


if __name__ == "__main__":
    unittest.main()
