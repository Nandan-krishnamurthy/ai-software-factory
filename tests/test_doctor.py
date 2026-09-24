"""T1.4: doctor checks with FakeGh and real temp git repos (offline)."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, doctor, target
from factory.doctor import FAIL, OK, SKIP, WARN, render, run_doctor
from factory.errors import CommandNotFound
from factory.gh import Gh
from factory.gh_fixtures import FakeGh, load_cassette
from factory.git import Git
from factory.labels import REQUIRED_LABELS
from factory.target import Target
from tests import REPO_ROOT

REPO = "owner/app"
REAL = load_cassette(REPO_ROOT / "tests" / "fixtures" / "gh" / "doctor_real.json")
REAL_PROTECTION = json.loads(REAL[1]["stdout"])  # the factory repo's real protection
NOT_PROTECTED_STDERR = REAL[2]["stderr"]         # "gh: Branch not protected (HTTP 404)"
NOT_FOUND_STDERR = REAL[3]["stderr"]             # "gh: Branch not found (HTTP 404)"

CONFIG = {"schema": 1, "project": "app", "repo": REPO, "default_branch": "main",
          "reviewers": ["me"]}
LABELS = [{"name": s.name, "color": s.color, "description": s.description}
          for s in REQUIRED_LABELS]


def call(args, stdout="", returncode=0, stderr=""):
    return {"args": args, "input": None, "returncode": returncode,
            "stdout": stdout if isinstance(stdout, str) else json.dumps(stdout),
            "stderr": stderr}


def user(login="me"):
    return call(["api", "user", "--method", "GET"], {"login": login})


def repo_view(permission="ADMIN", empty=False, branch="main"):
    return call(["repo", "view", REPO, "--json",
                 "nameWithOwner,viewerPermission,defaultBranchRef,isEmpty"],
                {"nameWithOwner": REPO, "viewerPermission": permission, "isEmpty": empty,
                 "defaultBranchRef": {"name": "" if empty else branch}})


def label_list(labels=LABELS):
    return call(["label", "list", "--repo", REPO, "--limit", "1000", "--json",
                 "name,color,description"], labels)


def protection(body=None, stderr=None, branch="main"):
    args = ["api", f"repos/{REPO}/branches/{branch}/protection", "--method", "GET"]
    if stderr is not None:
        return call(args, returncode=1, stderr=stderr)
    return call(args, body if body is not None else REAL_PROTECTION)


class DoctorTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.factory = root / "factory"
        self.factory.mkdir()
        Git(self.factory).run(["init", "-b", "main"])
        self.path = root / "app"
        self.path.mkdir()
        git = Git(self.path)
        git.run(["init", "-b", "main"])
        git.run(["remote", "add", "origin", f"https://github.com/{REPO}.git"])
        self.target = Target(self.path, REPO)

    def write_config(self, data=None):
        path = self.path / ".factory" / "config.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(CONFIG if data is None else data), encoding="utf-8")
        git = Git(self.path)
        git.run(["add", "-A"])
        git.run(["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "cfg"])

    def doctor(self, interactions, gh=None):
        gh = gh or FakeGh(interactions)
        checks = run_doctor(self.target, gh, self.factory)
        if isinstance(gh, FakeGh):
            gh.assert_all_used()
        return {c.name: c for c in checks}, checks

    def statuses(self, by_name):
        return {name: c.status for name, c in by_name.items()}


class HealthyTargetTest(DoctorTestCase):
    def test_all_checks_pass(self):
        self.write_config()
        by_name, checks = self.doctor([user(), repo_view(), label_list(), protection()])
        self.assertEqual(set(self.statuses(by_name).values()), {OK}, render(checks))
        self.assertEqual(doctor.exit_code(checks), 0)
        self.assertIn("Doctor PASSED: 0 failed, 0 warning(s).", render(checks))
        self.assertEqual(list(by_name), ["target", "working tree", "config", "gh auth",
                                         "remote", "labels", "branch protection"])

    def test_fresh_target_only_warns(self):
        """Before /factory-start: no config, empty repo. Warnings only, exit 0."""
        by_name, checks = self.doctor([user(), repo_view(empty=True), label_list()])
        self.assertEqual(by_name["config"].status, WARN)
        self.assertEqual(by_name["branch protection"].status, WARN)
        self.assertEqual(doctor.exit_code(checks), 0)


class FailingChecksTest(DoctorTestCase):
    def test_every_failure_is_listed_and_exit_is_nonzero(self):
        """AC: doctor exits non-zero with a readable list of every failing check."""
        self.write_config({**CONFIG, "repo": "someone/else"})           # config mismatch
        (self.path / "scratch.txt").write_text("x", encoding="utf-8")   # dirty tree
        by_name, checks = self.doctor([
            user(), repo_view(permission="READ"), label_list(LABELS[:3]), protection(),
        ])
        failing = [c.name for c in checks if c.status == FAIL]
        self.assertEqual(failing, ["working tree", "config", "remote", "labels"])
        self.assertEqual(doctor.exit_code(checks), 1)
        text = render(checks)
        for name in failing:
            self.assertRegex(text, rf"\[FAIL\] {name}\s")
        self.assertIn("scratch.txt", by_name["working tree"].detail)
        self.assertIn("does not match", by_name["config"].detail)
        self.assertIn("needs write access", by_name["remote"].detail)
        self.assertIn("missing: status:ready", by_name["labels"].detail)
        self.assertNotIn("factory:story", by_name["labels"].detail)  # present
        self.assertIn("labels ensure", by_name["labels"].detail)
        self.assertIn("Doctor FAILED: 4 failed", text)
        self.assertTrue(text.isascii(), "output must print on any Windows console")

    def test_invalid_config_lists_its_problems(self):
        self.write_config({**CONFIG, "auto_merge": True, "schema": 2})
        by_name, _ = self.doctor([user(), repo_view(), label_list(), protection()])
        self.assertEqual(by_name["config"].status, FAIL)
        self.assertIn("merging cannot be configured", by_name["config"].detail)
        self.assertIn("schema must be 1", by_name["config"].detail)

    def test_target_that_is_the_factory_fails_and_skips_the_rest(self):
        self.target = Target(self.factory, REPO)
        by_name, checks = self.doctor([])
        self.assertEqual(by_name["target"].status, FAIL)
        self.assertEqual({c.status for c in checks[1:]}, {SKIP})
        self.assertEqual(doctor.exit_code(checks), 1)

    def test_not_authenticated(self):
        self.write_config()
        by_name, checks = self.doctor([
            call(["api", "user", "--method", "GET"], returncode=1,
                 stderr="gh: To get started with GitHub CLI, please run:  gh auth login"),
        ])
        self.assertEqual(by_name["gh auth"].status, FAIL)
        self.assertIn("gh auth login", by_name["gh auth"].detail)
        for name in ("remote", "labels", "branch protection"):
            self.assertEqual(by_name[name].status, SKIP)
        self.assertEqual(doctor.exit_code(checks), 1)

    def test_gh_not_installed(self):
        def transport(argv, **kwargs):
            raise CommandNotFound(argv, None, "", "", detail="executable 'gh' not found")

        self.write_config()
        by_name, _ = self.doctor([], gh=Gh(transport=transport))
        self.assertEqual(by_name["gh auth"].status, FAIL)
        self.assertIn("not installed", by_name["gh auth"].detail)

    def test_remote_unreachable(self):
        self.write_config()
        by_name, checks = self.doctor([
            user(),
            call(["repo", "view", REPO, "--json",
                  "nameWithOwner,viewerPermission,defaultBranchRef,isEmpty"],
                 returncode=1, stderr=load_cassette(
                     REPO_ROOT / "tests" / "fixtures" / "gh" / "repo_view.json")[1]["stderr"]),
        ])
        self.assertEqual(by_name["remote"].status, FAIL)
        self.assertIn("Could not resolve to a Repository", by_name["remote"].detail)
        self.assertEqual(by_name["labels"].status, SKIP)


class WarningsTest(DoctorTestCase):
    def test_login_not_in_reviewers(self):
        self.write_config()
        by_name, checks = self.doctor([user("someone"), repo_view(), label_list(), protection()])
        self.assertEqual(by_name["gh auth"].status, WARN)
        self.assertIn("not in config.reviewers", by_name["gh auth"].detail)
        self.assertEqual(doctor.exit_code(checks), 0)

    def test_label_colour_drift(self):
        self.write_config()
        drifted = copy.deepcopy(LABELS)
        drifted[0]["color"] = "000000"
        by_name, _ = self.doctor([user(), repo_view(), label_list(drifted), protection()])
        self.assertEqual(by_name["labels"].status, WARN)

    def test_branch_protection_variants(self):
        approvals = copy.deepcopy(REAL_PROTECTION)
        approvals["required_pull_request_reviews"]["required_approving_review_count"] = 1
        weak = copy.deepcopy(REAL_PROTECTION)
        weak.pop("required_pull_request_reviews")
        weak["allow_force_pushes"] = {"enabled": True}
        weak["enforce_admins"] = {"enabled": False}
        cases = [
            ("real factory-repo protection", protection(), OK, "requires a pull request"),
            ("not protected (real stderr)", protection(stderr=NOT_PROTECTED_STDERR), WARN,
             "is not protected"),
            ("branch not found (real stderr)", protection(stderr=NOT_FOUND_STDERR), WARN,
             "does not exist yet"),
            ("no admin access", protection(stderr="gh: Must have admin rights (HTTP 403)"),
             WARN, "needs admin"),
            ("approvals required", protection(approvals), WARN, "blocks your own merge"),
            ("weak protection", protection(weak), WARN, "force pushes are allowed"),
        ]
        self.write_config()
        for name, response, status, text in cases:
            with self.subTest(name):
                by_name, checks = self.doctor([user(), repo_view(), label_list(), response])
                self.assertEqual(by_name["branch protection"].status, status)
                self.assertIn(text, by_name["branch protection"].detail)
                self.assertEqual(doctor.exit_code(checks), 0)  # never a failure

    def test_branch_with_slash_is_url_encoded(self):
        self.write_config({**CONFIG, "default_branch": "release/v1"})
        by_name, _ = self.doctor([user(), repo_view(), label_list(),
                                  protection(branch="release%2Fv1")])
        self.assertEqual(by_name["branch protection"].status, OK)


class DoctorCliTest(DoctorTestCase):
    def run_cli(self, argv, interactions):
        (self.factory / ".factory-local").mkdir()
        (self.factory / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(self.path), "repo": REPO}), encoding="utf-8")
        fake = FakeGh(interactions)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                mock.patch.object(cli, "Gh", lambda: fake), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_cli_prints_banner_and_exits_nonzero_on_failure(self):
        (self.path / "dirty.txt").write_text("x", encoding="utf-8")
        code, out = self.run_cli(["doctor"], [user(), repo_view(empty=True), label_list([])])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], f"Target: {self.path} ({REPO})")
        self.assertIn("[FAIL] working tree", out)
        self.assertIn("[FAIL] labels", out)

    def test_cli_json(self):
        self.write_config()
        code, out = self.run_cli(["doctor", "--json"],
                                 [user(), repo_view(), label_list(), protection()])
        self.assertEqual(code, 0)
        payload = json.loads(out)  # with --json the Target banner goes to stderr
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["checks"]), 7)

    def test_cli_labels_ensure(self):
        creates = [call(["label", "create", s.name, "--repo", REPO, "--color", s.color,
                         "--description", s.description]) for s in REQUIRED_LABELS]
        code, out = self.run_cli(["labels", "ensure"], [label_list([]), *creates])
        self.assertEqual(code, 0)
        self.assertIn(f"Labels: {len(REQUIRED_LABELS)} created, 0 updated, 0 unchanged.", out)


if __name__ == "__main__":
    unittest.main()
