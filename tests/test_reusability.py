"""T5.4: nothing in the factory is specific to one target (success criterion 8).

The factory runs on any target repo. Everything project-specific lives in the target's
``.factory/config.json`` and ``docs/factory/`` (requirements §14, criterion 8), so the
folders the factory runs from (``scripts/``, ``stations/``, ``.claude/``, ``templates/``)
must not name the Task Tracker test project, its stack or its owner. Docs and tests may:
they describe how the factory was proven.

The one place allowed to name an ecosystem is codebase discovery (S01, T5.1), which must
know the manifests of every stack it supports. That exception is narrow and checked: those
files must also name the other stacks, so they stay multi-stack. The same holds for the
evidence ledger's summary parser (T6.1), which must recognise the output of every test
runner it supports: it may name test runners only alongside the others.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from factory import target
from factory.git import Git
from tests import REPO_ROOT

AUDITED = ("scripts", "stations", ".claude", "templates")
# The gitignored per-machine files (rule S3's exception): they name the active target.
LOCAL_FILES = {Path(".claude") / "settings.local.json"}

# The test project, its content and its owner: never in the factory's own files.
PROJECT_SPECIFIC = {
    "the project's name": r"task[-_ ]?tracker",
    "its test repo or sandbox": r"factory-sandbox|celsius",
    "its owner": r"nandan",
    "a local checkout path": r"[a-z]:[\\/]+projects\b|/c/projects\b",
    "its domain examples": r"\btasks?\.(?:test|spec)\b|\badd-task\b|due dates?|buy milk|"
                           r"walk dog",
    "its browser storage": r"localstorage",
}
# Its stack: Task Tracker is TypeScript + Vite, tested with Vitest, Playwright and axe.
STACK_SPECIFIC = {
    "its build tool": r"\bvite\b",
    "its test runners": r"vitest|playwright|jsdom|axe-core|@axe",
    "its language tooling": r"typescript|\btsc\b|\.(?:test|spec)\.tsx?\b",
}
# Node.js names that only multi-stack discovery may use (S01, T5.1).
NODE = r"\bnpm\b|\byarn\b|\bpnpm\b|package\.json|package-lock|node_modules"
DISCOVERY_FILES = {Path("scripts/factory/discovery.py"), Path("stations/S01-discovery.md"),
                   Path("scripts/factory/cli.py")}  # cli.py: the `discover` help text
OTHER_STACKS = ("Python", "go.mod", "Cargo.toml", "Makefile")
# Test-runner names that only the multi-runner summary parser may use (T6.1).
RUNNER_FILES = {Path("scripts/factory/evidence.py")}
OTHER_RUNNERS = ("pytest", "unittest", "go test", "cargo test")


def audited_files(root: Path = REPO_ROOT) -> list[Path]:
    files = []
    for folder in AUDITED:
        for path in sorted((root / folder).rglob("*")):
            rel = path.relative_to(root)
            if path.is_file() and "__pycache__" not in rel.parts and rel not in LOCAL_FILES:
                files.append(rel)
    return files


def findings(root: Path = REPO_ROOT) -> list[str]:
    """Every target-specific string in the audited folders, as ``file:line: why: text``."""
    found = []
    rules = [(why, re.compile(p, re.I)) for why, p in {**PROJECT_SPECIFIC,
                                                        **STACK_SPECIFIC}.items()]
    node = re.compile(NODE, re.I)
    for rel in audited_files(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for why, pattern in rules:
                if why == "its test runners" and rel in RUNNER_FILES:
                    continue
                if match := pattern.search(line):
                    found.append(f"{rel.as_posix()}:{number}: {why}: {match.group(0)!r}")
            if rel not in DISCOVERY_FILES and (match := node.search(line)):
                found.append(f"{rel.as_posix()}:{number}: a Node.js name outside discovery: "
                             f"{match.group(0)!r}")
    return found


class ReusabilityTest(unittest.TestCase):
    def test_no_target_specific_strings_in_the_factory(self):
        self.assertEqual(findings(), [], "move project-specific values into the target's "
                                         ".factory/config.json or docs/factory/")

    def test_the_audit_covers_the_factory(self):
        files = {p.as_posix() for p in audited_files()}
        for expected in ("scripts/factory/state.py", "stations/S08-implement.md",
                         ".claude/settings.json", ".claude/agents/ac-verifier.md",
                         ".claude/commands/factory-start.md", "templates/config.json"):
            with self.subTest(file=expected):
                self.assertIn(expected, files)
        self.assertGreater(len(files), 50)

    def test_the_audit_catches_what_it_should(self):
        """Not vacuous: each kind of string is found when planted."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planted = {
                "scripts/x.py": 'REPO = "someone/Task-Tracker"',
                "stations/S99-x.md": "Run `npx playwright test` in C:\\Projects\\app.",
                ".claude/agents/x.md": "Evidence: `tests/tasks.test.ts` (`npm test`)",
                "templates/x.md": "Store it in localStorage with Vite.",
                "scripts/factory/discovery.py": "npm ci  # allowed here",
                "scripts/factory/evidence.py": "_VITEST = ...  # allowed here",
            }
            for name, text in planted.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            whys = "\n".join(findings(root))
        for expected in ("scripts/x.py:1: the project's name",
                         "stations/S99-x.md:1: its test runners",
                         "stations/S99-x.md:1: a local checkout path",
                         ".claude/agents/x.md:1: its domain examples",
                         ".claude/agents/x.md:1: a Node.js name outside discovery",
                         "templates/x.md:1: its browser storage",
                         "templates/x.md:1: its build tool"):
            with self.subTest(expected=expected):
                self.assertIn(expected, whys)
        self.assertNotIn("discovery.py", whys)
        self.assertNotIn("evidence.py", whys)

    def test_discovery_names_node_only_among_other_stacks(self):
        """The Node.js exception is for multi-stack discovery, not a Node.js factory."""
        for rel in DISCOVERY_FILES - {Path("scripts/factory/cli.py")}:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for stack in OTHER_STACKS:
                with self.subTest(file=rel.as_posix(), stack=stack):
                    self.assertTrue(stack in text, f"{rel.as_posix()} does not name {stack}")

    def test_summary_parser_names_runners_only_among_other_runners(self):
        """The runner-name exception is for a multi-runner parser, not a Vitest factory."""
        for rel in RUNNER_FILES:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for runner in OTHER_RUNNERS:
                with self.subTest(file=rel.as_posix(), runner=runner):
                    self.assertTrue(runner in text, f"{rel.as_posix()} does not name {runner}")


class OneCheckoutManyTargetsTest(unittest.TestCase):
    """Criterion 8: the same checkout is pointed at different targets with no code change.
    Selecting a target writes only the two gitignored per-machine files."""

    def make_repo(self, root: Path, name: str, owner: str) -> Path:
        path = root / name
        path.mkdir()
        git = Git(path)
        git.run(["init", "-q", "-b", "main"])
        git.run(["remote", "add", "origin", f"https://github.com/{owner}/{name}.git"])
        return path

    def test_switching_targets_touches_only_gitignored_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            factory = root / "factory"
            factory.mkdir()
            first = self.make_repo(root, "inventory-api", "acme")
            second = self.make_repo(root, "weather-cli", "example")
            before = {p for p in factory.rglob("*")}
            seen = []
            for path in (first, second, first):
                chosen = target.set_target(path, factory_root=factory)
                active = target.get_target(factory_root=factory)
                seen.append((chosen.repo, active.repo, active.path == path))
                settings = json.loads((factory / target.SETTINGS_LOCAL).read_text("utf-8"))
                self.assertEqual(settings["permissions"]["additionalDirectories"], [str(path)])
            written = {p.relative_to(factory) for p in factory.rglob("*") if p.is_file()}
            self.assertEqual(before, set())
        self.assertEqual(seen, [("acme/inventory-api", "acme/inventory-api", True),
                                ("example/weather-cli", "example/weather-cli", True),
                                ("acme/inventory-api", "acme/inventory-api", True)])
        self.assertEqual(written, {target.TARGET_FILE, target.SETTINGS_LOCAL})

    def test_those_files_are_gitignored(self):
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".factory-local/", ignored)
        self.assertIn(".claude/settings.local.json", ignored)
        self.assertEqual(target.TARGET_FILE.parts[0], ".factory-local")


if __name__ == "__main__":
    unittest.main()
