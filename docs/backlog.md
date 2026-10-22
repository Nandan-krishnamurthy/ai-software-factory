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
- **Status:** verified · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: the command is pending, not run before the merge, and S12 runs it on the default branch afterwards (decision 4 in [task-log.md](task-log.md#t65-stations-s09s11-use-the-verification-engine))

### <a id="b-02"></a>B-02 S10/S11 stop fail-closed until the stations run the engine
- **What:** `verdict check` requires the AC-to-test map, but no station runs `verify run` or `verify map` yet. On a live target, S10 reports `INVALID` and stops with `factory:needs-human`. This was accepted for the interval between T6.2 and T6.5.
- **Source:** [PR #37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), "Interim effect until T6.5 (accepted)"; approved at `12c41339#617` (see [task-log.md](task-log.md#t62-deterministic-ac--test-mapping))
- **Status:** verified · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: S09 runs `verify run` and S10 runs `verify map`

### <a id="b-03"></a>B-03 Bookkeeping commits move the branch head past the evidence
- **What:** `pr render` and `pr check` require the evidence to be for the story branch's head on `origin`, and `pr render` reads the traceability rows from the diff at the evidence commit. [S11](../stations/S11-pr.md) commits the traceability rows and a `.factory/log.md` line after opening the PR (steps 5–6). That moves the head past the evidence, so `pr render`/`pr check` must run after that commit, with `verify run`/`verify map` run again.
  - **Analysis, 2026-10-21:** [S09](../stations/S09-test.md) also commits a `.factory/log.md` line after running the commands (steps 5–6).
  - **Analysis, 2026-10-21:** the traceability row names the PR number, which exists only once the PR is open.
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Not in this PR"; the station files
- **Status:** verified (the S11 ordering); analysis (S09, and the PR-number dependency) · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: S09 commits before `verify run`; S11 records the evidence and the map again after its traceability commit (decision 1)

### <a id="b-04"></a>B-04 The rendered PR body versus an attribution footer: unresolved
- **What:**
  - **Verified:** `pr check` compares an open PR's whole body with a fresh render. Anything appended after rendering, "such as an attribution line", makes `pr check` fail; T6.3 intends this, since the template is factory-owned. This is PR #38's Limitation 6.
  - **Observed:** the Claude Code sessions that build this factory are instructed by their environment, not by a rule in this repository, to end the pull-request descriptions they create with an attribution line.
  - **The conflict:** once S11 opens story PRs with `pr render` output, the two can conflict for story PRs.
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Limitations" item 6; the conflict was raised on 2026-10-21 (`c878c238`)
- **Status:** verified (the `pr check` behaviour); observed (the attribution instruction) · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: the attribution line is part of `templates/pr.md` (decision 2)

### <a id="b-05"></a>B-05 S09's stuck path fills the PR template by hand
- **What:**
  - **Verified:** the roadmap's T6.5 requires a station lint that "checks that S09–S11 contain no hand-written gate results". [S09](../stations/S09-test.md)'s **Stuck** stop condition (step 2) tells the model to fill `templates/pr.md` by hand, where "every gate shows its real result".
  - **Verified:** `pr render` refuses to render without an S10 verdict, so it cannot produce that draft PR as it stands.
- **Source:** analysis of the committed station text and of [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38) ("`render` refuses … a missing verdict"), 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: `pr render --stuck` (decision 3)

### <a id="b-06"></a>B-06 S11 step 1 changes the branch head and re-runs the commands by hand
- **What:** [S11](../stations/S11-pr.md) step 1 merges new default-branch commits into the story branch and then re-runs the commands by hand. With the verification engine, that merge commit makes the evidence, the map and the verdict stale.
- **Source:** analysis of the committed station text, 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by the T6.5 PR: new default-branch commits send the story back to S09 (decision 1)

### <a id="b-07"></a>B-07 Where "rule H1 is enforced by code wherever it can be"
- **What:** T6.5's acceptance criterion "Rule H1 is enforced by code wherever it can be" does not say which code paths must enforce it.
- **Source:** [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), T6.5 acceptance criteria; analysis, 2026-10-21
- **Status:** analysis · **Owner:** T6.5 · **State:** resolved by the T6.5 PR, as proposed there for review: the station lint, and `factory.py pr` refusing a story PR body that is not the render

## Handed on by T6.5

### <a id="b-26"></a>B-26 The stations capture no test report, so a unit-only AC may not map
- **What:** S09 runs `verify run` without `--report`, because nothing records which report file a target's test command writes. With a runner whose default output lists no passing test by name (Vitest's default reporter), a test that passed has no result in the map. An AC covered only by such tests is `missing`, and the verifier's `pass` for it is `INVALID`, which stops S10 for the human. An AC that also has an end-to-end test listed by name is not affected.
- **Source:** [PR #37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), "Limitations" 1 and 2 (T6.2); the T6.5 station text
- **Status:** verified (the limitation); analysis (its effect on the M6 demo) · **Owner:** unassigned (likely before or during the M6 demo) · **State:** open

### <a id="b-27"></a>B-27 A stuck rework leaves a ready PR ready
- **What:** `factory.py pr --draft` makes a PR a draft only when it creates it; an existing PR keeps its state. When a story gets stuck during rework, its PR is already ready for review, so the stuck path updates its body (which states the failures) but does not make it a draft, as rule H2 asks.
- **Source:** `factory.py pr --help` ("an existing PR keeps its state"); the S09 stuck path, unchanged in this respect by T6.5
- **Status:** analysis · **Owner:** unassigned · **State:** open

## Specification gaps

### <a id="b-08"></a>B-08 Q6 scope: the story contract declares no areas
- **What:** the roadmap's T6.3 asks for Q6 to check the files touched "against the story's declared areas". The story contract has no areas field. By the T6.3 decision, Q6 reports "Not checked: the story contract declares no areas" with the files touched, so scope stays a reviewer judgement. The roadmap's T7.4 also relies on per-story "declared files".
- **Source:** [PR #38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), "Q6 roadmap gap"; decision `12c41339#927` (see [task-log.md](task-log.md#t63-deterministic-pr-body-pr-render--pr-check))
- **Status:** verified · **Owner:** T7.4, or a roadmap change · **State:** open

## Guard gaps

The roadmap assigns the M4 guard gaps to T9.5. Its T9.5 Build lists `git clone` outside the target, the `/tmp` mapping and computed verbs. B-10, B-11, B-14 and B-15 are not named in T9.5's Build, so whether they belong to T9.5 is a scope decision for that task.

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

## Verification not yet done

### <a id="b-16"></a>B-16 `trace` on squash and rebase merges against live GitHub
- **What:** `trace` relies on GitHub's commit-to-PR API listing the PR for the commit GitHub wrote. It is verified live for merge-commit merges only. Squash and rebase are tested only against GitHub-shaped answers, because the test project has only merge commits.
- **Source:** [PR #39](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/39), "Limitations"
- **Status:** verified (as a limitation) · **Owner:** unassigned · **State:** open

### <a id="b-17"></a>B-17 The timed traceability walk by a human (success criterion 6)
- **What:** `trace` gives the chain in one command, but the walk by a human reviewer has not been timed.
- **Source:** decision `c878c238#106` item 6 (see [task-log.md](task-log.md#t64-review-experience-and-traceability)); the roadmap's M6 demo item 5
- **Status:** verified · **Owner:** M6 demo · **State:** open

## Earlier findings assigned by the roadmap

The roadmap's open-findings table ([05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "Open findings from M2–M5") assigns these to tasks. They are listed here with their current state; the full descriptions are in [progress.md](progress.md).

| ID | Finding | Owner | State |
|---|---|---|---|
| <a id="b-18"></a>B-18 | The ID scanner counts mentions in the docs (M2 Problem 4, M5 follow-up 1) | T7.1 | open. In M5 the docs were reworded so that they mention no unallocated ID ([progress.md](progress.md), M5 record). The assistant restated this as an interim practice (`1bcf8818#1057`): keep literal `REQ-`/`STORY-` numbers out of prose under the target's `docs/factory/`, and check `increment show` before S05. This is guidance, not a recorded human decision. |
| <a id="b-19"></a>B-19 | Stale story markers without the label (M4 follow-up 1) | T7.1 | open |
| <a id="b-20"></a>B-20 | A PRD in `docs/` triggers S01 (M2 Problem 2, M4 follow-up 2) | T7.2 | open |
| <a id="b-21"></a>B-21 | A PDF PRD can't be "copied unchanged" (M2 Problem 3) | T7.2 | open |
| <a id="b-22"></a>B-22 | S00 runs `doctor` before `labels ensure` (M2 Problem 1) | T7.2 | open |
| <a id="b-23"></a>B-23 | The Gate A `/changes` revision round has never been demonstrated (M2, M4, M5) | M6 demo | open |
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
