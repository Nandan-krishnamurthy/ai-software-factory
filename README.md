# AI Software Factory

A reusable, human-gated workflow that uses Claude Code to take a **separate target repository** from requirements to merged, tested code, **one small GitHub story and one reviewed pull request at a time**. It stops at every human gate, never merges anything itself, and can resume after a session ends at any point.

The factory works on any GitHub repository. Everything project-specific lives in the target repo: its `.factory/config.json` and its `docs/factory/` folder. The factory's own code, stations, templates and commands contain nothing about any one project (checked by `tests/test_reusability.py`).

> **Status:** M0–M4 are complete and demonstrated. M5 (existing projects and hardening) is being built: see [docs/progress.md](docs/progress.md) and the runbook [docs/04-task-tracker-test-plan.md](docs/04-task-tracker-test-plan.md).

## Requirements

- **Python 3.11 or later.** The factory uses the standard library only; there is nothing to `pip install`.
- **git** and the **GitHub CLI `gh`** 2.x, logged in as you: `gh auth login`. The token needs access to the target repo's contents, issues and pull requests.
- **Claude Code**: the CLI, the desktop app or an IDE extension.
- A **target repository** on GitHub, cloned locally, with at least one commit on its default branch. To build it and run its tests, the target's own toolchain must be installed too (for example Node.js, Python or Go).
- Recommended: protect the target's default branch (require a pull request, no required approvals, include administrators). `doctor` warns if it is not protected.

## Install

```
git clone https://github.com/<you>/ai-software-factory.git
cd ai-software-factory
python -m unittest        # optional: check the factory itself (about 2–3 minutes)
```

Then **open Claude Code in this folder**. The slash commands (`.claude/commands/`), the AC-verifier subagent (`.claude/agents/`), the permission allowlist and the safety guard hook (`.claude/settings.json`) are loaded from here. Do not open Claude Code in the target repo to run the factory.

## Usage

### 1. Select the target

```
/factory-target C:\path\to\target-repo
```

This validates the path (a git repo with a GitHub `origin`, not the factory itself), records it in the gitignored `.factory-local/target.json`, gives Claude Code access to it, and runs `doctor`. Fix any `FAIL` before going on. Pointing the factory at another repo is just another `/factory-target`; no factory file changes.

### 2. Plan an increment (up to Gate A)

```
/factory-start path\to\requirements.md
```

The requirements file can be a full PRD (a new project) or a change request (an existing project). The factory:
- copies it to `docs/factory/increments/<NNN-slug>/00-prd.md`;
- for a project that already has code or earlier increments, runs **Codebase Discovery** (S01). It records the stack, conventions and commands, and runs the baseline tests. On a red baseline it stops and asks on an issue labelled `factory:needs-human`: fix the baseline, or reply `/accept-baseline` there;
- writes the requirements, architecture, plan and stories. For an existing project these describe the change: what exists, what changes, and what must keep working;
- opens a **Planning PR** and stops at **Gate A**.

The first increment is `001-initial`. Once every story of an increment is done, `/factory-start <change-request>` starts the next one (`002-<slug>`, …). REQ and STORY numbers continue across increments and are never reused.

### 3. Review at Gate A

- **Approve:** merge the Planning PR yourself, then run `/factory-resume`. The factory creates one GitHub issue per story and stops at **Gate C**.
- **Request changes:** comment on the PR with `/changes` on the first line, followed by your feedback, then run `/factory-resume`. Comments without `/changes` are not acted on.

### 4. Build stories (Gate C → Gate B)

```
/factory-continue
```

This starts **one** story: picks the next unblocked issue, creates its branch, implements it, writes tests for every acceptance criterion, has them checked by an independent AC-verifier subagent, and opens a PR with the evidence. Then it stops at **Gate B**.

### 5. Review at Gate B

- **Approve:** merge the PR yourself. Then:
  - `/factory-continue` closes the story out **and** starts the next one;
  - `/factory-resume` only closes it out and stops at Gate C.
- **Request changes:** comment `/changes` with your feedback, then run `/factory-resume`. The factory reworks the **same** PR and replies to each point.
- **Reject:** close the PR without merging. The factory then waits for your decision (`NEEDS_HUMAN`).

### Commands

| Command | What it does | Stops at |
|---|---|---|
| `/factory-target <path>` | Select and check the target repo | Immediately |
| `/factory-start <requirements-file>` | Begin an increment and plan it | Gate A (Planning PR) |
| `/factory-resume` | Finish whatever is in motion: planning, rework, issue creation, a story already started, a close-out. **Never starts a new story.** | The next gate |
| `/factory-continue` | Your "continue" at Gate C: finish anything pending, then start **one** story and take it to a PR | Gate B (story PR) |
| `/factory-status` | Read-only report. Its first line says what you do next. | Immediately |

If a session ends (a usage limit, a crash, a closed terminal), open a new one, run `/factory-target <path>` if needed, then `/factory-status` or `/factory-resume`. The factory works out where it is from GitHub and the target repo, and never duplicates a branch, PR, issue or checkpoint.

### What the factory never does

It never merges a PR, never pushes to the default branch, never starts a story without your `continue`, never force-pushes a reviewed branch, never changes repo settings, secrets or CI unless a story requires it, and never deploys. A guard hook (`python scripts/factory.py guard`) blocks these commands, and `stations/_rules.md` lists every rule.

### Where things live in the target repo

| Path | Contents |
|---|---|
| `.factory/config.json` | Repo, default branch, reviewers, the build/lint/typecheck/test commands (discovered, never guessed), limits |
| `.factory/log.md` | One line per station run |
| `docs/factory/increments/<NNN-slug>/` | `00-prd.md` … `05-stories.md`, and `01-codebase-analysis.md` for an existing project |
| `docs/factory/traceability.md` | REQ → story → PR → tests, across all increments |
| GitHub | Story issues with `status:*` labels, PRs, and `<!-- factory:… -->` markers in their bodies and comments |

## Working on the factory itself

While a target is active, the factory never modifies its own repo (rule S3). To change the factory:

1. **Deactivate the target:** delete the two gitignored files `.factory-local/target.json` and `.claude/settings.local.json`. `python scripts/factory.py target show` should then say there is no active target.
2. Follow [CLAUDE.md](CLAUDE.md): one task from the plan per branch `task/<id>-<slug>`, a PR titled `[<id>] …`, and you merge it.
3. Run the checks:
   ```
   python -m unittest
   python -m ruff check
   ```
   Code in `scripts/` uses the standard library only, `pathlib` for paths, and argument lists for subprocesses.
4. Run `/factory-target <path>` again before the next factory command.

## Documents

- [01 — Requirements](docs/01-factory-requirements.md): what the factory must do
- [02 — Architecture](docs/02-factory-architecture.md): how it is built
- [03 — Implementation plan](docs/03-factory-plan.md): tasks T0.1–T5.4
- [04 — Task Tracker test plan](docs/04-task-tracker-test-plan.md): the runbook that proves success criteria 1–8
- [Progress and milestone demos](docs/progress.md)
- [Stations](stations/) and their rules ([_rules.md](stations/_rules.md))
- [Templates](templates/README.md): what the factory writes into a target repo
