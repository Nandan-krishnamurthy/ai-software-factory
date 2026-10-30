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
- **T7.4 (decision P-A):** stories may now declare the files they expect to change, with estimated changed lines (`- Files: <path> (~<lines>), …` in `05-stories.md`). `plan check` uses them for the plan-time size check. The issue body is unchanged by decision, and `pr render` does not read the bullet, so Q6 still reports "Not checked". Wiring Q6 to the declared files would change the issue-body and PR-body contracts, which P-A kept out of T7.4.
- **Status:** verified · **Owner:** unassigned (T7.4 delivered the declared files; Q6 itself is not assigned to any task) · **State:** open

## Guard gaps

The roadmap assigns the M4 guard gaps to T9.5. Its T9.5 Build lists `git clone` outside the target, the `/tmp` mapping and computed verbs. B-10, B-11, B-14, B-15 and B-45 (B-28's optional guard block) are not named in T9.5's Build, so whether they belong to T9.5 is a scope decision for that task. B-28 itself was resolved by a standalone task before T8.1.

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
- **Standalone task, 2026-10-28:** the human sequenced B-28 as a standalone hardening task before T8.1 (`097efb85#173`, 2026-10-28T10:52:41Z). [PR #56](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/56) proposes the criteria above as decided, and records the design as [ADR-0005](adr/0005-approved-config-from-github.md) ([task-log.md](task-log.md#b-28-approved-config-from-github-not-local-refs)). For each proposed criterion:
  1. **Met, via GitHub's API rather than `ls-remote`.** The default branch's name and head come from GitHub for the repository `/factory-target` recorded (`repos/<R>`, `git/ref/heads/<D>`). The config's `default_branch` and `repo` must match, or nothing runs. `ls-remote` was not used for this because it follows the `origin` URL, which `set-url`, `remote.origin.url` and `insteadOf` can change. The clone's `origin` must still be the recorded repository (`check_origin`), because `remote_head` and `fetch` use it. **Review fix (B2):** the story branch's head now comes from GitHub's API too (`remote_head`), not from `ls-remote`: the review showed that a `core.sshCommand` in the clone's config makes `ls-remote` answer from another repository while `check_origin` still passes. `check_origin` remains as a consistency check only.
  2. **Met.** The config is read through GitHub's contents API at that exact commit. `verify map` and `pr render` need the commit in the clone for their diffs, so they fetch it by its SHA if it is missing, and otherwise nothing runs.
  3. **Met.** Real-git regression tests cover `update-ref`, `remote set-head`, `symbolic-ref`, a forged `origin/main` not on the remote, and also `git replace` and grafts, which the design found to have the same effect. The factory's git now ignores replace refs and grafts.
  4. **Met.** `config_source` is `<branch>@<full SHA>`. `verify check`, `verify map`, `verdict check`, `pr render` and `pr check` reject a source that is not the head of GitHub's default branch or an ancestor of it (GitHub's compare API), and evidence recorded before B-28 ("run `verify run` again"). **Review fix (B1):** an ancestor counts only while every `commands.*` entry and `test_reports` in its config are still the head's (`superseded`). The review showed that, before this fix, evidence recorded before a merge changed the approved commands passed every consumer.
  5. **Met.** Every GitHub failure, malformed answer or mismatch, a missing config and an unfetchable commit: nothing runs or is accepted, and the reason is stated.
  6. **Not done** (optional): the guard is unchanged; see [B-45](#b-45).
  7. **Met.** Unit tests use fakes with no network; the real-git tests use a throwaway local clone and contact no remote.
- **Adversarial review, 2026-10-28:** two merge blockers, fixed in PR #56 before merge (2026-10-30):
  - **B1:** superseded evidence was still accepted after the approved commands changed;
  - **B2:** the clone's git config could fake the story branch's head through `core.sshCommand`.

  Three further findings are recorded as [B-46](#b-46), [B-47](#b-47) and [B-48](#b-48). The review's other notes are in [task-log.md](task-log.md#b-28-approved-config-from-github-not-local-refs).
- **Status:** verified (the commands are allowed, and the code reads local refs; the fix, by `tests/test_config_source.py`) · **Owner:** standalone hardening task before T8.1 (the human's decisions of 2026-10-23 and 2026-10-28) · **State:** **resolved** by [PR #56](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/56) (on merge); what remains is [B-45](#b-45)

### <a id="b-45"></a>B-45 What B-28 left: an optional guard block, and the clone's own object store
- **What:**
  - **The guard still allows repointing the remote-tracking refs** (`update-ref refs/remotes/origin/*`, `remote set-head`, `symbolic-ref refs/remotes/origin/HEAD`, `remote set-url`). B-28 no longer reads any of them, so they change nothing the factory trusts. Blocking them in the target would only be defence in depth (B-28's optional criterion 6), and the project's test code would not pass through the guard anyway.
  - **Objects already in the clone are not re-hashed when git reads them.** A rewritten loose object, pack or commit-graph file in the target's `.git` could change what a local diff shows (`verify map`, `pr render`). Replace refs and grafts are ignored since B-28, and the approved config itself is read from GitHub, so neither is affected. Candidates: take the diff from GitHub's compare API, or verify the objects involved.
  - ~~**An older approved config is still accepted.**~~ **Resolved in PR #56 before merge** (review finding B1): evidence from an older commit of the default branch now counts only while its `commands.*` and `test_reports` are still the head's (`evidence.superseded`).
- **Source:** the B-28 design and its probes (git 2.52, 2026-10-28); [ADR-0005](adr/0005-approved-config-from-github.md), "Not decided here"; [S11](../stations/S11-pr.md) step 1
- **Status:** analysis · **Owner:** T9.5 for the guard block (a scope decision for that task); unassigned for the rest · **State:** open

### <a id="b-46"></a>B-46 A repository's own git config can make git run programs, outside the guard
- **What:** settings in the target's `.git/config` make git start programs that the guard never sees, because the guard vets the command typed, not what git starts:
  - `core.sshCommand` runs on any `fetch`, `ls-remote` or `push` over ssh;
  - `core.fsmonitor` runs on `git status`;
  - credential helpers run on network calls over HTTPS.
- **Shown on 2026-10-28:**
  - `guard.decide` allows `git -C <T> config core.sshCommand …`;
  - a `core.sshCommand` set that way ran when the factory's own `git ls-remote` ran, and answered from a local fake repository.
- **Where git still starts such programs:**
  - the factory's own git calls, outside the guard: `local_commit`'s `fetch` and `verify run`'s `git status`;
  - the stations' `git fetch`, `git push` and `git status`, which go through the guard as text.

  After B-28's review fix, no fact the factory trusts comes from these calls.
- **Risk:** a configured program can run any command, for example `gh pr merge`, which the guard would block if typed. Not demonstrated: no merge was attempted. Related to [B-11](#b-11) (indirect execution, "git aliases from config files"), which names none of these settings.
- **Before T8.1?** Recommended. T8.1 runs stations unattended between gates, and its acceptance criterion "the runner can't merge (the guard is still active)" rests on the guard seeing every command. This is the human's decision, like B-28's. Candidates:
  - the factory's git calls set the risky settings to safe values (`-c core.fsmonitor=false -c core.sshCommand=ssh`, no repository credential helper);
  - the guard refuses `git config` writes of program-valued keys in the target;
  - `doctor` fails on them.
- **Source:** the adversarial review of PR #56 (finding D1, 2026-10-28), with its `core.sshCommand` proof of concept and the `guard.decide` check
- **Status:** verified (the guard allows the setting, and git runs it); analysis (the merge path) · **Owner:** unassigned: T9.5 (guard hardening), or a standalone task sequenced by the human · **State:** open

### <a id="b-47"></a>B-47 S12's check after the merge does not hold its evidence against the merge commit
- **What:** `closeout.after_merge` reads the evidence of S12's `verify run` on the default branch and accepts it when the branch is not the story's and nothing failed. It does not check two things:
  - that the evidence is for the merge commit, or for GitHub's current head;
  - that its source passes `check_trusted`.

  If the clone's default branch is behind (`git pull` failed or was skipped), the approved commands run against the old code, pass, and the story is closed out. The commands the story introduced have then never run against its code. This predates B-28 (the same happens with a stale `origin/main`) and is outside B-28's list of consumers.
- **Before T8.1?** Not required: it is a correctness gap, not a merge path. But T8.1's `run --command resume` closes stories out unattended, so it should be fixed by T8.2's live evals at the latest. Candidate: `after_merge` requires the evidence's `sha` to be the merge commit (or GitHub's head of the default branch), and `check_trusted` to pass.
- **Source:** the adversarial review of PR #56 (finding D2, 2026-10-28); `scripts/factory/closeout.py` (`after_merge`, `inspect`)
- **Status:** analysis · **Owner:** unassigned · **State:** open

### <a id="b-48"></a>B-48 "Could not confirm" and "rejected" share exit code 1
- **What:** `main` in `scripts/factory/cli.py` returns 1 for any `FactoryError`, so a GitHub outage (`EvidenceError` from `approved_config` or `remote_head`) looks the same as rejected evidence or a failed test. S10 counts a `verify map` exit 1 as a failed attempt ([S10](../stations/S10-verify.md) step 1). A transient API failure can therefore spend a fix attempt, and repeated ones can make a story stuck. B-28 adds three or four API calls per command, which makes this more likely. The factory still fails closed: nothing is accepted.
- **Before T8.1?** Not required for safety. For an unattended runner it is a reliability problem: candidate for T8.1's scope (the runner tells a transient error from a real one) or a small standalone fix (a distinct exit code, such as 2, for "could not confirm", which the stations treat as "stop and retry").
- **Source:** the adversarial review of PR #56 (finding D3, 2026-10-28)
- **Status:** analysis · **Owner:** unassigned · **State:** open

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
- **M7 demo, 2026-10-27: not run.** Decision D5 authorised it on the PDF sandbox (`1821c3de#1911`). But it needs the human to close that sandbox's Planning PR unmerged and delete its branch, and the human's Phase B instruction was that the PR must stay open and unmerged (`858cb907#2`). What was seen instead: with the plan open, `increment show` gave `REQ-017`, `STORY-006`, so an open plan's IDs are reserved. That is not this item's closed-and-deleted case ([progress.md](progress.md#m7-plans--target-knowledge)). Both sandboxes' Planning PRs (#1 each) are still open and could serve a later run.
- **Status:** analysis · **Owner:** unassigned (the M7 demo did not run it) · **State:** open

### <a id="b-36"></a>B-36 Target knowledge base: S01's creation/update and S12's note, not yet run on a real target
- **What:** T7.3's `knowledge check` is proven at the unit level only, against real throwaway git repositories, not fake ones. What has not been run live is the **model-authored** half: S01 actually creating or updating `docs/factory/knowledge.md` by hand from `knowledge check`'s result (including reusing an earlier increment's `01-codebase-analysis.md` on first creation, K-D), and S12 actually posting the Knowledge base paragraph on an increment's last story (K-A).
- **Source:** [PR #52](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/52) (T7.3), decision K-G; [task-log.md](task-log.md#t73-target-knowledge-base)
- **M7 demo, Task Tracker increment 004 (2026-10-27/28): partly shown** ([progress.md](progress.md#m7-plans--target-knowledge)).
  - **Creation (shown):** S01 created `docs/factory/knowledge.md` on the target's first S01 run with the file `missing`, reusing 003's analysis (K-D). Header `checked=e89fbb2…`, the eight sections in order, and Architecture decisions linking `001`, `002` and `003/03-architecture.md` by path. S01's Done check, `knowledge check` → `fresh`, `"ok": true`, passed (commit `2ccaef1`).
  - **S12's note (shown):** on the increment's last story (#41, PR #42), the close-out summary had the Knowledge base paragraph (REQ-037..REQ-041, PR #42, and the `knowledge check` status), and S12 committed nothing (K-A).
  - **Use by S02–S04 (shown, with a limit):** `02`, `03` and `04` cite the file. The same session wrote it, so this shows use, not independent learning.
  - **Not shown: the update.** S01 reusing and updating an existing file (T7.3 AC1) needs a later increment, and decision D4 (`1821c3de#1911`) deferred it rather than create a demo-only increment 005. The file is now `stale` (Hotspots, Architecture decisions, Known risks, against `e89fbb2`), which is the input that run needs.
- **Status:** verified (creation and S12's note); analysis (the update) · **Owner:** unassigned (the next real increment on Task Tracker) · **State:** open (the update half)

### <a id="b-37"></a>B-37 Plan check: an overlapping change request, not yet run on a real target
- **What:** T7.4's `plan check` is proven at the unit level only. That proof uses the real Task Tracker plans of increments 001–003 and an authored replay of the M5 change request. What has not been run live is S05 handling the result:
  - writing the `- Files:` estimates;
  - running `plan check` until it exits 0;
  - recording an Open question for a flagged overlap, or stopping under rule H6;
  - embedding the output unedited in the Planning PR.

  The roadmap's M7 demo asks for exactly this: Task Tracker increment 004, a change request overlapping existing features, which `plan check` flags.
- **What the demo should also record** (from the review of PR #53):
  - which Done requirements the real change request is flagged against, and whether each flag was a real overlap ([B-40](#b-40));
  - that the Open question S05 writes is a list item asking a question, which is the only form that resolves the overlap;
  - that the Planning PR's "Plan check" section matches a fresh `plan check` run on the plan branch ([B-38](#b-38)).
- **Source:** [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection) (T7.4, "Handed on"); the M7 demo in [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md)
- **M7 demo, Task Tracker increment 004, Planning PR #40 (2026-10-27): shown** ([progress.md](progress.md#m7-plans--target-knowledge)).
  - **`Files` estimates:** written for the one story, which estimated 231 lines, then 368 and 385 after the two Gate A rounds. Q7 measured 333 at Gate B.
  - **Run until it exits 0, in three runs:**
    - first plan: exit 1, 3 unresolved potential overlaps, then PASS;
    - Gate A round 1: exit 1, 2 new unresolved, then PASS;
    - round 2: PASS on the first run.
  - **Open questions:** S05 judged each flagged pair not to be a restatement. It recorded each as a numbered list item with a `?`, naming both IDs (Open questions 8, 9, 11 and 12), and `plan check` reported every pair "resolved in Open questions".
  - **Embedded unedited, and matching a fresh run** ([B-38](#b-38)): in all three rounds, the fresh run on the plan branch was identical to the PR body's copy. (On the two sandboxes' first increments it was not: [B-43](#b-43).)
  - **The flags and verdicts** are under [B-40](#b-40).
  - **The change request's real overlap,** FR-017 restating REQ-010, never reached `plan check`. S02 stopped on it under rule H6, and the human kept it out of scope (`858cb907#917`).
- **Status:** verified · **Owner:** the M7 demo · **State:** **resolved** by the M7 record ([progress.md](progress.md#m7-plans--target-knowledge))

## Handed on by T7.4

### <a id="b-38"></a>B-38 `plan check` is enforced only by S05's text
- **What:** nothing in code requires `plan check` to have passed, or its output in the Planning PR to be the real, unedited output. Only S05's steps and Done check say so.
  - The state engine reports `GATE_A_WAITING` as soon as the Planning PR is open.
  - S05b creates the issues after the merge without re-running the check.
  - `issues sync --dry-run` has the same gap today.

  A plan that skips the check, or a pasted output that was edited, is caught only by the human at Gate A.
- **M7 demo:** checked by hand, the embedded output matched a fresh run in all three rounds of Task Tracker's Planning PR #40. On both sandboxes' first increments it did not, for a harmless reason ([B-43](#b-43)), which a code check like this would have to allow for.
- **Candidates:** S05b, or `issues sync` itself, re-runs `plan check` on the merged plan and refuses on a failure; or a check of the Planning PR body against a fresh run, like `pr check` does for story PRs.
- **Source:** the review of PR #53 (`1821c3de#999`), concern 3
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-39"></a>B-39 `plan check` parser edge cases
- **What:** found by the review of PR #53, none of them silent:
  - **A `Files` list of only lockfiles** gives an estimate of 0, which passes the size check.
  - **A bold `**REQ-###**` bullet under `## Changed or retired requirements`** counts as an in-scope requirement of the increment. It then needs a story, and is scored against its own Done self. S02 forbids such bullets, and the result fails loudly.
  - **An unindented continuation line** of a requirement bullet is dropped from its statement, which only affects the score.
  - **Coverage is lenient:** a story may trace any earlier REQ that `## Changed or retired requirements` merely mentions, including one no increment defines. Resolution was made strict by the review fixes; coverage was not.
  - **A bare path ending in another `(~N)`,** such as `a (~3) (~4)`, parses as the path `a (~3)`.
- **Source:** the review of PR #53 (`1821c3de#999`), concern 5; [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection)
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-40"></a>B-40 Overlap scoring: lexical false positives and misses
- **What:** the review of PR #53 tried realistic ways S02 might word the M5 request, beyond the verbatim replay. Each was still flagged against at least one Done requirement. But:
  - **Wrong Done requirements were flagged too.** "The user can optionally give a task a due date when creating it, and the task shows it." also flags REQ-004, a priority requirement, at 0.737 through parallel wording. A wording with "next to its title" flags REQ-002, a validation message, at 0.612.
  - **Synonyms are missed.** "Tasks can be given a deadline." flags nothing.
  - **The exact AC1 set needs the verbatim wording.** {REQ-003, REQ-009, REQ-012, REQ-014} comes from the request's own words only.

  Each false positive costs one Open question and is shown to the human. Each miss is silent. The scoring formula and thresholds were deliberately left unchanged.
- **Next step:** measure the rate on the M7 demo's real change request ([B-37](#b-37)) before deciding whether the rule needs more, such as phrases, synonyms or a second signal.
- **Measured in the M7 demo (Task Tracker increment 004, 36 Done requirements compared):**

  | `plan check` run | Pair | Score | Kind |
  |---|---|---|---|
  | First plan | REQ-037 ~ REQ-022 | 1.000 | potential |
  | | REQ-038 ~ REQ-022 | 0.827 | potential |
  | | REQ-038 ~ REQ-023 | 0.827 | potential |
  | | REQ-037 ~ REQ-023 | 0.462 | related |
  | | REQ-038 ~ REQ-024 | 0.499 | related |
  | After both Gate A rounds (final) | REQ-037 ~ REQ-022 | 0.943 | potential |
  | | REQ-038 ~ REQ-022, REQ-023 | 0.759 each | potential |
  | | REQ-038 ~ REQ-024 | 0.541 | potential |
  | | REQ-040 ~ REQ-025 | 0.924 | potential |
  | | REQ-037 ~ REQ-023 | 0.410 | related |
  | | REQ-040 ~ REQ-031 | 0.495 | related |
  | | REQ-039, REQ-041 | — | no candidate at or above 0.400 |

  - **Verdict on every potential flag: related, not a duplicate.** Each pairs a new "Due today" requirement with the matching "Overdue" requirement of 002, which says the same about a different label and date. S05 recorded that judgment as Open questions 8, 9, 11 and 12 ("Assumed: yes", new work), and the human approved it by merging PR #40. So the rate was **5 potential flags, 0 duplicates**, at a cost of 4 Open questions.
  - **A score of 1.000 for a different feature:** every weighted word of the first REQ-037 also appears in REQ-022, even the label's own words, "due" and "today". The words alone cannot tell "due today" from "due before today".
  - **A miss that did not matter here:** the change request's real duplicate, FR-017 against REQ-010, was never scored, because S02 caught it and kept it out of the requirements ([B-37](#b-37)).
- **Source:** the review of PR #53 (`1821c3de#999`), concern 4; the accepted limitation below; the M7 demo ([progress.md](progress.md#m7-plans--target-knowledge))
- **Status:** observed (review probes, and one live change request) · **Owner:** unassigned · **State:** open

## T7 review findings recorded after merge

These were reported as non-blocking in the final reviews of PR #52 and PR #53, but no PR recorded them before the merges. Each was re-checked on `main` at `481970c` (T7.4's merge) on 2026-10-26, against the code and with in-memory probes. None is fixed.

### <a id="b-41"></a>B-41 `knowledge check`: findings from T7.3's final review
- **What:** the review of `1d2775b` approved T7.3 with these non-blocking findings. `knowledge.py`, `markers.py`, S01 and S12 are unchanged since then, so they still apply.
  - **The header is accepted anywhere in the file** (probe E). `parse` finds the `factory:knowledge` marker with `markers.find` over the whole text. A file with no first-line header but an example marker inside a code block is read as checked against that commit. Decision K-C says a missing header makes every section stale. Candidate: accept the marker only on the first line.
  - **A one-line fenced span at the start of a line opens a fence that never closes** (probe F). For example, a ```` ```npm test``` ```` line: every later section is swallowed and the file is `invalid`. This fails safe, but is over-strict.
  - **Filename matching depends on the OS** (probe D). `fnmatch.fnmatch` follows the OS's case rules, so on Windows a lowercase `makefile` matches `Makefile`, and on Linux it does not. Candidate: `fnmatch.fnmatchcase`. Re-checked on Windows only; the Linux behaviour is Python's documented semantics, not run.
  - **Wording and output:**
    - on an empty repo, the error names `--ref 'HEAD'` although no `--ref` was given;
    - with `--json`, a bad ref prints no JSON, only the error;
    - S01 step 8's "first ever" sentence ("nothing was `missing` because of a stale commit, …") is hard to follow.
- **Source:** the final review of PR #52 (`34ce5c38#3155`, 2026-10-26T06:05:21Z), "Non-blocking concerns"
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-42"></a>B-42 `plan check`: findings from T7.4's second review
- **What:** the review of `a9d35af` approved the two review fixes with these non-blocking findings. They are not covered by [B-38](#b-38)–[B-40](#b-40).
  - **An Open question resolves the pair whatever it asks.** "1. REQ-007 is new and REQ-002 is unchanged. Should exports be zipped?" names both IDs and contains a `?`, so it resolves REQ-007 ~ REQ-002. This is the accepted limitation (below) at its weakest. Candidate: require the `?` in the sentence that names both IDs.
  - **A question inside a fenced code block counts** as an Open question. `section_items` does not skip fences.
  - **A question on a nested sub-bullet, or on an unindented continuation line, does not resolve.** For example, "1. REQ-007 may restate REQ-002." followed by "   - Is it new work?". This fails safe and loud, but a model could be stuck by it. S05's one-line example steers away from it.
  - **The hint "(wrap a path that holds a comma in backticks)"** is added to every malformed `Files` entry, including one whose only problem is a missing `~`, as in `src/a.py (40)`.
- **Source:** the second review of PR #53 (`1821c3de#1385`, 2026-10-26T08:13:29Z), "Non-blocking follow-ups"
- **Status:** verified · **Owner:** unassigned · **State:** open

## M7 demo findings

Found while running the M7 demo on the two new sandboxes and on Task Tracker, increment `004-edit-priority-due-today` ([progress.md](progress.md#m7-plans--target-knowledge)). Recurrences are recorded on [B-30](#b-30) and [B-32](#b-32); the live results of T7.2–T7.4 on [B-20](#b-20)–[B-22](#b-22) and [B-35](#b-35)–[B-40](#b-40).

### <a id="b-43"></a>B-43 S05's embedded `plan check` output differs from a fresh run on a project's first increment
- **What:** S05 runs `plan check` at step 3 and creates `docs/factory/traceability.md` at step 4. On a project's first increment, the output S05 embeds in the Planning PR therefore has a `Notes:` line, "No docs/factory/traceability.md: there are no Done requirements to compare". A fresh `plan check` on the committed plan branch does not have it. The result is the same (`PASS`, 0 compared); only the text differs. But a reviewer, or a future code check of the embedded output against a fresh run ([B-38](#b-38)), sees a mismatch. Later increments are not affected, because the matrix already exists: Task Tracker increment 004's three rounds matched.
- **Candidates:** run `plan check` after step 4; or make the note independent of whether the matrix exists (for example "0 Done requirements to compare").
- **Source:** the M7 demo, Phase A (`factory-sandbox-m7-md` Planning PR #1, 2026-10-26) and Phase B (`factory-sandbox-m7-pdf` Planning PR #1, 2026-10-27): in both, `diff` of the embedded and the fresh output shows only the 3 lines of the `Notes:` block. [S05](../stations/S05-stories.md) steps 3–4. Not fixed during the demo, by the human's instruction.
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-44"></a>B-44 Returning from an S11 stop to S09 is not described, and S09 cannot re-verify an unchanged commit
- **What:** two gaps, both met on Task Tracker #41.
  - **After an answered S11 question.** When `pr render` stops S11 (here on rule H3) and the human answers, the state engine names S11 again, which would hit the same problem: the fix is a change to the branch, which only S08 or S09 make. S11 documents `--station S11 --next S09` only for two cases, new `<D>` commits (step 1) and a failed final-commit check (step 7). The assistant used that hand-back for the answered question too, and said so.
  - **Re-verifying a commit that has not changed.** After S11 step 7 failed on a flaky run, S09 had to verify the same commit again. S09 step 3 always commits a `.factory/log.md` line before `verify run`, which would move the branch off the commit to be verified. The assistant skipped that commit for this run, so the log has no line for it.
- **Candidates:** S11's stop conditions say that, once a `pr render` question is answered, the station records S11 → S09; and S09 skips its step-3 commit when the story's tests are unchanged and only the evidence is missing for the branch head.
- **Source:** the M7 demo, Phase C (Task Tracker #41 and PR #42, 2026-10-28); [S11](../stations/S11-pr.md) steps 1, 4 and 7; [S09](../stations/S09-test.md) step 3
- **Status:** verified · **Owner:** unassigned · **State:** open

## M6 demo findings

Found while running the M6 demo on Task Tracker, increment `003-priority-filter` ([progress.md](progress.md#m6-deterministic-verification--review)). The recurrence of [B-18](#b-18) is recorded on that item.

### <a id="b-29"></a>B-29 S11's Done check cannot pass after a rework round
- **What:** in rework mode, S11 step 6 (the traceability commit) is skipped because the rows already list `#<P>` from the first run, so S11 makes no commit and the story branch's head carries S09's (or S08's) trailer. S11's Done check still requires `git -C <T> log origin/<B> -1 --format=%B` to show `Factory-Station: S11`, which cannot hold. The state engine reports `GATE_B_WAITING_REVIEW` regardless, so nothing is blocked; only the checklist is wrong. The same skip leaves the rows' test names stale when a rework renames tests (REQ-027 and REQ-028 on Task Tracker).
- **Source:** the M6 demo, point 4 (PR #37, rework round 1); [S11](../stations/S11-pr.md) step 6 and Done check
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-30"></a>B-30 A `Changed test:` line must give a full path for a change outside any test
- **What:** `prbody.changed_tests` matches a change outside any test (an import, a locator helper) by checking that the declared text contains the file's full path. `Changed test: due-date-priority.spec.ts …` did not match `tests/e2e/due-date-priority.spec.ts`, so `pr render` reported rule H3 problems, and also warned that the declared line named no change. [S09](../stations/S09-test.md) step 2 does not say that a full path is needed. Candidates: say so in S09, or also match by file name.
- **Source:** the M6 demo, point 2: S11 stopped and asked on Task Tracker #34; the human approved an empty commit (`3f48c51`) with full-path lines; `scripts/factory/prbody.py` (`changed_tests`)
- **M7 demo, Task Tracker #41 (2026-10-28):** a related case, with a different cause. The S09 commit `03aabd8` widened the existing import on line 2 of `src/app/controller.test.ts`, a modified line outside any test, and wrote no `Changed test:` line at all. `pr render` stopped with "rule H3: a line outside any test in `src/app/controller.test.ts` changed without a `Changed test:` line", and S11 asked on #41. The human chose to avoid the change rather than declare it (#41, 2026-10-28T06:53:43Z): `fad92c6` restored the line and added the new imports on a separate line, which the rule does not count. A second stop-and-ask round in two demos for an import line. Candidates, besides those above: S09 step 2 could say that an edited import is a change to declare, or the rule could treat a widened import as an addition.
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-31"></a>B-31 No factory path for changing an acceptance criterion after Gate A
- **What:** a Gate B `/changes` renamed a label that AC1 and AC2 name. The AC verifier, which sees only the issue's criteria and the diff, correctly failed AC1, and S08 had to stop and ask, because the only "fix" would have undone the feedback. At the human's request, AC1 and AC2 were edited on the issue. STORY-015 in the approved `05-stories.md` on the target's `main` and two test names in `traceability.md` are now out of date, and no station records or reconciles such a change. Needs a decision: how a rework that changes an approved criterion updates the issue and the planning documents (for example a small planning PR, or S11 carrying the document changes).
- **Source:** the M6 demo, point 4 (the question and the human's decision on Task Tracker #34; PR #37)
- **Status:** verified · **Owner:** unassigned · **State:** open

### <a id="b-32"></a>B-32 Vitest sometimes cannot start a worker on a cold start
- **What:** on the Windows machine used, the first `npm test` after a pause sometimes fails before Playwright runs: Vitest reports `Failed to start forks worker for test files …/src/ui/render.test.ts` (`Timeout waiting for worker to respond`), that file does not run, and every test that ran passes. `verify run` then records `test fail`, which can spend a fix attempt. Every rerun has passed. It is environmental, on the target's side (Vitest's pool), but the factory cannot tell such a failure from a real one.
- **Source:** the B-26 integration (Task Tracker PR #31, 2026-10-22); the M6 demo, point 2 (`verify run` on `383ae7a`); the M7 demo (below)
- **M7 demo, Task Tracker #41 (2026-10-28):** S11 step 7's `verify run` on `88cb913`, a commit that changed only `traceability.md` and the log, failed the same way: 131 of 131 tests that ran passed, there was `1 error`, and Playwright did not run. The same code had passed twice on `fad92c6`. The factory recorded S11 → S09 and stopped rather than retry. On the human's go-ahead (`858cb907#1969`), the re-run on the same commit passed: Vitest 169, Playwright 94. No fix attempt was spent, because S11 sends the story back to S09 and does not count it.
- **Status:** observed · **Owner:** unassigned · **State:** open

### <a id="b-33"></a>B-33 Q7 Size counts the factory's own `.factory/log.md` lines
- **What:** `pr render` counts every changed line toward Q7, including the `.factory/log.md` line that each station run appends. A rework round therefore adds lines that no reviewer needs to read: PR #37 went from 397 to 401 of 400 lines through log lines alone, and Q7 warned (a warning, not a stop; see Accepted limitations, T6.3). Candidate: leave `.factory/log.md` out of Q7, as generated files are.
- **Source:** the M6 demo, point 4 (PR #37, `pr render`)
- **Status:** verified · **Owner:** unassigned · **State:** open

## Earlier findings assigned by the roadmap

The roadmap's open-findings table ([05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "Open findings from M2–M5") assigns these to tasks. They are listed here with their current state; the full descriptions are in [progress.md](progress.md).

| ID | Finding | Owner | State |
|---|---|---|---|
| <a id="b-18"></a>B-18 | The ID scanner counts mentions in the docs (M2 Problem 4, M5 follow-up 1) | T7.1 | **resolved** by [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50) (T7.1), merged as `5cc0e27`; pinned by `ProseMentionRegressionTest` (the M5 and M6 notes). History: in M5 the docs were reworded so that they mention no unallocated ID ([progress.md](progress.md), M5 record). The assistant restated this as an interim practice (`1bcf8818#1057`): keep literal `REQ-`/`STORY-` numbers out of prose under the target's `docs/factory/`, and check `increment show` before S05. This is guidance, not a recorded human decision. It struck again in the M6 demo (2026-10-23): the S01 analysis named the next free IDs, and `increment show` skipped to `REQ-028`; rewording the line in a follow-up S01 commit restored `REQ-027` ([progress.md](progress.md#m6-deterministic-verification--review)). T7.1's fix: only the IDs named in an increment's `02-requirements.md` or `05-stories.md` (in the working tree and at every Planning PR's head commit) and labelled story issues allocate. A mention anywhere else is only a warning ([task-log.md](task-log.md#t71-id-allocation-from-structured-sources-only)). **M7 demo (live):** after S01 committed an analysis and a knowledge base mentioning ten existing IDs in prose, `increment show` still gave `REQ-037`, `STORY-018`, with no warnings; both sandboxes started at `REQ-001`/`STORY-001` ([progress.md](progress.md#m7-plans--target-knowledge)). |
| <a id="b-19"></a>B-19 | Stale story markers without the label (M4 follow-up 1) | T7.1 | **resolved** by [PR #50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50) (T7.1, on merge): a marker counts only on an issue with the `factory:story` label, for IDs and for the next increment number; an unlabelled one is a warning |
| <a id="b-20"></a>B-20 | A PRD in `docs/` triggers S01 (M2 Problem 2, M4 follow-up 2) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge). The detection logic had already ignored `docs/**` and documents since T5.2 ([PR #32](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/32)). T7.2 adds a fixture for each layout and closes the remaining false positives: `.git*` files, root licence/notice/changelog/authors files, `CODEOWNERS`, `.editorconfig`, and the `.claude/`, `.vscode/` and `.idea/` folders; HTML still counts as code outside `docs/` (a static site). Live proof: the M7 demo ([task-log.md](task-log.md#t72-intake-and-project-detection)). **Shown (2026-10-26/27):** both sandboxes, holding only `README.md` and `docs/prd.md` or `docs/prd.pdf`, routed S00 → S02 ([progress.md](progress.md#m7-plans--target-knowledge)). |
| <a id="b-21"></a>B-21 | A PDF PRD can't be "copied unchanged" (M2 Problem 3) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge): S00 copies Markdown unchanged, gives a text file or a transcribed PDF a `<!-- factory:prd-source` header ([templates/README.md](../templates/README.md), "PRD source header"), and stops and asks for any other format or for a PDF whose requirements cannot be reproduced as text. Live proof: the M7 demo. **Shown (2026-10-27):** `00-prd.md` of `factory-sandbox-m7-pdf` starts with the header; its `Blob` equals `git hash-object docs/prd.pdf`; 518 of 518 words match the PDF text, and 42 of 42 non-blank lines match the approved Markdown apart from the declared inline styles ([progress.md](progress.md#m7-plans--target-knowledge)). The stop-and-ask path for an unreadable PDF was not exercised. |
| <a id="b-22"></a>B-22 | S00 runs `doctor` before `labels ensure` (M2 Problem 1) | T7.2 | **resolved** by [PR #51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51) (T7.2, on merge): S00 runs `labels ensure` first, then `doctor`; `/factory-target` says that missing labels alone are created by `/factory-start`. Live proof: the M7 demo. **Shown (2026-10-26/27):** on both new sandboxes, `labels ensure` reported `9 created` before `doctor`, which then reported `labels OK`, with no manual step ([progress.md](progress.md#m7-plans--target-knowledge)). |
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
| T7.4 | `plan check`'s overlap score is lexical. A paraphrase in other words ("deadline" for "due date") is missed. Parallel wording is flagged: on the real plans, Task Tracker's REQ-034 ~ REQ-019 (both "reflected … within 100 ms of the user's action") scores 0.529, a known false positive that needs one Open question. The stop words and the singular rule are English. Every flag is a question for the human, never a verdict | [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection) (P-C) |
| T7.4 | A potential overlap is resolved only by an explicit record with literal IDs: `- <done>: changed by <new>` under `## Changed or retired requirements`, or a question (a list item with `?`) naming both IDs under `## Open questions`. A range such as "REQ-022 to REQ-026" does not name REQ-025. The check sees that a question was recorded, not whether it is a good one; the human judges that at Gate A | [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection) (P-C, review of PR #53) |
| T7.4 | The `- Files:` estimates are model-written, so the plan-time size check is only as good as the estimate; Q7 at Gate B still measures the real diff | [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection) (P-A) |
| T7.4 | "Done" for the overlap check is the local matrix's `Implemented` status, not GitHub's record of merged PRs, which `/factory-status` uses | [task-log.md](task-log.md#t74-plan-lint-and-overlap-detection) (P-B) |
