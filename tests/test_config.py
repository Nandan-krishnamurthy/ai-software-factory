"""T1.2: table-driven tests for .factory/config.json validation (architecture §5.3)."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from factory.config import (
    COMMAND_NAMES,
    ConfigError,
    ConfigNotFound,
    load_config,
    parse_config,
)

MINIMAL = {
    "schema": 1,
    "project": "task-tracker",
    "repo": "owner/task-tracker",
    "default_branch": "main",
    "reviewers": ["octocat"],
}

FULL = {
    **MINIMAL,
    "commands": {
        "install": "npm ci",
        "build": "npm run build",
        "lint": "npm run lint",
        "typecheck": None,
        "test": "npm test",
    },
    "limits": {"max_fix_attempts": 2, "max_review_rounds": 4, "max_diff_lines": 250},
    "ci": {"required": True},
    "identity": {"mode": "single-account", "bot_login": None, "bot_token_env": None},
}


def with_changes(base, **changes):
    data = copy.deepcopy(base)
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        node = data
        for key in parents:
            node = node.setdefault(key, {})
        if value is _DELETE:
            node.pop(leaf, None)
        else:
            node[leaf] = value
    return data


_DELETE = object()

# (description, config, substring expected in one of the problems)
INVALID = [
    ("not an object", [], "top level must be a JSON object"),
    ("missing repo", with_changes(MINIMAL, repo=_DELETE), "missing required key 'repo'"),
    ("missing reviewers", with_changes(MINIMAL, reviewers=_DELETE),
     "missing required key 'reviewers'"),
    ("wrong schema", with_changes(MINIMAL, schema=2), "schema must be 1"),
    ("empty project", with_changes(MINIMAL, project=" "), "project must be a non-empty string"),
    ("bad repo", with_changes(MINIMAL, repo="just-a-name"), "repo must look like 'owner/name'"),
    ("repo url instead of slug", with_changes(MINIMAL, repo="https://github.com/o/r"),
     "repo must look like"),
    ("bad branch", with_changes(MINIMAL, default_branch="a..b"), "not a valid branch name"),
    ("empty reviewers", with_changes(MINIMAL, reviewers=[]), "non-empty list"),
    ("bad reviewer login", with_changes(MINIMAL, reviewers=["has space"]),
     "invalid GitHub login"),
    ("unknown top-level key", with_changes(MINIMAL, colour="blue"), "unknown key 'colour'"),
    ("unknown command", with_changes(MINIMAL, commands__deploy="make deploy"),
     "unknown command 'deploy'"),
    ("empty command string", with_changes(MINIMAL, commands__test=""),
     "commands.test must be a non-empty string or null"),
    ("commands not an object", with_changes(MINIMAL, commands=["npm test"]),
     "commands must be an object"),
    ("zero limit", with_changes(MINIMAL, limits__max_fix_attempts=0), "positive integer"),
    ("bool limit", with_changes(MINIMAL, limits__max_diff_lines=True), "positive integer"),
    ("unknown limit", with_changes(MINIMAL, limits__max_minutes=5), "unknown key 'max_minutes'"),
    ("ci.required not bool", with_changes(MINIMAL, ci__required="yes"), "ci.required"),
    # identity (D5 / architecture §9.4)
    ("bot mode not implemented", with_changes(MINIMAL, identity__mode="bot"),
     "'bot' is not implemented yet"),
    ("unknown identity mode", with_changes(MINIMAL, identity__mode="app"),
     "identity.mode must be 'single-account'"),
    ("bot_token_env holding a token", with_changes(
        MINIMAL, identity__bot_token_env="ghp_" + "a" * 36), "looks like a token"),
    ("bot_token_env lowercase", with_changes(MINIMAL, identity__bot_token_env="my token"),
     "must be the NAME of an environment variable"),
    # merging can never be enabled (D1, rule S1)
    ("auto_merge top level", with_changes(MINIMAL, auto_merge=True),
     "merging cannot be configured"),
    ("merge nested in ci", with_changes(MINIMAL, ci__merge_when_green=True),
     "merging cannot be configured"),
    ("allow_merge false still rejected", with_changes(MINIMAL, allow_merge=False),
     "merging cannot be configured"),
    ("merge_method", with_changes(MINIMAL, identity__merge_method="squash"),
     "merging cannot be configured"),
    # secrets are never stored (rules S6, S13)
    ("token key", with_changes(MINIMAL, identity__token="abc"),
     "secrets must not be stored in config"),
    ("github_token key", with_changes(MINIMAL, github_token="abc"),
     "secrets must not be stored in config"),
    ("password key", with_changes(MINIMAL, password="hunter2"),
     "secrets must not be stored in config"),
    ("classic PAT as a value", with_changes(MINIMAL, project="ghp_" + "Z" * 36),
     "looks like a token"),
    ("fine-grained PAT in a command", with_changes(
        MINIMAL, commands__install="npm ci --token github_pat_" + "x" * 30),
     "looks like a token"),
    ("oauth token in reviewers", with_changes(MINIMAL, reviewers=["gho_" + "b" * 36]),
     "looks like a token"),
    ("private key", with_changes(MINIMAL, project="-----BEGIN RSA PRIVATE KEY-----"),
     "looks like a token or private key"),
]


class ValidConfigTest(unittest.TestCase):
    def test_minimal_config_gets_defaults(self):
        cfg = parse_config(MINIMAL)
        self.assertEqual(cfg.repo, "owner/task-tracker")
        self.assertEqual(cfg.reviewers, ("octocat",))
        self.assertEqual(cfg.commands, dict.fromkeys(COMMAND_NAMES))  # all gates skipped
        self.assertEqual(
            (cfg.limits.max_fix_attempts, cfg.limits.max_review_rounds, cfg.limits.max_diff_lines),
            (3, 3, 400),
        )
        self.assertFalse(cfg.ci_required)
        self.assertEqual(cfg.identity.mode, "single-account")

    def test_full_config(self):
        cfg = parse_config(FULL)
        self.assertEqual(cfg.commands["test"], "npm test")
        self.assertIsNone(cfg.commands["typecheck"])
        self.assertEqual(cfg.limits.max_review_rounds, 4)
        self.assertTrue(cfg.ci_required)

    def test_other_valid_variants(self):
        variants = [
            ("bot_token_env names a variable (allowed, still single-account)",
             with_changes(MINIMAL, identity__bot_token_env="FACTORY_BOT_TOKEN")),
            ("branch with slash", with_changes(MINIMAL, default_branch="release/v1")),
            ("repo with dots", with_changes(MINIMAL, repo="my-org/app.web")),
            ("several reviewers", with_changes(MINIMAL, reviewers=["a", "b-c"])),
            ("null sections", with_changes(MINIMAL, commands=None, limits=None)),
            ("'merge' in a value is fine", with_changes(MINIMAL, project="merge-tool")),
        ]
        for name, data in variants:
            with self.subTest(name):
                parse_config(data)


class InvalidConfigTest(unittest.TestCase):
    def test_invalid_configs_are_rejected_with_reason(self):
        for name, data, expected in INVALID:
            with self.subTest(name):
                with self.assertRaises(ConfigError) as ctx:
                    parse_config(data)
                joined = "\n".join(ctx.exception.problems)
                self.assertIn(expected, joined)

    def test_all_problems_reported_together(self):
        data = with_changes(MINIMAL, repo="bad", schema=9, auto_merge=True)
        with self.assertRaises(ConfigError) as ctx:
            parse_config(data)
        self.assertEqual(len(ctx.exception.problems), 3)

    def test_error_message_never_echoes_a_token(self):
        token = "ghp_" + "Q" * 36
        with self.assertRaises(ConfigError) as ctx:
            parse_config(with_changes(MINIMAL, project=token))
        self.assertNotIn(token, str(ctx.exception))


class LoadConfigTest(unittest.TestCase):
    def test_load_from_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".factory" / "config.json"
            path.parent.mkdir()
            path.write_text(json.dumps(FULL), encoding="utf-8")
            self.assertEqual(load_config(tmp).project, "task-tracker")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigNotFound):
                load_config(tmp)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".factory" / "config.json"
            path.parent.mkdir()
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_config(tmp)
            self.assertIn("not valid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
