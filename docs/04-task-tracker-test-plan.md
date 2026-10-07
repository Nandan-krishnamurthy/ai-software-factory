# 04 — Task Tracker test plan (runbook)

A step-by-step runbook for proving the MVP's **success criteria 1–8** ([requirements §14](01-factory-requirements.md)) on real repositories. Each criterion has its preconditions, the exact steps, the expected result, and what to record. Results go into [progress.md](progress.md), under the milestone that ran them.

## Targets

| Target | Repo | Local clone | Used for |
|---|---|---|---|
| **Task Tracker** | `Nandan-krishnamurthy/task-tracker-factory-test` | `C:\Projects\task-tracker-factory-test` | Criteria 1–7: the project the factory built from its PRD (increment `001-initial`), and then changes (increment `002-…`) |
| **Sandbox** | `Nandan-krishnamurthy/factory-sandbox` | `C:\Projects\factory-sandbox` | Criterion 8 (a second target), the reject path, and anything destructive |

Task Tracker is a TypeScript + Vite web app tested with Vitest and Playwright. None of that is known to the factory: it lives only in the target's `.factory/config.json` and `docs/factory/` (criterion 8).

## Before every session

1. Open Claude Code in the **factory** folder, on an up-to-date `main` (`git pull --ff-only`).
2. `/factory-target <clone>`. `doctor` must show no `FAIL`. The `branch protection` `WARN` is advice.
3. `/factory-status`. Its first line says what to do next. Check that it matches what you expect before running anything else.
4. After working on the factory itself, deactivate the target again: delete `.factory-local/target.json` and `.claude/settings.local.json` (see the [README](../README.md#working-on-the-factory-itself)).

**Evidence** is always real: links to PRs and issues, commit SHAs, the exact `Suite:` and test-count lines, and the state reported. Never a prediction (rule H1).

## Status at a glance

| # | Criterion | How it is proven | Status |
|---|---|---|---|
| 1 | New project: Planning PR, issues, ≥ 3 stories, tests green on `main` after each merge | Increment `001-initial` | ✅ M2 + M4 and increment 001: Planning PR #1, issues #2–#13, **12 stories** merged (PRs #14–#25) |
| 2 | Existing project: Codebase Discovery, then ≥ 1 story that follows existing conventions | Increment `002-…` (M5 demo) | ⏳ To run |
| 3 | Resume (a) during implementation, (b) at Gate B, (c) approved but not merged | Kill and restart sessions | ✅ (a), (b) in M4. (c): see §3, to run |
| 4 | Gates respected: never merges, never starts a story without `continue` | Every run, plus the checks in §4 | ✅ M4, re-checked in §4 |
| 5 | Rework: `/changes` → every comment addressed on the same PR | Task Tracker PR #22 | ✅ M4 step 3 |
| 6 | Traceability: a merged line → PR → issue → REQ → PRD section, in under a minute | Timed walk | 🟡 Chain verified, not yet timed |
| 7 | Reviewability: a PR reviewable in ~15 min; AC evidence accurate; no false "tests passed" | Review log over the story PRs | 🟡 Evidence on every PR; review times not recorded |
| 8 | Reusability: nothing Task Tracker-specific in the factory; one checkout, two targets | `tests/test_reusability.py` plus §8 | ✅ T5.4 (this runbook's PR) |

---

## 1. New project

**Goal:** from the PRD alone to a merged Planning PR, issues, and at least 3 stories delivered through PR → your merge → `continue`, with tests passing on `main` after each merge.

**Preconditions:** an empty GitHub repo with one commit on `main` (for example a README), cloned locally. The PRD is a file *outside* `docs/` of the target, or under `docs/factory/`.

**Steps**
1. `/factory-target <clone>`, then `/factory-start <prd-file>`.
   - Expect: S00 → S02 → S03 → S04 → S05, no S01 (a new project), and a Planning PR. The state is `GATE_A_WAITING`.
2. Review the Planning PR, then merge it yourself.
3. `/factory-resume`.
   - Expect: S05b creates one issue per story, then `IDLE_AT_GATE_C`.
4. `/factory-continue`.
   - Expect: one story, S06 → S11, a PR with an AC verdict, then `GATE_B_WAITING_REVIEW`.
5. Merge the PR. Then `/factory-continue`.
   - Expect: S12 close-out of that story, then the next story to its PR.
6. Repeat step 5 until at least 3 stories are merged.
7. After each merge, on an up-to-date `main` of the target, run the full test suite from `.factory/config.json` (`commands.test`).

**Record:** the Planning PR, the issue range, and each story PR with its `Suite:` line; the test result on `main` after each merge.

**Done:** M2 (planning, Planning PR #1, issues #2–#13) and M4 plus the rest of increment 001 (stories #2–#13 through PRs #14–#25, all merged by the human). On `main` at `e691d55`: `npm test` gives 107 unit and 65 end-to-end tests passing (recorded in the M5 verification report, 2026-10-07).

---

## 2. Existing project (the M5 demo)

**Goal:** starting from the Task Tracker repo plus a **new change request**, the factory runs Codebase Discovery (S01) and delivers at least one story that follows the existing conventions.

**Preconditions**
- Task Tracker is `INCREMENT_COMPLETE`. `/factory-status` says "Increment 001-initial is complete: run /factory-start <change-request>".
- The target's working tree is clean, on an up-to-date `main`.
- A short change request, kept **outside** the target repo (for example `C:\Projects\task-tracker-cr-002.md`). It should be small (2–4 stories) and touch existing code. For example: "Search tasks by title", or "Tag tasks and filter the list by tag".

**Steps**
1. `/factory-target C:\Projects\task-tracker-factory-test`, then `/factory-status`.
2. `/factory-start C:\Projects\task-tracker-cr-002.md`. Expect, in order:
   - **S00:** increment **`002-<slug>`** (not `001-…`) and branch `factory/plan-002-<slug>`.
   - **S01:** `docs/factory/increments/002-<slug>/01-codebase-analysis.md`, with:
     - a `## Commands` row for each of the five commands, each with its evidence or `null`. For Task Tracker: `install`, `build`, `typecheck` and `test` come from `.factory/config.json`, and `lint` is `null`, because no lint script exists;
     - a `## Baseline` that says `Green`.
   - **S02/S03:** the **delta** templates. `02-requirements.md` has `## Current system`, `## Changed or retired requirements` and `## Unchanged behaviour to protect`, and its new requirements start at **REQ-022**. `03-architecture.md` has `## Current architecture`, `## Changes` and `## Compatibility and migration`.
   - **S04/S05:** stories numbered from **STORY-013**, and a Planning PR. The state is `GATE_A_WAITING`.
3. *Optional, and recommended, because it is still unproven:* exercise the Gate A revision round. Comment `/changes` on the Planning PR with one point, then `/factory-resume`.
   - Expect: `GATE_A_CHANGES` → S05 revision mode → a reply to your point → `GATE_A_WAITING` again.
4. Merge the Planning PR. Then `/factory-resume`.
   - Expect: issues for the new stories, then `IDLE_AT_GATE_C`.
5. `/factory-continue`.
   - Expect: one story to a PR.
   - **Check the conventions:** code in the existing layout (`src/domain`, `src/app`, `src/ui`); unit tests next to the code (`*.test.ts`) and end-to-end tests in `tests/e2e/*.spec.ts`; tests named `#<issue> AC<n>: …`; no new dependency without a "New dependencies" line; and no existing test weakened.
6. Merge the story PR. Then `/factory-resume`.
   - Expect: S12 close-out, then Gate C.

**Red-baseline variant** (optional, on the sandbox or a scratch branch, never on Task Tracker's `main`): make one test fail on the default branch, then `/factory-start` a change request.
- Expect: S01 commits nothing and opens an issue labelled `factory:needs-human` ("Baseline is red for increment …"). The state is `NEEDS_HUMAN`, and every command stops.
- Either fix the test on the default branch, or reply `/accept-baseline` on the issue. Then remove the label and run `/factory-resume`: S01 runs again.

**Record:** the increment name; S01's commands table and baseline; the first REQ and STORY numbers; the Planning PR; the story PR and its verdict; and how the story follows the conventions (file paths and test names).

---

## 3. Resume after a session ends

**Goal:** when a session is stopped at each of these points, a new session reports the correct state and finishes the story with **no duplicate issues, branches or PRs**.

**Steps:** for each point below, stop the session as described, start a new one, and compare what the factory reports and does with the expected result.

| Point | Steps | Expect | Status |
|---|---|---|---|
| (a) During implementation | `/factory-continue`. While S08 runs, close the session. Open a new one: `/factory-target`, `/factory-resume`. | `STORY_IN_PROGRESS`, next S08, from the S07 checkpoint. The same branch, one PR, one commit per station, one checkpoint comment. | ✅ M4 step 1 (#11, PR #23) |
| (b) Waiting at Gate B | Stop at Gate B. Close the session and open a new one. `/factory-target`, `/factory-resume`. | `GATE_B_WAITING_REVIEW`; the route stops and nothing changes. | ✅ M4 step 2 (PR #22) |
| (c) Approved, not merged | **Single-account mode** (the MVP): your merge *is* the approval (D5), so "approved but not merged" is a PR at Gate B that you have commented on without `/changes`. Comment a remark (no `/changes`), close the session, open a new one, then `/factory-status` and `/factory-resume`. | `/factory-status` shows `Hint: PR #N has 1 comment from you in this round but no /changes…`. `/factory-resume` stops at Gate B and changes nothing. After you merge: S12, then Gate C. | ⏳ To run (in the M5 demo, on the story PR) |

In bot mode, a GitHub approval gives `GATE_B_APPROVED_UNMERGED`. That mode is not implemented in the MVP.

**Check for duplicates** after each restart:
- `gh pr list --repo <R> --head <branch> --state all`: exactly one PR;
- `git -C <clone> ls-remote --heads origin "story/<I>-*"`: exactly one branch;
- exactly one checkpoint comment on the issue.

---

## 4. Gates respected

**Goal:** the factory never merges a PR and never starts a story without `continue`, including when it is resumed after a merge.

**Checks** (run them at the end of each milestone):
1. **Every merge was yours.** `gh pr list --repo <R> --state merged --json number,mergedBy --jq '.[] | "\(.number) \(.mergedBy.login)"'` lists only your login, and the factory's commands never include a merge. The guard blocks `gh pr merge` and merges via the API in any spelling (`tests/test_guard.py`).
2. **No direct pushes to the default branch.** The state engine's invariant 4: `python scripts/factory.py state` never reports `INCONSISTENT` with "did not arrive through a merged PR".
3. **No story without `continue`.** After a merge, `/factory-resume` closes out and stops at Gate C without picking a story (M4 step 4). Only `/factory-continue` runs S06 (`tests/test_commands.py`).

**Expect:** every merge is by your login; the state is never `INCONSISTENT` for a direct push; and no story issue was labelled `status:in-progress` except right after a `/factory-continue`.

**Done:** M4 steps 4 and 5, and the whole of increment 001: all 13 PRs on Task Tracker (#1 and #14–#25) were merged by the human (`mergedBy` checked on 2026-10-07).

---

## 5. Rework

**Goal:** a PR receives `/changes`, and the factory addresses every comment on the same PR.

**Steps:** at Gate B, comment `/changes` with two numbered points, then `/factory-resume`.

**Expect:**
- `GATE_B_CHANGES_REQUESTED`, then S08 in rework mode → S09 → S10 → S11 on the same branch and PR;
- one marked reply per feedback item, and a "Rework round 1 done" comment;
- `review_round` is 1, and the issue is back to `status:in-review`.

**Done:** M4 step 3 (PR #22: both points addressed, a new regression test, and replies to each point).

---

## 6. Traceability

**Goal:** for any merged line of code, a reviewer can follow PR → issue → REQ → PRD section in **under a minute**.

**Steps** (start a stopwatch at step 1):
1. Pick any line in a file on `main`. Use `git blame -L <n>,<n> <file>` to get its commit.
2. Find the PR that merged it:
   - `gh pr list --repo <R> --state merged --search <sha>`;
   - or on GitHub, the commit page shows its PR;
   - or `git log --merges --ancestry-path <sha>..main --oneline | tail -1`.
3. The PR body says `Closes #<I>` and lists `Requirements: REQ-…`.
4. Issue `#<I>` has **Traces to:** `REQ-…`.
5. In `docs/factory/increments/<inc>/02-requirements.md`, each `REQ-###` names its source as `(PRD §<section>)`. Find that heading in `00-prd.md`.
6. Stop the stopwatch.

`docs/factory/traceability.md` gives the same chain in one table (REQ → stories → PRs → tests).

**Expect:** each hop is found from the previous one without searching the repo, and the whole walk takes **under 60 seconds**.

**Record:** the line, each hop, and the time. Repeat for 3 lines from different increments.

**Status:** the chain was verified on 2026-10-07: the `DATE_FORMAT` line in `src/ui/render.ts` → commit `3469b7c` → PR #25 → issue #13 (STORY-012) → REQ-019 → PRD §Non-functional requirements "Performance". It has not been **timed** yet; do that in the M5 demo, including a line from increment 002.

---

## 7. Reviewability

**Goal:** a typical PR is reviewable in about 15 minutes, and the AC evidence is accurate: no false "tests passed" claims.

**Steps:** for each story PR you review, record:
- **Review time:** from opening the PR to your decision.
- **Size:** the diff size, against `limits.max_diff_lines` (400) in the config.
- **Spot check:** pick one `pass` line in the AC verification and run the test it names on the PR branch. It must pass. Also check that the `Suite:` line matches a real run of `commands.test`.
- **Honesty:** any claim that turned out false. The target is none.

**Expect:** a typical review takes about 15 minutes or less; every spot-checked `pass` really passes; and no false "tests passed" claim is found.

**Status:** every story PR of increment 001 carries the independent AC verifier's per-criterion verdict and the real suite counts. Review times have not been recorded; start with the increment 002 story PR(s).

---

## 8. Reusability

**Goal:** nothing in the factory is specific to Task Tracker. Every project-specific value is in the target's `.factory/config.json` or `docs/factory/`, and the same factory checkout is pointed at two different targets without any change to factory code.

**Steps**
1. **The audit:**
   - `python -m unittest tests.test_reusability`. It fails on Task Tracker-specific strings (the project's name, owner, paths, domain examples or stack names) anywhere in `scripts/`, `stations/`, `.claude/` or `templates/`. Node.js names are allowed only in multi-stack Codebase Discovery, which must also name Python, Go, Rust and Make.
   - Manual cross-check: `git grep -n -i -E "task.?tracker|vite|vitest|playwright|typescript|npm" -- scripts stations .claude templates`. The only hits are the discovery files.
2. **One checkout, two targets:**
   1. `git status --porcelain` in the factory prints nothing. Note `git rev-parse HEAD`.
   2. `/factory-target C:\Projects\factory-sandbox`, then `python scripts/factory.py doctor` and `python scripts/factory.py status`.
   3. `/factory-target C:\Projects\task-tracker-factory-test`, then `doctor` and `status` again.
   4. `git status --porcelain` in the factory still prints nothing, and `HEAD` is unchanged. Only the gitignored `.factory-local/target.json` and `.claude/settings.local.json` changed.

**Expect:** each target reports its own repo, config, reviewers and state. No factory file changes.

**Record:** the two `doctor` and `status` outputs, and the factory's `HEAD` and `git status` before and after.

**Done:** T5.4. The audit test is in `tests/test_reusability.py` (it also checks that switching targets writes only the gitignored files), and the live two-target check is recorded in the T5.4 PR.

---

## Recording results

For each run, add to [progress.md](progress.md), under the milestone:
- the date, targets and factory commit;
- one row per step, with its result and evidence;
- any problem found: what happened, and the fix or follow-up.

A milestone is done only when its tasks are merged **and** its demo has been run and recorded (plan §3).
