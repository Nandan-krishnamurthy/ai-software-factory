"""T1.2: target validation, recording, and the Target banner (using temp directories)."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, target
from factory.git import Git
from factory.target import (
    NoTarget,
    TargetError,
    get_target,
    parse_github_remote,
    set_target,
    validate_target,
)
from tests import SCRIPTS_DIR


def make_repo(path: Path, remote: str | None = "https://github.com/owner/app.git") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git = Git(path)
    git.run(["init", "-b", "main"])
    if remote is not None:
        git.run(["remote", "add", "origin", remote])
    return path


class TempWorld(unittest.TestCase):
    """A temp directory holding a fake factory repo and some candidate targets."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.factory = make_repo(self.root / "factory",
                                 "https://github.com/owner/ai-software-factory.git")


class ValidateTargetTest(TempWorld):
    def test_valid_target(self):
        repo = make_repo(self.root / "app")
        result = validate_target(repo, self.factory)
        self.assertEqual(result.path, repo)
        self.assertEqual(result.repo, "owner/app")

    def test_subdirectory_resolves_to_repo_root(self):
        repo = make_repo(self.root / "app")
        (repo / "src").mkdir()
        self.assertEqual(validate_target(repo / "src", self.factory).path, repo)

    def test_refuses_missing_path(self):
        with self.assertRaisesRegex(TargetError, "not an existing directory"):
            validate_target(self.root / "nope", self.factory)

    def test_refuses_non_git_path(self):
        plain = self.root / "plain"
        plain.mkdir()
        with self.assertRaisesRegex(TargetError, "not inside a git repository"):
            validate_target(plain, self.factory)

    def test_refuses_repo_without_remote(self):
        repo = make_repo(self.root / "local-only", remote=None)
        with self.assertRaisesRegex(TargetError, "no 'origin' remote"):
            validate_target(repo, self.factory)

    def test_refuses_non_github_remote(self):
        repo = make_repo(self.root / "gitlab", remote="https://gitlab.com/owner/app.git")
        with self.assertRaisesRegex(TargetError, "not a GitHub repository"):
            validate_target(repo, self.factory)

    def test_refuses_the_factory_repo_itself(self):
        with self.assertRaisesRegex(TargetError, "cannot be the factory repository"):
            validate_target(self.factory, self.factory)

    def test_refuses_factory_subdirectory(self):
        sub = self.factory / "docs"
        sub.mkdir()
        with self.assertRaisesRegex(TargetError, "cannot be the factory repository"):
            validate_target(sub, self.factory)

    def test_refuses_repo_nested_inside_factory(self):
        nested = make_repo(self.factory / "nested-clone")
        with self.assertRaisesRegex(TargetError, "must not be nested"):
            validate_target(nested, self.factory)

    def test_refuses_repo_containing_factory(self):
        outer = make_repo(self.root / "outer")
        inner_factory = make_repo(outer / "factory")
        with self.assertRaisesRegex(TargetError, "must not be nested"):
            validate_target(outer, inner_factory)

    def test_the_real_factory_repo_is_refused_by_default(self):
        with self.assertRaisesRegex(TargetError, "cannot be the factory repository"):
            validate_target(target.FACTORY_ROOT)


class GithubRemoteParsingTest(unittest.TestCase):
    def test_remote_formats(self):
        cases = {
            "https://github.com/o/r.git": "o/r",
            "https://github.com/o/r": "o/r",
            "https://github.com/o/r/": "o/r",
            "https://user@github.com/o/my.repo.git": "o/my.repo",
            "git@github.com:o/r.git": "o/r",
            "ssh://git@github.com/o/r.git": "o/r",
            "https://gitlab.com/o/r.git": None,
            "https://github.com.evil.example/o/r.git": None,
            "https://github.com/o": None,
            "/local/path/repo.git": None,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(parse_github_remote(url), expected)


class SetAndGetTargetTest(TempWorld):
    def settings(self):
        return json.loads((self.factory / ".claude" / "settings.local.json")
                          .read_text(encoding="utf-8"))

    def test_no_target(self):
        with self.assertRaises(NoTarget):
            get_target(self.factory)

    def test_set_records_target_and_additional_directory(self):
        repo = make_repo(self.root / "app")
        set_target(repo, self.factory)
        record = json.loads((self.factory / ".factory-local" / "target.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual((record["path"], record["repo"]), (str(repo), "owner/app"))
        self.assertIn("set_at", record)
        self.assertEqual(self.settings()["permissions"]["additionalDirectories"], [str(repo)])
        self.assertEqual(get_target(self.factory).repo, "owner/app")

    def test_switching_target_replaces_old_dir_and_keeps_other_settings(self):
        settings_file = self.factory / ".claude" / "settings.local.json"
        settings_file.parent.mkdir()
        settings_file.write_text(json.dumps({
            "model": "keep-me",
            "permissions": {"allow": ["Bash(ls)"], "additionalDirectories": ["C:/mine"]},
        }), encoding="utf-8")
        first = make_repo(self.root / "first")
        second = make_repo(self.root / "second", "git@github.com:owner/second.git")
        set_target(first, self.factory)
        set_target(second, self.factory)
        settings = self.settings()
        self.assertEqual(settings["model"], "keep-me")
        self.assertEqual(settings["permissions"]["allow"], ["Bash(ls)"])
        self.assertEqual(settings["permissions"]["additionalDirectories"],
                         ["C:/mine", str(second)])

    def test_setting_same_target_twice_is_idempotent(self):
        repo = make_repo(self.root / "app")
        set_target(repo, self.factory)
        set_target(repo, self.factory)
        self.assertEqual(self.settings()["permissions"]["additionalDirectories"], [str(repo)])

    def test_invalid_target_leaves_previous_target_untouched(self):
        good = make_repo(self.root / "app")
        set_target(good, self.factory)
        with self.assertRaises(TargetError):
            set_target(self.factory, self.factory)
        self.assertEqual(get_target(self.factory).path, good)

    def test_deleted_target_is_reported(self):
        target_file = self.factory / ".factory-local" / "target.json"
        target_file.parent.mkdir()
        target_file.write_text(json.dumps({"path": str(self.root / "gone"), "repo": "o/r"}),
                               encoding="utf-8")
        with self.assertRaisesRegex(TargetError, "no longer exists"):
            get_target(self.factory)

    def test_corrupt_target_file(self):
        target_file = self.factory / ".factory-local" / "target.json"
        target_file.parent.mkdir()
        target_file.write_text("{oops", encoding="utf-8")
        with self.assertRaisesRegex(TargetError, "corrupt"):
            get_target(self.factory)

    def test_corrupt_settings_file_is_not_overwritten(self):
        settings_file = self.factory / ".claude" / "settings.local.json"
        settings_file.parent.mkdir()
        settings_file.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(TargetError, "not valid JSON"):
            set_target(make_repo(self.root / "app"), self.factory)
        self.assertEqual(settings_file.read_text(encoding="utf-8"), "{not json")


class CliTest(TempWorld):
    """The CLI prints `Target: <path> (<owner/repo>)` (rule T2)."""

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_set_then_show_print_banner(self):
        repo = make_repo(self.root / "app")
        code, out, _ = self.run_cli("target", "set", str(repo))
        self.assertEqual(code, 0)
        self.assertIn(f"Target: {repo} (owner/app)", out)
        code, out, _ = self.run_cli("target", "show")
        self.assertEqual((code, out.strip()), (0, f"Target: {repo} (owner/app)"))

    def test_show_json(self):
        repo = make_repo(self.root / "app")
        self.run_cli("target", "set", str(repo))
        code, out, _ = self.run_cli("target", "show", "--json")
        self.assertEqual(json.loads(out), {"path": str(repo), "repo": "owner/app"})

    def test_show_without_target_fails_with_guidance(self):
        code, out, err = self.run_cli("target", "show")
        self.assertEqual(code, 1)
        self.assertIn("/factory-target", err)

    def test_set_invalid_target_fails(self):
        code, _, err = self.run_cli("target", "set", str(self.factory))
        self.assertEqual(code, 1)
        self.assertIn("cannot be the factory repository", err)

    def test_every_target_command_gets_the_banner(self):
        """Any subcommand marked needs_target=True is preceded by the banner."""
        repo = make_repo(self.root / "app")
        self.run_cli("target", "set", str(repo))
        ran = []
        real_build = cli.build_parser

        def build_with_dummy():
            parser = real_build()
            sub = next(a for a in parser._actions if a.dest == "command")
            dummy = sub.add_parser("dummy")
            dummy.set_defaults(handler=lambda args: ran.append(args.target) or 0,
                               needs_target=True)
            return parser

        with mock.patch.object(cli, "build_parser", build_with_dummy):
            code, out, _ = self.run_cli("dummy")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], f"Target: {repo} (owner/app)")
        self.assertEqual(ran[0].repo, "owner/app")

    def test_target_command_without_target_is_refused(self):
        real_build = cli.build_parser

        def build_with_dummy():
            parser = real_build()
            sub = next(a for a in parser._actions if a.dest == "command")
            sub.add_parser("dummy").set_defaults(handler=lambda a: 0, needs_target=True)
            return parser

        with mock.patch.object(cli, "build_parser", build_with_dummy):
            code, _, err = self.run_cli("dummy")
        self.assertEqual(code, 1)
        self.assertIn("no active target", err)


class BannerOrderTest(TempWorld):
    """Found in the M1 demo: with stdout piped (buffered) and an error on stderr, the
    error used to appear before the Target banner. The banner must always come first."""

    def test_banner_precedes_error_when_piped(self):
        repo = make_repo(self.root / "app")  # no commits: the checkpoint fails before any gh
        set_target(repo, self.factory)
        script = (
            "import sys; from pathlib import Path\n"
            f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
            "from factory import cli, target\n"
            f"target.FACTORY_ROOT = Path({str(self.factory)!r})\n"
            "sys.exit(cli.main(['comment', '--issue', '1', '--kind', 'checkpoint',"
            " '--station', 'S08', '--next', 'S09']))\n"
        )
        result = subprocess.run([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=60)
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(lines[0].startswith("Target: "), lines)
        self.assertIn("error: the target has no commits", lines[1])


if __name__ == "__main__":
    unittest.main()
