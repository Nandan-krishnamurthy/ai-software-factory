"""T5.4: the README covers install and usage, and the runbook covers criteria 1-8."""

import re
import unittest

from factory import commands
from tests import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
RUNBOOK_PATH = REPO_ROOT / "docs" / "04-task-tracker-test-plan.md"


class ReadmeTest(unittest.TestCase):
    def test_install_and_usage_sections(self):
        for heading in ("## Requirements", "## Install", "## Usage", "### Commands",
                        "## Working on the factory itself", "## Documents"):
            with self.subTest(heading=heading):
                self.assertIn(heading + "\n", README)

    def test_every_command_is_documented(self):
        names = {p.stem for p in (REPO_ROOT / ".claude" / "commands").glob("*.md")}
        self.assertEqual(names, {"factory-target", "factory-start", "factory-resume",
                                 "factory-continue", "factory-status"})
        table = README[README.index("### Commands"):README.index("### What the factory")]
        for name in names:
            with self.subTest(command=name):
                self.assertIn(f"| `/{name}", table)
        self.assertEqual(set(commands.COMMANDS) - {f"/{n}" for n in names}, set())

    def test_prerequisites_and_checks(self):
        for text in ("Python 3.11", "gh auth login", "Claude Code", "python -m unittest",
                     "python -m ruff check", ".factory-local/target.json",
                     ".claude/settings.local.json"):
            with self.subTest(text=text):
                self.assertIn(text, README)

    def test_says_the_human_merges(self):
        self.assertIn("never merges anything itself", README)
        self.assertIn("merge the Planning PR yourself", README)
        self.assertIn("merge the PR yourself", README)

    def test_relative_links_exist(self):
        for link in re.findall(r"\]\(((?!https?:)[^)#]+)(?:#[^)]*)?\)", README):
            with self.subTest(link=link):
                self.assertTrue((REPO_ROOT / link).exists(), link)


class RunbookTest(unittest.TestCase):
    def setUp(self):
        self.text = RUNBOOK_PATH.read_text(encoding="utf-8")

    def test_one_section_per_success_criterion(self):
        found = re.findall(r"^## (\d)\. ", self.text, re.MULTILINE)
        self.assertEqual(found, [str(n) for n in range(1, 9)])

    def test_status_table_has_every_criterion(self):
        rows = re.findall(r"^\| (\d) \|", self.text, re.MULTILINE)
        self.assertEqual(rows, [str(n) for n in range(1, 9)])

    def test_each_criterion_has_steps_or_checks_and_what_to_expect(self):
        sections = re.split(r"^## \d\. ", self.text, flags=re.MULTILINE)[1:9]
        for number, section in enumerate(sections, start=1):
            with self.subTest(criterion=number):
                self.assertRegex(section, r"\*\*Goal:\*\*")
                self.assertRegex(section, r"\*\*(Steps|Checks)")
                self.assertRegex(section, r"Expect")

    def test_relative_links_exist(self):
        for link in re.findall(r"\]\(((?!https?:)[^)#]+)(?:#[^)]*)?\)", self.text):
            with self.subTest(link=link):
                self.assertTrue((RUNBOOK_PATH.parent / link).exists(), link)


if __name__ == "__main__":
    unittest.main()
