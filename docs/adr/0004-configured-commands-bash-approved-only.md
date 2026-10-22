# ADR-0004: Configured commands run with Bash, and only approved commands run

| | |
|---|---|
| **Status** | Accepted, implemented in T6.1 |
| **Decided** | 2026-10-08 (`1bcf8818#1503`, 2026-10-08T08:42:57Z) |
| **Recorded** | 2026-10-22 |
| **Scope** | The `build`, `lint`, `typecheck` and `test` commands from the target's `.factory/config.json` that the factory runs itself (`factory.py verify run`) |

## Context

T6.1 added `verify run`, which runs the target's configured commands in factory code so that results come from exit codes, not model text (rule H1). Its first version had two flaws, found in review ([PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36)):
1. It vetted each command with the guard's **bash** rules but ran it with **cmd.exe** on Windows. cmd-only syntax could turn a command the guard allowed into a merge, for example `gh pr mer^ge 5`.
2. It read the commands from the working tree's `.factory/config.json`, which the model can edit on the story branch.

## Decision

1. **The language checked is the language run.** Configured commands run as `[bash, "-c", command]` on every platform.
   - On Windows, `bash` is Git for Windows' own `bin/bash.exe`, found next to `git.exe`. A `bash` on `PATH` is never used, because it can be WSL's.
   - No bash found means nothing runs (fail closed).
   - A command using cmd.exe-only syntax (`^`, `%VAR%`, `!VAR!`, `call`) is refused before anything runs.
   - Each command is also vetted by the PreToolUse guard's rules, because `verify run` starts processes without the hook.
2. **Only approved commands run.** "Approved" means the `commands.*` entries in `.factory/config.json` on the default branch on `origin` (`origin/HEAD`), which only a PR merged by the human changes (D1, D5).
   - An entry the story branch adds, changes or removes is not run; it is recorded as `unapproved`, and `verify check` rejects the evidence.
   - No approved config, or no `origin/HEAD`, means nothing runs.
   - The evidence records its source as `config_source` (for example `origin/main@1661f63`).
3. **Older guard gaps are left for T9.5** (computed arguments, inherited environment variables, indirect execution). No credential stripping or other broad security change is made here.

## Consequences

- Windows support for `verify run` requires Git for Windows, which the factory already requires.
- A few legitimate bash forms are refused, such as a regex `'^test'` argument (accepted limitation, [backlog.md](../backlog.md)).
- On a project's walking-skeleton story, the commands are first set on the story branch, so they are unapproved until that PR merges. T6.5 must handle this ([B-01](../backlog.md#b-01)).
- Approval rests on the default branch changing only through merged PRs. The factory never pushes to `main`, but `main` has no branch protection yet ([B-24](../backlog.md#b-24), owner T9.6).
- `verify run` is as strong as the guard's analysis: the gaps in [B-09](../backlog.md#b-09) to [B-11](../backlog.md#b-11) still apply to approved commands, and the commands inherit the environment's credentials ([B-15](../backlog.md#b-15)).

## Evidence

- Decision: [task-log.md](../task-log.md), T6.1 "Approved decisions" 1–3.
- [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), review-fix commit `83411f1`; merge commit `dda1aed`.
- Code: `run_command_line` and `bash_executable` in `scripts/factory/gh.py`; `cmd_syntax`, `approved_config` and `unapproved_changes` in `scripts/factory/evidence.py`.
- Tests in `tests/test_evidence.py`, including `test_cmd_only_syntax_never_reaches_execution`, `test_configured_commands_run_with_bash`, `test_windows_uses_git_bash_next_to_git_never_a_bash_on_path` and `test_no_approved_config_runs_nothing`. PR #36 records mutation checks: 16 failing subtests without the cmd-syntax refusal, 7 failures with the branch config trusted.
- [02-factory-architecture.md](../02-factory-architecture.md) §4.4, the `verify run` row.

## Not covered

Commands the model runs through Claude Code's own Bash or PowerShell tools during a station are a separate path, controlled by the PreToolUse guard ([02-factory-architecture.md](../02-factory-architecture.md) §8). This ADR does not change it.
