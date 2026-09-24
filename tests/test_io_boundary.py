"""T1.1 acceptance criterion: no module except gh.py / git.py may use subprocess."""

import ast
import unittest

from tests import SCRIPTS_DIR

ALLOWED = {"factory/gh.py", "factory/git.py"}
FORBIDDEN_MODULES = {"subprocess"}
# Other ways to start processes that would bypass the I/O layer.
FORBIDDEN_CALLS = {("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "spawnv")}


def violations_in(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_MODULES:
            found.append(f"from {node.module} import …")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in FORBIDDEN_CALLS:
                found.append(f"{node.value.id}.{node.attr}")
    return found


class IoBoundaryTest(unittest.TestCase):
    def test_only_gh_and_git_modules_use_subprocess(self):
        files = sorted(SCRIPTS_DIR.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            rel = path.relative_to(SCRIPTS_DIR).as_posix()
            if rel in ALLOWED:
                continue
            with self.subTest(file=rel):
                self.assertEqual(violations_in(path.read_text(encoding="utf-8")), [])

    def test_checker_detects_violations(self):
        # Guard against the check silently passing.
        self.assertTrue(violations_in("import subprocess"))
        self.assertTrue(violations_in("from subprocess import run"))
        self.assertTrue(violations_in("import os\nos.system('x')"))
        self.assertEqual(violations_in("import os\nos.environ"), [])


if __name__ == "__main__":
    unittest.main()
