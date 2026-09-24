"""Templates in ``templates/`` follow their contracts (T2.1).

Each template must contain the ``factory:*`` marker placeholders the state engine looks
for (architecture §5.5) and every section its contract requires, in order: the story
contract (requirements §4), the PR body (requirements §6, §10), the Planning PR (Gate A)
and the traceability matrix (requirements §11). The config template must be a valid
schema-v1 config once filled in (architecture §5.3). Every placeholder is documented in
``templates/README.md``.
"""

import json
import re
import unittest

from factory import markers
from factory.config import COMMAND_NAMES, DEFAULT_LIMITS, ConfigError, parse_config
from tests import REPO_ROOT

TEMPLATES_DIR = REPO_ROOT / "templates"
TEMPLATES = ("config.json", "story.md", "pr.md", "planning-pr.md", "traceability.md")
MARKDOWN_TEMPLATES = tuple(name for name in TEMPLATES if name.endswith(".md"))
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")

STORY_SECTIONS = [
    "Story", "Traces to", "Acceptance criteria", "Out of scope", "Dependencies",
    "Technical notes", "Test plan", "Definition of done",
]
PR_SECTIONS = [
    "Summary", "Traceability", "Acceptance criteria verification", "Tests", "Quality gates",
    "New dependencies", "Doc changes", "Risks / notes for reviewer",
    "Out of scope / follow-ups", "How to review (Gate B)",
]
PLANNING_PR_SECTIONS = [
    "Summary", "Planning documents", "Requirements coverage", "Stories",
    "Issues to be created", "Assumptions and open questions", "Risks / notes for reviewer",
    "How to review (Gate A)",
]
QUALITY_GATES = [
    "Q1 Build", "Q2 Lint & types", "Q3 New tests", "Q4 Full suite", "Q5 AC evidence",
    "Q6 Scope", "Q7 Size", "Q8 CI",
]
# Never appears in any template: merge paths (D1) and direct comments (rule S14).
FORBIDDEN = [
    "gh pr merge", "mergePullRequest", "enablePullRequestAutoMerge", "--auto",
    "gh pr comment", "gh issue comment", "gh pr review",
]


def read(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render(text: str, values: dict[str, str]) -> str:
    """Fill every placeholder. A placeholder missing from ``values`` raises ``KeyError``."""
    return PLACEHOLDER.sub(lambda m: values[m[1]], text)


def sections(text: str) -> list[str]:
    """The level-2 headings, in order, ignoring anything inside code fences."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(line[3:].strip())
    return found


def section_body(text: str, heading: str) -> str:
    """The lines under ``## heading``, up to the next level-2 heading."""
    lines = text.splitlines()
    start = lines.index(f"## {heading}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def readme_sections() -> dict[str, str]:
    """``templates/README.md`` split into its per-template ``### `name` `` sections."""
    parts: dict[str, str] = {}
    current = None
    for line in read("README.md").splitlines():
        match = re.match(r"^### `([^`]+)`$", line)
        if match:
            current = match[1]
            parts[current] = ""
        elif line.startswith("## "):
            current = None
        elif current is not None:
            parts[current] += line + "\n"
    return parts


STORY_VALUES = {
    "story_id": "STORY-007",
    "increment": "001-initial",
    "milestone": "M2",
    "story": "As a user, I want a due date on tasks so that I know what is urgent.",
    "traces_to": "REQ-003, REQ-007",
    "acceptance_criteria": "- [ ] AC1: Given a task, when I set a date, then it is saved.\n"
                           "- [ ] AC2: Given a past date, when I save, then I see an error.",
    "out_of_scope": "- Reminders",
    "blocked_by": "#12, #14",
    "technical_notes": "Touches `src/tasks.ts`.",
    "test_plan": "- Unit: date validation\n- Integration/E2E: None",
}
PR_VALUES = {
    "story_id": "STORY-007",
    "issue": "14",
    "summary": "- Adds a due date field",
    "requirements": "REQ-003, REQ-007",
    "traceability_rows": "REQ-003, REQ-007 updated",
    "ac_verification": "- [x] AC1 — pass — evidence: `tasks.test.ts › #14 AC1` passes",
    "tests_added": "`tasks.test.ts › #14 AC1`",
    "tests_changed": "None",
    "test_command": "npm test",
    "test_result": "42 passed, 0 failed",
    "gate_build": "`npm run build` passed",
    "gate_lint": "Skipped: commands.lint is null",
    "gate_new_tests": "1 test per AC",
    "gate_full_suite": "`npm test` → 42 passed, 0 failed",
    "gate_ac_evidence": "Every AC has evidence",
    "gate_scope": "Only story files touched",
    "gate_size": "120 changed lines",
    "gate_ci": "Not configured",
    "new_dependencies": "None",
    "doc_changes": "None",
    "risks": "None",
    "follow_ups": "None",
}
PLANNING_PR_VALUES = {
    "increment": "001-initial",
    "summary": "- First release",
    "planning_documents": "- [02-requirements.md](increments/001-initial/02-requirements.md)",
    "requirements_coverage": "- REQ-001 → STORY-001",
    "stories": "| STORY-001 | Walking skeleton | M1 | None | REQ-001 |",
    "issues_sync_dry_run": "would create: STORY-001 Walking skeleton",
    "open_questions": "None",
    "risks": "None",
}
TRACEABILITY_VALUES = {
    "rows": "| REQ-001 | STORY-001 (#3) | #21 | `tasks.test.ts › create` | Implemented |\n"
            "| REQ-002 | STORY-002 | — | — | Not started |",
}
CONFIG_VALUES = {
    "project": "sandbox",
    "repo": "owner/sandbox",
    "default_branch": "main",
    "reviewer": "octocat",
}
SAMPLE_VALUES = {
    "story.md": STORY_VALUES,
    "pr.md": PR_VALUES,
    "planning-pr.md": PLANNING_PR_VALUES,
    "traceability.md": TRACEABILITY_VALUES,
    "config.json": CONFIG_VALUES,
}


class TemplateFilesTest(unittest.TestCase):
    def test_exactly_the_planned_templates_exist(self):
        present = {p.name for p in TEMPLATES_DIR.iterdir() if p.is_file()}
        self.assertEqual(present, {*TEMPLATES, "README.md"})


class PlaceholderTest(unittest.TestCase):
    def test_every_brace_pair_is_a_well_formed_placeholder(self):
        for name in TEMPLATES:
            with self.subTest(template=name):
                text = read(name)
                count = len(PLACEHOLDER.findall(text))
                self.assertEqual(text.count("{{"), count, "malformed '{{' in template")
                self.assertEqual(text.count("}}"), count, "malformed '}}' in template")

    def test_readme_documents_exactly_the_placeholders_of_each_template(self):
        documented = readme_sections()
        self.assertEqual(set(documented), set(TEMPLATES))
        for name in TEMPLATES:
            with self.subTest(template=name):
                self.assertEqual(placeholders(documented[name]), placeholders(read(name)))

    def test_sample_values_fill_every_placeholder(self):
        for name in TEMPLATES:
            with self.subTest(template=name):
                self.assertEqual(set(SAMPLE_VALUES[name]), placeholders(read(name)))
                self.assertNotIn("{{", render(read(name), SAMPLE_VALUES[name]))

    def test_unfilled_markers_are_never_recognised(self):
        # An unfilled template must not be mistaken for a real factory object.
        for name in MARKDOWN_TEMPLATES:
            with self.subTest(template=name):
                self.assertEqual(markers.parse_all(read(name)), [])


class StoryTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = read("story.md")
        self.filled = render(self.text, STORY_VALUES)

    def test_sections_follow_the_story_contract(self):
        self.assertEqual(sections(self.text), STORY_SECTIONS)

    def test_story_marker(self):
        self.assertTrue(self.text.startswith(
            "<!-- factory:story id={{story_id}} increment={{increment}} -->"))
        self.assertEqual(markers.parse_all(self.filled),
                         [markers.StoryMarker(id="STORY-007", increment="001-initial")])

    def test_story_id_and_milestone_are_readable(self):
        self.assertIn("**STORY-007**", self.filled)
        self.assertIn("Milestone M2", self.filled)

    def test_dependencies_and_traces(self):
        self.assertEqual(section_body(self.text, "Dependencies"), "Blocked by: {{blocked_by}}")
        self.assertEqual(section_body(self.text, "Traces to"), "{{traces_to}}")
        self.assertEqual(section_body(self.text, "Acceptance criteria"),
                         "{{acceptance_criteria}}")

    def test_definition_of_done_checklist(self):
        self.assertEqual(section_body(self.text, "Definition of done").splitlines(), [
            "- [ ] All ACs verified with evidence",
            "- [ ] Tests added and full suite passing",
            "- [ ] No lint/type errors",
            "- [ ] Docs updated if behaviour changed",
        ])


class PrTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = read("pr.md")
        self.filled = render(self.text, PR_VALUES)

    def test_sections_follow_the_pr_contract(self):
        self.assertEqual(sections(self.text), PR_SECTIONS)

    def test_pr_marker_then_closes_line(self):
        lines = self.text.splitlines()
        self.assertEqual(lines[0], "<!-- factory:pr story={{story_id}} -->")
        self.assertEqual(lines[1], "Closes #{{issue}}")
        self.assertEqual(markers.parse_all(self.filled), [markers.PrMarker(story="STORY-007")])

    def test_traceability_names_requirements_and_story(self):
        body = section_body(self.filled, "Traceability")
        self.assertIn("Requirements: REQ-003, REQ-007", body)
        self.assertIn("Story: #14 (STORY-007)", body)

    def test_ac_section_is_only_the_verifier_output(self):
        # Rule H5: the verifier's verdicts are copied in unchanged, with nothing added.
        self.assertEqual(section_body(self.text, "Acceptance criteria verification"),
                         "{{ac_verification}}")

    def test_tests_section_reports_the_real_full_suite_run(self):
        body = section_body(self.text, "Tests")
        self.assertIn("- Full suite: `{{test_command}}` → {{test_result}}", body)
        self.assertIn("- Changed existing tests: {{tests_changed}}", body)

    def test_every_quality_gate_has_a_row(self):
        rows = [line for line in section_body(self.text, "Quality gates").splitlines()
                if line.startswith("| Q")]
        self.assertEqual([row.split("|")[1].strip() for row in rows], QUALITY_GATES)
        for row in rows:
            self.assertRegex(row.split("|")[2].strip(), PLACEHOLDER)

    def test_explains_gate_b_and_that_the_human_merges(self):
        body = section_body(self.text, "How to review (Gate B)")
        self.assertIn("`/changes`", body)
        self.assertIn("The factory never merges.", body)
        self.assertIn("`/factory-continue`", body)


class PlanningPrTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = read("planning-pr.md")
        self.filled = render(self.text, PLANNING_PR_VALUES)

    def test_sections(self):
        self.assertEqual(sections(self.text), PLANNING_PR_SECTIONS)

    def test_planning_marker(self):
        self.assertTrue(self.text.startswith("<!-- factory:planning increment={{increment}} -->"))
        self.assertEqual(markers.parse_all(self.filled),
                         [markers.PlanningMarker(increment="001-initial")])

    def test_embeds_issues_sync_dry_run_verbatim(self):
        body = section_body(self.text, "Issues to be created")
        self.assertIn("issues sync --dry-run", body)
        self.assertIn("```text\n{{issues_sync_dry_run}}\n```", body)

    def test_explains_gate_a_and_that_the_human_merges(self):
        body = section_body(self.text, "How to review (Gate A)")
        self.assertIn("`/changes`", body)
        self.assertIn("The factory never merges.", body)
        self.assertIn("`/factory-continue`", body)


class TraceabilityTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = read("traceability.md")
        self.filled = render(self.text, TRACEABILITY_VALUES)

    def test_matrix_columns(self):
        lines = self.text.splitlines()
        header = lines.index("| REQ | Stories | PRs | Tests | Status |")
        self.assertEqual(lines[header + 1], "|---|---|---|---|---|")
        self.assertEqual(lines[header + 2], "{{rows}}")

    def test_filled_rows_have_five_cells(self):
        rows = [line for line in self.filled.splitlines() if line.startswith("| REQ-")]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(len(row.strip("|").split("|")), 5)

    def test_documents_the_done_rule_and_statuses(self):
        self.assertIn("**Done**", self.text)
        for status in ("Not started", "In progress", "Implemented", "Deferred"):
            self.assertIn(f"`{status}`", self.text)

    def test_is_a_repo_file_without_markers(self):
        self.assertFalse(markers.has_factory_marker(self.filled))


class ConfigTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = read("config.json")

    def test_is_valid_json_with_every_schema_section(self):
        data = json.loads(self.text)
        self.assertEqual(set(data), {
            "schema", "project", "repo", "default_branch", "reviewers",
            "commands", "limits", "ci", "identity",
        })
        self.assertEqual(tuple(data["commands"]), COMMAND_NAMES)
        self.assertEqual(data["limits"], DEFAULT_LIMITS)

    def test_filled_template_is_a_valid_config(self):
        config = parse_config(json.loads(render(self.text, CONFIG_VALUES)))
        self.assertEqual(config.schema, 1)
        self.assertEqual(config.repo, "owner/sandbox")
        self.assertEqual(config.reviewers, ("octocat",))
        self.assertEqual(config.identity.mode, "single-account")
        self.assertFalse(config.ci_required)

    def test_commands_start_as_null(self):
        # Rule H4: the factory never guesses a command; S01 fills in the ones it finds.
        config = parse_config(json.loads(render(self.text, CONFIG_VALUES)))
        self.assertEqual(config.commands, {name: None for name in COMMAND_NAMES})

    def test_unfilled_template_is_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_config(json.loads(self.text))
        problems = "\n".join(ctx.exception.problems)
        self.assertIn("repo must look like", problems)
        self.assertIn("reviewers: invalid GitHub login", problems)


class SafetyTest(unittest.TestCase):
    def test_no_template_contains_a_merge_path_or_direct_comment(self):
        for name in TEMPLATES:
            text = read(name)
            for forbidden in FORBIDDEN:
                with self.subTest(template=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
