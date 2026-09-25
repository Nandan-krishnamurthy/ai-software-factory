# 03 — AI Software Factory: Implementation Plan

| | |
|---|---|
| **Status** | Proposed, for review before implementation |
| **Date** | 2026-09-24 |
| **Based on** | [01-factory-requirements.md](01-factory-requirements.md) (v3, D1–D5), [02-factory-architecture.md](02-factory-architecture.md) |

---

## 1. Approach

- **Build it the way the factory will work.** Each task below is one small branch and one PR in *this* repo. You review and merge it by hand; nothing is merged automatically. The factory can't build itself yet, so this is done manually, but it follows the same rules the factory will enforce.
- **Deterministic core first, prompts second.** The state engine and the safety guard are built and unit-tested (M1) before any station prompt exists. Every later milestone depends on them.
- **Pure logic, thin I/O.** `state.py`, `signals.py`, `stories.py` and `guard.py` are pure functions over plain data (a "snapshot"). Only `gh.py`/`git.py` touch the network or disk. This makes most of the factory unit-testable offline with recorded fixtures.
- **Prove each milestone on a real repo.** M1 is proven against a throwaway **sandbox** GitHub repo, and M2–M5 against **Task Tracker**.

### Milestones at a glance

| # | Milestone | Outcome you can see | Requirements success criteria proven |
|---|---|---|---|
| **M0** | Repo foundations | Factory repo on GitHub with a test runner and CI-free lint | none |
| **M1** | State engine and safety core | `factory.py doctor/state/labels/comment/guard` work against the sandbox. The factory **cannot** merge or push to `main`. | Part of 4 (never merges) |
| **M2** | Planning pipeline | `/factory-start` on Task Tracker opens a **Planning PR**. After you merge it, issues are created. | Part of 1 |
| **M3** | Story loop | `/factory-continue` produces the **first story PR**, with AC evidence | Part of 1, 7 |
| **M4** | Gates, rework, close-out and resume | `/changes` rework, merge → close-out → Gate C, and resume after being killed at any point | 1, 3, 4, 5 |
| **M5** | Existing-project increment and hardening | A second increment on Task Tracker as an existing project. Runbook and README. | 2, 6, 7, 8 |

### Dependency graph

```
M0 ──► M1 ──► M2 ──► M3 ──► M4 ──► M5
        │                    ▲
        └── T1.6 guard ──────┘ (guard gets its tests extended in M4)
```
The milestones run strictly in order. Within a milestone, tasks can be done in any order that respects their `Depends` list.

---

## 2. Prerequisites (from you, before M0/M1)

| # | Needed | Needed by |
|---|---|---|
| P1 | An empty GitHub repo for the factory (e.g. `<you>/ai-software-factory`) | T0.1 |
| P2 | An empty **sandbox** GitHub repo for integration tests (e.g. `<you>/factory-sandbox`), which can be wiped at any time | M1 integration tests |
| P3 | An empty GitHub repo for **Task Tracker**, plus its **PRD** (Markdown) | M2 |
| P4 | `gh auth login` done as your account (single-account mode, D5) | M1 |
| P5 | Python ≥ 3.11 (3.12 is installed), `git`, `gh` ≥ 2.x, Claude Code CLI on PATH (not found yet) | M1 / M2 |

---

## 3. Conventions for every task

**Task format:** each task lists *Depends*, *Build* (the deliverables), *Acceptance criteria*, *Tests*, and a size (**S** under ½ day, **M** about 1 day, **L** about 2 days).

**Global Definition of Done** (applies to every task, in addition to its own acceptance criteria):
1. Built on branch `task/<id>-<slug>`, and PR opened with the task ID in the title.
2. All acceptance criteria are met, and the PR shows evidence for each one.
3. New logic has unit tests, and `python -m unittest` passes in full.
4. `ruff check` passes (lint only, no formatter debates). Stdlib only in `scripts/`: no pip dependencies at runtime.
5. Works on Windows (Git Bash and PowerShell). Paths use `pathlib`, and subprocesses are called with argument lists, never shell strings.
6. No merge path is added anywhere. The guard tests still pass.
7. The relevant docs are updated (README usage, station files, or docs 01/02 if the design changed, with the change noted in the PR).
8. You have reviewed the PR and merged it yourself.

**Milestone Definition of Done:** all tasks in the milestone are merged, **and** the milestone demo (listed at the end of each milestone) has been run and its result recorded in `docs/progress.md`.

---

## M0 — Repo foundations

### T0.1 Initialise the factory repo · S
- **Depends:** P1
- **Build:** `git init`; `.gitignore` (including `.factory-local/`, `.claude/settings.local.json`, `__pycache__/`); `README.md` (a stub: what this is, a link to docs); `LICENSE` (you choose); push to GitHub; branch protection on `main` set to "require PR, no required approvals" (architecture §9.3).
- **Acceptance criteria:** the remote exists; a direct push to `main` is rejected by GitHub; docs 01–03 are committed.
- **Tests:** manual. Run `git push origin HEAD:main` from a scratch commit and confirm GitHub rejects it.

### T0.2 Python project skeleton and test runner · S
- **Depends:** T0.1
- **Build:** `scripts/factory.py` (argparse entry point with an empty set of subcommands), a `scripts/factory/` package, `tests/` with a smoke test, `pyproject.toml` (ruff config only), and a `tests/fixtures/` directory.
- **Acceptance criteria:** `python scripts/factory.py --help` lists its subcommands; `python -m unittest` runs and passes; `ruff check` is clean.
- **Tests:** a smoke test that imports every module.

### T0.3 Factory `CLAUDE.md` and rules skeleton · S
- **Depends:** T0.1
- **Build:** a root `CLAUDE.md` ("you are the factory; always read `stations/_rules.md`; never act without an active target") and `stations/_rules.md` with the safety, honesty, untrusted-content and precedence rules from requirements §12 and architecture §4.3.
- **Acceptance criteria:** every rule in requirements §12 appears in `_rules.md`, with the section it comes from.
- **Tests:** a review checklist in the PR that ticks off each §12 bullet.

**M0 demo:** clone the repo fresh, run the tests, and see them pass.

---

## M1 — State engine and safety core

### T1.1 `gh.py` / `git.py` I/O layer · M
- **Depends:** T0.2
- **Build:** thin wrappers that run `gh`/`git` with arg lists, parse JSON (`--json` fields), and raise typed errors. There is one place to inject the auth environment (`GH_TOKEN`, for the future bot mode, §9.4). Also a **recorder** that saves real `gh` JSON responses as fixtures, and a **FakeGh** that replays them.
- **Acceptance criteria:** no other module calls `subprocess`; every call has a timeout; stderr is shown in the errors.
- **Tests:** unit tests using FakeGh; a test that fails if `subprocess` is imported anywhere except `gh.py`/`git.py`.

### T1.2 Config and target handling · S
- **Depends:** T0.2
- **Build:** `config.py`: loads and validates `.factory/config.json` (schema v1, architecture §5.3). Validation rejects `identity.mode: "bot"` with "not implemented yet", rejects any token value stored in the file, and rejects any option that enables merging. Also `target set|show` → `.factory-local/target.json`, and `permissions.additionalDirectories` written to `.claude/settings.local.json`.
- **Acceptance criteria:** `target set` refuses a non-git path, a repo with no GitHub remote, and the factory repo itself. Every command prints `Target: <path> (<owner/repo>)`.
- **Tests:** a table of valid and invalid configs; tests of the target validation cases, using temporary directories.

### T1.3 Markers module · S
- **Depends:** T0.2
- **Build:** `markers.py`: builds and parses every `<!-- factory:* -->` marker (architecture §5.5), including the checkpoint JSON.
- **Acceptance criteria:** round-trip parse(build(x)) == x; tolerant of whitespace and CRLF; a malformed marker is ignored, never a crash.
- **Tests:** round-trip, malformed and injection cases (a human pasting a fake marker is handled in T1.7).

### T1.4 `doctor` and `labels ensure` · S
- **Depends:** T1.1, T1.2
- **Build:** `doctor` checks gh auth, remote reachability, a clean working tree, the config, that the target is not the factory repo, the labels, and branch protection (warns only). `labels ensure` creates or updates all `status:*` labels plus `factory:story`, `factory:needs-human` and `factory:planning`.
- **Acceptance criteria:** running `labels ensure` twice gives the same result; `doctor` exits non-zero with a readable list of every failing check.
- **Tests:** unit tests with FakeGh; an integration test against the sandbox (P2).

### T1.5 `comment` subcommand · S
- **Depends:** T1.1, T1.3
- **Build:** `factory.py comment --issue|--pr N --kind reply|checkpoint --body-file F` posts a comment with the right marker added. `--kind checkpoint` edits the one existing checkpoint comment in place instead of adding another.
- **Acceptance criteria:** every comment posted has a marker; running the checkpoint command twice still leaves exactly one checkpoint comment.
- **Tests:** unit tests with FakeGh; sandbox integration.

### T1.6 Guard hook and `.claude/settings.json` · L
- **Depends:** T1.2
- **Build:** `guard.py`, a pure `decide(tool_name, tool_input, context) -> allow | block(reason)`, plus the `factory.py guard` stdin/exit-2 adapter. `.claude/settings.json` holds the `permissions.allow` and `permissions.deny` lists from architecture §8 and the `PreToolUse` hook on `Bash|Edit|Write`.
- **Acceptance criteria:** blocks every merge path (`gh pr merge` in any flag order, `gh api` REST `/merge`, GraphQL `mergePullRequest` and `enablePullRequestAutoMerge`, `git push` to the default branch in every refspec spelling, `--force`/`-f`/`--force-with-lease` to a branch that has been reviewed); blocks `gh pr|issue comment` and `gh pr review`; blocks `Edit`/`Write` in the factory repo while a target is active (except `.factory-local/`); blocks writes outside the target and scratch directories. Allows normal story work.
- **Tests:** a table-driven test with **at least 40 block cases and 20 allow cases**, including chained commands (`&&`, `;`, `|`), `bash -c`, env-var prefixes, quoted refspecs, and Windows paths. A test also confirms that `settings.json` points the hook at the right command.

### T1.7 `signals.py` (single-account) · M
- **Depends:** T1.1, T1.3
- **Build:** the `GateSignals` protocol, `SingleAccountSignals` (architecture §9.2), and a factory function chosen by `identity.mode`.
- **Acceptance criteria:** verdicts `PENDING`, `CHANGES_REQUESTED`, `MERGED` and `CLOSED_UNMERGED` are derived exactly as §9.2 defines them. A `/changes` comment from someone who is not a reviewer is ignored. A reviewer comment that contains a factory marker is treated as non-human. A `/changes` older than the factory's last round does not trigger rework again. `APPROVED` is never returned in single-account mode.
- **Tests:** fixture-based tests for each verdict, plus spoofing cases (a fake marker, a non-reviewer, an old `/changes`).

### T1.8 State reconciler, planning states · M
- **Depends:** T1.3, T1.7
- **Build:** `collect_snapshot()` (I/O), and a pure `derive_state(snapshot)` for UNCONFIGURED, PLANNING, GATE_A_WAITING, GATE_A_CHANGES, ISSUES_PENDING, IDLE_AT_GATE_C, NEEDS_HUMAN and INCONSISTENT. `factory.py state --json` outputs `{state, next_station, allowed_commands, waiting_on, details}`.
- **Acceptance criteria:** exactly one state for every snapshot; the invariants from architecture §6 produce INCONSISTENT; the output JSON matches a documented schema.
- **Tests:** one fixture snapshot per state, plus conflict and invariant cases.

**M1 demo (against the sandbox repo):** `target set` → `doctor` → `labels ensure` → `state` (UNCONFIGURED). Then post a comment and a checkpoint. Then, in a Claude Code session in the factory repo, **ask Claude to merge a sandbox PR and to push to `main`, and watch both get blocked.**

---

## M2 — Planning pipeline

### T2.1 Templates · S
- **Depends:** T0.2
- **Build:** `templates/config.json`, `story.md`, `pr.md`, `planning-pr.md`, `traceability.md`, following requirements §4 and §6 and architecture §5.
- **Acceptance criteria:** each template contains the required marker placeholders and every section required by the contracts.
- **Tests:** a unit test that checks each template for its required headings and markers.

### T2.2 Stories parser and `issues sync` · M
- **Depends:** T1.1, T1.3, T2.1
- **Build:** `stories.py` parses the strict `05-stories.md` format (architecture §5.4) and validates it against the Story Contract (1–5 ACs, Traces to, Blocked by). `issues sync [--dry-run]` creates only the issues that are missing and translates `STORY-###` dependencies to `#N`.
- **Acceptance criteria:** running it twice creates nothing the second time; a parse or contract error names the story and the rule it broke; `--dry-run` prints the exact plan without making changes.
- **Tests:** parser tests with good and bad examples; an idempotency test with FakeGh; a sandbox integration test.

### T2.3 Increment handling · S
- **Depends:** T1.8
- **Build:** detects the current increment and allocates the next `NNN-slug`; continues global `REQ-###`/`STORY-###` numbering from the highest existing number; refuses to start a new increment while the current one has open, unblocked stories.
- **Acceptance criteria:** IDs are never reused across increments.
- **Tests:** unit tests with repo layouts on disk.

### T2.4 Station files S00, S02–S05, S05b · L
- **Depends:** T0.3, T2.1, T2.2
- **Build:** one file per station in the standard format (frontmatter plus Purpose, Preconditions, Inputs, Steps, Outputs, Checkpoint, Stop conditions, Done check). S05 opens the Planning PR with the `issues sync --dry-run` output embedded. S01 comes later, in M5.
- **Acceptance criteria:** every station has an objective Done check; no station has a merge step; each output path matches architecture §5.1.
- **Tests:** a lint test (`tests/test_stations.py`) that parses every station file and checks the frontmatter, the required sections and the `allowed_from`/`next` graph, and scans for forbidden commands.

### T2.5 Commands `/factory-target`, `/factory-start`, `/factory-status`, `/factory-resume` (planning scope) · M
- **Depends:** T1.8, T2.4
- **Build:** the thin command files (architecture §4.2): read rules → `state --json` → summary → check that the command is allowed in this state → run the station → loop until a gate.
- **Acceptance criteria:** `/factory-resume` at GATE_A_CHANGES revises the docs and replies via `factory.py comment`; at ISSUES_PENDING it runs S05b and then **stops at Gate C**.
- **Tests:** the command-file lint (same checker as T2.4); a manual demo.

**M2 demo (Task Tracker, P3):** `/factory-target` → `/factory-start` with the PRD → the Planning PR opens. Comment `/changes` with one piece of feedback → `/factory-resume` revises the PR. Merge it yourself → `/factory-resume` creates the issues and stops at "say continue".

---

## M3 — Story loop

### T3.1 `pick` and `label` · S
- **Depends:** T1.8, T2.2
- **Build:** `pick --authorized-by-continue` applies the unblocked rule (requirements §4: lowest milestone first, then lowest issue number), sets `status:in-progress` and assigns the issue. `label --issue N --status X` makes sure the issue has exactly one `status:*` label.
- **Acceptance criteria:** `pick` refuses without the flag, and refuses when a story is already in progress or in review; ties are broken the same way every time.
- **Tests:** a table of dependency graphs covering the selection rule; refusal cases.

### T3.2 State reconciler, story states · M
- **Depends:** T1.8, T3.1
- **Build:** adds STORY_IN_PROGRESS (reading `checkpoint.next`), GATE_B_WAITING_REVIEW and INCREMENT_COMPLETE.
- **Acceptance criteria:** a checkpoint that points to a missing remote branch → INCONSISTENT.
- **Tests:** fixture snapshots for each new state.

### T3.3 Station files S06–S11 · L
- **Depends:** T2.4, T3.1
- **Build:** stations S06 to S11, as in architecture §7.1. Includes the push plus checkpoint after each station, `max_fix_attempts` handling (on exhaustion: a draft PR and `factory:needs-human`), the rebase and re-test before the PR, the traceability rows written into the PR, and reading `<target>/CLAUDE.md`.
- **Acceptance criteria:** the PR body follows `templates/pr.md` exactly; the evidence for each AC is copied from the verifier without changes; a skipped quality gate (a `null` command) is stated in the PR.
- **Tests:** the station lint; the full demo below.

### T3.4 AC-verifier subagent · M
- **Depends:** T0.3
- **Build:** `.claude/agents/ac-verifier.md`. It takes only the ACs, the diff and the test commands; it re-runs the tests; and it returns a structured per-AC verdict of `pass | fail | not-verifiable` with evidence.
- **Acceptance criteria:** it gives no verdict without evidence; a test failure reported by the verifier stops S11.
- **Tests:** a manual check on a seeded story with one AC deliberately left unmet. The verifier must report it as `fail`.

### T3.5 Command `/factory-continue` · S
- **Depends:** T3.2, T3.3
- **Build:** the only command that passes `--authorized-by-continue`. It does any pending resume work first, then S06 → S11, and stops at Gate B.
- **Acceptance criteria:** `/factory-resume` in IDLE_AT_GATE_C never picks a story (checked in the demo).
- **Tests:** command-file lint; demo.

**M3 demo (Task Tracker):** `/factory-continue` → the walking-skeleton story → a PR with AC evidence and a green test suite, then a stop at Gate B. Separately: run `/factory-resume` while idle and confirm it only reports.

---

## M4 — Gates, rework, close-out and resume

### T4.1 State reconciler, Gate B and close-out states · M
- **Depends:** T3.2, T1.7
- **Build:** adds GATE_B_CHANGES_REQUESTED, CLOSEOUT_PENDING, and CLOSED_UNMERGED → NEEDS_HUMAN. GATE_B_APPROVED_UNMERGED is present but reachable only in bot mode.
- **Acceptance criteria:** all 14 states in architecture §6 are reachable from fixtures, or marked as bot-only.
- **Tests:** a complete state-table test in which every row of the architecture §6 table is one test case.

### T4.2 Rework path (S08 rework mode) · M
- **Depends:** T4.1, T3.3
- **Build:** S08 in rework mode: `signals.feedback()` gathers the items → address each one → run S09 and S10 again → push → reply to each item via `factory.py comment` → refresh the AC section of the PR → `review_round += 1`. When `max_review_rounds` is exceeded, the factory sets `factory:needs-human`.
- **Acceptance criteria:** the same `/changes` never starts rework twice; every feedback item gets a marked reply.
- **Tests:** a signals-level round-closure test; the demo.

### T4.3 Station S12 close-out · S
- **Depends:** T4.1
- **Build:** confirms the merge, sets `status:done`, switches the local clone to `main` and pulls, deletes the local branch, posts a summary of the stories that are now unblocked, and ends at Gate C. The station only closes out the story and **never picks the next one**. The routing is already in place (T4.1): after S12, `/factory-resume` stops at Gate C, and `/factory-continue` goes on to S06 and takes exactly one next story to Gate B (architecture §7.3).
- **Acceptance criteria:** S12 only runs after it has observed a merge; it performs no merge itself, and it never runs `pick`.
- **Tests:** station lint; demo.

### T4.4 Resume robustness · M
- **Depends:** T4.1–T4.3
- **Build:** hardens the idempotency of every create-type action (branch, PR, issue, checkpoint): each checks whether the item already exists before creating it. If uncommitted local changes are found on resume, the factory reports them and does not discard them.
- **Acceptance criteria:** resuming produces no duplicate branches, PRs, issues or checkpoints.
- **Tests:** "crash replay" unit tests, in which a snapshot is taken after each step of a station and the rest is replayed; plus the kill tests below.

### T4.5 Guard hardening pass · S
- **Depends:** T1.6
- **Build:** extends the guard's test table with any command spellings observed during M2–M4 sessions (taken from the transcripts).
- **Acceptance criteria:** every command the model tried during the demos is classified correctly.
- **Tests:** the extended table.

**M4 demo (Task Tracker). This proves success criteria 3, 4 and 5:**
1. Kill the session during S08. `/factory-resume` finishes the story without duplicates.
2. Kill it at Gate B. `/factory-resume` reports "waiting for review".
3. Comment `/changes` with two points → `/factory-resume` → rework on the same PR, and both points get replies.
4. Merge → `/factory-resume` → close-out, then a stop at Gate C. `/factory-continue` → next story. Then merge that story → `/factory-continue` → close-out **and** the next story in one run, stopping at Gate B.
5. Close a PR without merging → NEEDS_HUMAN.
6. Repeat until **3 stories** are merged. This completes success criterion 1.

---

## M5 — Existing-project increment and hardening

### T5.1 Station S01 Codebase Discovery · M
- **Depends:** T2.4
- **Build:** detects the stack, layout, conventions and build/lint/test commands, and writes `commands` into the config. It runs the baseline tests; if they are red, it stops with `factory:needs-human`.
- **Acceptance criteria:** the factory never guesses a command; a command it cannot find is set to `null` and reported.
- **Tests:** a manual check on two repos with different stacks; a check that the baseline-red path stops.

### T5.2 `/factory-start` for existing projects and new increments · S
- **Depends:** T2.3, T5.1
- **Build:** detects a repo that already has code or earlier increments, runs S01, and uses a delta-style requirements and architecture template.
- **Acceptance criteria:** the new increment gets `002-<slug>`, and its REQ and STORY numbers continue from the previous increment.
- **Tests:** a unit test for detecting existing projects; the demo.

### T5.3 `/factory-status` report polish · S
- **Depends:** T4.1
- **Build:** shows what is waiting on you, the progress of the current increment, the Done status of each REQ (derived as described in requirements §11), and a hint when there are "N comments, no `/changes`".
- **Acceptance criteria:** answers "what do I do next?" in a single line at the top.
- **Tests:** snapshot tests of the rendered output.

### T5.4 Runbook, README and reusability check · M
- **Depends:** T5.2
- **Build:** `docs/04-task-tracker-test-plan.md` (a step-by-step runbook for success criteria 1–8); a README with install and usage; an **audit for Task Tracker specifics** (grep the factory repo for `task-tracker` or anything specific to that stack).
- **Acceptance criteria:** the grep finds no Task Tracker references outside docs and examples; the same checkout is pointed at the sandbox and at Task Tracker without any code change (success criterion 8).
- **Tests:** an automated test (`tests/test_reusability.py`) that fails on Task Tracker-specific strings in `scripts/`, `stations/`, `.claude/` or `templates/`.

**M5 demo:** write a change request for Task Tracker → `/factory-start` → S01 → Planning PR for increment 002 → merge → one story delivered following the existing conventions (success criterion 2). Then check traceability: choose a merged line of code, follow PR → issue → REQ → PRD section, and time it (success criterion 6).

---

## 4. Test strategy summary

| Layer | Scope | Runs | Tooling |
|---|---|---|---|
| Unit | `state`, `signals`, `stories`, `guard`, `markers`, `config`, `pick` | Every PR | `unittest` plus FakeGh fixtures, offline |
| Lint | Station and command files (structure, `next`/`allowed_from` graph, forbidden commands), templates, reusability | Every PR | Custom `unittest` checks |
| Integration | `doctor`, `labels ensure`, `comment`, `issues sync` idempotency | Once per milestone, or on demand | The sandbox repo (P2) |
| End-to-end | Requirements success criteria 1–8 | Milestone demos M2–M5 | Task Tracker and the runbook (T5.4) |

CI for the factory repo is **not** required for the MVP (architecture §10). The tests are run locally and their output is pasted into each PR as evidence.

---

## 5. Risks to the plan

| Risk | Mitigation |
|---|---|
| The Claude Code CLI isn't on PATH (seen during planning) | P5; check it before M2. The IDE extension is enough for M0–M1. |
| The guard blocks legitimate work too aggressively | Allow-cases in the T1.6 table; T4.5 hardening from real transcripts |
| Station prompts need many iterations to behave | Tune them during M2–M4 demos. Lint keeps them structurally valid while they change. |
| A Task Tracker PRD isn't ready when M2 starts | M1 needs no PRD. P3 is flagged now. |
| The plan grows as the factory is used | New findings go to a `docs/backlog.md` rather than into the current milestone, unless they block it |

---

## 6. Task index

| ID | Task | Size | Depends |
|---|---|---|---|
| T0.1 | Initialise the factory repo | S | P1 |
| T0.2 | Python skeleton and test runner | S | T0.1 |
| T0.3 | `CLAUDE.md` and `_rules.md` | S | T0.1 |
| T1.1 | `gh.py`/`git.py` I/O layer + FakeGh | M | T0.2 |
| T1.2 | Config and target handling | S | T0.2 |
| T1.3 | Markers module | S | T0.2 |
| T1.4 | `doctor`, `labels ensure` | S | T1.1, T1.2 |
| T1.5 | `comment` subcommand | S | T1.1, T1.3 |
| T1.6 | Guard hook and settings.json | L | T1.2 |
| T1.7 | `signals.py` (single-account) | M | T1.1, T1.3 |
| T1.8 | State reconciler, planning states | M | T1.3, T1.7 |
| T2.1 | Templates | S | T0.2 |
| T2.2 | Stories parser and `issues sync` | M | T1.1, T1.3, T2.1 |
| T2.3 | Increment handling | S | T1.8 |
| T2.4 | Stations S00, S02–S05, S05b | L | T0.3, T2.1, T2.2 |
| T2.5 | Commands target/start/status/resume | M | T1.8, T2.4 |
| T3.1 | `pick` and `label` | S | T1.8, T2.2 |
| T3.2 | State reconciler, story states | M | T1.8, T3.1 |
| T3.3 | Stations S06–S11 | L | T2.4, T3.1 |
| T3.4 | AC-verifier subagent | M | T0.3 |
| T3.5 | `/factory-continue` | S | T3.2, T3.3 |
| T4.1 | Reconciler: Gate B and close-out states | M | T3.2, T1.7 |
| T4.2 | Rework path | M | T4.1, T3.3 |
| T4.3 | Station S12 close-out | S | T4.1 |
| T4.4 | Resume robustness | M | T4.1–T4.3 |
| T4.5 | Guard hardening pass | S | T1.6 |
| T5.1 | Station S01 Discovery | M | T2.4 |
| T5.2 | Existing-project `/factory-start` | S | T2.3, T5.1 |
| T5.3 | `/factory-status` polish | S | T4.1 |
| T5.4 | Runbook, README, reusability check | M | T5.2 |

**Total: 30 tasks, roughly 25–30 working days of effort**, most of it in M1 (the safety core) and in tuning the station prompts during M2–M4.
