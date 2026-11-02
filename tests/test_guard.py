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
    ("newline", bash("git log -1\ngh pr merge 5"), "gh pr merge"),
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
    ("pwsh chained ;", pwsh("git log -1; gh pr merge 5"), "gh pr merge"),
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
    ("git -c alias", bash("git -c alias.p=push p origin main"), "alias"),
    ("git config alias", bash('git config alias.ship "push origin main"'), "alias"),
    ("git config push refspec", bash("git config remote.origin.push HEAD:main"), "redirect"),
    ("send-pack", bash("git send-pack origin HEAD:main"), "send-pack"),
    # --- E1: git config and flags that make git run a program ------------------------
    ("git -c hooksPath", bash('git -C /work/app -c core.hooksPath=/tmp/h status'), "program"),
    ("git -c sshCommand", bash('git -c core.sshCommand=evil fetch'), "program"),
    ("git -c filter", bash('git -c filter.x.clean=evil status'), "program"),
    ("git config set hooksPath", bash("git -C /work/app config core.hooksPath .hooks"), "program"),
    ("git config sshCommand", bash("git config core.sshCommand evil"), "program"),
    ("git config credential helper",
     bash("git config credential.helper '!evil'"), "program"),
    ("git config-env", bash("git --config-env=core.sshCommand=EV fetch"), "program"),
    ("git exec-path", bash("git --exec-path=/tmp fetch"), "exec-path"),
    ("git hook run", bash("git -C /work/app hook run pre-commit"), "hook"),
    ("git clone template", bash("git clone --template=/tmp/t url dest"), "template"),
    # --- D-4: git program variables ---------------------------------------------------
    ("prefix GIT_SSH_COMMAND", bash("GIT_SSH_COMMAND=evil git fetch"), "git finds programs"),
    ("export GIT_SSH_COMMAND", bash("export GIT_SSH_COMMAND=evil"), "git finds programs"),
    ("env GIT_SSH_COMMAND", bash("env GIT_SSH_COMMAND=evil git fetch"), "git finds programs"),
    ("setx GIT_EXEC_PATH", pwsh("setx GIT_EXEC_PATH C:\\evil"), "git finds programs"),
    ("pwsh env GIT_ASKPASS", pwsh('$env:GIT_ASKPASS = "evil"'), "git finds programs"),
    # --- T1 / D-10: the active target is human-only -----------------------------------
    ("target set", bash("python scripts/factory.py target set /work/app"), "active target"),
    ("target set relative", bash("python ./scripts/factory.py target set ../x"), "active target"),
    ("target set direct", bash("./scripts/factory.py target set /x"), "active target"),
    ("redirect into factory-local",
     bash(f'echo x > "{FACTORY / ".factory-local" / "target.json"}"'), ".factory-local"),
    ("cp into factory-local",
     bash(f'cp evil.json "{FACTORY / ".factory-local" / "target.json"}"'), ".factory-local"),
    ("Set-Content factory-local",
     pwsh(f'Set-Content "{FACTORY / ".factory-local" / "x"}" -Value y'), ".factory-local"),
    ("sc alias factory-local",
     pwsh(f'sc "{FACTORY / ".factory-local" / "x"}" y'), ".factory-local"),
    # --- E1 / D-11: protected paths ---------------------------------------------------
    ("cp into target .git",
     bash(f'cp evil "{TARGET / ".git" / "hooks" / "pre-commit"}"'), ".git/"),
    ("rm target .git", bash(f'rm -rf "{TARGET / ".git" / "hooks"}"'), ".git/"),
    ("cp into factory scripts",
     bash(f'cp evil "{FACTORY / "scripts" / "factory" / "guard.py"}"'), "scripts/"),
    ("Copy-Item into factory .claude",
     pwsh(f'Copy-Item evil "{FACTORY / ".claude" / "settings.local.json"}"'), ".claude/"),
    ("Write target .git hook", write(TARGET / ".git" / "hooks" / "post-checkout"), ".git/"),
    ("Write factory settings.local",
     write(FACTORY / ".claude" / "settings.local.json"), ".claude/"),
    # --- F1: dd of= write target (if= reads stay allowed, tested in ALLOW) ------------
    ("dd of= factory-local",
     bash(f'dd of="{FACTORY / ".factory-local" / "target.json"}" if=evil'), ".factory-local"),
    ("dd of= target .git",
     bash(f'dd of="{TARGET / ".git" / "hooks" / "pre-commit"}"'), ".git/"),
    ("dd of= factory scripts",
     bash(f'dd of="{FACTORY / "scripts" / "factory" / "guard.py"}"'), "scripts/"),
    # --- F2: bash read-write redirects open the target for writing --------------------
    ("1<> factory-local",
     bash(f'echo x 1<> "{FACTORY / ".factory-local" / "target.json"}"'), ".factory-local"),
    ("0<> target .git",
     bash(f'cat 0<> "{TARGET / ".git" / "config"}"'), ".git/"),
    ("N<> factory scripts",
     bash(f'echo x 9<> "{FACTORY / "scripts" / "factory" / "guard.py"}"'), "scripts/"),
    # --- F3: PowerShell .NET file-writing calls to a protected path -------------------
    ("WriteAllText factory-local",
     pwsh(f'[IO.File]::WriteAllText("{FACTORY / ".factory-local" / "target.json"}","x")'),
     ".factory-local"),
    ("WriteAllBytes target .git",
     pwsh(f'[System.IO.File]::WriteAllBytes("{TARGET / ".git" / "hooks" / "pre-commit"}",$b)'),
     ".git/"),
    ("Create factory .claude",
     pwsh(f'[IO.File]::Create("{FACTORY / ".claude" / "settings.local.json"}")'), ".claude/"),
    ("OpenWrite factory scripts",
     pwsh(f'[IO.File]::OpenWrite("{FACTORY / "scripts" / "factory" / "guard.py"}")'), "scripts/"),
    # --- D-9: inline code touching protected state ------------------------------------
    ("python set_target",
     bash('python -c "from factory.target import set_target; set_target(\'/x\')"'), "D-9"),
    ("python write factory-local",
     bash("python -c \"open('.factory-local/target.json','w')\""), "D-9"),
    ("Write factory-local", write(FACTORY / ".factory-local" / "target.json"), ".factory-local"),
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
    # --- C2: raw hook-running git must use the wrapper with a target active ------------
    ("raw status via wrapper", bash("git status"), "wrapper"),
    ("raw commit via wrapper", bash('git commit -m "x"'), "wrapper"),
    ("raw add via wrapper", bash("git add ."), "wrapper"),
    ("raw push story via wrapper", bash("git push -u origin story/12-add-due-date"), "wrapper"),
    ("raw switch via wrapper", bash("git switch main"), "wrapper"),
    ("raw fetch via wrapper", bash("git fetch origin"), "wrapper"),
    ("raw pull via wrapper", bash("git pull --ff-only"), "wrapper"),
    ("raw branch via wrapper", bash("git branch --show-current"), "wrapper"),
    ("raw ls-files via wrapper", bash("git ls-files"), "wrapper"),
    ("raw git -C target push via wrapper",
     bash(f'git -C "{TARGET}" push -u origin story/12-add-due-date'), "wrapper"),
    ("raw working-tree diff", bash("git diff"), "commit range"),
    ("raw diff range without flags", bash("git diff origin/main...HEAD"), "commit range"),
    ("raw diff cached", bash("git diff --cached"), "commit range"),
    ("raw hash-object -w", bash("git hash-object -w f.txt"), "object store"),
    ("raw merge refused", bash("git merge --no-ff origin/main"), "not an allowed raw"),
    ("raw rebase refused", bash("git rebase origin/main"), "not an allowed raw"),
    ("raw reset refused", bash("git reset --hard origin/main"), "not an allowed raw"),
    # --- C2: the wrapper gets the same push/merge checks as raw git --------------------
    ("wrapper push to main", bash("python scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper force to reviewed",
     bash("python scripts/factory.py git push --force origin story/12-add-due-date"),
     "under review"),
    ("wrapper -c program key",
     bash("python scripts/factory.py git -c core.sshCommand=evil fetch"), "program"),
    # --- C2: every supported invocation form of the wrapper is recognised -------------
    ("wrapper via py", bash("py scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper via python3", bash("python3 scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper via python -u", bash("python -u scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper via py -3", bash("py -3 scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper via absolute path",
     bash(f'python "{FACTORY / "scripts" / "factory.py"}" git push origin HEAD:main'),
     "default branch"),
    ("wrapper direct exec", bash("./scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper env prefix", bash("FOO=1 python scripts/factory.py git push origin HEAD:main"),
     "default branch"),
    ("wrapper inside bash -c",
     bash('bash -c "python scripts/factory.py git push origin HEAD:main"'), "default branch"),
    ("wrapper in pwsh with call operator",
     pwsh("& python scripts/factory.py git push origin HEAD:main"), "default branch"),
    ("wrapper with -- separator",
     bash("python scripts/factory.py git -- push origin HEAD:main"), "default branch"),
    # B1: interpreter options with a separate value must not hide factory.py.
    ("wrapper via python -X utf8",
     bash("python -X utf8 scripts/factory.py git push origin HEAD:main"), "default branch"),
    ("wrapper via python -W ignore",
     bash("python -W ignore scripts/factory.py git push origin HEAD:main"), "default branch"),
    ("target set via python -X utf8",
     bash("python -X utf8 scripts/factory.py target set /work/app"), "active target"),
    ("target set via python -W ignore",
     bash("python -W ignore scripts/factory.py target set /work/app"), "active target"),
    # B3: a versioned or windowed interpreter name is still that interpreter.
    ("wrapper via python3.12",
     bash("python3.12 scripts/factory.py git push origin HEAD:main"), "default branch"),
    ("target set via python3.11",
     bash("python3.11 scripts/factory.py target set /work/app"), "active target"),
    ("target set via pythonw", bash("pythonw scripts/factory.py target set /work/app"),
     "active target"),
    ("python3.12 -c writes factory-local",
     bash("python3.12 -c \"open('.factory-local/target.json','w')\""), "D-9"),
    ("python3.12 -c merge",
     bash("python3.12 -c \"import subprocess; subprocess.run(['gh','pr','merge','5'])\""),
     "gh pr merge"),
    # B2: with --repo every positional is a refspec.
    ("wrapper push --repo= to main",
     bash("python scripts/factory.py git push --repo=origin HEAD:main"), "default branch"),
    ("wrapper push --repo to main",
     bash("python scripts/factory.py git push --repo origin HEAD:main"), "default branch"),
    # Refspec spellings through the wrapper.
    ("wrapper +feature:main", bash("python scripts/factory.py git push origin +feature:main"),
     "default branch"),
    ("wrapper delete main", bash("python scripts/factory.py git push origin :main"),
     "delete the default branch"),
    ("wrapper refs/heads/main",
     bash("python scripts/factory.py git push origin HEAD:refs/heads/main"), "default branch"),
    ("wrapper --mirror", bash("python scripts/factory.py git push --mirror origin"), "mirror"),
    ("wrapper -C elsewhere to main",
     bash("python scripts/factory.py git -C /x push origin HEAD:main"), "default branch"),
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
    # Hook-running git goes through the wrapper (C2); read-only git stays raw.
    ("wrapper status", bash("python scripts/factory.py git status")),
    ("wrapper push story branch",
     bash("python scripts/factory.py git push -u origin story/12-add-due-date")),
    ("wrapper push HEAD:story",
     bash("python scripts/factory.py git push origin HEAD:story/12-add-due-date")),
    ("wrapper plain push", bash("python scripts/factory.py git push")),
    ("wrapper force before review",
     bash("python scripts/factory.py git push --force-with-lease origin story/13-fresh")),
    ("wrapper push tag", bash("python scripts/factory.py git push origin refs/tags/v1.0")),
    ("wrapper dry run to main", bash("python scripts/factory.py git push --dry-run origin main")),
    ("wrapper commit mentioning merge",
     bash('python scripts/factory.py git commit -m "Refuse mergePullRequest and gh pr merge"')),
    ("wrapper add", bash("python scripts/factory.py git add .factory/log.md")),
    ("wrapper switch", bash("python scripts/factory.py git switch -c story/12-add-due-date")),
    ("wrapper branch show-current", bash("python scripts/factory.py git branch --show-current")),
    ("raw read-only log grep", bash("git log --grep=merge --oneline")),
    ("raw read-only rev-parse", bash("git rev-parse HEAD")),
    ("raw read-only ls-remote", bash("git ls-remote --heads origin story/12-add-due-date")),
    ("raw diff with range and flags",
     bash("git diff --no-ext-diff --no-textconv origin/main...HEAD")),
    ("raw hash-object no -w", bash("git hash-object f.txt")),
    ("python3.12 target show", bash("python3.12 scripts/factory.py target show")),
    ("python3.12 -m pytest", bash("python3.12 -m pytest -q")),
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
    ("bash -c harmless", bash('bash -c "git rev-parse HEAD && git log --oneline -1"')),
    ("heredoc into target file",
     bash(f"cat > \"{TARGET / 'notes.md'}\" <<'EOF'\nhello\nEOF")),
    ("redirect into scratch", bash(f'echo x > "{SCRATCH / "out.txt"}"')),
    ("pwsh tests", pwsh("python -m unittest 2>&1 | Select-Object -Last 3")),
    ("pwsh redirect to null", pwsh("python scripts/factory.py git status > $null")),
    ("Write in target", write(TARGET / "src" / "app.py")),
    ("Edit in target", write(TARGET / "README.md", "Edit")),
    ("relative write in target", write("src/new.py")),
    ("Write in scratch", write(SCRATCH / "notes.md")),
    ("Write memory", write(MEMORY / "proj" / "memory" / "note.md")),
    ("read .git config", bash(f'cat "{TARGET / ".git" / "config"}"')),
    ("read factory script", bash(f'rg pattern "{FACTORY / "scripts" / "factory" / "guard.py"}"')),
    ("raw read-only -C target", bash("git -C /work/app rev-parse --short HEAD")),
    ("factory.py target show", bash("python scripts/factory.py target show")),
    ("factory.py target check", bash("python scripts/factory.py target check /work/app")),
    ("env CI only", bash("CI=1 npm test")),
    ("pwsh $env NO_COLOR", pwsh('$env:NO_COLOR = "1"; npm test')),
    # F1/F2/F3 must not block legitimate reads of a protected path.
    ("dd if= reads target .git",
     bash(f'dd if="{TARGET / ".git" / "config"}" of="{SCRATCH / "x"}"')),
    ("input redirect from .git", bash(f'cat < "{TARGET / ".git" / "config"}"')),
    (".NET OpenRead target .git",
     pwsh(f'[IO.File]::OpenRead("{TARGET / ".git" / "config"}")')),
    (".NET ReadAllText scripts",
     pwsh(f'[IO.File]::ReadAllText("{FACTORY / "scripts" / "factory" / "guard.py"}")')),
    ("Read tool", ("Read", {"file_path": str(OUTSIDE / "x")})),
    ("Grep tool", ("Grep", {"pattern": "gh pr merge"})),
]

# With no active target (developing the factory itself).
DEV_BLOCK = [
    ("dev: write outside", write(OUTSIDE / "x.txt"), "no active target"),
    ("dev: push main", bash("git push origin main"), "default branch"),
    ("dev: merge", bash("gh pr merge 1"), "gh pr merge"),
    # .factory-local and target set are human-only in BOTH modes (D-10, T1).
    ("dev: write factory-local", write(FACTORY / ".factory-local" / "target.json"),
     ".factory-local"),
    ("dev: redirect factory-local",
     bash(f'echo x > "{FACTORY / ".factory-local" / "target.json"}"'), ".factory-local"),
    ("dev: target set", bash("python scripts/factory.py target set /work/app"), "active target"),
    ("dev: target set via -X", bash("python -X utf8 scripts/factory.py target set /x"),
     "active target"),
    # B2 pre-dated C2: raw push with --repo in self-development mode.
    ("dev: raw push --repo= to main", bash("git push --repo=origin HEAD:main"),
     "default branch"),
    ("dev: raw push --repo to main", bash("git push --repo origin HEAD:main"),
     "default branch"),
]
DEV_ALLOW = [
    ("dev: write factory", write(FACTORY / "scripts" / "factory" / "x.py")),
    ("dev: cp into factory scripts (self-dev)",
     bash(f'cp a.py "{FACTORY / "scripts" / "factory" / "x.py"}"')),
    ("dev: write factory .claude (self-dev)", write(FACTORY / ".claude" / "settings.json")),
    ("dev: push task branch", bash("git push -q -u origin task/T1.6-guard 2>&1 | grep -v x")),
    ("dev: plain push on task branch", bash("git push")),
    ("dev: target show", bash("python scripts/factory.py target show")),
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


# PowerShell spellings seen in the M4 demo (T4.5), run from the factory repo with a target
# active, exactly as the model sent them. The guard used to block all three: a statement
# starting with a variable was taken for a command whose name is computed at run time,
# and `Out-File -Encoding utf8 <path>` was taken to write a file called `utf8`.
DEMO_PWSH_ALLOW = [
    ("demo: variable holding the target path",
     pwsh(f'$T="{TARGET}"; python scripts/factory.py git status --porcelain; '
          "python scripts/factory.py closeout --issue 3 --json")),
    ("demo: if ($?)",
     pwsh(f'python scripts/factory.py comment --issue 3 --kind reply --body-file '
          f'"{SCRATCH / "closeout-3.md"}"; if ($?) {{ python scripts/factory.py closeout '
          "--issue 3 --finish }")),
    ("demo: Out-File -Encoding utf8",
     pwsh(f'(Get-Content -Raw -Encoding utf8 "{SCRATCH / "pr-4.md"}").Replace("#PR", "#16")'
          f' | Out-File -Encoding utf8 -NoNewline "{SCRATCH / "pr-4.md"}"')),
]

PWSH_ALLOW = [
    ("pwsh assignment with spaces", pwsh(f'$T = "{TARGET}"; git -C $T log -1')),
    ("pwsh env assignment", pwsh('$env:NO_COLOR = "1"; npm test')),
    ("pwsh $LASTEXITCODE test", pwsh("npm test; if ($LASTEXITCODE -ne 0) { exit 1 }")),
    ("pwsh $? and -and", pwsh("git log -1; if ($? -and $LASTEXITCODE -eq 0) { git log -1 }")),
    ("pwsh assignment from a command", pwsh("$branch = git rev-parse --abbrev-ref HEAD")),
    ("pwsh $null discard", pwsh("$null = python scripts/factory.py git fetch origin; "
                                "python scripts/factory.py git status > $null")),
    ("pwsh known variable in cd", pwsh(f'$T = "{TARGET}"; cd $T; "x" > notes.txt')),
    ("pwsh wrapper push",
     pwsh("python scripts/factory.py git push -u origin story/12-add-due-date")),
    ("Out-File -FilePath and -Encoding",
     pwsh(f'"x" | Out-File -FilePath "{SCRATCH / "a.md"}" -Encoding utf8')),
    ("Out-File abbreviated -Enc", pwsh(f'"x" | Out-File -Enc utf8 "{SCRATCH / "a.md"}"')),
    ("Out-File -Encoding:utf8", pwsh(f'"x" | Out-File -Encoding:utf8 "{SCRATCH / "a.md"}"')),
    ("Set-Content value before path",
     pwsh(f'Set-Content -Encoding utf8 -Value "x" "{TARGET / "f.txt"}"')),
    ("Add-Content -Path first",
     pwsh(f'Add-Content -Path "{TARGET / ".factory" / "log.md"}" -Value "x" -Encoding utf8')),
    ("Tee-Object -Encoding", pwsh(f'"x" | Tee-Object -Encoding utf8 "{SCRATCH / "t.txt"}"')),
    ("bash tee -a", bash(f'echo x | tee -a "{SCRATCH / "t.txt"}"')),
    ("piped into python -c", bash("gh pr list --json number | python -c \"import sys\"")),
    ("piped into python -m", bash("cat x.json | python -m json.tool")),
]

PWSH_BLOCK = [
    # A variable must not hide a merge or a push from the guard.
    ("$null = discards but still runs", pwsh("$null = gh pr merge 5"), "gh pr merge"),
    ("assignment runs its right-hand side", pwsh("$r = gh pr merge 5"), "gh pr merge"),
    ("verb in a variable", pwsh('$v = "merge"; gh pr $v 5'), "gh pr merge"),
    ("branch in a variable", pwsh('$b = "main"; git push origin $b'), "default branch"),
    ("repo dir in a variable", pwsh(f'$D = "{OUTSIDE}"; git -C $D push'), "default branch"),
    ("query in a variable",
     pwsh("$q = 'mutation { mergePullRequest(input: {}) { id } }'; "
          "gh api graphql -f query=$q"), "GraphQL merge"),
    ("endpoint in a variable",
     pwsh('$u = "repos/o/r/pulls/5/merge"; gh api $u -X PUT'), "REST API"),
    ("exe in a variable", pwsh('$c = "gh"; & $c pr merge 5'), "gh pr merge"),
    ("iex of a variable", pwsh('$x = "gh pr merge 5"; Invoke-Expression $x'), "gh pr merge"),
    ("call operator on an unknown variable", pwsh("& $tool pr merge 5"),
     "computed at run time"),
    ("call operator on a computed variable", pwsh("$c = Get-Tool; & $c pr merge 5"),
     "computed at run time"),
    ("iex of an unknown variable", pwsh("Invoke-Expression $script"), "computed at run time"),
    ("pwsh -Command of an unknown variable", pwsh("powershell -Command $script"),
     "computed at run time"),
    ("member call on a variable",
     pwsh("$ExecutionContext.InvokeCommand.InvokeScript('gh pr merge 5')"),
     "computed at run time"),
    ("write to a computed path", pwsh('$p = Get-Path; "x" > $p'), "cannot tell where"),
    # Code piped into something that runs it cannot be inspected.
    ("variable piped into iex", pwsh('$x = "gh pr merge 5"; $x | iex'), "piped into it"),
    ("string piped into iex", pwsh('"gh pr merge 5" | Invoke-Expression'), "piped into it"),
    ("echo piped into bash", bash('echo "gh pr merge 5" | bash'), "piped into it"),
    ("echo piped into python", bash('echo "print(1)" | python'), "piped into it"),
    ("piped into pwsh -Command -", pwsh('"gh pr merge 5" | pwsh -Command -'), "piped into it"),
    ("query piped into gh api",
     pwsh("$q = '{}'; $q | gh api graphql --input -"), "piped into it"),
    # The file is still checked when -Encoding and friends come first.
    ("Out-File -Encoding into the factory",
     pwsh(f'"x" | Out-File -Encoding utf8 -NoNewline "{FACTORY / "stations" / "x.md"}"'),
     "read-only"),
    ("Out-File -Encoding outside", pwsh(f'"x" | Out-File -Encoding utf8 "{OUTSIDE / "x"}"'),
     "only inside"),
    ("Set-Content value first into the factory",
     pwsh(f'Set-Content -Value "x" -Encoding utf8 "{FACTORY / "x.md"}"'), "read-only"),
    ("unknown parameter: every positional checked",
     pwsh(f'"x" | Out-File -Frobnicate y "{OUTSIDE / "x"}"'), "only inside"),
    ("ambiguous prefix: every positional checked",
     pwsh(f'"x" | Out-File -E utf8 "{OUTSIDE / "x"}"'), "only inside"),
    ("Tee-Object alias -Encoding outside",
     pwsh(f'"x" | tee -Encoding utf8 "{OUTSIDE / "t.txt"}"'), "only inside"),
]


class PowerShellGuardTest(unittest.TestCase):
    """PowerShell expressions, assignments and write cmdlets (T4.5 hardening)."""

    check = GuardTableTest.check

    def test_demo_commands_are_allowed(self):
        self.check(DEMO_PWSH_ALLOW, ctx(cwd=FACTORY), expect_allowed=True)

    def test_allowed(self):
        self.check(PWSH_ALLOW, ctx(), expect_allowed=True)

    def test_blocked(self):
        self.check(PWSH_BLOCK, ctx(), expect_allowed=False)

    def test_known_variable_decides_where_a_write_goes(self):
        # `cd $F` follows the literal value: a relative write lands in $F, not in the cwd.
        decision = decide(*pwsh(f'$F = "{FACTORY}"; cd $F; "x" > notes.txt'), ctx())
        self.assertFalse(decision.allowed)
        self.assertIn("read-only", decision.reason)

    def test_variable_expressions_only_at_top_level(self):
        # Inside a nested script the text itself may have been computed.
        self.assertFalse(decide(*pwsh("pwsh -Command '$?'"), ctx()).allowed)
        self.assertTrue(decide(*pwsh("$?"), ctx()).allowed)


# Bash spellings seen in the M2–M4 sessions (T4.5), run from the factory repo with a target
# active, exactly as the model sent them apart from the paths. The guard used to block the
# allowed ones: a variable assigned a literal path earlier in the same command was taken
# for an unknown one.
T, S = TARGET.as_posix(), SCRATCH.as_posix()
DEMO_BASH_ALLOW = [
    ("demo: log line through $T",
     bash(f'T="{T}"; echo "2026-09-30T12:36:50Z S07 001-initial #7 branch story/7-x" >> '
          '"$T/.factory/log.md" && python scripts/factory.py git add .factory/log.md && '
          'python scripts/factory.py git commit -q '
          '-m "chore: start story #7" -m "Factory-Station: S07" && '
          'python scripts/factory.py git push -u origin '
          "story/12-add-due-date 2>&1 | tail -2")),
    ("demo: printf into $T",
     bash(f'T="{T}"; printf \'%s S00 001-initial intake\\n\' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
          '>> "$T/.factory/log.md"; cat "$T/.factory/log.md"; '
          'python scripts/factory.py git status --porcelain')),
    ("demo: scratch dir in $S, chained with &&",
     bash(f"S={S} && mkdir -p $S/oldguard/factory && git show main:scripts/factory/guard.py "
          "> $S/oldguard/factory/guard_old.py")),
    ("demo: $T and $B for the story branch",
     bash(f"T={T}; B=story/12-add-due-date; "
          "python scripts/factory.py git switch -c $B origin/main && echo "
          '"$(date -u +%Y-%m-%dT%H:%M:%SZ) S07 001-initial #2 branch $B" >> $T/.factory/log.md '
          "&& python scripts/factory.py git add .factory/log.md && "
          "python scripts/factory.py git push -u origin $B")),
    ("demo: brace group redirected into $P",
     bash(f"P={S}; {{ cat <<'EOF'\n## Summary\nEOF\ngrep -E '^- \\[' $P/verdict-2.md\n}} "
          "> $P/pr-2.md; grep -c '{{' $P/pr-2.md; gh pr create --title x --body-file $P/pr-2.md")),
]

# Blocked during the sessions, and rightly so.
DEMO_BASH_BLOCK = [
    ("demo: path from $(...)",
     bash('S=$(python -c "import tempfile;print(tempfile.gettempdir())"); echo "$S"\n'
          "cat > \"$S/closeout-6.md\" <<'EOF'\nx\nEOF"), "cannot tell where '$(...)"),
    ("demo: python script quoting a merge mutation",
     bash("python - <<'PYEOF'\nfrom pathlib import Path\nblock = r\"\"\"\n"
          "pwsh(\"$q = 'mutation { mergePullRequest(input: {}) { id } }'; gh api graphql\")\n"
          "\"\"\"\nPath('x').write_text(block)\nPYEOF"), "GraphQL merge"),
    ("demo: python script quoting gh pr merge",
     bash(f'F="{S}/pr-t1.8.md" && python - "$F" <<\'EOF\'\nimport sys\n'
          "text = '`gh pr merge` was blocked by the live guard hook'\nEOF"), "gh pr merge"),
    ("demo: build output into /tmp",
     bash('for c in "npm run build" "npm test"; do echo "### $c"; $c > /tmp/out.txt 2>&1; '
          'e=$?; tail -12 /tmp/out.txt; echo "### $c EXIT=$e"; done'), "only inside"),
]

BASH_VAR_ALLOW = [
    ("bash: branch in a variable",
     bash("B=story/12-add-due-date; python scripts/factory.py git push -u origin $B")),
    ("bash: cd into a known variable", bash(f'T="{T}"; cd "$T" && echo x > notes.txt')),
    ("bash: ${T} braces", bash(f'T="{T}" N=out; echo "${{T}}" > "${{T}}/${{N}}.txt"')),
    ("bash: single-quoted value", bash(f"S='{S}'; echo '$HOME' > \"$S/x\"")),
    ("bash: reassigned to another literal", bash(f'T="{OUTSIDE}"; T="{T}"; echo x > "$T/f"')),
]

# A variable must not hide a merge, a push or a write from the guard.
BASH_VAR_BLOCK = [
    ("bash: branch in a variable", bash("B=main; git push origin $B"), "default branch"),
    ("bash: verb in a variable", bash("V=merge; gh pr $V 5"), "gh pr merge"),
    ("bash: exe in a variable", bash("G=gh; $G pr merge 5"), "gh pr merge"),
    ("bash: write outside", bash(f'D="{OUTSIDE.as_posix()}"; echo x > "$D/x"'), "only inside"),
    ("bash: cd into the factory", bash(f'F="{FACTORY.as_posix()}"; cd $F; echo x > n.txt'),
     "read-only"),
    ("bash: double-quoted bash -c", bash(f'D="{OUTSIDE.as_posix()}"; bash -c "echo x > $D/x"'),
     "only inside"),
    # Anything the guard cannot follow leaves the variable unknown.
    ("bash: appended to", bash(f'T="{T}"; T+=/../elsewhere; echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned in a subshell", bash(f'(T="{T}"); echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned in a group", bash(f'{{ T="{T}"; }}; echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned in a pipeline", bash(f'T="{T}" | true; echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned in the background", bash(f'T="{T}" & echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned after &&", bash(f'false && T="{T}"; echo x > "$T/f"'), "cannot tell"),
    ("bash: assigned after a keyword",
     bash(f'T="{T}"; if true; then T=/elsewhere; fi; echo x > "$T/f"'), "cannot tell"),
    ("bash: export", bash(f'T="{T}"; export T=/elsewhere; echo x > "$T/f"'), "cannot tell"),
    ("bash: read", bash(f'T="{T}"; read T < in.txt; echo x > "$T/f"'), "cannot tell"),
    ("bash: for loop", bash(f'T="{T}"; for T in /e; do echo x > "$T/f"; done'), "cannot tell"),
    ("bash: printf -v", bash(f'T="{T}"; printf -v T /e; echo x > "$T/f"'), "cannot tell"),
    ("bash: computed", bash('T=$(pwd); echo x > "$T/f"'), "cannot tell where '$(...)"),
    ("bash: from an unknown variable", bash('T="$NO_SUCH_FACTORY_VAR_2/x"; echo y > "$T/f"'),
     "cannot tell"),
    ("bash: single quotes keep $T literal", bash(f"T=\"{T}\"; echo x > '$T/f'"),
     "cannot tell"),
]


class BashVariableGuardTest(unittest.TestCase):
    """Bash variables assigned in the same command (T4.5 hardening)."""

    check = GuardTableTest.check

    def test_demo_commands(self):
        self.check(DEMO_BASH_ALLOW, ctx(cwd=FACTORY), expect_allowed=True)
        self.check(DEMO_BASH_BLOCK, ctx(cwd=FACTORY), expect_allowed=False)

    def test_allowed(self):
        self.check(BASH_VAR_ALLOW, ctx(), expect_allowed=True)

    def test_blocked(self):
        self.check(BASH_VAR_BLOCK, ctx(), expect_allowed=False)


# Commands inside bash compound commands. The guard used to take the keyword in front of
# them (`then`, `do`, `!` …) for the command name, so the real command was never checked.
KEYWORD_BLOCK = [
    ("then", bash("if true; then gh pr merge 5; fi"), "gh pr merge"),
    ("for … do", bash("for i in 1; do gh pr merge 5; done"), "gh pr merge"),
    ("while … do", bash("while true; do git push origin main; done"), "default branch"),
    ("until … do", bash("until false; do gh pr merge 5; done"), "gh pr merge"),
    ("if condition", bash("if gh pr merge 5; then :; fi"), "gh pr merge"),
    ("while condition", bash("while gh pr merge 5; do :; done"), "gh pr merge"),
    ("else", bash("if false; then :; else gh pr merge 5; fi"), "gh pr merge"),
    ("elif condition", bash("if false; then :; elif gh pr merge 5; then :; fi"),
     "gh pr merge"),
    ("negation", bash("! gh pr merge 5"), "gh pr merge"),
    ("if !", bash("if ! gh pr merge 5; then :; fi"), "gh pr merge"),
    ("coproc", bash("coproc gh pr merge 5"), "gh pr merge"),
    ("nested if", bash("if true; then if true; then gh pr merge 5; fi; fi"), "gh pr merge"),
    ("multi-line", bash("if true\nthen\n  gh pr merge 5\nfi"), "gh pr merge"),
    ("keyword then env prefix", bash("if true; then GH_TOKEN=x gh pr merge 5; fi"),
     "gh pr merge"),
    ("keyword then wrapper", bash("for i in 1; do timeout 9 gh pr merge 5; done"),
     "gh pr merge"),
    ("inside bash -c", bash("bash -c 'if true; then gh pr merge 5; fi'"), "gh pr merge"),
    ("force push in a loop",
     bash("for b in x; do git push --force origin story/12-add-due-date; done"),
     "under review"),
    ("direct comment after then", bash("if true; then gh pr comment 5 --body x; fi"),
     "factory.py comment"),
    ("GraphQL merge after do",
     bash("for i in 1; do gh api graphql -f query='mutation { mergePullRequest(input: {}) "
          "{ x } }'; done"), "GraphQL merge"),
]

KEYWORD_ALLOW = [
    ("if/else on git", bash("if git rev-parse -q HEAD; then echo a; else echo b; fi")),
    ("for loop", bash('for f in a b; do echo "$f"; done')),
    ("while read", bash('while read line; do echo "$line"; done < in.txt')),
    ("push story branch in if",
     bash("if [ -f x ]; then python scripts/factory.py git push -u origin "
          "story/12-add-due-date; fi")),
    ("negated test", bash("! git log -1 --oneline")),
    ("multi-line loop", bash("for t in unit e2e; do\n  npm run test:$t\ndone")),
]


class KeywordGuardTest(unittest.TestCase):
    """Commands after bash keywords are checked like any other command."""

    check = GuardTableTest.check

    def test_blocked(self):
        self.check(KEYWORD_BLOCK, ctx(), expect_allowed=False)

    def test_allowed(self):
        self.check(KEYWORD_ALLOW, ctx(), expect_allowed=True)


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


class PointerFailClosedTest(unittest.TestCase):
    """D-5 through the whole hook path (``build_context`` → ``target_broken`` → ``decide``):
    only a genuinely absent target pointer means no-target mode. A pointer that exists in
    any unusable form makes the guard fail closed for shell and write tools alike."""

    BROKEN = {
        "corrupt JSON": "{not json",
        "empty file": "",
        "incomplete record": json.dumps({"path": "/somewhere"}),
        "names a missing folder": None,  # filled in setUp with a path that does not exist
        "empty object": "{}",
        "JSON null": "null",
        "JSON list": "[]",
        "JSON string": '"x"',
        "a directory": "<dir>",
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.factory = self.root / "factory"
        self.pointer = self.factory / guard_hook.target_mod.TARGET_FILE
        self.pointer.parent.mkdir(parents=True)

    def place(self, content):
        if content == "<dir>":
            self.pointer.mkdir()
        elif content is not None:
            self.pointer.write_text(content, encoding="utf-8")

    def hook(self, tool, tool_input):
        payload = {"tool_name": tool, "cwd": str(self.factory), "tool_input": tool_input}
        with mock.patch.object(guard_hook.target_mod, "FACTORY_ROOT", self.factory):
            return guard_hook.run(json.dumps(payload).encode("utf-8"))

    def context(self):
        with mock.patch.object(guard_hook.target_mod, "FACTORY_ROOT", self.factory):
            return guard_hook.build_context({"cwd": str(self.factory)})

    def calls(self):
        guard_file = str(self.factory / "scripts" / "factory" / "guard.py")
        return [("Bash", {"command": "git log -1"}),
                ("PowerShell", {"command": "Get-ChildItem"}),
                ("Write", {"file_path": guard_file})]

    def test_every_unusable_pointer_fails_closed(self):
        for label, content in self.BROKEN.items():
            if content is None:
                content = json.dumps({"path": str(self.root / "gone"), "repo": "o/r"})
            with self.subTest(state=label):
                self.place(content)
                try:
                    ctx = self.context()
                    self.assertTrue(ctx.target_broken, label)
                    self.assertIsNone(ctx.target_root)
                    for tool, tool_input in self.calls():
                        code, message = self.hook(tool, tool_input)
                        self.assertEqual(code, 2, f"{label}: {tool} was allowed")
                        self.assertIn("could not be read", message)
                finally:
                    if self.pointer.is_dir():
                        self.pointer.rmdir()
                    elif self.pointer.exists():
                        self.pointer.unlink()

    def test_an_unreadable_pointer_fails_closed(self):
        # Windows cannot reliably make a file unreadable to its owner, so the read error is
        # simulated: any exception while reading the pointer must block, not allow.
        self.place('{"path": "x", "repo": "o/r"}')
        with mock.patch.object(guard_hook.target_mod, "get_target",
                               side_effect=PermissionError("denied")):
            for tool, tool_input in self.calls():
                with self.subTest(tool=tool):
                    self.assertEqual(self.hook(tool, tool_input)[0], 2)

    def test_an_absent_pointer_is_self_development(self):
        ctx = self.context()
        self.assertFalse(ctx.target_broken)
        self.assertIsNone(ctx.target_root)
        for tool, tool_input in self.calls():  # the factory tree is writable with no target
            with self.subTest(tool=tool):
                self.assertEqual(self.hook(tool, tool_input), (0, ""))

    def test_a_valid_pointer_is_target_mode(self):
        app = self.root / "app"
        app.mkdir()
        self.place(json.dumps({"path": str(app), "repo": "o/app"}))
        ctx = self.context()
        self.assertFalse(ctx.target_broken)
        self.assertEqual(ctx.target_root, app)


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
