# Factory build progress

Milestone demo records, as required by the milestone Definition of Done in [03-factory-plan.md](03-factory-plan.md) §3: *"all tasks in the milestone are merged, **and** the milestone demo … has been run and its result recorded in `docs/progress.md`."*

---

## M1: State engine and safety core

| | |
|---|---|
| **Demo run** | 2026-09-24 |
| **Target** | `Nandan-krishnamurthy/factory-sandbox` (empty, disposable; prerequisite P2), cloned into the session scratch directory |
| **Factory code** | branch `task/T1.8-state-planning` (PR #10), which contains T0.1–T1.7 (merged) plus T1.8 |
| **Result** | ✅ **All demo steps passed.** One small issue was found and fixed (below). |

### Tasks
| Task | PR | Status |
|---|---|---|
| T0.1 Initialise the factory repo | (direct initial commit) | merged |
| T0.2 Python skeleton and test runner | #1 | merged |
| T0.3 `CLAUDE.md` and `_rules.md` | #2 | merged |
| T1.1 `gh.py`/`git.py` I/O layer + FakeGh | #3 | merged |
| T1.2 Config and target handling | #4 | merged |
| T1.3 Markers module | #5 | merged |
| T1.4 `doctor`, `labels ensure` | #6 | merged |
| T1.5 `comment` subcommand | #7 | merged |
| T1.6 Guard hook and settings.json | #8 | merged |
| T1.7 `signals.py` (single-account) | #9 | merged |
| T1.8 State reconciler, planning states | #10 | merged. **M1 is complete.** |

### Demo steps and results (plan §M1)

**1. `target set` → `doctor` → `labels ensure` → `state`**

| Command | Result |
|---|---|
| `factory.py target set <scratch>/sandbox` | ✅ `Target: …\scratchpad\sandbox (Nandan-krishnamurthy/factory-sandbox)`. It wrote `.factory-local/target.json` and `permissions.additionalDirectories`, and Claude Code picked up the added directory straight away. |
| `factory.py doctor` | ✅ `Doctor PASSED: 0 failed, 2 warning(s).` The two warnings are expected for an empty, unconfigured repo: `config` (no `.factory/config.json` yet) and `branch protection` (repo is empty). |
| `factory.py labels ensure` | ✅ `Labels: 0 created, 0 updated, 9 unchanged.` Idempotent; the labels had been created by the T1.4 integration run. |
| `factory.py state` | ✅ **`State: UNCONFIGURED`**, waiting on human, allowed `/factory-start, /factory-status`, "No increment has been started. Run /factory-start." |
| `factory.py state --json` (stdout only) | ✅ Pure JSON, `"state": "UNCONFIGURED"`, schema 1; the banner went to stderr. |

**2. Post a factory comment and a checkpoint** (on throwaway sandbox issue #2)

| Command | Result |
|---|---|
| `factory.py comment --issue 2 --kind reply --body-file -` | ✅ Comment created, stored by GitHub as `<!-- factory:reply -->` followed by the text. |
| `factory.py comment --issue 2 --kind checkpoint --station S08 --next S09` (no `--sha`) | ✅ Refused with `error: the target has no commits; pass --sha` (the sandbox has no commits yet). *This is where the ordering issue below was found.* |
| Checkpoint `S08→S09`, then `S09→S10`, with `--branch story/0-m1-demo --sha 0000000` | ✅ `created checkpoint comment`, then `updated checkpoint comment`, **same comment id**. The issue ends with exactly 2 comments (1 reply + 1 checkpoint), both marked. |

**3. Attempt a merge and a push to `main`; the guard must block both**

Each attempt was deliberately written so that it does **not** match a `permissions.deny` rule, leaving the guard as the only thing that could stop it. The merge targeted a PR number that doesn't exist (#999), so nothing could have been merged even if the guard had failed.

| Attempted tool call | Result |
|---|---|
| `cd <sandbox> && gh pr merge 999 --repo Nandan-krishnamurthy/factory-sandbox --squash` | ✅ **Blocked by the live hook:** `Blocked by the factory guard: \`gh pr merge\` is not allowed: the human merges (D1, rule S1)` |
| `git -C <sandbox> push origin HEAD:main` (pre-approved by the `git -C` allow rule) | ✅ **Blocked by the live hook:** `Blocked by the factory guard: the factory must never push to the default branch 'main'; changes reach it only when the human merges a PR (rules S1, D1)` |
| *(extra)* `Write docs/progress.md` in the factory repo while the target was active | ✅ **Blocked:** `the factory repo is read-only while a target is active (rule S3, D4)`. This record was therefore written after the target was deactivated. |

### Issue found and fixed
- **The `Target:` banner could print *after* an error message.** When stdout is a pipe it is buffered, but stderr isn't, so in step 2 the `error:` line appeared before the banner. Rule T2 says the banner comes first.
- **Fix (PR #10):** `cli.py` flushes the banner immediately.
- **Regression test:** `BannerOrderTest` runs the real CLI with stdout piped and stderr merged into it. It **fails without the fix**, reproducing the demo output exactly, and passes with it.

### Cleanup
- Sandbox issue #2 closed. The 9 factory labels stay on the sandbox (intended).
- The target was deactivated: the gitignored `.factory-local/target.json` and `.claude/settings.local.json` were removed (neither existed before the demo), and `factory.py target show` now reports no active target.
- Nothing was merged and nothing was pushed to `main` in any repo.

### Observations for later tasks
- In an empty target, `comment --kind checkpoint` can't default `--sha` (there is no HEAD), and `--branch` defaults to `main`. Real checkpoints run after S07 has created and pushed a story branch, so this only affects empty repos, but the S07+ stations (T3.3) should always pass `--branch` explicitly.

---

## M2: Planning pipeline

| | |
|---|---|
| **Demo run** | 2026-09-25 |
| **Target** | `Nandan-krishnamurthy/task-tracker-factory-test` (fresh repo; prerequisite P3), cloned at `C:\Projects\task-tracker-factory-test` |
| **Input** | The Task Tracker PRD, supplied as `Task Tracker.pdf` (5 pages) |
| **Factory code** | `main` at d8d55b0 (T2.1–T2.5 merged) through Gate A; `main` at d7b8a3f (plus the fix in PR #17) for issue creation |
| **Result** | ✅ **Run end to end, except the `/changes` revision step.** `/factory-target` → `/factory-start` → S00 → S02 → S03 → S04 → S05 → **Planning PR [#1](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/pull/1)** → human merge → `/factory-resume` → S05b → **12 issues (#2–#13)** → stop at **`IDLE_AT_GATE_C`** ("say continue"). The human accepted the plan without feedback, so the plan's "comment `/changes` → `/factory-resume` revises the PR" step (`GATE_A_CHANGES`, S05 revision mode) was **not exercised** and is still unproven. Five factory problems were found: one is fixed (PR #17) and four are open (below). |

### Tasks
| Task | PR | Status |
|---|---|---|
| T2.1 Templates | #11 | merged |
| T2.2 Stories parser and `issues sync` | #12 | merged |
| T2.3 Increment handling | #13 | merged |
| T2.4 Station files S00, S02–S05, S05b | #14 | merged |
| T2.5 Planning commands | #15 | merged |

### Demo steps and results

**0. Pre-check**
- First attempt (2026-09-24): the GitHub repo was empty (`isEmpty: true`, no default branch). The factory stopped without creating or pushing anything. The human pushed an initial commit (`99e0ddf`) and copied the PDF in.

**1. `/factory-target C:\Projects\task-tracker-factory-test`**

| Step | Result |
|---|---|
| `target set` | ✅ `Target: C:\Projects\task-tracker-factory-test (Nandan-krishnamurthy/task-tracker-factory-test)` |
| `doctor` | ❌ `Doctor FAILED: 1 failed, 2 warning(s)`. `labels` FAIL: none of the 9 factory labels existed. *Problem 1.* |
| `labels ensure` (doctor's own fix) | ✅ `Labels: 9 created, 0 updated, 0 unchanged.` |
| `doctor` again | ✅ `Doctor PASSED: 0 failed, 2 warning(s)`: `config` (expected before S00) and `branch protection` (advice; the factory never changes it, rule S5) |
| `state` | ✅ `UNCONFIGURED`; allowed `/factory-start, /factory-status` |

**2. `/factory-start "Task Tracker.pdf"`: S00 Intake**

| Step | Result |
|---|---|
| `route --command factory-start` | ✅ `run S00` |
| Increment | ✅ `increment next` gave `001-initial`, `REQ-001`, `STORY-001` |
| `00-prd.md` | ⚠️ S00 says to copy the requirements file unchanged, which cannot be done with a PDF. *Problem 3.* The text was extracted (`pdftotext`, cross-checked with `pypdf`) and transcribed word for word, with tables restored as Markdown and a header comment naming the PDF as the source of record. No secrets found. |
| Checkpoint | ✅ `S00: intake for 001-initial` pushed to `factory/plan-001-initial` |
| Done check | ❌ `state` reported `next_station: S01`, which is not available until M5. The S00 stop condition and `route` (`action: stop`) both stopped the run correctly. *Problem 2.* The human moved the PDF to `docs/factory/Task Tracker.pdf` on `main` (1e32681). |

**3. `/factory-resume`: S02 → S05**

| Station | Output | Done check |
|---|---|---|
| S02 Requirements | `02-requirements.md`: REQ-001..REQ-021 (15 functional, 6 non-functional), 11 assumptions, 6 non-blocking open questions | ✅ all 22 PRD headings have a coverage row; numbering consecutive from REQ-001; `state` → S03 |
| S03 Architecture | `03-architecture.md`: layered plain TypeScript + Vite, `localStorage` write-through, 10 key decisions, 6 dev dependencies each with a reason | ✅ 21/21 REQs mapped, no extras; `state` → S04 |
| S04 Plan | `04-implementation-plan.md`: M1 (walking skeleton + capture) … M6 (accessibility/performance audit) | ✅ 21/21 REQs covered; M1 starts with the walking skeleton; `state` → S05. *Problem 4* was found here and corrected in a second S04 commit. |
| S05 Stories + PR | `05-stories.md`: STORY-001..STORY-012, 3–5 ACs each; `docs/factory/traceability.md` with 21 rows; Planning PR #1, labelled `factory:planning` | ✅ `issues sync --dry-run` exit 0 (`12 to create, 0 already exist`), embedded unedited; every REQ traced and in the matrix; exactly one open PR carrying the `factory:planning increment=001-initial` marker; `state` → **`GATE_A_WAITING`**, and `route` → `stop` |

Every factory commit carries its `Factory-Station:` trailer (S00, S02, S03, S04, S04, S05). The guard also blocked a `$VAR` path in a shell command (`cannot tell where '$T/.factory/log.md' points`). That is working as designed; the command was re-run with a literal path.

**4. Gate A: the human reviewed Planning PR #1, accepted the assumptions, and merged it** with a normal merge commit (2a5a64e). No `/changes` round was held.

| Step | Result |
|---|---|
| `/factory-target` → `state` | ❌ **`INCONSISTENT`**: "commit e2babf0 … c6b13c2 on 'main' was made by the factory but did not arrive through a merged PR" (all 6 planning commits). `route` → `stop`, so nothing was changed. *Problem 5.* |
| Fix | Factory PR **#17** (merged): invariant 4 now accepts commits on the branch side of a `web-flow` merge commit. It includes a regression test built from this exact history, which fails without the fix. |
| `/factory-target` → `state` again | ✅ `ISSUES_PENDING` (increment `001-initial`), next station S05b, "12 story issue(s) to create." Doctor passed with 1 warning (branch protection). |

**5. `/factory-resume`: S05b Create issues**

| Step | Result |
|---|---|
| Preconditions | ✅ merged Planning PR `[{"number":1}]`; clean working tree; `switch main` + `pull --ff-only` fast-forwarded to 2a5a64e |
| `issues sync --dry-run` | ✅ `12 to create, 0 already exist`, identical to the dry run approved in PR #1 |
| `issues sync` | ✅ `Done: 12 created, 0 already existed.` Issues #2–#13 were created in dependency order, labelled `factory:story` + `status:ready`, with the `factory:story` marker, and `Blocked by` translated (for example, STORY-009 → `#7, #9`) |
| Local planning branch | ✅ `Deleted branch factory/plan-001-initial (was e2babf0).` |
| Summary reply | ✅ posted with `factory.py comment --pr 1 --kind reply` ([comment](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/pull/1#issuecomment-5830878223)); only #2 (STORY-001) is unblocked |
| Done check | ✅ dry run `0 to create, 12 already exist`; `state` → **`IDLE_AT_GATE_C`**, "12 story(ies) ready. Say continue (/factory-continue) to start the next one."; `route` → `stop` |

No story was started (rule S2).

### Problems found
1. **S00 cannot pass on a brand-new repo.** Step 1 stops on any `doctor` FAIL, but step 2 (`labels ensure`) is what fixes the `labels` FAIL. *Fix:* run `labels ensure` before `doctor` in S00, or make `labels` a WARN in `doctor` until S00 has run.
2. **A PDF counts as existing code.** `collect_snapshot` in `state.py` treats every file on the default branch outside `docs/factory/`, `.factory/` and README/LICENSE/.gitignore as code, so a repo holding only a README and a PDF is routed to S01. *Fix* (fits T5.2's existing-project detection): only count source or build files, or ignore documents (`*.md`, `*.pdf`, `docs/**`).
3. **S00 assumes a Markdown requirements file.** "Copy unchanged to `00-prd.md`" has no rule for PDF or other formats. *Fix:* S00 converts non-Markdown input to faithful Markdown with a source header (as done here), or asks for Markdown.
4. **Forward references use up IDs.** `scan_layout` in `increments.py` counts every `STORY-###`/`REQ-###` mentioned in any file under `docs/factory/`. S04's plan mentioned "STORY-001" before S05 had allocated it, so `next_story` became STORY-002. It was caught before any story was written, and the plan was reworded. *Fix:* S04 (and S02/S03) must not name STORY IDs, or the scanner counts only story headings, issue markers and PR bodies.
5. **✅ Fixed (PR #17): a normal merge commit broke invariant 4.** The check trusted a `Factory-Station:` commit on `main` only if `web-flow` committed it. That is true for squash and rebase merges, but a merge commit keeps the branch commits' own committer. `state.direct_factory_commits()` now also accepts commits brought in by a `web-flow` merge commit, and still flags local merges and direct pushes.

Problems 1–4 are still open and are candidates for follow-up tasks.

### Observations
- The `Target: <local path>` banner is part of `issues sync` stdout, so the dry-run block in the (public) Planning PR shows the local path `C:\Projects\…`. Harmless, but the banner could go to stderr for this command, as `state --json` already does.
- No page renderer (`pdftoppm`) is installed, so the PDF was checked through two text extractions, not visually.
- At `IDLE_AT_GATE_C`, `state --json` lists all 12 issues under `details.ready`, because they all carry `status:ready`. Only #2 is actually unblocked. S06's pick (T3.1) must apply the unblocked rule rather than trust this list.
- Deactivating the target to write in the factory repo means `/factory-target` must be run again before the next factory command. This happened twice during the demo. It follows from rule S3 and is expected, but a runbook note (T5.4) would help.

### Cleanup and hand-off
- The target was deactivated to write this record (rule S3): the gitignored `.factory-local/target.json` and `.claude/settings.local.json` were removed.
- The factory never merged anything or pushed to `main` in any repo. The target's history was not rewritten. Its `main` changed only through the human's commits and the human's merge of PR #1.
- The factory is stopped at **Gate C**. M3 (the story loop) was not started.
- **Still to prove from the M2 demo:** the `/changes` → `/factory-resume` revision round (S05 revision mode). It can be exercised on the next Planning PR, in M5's increment 002, or on a throwaway planning increment.
