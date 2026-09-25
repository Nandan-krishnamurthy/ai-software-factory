# 02 — AI Software Factory: Architecture

| | |
|---|---|
| **Status** | Proposed, for review before implementation |
| **Date** | 2026-09-24 |
| **Implements** | [01-factory-requirements.md](01-factory-requirements.md) (Draft v2, D1–D5) |

---

## 1. Architecture in one page

The factory is a **Claude Code project** (this repo). You open Claude Code in this repo and point it at a separate **target repo** on disk. The factory has three layers plus a safety net:

```
┌──────────────────────────────────────────────────────────────────────┐
│  YOU  ── /factory-start  /factory-resume  /factory-continue  ...     │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
 ┌──────────────────────────────┐   Layer 1: COMMANDS (thin)
 │ .claude/commands/factory-*.md │  "Ask the state engine where we are, then
 └───────────────┬──────────────┘   follow the station file it names."
                ▼
 ┌──────────────────────────────┐   Layer 2: STATIONS (the "how")
 │ stations/S00…S12-*.md         │  Markdown instructions for Claude, one per
 │ stations/_rules.md            │  station. They do not depend on how they are
 │ templates/*.md                │  invoked (slash command today, headless later).
 └───────────────┬──────────────┘
                ▼
 ┌──────────────────────────────┐   Layer 3: STATE ENGINE (deterministic)
 │ scripts/factory.py            │  Python stdlib + git + gh. Reads GitHub and the
 │  state | doctor | issues sync │  target repo, then works out the current state
 │  pick | checkpoint | comment  │  and the next allowed action. Performs the
 │  guard                        │  bookkeeping that must be idempotent.
 │  └ gate signals: single-account (MVP) | bot (later)
 └───────────────┬──────────────┘
                ▼
 ┌──────────────────────────────┐
 │ TARGET REPO (local clone)     │  code, .factory/config.json, docs/factory/**
 │ GitHub (issues, labels, PRs)  │  ← the source of truth for all state
 └──────────────────────────────┘

 SAFETY NET: .claude/settings.json → permission allow/deny list + a PreToolUse
 hook (factory.py guard). The hook blocks merges, pushes to main, force-pushes
 and writes to the factory repo, even if the model tries to do them.
```

**Division of labour**
- **Claude (LLM) does the creative work.** It writes requirements, architecture, plans, stories, code, tests, PR descriptions, and the evidence for each acceptance criterion.
- **`factory.py` (code) does the bookkeeping.** It works out the current state, picks the next story, creates issues without duplicates, writes checkpoints, and enforces the guard rules. These steps must give the same answer every time, so they are code, not prompts.
- **You** hold every gate. You merge (D1), and you say `continue` (D2).

---

## 2. How the confirmed decisions are preserved

| Decision | How the architecture enforces it |
|---|---|
| **D1 Human merges** | No station ever asks for a merge. The **permission deny list** blocks `gh pr merge` and `gh api` merge endpoints, and the **guard hook** blocks them again in case they get past the list. The state engine treats *merged* as something it **observes**, never something it does. There is no config option to enable auto-merge. |
| **D2 Explicit continue** | Only `/factory-continue` may run S6 (Pick Story). `factory.py pick` refuses unless it is passed `--authorized-by-continue`, and only the continue command passes that flag. `/factory-resume` stops at Gate C by design. |
| **D3 Skills/commands first, headless later** | Stations are plain Markdown that does not depend on how it is invoked. Commands are about 10-line wrappers. `factory.py state` returns machine-readable JSON, which a future headless runner can loop on (§11). |
| **D4 Separate repos** | Factory code lives only here. The target holds only `.factory/config.json`, `docs/factory/**`, and its own code. The guard blocks writes and commits to the factory repo while a target is active. The only exception is the gitignored `.factory-local/` pointer file. |
| **D5 Single account, merge = approval** | Gate decisions are read through one **gate-signal interface** (§9) that has two implementations. `single-account` is the only one built for the MVP: your merge is the approval and `/changes` requests rework. `bot` comes later and reads GitHub's real Approve / Request changes reviews. Stations and the state machine only use the interface's normalised verdicts, so moving to a bot account changes config, not design. |

---

## 3. Invocation model (resolves open question 7)

**Decision: run Claude Code from the factory repo, and give it the target path.**

```
cd C:\Projects\ai-software-factory
claude
> /factory-target C:\Projects\task-tracker
> /factory-start
```

- `/factory-target <path>` checks the path. It must be a git repo with a GitHub remote, and must not be the factory repo itself. It then records the path in `.factory-local/target.json` (gitignored, so it survives across sessions) and adds the path to Claude Code's allowed directories via `.claude/settings.local.json` → `permissions.additionalDirectories` (also gitignored).
- Every command and station starts by printing **`Target: <path> (<owner/repo>)`**. This reduces the risk of working on the wrong repo.
- Git commands run as `git -C <target> …`, and project commands (tests, build) run from inside the target directory.
- **The target's own `CLAUDE.md`** is not loaded automatically in this setup, because Claude Code loads `CLAUDE.md` from its working directory, which is the factory repo. Stations therefore read `<target>/CLAUDE.md` explicitly and follow it as project conventions. Where it conflicts with the factory safety rules, the safety rules win.

**Why not the alternatives**
- *Install commands into the target:* this breaks D4.
- *User-level commands or a plugin, run from the target:* this would work, but it spreads factory state across `~/.claude` and makes the factory's version harder to pin. It is kept as a **future packaging option** (§11). Stations do not change either way.

---

## 4. Component design

### 4.1 Factory repo layout

```
ai-software-factory/
├── CLAUDE.md                    # tells Claude it is the factory; points to stations/_rules.md
├── .claude/
│   ├── settings.json            # permissions allow/deny + PreToolUse guard hook (committed)
│   ├── commands/
│   │   ├── factory-target.md
│   │   ├── factory-start.md
│   │   ├── factory-resume.md
│   │   ├── factory-continue.md
│   │   └── factory-status.md
│   └── agents/
│       └── ac-verifier.md       # independent verifier subagent for S10
├── stations/
│   ├── _rules.md                # global rules every station loads (safety, honesty, target handling)
│   ├── S00-intake.md
│   ├── S01-discovery.md
│   ├── S02-requirements.md
│   ├── S03-architecture.md
│   ├── S04-plan.md
│   ├── S05-stories.md           # also opens the Planning PR
│   ├── S05b-issues.md
│   ├── S06-pick.md
│   ├── S07-branch.md
│   ├── S08-implement.md         # also handles the rework path
│   ├── S09-test.md
│   ├── S10-verify.md
│   ├── S11-pr.md
│   └── S12-closeout.md
├── templates/
│   ├── config.json              # target .factory/config.json skeleton
│   ├── story.md                 # issue body (Story Contract)
│   ├── pr.md                    # PR body
│   ├── planning-pr.md
│   └── traceability.md
├── scripts/
│   ├── factory.py               # CLI entry point (stdlib only)
│   └── factory/                 # modules: gh.py, state.py, stories.py, guard.py, config.py
├── tests/                       # unit tests for the state engine, stories parser and guard
├── docs/                        # 01 requirements, 02 architecture, 03 plan…
└── .factory-local/              # gitignored: target.json
```

### 4.2 Commands (Layer 1)

| Command | Purpose | Stations it may run | Stops at |
|---|---|---|---|
| `/factory-target <path>` | Select and validate the target | None (runs `factory.py doctor`) | Immediately |
| `/factory-start [requirements-file]` | Begin a new **increment** (§5.2): new project or new requirements for an existing project | S0 → S1 (if existing) → S2 → S3 → S4 → S5 | **Gate A** (Planning PR open) |
| `/factory-resume` | Finish whatever is already in motion, or whatever your last action on GitHub unlocked | Planning revisions, S5b, the in-progress story station, S8 rework, S12 | The next gate. **Never runs S6.** |
| `/factory-continue` | Your Gate C "continue" | Anything `/factory-resume` would do first (including S12 close-out of a story you merged), then S6 → S7 → … → S11 for exactly one story | **Gate B** (PR open) |
| `/factory-status` | Read-only report: state, what is waiting on you, story progress | None | Immediately |

Each command file follows the same pattern:

```
1. Read stations/_rules.md.
2. Run: python scripts/factory.py state --json
3. Print the "Where we are" summary from the JSON.
4. If state.next_action is not permitted for this command → report and stop.
5. Read stations/<state.next_station>.md and execute it.
6. After the station finishes, go back to step 2, until a gate or a stop condition is reached.
```

As built (T2.5), steps 4–6 are decided in code by `python scripts/factory.py route --command <name> [--continuing --after <Sxx>] --json` (`scripts/factory/commands.py`). It answers `run` (a station and its file) or `stop` (a reason), based on these rules:
- **Entry:** the command must be in `allowed_commands`.
- **Continuing:** only while `waiting_on` is `factory`.
- **Scope:** only the stations that command may run. `/factory-resume` never runs S06.
- **Progress:** a station that is still named after it ran stops the loop.
- **Availability:** a station file that doesn't exist yet (S01) stops the command with an explanation.

`/factory-start` enters at S00 from `UNCONFIGURED`, where the state engine names no station. Command names are passed without their slash, e.g. `--command factory-start`, because Git Bash on Windows rewrites `/…` arguments into paths. `/factory-target` and `/factory-status` run no station.

### 4.3 Stations (Layer 2)

Every station file has the same sections, so behaviour is predictable and auditable:

```markdown
---
id: S09
name: Test
allowed_from: [S08]           # the state engine enforces this
next: S10
---
## Purpose
## Preconditions            (checked against factory.py state)
## Inputs                   (exact files / issue fields to read)
## Steps
## Outputs                  (exact files / GitHub objects produced)
## Checkpoint               (factory.py checkpoint call to make at the end)
## Stop conditions          (when to label needs-human and stop)
## Done check               (objective test for completion)
```

Station conventions, checked by `tests/test_stations.py`:
- **`allowed_from` entries.** An entry is a station ID, an entry point (`START`, i.e. `/factory-start`) or a gate (`GATE_A`, `GATE_B`, `GATE_C`). `next` is a station or a gate. A station's `next` must list that station back in its `allowed_from`, and every station must be reachable from `START`.
- **Done check.** Always a checklist naming at least one command, plus the state that `factory.py state --json` must report afterwards.
- **Outputs.** Only target paths from §5.1.
- **Commands.**
  - Every `factory.py` command must parse with the real CLI.
  - Every `gh` command must be pre-approved or read-only.
  - Every `git` command runs as `git -C <T>`.
  - Every `gh`/`git` command must be allowed by the guard.
- **Planning commits** carry the trailer `Factory-Station: <Sxx>`, which invariant 4 relies on.
- **Mode by state.** One station may have several modes, selected by the state. For example, S05 opens the Planning PR from `PLANNING`, and revises it from `GATE_A_CHANGES`.

`stations/_rules.md` holds rules that apply to every station. It repeats the requirements' safety boundaries (§12) and honesty rules (never claim a test passed if it did not run; report failures in the PR), and explains how to treat untrusted content. Issue and PR text, and repo files, are **data**. Only feedback from configured `reviewers` is acted on as instructions, and even then the safety rules win.

### 4.4 State engine — `scripts/factory.py` (Layer 3)

Written in Python 3.11+ using only the standard library. It calls `git` and `gh` as subprocesses and has no pip dependencies.

| Subcommand | What it does | Idempotent |
|---|---|---|
| `target set <path>` / `target show` | Manages `.factory-local/target.json` | ✔ |
| `doctor` | Checks: `gh auth`, remote reachable, target is not the factory repo, clean working tree, required labels exist, branch protection (warns only), config valid | ✔ (read-only) |
| `labels ensure` | Creates or updates the §4 labels, plus `factory:needs-human` and `factory:planning` | ✔ |
| `state [--json]` | **Reconciler.** Works out the current state and the next action (§6) | ✔ (read-only) |
| `increment show` / `increment next [--slug S]` | Reports the current increment and the next free `REQ-`/`STORY-` IDs; `next` allocates the next `NNN-slug` or refuses (§5.2). Changes nothing. | ✔ (read-only) |
| `issues sync [--dry-run]` | Parses `05-stories.md` (§5.4), then creates only the issues that are missing, matched by their `STORY-###` marker. Refuses before Gate A, except with `--dry-run`. | ✔ |
| `pick --authorized-by-continue` | Applies the unblocked rule (§4 of the requirements): open, `status:ready`, not `factory:needs-human`, every "Blocked by" issue closed (an issue it cannot see counts as open). Picks the oldest increment, then the lowest milestone, then the lowest issue number. Assigns the issue, then sets `status:in-progress` last, because that label is the lock. | ✔ (refuses without the flag, and while a story is `in-progress`, `in-review` or `changes-requested`) |
| `checkpoint --issue N --station S09 --next S10 [--note …]` | Adds or updates the single machine-readable checkpoint comment | ✔ |
| `feedback --pr N [--json]` | Lists the PR's verdict and the human feedback items of the current review round (§9.2). Rework stations answer each item with `comment`. | ✔ (read-only) |
| `verdict check --issue N [--file F]` | Checks the AC verifier's verdict (§4.5) against the issue's ACs: one line per AC, each with evidence, plus a `Suite:` line. Exits 1 if it is invalid or anything failed | ✔ (read-only) |
| `label --issue N --status in-review` | Moves the status label on a story issue: adds the new one, then removes the other `status:*` labels, so the issue always has a status. It changes nothing when the label is already right. | ✔ |
| `guard` | PreToolUse hook entry point. Reads the tool call from stdin and exits with code 2 to block it (§8) | ✔ |

Keeping these operations in code gives three things. The operations the requirements need to be idempotent (issues, labels, checkpoints, picking a story) are idempotent by construction. They can be unit-tested. And a headless runner can call exactly the same code later.

### 4.5 AC-verifier subagent

`.claude/agents/ac-verifier.md` is a subagent that runs S10. It gets **only** the issue's acceptance criteria, the diff, and the test commands. It does not see the implementer's reasoning. It re-runs the tests and, for each AC, returns `pass | fail | not-verifiable` along with its evidence. S11 copies that verdict into the PR as it is. Its answer has a fixed shape (one line per AC, then a `Suite:` line), and `factory.py verdict check` enforces the rules on it: every AC covered, in order, each with evidence, and nothing failing. S10 checks the answer before storing it in the checkpoint note; S11 refuses to open a ready PR unless the stored verdict passes the check.

This targets the top requirements risk: a model marking its own work as passed. A fresh context has no stake in the implementation being right.

---

## 5. Data model

### 5.1 Target repo layout

```
<target-repo>/
├── .factory/
│   ├── config.json
│   └── log.md                          # append-only; one line per station run
└── docs/factory/
    ├── traceability.md                 # global matrix across all increments
    └── increments/
        ├── 001-initial/
        │   ├── 00-prd.md
        │   ├── 01-codebase-analysis.md # existing-project increments only
        │   ├── 02-requirements.md
        │   ├── 03-architecture.md
        │   ├── 04-implementation-plan.md
        │   └── 05-stories.md
        └── 002-<slug>/ …
```

*This refines requirements Appendix A: planning docs are grouped into **increments**, and config is JSON so that `factory.py` needs no dependencies. Requirements doc 01 has been updated to match.*

### 5.2 Increments (makes the existing-project workflow repeatable)

An **increment** is one pass through planning: one PRD or change request → one Planning PR → a set of stories.
- **New project:** increment `001-initial`.
- **Existing project** (including Task Tracker once the factory has built it): each new set of requirements starts a new increment `00N-<slug>` with S1 Discovery.
- IDs are **global and never reused**. `REQ-###` and `STORY-###` numbering continues from the highest existing number, so traceability stays unambiguous.
- `/factory-start` refuses to start a new increment while the current one has stories that are open and not blocked. The MVP runs one increment at a time.

`factory.py increment show|next` (`scripts/factory/increments.py`) implements these rules:
- **Current increment:** the highest-numbered one with a local folder, a `factory/plan-<inc>` branch or a Planning PR.
- **Next increment:** one above the highest increment number seen anywhere, including numbers seen only in story issue markers or abandoned plans. An increment number is therefore never reused.
- **Next IDs:** one above the highest `REQ-`/`STORY-` number mentioned in any file under `docs/factory/`, in any story issue marker, or in any Planning PR body.
- **Refusal:** `increment next` refuses (exit 1, with the reasons) while the current increment:
  - has not passed Gate A, unless its Planning PR was closed and its branch deleted (abandoned);
  - still has stories without issues;
  - or has an open story that is not blocked.

  A story counts as blocked if it has `status:blocked` or `factory:needs-human`, or an open story issue in its `Blocked by` line.

### 5.3 `.factory/config.json`

```json
{
  "schema": 1,
  "project": "task-tracker",
  "repo": "owner/task-tracker",
  "default_branch": "main",
  "reviewers": ["<your-github-login>"],
  "commands": {
    "install":   "npm ci",
    "build":     "npm run build",
    "lint":      "npm run lint",
    "typecheck": "npm run typecheck",
    "test":      "npm test"
  },
  "limits": {
    "max_fix_attempts": 3,
    "max_review_rounds": 3,
    "max_diff_lines": 400
  },
  "ci": { "required": false },
  "identity": {
    "mode": "single-account",
    "bot_login": null,
    "bot_token_env": null
  }
}
```
`identity.mode` is `single-account` for the MVP. `bot` is recognised in the schema but rejected by `doctor` with "not implemented yet" until the bot adapter exists (§9.4). The factory's token is **never** stored in config. `bot_token_env` names an environment variable that holds it.
S0 creates this file. S1 fills in `commands` by discovering them. A missing command is set to `null`, which means the gate is skipped and the PR says so. The factory never guesses a command.

### 5.4 `05-stories.md` format (parsed by `issues sync`)

```markdown
### STORY-007: Add due date to tasks
- Traces to: REQ-003, REQ-007
- Blocked by: STORY-005
- Milestone: M2
#### Story
As a <user>, I want <capability> so that <benefit>.
#### Acceptance criteria
- AC1: Given … when … then …
#### Out of scope
None
#### Technical notes
…
#### Test plan
- Unit: …
```
`Blocked by` uses **STORY IDs** (or `None`). `issues sync` translates them to `#issue` numbers when it creates the issues, so dependencies can be written before any issue number exists. It creates issues in dependency order for this reason.

The format is strict (`scripts/factory/stories.py` holds the full rules): the three bullets come right after the heading, and the five `####` sections are all required, in this order, with `None` for an empty one. There are 1–5 ACs, numbered from AC1. Every `###` heading must be a story, while `#`/`##` headings (e.g. one per milestone) and text before the first story are ignored. A dependency cycle, an unknown dependency, a reused STORY ID or a `factory:` marker in a story is an error. Every error names the story, the line and the rule it broke.

Each story becomes an issue titled `STORY-###: <title>`, with the body from `templates/story.md`, labelled `factory:story` and `status:ready`. `issues sync --dry-run` reads the local file and prints the exact plan. A real run requires the increment's Planning PR to be merged (Gate A) and reads the file from the default branch.

### 5.5 Machine-readable markers (in GitHub, invisible when rendered)

| Where | Marker |
|---|---|
| Issue body | `<!-- factory:story id=STORY-007 increment=001-initial -->` |
| Planning PR body | `<!-- factory:planning increment=001-initial -->` |
| Story PR body | `<!-- factory:pr story=STORY-007 -->` |
| Checkpoint comment (one per issue, edited in place) | `<!-- factory:checkpoint {"station":"S09","next":"S10","branch":"story/14-…","sha":"abc123","fix_attempts":1,"review_round":0,"ts":"…"} -->` followed by a human-readable line |
| **Every other comment or reply the factory posts** | `<!-- factory:reply -->` (or a more specific `factory:*` marker) |
| Rework reply to one feedback item (§7.2) | `<!-- factory:reply to=<comment id> -->`: the id of the human comment it answers |

The reconciler finds everything by these markers, not by titles, which a human may edit.

**Why every factory comment is marked.** In single-account mode (§9) the factory and the human post as the **same GitHub user**, so the author can't tell them apart. The marker can. A comment from a configured reviewer **without** a `factory:` marker is treated as human. `factory.py` adds the marker for every comment it posts, and stations must post comments through `factory.py comment` rather than calling `gh … comment` directly. The deny list enforces this (§8).

---

## 6. State machine

`factory.py state` works out **exactly one** state from GitHub and the target repo. Nothing about state is held only in memory.

```
UNCONFIGURED ──/factory-start──► PLANNING(S0…S5) ──► GATE_A_WAITING
                                     ▲                    │
                                     └── changes ─────────┤ (you: request changes)
                                                          │ (you: merge Planning PR)
                                                          ▼
                                                   ISSUES_PENDING (S5b)
                                                          ▼
         ┌────────────────────────────────────────► IDLE_AT_GATE_C ◄──────────┐
         │                                                │ /factory-continue  │
         │                                                ▼                    │
         │                          STORY_IN_PROGRESS (S6…S11, checkpointed)  │
         │                                                ▼                    │
         │                 ┌──────────────────────► GATE_B_WAITING_REVIEW      │
         │                 │ rework pushed                │                    │
         │           GATE_B_CHANGES_REQUESTED ◄───────────┤ you: comment /changes
         │                                                │                    │
         │                      (bot mode only: GATE_B_APPROVED_UNMERGED)      │
         │                                                │ you: merge = approval
         │                                                ▼                    │
         │                                        CLOSEOUT_PENDING (S12) ──────┘
         │
      INCREMENT_COMPLETE (all stories done) ── /factory-start (new increment)

  From any state → NEEDS_HUMAN (factory:needs-human label) or INCONSISTENT (e.g. two stories in progress)
```

**How each state is detected, and which commands may act on it**

| State | Detected when | `/factory-resume` | `/factory-continue` |
|---|---|---|---|
| UNCONFIGURED | No `.factory/config.json` on `main` or on `factory/plan-*` | Report | Report |
| PLANNING | A `factory/plan-<inc>` branch exists and its Planning PR is not open yet | Continue from the first missing doc | Same |
| GATE_A_WAITING | Planning PR open, verdict `PENDING` | Report "waiting for your review / merge" | Same |
| GATE_A_CHANGES | Planning PR verdict `CHANGES_REQUESTED` (§9) | Revise docs, push, reply to each feedback item | Same |
| ISSUES_PENDING | Planning PR merged, and some stories have no issue | Run S5b, then stop at Gate C | Run S5b, then S6… |
| IDLE_AT_GATE_C | No story is in progress or in review; ready stories exist | **Report "say continue"** | Run S6 → S11 |
| STORY_IN_PROGRESS | One issue has `status:in-progress` | Continue from `checkpoint.next` | Same |
| GATE_B_WAITING_REVIEW | Story PR open, verdict `PENDING` | Report "review, then merge or comment `/changes`" | Report |
| GATE_B_CHANGES_REQUESTED | Verdict `CHANGES_REQUESTED`, or the rework lock `status:changes-requested` is held (§7.2) | S8 rework → S9 → S10 → push → reply to each feedback item | Same |
| GATE_B_APPROVED_UNMERGED | Verdict `APPROVED` (**bot mode only**, never reached in the MVP) | Report "approved, please merge" | Report |
| CLOSEOUT_PENDING | Verdict `MERGED` (your approval), issue not yet `status:done` | Run S12, then **stop at Gate C** | Run S12, then S6… |
| *(→ NEEDS_HUMAN)* | Verdict `CLOSED_UNMERGED` | Report "story rejected" | Same |
| INCREMENT_COMPLETE | All of the increment's stories are done | Report | Report "run /factory-start for new requirements" |
| NEEDS_HUMAN | Any issue or PR has `factory:needs-human` | Report the question | Report. You answer, remove the label, then resume. |
| INCONSISTENT | Invariants are broken (see below) | Report, change nothing | Same |

**Invariants** (if any is broken, the state is INCONSISTENT and the factory refuses to act):
- at most one story is `in-progress` or `in-review` (a story with `changes-requested` counts too: it is still in flight),
- every story PR maps to exactly one issue,
- the branch named in a checkpoint exists on the remote,
- the default branch has no unexpected commits authored by the factory.

---

## 7. Key flows

### 7.1 Story run (`/factory-continue` from IDLE)

```
factory.py state            → IDLE_AT_GATE_C
factory.py pick --authorized-by-continue → #14 (STORY-007), label in-progress
S07  git -C T switch -c story/14-add-due-date origin/main; push -u
     checkpoint S07→S08
S08  read issue, 03-architecture, <target>/CLAUDE.md; implement; commit "(#14)"; push
     checkpoint S08→S09
S09  write tests (named "#14 AC1…"); run lint/typecheck/full suite
     on failure: fix and retry, up to max_fix_attempts, else needs-human + draft PR
     checkpoint S09→S10
S10  ac-verifier subagent → per-AC verdict + evidence
     checkpoint S10→S11
S11  if origin/main moved: git pull --no-rebase origin main (no force-push), re-run suite
     gh pr create (templates/pr.md); update traceability.md rows (with the PR number); push
     label in-review
     checkpoint S11→GATE_B
STOP  "PR #21 ready for review: <url>"
```

A push happens after every station, so if the session dies, at most one station's work is lost. Resuming re-runs that station from the pushed state.

### 7.2 Rework (`/factory-resume` or `/factory-continue` at GATE_B_CHANGES_REQUESTED)
1. **S8 (rework mode) checks the round limit.** If round `review_round + 1` would go over `limits.max_review_rounds`, it sets `factory:needs-human` and asks. Otherwise it takes the **rework lock**: it moves the label to `status:changes-requested`, then writes the checkpoint `S08` → `S08`.
2. **S8 collects the items and addresses each one.** `signals.rework_items(pr)` (`factory.py feedback --pr <P> --rework`) returns the human feedback items since the factory's last round summary that no factory reply answers yet. Pushing a commit does not reset this list, so an interrupted rework finds exactly the items still open. S8 addresses each item on the same branch, and records one `Feedback <id>: …` line per item in the commit body.
3. **S9 and S10 run again.** The state stays `GATE_B_CHANGES_REQUESTED` while the lock is held, and the checkpoint's `next` names the station, as it does while a story is in progress.
4. **S11 (rework mode) finishes the round**, in this order:
   - refreshes the PR body, including the AC section with the new verdict;
   - replies to each item via `factory.py comment --to <id>` (marked `to=<id>`, §5.5), with what changed or why not;
   - closes the round with a summary reply that has no `to`;
   - writes `review_round += 1` in the checkpoint (`S11` → `GATE_B`);
   - moves the label back to `status:in-review`, last.

   The push and the marked replies start a new review round, so the same `/changes` never triggers rework twice.

### 7.3 Close-out (after you merge)
S12 checks that the PR is merged, sets `status:done`, runs `git -C T switch main && git pull`, deletes the local story branch, and posts a summary listing the stories that are now unblocked. The station itself only closes out the merged story: it ends at Gate C and **never picks the next story**. What happens next depends on the command that ran it:
- `/factory-resume` **stops at Gate C**. It never starts a story (D2).
- `/factory-continue` goes on through Gate C to S6 and takes **exactly one** next story through S11, stopping at Gate B. Running `/factory-continue` after the merge *is* the human's continue (D2). One continue therefore closes out the previous story and starts at most one new one. This is the same rule as after S5b (`ISSUES_PENDING`). If nothing can start (the increment is complete, or every remaining story is blocked), it stops and reports.

---

## 8. Safety enforcement (defence in depth)

| Layer | Mechanism | Blocks |
|---|---|---|
| 1. Instructions | `stations/_rules.md` | Everything in requirements §12 |
| 2. Permissions | `.claude/settings.json` `permissions.deny` | `gh pr merge*`, `gh pr review*`, `gh pr comment*`, `gh issue comment*`, `gh repo edit*`, `gh repo delete*`, `gh secret*`, `gh api * -X DELETE*`, `git push --force*`, `git push * main`, `git push * HEAD:main`. Direct `gh … comment` is denied so that every factory comment goes through `factory.py comment` and carries its marker (§5.5). |
| 3. Guard hook | `PreToolUse` → `python scripts/factory.py guard` on `Bash`, `Edit`, `Write` | Anything layer 2 cannot match by pattern: pushes to the configured default branch in any spelling, force-pushes to branches that already have a review, **any merge path** (`gh pr merge`, `gh api …/merge`, GraphQL `mergePullRequest`, `enablePullRequestAutoMerge`, `git push` of a merge onto the default branch), `Edit`/`Write` inside the factory repo while a target is active (except `.factory-local/`), and writes outside the target and scratch directories |
| 4. GitHub | Branch protection on `main` (recommended by `doctor`) | Direct pushes. In single-account mode this layer **cannot** stop a merge made with your credentials (§9.3), which is why layers 2 and 3 are tested exhaustively. |

`permissions.allow` pre-approves the routine commands (`git -C`, the `gh issue create|view|edit|list` and `gh pr create|view|edit|list` subcommands, and `python scripts/factory.py`), so the loop is not interrupted by permission prompts. The target's build and test commands are approved the first time they run, or you can add them to `settings.local.json`.

---

## 9. Human identity and gate signals (D5; resolves open question 5)

GitHub does not allow a PR's author to *Approve* or *Request changes* on their own PR. **D5:** the MVP uses **single-account** mode, and **your merge is the approval**. The factory never merges, in any mode.

### 9.1 The gate-signal interface

The only thing the state machine and stations know about a human decision is a **normalised verdict**, produced by `scripts/factory/signals.py`:

```python
class GateSignals(Protocol):
    def verdict(self, pr) -> Verdict: ...            # PENDING | CHANGES_REQUESTED | APPROVED | MERGED | CLOSED_UNMERGED
    def feedback(self, pr, since) -> list[Feedback]: ...  # human feedback items to address in rework
    def is_human(self, comment) -> bool: ...          # separates your comments from the factory's
```

`config.identity.mode` selects the implementation. Nothing outside `signals.py` checks the mode. Gate A (Planning PR) and Gate B (story PRs) both use this interface.

### 9.2 `single-account` (MVP, the only mode built)

| | Rule |
|---|---|
| Factory authenticates as | Your own `gh` login |
| **is_human** | Author is in `config.reviewers` **and** the body has no `factory:` marker (§5.5) |
| **CHANGES_REQUESTED** | A human comment whose first line is `/changes`, posted after the factory's last push. It can be a PR conversation comment or a review summary (a review submitted as *Comment*). |
| **feedback** | Every human comment since the last round: inline review comments, review summaries, and PR comments. The text after `/changes` is included. |
| **APPROVED** | Never reported separately. Approval and merge are the same act. |
| **MERGED** | The PR is merged. This counts as **approval**, and S12 close-out runs. |
| **CLOSED_UNMERGED** | You closed the PR without merging. The factory treats this as a rejection: `NEEDS_HUMAN`, "story rejected: re-plan, split or drop it?". It never reopens the PR by itself. |
| **PENDING** | Anything else. Human comments without `/changes` are listed by `/factory-status` as "N comments, no `/changes` yet". They do not trigger rework. |

**Why use an explicit `/changes`:** a question or a remark should not start a rework round. You decide when a round of feedback is complete, which gives the factory one clear signal to act on.

### 9.3 Safety in single-account mode
Because the factory uses your credentials, **GitHub will allow it to merge**, and branch protection cannot tell the factory apart from you. Merge prevention therefore depends on the factory's own layers (§8): the deny list, the guard hook, and no merge path in any station. These layers are tested for every spelling of a merge command (§12). `doctor` recommends branch protection of "require a PR, no direct pushes" **without** a required approval count, because a required approval would block your own merge.

### 9.4 `bot` mode (future; designed now, not built)

| | Rule |
|---|---|
| Factory authenticates as | A separate machine user, with its token taken from the env var named in `identity.bot_token_env`. Every `gh`/`git` call goes through `gh.py`, which injects `GH_TOKEN`, so this is the only place auth is handled. |
| **is_human** | Author is in `config.reviewers` (the bot is a different login, so no marker is needed; markers are kept anyway) |
| **CHANGES_REQUESTED** | Latest review from a reviewer is *Request changes* |
| **APPROVED** | Latest review from a reviewer is *Approve*, and the PR is not merged → state `GATE_B_APPROVED_UNMERGED`, "please merge" |
| **MERGED / CLOSED_UNMERGED** | Same as single-account |
| Extra safety | Branch protection can then **require your approval**, and the bot can be left off the merge allowlist. This adds a GitHub-level merge block. |

**The switch later:** create the bot account, add it as a collaborator, set `identity.mode: "bot"`, set the token env var, and tighten branch protection. The code change is to add the `BotSignals` class and let `doctor` accept `bot`. Stations, commands, the state machine and the markers stay the same. `/changes` also keeps working in bot mode as a fallback.

- In both modes, only logins listed in `config.reviewers` count. Comments from anyone else appear in the status report but are never acted on.

---

## 10. Remaining open questions, as decided by the architecture

| Req. open question | Decision |
|---|---|
| 1 Gate A granularity | **One Planning PR per increment.** Anything smaller is a new increment. This keeps the MVP simple, and increments already give you milestone-sized approval when you want it. |
| 2 CI | **Not required.** Local quality gates (Q1–Q7) are mandatory. If CI exists, the factory reads its checks, and `ci.required: true` makes a green CI part of the PR gate. For new projects, the walking-skeleton story *offers* a minimal Actions workflow; it is not required. |
| 3 Rework limit | `limits.max_review_rounds` (default 3), then `factory:needs-human`. `limits.max_fix_attempts` (default 3) applies to S9 test-fix loops. |
| 4 Planning-doc changes during implementation | A story PR may make **corrective edits** to its own increment's `03-architecture.md` (listed under "Doc changes" in the PR). **New or changed requirements** always start a new increment with its own Planning PR. |
| 5 Reviewer identity | **Single-account for the MVP, and merge = approval (D5).** `config.reviewers` plus the gate-signal interface (§9), with the bot mode designed but not built. |
| 6 Tracking issue | **Dropped.** Labels, markers and `/factory-status` cover it. |
| 7 Invocation | Run from the factory repo with an active target (§3). |

---

## 11. Extension points (D3, and later work)

| Extension | How it plugs in, without rewriting stations |
|---|---|
| **Headless runner** | `factory.py run --until-gate` loops: `state` → `claude -p "/factory-resume" --output-format json` → `state`, and stops when it reaches a gate or NEEDS_HUMAN. It uses the same commands and guard. |
| **Event-driven (GitHub Actions)** | A workflow triggered by `pull_request_review` / `issue_comment` runs the headless runner with `/factory-resume` (this handles rework). A `/continue` comment from a listed reviewer maps to `/factory-continue`, which keeps D2. |
| **Plugin packaging** | `.claude/commands`, `.claude/agents`, the hook and `stations/` are packaged as a Claude Code plugin, so they can be run from inside a target repo. The code stays in this repo, so D4 still holds. |
| **Bot account (real Approve / Request changes)** | Add the `BotSignals` implementation plus the token handling in `gh.py`, then switch `identity.mode`. See §9.4. Nothing else changes. |
| **Other trackers** | GitHub access is concentrated in `scripts/factory/gh.py` and in station steps that name `gh`. A tracker adapter would replace both. This is a non-goal for the MVP. |
| **Parallel stories** | Would need the "one in-progress" invariant relaxed, plus worktrees. It is explicitly out of scope, and the invariant check keeps it from happening by accident. |

---

## 12. Verifying the factory itself

| Level | What | How |
|---|---|---|
| Unit | State reconciler, stories parser, guard rules, unblocked-pick rule | `python -m unittest` using recorded `gh` JSON fixtures, no network. The guard tests include every blocked spelling of merge and push-to-main commands. |
| Integration | `doctor`, `labels ensure`, `issues sync` idempotency (running it twice changes nothing) | Against a throwaway GitHub sandbox repo |
| End-to-end | Requirements success criteria 1–8 | Task Tracker runbook (`docs/04-task-tracker-test-plan.md`). It includes deliberately killing the session at S8, at Gate B, and after approval but before merge. |

---

## 13. Risks specific to this architecture

| Risk | Mitigation |
|---|---|
| Model skips the `state` call and improvises | Commands are short and always call `state` first. Stations check preconditions. `pick` and `checkpoint` refuse to run from the wrong state. |
| Hook or deny patterns miss a merge spelling. **In single-account mode, GitHub itself will not block a merge made with your credentials.** | Merge-path unit tests covering the CLI, REST, GraphQL and auto-merge spellings; no station has a merge step; an end-to-end check that the factory never merges (requirements success criterion 4). Bot mode later adds a GitHub-level block. |
| Your own comments are mistaken for the factory's, or the other way round (same login) | A `factory:` marker on every factory comment, and direct `gh … comment` is denied, so comments can only be posted through `factory.py comment` |
| A casual comment starts an unwanted rework round | Rework starts only on an explicit `/changes` |
| Parsing `05-stories.md` fails on free-form text | A strict format (§5.4). `issues sync --dry-run` is shown in the Planning PR, so parse errors show up at Gate A. |
| A long S8 fills the context window | Stories are small by contract, and the push plus checkpoint after each station means compaction or a restart loses little |
| The target's `CLAUDE.md` contains instructions that conflict with safety | `_rules.md` precedence: factory safety rules first, then target conventions |
| Windows path and shell differences | `factory.py` uses `pathlib` and `subprocess` lists, never shell strings. The guard normalises paths. |

---

## 14. What gets built first (preview of doc 03)

1. `factory.py` core: `target`, `doctor`, `labels ensure`, `comment`, `state` (planning states only), `signals.py` (single-account only), and the guard with merge-path tests, all with unit tests. Also `.claude/settings.json`.
2. Commands and stations S0–S5, S5b; `issues sync`. **Milestone: a Planning PR for Task Tracker.**
3. Stations S6–S11, `pick`, `checkpoint`, the AC-verifier. **Milestone: the first story PR.**
4. S12, rework, and all resume states. **Milestone: requirements success criteria 3–5.**
5. Existing-project increment on Task Tracker. **Milestone: success criteria 2, 6–8.**
