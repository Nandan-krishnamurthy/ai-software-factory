"""T1.6: the PreToolUse guard — table-driven block/allow cases, hook adapter, settings."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import guard_hook
from factory.guard import GuardContext, decide
from tests import REPO_ROOT

_TMP = tempfile.TemporaryDirectory()
ROOT = Path(_TMP.name).resolve()
FACTORY = ROOT / "factory"
TARGET = ROOT / "app"
SCRATCH = ROOT / "scratch"
MEMORY = ROOT / "home" / ".claude" / "projects"
OUTSIDE = ROOT / "elsewhere"

# Branch that each repo dir is on (for plain `git push` / `git push origin HEAD`).
BRANCHES = {TARGET: "story/12-add-due-date", FACTORY: "task/T1.6-guard", OUTSIDE: "main"}
# Whether a branch already has a PR (reviewed): None means "could not tell".
REVIEWED = {"story/12-add-due-date": True, "story/13-fresh": False}


def ctx(target=True, cwd=None, **overrides) -> GuardContext:
    values = dict(
        factory_root=FACTORY,
        target_root=TARGET if target else None,
        cwd=cwd or (TARGET if target else FACTORY),
        default_branch="main",
        scratch_dirs=(SCRATCH,),
        extra_write_dirs=(MEMORY,),
        current_branch=lambda d: BRANCHES.get(Path(d)),
        is_reviewed=lambda branch, d: REVIEWED.get(branch),
    )
    values.update(overrides)
    return GuardContext(**values)


def bash(command):
    return ("Bash", {"command": command})


def pwsh(command):
    return ("PowerShell", {"command": command})


def write(path, tool="Write"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return (tool, {key: str(path)})


HEREDOC_MERGE = (
    "gh api graphql --input - <<'EOF'\n"
    '{"query": "mutation { mergePullRequest(input: {pullRequestId: \\"x\\"}) { id } }"}\n'
    "EOF"
)

# (description, tool call, substring expected in the reason)
BLOCK = [
    # --- gh pr merge, in every shape -------------------------------------------------
    ("gh pr merge", bash("gh pr merge 5"), "human merges"),
    ("flags before number", bash("gh pr merge --squash --delete-branch 5"), "gh pr merge"),
    ("flags after number", bash("gh pr merge 5 --auto --merge"), "gh pr merge"),
    ("repo flag between", bash("gh pr --repo o/r merge 5"), "gh pr merge"),
    ("-R before group", bash("gh -R o/r pr merge 5"), "gh pr merge"),
    ("env-var prefix", bash("GH_TOKEN=abc gh pr merge 5"), "gh pr merge"),
    ("env command", bash("env GH_DEBUG=1 GH_PAGER= gh pr merge 5"), "gh pr merge"),
    ("chained &&", bash("cd /tmp && gh pr merge 5"), "gh pr merge"),
    ("chained ;", bash("echo hi; gh pr merge 5"), "gh pr merge"),
    ("chained ||", bash("false || gh pr merge 5"), "gh pr merge"),
    ("newline", bash("git status\ngh pr merge 5"), "gh pr merge"),
    ("pipe to xargs", bash("gh pr list -q '.[].number' | xargs -n1 gh pr merge"), "gh pr merge"),
    ("bash -c", bash('bash -c "gh pr merge 5"'), "gh pr merge"),
    ("bash -lc single-quoted", bash("bash -lc 'gh pr merge 5'"), "gh pr merge"),
    ("sh -c chained", bash('sh -c "echo x && gh pr merge 5"'), "gh pr merge"),
    ("eval", bash('eval "gh pr merge 5"'), "gh pr merge"),
    ("subshell", bash("(cd .. && gh pr merge 5)"), "gh pr merge"),
    ("command substitution", bash('echo "$(gh pr merge 5)"'), "gh pr merge"),
    ("backticks", bash("echo `gh pr merge 5`"), "gh pr merge"),
    ("windows exe path", bash('"C:\\Program Files\\GitHub CLI\\gh.exe" pr merge 5'),
     "gh pr merge"),
    ("unix exe path", bash("/usr/bin/gh pr merge 5"), "gh pr merge"),
    ("wrapper command", bash("command gh pr merge 5"), "gh pr merge"),
    ("timeout wrapper", bash("timeout 30 gh pr merge 5"), "gh pr merge"),
    ("dynamic executable", bash("$(echo gh) pr merge 5"), "computed at run time"),
    ("variable executable", bash("$GH pr merge 5"), "computed at run time"),
    # --- REST / GraphQL merge ---------------------------------------------------------
    ("REST merge PUT", bash("gh api repos/o/r/pulls/5/merge -X PUT"), "REST API"),
    ("REST merge leading slash", bash("gh api -X PUT /repos/o/r/pulls/5/merge"), "REST API"),
    ("REST merges endpoint", bash("gh api repos/o/r/merges -f base=main -f head=x"),
     "REST API"),
    ("GraphQL mergePullRequest",
     bash("gh api graphql -f query='mutation { mergePullRequest(input: {}) { x } }'"),
     "GraphQL merge"),
    ("GraphQL enablePullRequestAutoMerge",
     bash("gh api graphql -F query='mutation{enablePullRequestAutoMerge(input:{}){x}}'"),
     "GraphQL merge"),
    ("GraphQL mergeBranch", bash("gh api graphql -f query='mutation{mergeBranch(input:{}){x}}'"),
     "GraphQL merge"),
    ("GraphQL via heredoc", bash(HEREDOC_MERGE), "GraphQL merge"),
    ("GraphQL input file", bash("gh api graphql --input query.json"), "cannot be inspected"),
    ("curl REST merge", bash("curl -X PUT -H 'Authorization: token x' "
                             "https://api.github.com/repos/o/r/pulls/5/merge"), "REST API"),
    ("python subprocess merge",
     bash("python -c \"import subprocess; subprocess.run(['gh','pr','merge','5'])\""),
     "gh pr merge"),
    ("python stdin script",
     bash("python - <<'EOF'\nimport os\nos.system('gh pr merge 5')\nEOF"), "gh pr merge"),
    # --- PowerShell -------------------------------------------------------------------
    ("pwsh gh pr merge", pwsh("gh pr merge 5"), "gh pr merge"),
    ("pwsh call operator", pwsh('& "C:\\Program Files\\GitHub CLI\\gh.exe" pr merge 5'),
     "gh pr merge"),
    ("pwsh chained ;", pwsh("git status; gh pr merge 5"), "gh pr merge"),
    ("pwsh -Command", pwsh('pwsh -NoProfile -Command "gh pr merge 5"'), "gh pr merge"),
    ("pwsh Start-Process", pwsh("Start-Process gh -ArgumentList 'pr merge 5' -Wait"),
     "gh pr merge"),
    ("pwsh Invoke-Expression", pwsh("Invoke-Expression 'gh pr merge 5'"), "gh pr merge"),
    ("pwsh script block", pwsh("1..3 | ForEach-Object { gh pr merge $_ }"), "gh pr merge"),
    ("pwsh encoded command", pwsh("powershell -EncodedCommand ZQBjAGgAbwA="), "encoded"),
    ("cmd /c", bash('cmd /c "gh pr merge 5"'), "gh pr merge"),
    # --- git push to the default branch ----------------------------------------------
    ("push main", bash("git push origin main"), "default branch"),
    ("push HEAD:main", bash("git push origin HEAD:main"), "default branch"),
    ("push full ref", bash("git push origin HEAD:refs/heads/main"), "default branch"),
    ("forced refspec to main", bash("git push origin +feature:main"), "default branch"),
    ("double-quoted refspec", bash('git push origin "HEAD:main"'), "default branch"),
    ("single-quoted refspec", bash("git push origin 'refs/heads/main'"), "default branch"),
    ("-u main", bash("git push -u origin main"), "default branch"),
    ("master", bash("git push origin master"), "default branch"),
    ("case variant", bash("git push origin feature:MAIN"), "default branch"),
    ("git -C elsewhere", bash(f'git -C "{OUTSIDE}" push origin main'), "default branch"),
    ("plain push on main", bash(f'cd "{OUTSIDE}" && git push'), "default branch"),
    ("push HEAD on main", bash(f'git -C "{OUTSIDE}" push origin HEAD'), "default branch"),
    ("delete main :refspec", bash("git push origin :main"), "delete the default branch"),
    ("delete main flag", bash("git push origin --delete main"), "delete the default branch"),
    ("mirror", bash("git push --mirror origin"), "--mirror"),
    ("all", bash("git push --all origin"), "--all"),
    ("wildcard refspec", bash("git push origin 'refs/heads/*:refs/heads/*'"), "wildcard"),
    ("configured default branch", bash("git push origin trunk"), "default branch"),
    ("pwsh push main", pwsh("git push origin main"), "default branch"),
    ("bash -c push main", bash("bash -c 'git push origin HEAD:main'"), "default branch"),
    ("git -c alias", bash("git -c alias.p=push p origin main"), "aliases"),
    ("git config alias", bash('git config alias.ship "push origin main"'), "alias"),
    ("git config push refspec", bash("git config remote.origin.push HEAD:main"), "redirect"),
    ("send-pack", bash("git send-pack origin HEAD:main"), "send-pack"),
    ("python push main",
     bash("python -c \"import subprocess; subprocess.run(['git','push','origin','main'])\""),
     "default branch"),
    # --- force-push to a reviewed branch ---------------------------------------------
    ("--force reviewed", bash("git push --force origin story/12-add-due-date"), "under review"),
    ("-f reviewed", bash("git push -f origin story/12-add-due-date"), "under review"),
    ("--force-with-lease reviewed",
     bash("git push --force-with-lease origin story/12-add-due-date"), "under review"),
    ("+refspec reviewed", bash("git push origin +story/12-add-due-date"), "under review"),
    ("combined -fu reviewed", bash("git push -fu origin story/12-add-due-date"), "under review"),
    ("force current branch", bash("git push --force"), "under review"),
    ("force unknown review state", bash("git push --force origin story/99-unknown"),
     "could not confirm"),
    # --- comments, reviews, settings -------------------------------------------------
    ("gh pr comment", bash("gh pr comment 5 --body hi"), "factory.py comment"),
    ("gh issue comment", bash("gh issue comment 3 -b hi"), "factory.py comment"),
    ("gh pr review", bash("gh pr review 5 --approve"), "gh pr review"),
    ("REST comment", bash("gh api repos/o/r/issues/5/comments -f body=hi"),
     "factory.py comment"),
    ("REST comment edit", bash("gh api -X PATCH repos/o/r/issues/comments/99 -f body=x"),
     "factory.py comment"),
    ("REST review", bash("gh api repos/o/r/pulls/5/reviews -f event=APPROVE"), "human's"),
    ("gh repo edit", bash("gh repo edit --default-branch trunk"), "rule S5"),
    ("gh secret", bash("gh secret set TOKEN --body x"), "rule S5"),
    ("protection API", bash("gh api -X PUT repos/o/r/branches/main/protection --input p.json"),
     "branch protection"),
    ("repo settings API", bash("gh api repos/o/r -X PATCH -f default_branch=x"),
     "repository settings"),
    ("DELETE API", bash("gh api -X DELETE repos/o/r/git/refs/heads/x"), "DELETE"),
    ("ref move API", bash("gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=abc"),
     "push checks"),
    ("gh alias", bash("gh alias set mm 'pr merge'"), "alias"),
    # --- file writes ------------------------------------------------------------------
    ("Write into factory", write(FACTORY / "scripts" / "x.py"), "read-only"),
    ("Edit factory settings", write(FACTORY / ".claude" / "settings.json", "Edit"),
     "read-only"),
    ("MultiEdit factory rules", write(FACTORY / "stations" / "_rules.md", "MultiEdit"),
     "read-only"),
    ("Write outside", write(OUTSIDE / "x.txt"), "only inside the target"),
    ("relative path escaping target", write("../factory/README.md"), "read-only"),
    ("NotebookEdit outside", write(OUTSIDE / "n.ipynb", "NotebookEdit"), "only inside"),
    ("bash redirect into factory", bash(f'echo x > "{FACTORY / "README.md"}"'), "read-only"),
    ("bash append outside", bash(f'echo x >> "{OUTSIDE / "log.txt"}"'), "only inside"),
    ("tee outside", bash(f'echo x | tee "{OUTSIDE / "t.txt"}"'), "only inside"),
    ("pwsh Set-Content outside",
     pwsh(f'Set-Content -Path "{OUTSIDE / "x.txt"}" -Value 1'), "only inside"),
    ("pwsh redirect outside", pwsh(f'"x" > "{OUTSIDE / "x.txt"}"'), "only inside"),
    ("unexpanded variable path", bash('echo x > "$NO_SUCH_FACTORY_VAR_1/f"'),
     "cannot tell where"),
]

ALLOW = [
    ("git status", bash("git status")),
    ("push story branch", bash("git push -u origin story/12-add-due-date")),
    ("push HEAD:story", bash("git push origin HEAD:story/12-add-due-date")),
    ("plain push on story branch", bash("git push")),
    ("git -C target push", bash(f'git -C "{TARGET}" push -u origin story/12-add-due-date')),
    ("force before review", bash("git push --force-with-lease origin story/13-fresh")),
    ("push tag", bash("git push origin refs/tags/v1.0")),
    ("dry run to main", bash("git push --dry-run origin main")),
    ("local merge", bash("git merge --no-ff origin/main")),
    ("commit mentioning merge",
     bash('git commit -m "Refuse mergePullRequest and gh pr merge"')),
    ("git log grep", bash("git log --grep=merge --oneline")),
    ("gh pr create with heredoc body",
     bash("gh pr create --title 'Add merge sort' --body-file - <<'EOF'\n"
          "Never run gh pr merge; mergePullRequest is blocked.\nEOF")),
    ("gh pr view merged state", bash("gh pr view 5 --json mergedAt,state,mergeable")),
    ("gh pr list search", bash("gh pr list --search 'is:merged merge'")),
    ("gh issue create", bash("gh issue create --title 'Fix merge bug' --body x")),
    ("gh api GET pull", bash("gh api repos/o/r/pulls/5")),
    ("gh api GET comments", bash("gh api repos/o/r/issues/5/comments --paginate")),
    ("gh api GraphQL query", bash("gh api graphql -f query='query { viewer { login } }'")),
    ("factory comment with heredoc",
     bash("python scripts/factory.py comment --issue 5 --kind reply --body-file - "
          "<<'EOF'\nI did not run gh pr merge.\nEOF")),
    ("python module", bash("python -m unittest 2>&1 | tail -3")),
    ("ruff and tests", bash("python -m ruff check && python -m unittest")),
    ("devnull redirects", bash("echo x > /dev/null 2>&1; ls 2>/dev/null")),
    ("echo text", bash('echo "gh pr merge is forbidden"')),
    ("curl GET", bash("curl -s https://api.github.com/repos/o/r")),
    ("bash -c harmless", bash('bash -c "git status && git log --oneline -1"')),
    ("heredoc into target file",
     bash(f"cat > \"{TARGET / 'notes.md'}\" <<'EOF'\nhello\nEOF")),
    ("redirect into scratch", bash(f'echo x > "{SCRATCH / "out.txt"}"')),
    ("pwsh tests", pwsh("python -m unittest 2>&1 | Select-Object -Last 3")),
    ("pwsh redirect to null", pwsh("git status > $null")),
    ("Write in target", write(TARGET / "src" / "app.py")),
    ("Edit in target", write(TARGET / "README.md", "Edit")),
    ("relative write in target", write("src/new.py")),
    ("Write in scratch", write(SCRATCH / "notes.md")),
    ("Write factory-local", write(FACTORY / ".factory-local" / "target.json")),
    ("Write memory", write(MEMORY / "proj" / "memory" / "note.md")),
    ("Read tool", ("Read", {"file_path": str(OUTSIDE / "x")})),
    ("Grep tool", ("Grep", {"pattern": "gh pr merge"})),
]

# With no active target (developing the factory itself).
DEV_BLOCK = [
    ("dev: write outside", write(OUTSIDE / "x.txt"), "no active target"),
    ("dev: push main", bash("git push origin main"), "default branch"),
    ("dev: merge", bash("gh pr merge 1"), "gh pr merge"),
]
DEV_ALLOW = [
    ("dev: write factory", write(FACTORY / "scripts" / "factory" / "x.py")),
    ("dev: push task branch", bash("git push -q -u origin task/T1.6-guard 2>&1 | grep -v x")),
    ("dev: plain push on task branch", bash("git push")),
]


class GuardTableTest(unittest.TestCase):
    def check(self, cases, context, expect_allowed):
        for case in cases:
            name, (tool, tool_input) = case[0], case[1]
            with self.subTest(name):
                decision = decide(tool, tool_input, context)
                self.assertEqual(decision.allowed, expect_allowed,
                                 f"{name}: {tool_input} -> {decision.reason!r}")
                if not expect_allowed and len(case) > 2:
                    self.assertIn(case[2], decision.reason)

    def test_table_sizes(self):
        self.assertGreaterEqual(len(BLOCK) + len(DEV_BLOCK), 40)
        self.assertGreaterEqual(len(ALLOW) + len(DEV_ALLOW), 20)

    def test_blocked_with_target(self):
        self.check(BLOCK, ctx(default_branch="trunk"), expect_allowed=False)

    def test_allowed_with_target(self):
        self.check(ALLOW, ctx(), expect_allowed=True)

    def test_dev_mode(self):
        self.check(DEV_BLOCK, ctx(target=False), expect_allowed=False)
        self.check(DEV_ALLOW, ctx(target=False), expect_allowed=True)

    def test_unknown_current_branch_blocks_plain_push(self):
        context = ctx(current_branch=lambda d: None)
        decision = decide(*bash("git push"), context)
        self.assertFalse(decision.allowed)
        self.assertIn("could not determine", decision.reason)

    def test_reasons_cite_a_rule(self):
        for name, (tool, tool_input), _ in BLOCK:
            with self.subTest(name):
                reason = decide(tool, tool_input, ctx(default_branch="trunk")).reason
                self.assertTrue(reason)

    def test_deep_nesting_is_refused_not_crashed(self):
        command = "gh pr view 1"
        for _ in range(12):
            command = f"bash -c {json.dumps(command)}"
        self.assertFalse(decide(*bash(command), ctx()).allowed)

    def test_malformed_inputs_do_not_crash(self):
        for command in ('echo "unterminated', "echo 'x", "$(", "`", "cat <<EOF\nno end",
                        "a && && b", "|||", "git push 'origin", ">", "&>"):
            with self.subTest(command=command):
                decide(*bash(command), ctx())
                decide(*pwsh(command), ctx())


class HookAdapterTest(unittest.TestCase):
    def run_hook(self, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        with mock.patch.object(guard_hook.target_mod, "FACTORY_ROOT", FACTORY):
            return guard_hook.run(raw)

    def test_block_exits_2_with_reason(self):
        code, message = self.run_hook({"tool_name": "Bash", "cwd": str(ROOT),
                                       "tool_input": {"command": "gh pr merge 5"}})
        self.assertEqual(code, 2)
        self.assertIn("Blocked by the factory guard", message)

    def test_allow_exits_0_silently(self):
        code, message = self.run_hook({"tool_name": "Bash", "cwd": str(ROOT),
                                       "tool_input": {"command": "git status"}})
        self.assertEqual((code, message), (0, ""))

    def test_other_tools_pass_through(self):
        self.assertEqual(self.run_hook({"tool_name": "Read", "tool_input": {}})[0], 0)

    def test_bad_input_fails_closed(self):
        self.assertEqual(self.run_hook(b"not json")[0], 2)

    def test_guard_bug_fails_closed(self):
        with mock.patch.object(guard_hook, "decide", side_effect=RuntimeError("boom")):
            code, message = self.run_hook({"tool_name": "Bash", "tool_input":
                                           {"command": "ls"}})
        self.assertEqual(code, 2)
        self.assertIn("boom", message)


def hook_shell() -> str | None:
    """The bash Claude Code runs hooks with. On Windows that is Git Bash, not WSL's
    System32\\bash.exe (which `shutil.which("bash")` may find first)."""
    if os.name != "nt":
        return shutil.which("bash")
    configured = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if configured and Path(configured).is_file():
        return configured
    git = shutil.which("git")
    if git:  # e.g. ...\Git\cmd\git.exe or ...\Git\mingw64\bin\git.exe
        for parent in Path(git).parents:
            candidate = parent / "bin" / "bash.exe"
            if candidate.is_file() and (parent / "usr").is_dir():
                return str(candidate)
    return None


class SettingsTest(unittest.TestCase):
    SETTINGS = REPO_ROOT / ".claude" / "settings.json"

    def load(self):
        return json.loads(self.SETTINGS.read_text(encoding="utf-8"))

    def hook(self):
        entries = self.load()["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 1)
        return entries[0]

    def test_hook_covers_shell_and_write_tools(self):
        matcher = self.hook()["matcher"].split("|")
        for tool in ("Bash", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit"):
            self.assertIn(tool, matcher)

    def test_hook_points_at_the_guard(self):
        (handler,) = self.hook()["hooks"]
        self.assertEqual(handler["type"], "command")
        self.assertEqual(handler["command"],
                         'python "$CLAUDE_PROJECT_DIR/scripts/factory.py" guard')

    def test_permissions_deny_merges_and_direct_comments(self):
        deny = self.load()["permissions"]["deny"]
        for rule in ("Bash(gh pr merge:*)", "Bash(gh pr review:*)", "Bash(gh pr comment:*)",
                     "Bash(gh issue comment:*)", "Bash(gh repo edit:*)",
                     "Bash(gh repo delete:*)", "Bash(gh secret:*)", "Bash(git push --force:*)",
                     "Bash(git push origin main)", "Bash(git push origin HEAD:main)"):
            self.assertIn(rule, deny)
        allow = self.load()["permissions"]["allow"]
        self.assertIn("Bash(python scripts/factory.py:*)", allow)
        self.assertFalse([rule for rule in allow if "merge" in rule])

    @unittest.skipUnless(hook_shell(), "Git Bash / bash is needed to run the hook command")
    def test_hook_command_runs_and_blocks(self):
        """Run the exact command string from settings.json, the way Claude Code does."""
        (handler,) = self.hook()["hooks"]
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)}
        cases = [({"command": "gh pr merge 5"}, 2), ({"command": "git status"}, 0)]
        for tool_input, expected in cases:
            with self.subTest(tool_input=tool_input):
                payload = json.dumps({"tool_name": "Bash", "tool_input": tool_input,
                                      "cwd": str(REPO_ROOT), "hook_event_name": "PreToolUse"})
                result = subprocess.run([hook_shell(), "-c", handler["command"]], input=payload,
                                        capture_output=True, text=True, env=env, timeout=60)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 2:
                    self.assertIn("Blocked by the factory guard", result.stderr)


if __name__ == "__main__":
    unittest.main()
