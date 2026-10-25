"""T7.3: the target's knowledge base, docs/factory/knowledge.md."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import cli, knowledge, target
from factory.git import Git
from factory.knowledge import CheckResult, Diff

IDENTITY = ["-c", "user.name=Factory Test", "-c", "user.email=test@example.invalid"]
PLACEHOLDER = {name: f"{name} placeholder." for name in knowledge.SECTIONS}


def text(checked: str, overrides: dict[str, str] | None = None,
         sections: tuple[str, ...] = knowledge.SECTIONS) -> str:
    """Valid (unless ``sections`` is reordered/short) knowledge.md content."""
    bodies = {**PLACEHOLDER, **(overrides or {})}
    body = "\n\n".join(f"## {name}\n{bodies[name]}" for name in sections)
    return f"<!-- factory:knowledge checked={checked} -->\n# Target knowledge base\n\n{body}\n"


class ParseTest(unittest.TestCase):
    def test_parses_marker_and_sections_in_order(self):
        kf = knowledge.parse(text("a" * 40, {"Stack": "Python."}))
        self.assertEqual(kf.checked, "a" * 40)
        self.assertEqual(tuple(kf.sections), knowledge.SECTIONS)
        self.assertEqual(kf.sections["Stack"], "Python.")

    def test_missing_marker_is_not_well_formed(self):
        kf = knowledge.parse(text("a" * 40).replace(
            "<!-- factory:knowledge checked=" + "a" * 40 + " -->\n", ""))
        self.assertIsNone(kf.checked)
        self.assertFalse(knowledge.well_formed(kf))

    def test_missing_section_is_not_well_formed(self):
        short = text("a" * 7, sections=knowledge.SECTIONS[:-1])  # no Changes
        self.assertFalse(knowledge.well_formed(knowledge.parse(short)))

    def test_out_of_order_sections_are_not_well_formed(self):
        reordered = ("Layout", "Stack", *knowledge.SECTIONS[2:])
        self.assertFalse(knowledge.well_formed(knowledge.parse(text("a" * 7, sections=reordered))))

    def test_extra_heading_breaks_the_order(self):
        injected = text("a" * 7).replace("## Layout", "## Something else\nx\n\n## Layout")
        self.assertFalse(knowledge.well_formed(knowledge.parse(injected)))

    def test_duplicate_heading_keeps_the_first_body(self):
        doc = text("a" * 7) + "\n## Stack\nreplaced?\n"
        kf = knowledge.parse(doc)
        self.assertEqual(tuple(kf.sections), knowledge.SECTIONS)  # the extra repeat is dropped
        self.assertNotIn("replaced?", kf.sections["Stack"])

    def test_empty_text_is_not_well_formed(self):
        self.assertFalse(knowledge.well_formed(knowledge.parse("")))


class ArchitectureLinksTest(unittest.TestCase):
    def test_finds_increment_names_in_any_form(self):
        found = knowledge.architecture_links(
            "- [001-initial](../increments/001-initial/03-architecture.md): walking skeleton\n"
            "- 002-add-due-dates: a new AppState field\n"
            "Not an increment: 01-initial, 0001-initial, STORY-001.")
        self.assertEqual(found, {"001-initial", "002-add-due-dates"})

    def test_empty_text_has_no_links(self):
        self.assertEqual(knowledge.architecture_links(""), frozenset())


class StalenessTest(unittest.TestCase):
    """Pure: ``staleness(sections, Diff)``. No git involved."""

    def setUp(self):
        self.sections = knowledge.parse(text("a" * 7)).sections

    def stale(self, **diff_kwargs):
        return knowledge.staleness(self.sections, Diff(**diff_kwargs))

    def test_fresh_when_nothing_relevant_changed(self):
        self.assertEqual(self.stale(changed=frozenset({"docs/factory/increments/x/foo"})), ())

    def test_stack_and_commands_stale_together_on_a_manifest(self):
        for path in ("package.json", "sub/package.json", "pyproject.toml", "Cargo.lock",
                     ".github/workflows/ci.yml", "Makefile"):
            with self.subTest(path=path):
                result = self.stale(changed=frozenset({path}))
                self.assertIn("Stack", result)
                self.assertIn("Commands", result)

    def test_the_factorys_own_config_makes_nothing_stale(self):
        # S00 and S01 write .factory/config.json themselves on the plan branch (review of
        # PR #52): it is the factory's bookkeeping, so no section goes stale because of it.
        self.assertEqual(self.stale(changed=frozenset({".factory/config.json",
                                                       ".factory/log.md"})), ())

    def test_conventions_stale_on_lint_or_claude_md(self):
        for path in ("CLAUDE.md", "CONTRIBUTING.md", ".editorconfig", "a/.eslintrc.json"):
            with self.subTest(path=path):
                self.assertIn("Conventions", self.stale(changed=frozenset({path})))

    def test_layout_stale_on_a_top_level_change(self):
        result = self.stale(top_level_before=frozenset({"README.md"}),
                            top_level_after=frozenset({"README.md", "src"}))
        self.assertEqual(result, ("Layout",))

    def test_layout_fresh_when_top_level_is_unchanged(self):
        same = frozenset({"README.md", "src", "docs"})
        self.assertEqual(self.stale(top_level_before=same, top_level_after=same), ())

    def test_hotspots_and_known_risks_stale_on_any_non_factory_change(self):
        self.assertEqual(self.stale(changed=frozenset({"src/app.py"})),
                         ("Hotspots", "Known risks"))

    def test_hotspots_and_known_risks_fresh_on_factory_only_changes(self):
        changed = frozenset({"docs/factory/increments/002-x/00-prd.md", ".factory/log.md",
                             "docs/factory/traceability.md"})
        self.assertEqual(self.stale(changed=changed), ())

    def test_architecture_decisions_stale_when_a_merged_increment_is_not_linked(self):
        self.assertEqual(self.stale(architecture_files=frozenset({"002-add-due-dates"})),
                         ("Architecture decisions",))

    def test_architecture_decisions_fresh_when_every_increment_is_linked(self):
        sections = knowledge.parse(text("a" * 7, {
            "Architecture decisions": "See 001-initial and 002-add-due-dates."})).sections
        result = knowledge.staleness(sections, Diff(
            architecture_files=frozenset({"001-initial", "002-add-due-dates"})))
        self.assertEqual(result, ())

    def test_changes_section_is_never_flagged_by_a_diff(self):
        result = self.stale(changed=frozenset({"src/app.py", "package.json", "CLAUDE.md"}),
                            top_level_before=frozenset(), top_level_after=frozenset({"src"}),
                            architecture_files=frozenset({"999-unlinked"}))
        self.assertNotIn("Changes", result)
        self.assertEqual(result, tuple(n for n in knowledge.SECTIONS if n != "Changes"))

    def test_stale_list_follows_section_order_not_detection_order(self):
        # Hotspots/Known risks are flagged after Layout in the code, but Layout must still
        # come first in the result, because it comes first in SECTIONS.
        result = self.stale(top_level_before=frozenset(), top_level_after=frozenset({"src"}),
                            changed=frozenset({"src/x"}))
        self.assertEqual(result, ("Layout", "Hotspots", "Known risks"))


class GitRepo:
    """A real, throwaway git repository (offline), for collect()/check() tests."""

    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git = Git(self.root, timeout=30)
        self.git.run(["init", "-b", "main"])

    def commit(self, path: str, content: str) -> str:
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        self.git.run(["add", path])
        self.git.run([*IDENTITY, "commit", "-m", f"write {path}"])
        return self.git.rev_parse("HEAD")


class CollectTest(unittest.TestCase):
    """``collect()``: the git I/O that feeds ``staleness()``."""

    def test_new_factory_docs_are_not_a_layout_change(self):
        repo = GitRepo(self)
        checked = repo.commit("README.md", "hi")
        repo.commit("docs/factory/increments/001-initial/00-prd.md", "prd")
        repo.commit("docs/factory/knowledge.md", text(checked))
        diff = knowledge.collect(repo.git, checked, "HEAD")
        self.assertEqual(diff.top_level_before, diff.top_level_after)

    def test_a_real_top_level_folder_is_a_layout_change(self):
        repo = GitRepo(self)
        checked = repo.commit("README.md", "hi")
        repo.commit("src/app.py", "print(1)")
        diff = knowledge.collect(repo.git, checked, "HEAD")
        self.assertEqual(diff.top_level_before, frozenset({"README.md"}))
        self.assertEqual(diff.top_level_after, frozenset({"README.md", "src"}))

    def test_architecture_files_are_found_and_filtered_to_real_increments(self):
        repo = GitRepo(self)
        checked = repo.commit("README.md", "hi")
        repo.commit("docs/factory/increments/001-initial/03-architecture.md", "# arch")
        repo.commit("docs/factory/increments/not-an-increment/03-architecture.md", "# x")
        diff = knowledge.collect(repo.git, checked, "HEAD")
        self.assertEqual(diff.architecture_files, frozenset({"001-initial"}))

    def test_unknown_commit_raises(self):
        repo = GitRepo(self)
        repo.commit("README.md", "hi")
        from factory.errors import GitError
        with self.assertRaises(GitError):
            knowledge.collect(repo.git, "0" * 40, "HEAD")


class CheckIntegrationTest(unittest.TestCase):
    """``check()`` end to end, against a real git repository."""

    def test_missing_file(self):
        repo = GitRepo(self)
        repo.commit("README.md", "hi")
        result = knowledge.check(repo.git)
        self.assertEqual(result, CheckResult(missing=True, invalid=False))

    def test_fresh_right_after_creation(self):
        repo = GitRepo(self)
        checked = repo.commit("README.md", "hi")
        repo.commit("docs/factory/knowledge.md", text(checked))
        result = knowledge.check(repo.git)
        self.assertEqual((result.missing, result.invalid, result.stale, result.checked),
                         (False, False, (), checked))
        self.assertTrue(result.ok)

    def test_stale_after_a_relevant_change(self):
        # package.json is an existing top-level file at `checked`, so editing it is a
        # Stack/Commands change without also being a Layout one (isolated further in
        # StalenessTest; this only proves collect() and staleness() are wired together).
        repo = GitRepo(self)
        repo.commit("package.json", "{}")
        checked = repo.commit("README.md", "hi")
        repo.commit("docs/factory/knowledge.md", text(checked))
        repo.commit("package.json", '{"name": "x"}')
        result = knowledge.check(repo.git)
        self.assertIn("Stack", result.stale)
        self.assertIn("Commands", result.stale)
        self.assertNotIn("Layout", result.stale)
        self.assertFalse(result.ok)

    def test_malformed_header_is_invalid_not_missing(self):
        repo = GitRepo(self)
        repo.commit("README.md", "hi")
        repo.commit("docs/factory/knowledge.md", "no marker here\n## Stack\nx\n")
        result = knowledge.check(repo.git)
        self.assertEqual((result.missing, result.invalid), (False, True))
        self.assertIn("header", result.reason)

    def test_unreadable_commit_is_invalid(self):
        repo = GitRepo(self)
        repo.commit("README.md", "hi")
        repo.commit("docs/factory/knowledge.md", text("0" * 40))
        result = knowledge.check(repo.git)
        self.assertEqual((result.missing, result.invalid), (False, True))
        self.assertIn("0" * 40, result.reason)

    def test_ref_defaults_to_head_and_can_be_overridden(self):
        repo = GitRepo(self)
        checked = repo.commit("README.md", "hi")
        created = repo.commit("docs/factory/knowledge.md", text(checked))
        stale_at = repo.commit("package.json", "{}")
        self.assertTrue(knowledge.check(repo.git, created).ok)  # fresh right after creation
        self.assertFalse(knowledge.check(repo.git, stale_at).ok)  # stale once HEAD moved on
        self.assertEqual(knowledge.check(repo.git), knowledge.check(repo.git, "HEAD"))


class ReviewRegressionTest(unittest.TestCase):
    """The two blockers found in the review of PR #52, against real git repositories."""

    def test_s01_done_check_can_pass_on_the_plan_branch(self):
        """An existing project's first increment: S00 creates .factory/config.json on the
        plan branch, S01 sets its commands and writes knowledge.md with the commit of <D>
        it analysed. The factory's own writes must not make the fresh file stale."""
        repo = GitRepo(self)
        repo.commit("src/app.py", "print(1)")
        analysed = repo.commit("requirements.txt", "flask\n")  # origin/<D>, step 1
        repo.git.run(["switch", "-q", "-c", "factory/plan-001-initial"])
        repo.commit(".factory/config.json", "{}")  # S00
        repo.commit("docs/factory/increments/001-initial/00-prd.md", "# PRD")  # S00
        repo.commit("docs/factory/increments/001-initial/01-codebase-analysis.md", "x")
        repo.commit(".factory/config.json", '{"commands": {"test": "pytest"}}')  # S01 step 9
        repo.commit(".factory/log.md", "S01 001-initial discovery")
        repo.commit("docs/factory/knowledge.md", text(analysed))  # S01 step 8
        result = knowledge.check(repo.git)
        self.assertTrue(result.ok, result.to_dict())

        # Fail-safe kept: a real change on the plan branch still makes sections stale.
        repo.commit("requirements.txt", "flask\nrequests\n")
        result = knowledge.check(repo.git)
        self.assertIn("Stack", result.stale)
        self.assertIn("Commands", result.stale)

    def test_a_renamed_manifest_is_stale_whatever_the_rename_config(self):
        """`git mv requirements.txt deps.txt`: with rename detection, `git diff --name-only`
        lists only deps.txt, which is not a manifest. --no-renames lists both paths."""
        for renames in ("true", "false"):
            with self.subTest(diff_renames=renames):
                repo = GitRepo(self)
                repo.git.run(["config", "diff.renames", renames])
                repo.commit("src/app.py", "print(1)")
                checked = repo.commit("requirements.txt", "flask\nrequests\n" * 20)
                repo.commit("docs/factory/knowledge.md", text(checked))
                repo.git.run(["mv", "requirements.txt", "deps.txt"])
                repo.git.run([*IDENTITY, "commit", "-q", "-m", "rename"])
                result = knowledge.check(repo.git)
                self.assertIn("Stack", result.stale)
                self.assertIn("Commands", result.stale)


class RenderTest(unittest.TestCase):
    def test_each_status(self):
        self.assertEqual(knowledge.render(CheckResult(missing=True, invalid=False)),
                         "docs/factory/knowledge.md: missing")
        self.assertEqual(
            knowledge.render(CheckResult(missing=False, invalid=True, reason="bad")),
            "docs/factory/knowledge.md: invalid (bad)")
        self.assertEqual(
            knowledge.render(CheckResult(False, False, ("Stack",), "a" * 40)),
            "docs/factory/knowledge.md: stale (aaaaaaa): Stack")
        self.assertEqual(knowledge.render(CheckResult(False, False, (), "a" * 40)),
                         "docs/factory/knowledge.md: fresh (checked aaaaaaa)")

    def test_to_dict_status_field(self):
        cases = [
            (CheckResult(missing=True, invalid=False), "missing"),
            (CheckResult(False, True, reason="x"), "invalid"),
            (CheckResult(False, False, ("Stack",), "a" * 7), "stale"),
            (CheckResult(False, False, (), "a" * 7), "fresh"),
        ]
        for result, status in cases:
            with self.subTest(status=status):
                self.assertEqual(result.to_dict()["status"], status)
                self.assertEqual(result.to_dict()["ok"], status == "fresh")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.repo = GitRepo(self)
        self.checked = self.repo.commit("README.md", "hi")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(target, "get_target",
                               lambda: target.Target(self.repo.root, "owner/app")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["knowledge", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_missing_is_exit_1(self):
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("missing", out)

    def test_fresh_is_exit_0_and_json_has_every_field(self):
        self.repo.commit("docs/factory/knowledge.md", text(self.checked))
        code, out, err = self.run_cli("check", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data, {"status": "fresh", "checked": self.checked, "stale": [],
                                "reason": None, "ok": True})
        self.assertIn("Target:", err)  # the banner goes to stderr with --json

    def test_stale_is_exit_1(self):
        self.repo.commit("docs/factory/knowledge.md", text(self.checked))
        self.repo.commit("package.json", "{}")
        code, out, _ = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("stale", out)
        self.assertIn("Stack", out)

    def test_ref_argument_is_accepted(self):
        created = self.repo.commit("docs/factory/knowledge.md", text(self.checked))
        code, _, _ = self.run_cli("check", "--ref", created)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
