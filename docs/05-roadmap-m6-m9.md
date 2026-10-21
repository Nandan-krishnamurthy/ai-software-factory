# 05 — AI Software Factory: Roadmap M6–M9 (original)

| | |
|---|---|
| **Status** | Original roadmap, preserved verbatim. Approved for sequential execution (see "Later decisions" below). |
| **Date** | 2026-10-08 |
| **Scope** | Milestones M6–M9, tasks T6.1–T9.9. M0–M5 are in [03-factory-plan.md](03-factory-plan.md). |
| **Conventions** | The task format and the global Definition of Done of [03-factory-plan.md](03-factory-plan.md) §3 apply to every task. |

## About this document

This roadmap was written in a Claude Code session on 2026-10-08 and was not committed to the repository at the time. The text between the two `roadmap:original` markers below is that roadmap **exactly as written**, with every character unchanged, including its original heading levels and its closing remarks. Nothing has been added to it, removed from it, or updated in it. This header is the only part of the file written afterwards.

### Provenance

| | |
|---|---|
| **Source** | Claude Code session `1bcf8818-42c6-44aa-82e5-e187c8b50c7e`, the assistant message at JSONL line index 1046 (0-based; line 1047 counting from 1), message id `msg_011CfpGXNArSnLxXKkQBxurn` |
| **Timestamp** | `2026-10-08T06:09:00.993Z` |
| **Requested by** | The user prompt at line index 1032 of the same session (`2026-10-08T06:06:30Z`): define the complete T6–T9 milestone plan. The milestone names T6–T9 were given in that prompt. |
| **SHA-256** | `9e061a4b6b6e9e33c31044a48191b1f1706c55fba4f87125168d1fc57a1ca533`: the UTF-8 bytes of the original text, which are exactly the bytes between the line `<!-- roadmap:original:start -->` and the line `<!-- roadmap:original:end -->` (excluding the newline that ends the start line and the newline before the end line) |
| **Independent copy** | Claude Code session `1848d76a-f2c2-4145-9479-beabada203a5`, line index 81, contains the same text, character for character |
| **Completeness** | One message that finished normally (`stop_reason: end_turn`). 21 task sections (T6.1–T6.5, T7.1–T7.4, T8.1–T8.3, T9.1–T9.9), each with Depends, Build, Acceptance criteria and Tests; a Goal, Demo and Milestone DoD for each of M6–M9; the open-findings table; the task index; the closing section on order. |

The session logs themselves are not part of the repository and are not needed to use this document.

### Later decisions (not applied to the original text)

- **Sequential execution supersedes the original's closing section.** The original ends with "Does the order T6 → T7 → T8 → T9 need to change?", which recommends pulling T9.1 and T7.1 forward. That recommendation was **rejected** on 2026-10-08 (`2026-10-08T06:36:54Z`, line index 1053 of the same session). The official order is strictly sequential, T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9, and every task stays in its own milestone. If a task meets a dependency problem, it is handled when that milestone is reached, not by reordering the roadmap. The section is kept below only as part of the original text.
- **Decisions and deviations made while implementing tasks** are recorded separately and are never written into the original text. One example is T6.3's quality gate Q6, which is reported as "Not checked: the story contract declares no areas" instead of being checked against declared areas. Until a committed decision log exists, these are recorded in the task PRs (#36 T6.1, #37 T6.2, #38 T6.3, #39 T6.4).

---

<!-- roadmap:original:start -->
## Factory roadmap: milestones M6–M9 (T6–T9)

This follows `docs/03-factory-plan.md` §3. Each milestone **Mn** has tasks **Tn.x**, and each task lists *Depends*, *Build*, *Acceptance criteria*, *Tests* and a size (**S** under ½ day, **M** about 1 day, **L** about 2 days). The **global Definition of Done** (§3, items 1–8) applies to every task unchanged, notably:
- standard library only in `scripts/`;
- Windows support in Git Bash and PowerShell;
- no merge path anywhere;
- the human merges every PR.

The **milestone Definition of Done** is also unchanged: all tasks are merged and the demo is recorded in `docs/progress.md`.

**Invariants every task preserves:**
- **state → route → station:** the state engine decides and stations execute.
- **Human merge approval** (D1, D5).
- **One story only, on an explicit `/factory-continue`** (D2).
- **A fail-closed guard.**
- **No factory code in the target** (D4).

**Open findings from M2–M5, each assigned to a task:**

| Finding | Task |
|---|---|
| ID scanner counts mentions in the docs (M2 Problem 4, M5 follow-up 1) | T7.1 |
| Stale story markers without the label (M4 follow-up 1) | T7.1 |
| A PRD in `docs/` triggers S01 (M2 Problem 2, M4 follow-up 2) | T7.2 |
| A PDF PRD can't be "copied unchanged" (M2 Problem 3) | T7.2 |
| S00 runs `doctor` before `labels ensure` (M2 Problem 1) | T7.2 |
| Close-out wording on an increment's last story (M5 follow-up 2) | T6.4 |
| Gate A `/changes` revision round never demonstrated (M2, M4, M5) | T6 demo |
| Timed traceability walk-through, success criterion 6 (M5) | T6.4 |
| `main` branch protection (M5 follow-up 3) | T9.6 (`doctor`) and the runbook |
| Guard gaps: `git clone` outside the target, `/tmp`, `gh pr $(echo merge)` (M4) | T9.5 |

---

## M6 — Deterministic Verification & Review

**Goal:** facts in a PR come from the factory's code, not from model-written text. The engine runs the quality commands itself, records exact results and maps every AC to tests that really passed. It also builds the PR body from that evidence. The AC verifier's verdict is cross-checked against those facts and can no longer be the only proof. Reviewing becomes faster and harder to fool (success criterion 7).

### T6.1 Evidence ledger: `factory.py verify run` · M
- **Depends:** M5
- **Build:**
  - `verify run --issue <I>` runs `build`, `lint`, `typecheck` and `test` from `.factory/config.json` in the target, in order. It uses argument lists where possible, and the config's string otherwise, run exactly as written (rule H4).
  - It records each command's exact text, exit code, duration, the commit SHA, the last 50 lines of output and a parsed summary line.
  - The result is written to `<SCRATCH>/evidence-<I>.json` and stored in the checkpoint note. A `null` command is recorded as `skipped`.
- **Acceptance criteria:**
  - Evidence names the exact commit it ran on.
  - A command that fails gives `fail` with its exit code; nothing is inferred.
  - A later `verify check` refuses evidence whose SHA isn't the branch head.
- **Tests:**
  - Unit tests with fake processes: pass, fail, timeout and `null`.
  - A summary-parser table covering Vitest, Playwright, pytest, `unittest`, `go test`, `cargo test` and an unknown runner (raw tail kept, `summary: null`).

### T6.2 Deterministic AC ↔ test mapping · M
- **Depends:** T6.1
- **Build:** `verify map --issue <I>` finds the tests named `#<I> AC<n>` in the branch diff, and their results in the runner output (JUnit or JSON reporter when the target already configures one, otherwise name matching in the output). The result is a table of AC to tests (passed, failed, missing). `verdict check` then refuses:
  - a verifier `pass` for an AC that has no passing mapped test;
  - an AC with no test that isn't marked `not-verifiable`.
- **Acceptance criteria:**
  - A verdict claiming `pass` while its mapped test failed is `INVALID`.
  - An AC with no test and no written manual steps blocks S10.
- **Tests:** fixtures from the real #27 and #28 runs (all pass), plus doctored versions of them (a missing test, a failing test, a false "pass").

### T6.3 Deterministic PR body: `pr render` / `pr check` · M
- **Depends:** T6.1, T6.2
- **Build:**
  - `pr render --issue <I>` fills `templates/pr.md` from the ledger, the mapping, the verifier's lines (copied unchanged), `git diff` and the commit bodies.
  - Quality gates Q1–Q8 are computed:
    - **Q6 scope:** the files touched, checked against the story's declared areas.
    - **Q7 size:** excludes lockfiles and generated files.
    - **New dependencies and changed tests:** taken from the manifest and test-file diffs, cross-checked against the commit `New dependency:` and `Changed test:` lines.
  - `pr check <P>` checks an open PR against a fresh render.
- **Acceptance criteria:**
  - A PR body test result that disagrees with the ledger fails `pr check`.
  - A changed existing test that has no `Changed test:` line is flagged (rule H3).
  - The model writes only Summary, Risks and Follow-ups.
- **Tests:** snapshot tests of renders for PR #29 and PR #30 (the #29 snapshot must show its two changed tests), plus mismatch cases.

### T6.4 Review experience and traceability · S
- **Depends:** T6.3
- **Build:**
  - `factory.py trace <file>:<line>` follows `git blame` → merge commit → PR → `Closes #<I>` → `Traces to` → REQ → PRD section. It prints the chain with links and the time taken (success criterion 6).
  - S12's close-out summary says "increment complete, run `/factory-start`" when no open story remains (M5 follow-up 2).
  - `/factory-status` shows the latest evidence and verdict for a PR at Gate B.
- **Acceptance criteria:**
  - `trace` on any line changed by PR #29 or PR #30 reaches the REQ and PRD row in one command.
  - The last story's close-out text names `/factory-start`.
- **Tests:** `trace` on fixture history (squash, merge commit, rebase); the S12 wording for both cases.

### T6.5 Stations S09–S11 use the verification engine · S
- **Depends:** T6.1–T6.4
- **Build:** S09 runs `verify run`, S10 runs `verify map` and then the verifier, and S11 runs `pr render` and `pr check`. Station lint checks that S09–S11 contain no hand-written gate results.
- **Acceptance criteria:**
  - No station tells the model to type test results itself.
  - Rule H1 is enforced by code wherever it can be.
- **Tests:** station lint; the existing `test_stations` suite.

**Demo:** run increment `003-<slug>` on Task Tracker (a small change request), covering:
1. A Gate A `/changes` round, which is the S05 revision mode never demonstrated before.
2. One story, with one deliberately broken AC test pushed during S09. The ledger shows `fail` and the factory fixes it.
3. A forged "pass" in the verdict, which `verdict check` rejects.
4. A Gate B `/changes` round.
5. A merge, then `trace` on a changed line, timed at under one minute.

**Milestone DoD:** T6.1–T6.5 merged, and the demo recorded with timings.

---

## M7 — Plans & Target Knowledge

**Goal:** plans are correct by construction, and the factory keeps durable, current knowledge of each target across increments. IDs are allocated only from structured sources. New and existing projects are detected reliably. Duplicate or already-met requests are caught (M5 observation). Plans are checked by code before Gate A.

### T7.1 ID allocation from structured sources only · S
- **Depends:** M6
- **Build:** `increments.py` counts only these:
  - `**REQ-###**` requirement bullets and `### STORY-###` headings in increment docs;
  - story issues carrying **both** the `factory:story` label and the marker.

  Mentions in prose are ignored. `increment show` reports any ID that is mentioned but never allocated, as a warning.
- **Acceptance criteria:**
  - The M5 note "Next free IDs: REQ-022, STORY-013" no longer uses up STORY-013.
  - The M4 sandbox case (stale unlabelled markers) no longer gives `901-initial` or `STORY-9251317`.
- **Tests:** regression fixtures built from both incidents.

### T7.2 Intake and project detection · M
- **Depends:** T7.1
- **Build:**
  - Existing-project detection counts source and build files only, ignoring `*.md`, `*.pdf` and `docs/**` (M2 Problem 2).
  - S00 accepts non-Markdown requirements by converting them to faithful Markdown with a source header, or by stopping and asking (M2 Problem 3).
  - S00 runs `labels ensure` before `doctor` (M2 Problem 1).
- **Acceptance criteria:**
  - A repo with only a README and `docs/prd.md` routes to S02.
  - A PDF PRD gives `00-prd.md` with a source header.
  - A brand-new repo passes S00 with no manual label step.
- **Tests:** detection fixtures for each layout; a station lint check of the S00 step order.

### T7.3 Target knowledge base · M
- **Depends:** T7.2
- **Build:**
  - `docs/factory/knowledge.md` in the target holds the stack, layout, conventions, commands, hotspots, architecture decisions (with links to each increment's `03`) and known risks.
  - S01 creates or updates it and records the commit it was checked against.
  - The S12 close-out of an increment's last story appends what changed.
  - S02–S08 read it as level-4 conventions (precedence is unchanged).
  - `knowledge check` flags sections that are stale (the code changed since the recorded commit).
- **Acceptance criteria:**
  - The second increment's S01 reuses and updates the file rather than rediscovering everything.
  - No project-specific text appears in the factory (`test_reusability` still passes).
- **Tests:** unit tests for the staleness check; S01 and S12 station lint.

### T7.4 Plan lint and overlap detection · M
- **Depends:** T7.1, T7.3
- **Build:** `plan check --increment <INC>` runs before the Planning PR. It checks:
  - AC form and count (1–5);
  - REQ coverage both ways;
  - `Blocked by` cycles;
  - each story's estimated size against `max_diff_lines` (from its declared files);
  - an `Out of scope` section on every story;
  - **overlap:** new REQs whose text matches REQs that are already Done (the M5 "due dates already exist" case). These become an Open question, or a stop under rule H6.

  S05 embeds the output in the Planning PR.
- **Acceptance criteria:**
  - Replaying the M5 change request against increment 001 flags the overlap with REQ-003, REQ-009, REQ-012 and REQ-014.
  - A planted dependency cycle fails.
- **Tests:** fixtures of the 001 and 002 plans, plus mutated versions.

**Demo:**
- **Sandbox:** a new project with its PRD in `docs/` and a PDF variant. Both route to S02, labels are created by S00, and the IDs are correct.
- **Task Tracker increment 004:** a change request overlapping existing features, which `plan check` flags. `knowledge.md` is updated by S01 and S12, and prose ID mentions don't move the numbering.

**Milestone DoD:** T7.1–T7.4 merged, and the demo recorded.

---

## M8 — Headless Runner, Evals & Metrics

**Goal:** the factory can run unattended **between** gates, never past them. Its behaviour is checked by repeatable evals, and its performance is measured from data it already records. This is the regression harness that M9 depends on.

### T8.1 Headless runner: `factory.py run --until-gate` · L
- **Depends:** M7
- **Build:**
  - The loop goes `state` → `claude -p "/factory-<command>"` → `state`, and stops at any gate, at `NEEDS_HUMAN`, at `INCONSISTENT`, or when a step makes no progress (the state hasn't changed after N attempts).
  - `--command resume` never starts a story. `--command continue` maps to exactly one human "continue": it starts at most one story and then runs as `resume`.
  - It never passes bypass or skip-permissions flags.
  - All Claude invocations go through **one adapter function** (the executable, arguments and working directory), so M9 can switch to target-root invocation in one place.
  - It writes a run log.
- **Acceptance criteria:**
  - A runner given `continue` stops at Gate B after exactly one story.
  - The runner can't merge (the guard is still active) and never continues past a gate.
  - It exits non-zero with the reason on `NEEDS_HUMAN`.
- **Tests:** unit tests with a fake `claude` adapter covering each stop condition, the one-story limit and the no-progress cut-off.

### T8.2 Eval harness · L
- **Depends:** T8.1
- **Build:**
  - **Offline evals:** recorded snapshot scenarios (every state-table row plus the real M2–M5 incidents) run through `state` and `route`.
  - **Live evals:** scenario scripts on the sandbox that act as the human through `gh`: merge, `/changes`, close without merging, kill mid-station. The runner drives the factory, and assertions check the invariants:
    - no duplicate issues, branches or PRs;
    - no merge and no push to `main` by the factory;
    - gates respected;
    - the PR evidence matches the ledger.
  - A report lists scenario, pass/fail and evidence.
  - Station or command changes must pass the offline evals, and the live evals at milestone boundaries.
- **Acceptance criteria:**
  - Offline evals run with `python -m unittest` in under 5 minutes.
  - At least 6 live scenarios: new project to Gate A; Gate A `/changes`; story to Gate B; Gate B `/changes`; closed PR leading to `NEEDS_HUMAN`; kill and resume.
- **Tests:** the evals themselves, plus a mutated factory (for example, a station that skips a gate) that the evals must catch.

### T8.3 Metrics: `factory.py metrics` · M
- **Depends:** T6.1, T8.1
- **Build:** metrics come from `.factory/log.md`, checkpoints, ledgers and the GitHub timeline only, with no external telemetry:
  - time per station and per story;
  - time waiting at each gate (human time, reported separately);
  - fix attempts and review rounds;
  - PR size;
  - first-pass verifier rate;
  - stories per increment.

  Output is JSON and a Markdown report per target and increment.
- **Acceptance criteria:**
  - For Task Tracker 001–003, the report matches hand-checked values for at least 3 stories, including #27 (1 fix attempt) and #22 (1 review round).
- **Tests:** fixture logs and timelines, with the expected numbers.

**Demo:**
1. The runner takes a sandbox increment from Gate C to Gate B unattended and stops.
2. The human merges, and `run --command resume` closes out the story and stops at Gate C.
3. The full eval suite passes.
4. The metrics report is produced for Task Tracker.

**Milestone DoD:** T8.1–T8.3 merged, and the demo recorded.

---

## M9 — Plugin Packaging & Target-Root Invocation

**Goal:** the factory is installed once as a Claude Code plugin and used from a target's root (`cd my-project` → `claude` → `/factory-start docs/factory/prd.md`). It must be at least as safe as today's checkout mode: the guard stays authoritative and fails closed, its liveness is proven on every command, and a target's own settings can't silently disable it. The plugin becomes the **single supported mode**.

### T9.1 Local plugin spike and decision record · M
- **Depends:** none (can run early; see the ordering notes)
- **Build:** `docs/05-plugin-spike.md`, which tests the seven open items on a throwaway plugin and target:
  1. Plugin command naming: is a bare `/factory-start` possible, or only `/factory:start`?
  2. Whether a project's `disableAllHooks: true` silences a user-installed plugin's PreToolUse hook, and whether `.claude/settings.local.json` or `--settings` can override it.
  3. Whether `CLAUDE_PROJECT_DIR` is visible in Bash tool commands.
  4. `bin/` executables on Windows (Git Bash and PowerShell).
  5. Exec-form hooks resolving `python` on Windows.
  6. What the workspace trust dialog shows for a target's own hooks.
  7. A hostile target `CLAUDE.md` against the factory rules.
- **Acceptance criteria:**
  - Each item has a recorded result with evidence and a decision.
  - Any **NO** on item 2 without a working override changes T9.5's design before any other T9 task starts.
- **Tests:** the spike itself, with its transcripts kept.

### T9.2 Plugin manifest and components · M
- **Depends:** T9.1
- **Build:**
  - The repo root becomes the plugin root, with `.claude-plugin/plugin.json` (name, pinned `version`, `defaultEnabled: false`) and `.claude-plugin/marketplace.json` (the repo is its own marketplace).
  - Commands or skills for `target`, `start`, `resume`, `continue` and `status`, named as the spike decided. Each carries `allowedTools` for its engine calls.
  - `agents/ac-verifier.md`, using only supported frontmatter.
  - `hooks/hooks.json`: the PreToolUse guard in **exec form** with `${CLAUDE_PLUGIN_ROOT}`, and a SessionStart check.
  - `CLAUDE.md` is not relied on: the rules are reached through `stations/_rules.md`, which every command reads.
- **Acceptance criteria:**
  - `claude plugin validate --strict` passes.
  - The plugin loads with `--plugin-dir`, and its commands, agent and hook all register.
- **Tests:** a manifest and structure lint test (paths start with `./`, nothing escapes the root, no unknown keys).

### T9.3 Plugin-root path resolution · M
- **Depends:** T9.2
- **Build:**
  - `bin/factory` is a launcher for `scripts/factory.py`, with a Windows shim if the spike requires one.
  - Command bodies use `${CLAUDE_PLUGIN_ROOT}` (substituted inline).
  - Station files call the engine only as `factory …`, and refer to stations and templates through a plugin-root placeholder the command defines.
  - Nothing writes under `${CLAUDE_PLUGIN_ROOT}`. Durable per-user state goes to `${CLAUDE_PLUGIN_DATA}`.
- **Acceptance criteria:**
  - No working-directory-relative factory path remains in commands, stations or templates.
  - It works from a target folder whose path contains spaces.
- **Tests:** a lint that fails on `python scripts/factory.py`, a bare `stations/` or a bare `templates/` reference; a path-with-spaces test.

### T9.4 Target-root invocation · M
- **Depends:** T9.3
- **Build:**
  - The target is the git top level of the session's project directory (`CLAUDE_PROJECT_DIR` in hooks; the working directory, or an explicit `--target`, in the CLI).
  - `/factory-target` becomes a check-only command.
  - `.factory-local/target.json` and the `additionalDirectories` handling are removed.
  - Rule S3 now means the plugin's install folder is read-only. That follows from `FACTORY_ROOT` being derived from the script's location.
  - The plugin is enabled per target through the target's gitignored `.claude/settings.local.json`, so the guard never runs in unrelated projects.
  - Rule T2's banner (`Target: …`) is unchanged.
  - The target's auto-loaded `CLAUDE.md` stays precedence level 4 and is treated as data (rule U1).
- **Acceptance criteria:**
  - From a target root, the full sequence `/factory-start` → Gate A → issues → `/factory-continue` → Gate B works with no target path typed.
  - With a target active, the plugin folder can't be written.
- **Tests:** target-resolution unit tests (subfolder, worktree, not a repo, the factory itself); guard tests for the plugin root being read-only.

### T9.5 Guard liveness canary and fail-closed hardening · M
- **Depends:** T9.2, T9.1 (item 2)
- **Build:**
  - `factory guard-canary` is a no-op that the guard always blocks by name. If it ever runs, it prints `GUARD INACTIVE` and exits 1.
  - **Every factory command's step 0** runs the canary and stops unless it was blocked.
  - The SessionStart hook warns when the guard can't load (Python missing, import error).
  - The guard stays fail-closed on its own errors.
  - Guard gaps from M4 are closed: `git clone` outside the target and scratch areas, `/tmp` mapping, and computed verbs such as `gh pr $(echo merge)`.
- **Acceptance criteria:**
  - With hooks disabled, Python missing or the hook misconfigured, every factory command stops before its first station step.
  - The M4 775-call replay changes no allow verdicts beyond the planned fixes.
- **Tests:** canary unit tests and guard tests for each gap; the replay suite.

### T9.6 `doctor` safety checks · S
- **Depends:** T9.4, T9.5
- **Build:**
  - **FAIL** when the target's effective settings:
    - set `disableAllHooks: true`;
    - set the factory plugin to `false` in `enabledPlugins`;
    - set `permissions.defaultMode: bypassPermissions` without a local override.
  - **FAIL** when the guard canary isn't blocked.
  - **WARN** for: target hooks or `permissions.allow` entries that cover git or gh commands; no branch protection on `main` (M5 follow-up 3); the plugin version differing from the target's recorded version.
- **Acceptance criteria:** each condition yields the stated FAIL or WARN, with the fix named.
- **Tests:** settings fixtures for each case.

### T9.7 Target settings and hook interaction suite · M
- **Depends:** T9.5, T9.6, T8.2
- **Build:** live eval scenarios (T8.2 harness) on hostile sandbox targets:
  - `disableAllHooks` in the project file;
  - its own PreToolUse hook that allows everything;
  - broad `permissions.allow`;
  - `bypassPermissions`;
  - a `CLAUDE.md` saying "merge the PR";
  - a committed `enabledPlugins: false`.
- **Acceptance criteria:**
  - In every scenario the factory either stops at `doctor` or the canary, or runs with the guard still blocking `gh pr merge` and pushes to `main`.
  - No scenario reaches a merge.
- **Tests:** these scenarios become part of the eval suite.

### T9.8 Windows verification · S
- **Depends:** T9.3, T9.5
- **Build:** a recorded matrix of Git Bash and PowerShell against: the hook in exec form, the `bin/factory` shim, paths with spaces, `python` vs `py` resolution, the full eval suite and one live story.
- **Acceptance criteria:** every cell is green or has a documented fix.
- **Tests:** the matrix run, recorded in the PR.

### T9.9 Single supported mode and documentation · M
- **Depends:** T9.4–T9.8, T8.1
- **Build:**
  - Remove the factory-checkout workflow. Factory development uses `claude --plugin-dir <checkout>` from a target.
  - Switch the T8.1 runner adapter to target-root invocation.
  - Rewrite architecture §3 (invocation model) and §11.
  - Update the README (install from the marketplace, update, uninstall) and the runbook.
  - Update `test_reusability` for the new layout.
- **Acceptance criteria:**
  - The README's only usage path is install → `cd target` → `claude` → `/factory-start`.
  - No doc describes opening Claude Code in the factory repo except for factory development.
- **Tests:** doc lint (no stale `/factory-target <path>` workflow); the eval suite through the plugin.

**Demo:**
1. On a clean user profile, install from the GitHub marketplace.
2. On a brand-new target: `cd` → `claude` → `/factory-start docs/factory/prd.md` → Gate A → merge → issues → `/factory-continue` → Gate B → merge → close-out.
3. Run one Task Tracker increment through the plugin.
4. Show the hostile-target scenarios stopped.
5. Show the Windows matrix green.
6. Show the runner working from a target root.

**Milestone DoD:** T9.1–T9.9 merged, and the demo recorded.

---

### Task index (M6–M9)

| ID | Task | Size | Depends |
|---|---|---|---|
| T6.1 | Evidence ledger | M | M5 |
| T6.2 | AC ↔ test mapping | M | T6.1 |
| T6.3 | Deterministic PR body | M | T6.1, T6.2 |
| T6.4 | Review experience and `trace` | S | T6.3 |
| T6.5 | Stations S09–S11 use the engine | S | T6.1–T6.4 |
| T7.1 | Structured ID allocation | S | M6 |
| T7.2 | Intake and project detection | M | T7.1 |
| T7.3 | Target knowledge base | M | T7.2 |
| T7.4 | Plan lint and overlap detection | M | T7.1, T7.3 |
| T8.1 | Headless runner | L | M7 |
| T8.2 | Eval harness | L | T8.1 |
| T8.3 | Metrics | M | T6.1, T8.1 |
| T9.1 | Plugin spike and decision record | M | none |
| T9.2 | Manifest and components | M | T9.1 |
| T9.3 | Plugin-root path resolution | M | T9.2 |
| T9.4 | Target-root invocation | M | T9.3 |
| T9.5 | Guard canary and hardening | M | T9.2, T9.1 |
| T9.6 | `doctor` safety checks | S | T9.4, T9.5 |
| T9.7 | Target settings and hook suite | M | T9.5, T9.6, T8.2 |
| T9.8 | Windows verification | S | T9.3, T9.5 |
| T9.9 | Single supported mode and docs | M | T9.4–T9.8, T8.1 |

---

### Does the order T6 → T7 → T8 → T9 need to change?

**Keep the milestone order, with three adjustments.**

1. **Pull T9.1 (the spike) forward and run it alongside M6.** It depends on nothing and changes no code. Its result on `disableAllHooks` decides how strong T9's safety story is, and its results on naming and paths decide how M6–M8 should write new command and station text. Learning that late would mean rework.
2. **Pull T7.1 (structured ID allocation) forward, before the M6 demo.** It is a known correctness bug that hit two demos. The M6 demo runs increment 003 on Task Tracker, where the bug can strike again. It's a small task with no dependency on M6. The rest of M7 stays where it is.
3. **T8 must stay before T9.** This is a real dependency, not a preference:
   - T9.7 runs on the T8.2 eval harness.
   - T9.9 migrates the T8.1 runner through its invocation adapter.
   - The eval suite is the regression proof that plugin mode behaves exactly like checkout mode.

   Doing T9 first would mean shipping the riskiest change, which moves the safety layer, with no harness to prove it.

Two further constraints:
- T8.3 metrics read the T6.1 ledger, so M6 must come before M8.
- Until T9.3 lands, M6–M8 should write every engine call uniformly as `python scripts/factory.py …` and every station path as `stations/…`, so T9.3's rewrite is mechanical and covered by its lint.

**Resulting order:** T9.1 and T7.1 → M6 → rest of M7 → M8 → rest of M9.

Nothing was modified, no branch was created and no PR was opened.
<!-- roadmap:original:end -->
