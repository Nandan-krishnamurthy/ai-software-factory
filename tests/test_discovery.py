"""T5.1: codebase discovery proposes only the commands a repo declares (rule H4)."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, discovery, target
from factory.config import COMMAND_NAMES
from tests import REPO_ROOT

NPM_SCRIPTS = {"build": "vite build", "lint": "eslint .", "typecheck": "tsc --noEmit",
               "test": "vitest run", "dev": "vite"}


class RepoDir:
    def __init__(self, case: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, name: str, text: str = "") -> "RepoDir":
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return self

    def package(self, scripts=None, **extra) -> "RepoDir":
        return self.write("package.json", json.dumps({"name": "app", "scripts": scripts or {},
                                                      **extra}))


def commands(root: Path) -> dict[str, str | None]:
    return {name: (c.command if c else None)
            for name, c in discovery.discover(root).commands.items()}


class NothingIsGuessedTest(unittest.TestCase):
    """The acceptance criterion: a command nobody declared is null and reported."""

    def test_an_empty_repo_proposes_nothing(self):
        result = discovery.discover(RepoDir(self).root)
        self.assertEqual(result.commands, dict.fromkeys(COMMAND_NAMES))
        self.assertEqual(result.missing, list(COMMAND_NAMES))
        self.assertIn("No known manifest at the repository root.", result.notes)
        self.assertEqual(result.to_dict()["missing"], list(COMMAND_NAMES))

    def test_every_proposal_names_its_evidence(self):
        repo = (RepoDir(self).package(NPM_SCRIPTS).write("package-lock.json", "{}")
                .write("Makefile", "test:\n\tpytest\n").write("go.mod", "module x\n")
                .write("pyproject.toml", "[tool.ruff]\n[tool.pytest.ini_options]\n"))
        result = discovery.discover(repo.root)
        for name, found in result.found.items():
            for candidate in found:
                with self.subTest(command=name, candidate=candidate.command):
                    self.assertTrue(candidate.evidence.strip())
                    self.assertTrue(candidate.command.strip())

    def test_this_repo_declares_no_test_runner_in_its_manifests(self):
        # The factory runs `python -m unittest`, but only its CLAUDE.md says so: discovery
        # leaves it to S01 to take from the docs, with a quote, rather than guess it.
        result = discovery.discover(REPO_ROOT)
        self.assertEqual(commands(REPO_ROOT), {
            "install": None, "build": None, "lint": "python -m ruff check",
            "typecheck": None, "test": None})
        self.assertIn("CLAUDE.md", result.docs)
        self.assertTrue(any("without a test runner configuration" in n for n in result.notes))

    def test_unsupported_stacks_are_named_without_commands(self):
        repo = RepoDir(self).write("pom.xml", "<project/>").write("App.csproj", "<Project/>")
        result = discovery.discover(repo.root)
        self.assertEqual(result.missing, list(COMMAND_NAMES))
        self.assertEqual([name for name, _ in result.stacks], ["Maven", ".NET"])
        self.assertEqual(sum("proposes no commands" in n for n in result.notes), 2)


class NodeTest(unittest.TestCase):
    def test_npm_scripts_and_lockfile(self):
        repo = RepoDir(self).package(NPM_SCRIPTS).write("package-lock.json", "{}")
        result = discovery.discover(repo.root)
        self.assertEqual(commands(repo.root), {
            "install": "npm ci", "build": "npm run build", "lint": "npm run lint",
            "typecheck": "npm run typecheck", "test": "npm test"})
        self.assertEqual(result.commands["test"].evidence, "package.json: scripts.test")
        self.assertEqual(result.commands["install"].evidence, "package-lock.json (npm lockfile)")

    def test_the_lockfile_or_package_manager_field_picks_the_runner(self):
        cases = [
            ({"yarn.lock": ""}, {}, ("yarn install", "yarn build", "yarn test")),
            ({"pnpm-lock.yaml": ""}, {}, ("pnpm install", "pnpm run build", "pnpm test")),
            ({"package-lock.json": "{}"}, {"packageManager": "pnpm@9.1.0"},
             ("pnpm install", "pnpm run build", "pnpm test")),
        ]
        for files, extra, (install, build, test) in cases:
            with self.subTest(files=files, extra=extra):
                repo = RepoDir(self).package({"build": "b", "test": "t"}, **extra)
                for name, text in files.items():
                    repo.write(name, text)
                found = commands(repo.root)
                self.assertEqual((found["install"], found["build"], found["test"]),
                                 (install, build, test))

    def test_without_a_lockfile_the_install_is_not_determined(self):
        repo = RepoDir(self).package({"test": "jest"})
        result = discovery.discover(repo.root)
        self.assertIsNone(result.commands["install"])
        self.assertEqual(result.commands["test"].command, "npm test")
        self.assertIn("no other package manager is declared", result.commands["test"].evidence)
        self.assertTrue(any("install command is not determined" in n for n in result.notes))

    def test_npm_init_placeholder_is_not_a_test_command(self):
        placeholder = 'echo "Error: no test specified" && exit 1'
        repo = RepoDir(self).package({"test": placeholder}).write("package-lock.json", "{}")
        result = discovery.discover(repo.root)
        self.assertIsNone(result.commands["test"])
        self.assertTrue(any("placeholder" in n for n in result.notes))

    def test_only_the_known_script_names_count(self):
        repo = RepoDir(self).package({"type-check": "tsc", "check": "x", "ci": "y",
                                      "test:unit": "vitest"}).write("yarn.lock", "")
        self.assertEqual(commands(repo.root), {
            "install": "yarn install", "build": None, "lint": None,
            "typecheck": "yarn type-check", "test": None})

    def test_an_invalid_package_json_gives_no_commands(self):
        repo = RepoDir(self).write("package.json", "{not json").write("package-lock.json", "{}")
        result = discovery.discover(repo.root)
        self.assertEqual(result.missing, list(COMMAND_NAMES))
        self.assertEqual(result.stacks, [("Node.js", "package.json")])
        self.assertTrue(any("not valid JSON" in n for n in result.notes))


class MakeTest(unittest.TestCase):
    def test_makefile_targets_come_first_and_the_rest_are_alternatives(self):
        repo = (RepoDir(self).package(NPM_SCRIPTS).write("package-lock.json", "{}")
                .write("Makefile", "VERSION := 1\n.PHONY: test\nbuild: deps\n\tgo build\n"
                                   "test:\n\tnpm test\ninstall:\n\tcp app /usr/bin\n"))
        result = discovery.discover(repo.root)
        self.assertEqual(result.commands["build"].command, "make build")
        self.assertEqual(result.commands["test"].evidence, "Makefile: target `test`")
        # `make install` usually installs onto the system: never proposed.
        self.assertEqual(result.commands["install"].command, "npm ci")
        self.assertEqual(result.to_dict()["alternatives"]["test"],
                         [{"command": "npm test", "evidence": "package.json: scripts.test"}])
        self.assertEqual(result.commands["lint"].command, "npm run lint")

    def test_variable_assignments_are_not_targets(self):
        repo = RepoDir(self).write("Makefile", "test := 1\nlint ?= 2\nbuild:=3\n")
        self.assertEqual(discovery.discover(repo.root).missing, list(COMMAND_NAMES))


class PythonTest(unittest.TestCase):
    def test_configured_tools(self):
        repo = (RepoDir(self)
                .write("pyproject.toml", '[tool.pytest.ini_options]\n[tool.ruff]\n'
                                         '[tool.mypy]\nfiles = ["src"]\n')
                .write("requirements.txt", "requests\n"))
        result = discovery.discover(repo.root)
        self.assertEqual(commands(repo.root), {
            "install": "python -m pip install -r requirements.txt", "build": None,
            "lint": "python -m ruff check", "typecheck": "python -m mypy",
            "test": "python -m pytest"})
        self.assertEqual(result.commands["typecheck"].evidence,
                         "pyproject.toml: [tool.mypy] with `files`")

    def test_mypy_without_files_is_reported_not_proposed(self):
        repo = RepoDir(self).write("pyproject.toml", "[tool.mypy]\nstrict = true\n")
        result = discovery.discover(repo.root)
        self.assertIsNone(result.commands["typecheck"])
        self.assertTrue(any("without `files`" in n for n in result.notes))

    def test_ini_style_configuration(self):
        repo = (RepoDir(self).write("setup.cfg", "[tool:pytest]\naddopts = -q\n")
                .write("tox.ini", "[flake8]\nmax-line-length = 100\n")
                .write("mypy.ini", "[mypy]\nfiles = app\n"))
        result = discovery.discover(repo.root)
        self.assertEqual((result.commands["test"].evidence, result.commands["lint"].command,
                          result.commands["typecheck"].evidence),
                         ("setup.cfg: [tool:pytest]", "python -m flake8",
                          "mypy.ini: [mypy] with `files`"))

    def test_unreadable_configuration_is_a_note(self):
        repo = (RepoDir(self).write("pyproject.toml", "[tool.ruff\n")
                .write("setup.cfg", "no section header\n"))
        result = discovery.discover(repo.root)
        self.assertIsNone(result.commands["lint"])
        self.assertTrue(any("not valid TOML" in n for n in result.notes))
        self.assertTrue(any("setup.cfg could not be read" in n for n in result.notes))


class ToolchainTest(unittest.TestCase):
    def test_go_and_rust_standard_commands(self):
        go = RepoDir(self).write("go.mod", "module example.com/x\n")
        self.assertEqual(commands(go.root), {
            "install": None, "build": "go build ./...", "lint": "go vet ./...",
            "typecheck": None, "test": "go test ./..."})
        rust = RepoDir(self).write("Cargo.toml", "[package]\nname = 'x'\n")
        self.assertEqual(commands(rust.root), {
            "install": None, "build": "cargo build", "lint": None, "typecheck": None,
            "test": "cargo test"})


class HintsTest(unittest.TestCase):
    def test_workflow_run_lines_are_hints_not_proposals(self):
        repo = RepoDir(self).write(".github/workflows/ci.yml", (
            "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n"
            "      - run: npm ci\n      - name: Test\n        run: |\n"
            "          npm run lint\n          npm test -- --ci\n"
            "      - run: 'echo done'\n"))
        result = discovery.discover(repo.root)
        self.assertEqual([(h.line, h.text) for h in result.hints],
                         [(5, "npm ci"), (8, "npm run lint"), (9, "npm test -- --ci"),
                          (10, "echo done")])
        self.assertEqual(result.missing, list(COMMAND_NAMES))
        self.assertIn("Hint: .github/workflows/ci.yml:9: npm test -- --ci",
                      discovery.render(result))


class DiscoverCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.factory = Path(tmp.name) / "factory"
        (self.factory / ".factory-local").mkdir(parents=True)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "FACTORY_ROOT", self.factory), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_json_for_a_path(self):
        repo = RepoDir(self).package({"test": "vitest"}).write("package-lock.json", "{}")
        code, out, _ = self.run_cli("discover", "--path", str(repo.root), "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(set(data), {"schema", "stacks", "commands", "alternatives", "missing",
                                     "hints", "docs", "notes"})
        self.assertEqual(data["commands"]["test"],
                         {"command": "npm test", "evidence": "package.json: scripts.test"})
        self.assertIsNone(data["commands"]["build"])
        self.assertEqual(data["missing"], ["build", "lint", "typecheck"])

    def test_the_active_target_by_default_with_its_banner(self):
        repo = RepoDir(self).write("go.mod", "module x\n")
        (self.factory / ".factory-local" / "target.json").write_text(
            json.dumps({"path": str(repo.root), "repo": "owner/app"}), encoding="utf-8")
        code, out, err = self.run_cli("discover", "--json")
        self.assertEqual(code, 0)
        self.assertIn("Target: ", err)
        self.assertEqual(json.loads(out)["commands"]["test"]["command"], "go test ./...")

    def test_no_target_and_no_path(self):
        code, _, err = self.run_cli("discover")
        self.assertEqual(code, 1)
        self.assertIn("no active target", err)

    def test_a_missing_path(self):
        code, _, err = self.run_cli("discover", "--path", str(self.factory / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("is not a directory", err)


if __name__ == "__main__":
    unittest.main()
