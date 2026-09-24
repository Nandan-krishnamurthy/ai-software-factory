"""T1.3: factory markers — round-trip, whitespace/CRLF tolerance, malformed input."""

import random
import string
import unittest

from factory.markers import (
    CheckpointMarker,
    PlanningMarker,
    PrMarker,
    ReplyMarker,
    StoryMarker,
    build,
    find,
    has_factory_marker,
    parse_all,
)

CHECKPOINT = CheckpointMarker(
    station="S09", next="S10", branch="story/14-add-due-date", sha="abc1234",
    fix_attempts=1, review_round=0, ts="2026-09-24T10:00:00+00:00",
)
EXAMPLES = [
    StoryMarker(id="STORY-007", increment="001-initial"),
    StoryMarker(id="STORY-1234", increment="002-due-dates-v2"),
    PlanningMarker(increment="001-initial"),
    PrMarker(story="STORY-007"),
    CHECKPOINT,
    CheckpointMarker(station="S05b", next="GATE_A", branch="factory/plan-001",
                     sha="0" * 40, fix_attempts=0, review_round=3, ts="2026-09-24T10:00:00Z"),
    ReplyMarker(),
]


class RoundTripTest(unittest.TestCase):
    def test_parse_of_build_is_identity(self):
        for marker in EXAMPLES:
            with self.subTest(marker=marker):
                self.assertEqual(parse_all(build(marker)), [marker])

    def test_documented_formats(self):
        """The exact strings from architecture §5.5."""
        self.assertEqual(build(EXAMPLES[0]),
                         "<!-- factory:story id=STORY-007 increment=001-initial -->")
        self.assertEqual(build(PlanningMarker("001-initial")),
                         "<!-- factory:planning increment=001-initial -->")
        self.assertEqual(build(PrMarker("STORY-007")), "<!-- factory:pr story=STORY-007 -->")
        self.assertEqual(build(ReplyMarker()), "<!-- factory:reply -->")
        self.assertTrue(build(CHECKPOINT).startswith(
            '<!-- factory:checkpoint {"station":"S09","next":"S10",'))

    def test_markers_inside_surrounding_text(self):
        body = "\n".join(["# Add due date", build(EXAMPLES[0]), "Some text", build(ReplyMarker())])
        self.assertEqual(parse_all(body), [EXAMPLES[0], ReplyMarker()])
        self.assertEqual(find(body, StoryMarker), EXAMPLES[0])
        self.assertIsNone(find(body, PrMarker))

    def test_branch_containing_comment_characters_round_trips(self):
        tricky = CheckpointMarker(station="S08", next="S09", branch="story/1-a-->b<!--c",
                                  sha="abc1234", fix_attempts=0, review_round=0,
                                  ts="2026-09-24T10:00:00+00:00")
        text = build(tricky)
        self.assertNotIn("-->b", text)
        self.assertEqual(text.count("-->"), 1)
        self.assertEqual(parse_all("before " + text + " after " + build(ReplyMarker())),
                         [tricky, ReplyMarker()])


class ToleranceTest(unittest.TestCase):
    def test_whitespace_and_line_break_variants(self):
        expected = StoryMarker(id="STORY-007", increment="001-initial")
        variants = [
            "<!--factory:story id=STORY-007 increment=001-initial-->",
            "<!--   factory:story    id=STORY-007\tincrement=001-initial    -->",
            "<!--\nfactory:story\nid=STORY-007\nincrement=001-initial\n-->",
            "<!--\r\nfactory:story\r\nid=STORY-007\r\nincrement=001-initial\r\n-->",
            "<!-- factory:story increment=001-initial id=STORY-007 -->",  # any order
        ]
        for text in variants:
            with self.subTest(text=text):
                self.assertEqual(parse_all(text), [expected])

    def test_crlf_body_and_checkpoint(self):
        text = build(CHECKPOINT).replace("{", "{\r\n  ").replace(",", ",\r\n  ")
        body = f"Checkpoint\r\n\r\n{text}\r\nS09 Test complete.\r\n"
        self.assertEqual(find(body, CheckpointMarker), CHECKPOINT)

    def test_checkpoint_ignores_unknown_keys(self):
        text = build(CHECKPOINT).replace('"ts"', '"future_field":42,"ts"')
        self.assertEqual(parse_all(text), [CHECKPOINT])

    def test_marker_in_code_block_is_still_a_marker(self):
        # Trust is decided in signals.py (T1.7), not here.
        text = "```\n<!-- factory:reply -->\n```"
        self.assertEqual(parse_all(text), [ReplyMarker()])


class MalformedTest(unittest.TestCase):
    MALFORMED = [
        "<!-- factory:story id=STORY-007 -->",                             # missing attr
        "<!-- factory:story id=STORY-7 increment=001-initial -->",         # bad id
        "<!-- factory:story id=STORY-007 increment=initial -->",           # bad increment
        "<!-- factory:story id=STORY-007 id=STORY-008 increment=001-a -->",  # duplicate key
        "<!-- factory:story id=STORY-007 increment=001-a extra=1 -->",     # unknown attr
        "<!-- factory:story id=STORY-007; rm -rf / increment=001-a -->",   # junk
        '<!-- factory:story id="STORY-007" increment=001-initial -->',     # quotes
        "<!-- factory:pr -->",                                             # missing attr
        "<!-- factory:reply now -->",                                      # attrs on reply
        "<!-- factory:unknown x=1 -->",                                    # unknown kind
        "<!-- factory:Story id=STORY-007 increment=001-initial -->",       # wrong case
        "<!-- factory:checkpoint -->",                                     # no JSON
        "<!-- factory:checkpoint {not json} -->",
        "<!-- factory:checkpoint [1, 2] -->",                              # not an object
        '<!-- factory:checkpoint {"station":"S09"} -->',                   # missing keys
        build(CHECKPOINT).replace('"S09"', '"S9"'),                        # bad station
        build(CHECKPOINT).replace('"S10"', '"DONE"'),                      # bad next
        build(CHECKPOINT).replace('"abc1234"', '"xyz"'),                   # bad sha
        build(CHECKPOINT).replace('"fix_attempts":1', '"fix_attempts":-1'),
        build(CHECKPOINT).replace('"fix_attempts":1', '"fix_attempts":true'),
        build(CHECKPOINT).replace('"review_round":0', '"review_round":"0"'),
        build(CHECKPOINT).replace("2026-09-24T10:00:00+00:00", "yesterday"),
        build(CHECKPOINT).replace('"story/14-add-due-date"', '"  "'),      # blank branch
        build(CHECKPOINT).replace('"story/14-add-due-date"', "null"),
        '<!-- factory:checkpoint ' + "[" * 100000 + " -->",                # huge nesting
        '<!-- factory:checkpoint ' + "[" * 3000 + "]" * 3000 + " -->",     # RecursionError
        "<!-- factory:checkpoint {" + '"a":1,' * 2000 + "} -->",           # oversized
        "<!-- factory:story id=STORY-007 increment=001-initial",           # unterminated
        "factory:story id=STORY-007 increment=001-initial -->",            # no opener
        "<!-- not-factory:story id=STORY-007 increment=001-initial -->",
        "",
    ]

    def test_malformed_markers_are_ignored(self):
        for text in self.MALFORMED:
            with self.subTest(text=text[:80]):
                self.assertEqual(parse_all(text), [])

    def test_none_input(self):
        self.assertEqual(parse_all(None), [])
        self.assertIsNone(find(None, ReplyMarker))

    def test_malformed_marker_does_not_hide_valid_ones(self):
        valid = build(EXAMPLES[0])
        texts = [
            "<!-- factory:story id=BAD --> " + valid,
            "<!-- factory:story id=STORY-007 (unterminated)\n" + valid,
            "<!-- plain html comment\n" + valid,
            valid + " <!-- factory:checkpoint {broken",
        ]
        for text in texts:
            with self.subTest(text=text[:60]):
                self.assertEqual(parse_all(text), [EXAMPLES[0]])

    def test_random_garbage_never_raises(self):
        rng = random.Random(1234)
        alphabet = string.printable + "<!-->{}[]\":=é✓"
        pieces = ["<!--", "-->", "factory:", "checkpoint", "story", "{", "}", "=", " "]
        for _ in range(2000):
            text = "".join(
                rng.choice(pieces) if rng.random() < 0.3 else rng.choice(alphabet)
                for _ in range(rng.randint(0, 120))
            )
            parse_all(text)  # must not raise
            has_factory_marker(text)


class BuildValidationTest(unittest.TestCase):
    def test_build_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            StoryMarker(id="STORY-7", increment="001-initial")
        with self.assertRaises(ValueError):
            PrMarker(story="not-a-story")
        with self.assertRaises(ValueError):
            PlanningMarker(increment="001 initial")
        with self.assertRaises(ValueError):
            CheckpointMarker(station="S09", next="S10", branch="b", sha="abc1234",
                             fix_attempts=0, review_round=0, ts="not a date")

    def test_build_rejects_non_markers(self):
        with self.assertRaises(TypeError):
            build("<!-- factory:reply -->")


class HasFactoryMarkerTest(unittest.TestCase):
    def test_detects_valid_and_malformed_markers(self):
        self.assertTrue(has_factory_marker(build(ReplyMarker())))
        self.assertTrue(has_factory_marker("text <!-- factory:broken"))
        self.assertTrue(has_factory_marker("<!--\r\n FACTORY:reply -->"))

    def test_plain_human_text(self):
        for text in (None, "", "Looks good. /changes please rename x",
                     "<!-- a normal comment -->", "factory: the word alone"):
            with self.subTest(text=text):
                self.assertFalse(has_factory_marker(text))


if __name__ == "__main__":
    unittest.main()
