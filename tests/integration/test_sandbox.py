"""T1.4 integration test against the real sandbox repo (plan prerequisite P2).

Skipped unless enabled, because it talks to GitHub and creates labels:

    FACTORY_SANDBOX_REPO=owner/factory-sandbox python -m unittest tests.integration.test_sandbox

It clones the sandbox into a temp directory, runs `labels ensure` twice (the second run
must change nothing), then runs doctor and expects no failed checks.
"""

import os
import tempfile
import unittest
from pathlib import Path

from factory import doctor
from factory.gh import Gh
from factory.git import Git
from factory.labels import REQUIRED_LABELS, ensure_labels, list_labels
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


if __name__ == "__main__":
    unittest.main()
