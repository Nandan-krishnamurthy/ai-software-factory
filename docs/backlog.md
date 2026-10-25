# Backlog

| | |
|---|---|
| **Status** | Living record, updated by the PR that adds, changes or resolves an item |
| **Scope** | Known gaps, unresolved issues, deferred work and accepted limitations, from M6 onwards, plus the earlier findings the M6–M9 roadmap assigned to tasks |
| **Related** | [task-log.md](task-log.md) (what each task decided), [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md) (specifications), [progress.md](progress.md) (milestone records) |

This is the backlog that [03-factory-plan.md](03-factory-plan.md) §5 refers to ("new findings go to a `docs/backlog.md`").

**Items.** Each has:
- an ID (`B-NN`), which is never reused;
- a source;
- a verification status:
  - **verified**: stated in a merged PR, a committed document, the code, or a test;
  - **analysis**: identified from the committed station text but not yet decided;
  - **observed**: seen once, not yet reproduced by a test;
- an owner: the task named by the roadmap or a decision, or **unassigned**;
- a state: **open**, **resolved** (with the PR that resolved it), or **accepted** (a known limitation, kept on purpose).

**Rules.**
- An item is never deleted; it is marked resolved or accepted.
- Recording an item here does not decide it. Decisions are made in the owning task and recorded in [task-log.md](task-log.md).

---

## T6.5: station wiring

### <a id="b-01"></a>B-01 Walking-skeleton story: its commands are unapproved until its PR merges
- **What:** `verify run` runs only the commands in `.factory/config.json` on the default branch on `origin`. On a project's walking-skeleton story, the commands are first set on the story branch, so `verify run` reports them as unapproved until that PR is merged.
- **Source:** [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Impact for T6.5". The PR suggests, as an example only, letting the skeleton story's evidence follow its merge.
- **Status:** verified · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): the command is pending, not run before the merge, and S12 runs it on the default branch afterwards (decision 4 in [task-log.md](task-log.md#t65-stations-s09s11-use-the-verification-engine))

### <a id="b-02"></a>B-02 S10/S11 stop fail-closed until the stations run the engine
- **What:** `verdict check` requires the AC-to-test map, but no station runs `verify run` or `verify map` yet. On a live target, S10 reports `INVALID` and stops with `factory:needs-human`. This was accepted for the interval between T6.2 and T6.5.
- **Source:** [PR #37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), "Interim effect until T6.5 (accepted)"; approved at `12c41339#617` (see [task-log.md](task-log.md#t62-deterministic-ac--test-mapping))
- **Status:** verified · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): S09 runs `verify run` and S10 runs `verify map`

### <a id="b-03"></a>B-03 Bookkeeping commits move the branch head past the evidence
- **What:** `pr render` and `pr check` require the evidence to be for the story branch's head on `origin`, and `pr render` reads the traceability rows from the diff at the evidence commit. [S11](../stations/S11-pr.md) commits the traceability rows and a `.factory/log.md` line after opening the PR (steps 5–6). That moves the head past the evidence, so `pr render`/`pr check` must run after that commit, with `verify run`/`verify map` run again.
  - **Analysis, 2026-10-21:** [S09](../stations/S09-test.md) also commits a `.factory/log.md` line after running the commands (steps 5–6).
  - **Analysis, 2026-10-21:** the traceability row names the PR number, which exists only once the PR is open.
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Not in this PR"; the station files
- **Status:** verified (the S11 ordering); analysis (S09, and the PR-number dependency) · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): S09 commits before `verify run`; S11 records the evidence and the map again after its traceability commit (decision 1)

### <a id="b-04"></a>B-04 The rendered PR body versus an attribution footer: unresolved
- **What:**
  - **Verified:** `pr check` compares an open PR's whole body with a fresh render. Anything appended after rendering, "such as an attribution line", makes `pr check` fail; T6.3 intends this, since the template is factory-owned. This is PR #38's Limitation 6.
  - **Observed:** the Claude Code sessions that build this factory are instructed by their environment, not by a rule in this repository, to end the pull-request descriptions they create with an attribution line.
  - **The conflict:** once S11 opens story PRs with `pr render` output, the two can conflict for story PRs.
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Limitations" item 6; the conflict was raised on 2026-10-21 (`c878c238`)
- **Status:** verified (the `pr check` behaviour); observed (the attribution instruction) · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): the attribution line is part of `templates/pr.md` (decision 2)

### <a id="b-05"></a>B-05 S09's stuck path fills the PR template by hand
- **What:**
  - **Verified:** the roadmap's T6.5 requires a station lint that "checks that S09–S11 contain no hand-written gate results". [S09](../stations/S09-test.md)'s **Stuck** stop condition (step 2) tells the model to fill `templates/pr.md` by hand, where "every gate shows its real result".
  - **Verified:** `pr render` refuses to render without an S10 verdict, so it cannot produce that draft PR as it stands.
- **Source:** analysis of the committed station text and of [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38) ("`render` refuses … a missing verdict"), 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): `pr render --stuck` (decision 3)

### <a id="b-06"></a>B-06 S11 step 1 changes the branch head and re-runs the commands by hand
- **What:** [S11](../stations/S11-pr.md) step 1 merges new default-branch commits into the story branch and then re-runs the commands by hand. With the verification engine, that merge commit makes the evidence, the map and the verdict stale.
- **Source:** analysis of the committed station text, 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44): new default-branch commits send the story back to S09 (decision 1)

### <a id="b-07"></a>B-07 Where "rule H1 is enforced by code wherever it can be"
- **What:** T6.5's acceptance criterion "Rule H1 is enforced by code wherever it can be" does not say which code paths must enforce it.
- **Source:** [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), T6.5 acceptance criteria; analysis, 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by [PR #44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44), as proposed there for review: the station lint, and `factory.py pr` refusing a story PR body that is not the render

## Handed on by T6.5

### <a id="b-26"></a>B-26 The stations capture no test report, so a unit-only AC may not map
- **What:** S09 runs `verify run` without `--report`, because nothing records which report file a target's test command writes. With a runner whose default output lists no passing test by name (Vitest's default reporter), a test that passed has no result in the map. An AC covered only by such tests is `missing`, and the verifier's `pass` for it is `INVALID`, which stops S10 for the human. An AC that also has an end-to-end test listed by name is not affected.
  - **Verified, 2026-10-22** (Vitest 5.0.2 as installed in Task Tracker, from its source; no tests were run): with no reporter configured, Vitest uses `minimal` when `std-env` detects an AI agent (for example `CLAUDECODE` or `AI_AGENT`, which `verify run` passes on to the commands) and `default` otherwise. Neither prints a passing test by name. Its `json` reporter writes the jest-style report that `verify map` already reads.
  - **Analysis, 2026-10-22:** none of the 62 tagged ACs in Task Tracker's history is unit-only, so this has not stopped a story there yet.
- **Source:** [PR #37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), "Limitations" 1 and 2 (T6.2); the T6.5 station text
- **Fix (factory side):** an optional `test_reports` list in `.factory/config.json`, read only from the approved config. `verify run` captures those reports with no station naming them, accepts only fresh, readable ones, and does not accept the evidence when the tests passed without them (architecture §5.3, §4.4). Merged in [PR #45](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/45) on 2026-10-22.
- **Target side (Task Tracker):** [Task Tracker PR #31](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/pull/31), merged on 2026-10-22, sets Vitest's reporters to `default` plus `json` with `outputFile` `reports/vitest.json` (gitignored), and lists `reports/vitest.json` in `test_reports`. The report is not under `test-results/`, because Playwright clears that folder at the start of its run, which `npm test` starts right after Vitest. Any other target that needs a report sets up its own (architecture §5.3).
- **Verified end to end, 2026-10-22,** on the throwaway [Task Tracker issue #32](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/issues/32) (no `factory:story` label or marker, now closed as not planned), with one unit-only test, `#32 AC1`. `verify run` captured `reports/vitest.json` from the approved config (`configured: true`, `origin/main@dcbe6e7`), `verify check` returned OK, and `verify map` mapped AC1 to `passed` from that report.
- **Status:** verified (the limitation, the Vitest behaviour and the fix) · **Owner:** unassigned · **State:** resolved by [PR #45](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/45) (factory side) and [Task Tracker PR #31](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/pull/31) (target side)

### <a id="b-27"></a>B-27 A stuck rework leaves a ready PR ready
- **What:** `factory.py pr --draft` makes a PR a draft only when it creates it; an existing PR keeps its state. When a story gets stuck during rework, its PR is already ready for review, so the stuck path updates its body (which states the failures) but does not make it a draft, as rule H2 asks.
- **Source:** `factory.py pr --help` ("an existing PR keeps its state"); the S09 stuck path, unchanged in this respect by T6.5
- **Status:** analysis · **Owner:** unassigned · **State:** open

## Handed on by T7.1

### <a id="b-34"></a>B-34 An ID dropped at Gate A, or deleted from the record files, can be reused
- **What:** S05 revision mode moves a dropped requirement or story to `## Out of scope`, as a plain bullet. A dropped story also loses its `### STORY-###` heading, so that `issues sync` does not create its issue.
  - **The finding:** with T7.1's first design (D2: only `- **REQ-###**` bullets and `### STORY-###` headings allocate), a dropped ID was no longer allocated. When it was the highest, the next increment handed it out again, with only a warning. This was reproduced on PR #50's head `24e59be`: REQ-005 and STORY-003 dropped at Gate A gave `REQ-005 STORY-003`, where `main` at `5c2e9a7` gave `REQ-006 STORY-004`.
  - **Resolved** by [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50) (Option 1, before merge): every ID named anywhere in `02-requirements.md` or `05-stories.md` is allocated, in the working tree and at every Planning PR's head commit. The tests are in `GateADropRegressionTest`.
  - **What remains (accepted):** T7.1 reads only a Planning PR's final head and the two record files. An ID that is deleted from both record files altogether, instead of being moved to `## Out of scope` as S05 requires, can still be handed out again. It then shows as a warning while any other file still mentions it. Closing this would mean reading every commit of each Planning PR.
- **Source:** T7.1 design discussion (`34ce5c38#146`–`#165`); the pre-merge review of PR #50 (`34ce5c38#646`), and the human's choice of Option 1 (`34ce5c38#739`); [task-log.md](task-log.md#t71-id-allocation-from-structured-sources-only)
- **Status:** verified · **Owner:** T7.1 · **State:** **resolved** by PR #50 (on merge); the remaining deletion case is listed under Accepted limitations

## Specification gaps

### <a id="b-08"></a>B-08 Q6 scope: the story contract declares no areas
- **What:** the roadmap's T6.3 asks for Q6 to check the files touched "against the story's declared areas". The story contract has no areas field. By the T6.3 decision, Q6 reports "Not checked: the story contract declares no areas" with the files touched, so scope stays a reviewer judgement. The roadmap's T7.4 also relies on per-story "declared files".
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Q6 roadmap gap"; decision `12c41339#927` (see [task-log.md](task-log.md#t63-deterministic-pr-body-pr-render--pr-check))
- **Status:** verified · **Owner:** T7.4, or a roadmap change · **State:** open

## Guard gaps

The roadmap assigns the M4 guard gaps to T9.5. Its T9.5 Build lists `git clone` outside the target, the `/tmp` mapping and computed verbs. B-10, B-11, B-14, B-15 and B-28 are not named in T9.5's Build, so whether they belong to T9.5 is a scope decision for that task.

### <a id="b-09"></a>B-09 Computed arguments are not analysed
- **What:** for example `gh pr $(echo merge) 5`.
- **Source:** [PR #27](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/27), "Still open"; [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Known gaps left for T9.5"; [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), open-findings table and T9.5
- **Status:** verified · **Owner:** T9.5 · **State:** open

### <a id="b-10"></a>B-10 Variables are not substituted
- **What:**
  - Bash assignments are not tracked, for example `B=main; git push origin $B`. PowerShell assignments are tracked.
  - Variables inherited from the environment are not resolved, for example `gh pr $VERB 5`.
- **Source:** [PR #27](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/27), "Still open"; [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Known gaps left for T9.5"
- **Status:** verified · **Owner:** T9.5 (by the T6.1 decision; not named in T9.5's Build) · **State:** open

### <a id="b-11"></a>B-11 Indirect execution is not analysed
- **What:** npm and make scripts, `./script.sh`, `python file.py`, git aliases from config files, `find -exec`. Because `verify run` runs only approved, human-merged commands, exploiting these through it needs a merged config change or project code.
- **Source:** [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Known gaps left for T9.5"
- **Status:** verified · **Owner:** T9.5 (by the T6.1 decision; not named in T9.5's Build) · **State:** open

### <a id="b-12"></a>B-12 `git clone` into a folder outside the target is not blocked
- **What:** the guard did not block a `git clone` outside the target, although later file writes there were blocked.
- **Source:** [progress.md](progress.md), M4 "Follow-ups from the sandbox run" item 3; [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), open-findings table and T9.5
- **Status:** verified · **Owner:** T9.5 · **State:** open

### <a id="b-13"></a>B-13 Git Bash's `/tmp` is treated as outside the allowed areas
- **What:** Git Bash maps `/tmp` to the user's temp folder, which is an allowed area, but the guard treats `/tmp` as outside.
- **Source:** [progress.md](progress.md), M4 observations ("noted in #28"); [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), open-findings table and T9.5
- **Status:** verified · **Owner:** T9.5 · **State:** open

### <a id="b-14"></a>B-14 Bash writes outside the factory repo with no active target
- **What:** with no active target, the guard blocked a direct file write to a folder outside the factory repo and scratch area, but `mkdir`, `cp` and a Python script run through Bash wrote to that same folder without being blocked.
- **Source:** observed on 2026-10-21 in session `c878c238`, during the roadmap recovery (`c878c238#1424` onwards)
- **Status:** observed, not reproduced by a test · **Owner:** unassigned (likely T9.5; not named in its Build) · **State:** open

### <a id="b-15"></a>B-15 Credentials are not stripped from the environment of configured commands
- **What:** the commands `verify run` executes inherit the environment, including any credentials in it.
- **Source:** [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Known gaps left for T9.5" ("out of scope for this PR")
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-28"></a>B-28 The approved config's trust root is a local ref that can be repointed
- **What:** "approved" means `.factory/config.json` on the default branch on `origin` (ADR-0004). `verify run` finds that commit through the clone's **local** refs: `evidence.default_ref` reads the symbolic ref `origin/HEAD`, and `evidence.approved_config` reads the config at the local remote-tracking ref it names (`origin/main`). Both are plain local refs. The guard allows the commands that repoint them (checked with `guard.decide` on 2026-10-22):
  - `git -C <T> remote set-head origin story/27-x`
  - `git -C <T> update-ref refs/remotes/origin/main HEAD`
  - `git -C <T> symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/story/27-x`
  - **Also allowed** (checked with `guard.decide` on 2026-10-23): `git -C <T> remote set-url origin <url>` and `git -C <T> config remote.origin.url <url>`. `origin` can then name another repository, so `git ls-remote origin` is not authoritative by itself; the GitHub API for the repository recorded with the target is.
  - **Not only through the guard:** `verify run` runs the approved test command with bash, outside the guard, so the story branch's test code can also run these commands. A guard block (criterion 6 below) cannot be the main fix.
- **Risk:** after any of these, the story branch's own config is treated as approved. Its `commands.*` would run and pass `verify check` as approved, and its `test_reports` would be read as trusted, bypassing ADR-0004's rule that only commands a human merged may run. The same refs also decide `config_source`, `unapproved`, `pending`, the base of `verify map`'s diff, and `pr render`'s diff base and its `limits.max_diff_lines` and `ci_required`. The guard still vets every command, so this does not by itself open a merge path. In contrast, the story branch's head is already taken from the remote (`git ls-remote`, `evidence.remote_head`).
- **Expected behaviour:** the approved config comes from an authoritative default-branch head: the default branch and its commit as GitHub reports them, never from what local refs say. Local ref changes cannot change what is approved, and anything that cannot be confirmed fails closed.
- **Proposed acceptance criteria** (for the owning task to confirm; not decided):
  1. The default branch's name and head commit come from the remote (`git ls-remote --symref origin HEAD` or `refs/heads/<D>`, or the GitHub API), not from `refs/remotes/origin/*`. The name must match `default_branch` in that config, or nothing runs.
  2. The approved config is read from that exact commit. If the commit is not in the clone, it is fetched; if it still cannot be read, nothing runs.
  3. Repointing `origin/HEAD` (`remote set-head`, `symbolic-ref`) or the remote-tracking default branch (`update-ref`) changes neither the commands that run nor the reports that are read. One regression test for each of the three commands above, plus one for a forged `refs/remotes/origin/main` that points at a commit that is not on the remote.
  4. `config_source` records the authoritative commit, and `verify check`, `verify map`, `verdict check` and `pr render` reject evidence whose `config_source` is not a commit of the remote default branch.
  5. The remote cannot be reached, or its answer cannot be parsed: fail closed, with the reason, and nothing runs.
  6. Optional defence in depth: the guard blocks rewriting `refs/remotes/origin/*` and `remote set-head` in the target.
  7. Unit tests use fakes, with no network; Windows Git Bash and PowerShell, like the rest of the engine.
- **Source:** found during the review of B-26 ([PR #45](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/45)), 2026-10-22: the code paths above and a `guard.decide` check of the three commands; the `remote set-url` check, 2026-10-23
- **Status:** verified (the commands are allowed, and the code reads local refs); analysis (the acceptance criteria) · **Owner:** unassigned: T9.5 (guard hardening) or a standalone hardening task sequenced by the human; **due before T8.1** (the headless runner, which runs unattended between gates), the human's decision on 2026-10-23 · **State:** open. ADR-0004 is unchanged; making its "default branch on `origin`" authoritative may call for an amendment or a new ADR.

## Verification not yet done

### <a id="b-16"></a>B-16 `trace` on squash and rebase merges against live GitHub
- **What:** `trace` relies on GitHub's commit-to-PR API listing the PR for the commit GitHub wrote. It is verified live for merge-commit merges only. Squash and rebase are tested only against GitHub-shaped answers, because the test project has only merge commits.
- **Source:** [PR #39](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/39), "Limitations"
- **Status:** verified (as a limitation) · **Owner:** unassigned · **State:** open

### <a id="b-17"></a>B-17 The timed traceability walk by a human (success criterion 6)
- **What:** `trace` gives the chain in one command, but the walk by a human reviewer has not been timed.
- **Source:** decision `c878c238#106` item 6 (see [task-log.md](task-log.md#t64-review-experience-and-traceability)); the roadmap's M6 demo item 5
- **M6 demo, 2026-10-23:** `trace src/domain/filter.ts:21` followed the line to PR #37, issue #34, REQ-027..REQ-030 and the PRD in 2.44 s (3.0 s wall-clock), which meets the roadmap's M6 demo item 5. The assistant ran it; a walk by a human reviewer has still not been timed ([progress.md](progress.md#m6-deterministic-verification--review)).
- **Status:** verified · **Owner:** unassigned (was the M6 demo) · **State:** open

### <a id="b-35"></a>B-35 Reading a closed Planning PR's records after its branch is deleted, against live GitHub
- **What:** T7.1 reads each Planning PR's records at its head commit by SHA, so that an abandoned plan's IDs are never reused, even after its `factory/plan-<inc>` branch is deleted. GitHub keeps a closed PR's head commit (`refs/pull/<n>/head`), but this has been tested only with a fake GitHub. A live check needs GitHub writes on a throwaway repo: push a record file, open a PR with a planning marker, close it, delete the branch, and run `increment show`. Every Planning PR read live so far (Task Tracker #1, #26, #33) still has its branch.
- **Source:** T7.1, Step 6 of the approved implementation prompt; declined for now by the human (`34ce5c38#481`, 2026-10-25T10:44:41Z). See [task-log.md](task-log.md#t71-id-allocation-from-structured-sources-only).
- **Status:** analysis · **Owner:** unassigned (candidate: the M7 demo) · **State:** open

## M6 demo findings

Found while running the M6 demo on Task Tracker, increment `003-priority-filter` ([progress.md](progress.md#m6-deterministic-verification--review)). The recurrence of [B-18](#b-18) is recorded on that item.

### <a id="b-29"></a>B-29 S11's Done check cannot pass after a rework round
- **What:** in rework mode, S11 step 6 (the traceability commit) is skipped because the rows already list `#<P>` from the first run, so S11 makes no commit and the story branch's head carries S09's (or S08's) trailer. S11's Done check still requires `git -C <T> log origin/<B> -1 --format=%B` to show `Factory-Station: S11`, which cannot hold. The state engine reports `GATE_B_WAITING_REVIEW` regardless, so nothing is blocked; only the checklist is wrong. The same skip leaves the rows' test names stale when a rework renames tests (REQ-027 and REQ-028 on Task Tracker).
- **Source:** the M6 demo, point 4 (PR #37, rework round 1); [S11](../stations/S11-pr.md) step 6 and Done check
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-30"></a>B-30 A `Changed test:` line must give a full path for a change outside any test
- **What:** `prbody.changed_tests` matches a change outside any test (an import, a locator helper) by checking that the declared text contains the file's full path. `Changed test: due-date-priority.spec.ts …` did not match `tests/e2e/due-date-priority.spec.ts`, so `pr render` reported rule H3 problems, and also warned that the declared line named no change. [S09](../stations/S09-test.md) step 2 does not say that a full path is needed. Candidates: say so in S09, or also match by file name.
- **Source:** the M6 demo, point 2: S11 stopped and asked on Task Tracker #34; the human approved an empty commit (`3f48c51`) with full-path lines; `scripts/factory/prbody.py` (`changed_tests`)
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-31"></a>B-31 No factory path for changing an acceptance criterion after Gate A
- **What:** a Gate B `/changes` renamed a label that AC1 and AC2 name. The AC verifier, which sees only the issue's criteria and the diff, correctly failed AC1, and S08 had to stop and ask, because the only "fix" would have undone the feedback. At the human's request, AC1 and AC2 were edited on the issue. STORY-015 in the approved `05-stories.md` on the target's `main` and two test names in `traceability.md` are now out of date, and no station records or reconciles such a change. Needs a decision: how a rework that changes an approved criterion updates the issue and the planning documents (for example a small planning PR, or S11 carrying the document changes).
- **Source:** the M6 demo, point 4 (the question and the human's decision on Task Tracker #34; PR #37)
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-32"></a>B-32 Vitest sometimes cannot start a worker on a cold start
- **What:** on the Windows machine used, the first `npm test` after a pause sometimes fails before Playwright runs: Vitest reports `Failed to start forks worker for test files …/src/ui/render.test.ts` (`Timeout waiting for worker to respond`), that file does not run, and every test that ran passes. `verify run` then records `test fail`, which can spend a fix attempt. Every rerun has passed. It is environmental, on the target's side (Vitest's pool), but the factory cannot tell such a failure from a real one.
- **Source:** the B-26 integration (Task Tracker PR #31, 2026-10-22); the M6 demo, point 2 (`verify run` on `383ae7a`)
- **Status:** observed · **Owner:** unassigned · **State:** open

### <a id="b-33"></a>B-33 Q7 Size counts the factory's own `.factory/log.md` lines
- **What:** `pr render` counts every changed line toward Q7, including the `.factory/log.md` line that each station run appends. A rework round therefore adds lines that no reviewer needs to read: PR #37 went from 397 to 401 of 400 lines through log lines alone, and Q7 warned (a warning, not a stop; see Accepted limitations, T6.3). Candidate: leave `.factory/log.md` out of Q7, as generated files are.
- **Source:** the M6 demo, point 4 (PR #37, `pr render`)
- **Status:** verified · **Owner:** unassigned · **State:** open

## Earlier findings assigned by the roadmap

The roadmap's open-findings table ([05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "Open findings from M2–M5") assigns these to tasks. They are listed here with their current state; the full descriptions are in [progress.md](progress.md).

| ID | Finding | Owner | State |
|---|---|---|---|
| <a id="b-18"></a>B-18 | The ID scanner counts mentions in the docs (M2 Problem 4, M5 follow-up 1) | T7.1 | open. In M5 the docs were reworded so that they mention no unallocated ID ([progress.md](progress.md), M5 record). The assistant restated this as an interim practice (`1bcf8818#1057`): keep literal `REQ-`/`STORY-` numbers out of prose under the target's `docs/factory/`, and check `increment show` before S05. This is guidance, not a recorded human decision. It struck again in the M6 demo (2026-10-23): the S01 analysis named the next free IDs, and `increment show` skipped to `REQ-028`; rewording the line in a follow-up S01 commit restored `REQ-027` ([progress.md](progress.md#m6-deterministic-verification--review)). **Resolved** by [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50) (T7.1, on merge): only the IDs named in an increment's `02-requirements.md` or `05-stories.md` (in the working tree and at every Planning PR's head commit) and labelled story issues allocate. A mention anywhere else is only a warning ([task-log.md](task-log.md#t71-id-allocation-from-structured-sources-only)). |
| <a id="b-19"></a>B-19 | Stale story markers without the label (M4 follow-up 1) | T7.1 | **resolved** by [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50) (T7.1, on merge): a marker counts only on an issue with the `factory:story` label, for IDs and for the next increment number; an unlabelled one is a warning |
| <a id="b-20"></a>B-20 | A PRD in `docs/` triggers S01 (M2 Problem 2, M4 follow-up 2) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge). The detection logic had already ignored `docs/**` and documents since T5.2 ([PR #32](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/32)). T7.2 adds a fixture for each layout and closes the remaining false positives: `.git*` files, root licence/notice/changelog/authors files, `CODEOWNERS`, `.editorconfig`, and the `.claude/`, `.vscode/` and `.idea/` folders; HTML still counts as code outside `docs/` (a static site). Live proof: the M7 demo ([task-log.md](task-log.md#t72-intake-and-project-detection)). |
| <a id="b-21"></a>B-21 | A PDF PRD can't be "copied unchanged" (M2 Problem 3) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge): S00 copies Markdown unchanged, gives a text file or a transcribed PDF a `<!-- factory:prd-source` header ([templates/README.md](../templates/README.md), "PRD source header"), and stops and asks for any other format or for a PDF whose requirements cannot be reproduced as text. Live proof: the M7 demo. |
| <a id="b-22"></a>B-22 | S00 runs `doctor` before `labels ensure` (M2 Problem 1) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge): S00 runs `labels ensure` first, then `doctor`; `/factory-target` says that missing labels alone are created by `/factory-start`. Live proof: the M7 demo. |
| <a id="b-23"></a>B-23 | The Gate A `/changes` revision round has never been demonstrated (M2, M4, M5) | M6 demo | **resolved**: demonstrated in the M6 demo, point 1, on Task Tracker's Planning PR #33 ([progress.md](progress.md#m6-deterministic-verification--review)) |
| <a id="b-24"></a>B-24 | `main` has no branch protection (M5 follow-up 3) | T9.6 (`doctor`) and the runbook | open |
| <a id="b-25"></a>B-25 | Close-out wording on an increment's last story (M5 follow-up 2) | T6.4 | **resolved** by [PR #39](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/39) |
| — | Timed traceability walk-through, success criterion 6 (M5) | T6.4 | `trace` delivered by PR #39; the timed human walk moved to the M6 demo: see [B-17](#b-17) |
| — | Guard gaps: `git clone` outside the target, `/tmp`, `gh pr $(echo merge)` (M4) | T9.5 | see [B-12](#b-12), [B-13](#b-13), [B-09](#b-09) |

## Accepted limitations

Kept on purpose by the task that introduced them. Each is described in its PR.

| Task | Limitation | Source |
|---|---|---|
| T6.1 | cmd.exe-only syntax (`^`, `%NAME%`, `!NAME!`, `call`) is refused on every platform, which also rejects a few legitimate bash forms, such as a regex `'^test'` argument | [PR #36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), "Notes for the reviewer" |
| T6.1 | `verify check --file` has no checkpoint, so it skips the "same branch as the checkpoint" rule (it still requires the branch head on `origin` and the approved config) | PR #36, "Notes for the reviewer" |
| T6.2 | Vitest's default reporter lists no passing test by name, so a unit-only AC needs a captured report or a verbose reporter to count as passed | [PR #37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), "Limitations" 1 |
| T6.2 | `--report` is explicit, and nothing auto-detects report paths | PR #37, "Limitations" 2 |
| T6.2 | Name matching ignores the file, so two tests with the same name share their results | PR #37, "Limitations" 3 |
| T6.2 | A map over 20,000 characters is refused for the checkpoint note (fails closed) | PR #37, "Limitations" 4 |
| T6.2 | Out of reach: a weak or rewritten test that keeps its tag, moving local git refs (can only hide tests), edits outside the model's tools | PR #37, "Limitations" 5 |
| T6.3 | Enclosing tests are found by indentation, so unusual formatting can attribute a change to the file or miss an added line | [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Limitations" 2 |
| T6.3 | Dependency detection reads eight manifest formats; others (Maven, Gradle, NuGet …) are not read | PR #38, "Limitations" 3 |
| T6.3 | Q7 "generated" relies on `.gitattributes` or a standard header | PR #38, "Limitations" 4 |
| T6.3 | Q8 reads GitHub check runs only, not legacy commit statuses | PR #38, "Limitations" 5 |
| T6.3 | Q7 over the limit is a warning, not a stop | PR #38, "Limitations" 7 |
| T6.4 | `trace` reads files at `--ref` from the local clone, so fetch first | [PR #39](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/39), "Limitations" |
| T6.4 | Close-out finds stories by their marker, while the state engine lists them by the `factory:story` label (a story whose label was removed: close-out errs towards "continue") | Final review, `c878c238#1216` |
| T6.4 | `trace /c:12` becomes the bare drive `C:` and fails with a blame error | Final review, `c878c238#1216` |
| T6.4 | The `trace` test fixture is a 300 KB git bundle of the test project's history; `test_trace` takes about 35 s on Windows | PR #39, "Limitations" |
| T7.1 | An ID deleted from both record files (`02-requirements.md`, `05-stories.md`), instead of being moved to `## Out of scope` as S05 requires, can be handed out again, because only a Planning PR's final head is read ([B-34](#b-34)) | [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50), pre-merge review (`34ce5c38#739`) |
| T7.1 | A stray mention inside a record file uses up an ID (the safe direction: the numbering skips, never reuses) | PR #50, pre-merge review (`34ce5c38#739`) |
| T7.2 | A root-level file named like repository metadata (`license*`, `licence*`, `copying*`, `notice*`, `changelog*`, `authors*`) is excluded from project detection whatever its suffix, so a root `changelog.py` or `notice.ts` does not count as code. This only matters when such a file is the repo's only code; nested files with these names still count | [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51), review correction (`34ce5c38#1412`); [task-log.md](task-log.md#t72-intake-and-project-detection) |
