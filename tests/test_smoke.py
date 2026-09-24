"""Smoke tests: every module imports, and the CLI entry point runs."""

import importlib
import pkgutil
import subprocess
import sys
import unittest

import factory
from tests import REPO_ROOT, SCRIPTS_DIR


class ImportEveryModuleTest(unittest.TestCase):
    def test_every_factory_module_imports(self):
        names = [m.name for m in pkgutil.walk_packages(factory.__path__, prefix="factory.")]
        self.assertIn("factory.cli", names)
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(name)


class CliEntryPointTest(unittest.TestCase):
    def run_cli(self, *args):
        # Run from a directory other than the repo root to prove the entry
        # point does not depend on the current working directory.
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "factory.py"), *args],
            cwd=REPO_ROOT / "tests",
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_help_lists_subcommands_section(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: factory.py", result.stdout)
        self.assertIn("subcommands:", result.stdout)

    def test_no_arguments_prints_help_and_succeeds(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("subcommands:", result.stdout)

    def test_unknown_subcommand_fails(self):
        result = self.run_cli("does-not-exist")
        self.assertNotEqual(result.returncode, 0)

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(factory.__version__, result.stdout)


if __name__ == "__main__":
    unittest.main()
