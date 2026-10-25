# Task log

| | |
|---|---|
| **Status** | Living record, updated by each task's PR |
| **Scope** | T6.1 onwards. Tasks T0.1–T5.4 are covered by [03-factory-plan.md](03-factory-plan.md), their PRs and the milestone records in [progress.md](progress.md). |
| **Specifications** | M0–M5: [03-factory-plan.md](03-factory-plan.md). M6–M9: [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md). |
| **Open items** | [backlog.md](backlog.md) |

## What this log is for

The roadmap states what each task must do. This log records **what happened when it was built**:
- the specification the task followed;
- the decisions the human approved;
- any deviation from, or addition to, the specification;
- the review findings and how each was handled;
- the PR and commits, and the verification evidence;
- the items handed on to later tasks.

The specifications themselves are never edited to match. A deviation is recorded here, with its source, and the original text stays as it is.

Each entry is taken from its PR description and from the session in which the human made each decision. Nothing here is inferred.
- **"Approved"** means the human stated the decision, in that session or in the PR.
- **"Analysis"** marks a finding that was identified but not yet decided.

**Sources.** PR links point to GitHub. Decisions made in a Claude Code session are cited by session ID, entry index (0-based line index in the session's JSONL log) and UTC timestamp, for example `12c41339#617, 2026-10-08T11:15:53Z`. The session logs are not part of the repository; this log records what was decided there, so they are not needed to use it.

| Session | Full ID | Used for |
|---|---|---|
| `1bcf8818` | `1bcf8818-42c6-44aa-82e5-e187c8b50c7e` | Roadmap (2026-10-08), sequencing decision, T6.1 |
| `12c41339` | `12c41339-9a82-42b9-8504-24909a76cbea` | T6.2, T6.3 |
| `c878c238` | `c878c238-890e-4dd2-a905-6956ecf1b25d` | T6.4, T6.5 preparation, documentation migration |
| `c161a4ca` | `c161a4ca-39de-4e3c-bad1-4ee8caeeadcb` | Documentation migration PRs C and D, T6.5 |
| `34ce5c38` | `34ce5c38-2316-4d05-b39a-d5a5cf9b33bc` | T7.1, T7.2, T7.3 |

---

## Roadmap-level decisions

| Decision | Source |
|---|---|
| **Strictly sequential order**, T0 → T1 → … → T9; every task stays in its own milestone. The roadmap's closing recommendation to pull T9.1 and T7.1 forward is **rejected**. Dependency problems are handled when that milestone is reached. | Approved: `1bcf8818#1053`, 2026-10-08T06:36:54Z. Recorded in the header of [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md). |
| **The roadmap is committed verbatim**, and later decisions are recorded separately (here and in the backlog). | Approved: `c878c238#1586`, 2026-10-21T16:53:43Z. Delivered by [PR #40](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/40) (merge `2d95b7c`). |

---

## T6.1 Evidence ledger: `factory.py verify run`

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T6.1 Evidence ledger" |
| **PR** | [#36](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/36), merged 2026-10-08T09:19:27Z, merge commit `dda1aed` |
| **Commits** | `b25bb57` (implementation), `83411f1` (review fixes) |
| **Status** | Done |

**Approved decisions** (`1bcf8818#1503`, 2026-10-08T08:42:57Z, after the review question at `1bcf8818#1445`):
1. **The executor runs the language the guard checks.** Configured commands run with bash on every platform (on Windows, Git for Windows' own `bin/bash.exe` next to `git.exe`, never a `bash` on `PATH`). A command using cmd.exe-only syntax (`^`, `%VAR%`, `!VAR!`, `call`) is refused before anything runs.
2. **Only approved commands run.** Commands come from `.factory/config.json` on the default branch on `origin`, which only a merged PR changes. A `commands.*` entry that the story branch changes is not run, and `verify check` rejects the evidence.
3. **The older guard gaps are left for T9.5:** computed arguments, inherited environment variables, and indirect execution. No credential stripping or other broad security change.

**Additions to the specification:** decisions 1 and 2 go beyond the roadmap's Build list; the human requested both as review fixes. The roadmap's three acceptance criteria are unchanged.

**Review findings:**
- **Found:** the first version vetted commands as bash but ran them with cmd.exe on Windows, and it read the commands from the editable working tree.
- **Fixed** in `83411f1`, with regression tests. Mutation checks: 16 failing subtests without the cmd-syntax refusal, and 7 failures with the branch config trusted instead.

**Verification** (PR #36):
- `python -m unittest`: 657 tests, OK (4 skipped), in Git Bash and in PowerShell.
- `ruff`: clean in both shells.
- A live, read-only run against the Task Tracker checkout at `1661f63` from both shells: every configured command passed, with an approved `config_source`.

**Handed on:**
- **T6.5:** the walking-skeleton story's commands are unapproved until its PR merges ([backlog B-01](backlog.md#b-01)).
- **T9.5:** the guard gaps ([B-09](backlog.md#b-09), [B-10](backlog.md#b-10), [B-11](backlog.md#b-11)).
- Credentials are not stripped from the commands' environment ([B-15](backlog.md#b-15)).

---

## T6.2 Deterministic AC ↔ test mapping

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T6.2 Deterministic AC ↔ test mapping" |
| **PR** | [#37](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/37), merged 2026-10-08T11:33:21Z, merge commit `2acc3d8` |
| **Commits** | `43ef2ed` (implementation), `1b937f6` (review fixes) |
| **Status** | Done |

**Approved decisions** (`12c41339#617`, 2026-10-08T11:15:53Z):
1. **The AC-to-test map is mandatory** in `verdict check`. It must be beside the evidence it was built from, for the branch the checkpoint names, and for that branch's head on `origin`.
2. **S10/S11 stop fail-closed until T6.5 is accepted.** No station runs `verify run` or `verify map` before T6.5, so between T6.2 and T6.5 a live S10 reports `INVALID` and stops with `factory:needs-human`. Station wiring was not pulled forward.
3. **The evidence half of checkpoint forgery is closed in T6.2.** This **intentionally changes T6.1 behaviour**: a checkpoint note may carry existing evidence and map blocks, but may not supply its own.
4. The escape hatches `verdict check --map` and `verify map --evidence` are removed. Local files are trusted only through the SHA-256 recorded in the checkpoint's evidence.

**Deviation:** none from the roadmap's text. Decision 3 changes behaviour delivered by T6.1, as approved.

**Review findings:**
- **Not approved as first submitted** (`12c41339#590`, 2026-10-08T11:09:57Z). The four refusals the roadmap requires held only when a map was already stored, and three trust gaps were open: a checkpoint note could supply blocks, `--map` was accepted, and `--evidence` was trusted.
- **Fixed** in `1b937f6`. Mutation checks: accepting a missing map gives 5 failures, ignoring the branch head 3, allowing blocks in notes 5.

**Verification** (PR #37):
- `python -m unittest`: 715 tests, OK (4 skipped), in Git Bash and in PowerShell.
- `ruff`: clean in both shells.
- The real Task Tracker #27/#28 fixtures pass, and the doctored cases (a missing test, a failing test, a false pass) are rejected.

**Handed on:**
- **T6.5:** wire `verify run` / `verify map` into the stations, which ends the interim stop ([B-02](backlog.md#b-02)).
- Known limitations are accepted and listed in the backlog.

---

## T6.3 Deterministic PR body: `pr render` / `pr check`

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T6.3 Deterministic PR body" |
| **PR** | [#38](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/38), merged 2026-10-08T12:45:25Z, merge commit `f5f00ea` |
| **Commits** | `0545759` (implementation), `2075c53` (review fix) |
| **Status** | Done, with one recorded deviation (Q6) |

**Approved decisions** (`12c41339#927`, 2026-10-08T11:44:42Z):
1. **Q6 "option 1":** no `areas` field is added and the story contract is unchanged. Q6 reports **"Not checked: the story contract declares no areas"** with the list of files touched. The row is factory-owned and reproducible, the model never writes it, and `pr check` fails if it is falsified.
2. The rest of T6.3 ships in the same PR: Q1–Q5, Q7, Q8, dependency and changed-test detection, the model-owned Summary, Risks and Follow-ups, and the #29/#30 snapshots.

**Deviation from the specification:** the roadmap's Build says "**Q6 scope:** the files touched, checked against the story's declared areas". The story contract declares no areas, so Q6 is **not checked**. The roadmap's T7.4 also assumes per-story "declared files". Where declared areas come from is open ([B-08](backlog.md#b-08)).

**Review findings:**
- **Not approved as first submitted** (`12c41339#1298`, 2026-10-08T12:18:54Z). Rule H3 missed an existing test that changes only by gaining lines, which fails the acceptance criterion "A changed existing test that has no `Changed test:` line is flagged".
- **Fixed** in `2075c53`. An added line inside a test that existed at the base now counts as a change to that test; new test files, new tests, blank lines and additions outside any test do not.

**Verification** (PR #38):
- `python -m unittest`: 771 tests, OK (4 skipped), in Git Bash and in PowerShell.
- `ruff`: clean in both shells.
- The snapshot tests for PR #29 (with its two changed tests) and PR #30 pass. The mutation checks are listed in the PR.

**Handed on:**
- **T6.5:**
  - S11 commits the traceability rows after opening the PR, which moves the branch head past the evidence ([B-03](backlog.md#b-03)).
  - The rendered body is the whole body, so anything appended to it, such as an attribution line, makes `pr check` fail ([B-04](backlog.md#b-04)).
- **T7.4 or a roadmap change:** the Q6 declared-areas gap ([B-08](backlog.md#b-08)).

---

## T6.4 Review experience and traceability

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T6.4 Review experience and traceability" |
| **PR** | [#39](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/39), merged 2026-10-21T12:28:26Z, merge commit `61d71bb` |
| **Commits** | `5b95fde` (implementation), `0912332` (review fixes) |
| **Status** | Done, with one recorded deviation (the timed walk) |

**Approved decisions** (`c878c238#106`, 2026-10-21T09:11:04Z):
1. **Finding the PR:** GitHub's commit-to-PR API, with a deterministic fallback for merge commits. Standard library only, using `gh`.
2. **PRD traceability:** print both the PRD section heading and the REQ's traceability-matrix row.
3. **Target:** `trace` runs against the active target, with local git and `gh`. Tests run offline, on temporary git repos and recorded GitHub CLI answers.
4. **S12 close-out:** increment completion is decided in `closeout.py`. The `/factory-start` instruction appears only when no open story remains. Both cases are tested.
5. **Missing evidence:** at Gate B, `/factory-status` shows "no evidence recorded" rather than failing, because T6.5 has not wired the stations yet.
6. **Timing:** `trace` reports its own elapsed time. The timed walk by a human reviewer stays in the M6 demo, not in T6.4's acceptance.

**Deviation from the specification:** the roadmap's findings table assigns the "Timed traceability walk-through, success criterion 6 (M5)" to T6.4. By decision 6, T6.4 delivers the one-command `trace` and its own elapsed time. The **timed human walk is deferred to the M6 demo**, which the roadmap's M6 demo also lists, as item 5.

**Additions:** `--ref` and `--json` options on `trace`, and GitHub-error handling (review fix 3).

**Review findings** (review requested at `c878c238#833`; fixes requested at `c878c238#900`, 2026-10-21T11:56:52Z):

| Finding | Severity | Outcome |
|---|---|---|
| `increment_complete` counted only open stories, so a story closed by hand without `status:done` made close-out say `/factory-start` while the state engine reported `NEEDS_HUMAN` | Medium | **Fixed** in `0912332`. It now uses the state engine's rule (every other story closed and `status:done`), with a regression test that cross-checks the state engine. |
| A Git Bash absolute path (`/c/…`) was not recognised on Windows | Low | **Fixed** in `0912332` (`trace.from_git_bash`), with tests |
| Every HTTP 404 from the commit-to-PR API was treated as "no PR" | Low | **Fixed** in `0912332`. Only HTTP 422 "No commit found for SHA" means the commit isn't on GitHub, and then the fallback is not used. Any other error stops with the reason. Tests added; docs no longer claim live squash/rebase support. |

The final review (`c878c238#1216`, 2026-10-21T12:15:58Z) found no blocking issue. Three nits were **accepted and not fixed**:
- Close-out finds stories by their marker, while the state engine lists them by the `factory:story` label. They can differ for a story whose label was removed; close-out then errs towards "continue".
- `trace /c:12` becomes the bare drive `C:` and fails with a blame error. Normal inputs are unaffected.
- One sentence in the PR description was inaccurate (it said "both other 002 stories"). The PR description has since been corrected.

**Verification** (PR #39):
- `python -m unittest`: 808 tests, OK (4 skipped), in Git Bash and in PowerShell.
- `ruff`: clean in both shells.
- Offline: `trace` reaches the REQ, PRD and matrix row for the first and last line of every hunk of PR #29 (31 lines) and PR #30 (7 lines), on a clone of the real Task Tracker history.
- Live: traces of PR #29, #30 and #25 lines (about 2–4 s each), and a correct broken-hop report for a commit with no PR.
- Merge-commit, squash and rebase histories are tested offline.

**Handed on:**
- **M6 demo:** the timed human walk (success criterion 6).
- **Not verified live:** squash and rebase merges ([B-16](backlog.md#b-16)).

---

## T6.5 Stations S09–S11 use the verification engine

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T6.5 Stations S09–S11 use the verification engine" |
| **PR** | [#44](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/44), not merged |
| **Status** | In review |

**Approved decisions** (`c161a4ca#426`, 2026-10-22T07:52:22Z; each was the recommended option of a question listing the alternatives):
1. **B-03, B-06: re-verify in S11.** Merging new default-branch commits sends the story back to S09, since the code changed: the commands run again and the AC verifier runs again. For the traceability commit, which needs the PR number, S11 opens the PR from a first render, commits the rows, runs `verify run` and `verify map` again, re-checks the verdict, renders again, edits the PR and runs `pr check`. No engine guard ties the verdict to the documentation-only commit (the option that added one was not chosen). The matrix format is unchanged.
2. **B-04: the attribution line is in `templates/pr.md`.** It is factory-owned and rendered, so `pr check` still compares the whole body, and nothing is appended after rendering. The #29/#30 snapshots change by that line.
3. **B-05: `pr render --stuck`.** A stuck story's draft PR is rendered from the evidence and the map; with no verdict, the AC section says the verifier did not run and Q5 fails. The model writes only Summary, Risks and Follow-ups. Rule H2 (a draft PR) is kept.
4. **B-01: verify after the merge.** A command that is `null` in the approved config and set by the story branch is **pending**: vetted like the others but not run. The PR shows its gate as `Not run`, and S12 runs `verify run` on the default branch after the merge approves it, stopping with `factory:needs-human` if it fails. ADR-0004 is unchanged: no command runs before a human approved it. A command the branch changes or removes is still rejected.

**Proposed in the PR, for the human's review** (not asked before implementation; B-07 asks where "rule H1 is enforced by code wherever it can be"):
- the station lint the roadmap names: S09–S11 may not ask the model to run a configured command, keep a result line, fill a template placeholder or write a gate result (`tests/test_stations.py`, `HAND_WRITTEN`);
- `factory.py pr` refuses a story PR body (`factory:pr`) that is not a fresh `pr render` of the recorded facts, apart from Summary, Risks and Follow-ups.

**Deviation from the specification:** none from the roadmap's Build. Decision 4 also applies to any command a story introduces, not only the walking skeleton's, because the engine cannot tell the two apart.

**Changed existing tests** (each pinned the behaviour these decisions replace):
- `tests/test_evidence.py` `test_a_command_added_on_the_branch_is_not_run`: an added command is now pending, not unapproved (decision 4).
- `tests/test_closeout.py` `test_inspect_reports_and_changes_nothing`: the report gains `verify_after_merge` (decision 4).
- `tests/test_stations.py`: `test_s11_brings_the_branch_up_to_date_and_re_tests_before_the_pr`, `test_s11_pr_follows_the_template_and_copies_the_verdict_unchanged` and `test_skipped_gate_wording_matches_the_template_contract` asserted the hand-written steps this task removes (decisions 1 and 3, and the roadmap's lint).
- `tests/fixtures/prbody/29.md` and `30.md`: the footer line (decision 2).

**Handed on:**
- The stations pass no `--report` to `verify run`. With Vitest's default reporter, an AC covered only by unit tests has no passing mapped test, so its `pass` is `INVALID` ([B-26](backlog.md#b-26)). This is likely to matter in the M6 demo on Task Tracker.
- The stuck path on a PR that is already ready for review (a rework that gets stuck) leaves it ready, because `--draft` applies only when a PR is created ([B-27](backlog.md#b-27)). This was already so before T6.5.

---

## T7.1 ID allocation from structured sources only

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T7.1 ID allocation from structured sources only" |
| **PR** | [#50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50), not merged |
| **Status** | In review |

**Approved decisions.** The questions were raised in `34ce5c38#146` (2026-10-25T07:47:22Z). Option C was approved in `34ce5c38#165` (2026-10-25T08:06:58Z), and implementation was approved in `34ce5c38#189` (2026-10-25T09:35:48Z), with the M5 test required to warn about both IDs.
1. **D1, Option C: records at every Planning PR's head commit allocate IDs.**
   - **What is read:** the PR's increment's `02-requirements.md` and `05-stories.md`, at its `headRefOid`, through the GitHub API by SHA (`repos/<repo>/commits/<sha>`, then `contents/<path>?ref=<sha>`). This applies to every PR with a planning marker, open, merged or closed, so an abandoned plan's IDs are never reused, even after its source branch is deleted.
   - **What does not allocate:** a Planning PR body.
   - **Fallback:** if a plan's records cannot be read, every ID in its body counts, with a warning naming the PR, the short SHA and the reason. The fallback applies when the head SHA is missing, when the commit request fails, when a file request fails with anything but a 404, when the response is not base64 file content, or when the content cannot be decoded. It can only count more IDs, never fewer.
   - **Missing files:** a file missing (404) from a readable commit has no records and is not an error.
   - **Rejected options:** Option A (abandoned plans' IDs may be reused) and Option B (count the stories table of closed Planning PR bodies) were both rejected.
2. **D2: the record files.** As approved before implementation, D2 counted only the record forms: `^\s*-\s+\*\*REQ-###\*\*` in `<NNN-slug>/02-requirements.md`, and `^###\s+STORY-###` in `<NNN-slug>/05-stories.md`. **It was amended by the pre-merge review (below):** every `REQ-###` and `STORY-###` named anywhere in either record file is allocated.
   - **Where:** only in folders that are valid increment names, in the working tree and at every Planning PR's head commit.
   - **What does not allocate:** `00-prd.md` (even with its own bold REQ bullets), the `01`, `03` and `04` documents, `traceability.md` and other folders.
3. **D3: the label filter.**
   - **What changes:** a story issue's marker counts only when the issue has the `factory:story` label (case-insensitive), as the state engine lists stories. This applies to ID allocation and to the next increment number.
   - **What doesn't:** the refusal checks (`_blockers`, "stories without issues") are unchanged.
4. **D4: warnings.**
   - **Mentions:** every `REQ-`/`STORY-` match in any `*.md` under `docs/factory/`, in any Planning PR body, and in the marker of an issue without the label.
   - **Warning lines:** each mentioned ID that is not allocated gives one warning, naming every source. These are sorted by ID, and the fallback warnings follow them.
   - **Where they appear:** `warnings` is added to the JSON of `increment show` and `increment next`, and as `Warning:` lines in the text output. Exit codes are unchanged.
5. **D5: no station changes.**

**Interpretation:** the roadmap's "in increment docs" is read as the record files at any published planning commit, not only in the local working tree. Architecture §5.2 keeps "IDs are global and never reused"; its "Next IDs" and "Next increment" bullets were rewritten to match, and a bullet on warnings was added (Definition of Done item 7).

**Deviation from the specification:** one, from the pre-merge review. The roadmap lists "`**REQ-###**` requirement bullets and `### STORY-###` headings in increment docs". T7.1 allocates every ID named in the two record files, which includes those bullets and headings but goes beyond them. The roadmap text is unchanged.

**Pre-merge review** (`34ce5c38#646`, 2026-10-25T11:05:49Z): with the record forms of D2, an ID dropped at Gate A could be handed out again.
- **Why:** S05 revision mode moves a dropped requirement or story to `## Out of scope`, as a plain bullet. A dropped story must also lose its `### STORY-###` heading, or `issues sync` would create its issue. When the dropped ID was the highest, the next increment reused it, with only a warning. On `main` at `5c2e9a7` that prose mention had still counted, so this was a regression.
- **Reproduced:** REQ-005 and STORY-003 were dropped at Gate A. `main` gave `REQ-006 STORY-004`, and the reviewed PR head `24e59be` gave `REQ-005 STORY-003`.
- **Fixed:** Option 1 was chosen (`34ce5c38#739`, 2026-10-25T11:13:16Z) over changing S05's rule (which would break D5) and over reading every commit of a Planning PR. Every ID named in `02-requirements.md` or `05-stories.md` is allocated. A stray mention inside a record file now uses up an ID, which errs in the safe direction. A requirement bullet in any form (`*`, a numbered list) is also allocated.
- **After the fix:** the same case gives `REQ-006 STORY-004`. AC1, AC2, the abandoned-plan behaviour and the fallback are unchanged. The read-only Task Tracker run still gives `REQ-037, STORY-018`, with no warnings.

**Other decisions in the session:**
- **The target was deactivated before starting.** Task Tracker was still the active target, so rule S3 applied. With approval (`34ce5c38#205`, 2026-10-25T09:44:39Z), `.factory-local/target.json` was removed, and the gitignored `.claude/settings.local.json` was left in place.
- **The live sandbox check was declined.** It would have needed GitHub writes: close a Planning PR, delete its branch, then run `increment show` (`34ce5c38#481`, 2026-10-25T10:44:41Z). Reading after branch deletion is covered by a fake-GitHub unit test, and the live check is open as [B-35](backlog.md#b-35).

**Verification:**
- **Before and after, on the incidents** (the old code is `main` at `5c2e9a7`):
  - AC1 (M5 note): before, `REQ-027 STORY-014`; after, `REQ-027 STORY-013`, with a warning for STORY-013.
  - AC2 (M4 markers): before, `901-initial STORY-9251317`; after, `001-initial STORY-001`, with a warning for each issue.
- **A read-only run against Task Tracker's GitHub** (no target activated, nothing written): the records of Planning PRs #1, #26 and #33 were read at `e2babf0`, `88900ec` and `36a17e4` (REQ-001..036, STORY-001..017). The result was `Next IDs: REQ-037, STORY-018`, with no warnings.

**Changed existing tests** (each pinned the behaviour T7.1 replaces), all in `tests/test_increments.py`:
- `test_reads_increments_ids_and_stories`: `REQ-013` in `traceability.md` and `REQ-500` in a non-increment folder are now mentions, not IDs.
- `test_word_boundaries`: prose in `docs/factory/x.md` is now a mention.
- `test_ids_from_issue_markers_and_planning_pr_bodies_count` became `test_ids_from_planning_records_and_labelled_issues_count`: a PR body no longer allocates, and the plan's records do.
- `test_increment_seen_only_in_issue_markers_is_not_current`: the issue now carries the label. Without it the number is no longer kept (AC2, `M4RegressionTest`).
- `CollectRemoteTest.test_reads_branches_planning_prs_and_story_issues` and the `CliTest` fixtures: Planning PRs have a head commit with record files, and story issues carry the label. `test_next_allowed_json` expects `"warnings": []`.
- `test_record_forms` (added by this PR, then changed by the pre-merge review) became `test_every_id_named_in_a_record_file_is_allocated`. It had pinned the bullet and heading forms that Option 1 replaces.

**Regression tests for the pre-merge finding** (`GateADropRegressionTest`):
- a requirement dropped at the highest ID;
- a story dropped at the highest ID, recorded in either Out of scope section;
- both dropped, with the records read only at the merged Planning PR's head commit.

In every case the next increment reuses neither ID, and there are no warnings.

**Known limitation:** only a Planning PR's final head is read, and only the two record files allocate. An ID that is deleted from both record files altogether, instead of being moved to `## Out of scope` as S05 requires, can be handed out again. This is accepted ([B-34](backlog.md#b-34)).

**Handed on:**
- The B-18 interim practice (keep literal ID numbers out of prose under `docs/factory/`) was guidance only; no station states it, and D5 left the stations unchanged. It is no longer needed for correctness, since a mention now only warns. Whether S02 and S05 should report `increment show`'s warnings is left open.
- The live check of reading a closed Planning PR after its branch is deleted ([B-35](backlog.md#b-35)).

---

## T7.2 Intake and project detection

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T7.2 Intake and project detection" |
| **PR** | [#51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51), not merged |
| **Status** | In review |

**Approved decisions.** The scoping pass was `34ce5c38#971` (2026-10-25T11:41:41Z). Decisions D-A to D-F were confirmed, with the recommended options, in `34ce5c38#1092` (2026-10-25T11:57:18Z).
1. **D-A: keep T5.2's detection approach and close its gaps.**
   - **The rule:** `state.is_existing_project` still counts every file that is not known to be a document or repository metadata.
   - **Why:** an unknown file therefore means "existing project". S01 then runs needlessly, which is the safe error. Treating an existing project as new would plan over its code.
   - **Rejected:** a list of known source and build file types was not adopted.
2. **D-B: the exclusion list.** None of these count as code:
   - every `.git*` file;
   - the `.claude/`, `.vscode/` and `.idea/` folders;
   - `CODEOWNERS` and `.editorconfig`;
   - repository metadata at the root, with any suffix (`LICENSE*`, `LICENCE*`, `COPYING*`, `NOTICE*`, `CHANGELOG*`, `AUTHORS*`).

   **Narrowing:** the metadata names apply only to root-level files, so nested source such as `src/notice_service.py` or `src/changelog_parser.py` still counts as code. Everything that counted before still counts: `Makefile`, `.eslintrc.json`, `.devcontainer/**`, data files and HTML.

   **Corrected by the review of PR #51** (`34ce5c38#1395`, 2026-10-25T12:29:07Z; approved in `34ce5c38#1412`, 2026-10-25T12:31:24Z):
   - **The suffix restriction was removed.** The first implementation applied the metadata names only to suffix-less files. That kept `COPYING.LESSER`, `LICENSE-2.0` and `LICENSE.BSD` counting as code, which wrongly sends a new project to S01, the B-20 problem. A root file named like metadata is now excluded whatever its suffix. That includes a root `changelog.py`, which only matters if it is the repo's only code.
   - **`.html` and `.htm` were removed from the document suffixes.** The first implementation excluded them, so a static site (`index.html` and images) was detected as a new project and Codebase Discovery was skipped. That was a regression from `main`, and against D-A. HTML now counts as code again, except under `docs/**`. S00's intake rule for an HTML requirements file (stop and ask) is unchanged.
3. **D-C: S00 step 7 by format.**
   - `.md`/`.markdown`: copied unchanged.
   - `.txt`: copied unchanged below a source header.
   - `.pdf`: transcribed as faithful Markdown below a source header. The wording is kept; headings, lists and tables are restored; nothing is added, reordered or summarised.
   - **Stop and ask:** any other format, or a PDF whose requirement content cannot be reproduced as text.
   - **Still applies:** rules U1 and S6.
4. **D-D: the source header.** It is a `<!-- factory:prd-source` HTML comment documented in `templates/README.md` ("PRD source header"). It records:
   - the source file name;
   - its location (repo path and commit, or "outside the repository");
   - its `git hash-object`;
   - a provenance statement for the format (`.txt` copied unchanged, or `.pdf` transcribed);
   - `Not reproduced:`.

   No helper was added, and the source file is not committed.
5. **D-E: `/factory-target` wording.** A `labels` FAIL that lists missing labels is created by `/factory-start` (S00), and every other FAIL must still be fixed first. The command stays read-only.
6. **D-F: no live run.** AC2 and AC3 depend on how the model follows S00, and are proven by the M7 demo (see "Handed on").

**The S00 order (AC3):** step 1 is now `labels ensure`, and step 2 is `doctor`, stopping on any FAIL. The rest of S00 is unchanged, and `doctor` still runs again at the end. Running `labels ensure` first writes only the factory's own labels. It runs on a target that `target set` has already validated (a git repo with a GitHub remote, not the factory itself). If it fails, S00 stops.

**Interpretation, not a deviation:** the roadmap's "counts source and build files only, ignoring `*.md`, `*.pdf` and `docs/**`" is met by D-A. The documents and `docs/**` are ignored, and everything else is treated as possible source, which is the safe reading. M2 Problem 2 named both readings as fixes. **Deviation from the specification:** none.

**What T5.2 had already done:** AC1's layout (a README and `docs/prd.md`) has routed to S02 since T5.2 ([PR #32](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/32)). T7.2 adds the fixtures for it and closes the D-B gaps.

**Verification (unit level):**
- **Detection fixtures for each layout:**
  - `ExistingProjectTest.test_t72_layouts_that_are_new_projects`;
  - `ExistingProjectTest.test_t72_code_still_counts`;
  - `CollectSnapshotTest.test_readme_and_docs_prd_route_to_requirements` (AC1);
  - `CollectSnapshotTest.test_repository_metadata_does_not_route_to_discovery`;
  - `CollectSnapshotTest.test_static_html_site_needs_discovery` (review correction).
- **Station lint of the S00 step order:** `IntakeStationTest.test_labels_are_ensured_before_the_first_doctor` (AC3).
- **The intake rule and header:**
  - `IntakeStationTest.test_requirements_are_taken_by_format` (AC2);
  - `IntakeStationTest.test_the_source_header_format_is_documented` (AC2).
- **The command wording:** `CommandFileLintTest.test_target_lets_factory_start_create_missing_labels`.

Before the change, every new D-B case and lint failed, and the AC1 fixtures already passed (10 failures in 33 tests).

**Changed existing tests:** none; T7.2 only adds tests.

**Known limitation:** a root-level file named like repository metadata is excluded whatever its suffix (D-B, after the review correction), so a root `changelog.py` or `notice.ts` does not count as code. This only matters when such a file is the repo's only code. Nested files with these names still count. Accepted ([backlog](backlog.md), Accepted limitations). The HTML-only limitation of the first implementation was removed by the review correction above.

**Handed on:**
- **Live proof in the M7 demo (D-F).** The roadmap's M7 demo runs on a sandbox: a new project with its PRD in `docs/`, and a PDF variant. Both must route to S02, labels must be created by S00, and the PDF must give `00-prd.md` with a `<!-- factory:prd-source` header. T7.2's tests check the station text and the detection logic, not a model run.
- **The header is model-written and checked at Gate A.** No code checks the header's facts (D-D: no helper).

---

## T7.3 Target knowledge base

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T7.3 Target knowledge base" |
| **PR** | not yet opened |
| **Status** | In review |

**Approved decisions.** The scoping pass was `34ce5c38#1722` (2026-10-25T13:11:46Z). Decisions K-A to K-G were confirmed, with the recommended options, in `34ce5c38#1801` (2026-10-25T14:08:57Z).
1. **K-A: S01 is the only writer of `docs/factory/knowledge.md` (a deviation, recorded below).**
   - S01 reads `factory.py knowledge check --json` (read-only, local git only) and rewrites only the sections it names stale, or every section if the file is `missing` or `invalid`. It then appends one `## Changes` entry.
   - On an increment's last story, S12's close-out summary adds a **Knowledge base** paragraph: the increment's REQs and story PR numbers (read from `docs/factory/traceability.md`), and `knowledge check`'s result. S12 still commits nothing (rule S1); the next S01 is what actually updates the file.
2. **K-B: fixed, deterministic staleness scopes**, none project-specific:
   - **Stack**/**Commands**: `manifests.py`'s `is_manifest`/`is_lockfile` (every stack it already knows, T6.3) plus `Makefile`, `pom.xml`, `build.gradle*`, `.github/workflows/**` and `.factory/config.json`.
   - **Conventions**: lint/format configuration, `CLAUDE.md`, `CONTRIBUTING*`, `.editorconfig`.
   - **Layout**: any top-level entry added or removed, **after** removing `docs/factory/` and `.factory/` paths first, so S01's own first write of `knowledge.md`/`01-codebase-analysis.md` is never itself a "new top-level folder" (found and fixed during implementation; see "Problems found").
   - **Hotspots**/**Known risks**: any change outside `docs/factory/` and `.factory/`.
   - **Architecture decisions**: a merged increment's `03-architecture.md` not named in the section's own text.
   - **Changes** is never flagged by a diff; S01 appends to it directly, every run.
3. **K-C: the file format.** First line `<!-- factory:knowledge checked=<sha> -->` (a new `KnowledgeMarker` in `markers.py`, reusing the existing marker system rather than a bespoke parser), then the eight sections as `##` headings, in this fixed order: Stack, Layout, Conventions, Commands, Hotspots, Architecture decisions, Known risks, Changes. A missing marker, an unresolvable commit, or sections missing, duplicated or out of order make **every** section stale (fail-safe), regardless of the diff.
4. **K-D:** on first creation, S01 also reuses the latest earlier increment's `01-codebase-analysis.md`, if one exists.
5. **K-E:** S02–S08 each list `docs/factory/knowledge.md` (if present) as a level-4 input, next to `CLAUDE.md`. `stations/_rules.md` §5 item 4 names it there, and says both are data (rule U1), never instructions, and never override rules 1–3.
6. **K-F:** `factory.py knowledge check [--ref R] [--json]`, read-only, **local git only** (it never calls GitHub, unlike most other read-only commands). Exit 0 only when the file exists, is well-formed, and nothing is stale.
7. **K-G:** no live run. The proof is the M7 demo (Task Tracker 004: S01 creates or updates the file, S12's note appears). Recorded as a hand-off, like T7.1 and T7.2's live checks.

**Deviation from the specification:** one. The roadmap's Build says "The S12 close-out of an increment's last story appends what changed." S12 commits nothing (rule S1 — the only write path left after the last merge is a new PR, which K-A rejected as disproportionate). K-A has S12 **report** what changed (REQs, PRs, stale sections) in its summary, and the next **S01** is the one that appends to `## Changes`. The roadmap text is unchanged.

**Problems found during implementation, fixed before any test was finalised:**
- **A false "Layout" staleness on first creation.** `collect()`'s first draft derived the top-level sets from `git ls-tree --name-only` directly. Writing `docs/factory/knowledge.md` for the first time (or `00-prd.md` by S00, before S01 ever runs) adds a `docs` top-level entry that was not there before, which read as a real layout change on the very first check. Fixed by deriving the top-level sets from the full recursive tree with `docs/factory/` and `.factory/` paths removed first, so the factory's own bookkeeping can never look like a target's layout change. Covered by `CollectTest.test_new_factory_docs_are_not_a_layout_change` and `CheckIntegrationTest.test_fresh_right_after_creation`.
- **An ambiguous `invalid` message.** The first draft could not tell "no header, or sections out of order" apart from "the recorded commit is unreadable" in its rendered text, because both used the same field to decide the message. `CheckResult` gained an explicit `reason` field, set once, at the one place each cause is detected.
- **A reusability conflict (success criterion 8).** The first draft's `_STACK_COMMANDS_GLOBS` named Node.js files (`package.json`, `yarn.lock`, …) directly, which `tests/test_reusability.py` refuses outside `discovery.py`/`manifests.py` (so stack knowledge stays in one checked place). Fixed by reusing `manifests.is_manifest`/`is_lockfile` (T6.3's own canonical, multi-stack, already-audited list) instead of a second list of the same names.

**Verification (unit level):**
- **Markers:** `markers.py` gains `KnowledgeMarker`; round-trip, tolerance and malformed coverage come from the existing parametrised `EXAMPLES`/`MALFORMED` tests, plus `KnowledgeMarkerTest`.
- **Parsing and the fail-safe rule:** `tests/test_knowledge.py`, `ParseTest` (missing marker, missing/out-of-order/duplicate sections).
- **The staleness check (the roadmap's named test):** `StalenessTest`, one test per K-B scope, plus ordering and the `Changes`-is-never-flagged rule.
- **The git I/O:** `CollectTest` and `CheckIntegrationTest`, against real throwaway git repositories (no fixtures), covering the Layout fix, architecture-file filtering, an unknown commit, and `--ref`.
- **The CLI:** `CliTest`, exit codes and `--json`.
- **Station lint (the roadmap's other named test):** `DiscoveryStationTest.test_knowledge_base_is_created_or_updated` (S01) and `StoryStationsTest.test_s12_reports_the_knowledge_base_on_the_increments_last_story_only` (S12), plus the generic per-station command and output lints that already cover every station (`StationFilesTest`).
- `docs/factory/knowledge.md` added to `ALLOWED_OUTPUTS` (test support) and to architecture §5.1 and §5.5.

**Changed existing tests:** none; T7.3 only adds tests.

**Handed on:**
- **Live proof in the M7 demo (K-G).** Task Tracker increment 004: S01 must create or update `knowledge.md`, and S12's note must appear on the increment's last story.
- **The header and every section are model-written.** `knowledge check` only checks the header and the diff-derived staleness; it never checks that a rewritten section's *content* is accurate. Gate A review is the safeguard, as for `01-codebase-analysis.md` today.
