"""T2.2: the strict ``05-stories.md`` parser and the Story Contract checks."""

import unittest

from factory import state
from factory.stories import RULES, StoriesError, Story, parse

GOOD = """\
# Stories: increment 001-initial

Free text before the first story is ignored.

## Milestone M1

### STORY-001: Walking skeleton
- Traces to: REQ-001
- Blocked by: None
- Milestone: M1
#### Story
As a developer, I want a project scaffold so that stories have somewhere to land.
#### Acceptance criteria
- AC1: Given a fresh clone, when I run the tests, then one test passes.
#### Out of scope
None
#### Technical notes
Scaffold only.
#### Test plan
- Unit: the smoke test

## Milestone M2

### STORY-002: Add tasks
- Traces to: REQ-002, REQ-003
- Blocked by: STORY-001
- Milestone: M2
#### Story
As a user, I want to add a task so that I can track it.
#### Acceptance criteria
- AC1: Given the task list, when I add a task,
  then it appears in the list.
- [ ] AC2: Given an empty title, when I add a task, then I see an error.
#### Out of scope
- Editing tasks
#### Technical notes
Example config, kept verbatim:

```yaml
### not a story heading, because it is inside a code fence
key: {{value}}
```
##### A deeper heading is content
More notes.
#### Test plan
- Unit: validation
- Integration/E2E: add then list
"""

STORY_3 = """
### STORY-003: Delete tasks
- Traces to: REQ-004
- Blocked by: STORY-002
- Milestone: M2
#### Story
As a user, I want to delete a task so that the list stays short.
#### Acceptance criteria
- AC1: Given a task, when I delete it, then it is gone.
#### Out of scope
None
#### Technical notes
None
#### Test plan
- Unit: delete
"""


def with_story_3(**replace: str) -> str:
    """GOOD plus STORY-003, with ``old=new`` replacements applied to STORY-003 only."""
    story = STORY_3
    for old, new in replace.items():
        assert old in story, old
        story = story.replace(old, new, 1)
    return GOOD + story


class ParseGoodTest(unittest.TestCase):
    def setUp(self):
        self.stories = parse(GOOD)

    def test_stories_in_file_order(self):
        self.assertEqual([s.id for s in self.stories], ["STORY-001", "STORY-002"])
        self.assertTrue(all(isinstance(s, Story) for s in self.stories))

    def test_metadata(self):
        first, second = self.stories
        self.assertEqual(first.title, "Walking skeleton")
        self.assertEqual(first.issue_title, "STORY-001: Walking skeleton")
        self.assertEqual(first.traces_to, ("REQ-001",))
        self.assertEqual(first.blocked_by, ())
        self.assertEqual(first.milestone, "M1")
        self.assertEqual(second.traces_to, ("REQ-002", "REQ-003"))
        self.assertEqual(second.blocked_by, ("STORY-001",))
        self.assertEqual(first.line, 7)

    def test_acceptance_criteria_with_continuation_and_checkbox(self):
        self.assertEqual(self.stories[1].acceptance_criteria, (
            "Given the task list, when I add a task, then it appears in the list.",
            "Given an empty title, when I add a task, then I see an error.",
        ))

    def test_sections_keep_fenced_code_and_deeper_headings(self):
        notes = self.stories[1].technical_notes
        self.assertIn("### not a story heading", notes)
        self.assertIn("key: {{value}}", notes)
        self.assertIn("##### A deeper heading is content", notes)
        self.assertEqual(self.stories[0].out_of_scope, "None")
        self.assertEqual(self.stories[1].test_plan,
                         "- Unit: validation\n- Integration/E2E: add then list")

    def test_crlf_and_whitespace_tolerant(self):
        crlf = GOOD.replace("\n", "\r\n").replace("- Traces to: REQ-001",
                                                  "-   traces to :  REQ-001  ")
        self.assertEqual(parse(crlf), self.stories)

    def test_story_ids_agree_with_the_state_engine(self):
        # state.py counts stories with its own heading regex; both must see the same set.
        text = with_story_3()
        self.assertEqual(set(state._STORY_HEADING.findall(text)),
                         {s.id for s in parse(text)})

    def test_five_acs_is_the_maximum_allowed(self):
        five = "\n".join(f"- AC{n}: Given a, when b, then c." for n in range(1, 6))
        text = with_story_3(**{"- AC1: Given a task, when I delete it, then it is gone.": five})
        self.assertEqual(len(parse(text)[2].acceptance_criteria), 5)


# (description, text, story named in the error or None, rule)
BAD_CASES = [
    ("no stories", "# Stories\n\nNothing yet.\n", None, "no-stories"),
    ("zero ACs", with_story_3(**{"- AC1: Given a task, when I delete it, then it is gone.":
                                 ""}), "STORY-003", "sections"),
    ("six ACs", with_story_3(**{"- AC1: Given a task, when I delete it, then it is gone.":
                                "\n".join(f"- AC{n}: x" for n in range(1, 7))}),
     "STORY-003", "acceptance-criteria"),
    ("AC numbering gap", with_story_3(**{"- AC1: Given": "- AC2: Given"}),
     "STORY-003", "acceptance-criteria"),
    ("AC not a bullet", with_story_3(**{"- AC1: Given": "Given"}),
     "STORY-003", "acceptance-criteria"),
    ("AC without text", with_story_3(**{"- AC1: Given a task, when I delete it, then it "
                                        "is gone.": "- AC1:"}),
     "STORY-003", "acceptance-criteria"),
    ("missing Traces to", with_story_3(**{"- Traces to: REQ-004\n": ""}),
     "STORY-003", "metadata"),
    ("Traces to not a REQ", with_story_3(**{"REQ-004": "requirement 4"}),
     "STORY-003", "traces-to"),
    ("Traces to None", with_story_3(**{"REQ-004": "None"}), "STORY-003", "traces-to"),
    ("Blocked by an issue number", with_story_3(**{"Blocked by: STORY-002": "Blocked by: #12"}),
     "STORY-003", "blocked-by"),
    ("Blocked by itself", with_story_3(**{"Blocked by: STORY-002": "Blocked by: STORY-003"}),
     "STORY-003", "blocked-by"),
    ("Blocked by empty", with_story_3(**{"Blocked by: STORY-002": "Blocked by:"}),
     "STORY-003", "blocked-by"),
    ("missing Blocked by", with_story_3(**{"- Blocked by: STORY-002\n": ""}),
     "STORY-003", "metadata"),
    ("bad milestone", with_story_3(**{"Milestone: M2": "Milestone: two"}),
     "STORY-003", "milestone"),
    ("unknown metadata", with_story_3(**{"- Milestone: M2": "- Milestone: M2\n- Owner: me"}),
     "STORY-003", "metadata"),
    ("duplicate metadata", with_story_3(**{"- Milestone: M2": "- Milestone: M2\n- Milestone: M3"}),
     "STORY-003", "metadata"),
    ("missing section", with_story_3(**{"#### Test plan\n- Unit: delete\n": ""}),
     "STORY-003", "sections"),
    ("empty section", with_story_3(**{"#### Technical notes\nNone": "#### Technical notes\n"}),
     "STORY-003", "sections"),
    ("unknown section", with_story_3(**{"#### Test plan": "#### Notes\nx\n#### Test plan"}),
     "STORY-003", "sections"),
    ("sections out of order", with_story_3(**{
        "#### Out of scope\nNone\n#### Technical notes\nNone":
        "#### Technical notes\nNone\n#### Out of scope\nNone"}), "STORY-003", "sections"),
    ("duplicate id", with_story_3(**{"STORY-003: Delete": "STORY-001: Delete"}),
     "STORY-001", "duplicate-id"),
    ("heading without colon", with_story_3(**{"STORY-003: Delete": "STORY-003 Delete"}),
     None, "heading"),
    ("level-3 heading that is not a story", GOOD + "\n### Notes\nsome text\n", None, "heading"),
    ("heading without title", with_story_3(**{"STORY-003: Delete tasks": "STORY-003:"}),
     "STORY-003", "heading"),
    ("title too long", with_story_3(**{"Delete tasks": "x" * 201}), "STORY-003", "heading"),
    ("factory marker in a story", with_story_3(**{
        "#### Technical notes\nNone": "#### Technical notes\n<!-- factory:checkpoint {} -->"}),
     "STORY-003", "markers"),
    ("dependency cycle", GOOD.replace("- Blocked by: None", "- Blocked by: STORY-002"),
     "STORY-001", "dependency-cycle"),
]


class ParseBadTest(unittest.TestCase):
    def test_each_error_names_the_story_and_the_rule(self):
        for description, text, story, rule in BAD_CASES:
            with self.subTest(description):
                self.assertIn(rule, RULES)
                with self.assertRaises(StoriesError) as ctx:
                    parse(text)
                matching = [p for p in ctx.exception.problems if p.rule == rule]
                self.assertTrue(matching, f"expected rule {rule!r}, got "
                                f"{[str(p) for p in ctx.exception.problems]}")
                self.assertEqual(matching[0].story, story)
                message = str(ctx.exception)
                self.assertIn(f"[{rule}]", message)
                if story:
                    self.assertIn(story, message)

    def test_error_includes_source_and_line(self):
        with self.assertRaises(StoriesError) as ctx:
            parse(with_story_3(**{"Milestone: M2": "Milestone: two"}), "increments/x/05.md")
        message = str(ctx.exception)
        self.assertTrue(message.startswith("increments/x/05.md does not meet the story contract"))
        self.assertRegex(message, r"STORY-003 \(line \d+\) \[milestone\]: 'two' is not a milestone")

    def test_every_problem_is_reported_not_just_the_first(self):
        text = with_story_3(**{"Milestone: M2": "Milestone: two", "REQ-004": "x"})
        text = text.replace("- Blocked by: STORY-001", "- Blocked by: #1")
        with self.assertRaises(StoriesError) as ctx:
            parse(text)
        found = {(p.story, p.rule) for p in ctx.exception.problems}
        self.assertEqual(found, {("STORY-003", "milestone"), ("STORY-003", "traces-to"),
                                 ("STORY-002", "blocked-by")})

    def test_heading_inside_a_fence_does_not_start_a_story(self):
        text = GOOD + "\n```\n### STORY-009: not real\n```\n"
        self.assertEqual([s.id for s in parse(text)], ["STORY-001", "STORY-002"])


if __name__ == "__main__":
    unittest.main()
