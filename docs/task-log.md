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
| `1821c3de` | `1821c3de-0747-4e19-a8a9-4e9b532df1bb` | T7.4, the T7 audit and its follow-up documentation PR |
| `097efb85` | `097efb85-defc-4f51-af7e-29b021ce53d0` | The pre-T8 assessment, B-28 |

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
| **PR** | [#50](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/50), merged 2026-10-25T11:32:27Z, merge commit `5cc0e27` |
| **Status** | Done, with one recorded deviation (every ID named in a record file is allocated) |

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
| **PR** | [#51](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/51), merged 2026-10-25T13:09:27Z, merge commit `024c857` |
| **Status** | Done |

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
| **PR** | [#52](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/52), merged 2026-10-26T06:12:55Z, merge commit `1bd6218` |
| **Status** | Done, with one recorded deviation (S12 reports what changed; S01 writes it, K-A) |

**Approved decisions.** The scoping pass was `34ce5c38#1722` (2026-10-25T13:11:46Z). Decisions K-A to K-G were confirmed, with the recommended options, in `34ce5c38#1801` (2026-10-25T14:08:57Z).
1. **K-A: S01 is the only writer of `docs/factory/knowledge.md` (a deviation, recorded below).**
   - S01 reads `factory.py knowledge check --json` (read-only, local git only) and rewrites only the sections it names stale, or every section if the file is `missing` or `invalid`. It then appends one `## Changes` entry.
   - On an increment's last story, S12's close-out summary adds a **Knowledge base** paragraph: the increment's REQs and story PR numbers (read from `docs/factory/traceability.md`), and `knowledge check`'s result. S12 still commits nothing (rule S1); the next S01 is what actually updates the file.
2. **K-B: fixed, deterministic staleness scopes**, none project-specific:
   - **Stack**/**Commands**: `manifests.py`'s `is_manifest`/`is_lockfile` (every stack it already knows, T6.3) plus `Makefile`, `pom.xml`, `build.gradle*` and `.github/workflows/**`. Not `.factory/config.json` (removed by the review of PR #52, below).
   - **Conventions**: lint/format configuration, `CLAUDE.md`, `CONTRIBUTING*`, `.editorconfig`; widened by the review follow-up (below) to `tsconfig*.json`, `setup.cfg`, `.pylintrc`, `biome.json(c)`, `.rubocop*.yml`, `.clang-format` and `.clang-tidy`.
   - **Layout**: any top-level entry added or removed, **after** removing `docs/factory/` and `.factory/` paths first, so S01's own first write of `knowledge.md`/`01-codebase-analysis.md` is never itself a "new top-level folder" (found and fixed during implementation; see "Problems found").
   - **Hotspots**/**Known risks**: any change outside `docs/factory/` and `.factory/`.
   - **Architecture decisions**: a merged increment's `03-architecture.md` not linked by its path (`<NNN-slug>/03-architecture.md`) in the section's text. Before the review follow-up (below), a bare mention of the increment name counted.
   - **Changes** is never flagged by a diff; S01 appends to it directly, every run.
3. **K-C: the file format.** First line `<!-- factory:knowledge checked=<sha> -->` (a new `KnowledgeMarker` in `markers.py`, reusing the existing marker system rather than a bespoke parser), then the eight sections as `##` headings, in this fixed order: Stack, Layout, Conventions, Commands, Hotspots, Architecture decisions, Known risks, Changes. A missing marker, an unresolvable commit, or sections missing, duplicated or out of order make **every** section stale (fail-safe), regardless of the diff.
4. **K-D:** on first creation, S01 also reuses the latest earlier increment's `01-codebase-analysis.md`, if one exists.
5. **K-E:** S02–S08 each list `docs/factory/knowledge.md` (if present) as a level-4 input, next to `CLAUDE.md`. `stations/_rules.md` §5 item 4 names it there, and says both are data (rule U1), never instructions, and never override rules 1–3.
6. **K-F:** `factory.py knowledge check [--ref R] [--json]`, read-only, **local git only** (it never calls GitHub, unlike most other read-only commands). Exit 0 only when the file exists, is well-formed, and nothing is stale.
7. **K-G:** no live run. The proof is the M7 demo (Task Tracker 004: S01 creates or updates the file, S12's note appears). Recorded as a hand-off, like T7.1 and T7.2's live checks.

**Deviation from the specification:** one. The roadmap's Build says "The S12 close-out of an increment's last story appends what changed." S12 commits nothing (rule S1 — the only write path left after the last merge is a new PR, which K-A rejected as disproportionate). K-A has S12 **report** what changed (REQs, PRs, stale sections) in its summary, and the next **S01** is the one that appends to `## Changes`. The roadmap text is unchanged.

**Review of PR #52** (`34ce5c38#2761`, 2026-10-25T16:15:24Z; fixes requested in `34ce5c38#2824`, 2026-10-25T16:25:51Z): two blockers, both fixed with regression tests (`ReviewRegressionTest`), which fail on the reviewed head `52149bf`:
- **S01's Done check could not pass on an existing project's first increment.** S00 creates `.factory/config.json` on the plan branch and S01 sets its commands, so the diff from the analysed commit always contained it, and it was in the Stack/Commands scope: the freshly written file was reported stale at once. `.factory/config.json` was removed from that scope (manifests, lockfiles, `Makefile` and CI workflows stay). K-B is narrowed accordingly; K-A is unchanged.
- **A renamed manifest was reported fresh, and the result depended on the user's git config.** With rename detection, `git diff --name-only` lists only the new path, so `requirements.txt` renamed to `deps.txt` left Stack and Commands fresh, but not with `diff.renames=false`. `collect()` now passes `--no-renames`, which lists both paths whatever the config.

**Review follow-up** (`34ce5c38#2925`, 2026-10-25T16:36:57Z), non-blocking findings fixed, each with tests that fail on `edca6e7`:
- **Conventions false-fresh:** `tsconfig*.json`, `setup.cfg`, `.pylintrc`, `biome.json`/`biome.jsonc`, `.rubocop*.yml`, `.clang-format` and `.clang-tidy` now make Conventions stale (`StalenessTest.test_conventions_stale_on_other_stacks_configuration`). The list is still fixed, so a tool it does not name stays a limitation (below).
- **A bad `--ref` was reported as `missing`:** `check()` resolves `--ref` first and raises `KnowledgeError`, so the CLI prints an error and exits 1 (`test_a_ref_that_is_not_a_commit_is_an_error_not_missing`, `CliTest.test_bad_ref_is_exit_1_with_an_error`).
- **A `##` line in a fenced code block made the file invalid:** headings inside ```` ``` ```` or `~~~` fences are ignored; an unclosed fence hides the rest of the file, so it stays fail-safe (`ParseTest`).
- **A bare mention counted as an architecture link:** only a path, `<NNN-slug>/03-architecture.md`, counts now, which is what the roadmap's "with links to each increment's `03`" asks; S01 says to link by path (`ArchitectureLinksTest.test_a_bare_mention_is_not_a_link`).
- **S12** now says how to report each `knowledge check` status (`fresh`, `stale`, `missing`, `invalid`), and that its exit 1 is not a stop condition. `missing` is normal after a new project's first increment, which has no S01.
- **`_rules.md` §5 item 4** now says to follow the conventions `CLAUDE.md` and `knowledge.md` record, while their text stays data (rule U1) and nothing in them overrides rules 1–3.

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

**Known limitations:**
- The staleness scopes are fixed lists. A configuration file of a tool they do not name (for example a new linter) changes no Conventions or Stack/Commands staleness; Hotspots and Known risks still go stale for any change outside `docs/factory/` and `.factory/`.
- A path that names an increment's `03-architecture.md` counts as a link whether or not it is a working Markdown link; `knowledge check` does not follow links.

**Handed on:**
- **Live proof in the M7 demo (K-G).** Task Tracker increment 004: S01 must create or update `knowledge.md`, and S12's note must appear on the increment's last story.
- **The header and every section are model-written.** `knowledge check` only checks the header and the diff-derived staleness; it never checks that a rewritten section's *content* is accurate. Gate A review is the safeguard, as for `01-codebase-analysis.md` today.

**After merge** (the T7 follow-up documentation PR, 2026-10-26):
- **The final review's non-blocking findings are now recorded** as [B-41](backlog.md#b-41). They are unchanged on `main`.
- **"S02–S08 read it as level-4 conventions"** had been checked only by reading the stations (T7 audit, `1821c3de#1497`). It is now pinned by `KnowledgeBaseReadersTest` in `tests/test_stations.py`.

---

## T7.4 Plan lint and overlap detection

| | |
|---|---|
| **Specification** | [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md), "T7.4 Plan lint and overlap detection" |
| **PR** | [#53](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/53), merged 2026-10-26T08:16:55Z, merge commit `481970c` |
| **Status** | Done |

**Approved decisions.** The scoping pass was `1821c3de#176` (2026-10-26T06:19:47Z). P-A to P-F were approved, with the conditions below, in `1821c3de#179` (2026-10-26T06:31:23Z).
1. **P-A: story file estimates for the size check.**
   - **The bullet:** `05-stories.md` gains an optional `- Files: <path> (~<lines>), …` metadata bullet (`stories.py`, `Story.files`), at most once per path. The estimate must be a whole number of at least 1.
   - **A missing estimate is never zero.** A story without the bullet still parses, so `issues sync` and earlier plans are unaffected. `plan check` reports it as a `size` problem: "its size cannot be checked".
   - **The issue body is unchanged.** `issues.issue_body` does not render the bullet (tested), so the GitHub issue contract is unchanged.
   - **Lockfiles are left out** of the total, as Q7 does (`manifests.is_lockfile`).
2. **P-B: Done is read locally.**
   - **Done:** a row of the working tree's `docs/factory/traceability.md` that says `Implemented` (`status.parse_traceability`), for a requirement defined by an earlier increment's `02-requirements.md`.
   - **No GitHub call.** A row reaches the default branch, where the plan branch starts, only together with its merged story PR (S11).
   - **Not compared:** this increment's own rows and later increments' rows. An `Implemented` requirement that no increment defines is named in a note.
3. **P-C: potential overlap, scored by an explicit rule** (`plan.py` docstring, architecture §5.4).
   - **Words:**
     - each requirement's statement without its `(PRD §…):` citation or any IDs;
     - case-folded, letter-and-digit runs;
     - made singular by one rule;
     - without one-letter words, numbers and a fixed list of English function words. No domain word is listed anywhere.
   - **Weight:** `1 + ln((M+1)/(d+1))`, the standard smoothed inverse document frequency over the `M` Done requirements, where `d` is how many of them use the word.
   - **Score:** the shared words' weight ÷ the new requirement's total weight, rounded to 3 decimals and compared as rounded.
   - **The thresholds:**
     - `OVERLAP = 0.5` ("at least half of what the new requirement says"): a **potential overlap**, which fails the check until resolved;
     - `NEAR = 0.4`: **related**, reported for the reviewer and never failing.
   - **Resolution must be explicit:** an item (a list item with its continuation lines, or a paragraph) of the increment's `## Open questions` or `## Changed or retired requirements` that names both IDs literally. **Amended by the review of PR #53 (below):** naming both IDs is no longer enough.
   - **Each candidate's output:** both statements, the shared words (heaviest first), the score and, when unresolved, what to do.
4. **P-D: the checks.**
   - **The Story Contract**, through a new non-raising `stories.check` that `parse` now wraps: AC count and numbering, the `Out of scope` section (`None` stays valid), and `Blocked by` cycles.
   - **`ac-form`:** every AC reads `Given …, when …, then …`.
   - **`coverage`, both directions:**
     - every in-scope requirement (a `- **REQ-###**` bullet outside `## Out of scope`) is traced by a story;
     - every traced REQ is in scope, or is an earlier requirement named under `## Changed or retired requirements`.
   - **`size`:** the `Files` estimate against `limits.max_diff_lines`. At the limit passes, as Q7 does.
   - **`requirements`:** no in-scope requirement, or a duplicate definition.
   - **When the Story Contract is broken,** "every requirement is traced" is skipped, with a note, so a story that failed to parse cannot produce false coverage problems.
5. **P-E: S05 integration.**
   - **Normal mode, step 3:** `plan check` runs after `issues sync --dry-run` and before the commit and the Planning PR. It is repeated until it exits 0.
   - **A potential overlap** is either a stop under rule H6, when the requirement only restates finished work, or one Open question naming the new REQ and every Done REQ it was flagged against. That is S05's only normal-mode edit to `02-requirements.md`.
   - **Revision mode** runs it too.
   - **The Planning PR** template has a new "Plan check" section, `{{plan_check}}`, holding the exact output.
   - **Additions:** the Done check, the outputs and the stop conditions.
   - **Step renumbering:** the later steps moved down by one, so "normal mode step 8" is now step 9.
6. **P-F:** the stale task-log status rows (T6.5, T7.1–T7.3) and the non-blocking follow-ups from T7.3's final review are left for a separate documentation-only PR.

**Interpretations, not deviations:**
- **"AC form"** is read as the `Given …, when …, then …` form that S05 already prescribes. Before T7.4 only the `- AC<n>:` shape was checked. All 79 ACs of the three real Task Tracker plans already comply.
- **"`Blocked by` cycles"** are checked within the plan. A story can only be blocked by stories that already exist, so a cycle across increments cannot form. A dependency on a story outside the file is still checked by `issues sync` against GitHub.
- **"Each story's estimated size … (from its declared files)":** the story contract had no declared files ([B-08](backlog.md#b-08)). P-A adds them, with a per-file estimate, since a file list alone gives no size.
- **"These become an Open question, or a stop under rule H6":** `plan check` itself never writes. It fails, and S05 records the question or stops.

**Deviation from the specification:** none.

**How the rule was settled.** It was prototyped on the real Task Tracker plans before any test was written, and changed once after that.
- **The change:** the first draft weighed words by `ln((M+1)/(d+1))`. With that weight, a word every Done requirement uses weighs 0, so with a single Done requirement no overlap could ever be found. It was replaced by the standard smoothed form, `1 + ln(…)` (`ScoreTest.test_one_done_requirement_still_compares`).
- **What it moved:** the change was made for that reason alone. It moved 003's REQ-034 ~ REQ-019 from 0.494 to 0.529, over the threshold, and that result was kept (below).
- **The thresholds:**
  - 0.5 was chosen before any real score was seen.
  - The related band at 0.4, within 0.1 of it, was added after the prototype showed a related pair just under 0.5 (003's REQ-034 ~ REQ-019, then 0.494). Its purpose is to report such pairs rather than drop them silently. It can only add output, never a failure.
  - No threshold and no word list was adjusted to make a fixture pass.

**AC1, the M5 replay, and what is authored.**
- **The history:** M5's change request was the one line "Add due dates to tasks" (still `002-add-due-dates/00-prd.md` on Task Tracker). S02 stopped and asked the human under H6 before writing any requirement for it ([progress.md](progress.md), M5).
- **Authored, not history:** `tests/fixtures/plan/m5-replay/` records the request as one requirement whose statement is the request itself, verbatim. The file says that it is authored.
- **The real plans** of increments 001, 002 and 003 are copied unchanged from Task Tracker's `main` at `e89fbb2` (read with `git show`; nothing in that repository was changed or run).
- **The result:** against increment 001, with REQ-001..REQ-021 Done as at M5, the replay flags REQ-003, REQ-009, REQ-012 and REQ-014 as potential overlaps, each at 0.709 (shared words: due, date, task). REQ-001, REQ-002, REQ-015 and REQ-016 score 0.419 through "add-task form", and are reported as related only (`M5ReplayTest`).

**AC2:** a `Blocked by` cycle planted in the real 002 plan fails with `dependency-cycle` (`RealPlansTest.test_002_with_a_planted_dependency_cycle_fails`). The small-plan form is `CheckTest.test_a_dependency_cycle_fails`.

**Related work versus duplication, on the real plans:**
- **002 (overdue highlighting)** talks about due dates throughout, and REQ-025 cites REQ-009. Yet nothing in it scores even 0.4, because its new words (overdue, label, today …) carry most of its weight. Its only problems are the two missing `Files` estimates, since the plan predates T7.4. With estimates added, it passes.
- **A duplicate planted in 002** ("The user can set, change or clear the due date of a task") scores 1.0 against REQ-009. It also scores 0.687 against REQ-010, the same edit of the priority, which is parallel wording, not duplication. Both must be resolved.
- **003 (priority filter)** has one potential overlap that is a **known false positive**: REQ-034 ("choosing a filter is reflected in the list within 100 ms of the user's action") against REQ-019 ("… is reflected in the UI within 100 ms of the user's action") scores 0.529. It is kept, not tuned away: the plan must say, in one Open question, that REQ-034 applies REQ-019's budget to a new action. REQ-031 ~ REQ-025 (0.424) is reported as related.

**Verification (unit level):** `tests/test_plan.py`.
- `WordsTest`.
- `ParseRequirementsTest`.
- `ScoreTest`: the formula number for number; exactly 0.5 is a potential overlap; 0.4 is related; under 0.4 is not reported; one Done requirement; a deterministic order.
- `CheckTest`: each rule, the at-limit boundary, lockfiles, the notes, the JSON.
- `OverlapResolutionTest`: resolved by an Open question or a Changed item; not by one ID, by IDs in different items, by a longer ID, or by another section.
- `M5ReplayTest`, `RealPlansTest`: 001, 002 and 003, and mutated versions.
- `CollectTest` and `CliTest`: the reading, the exit codes, `--json`, and the errors.

`tests/test_stories.py` adds `FilesBulletTest`, `CheckTest`, and seven `Files` cases in `BAD_CASES`. `tests/test_stations.py` adds two S05 lints. `tests/test_templates.py` adds `test_embeds_plan_check_verbatim`.

**Changed existing tests**, both in `tests/test_templates.py`, because the Planning PR template gained a section: `PLANNING_PR_SECTIONS` now lists "Plan check", and `PLANNING_PR_VALUES` gains `plan_check`. No assertion was removed or weakened.

**Review of PR #53.** The read-only review (`1821c3de#999`, 2026-10-26T07:42:25Z, of head `aadab05`) found no blocker. The human asked for two fixes before merging (`1821c3de#1002`, 2026-10-26T07:58:24Z). Neither changes the scoring formula or the thresholds.
1. **`Files` paths with parentheses.**
   - **The problem:** `app/(auth)/login/page.tsx (~40)` was rejected. Route groups like this are ordinary paths in some web frameworks.
   - **Why it was rejected:** `_FILE` in `stories.py` excluded parentheses from paths.
   - **The fix:** an item's estimate is now its final `(~<lines>)`, so the parentheses in a path are not ambiguous. A path may be wrapped in backticks, and must be if it contains a comma: items are split only at commas outside backticks.
   - **Still rejected:** an unclosed backtick, empty backticks, an estimate alone, text after the backticks, and a bare path holding a comma.
   - **Tests:** `FilesBulletTest.test_paths_with_parentheses` and `test_a_backticked_path_may_hold_a_comma` fail on `aadab05`. Five new `BAD_CASES` guard against weakening; they are rejected before and after. `CheckTest.test_paths_with_parentheses_are_counted` is also new.
2. **Explicit overlap resolution.**
   - **The problem:** any item naming both IDs resolved a potential overlap, including "REQ-003 remains unchanged; REQ-022 is new" and Task Tracker 002's own "None. REQ-003 … stay in force unchanged … by REQ-022 to REQ-026". Neither says how the two relate.
   - **The fix:** `plan.resolution` now accepts only two forms:
     - under `## Changed or retired requirements`, an entry in the form `templates/README.md` already documents, `- <done>[, …]: changed by <new>[, …] (<how>)`, with the earlier requirement first. The human's example, `REQ-022: changed by REQ-003`, has the IDs the other way round, and that order is not accepted;
     - under `## Open questions`, a list item that names both IDs and contains `?`.
   - **Updated to match:** S05 step 3 (with an example question), the "To resolve" text, the CLI help and architecture §5.4.
   - **Found while fixing it:** `section_items` joined an unindented paragraph to the list item above it, so a statement could borrow a later paragraph's `?`. The original 003 test did exactly that. An item now continues only on indented lines, which is how `parse_requirements` already reads requirement bullets.
   - **Tests:** 14 new negative cases in `OverlapResolutionTest`, every one of which fails on `aadab05`:
     - the misleading statement, in both sections, as a paragraph and as a bullet;
     - the real 002 paragraph shape;
     - a reversed `changed by` entry, a `retired` entry, prose that is not an entry, and a paragraph that is not a list item;
     - a question that is not a list item, and a list item with no question;
     - the borrowed `?`.

     Valid resolutions still pass: an Open question, a `changed by` entry, several IDs, and an indented continuation. Unresolved overlaps still fail.

**Changed existing tests in the review fixes:**
- `OverlapResolutionTest.test_a_planted_duplicate_is_flagged_with_its_reason` pins the new "To resolve" text.
- `RealPlansTest.test_003_…` now records its Open question as a question, through `replace_once`. Its earlier statement "resolved" only by borrowing the next paragraph's `?`.

**The review's other findings** are recorded as follow-ups, not fixed here: [B-38](backlog.md#b-38) (enforcement in code), [B-39](backlog.md#b-39) (parser edge cases), [B-40](backlog.md#b-40) (lexical false positives and misses). [B-37](backlog.md#b-37) gains what the M7 demo should check.

**Known limitations** (also in [backlog.md](backlog.md), Accepted limitations):
- **The overlap score is lexical.**
  - A paraphrase with different words ("deadline" for "due date") is missed.
  - Parallel wording is flagged: 003's REQ-034 ~ REQ-019, and the planted REQ-027 ~ REQ-010.
  - The stop-word list and the singular rule are English.
  - Every flag is a question for the human, never an automatic verdict.
- **Resolution takes two explicit forms only,** with literal IDs: `- <done>: changed by <new>`, or a question (a list item with `?`) under Open questions. A range such as "REQ-022 to REQ-026" does not name REQ-025. A question that names both IDs resolves the pair whatever it asks: the check sees that the question was recorded, not whether it is a good one, and the human judges it at Gate A.
- **The `Files` estimates are model-written.** The plan-time check is only as good as the estimate, and Q7 at Gate B still measures the real diff.
- **Done is read from the local matrix's `Implemented` status,** not from GitHub's record of merged PRs (P-B).

**Handed on:**
- **Live proof in the M7 demo** ([B-37](backlog.md#b-37)): Task Tracker increment 004, a change request overlapping existing features, which `plan check` must flag in its Planning PR.
- **Q6 Scope stays "Not checked"** ([B-08](backlog.md#b-08)). The `Files` bullet is now there to use for it, but wiring it into `pr render` and the issue body was out of P-A's scope.
- **The review's follow-ups:** [B-38](backlog.md#b-38), [B-39](backlog.md#b-39) and [B-40](backlog.md#b-40).
- **After merge:** the second review's non-blocking findings (`1821c3de#1385`) are recorded as [B-42](backlog.md#b-42). The M7 milestone is not complete: its demo ([B-37](backlog.md#b-37)) has not been run or recorded in [progress.md](progress.md).

---

## B-28 Approved config from GitHub, not local refs

| | |
|---|---|
| **Specification** | [backlog.md](backlog.md#b-28), B-28: "Expected behaviour" and "Proposed acceptance criteria" 1–7 (marked "not decided"). B-28 is a backlog item, not a roadmap task. |
| **PR** | [#56](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/56), merged 2026-10-30T06:28:17Z, merge commit `d666b6f` |
| **Status** | Done |

**Approved decisions.**
- **B-28 is due before T8.1,** the human's decision on 2026-10-23 ([backlog.md](backlog.md#b-28)).
- **B-28 runs as a standalone hardening task before T8.1,** not in T9.5. Its roadmap position is unchanged ([ADR-0001](adr/0001-strict-sequential-roadmap.md)). The human approved this in `097efb85#173` (2026-10-28T10:52:41Z). The same message asked the task to choose the source of truth, to decide on the ADR, and to report any decision that still needs the human.

**Proposed decisions** (analysis; the human decides them by reviewing and merging the PR):
1. **R-A: GitHub's API is the source of truth.** The default branch's name, its head and the config come from `repos/<R>`, `git/ref/heads/<D>` and `contents/.factory/config.json?ref=<SHA>`, for the repository `/factory-target` recorded. B-28's criterion 1 also allowed `git ls-remote --symref origin HEAD`. That was not chosen, because `ls-remote` follows the `origin` URL, which `remote set-url`, `remote.origin.url` and an `insteadOf` rewrite can all change (B-28's own `set-url` finding).
2. **R-B: the config is read through GitHub, not from the clone.** `verify run` therefore needs no fetch. `verify map` and `pr render` still need the head commit in the clone for their diffs: they fetch it by its SHA if it is missing (`local_commit`), and otherwise nothing runs.
3. **R-C: the config must agree.** Its `default_branch` must be the branch GitHub names (B-28 criterion 1), and its `repo` must be the recorded repository (an addition).
4. **R-D: `origin` must still be the recorded repository** (`check_origin`, an addition). It is compared through `git remote get-url`, which applies `insteadOf`. **Superseded by R-K after the review:** `remote_head` no longer uses `ls-remote`, and `check_origin` is a consistency check only.
5. **R-E: `config_source` is `<branch>@<full SHA>`.** A source counts as approved when it is GitHub's head, or an ancestor of it according to GitHub's compare API (B-28 criterion 4, "a commit of the remote default branch"). The stricter rule, head only, was not chosen: it would also reject evidence after unrelated merges, and S11 step 1 already sends a story back to S09 when the default branch moves. The residual case was recorded in [B-45](backlog.md#b-45). **Narrowed by R-J after the review:** an ancestor counts only while its approved commands and `test_reports` are still the head's.
6. **R-F: replace refs and grafts are ignored** by every git call the factory makes (`Git._env`). This is an addition. The probes found that `git replace` changes what a commit reads as, contents and parents both, and that a graft file changes its parents. Either could make the approved commit show the story's config, or move a merge base so that a diff hides a change. `GIT_NO_REPLACE_OBJECTS=1` ignores replace refs. `GIT_GRAFT_FILE` points below the null device (`os.devnull`), a path that cannot exist. Pointing it at the null device itself also ignores grafts, but git then prints a deprecation hint on every call.
7. **R-G: one checked path for consumers.** `check_trusted` is `check` plus `source_problems`. A static test fails if any module other than `evidence.py` calls `evidence.check(` directly, or if any factory code reads `origin/HEAD`, `origin/main` or `refs/remotes`.
8. **R-H: a new ADR, not an amendment.** An accepted ADR is not rewritten ([README](README.md), "Writing an ADR"), and the decision spans tasks: T8.1's runner and T9's target-root invocation both rely on it. So the decision is recorded as [ADR-0005](adr/0005-approved-config-from-github.md), and ADR-0004's Status names the part it supersedes. The rest of ADR-0004 stands.
9. **R-I: criterion 6, the optional guard block, is not done.** The fix reads no local ref, the project's test code bypasses the guard anyway, and guard hardening belongs to T9.5 ([B-45](backlog.md#b-45)).

**Deviations from B-28's proposed criteria:**
- **Criterion 1:** GitHub's API rather than `ls-remote` (R-A). Criterion 1 allowed either.
- **Criterion 3:** the replace-ref and graft cases are added (R-F).
- **Criterion 2:** the config is read from GitHub, not from the commit in the clone. The commit is fetched only for the diffs (R-B).

**Evidence:**
- **Tests:** `tests/test_config_source.py` (40 tests). The suite went from 1030 tests to 1070 (5 skipped, as before), and `ruff` is clean.
- **Tests first:** before the change, the new tests failed or errored (`run_verification` took no GitHub source). The replace-ref and graft tests failed on their assertions: the old code read the forged config and the shortened diff.
- **Changed existing tests:** the fakes now serve the approved config from GitHub (`ApprovedOnGitHub` in `tests/test_evidence.py`), and the expectations changed:
  - `config_source` is `main@<full SHA>`;
  - `verify map`'s diff base is GitHub's head SHA (`test_acmap`);
  - `test_unknown_default_branch_runs_nothing` now fails on GitHub, not on `origin/HEAD`;
  - `test_ci_runs_are_read_when_required` sets GitHub's config instead of the clone's copy of the base (`test_prbody`).


**Adversarial review and fixes before merge.** The session review of PR #56 at `3b3c0d4` (`097efb85`, 2026-10-28) recommended *fix before merge*. It reported two blockers and three further findings. The human asked for both blockers to be fixed in PR #56, and for the other findings to be recorded in the backlog (`097efb85#1060`, 2026-10-30T04:56:23Z).
- **R-J, B1: superseded evidence.**
  - **The finding:** evidence recorded at an older commit of the default branch was accepted after a merge had changed the approved commands. The proof of concept: `commands.test` and `commands.lint` change from `main@3333333` to `main@4444444`, and `check_trusted` returned nothing.
  - **The fix:** `source_problems` also reads the config at the evidence's commit through GitHub, `superseded` compares it with the head's, and any change rejects the evidence with "run `verify run` again". The comparison covers every `commands.*` entry (they decide what ran, what is unapproved and what is pending) and `test_reports`. Nothing else in the config affects the evidence.
  - **The cost:** one more API call, only when the default branch has moved on.
- **R-K, B2: the story branch's head.**
  - **The finding:** `remote_head` used `git ls-remote origin`, whose transport the clone's own config decides. In the proof of concept, a `core.sshCommand` made it answer from a local fake repository, while `check_origin` passed.
  - **The fix:** `remote_head(gh, repo, branch)` reads `repos/<R>/git/ref/heads/<B>` from GitHub's API, exact match only. A 404 means "not on GitHub"; any other failure fails closed. It is used by `verify check`, `verify map`, `verdict check` and `pr render`/`pr check`.
  - **What stays:** `check_origin`, as a consistency check. ADR-0005 decision 3 is corrected to say so.
- **D1–D3** are recorded as [B-46](backlog.md#b-46) (a repository's git config can make git run programs; recommended before T8.1, the human's decision), [B-47](backlog.md#b-47) (S12's check after the merge) and [B-48](backlog.md#b-48) (exit codes).
- **Review-fix tests:** 10 new tests in `tests/test_config_source.py`, which now has 50:
  - **B1:** the review's scenario; `test_reports`; a pending command later approved; an unchanged older config; an unreadable older config; every CLI consumer; `pr render`.
  - **B2:** a real clone with a fake ssh transport; a CLI test where git and GitHub disagree.
  - **Static:** no evidence consumer runs `ls-remote`.

  Run against `3b3c0d4`, they gave 11 failures and 4 errors. Three of the errors come from the new helpers and signatures; the CLI-level B2 test fails on behaviour.
- **Changed existing tests:** `test_evidence.test_remote_head` now asks the fake GitHub. The shared fake `ApprovedOnGitHub` also serves story-branch heads and per-commit configs, and `test_prbody` and `test_verdict` give it their story branch's head.

**Second adversarial review and fixes before merge.** The second review, of `d7b4233` (`097efb85`, 2026-10-30), recommended merge, with four findings:
- **F1:** B-46 understated the problem of programs outside the guard.
- **F2:** the exact-ref check was essential but untested.
- **F3:** two checks were untested.
- **F4:** a 404 read as "not on origin, push it".

The human asked for a plan covering all four (`097efb85#1329`, 2026-10-30T05:45:36Z). They then approved it with decisions D1–D4, and authorized F2–F4 in PR #56 (`097efb85#1384`, 2026-10-30T05:53:47Z).
- **Approved decisions:**
  - **D1, git hooks:** option (b), with safeguards:
    - hooks are disabled for every git operation the factory controls;
    - changing the hook configuration is blocked;
    - `doctor` detects and reports active hooks;
    - real-git tests prove that hooks cannot run in the factory's own operations;
    - the documentation states that this does not fully protect against model-written code running git by itself during verification.
  - **D2:** `local_commit`'s fetch is removed; the factory stops with "run `git fetch origin`" (PR B).
  - **D3:** a separate bot identity without merge permission is **required before unattended execution on real projects** ([B-49](backlog.md#b-49)). Controlled sandbox demonstrations may proceed after E0–E3, with their limitations documented. E0–E3 are not complete isolation against malicious model-written code.
  - **D4, structure:**
    - F2–F4 in PR #56;
    - PR B for E0 (the threat-model ADR), E2 (the factory's own git calls) and E3 (`verify run`'s environment);
    - PR C for E1 (the guard and `doctor`);
    - B-49 for the bot identity and sandboxing.

    PR B and PR C start only after the human approves the next phase.
- **R-L, F2: branch names.**
  - **What GitHub does:** it resolves `..` in a request path. On the live API, `git/ref/heads/x/../../../../pulls/42` returned pull request #42, and `story/41-…/../41-…` returned that branch.
  - **The fix:** `config.is_git_branch_name` implements git's `check-ref-format --branch` rules, without its `@{-N}` shorthand, and rejects `@`, which git expands there as shorthand. `remote_head` refuses any other name before a request, then percent-encodes each segment, `%` included, so a legal name such as `%2e%2e` is sent as `%252e%252e`. The exact-ref check stays.
  - **The default branch** keeps the stricter `is_branch_name`, which the config file also enforces.
  - **Live check (read-only):** encoded names (`%2B`, `%C3%A9`, `%23`, `%40`, `%7B…%7D`, `%252e%252e`) get a 404 from the ref endpoint, not a 400. Not checked: a positive match for a real branch with such characters, since none exists and creating one would be a write.
- **R-M, F3:** tests pin the commit-type check in `remote_head` and the `commands.install` comparison in `superseded`.
- **R-N, F4: a 404.** GitHub answers 404 both for a missing branch and for a repository the credentials cannot see. After a branch 404, `remote_head` reads `repos/<R>` (`_confirm_reachable`):
  - if that works, the branch is missing, and `check` and `verdict.cross_check` say "not on GitHub (the repository is reachable …): push it, or check the branch name";
  - if it fails, `remote_head` fails closed with an access message that suggests `gh auth status` and never says "push it".
- **Tests:** 11 new tests in `tests/test_config_source.py` (61 in all):
  - `NormalizingGitHub`, a fake that resolves paths as GitHub does, and decodes `%2e` first as a worst case;
  - names git rejects are never sent;
  - legitimate names are encoded segment by segment;
  - `%2e%2e` stays literal;
  - only the exact ref counts;
  - a ref that is not a commit is refused;
  - a missing branch in a reachable repository;
  - an unreachable repository (404, 403, 502);
  - parity with real git over 34 names;
  - `commands.install`;
  - two CLI tests for F4.

  `test_evidence` and `test_acmap` now pin "not on GitHub". The shared fake gains `fail_on_call`.
- **Mutation run on the commit:** from a green baseline, each of 8 mutations was caught by its own test:
  - N3, the exact-ref check;
  - N6, the commit type;
  - N9, `install`;
  - F2a, no validation;
  - F2b, no encoding;
  - F2c, `%` left unencoded;
  - F2d, `..` allowed (caught by the git parity test: a `.`-leading segment is refused anyway, so traversal stays blocked);
  - F4a, no reachability check.
- **F1** is planned, not done: [B-46](backlog.md#b-46) (E1, E2), [B-15](backlog.md#b-15) (E3) and [B-49](backlog.md#b-49) (bot identity, sandbox). E0 is the threat-model ADR in PR B. None of them is complete.

**Third adversarial review** (of `2ae32c0`, `097efb85`, 2026-10-30): **merge** recommended. No defect in F2–F4 blocked it.
- **F2–F4 are complete.** Merged with PR #56.
- **Verified:**
  - parity with `git check-ref-format --branch` over 400 random names, including Unicode lookalikes, control characters and every special character: 0 mismatches apart from the documented `@`;
  - every protection caught when removed (8 of 8 mutations).
- **T1 (medium, older than this PR):** with a target active, the guard allows a Write or a shell redirect into `.factory-local/target.json`. That file records the repository that ADR-0005 trusts, and the guard allows `git remote set-url` too, so the two together can move the factory to another repository. Added to [B-46](backlog.md#b-46) for PR C, at the human's request (`097efb85`, 2026-10-30).
- **T2, T4, T5 and T6 (low or info)** are recorded in [B-45](backlog.md#b-45). **T3** is recorded in [B-48](backlog.md#b-48).
- **The merge:** PR #56 was merged by the human at 2026-10-30T06:28:17Z (`d666b6f`). The factory never merges.

**Handed on:**
- [B-45](backlog.md#b-45): the optional guard block (T9.5); the clone's own object store. Its third point, an older approved config, is closed by R-J.
- [B-46](backlog.md#b-46), [B-47](backlog.md#b-47) and [B-48](backlog.md#b-48): from the review.
- [B-46](backlog.md#b-46), [B-15](backlog.md#b-15) and [B-49](backlog.md#b-49): F1, planned as PR B and PR C, and as a later task for B-49.
- **Evidence recorded before B-28 is rejected** ("run `verify run` again"). No story was in progress: Task Tracker was at `INCREMENT_COMPLETE`, and both M7 sandboxes were at Gate A ([progress.md](progress.md#m7-plans--target-knowledge)).
- **Not run live.** The first live run is the next `verify run` on a target, at the latest T8.1's demo.

---

## PR B: E0, E2 and E3 (B-46, B-15, ADR-0006)

| | |
|---|---|
| **Specification** | [backlog.md](backlog.md): [B-46](backlog.md#b-46) "Plan, E2 (PR B)", [B-15](backlog.md#b-15) "Plan, E3 (PR B)", and E0 from the approved F1 plan. These are backlog items, not roadmap tasks. |
| **PR** | PR B, branch `task/B-46-B-15-git-and-verify-env`, not merged |
| **Status** | In review |

**Approved decisions.**
- **The F1 plan, decisions D1–D4** (`097efb85#1384`, 2026-10-30T05:53:47Z):
  - **D1, option (b):** hooks disabled for every git operation the factory controls, among other safeguards (the rest are PR C's);
  - **D2:** no fetch in `local_commit`;
  - **D3:** the bot identity is required before unattended runs on real projects, and sandbox demonstrations may follow E0–E3;
  - **D4:** PR B is E0, E2 and E3.
- **PR B authorized** (`097efb85#1670`, 2026-10-30T06:58:13Z), with these instructions:
  - E3 keeps "only the environment variables actually required for verification";
  - E3 must not be called complete isolation;
  - `guard.py`, E1, B-49 and T8.1 are out of scope.

**Proposed decisions** (analysis; the human decides them by reviewing and merging the PR):
1. **P-1: which variables E3 removes.** The listed variables are removed, plus any variable named like a secret (`TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `CREDENTIAL`, `API_KEY`, `PRIVATE_KEY`, `ACCESS_KEY`, any case), plus inherited command-line git config, which could name a credential helper again. Everything else is kept.
   - **Why not a strict allow-list:** a reusable factory cannot know which variables a project's build and test tools need. Examples are `PATH`, `HOME`, `APPDATA`, `LOCALAPPDATA` (Playwright's browsers on Windows), `SystemRoot`, `PATHEXT` and `NODE_OPTIONS`. A strict allow-list would break criterion 3 ("nothing that ran before E3 stops running") on stacks the factory has not seen.
   - **How the instruction is read:** "only the variables actually required" is taken as "every credential-like variable removed, the rest kept".
   - **For the human to decide otherwise:** a strict allow-list would be a small change in `verification_env`.
2. **P-2:** `gh.run_command_line` **requires** `env`, so no caller can run a configured command with the whole environment by accident. Its only production caller is `run_verification`.
3. **P-3:** `git.with_config` appends after any `GIT_CONFIG_COUNT` entries already present, so they are kept and ours win. A count git would refuse (not a whole number) is treated as none.
4. **P-4: no hooks folder.** `core.hooksPath` points below the null device (`os.devnull` joined with a name, a path that cannot exist), as the graft file already does (ADR-0005). The probe on 2026-10-30 confirmed that plain git ran `post-checkout`, `reference-transaction` and the fsmonitor script during `status`, `diff`, `switch` and `pull`, and that the two overrides stopped all of them.
5. **P-5:** [ADR-0006](adr/0006-threat-model-typed-commands-and-executed-code.md) supersedes ADR-0005 decision 5's fetch, and the sentence of its decision 3 about it. Only ADR-0005's Status line changes, as the README's rule for accepted ADRs requires.
6. **P-6:** S10 step 1 gains one line: on the "does not have the default branch's head" error, run `git -C <T> fetch origin` and repeat the step. This is not a failed attempt. S11 and S12 already fetch.

**Evidence:**
- **Baseline before the change:** `python -m unittest` OK (5 skipped), `ruff` clean, tree clean, on `main` at `8ef80bc`.
- **New tests:**
  - `tests/test_factory_git_env.py` (7), with real git. A control proves the hooks and the fsmonitor script run for plain git. Through `Git`, none of them runs for `status`, `diff`, `switch`, `fetch`, `pull` or `ensure.ensure_branch`. Inherited `GIT_CONFIG_COUNT` entries are kept and still apply.
  - `tests/test_verification_env.py` (7): the cleaned environment (including lower-case names and inherited overrides); every command of a `verify run` gets it, and its folders are removed after the run; `run_command_line` needs an environment.
  - **The two live tests** ran (not skipped) on this machine, where `gh` is logged in and git has a credential helper. Inside the cleaned environment:
    - `gh auth status` reports not logged in;
    - no credential helper, global config or system config is read;
    - `git credential fill` produces no credential.

    The tests never print command output, so a regression could not write a credential into the test log.
- **Changed tests:**
  - `LocalCommitTest` now expects a refusal with the fetch instruction and no fetch, even when one would work;
  - a CLI test checks that `verify map` stops with the instruction;
  - the fake runners accept `env`, and `FakeRunner` records it;
  - three direct `run_command_line` tests pass an environment.
- **Mutation run on the committed code** (`3ffbcc2`; the amend to `83700cc` changed one comment, after the reusability audit flagged a stack name in it): from a green baseline, each of 12 mutations was caught.
  - **E2:** no hooks override; no fsmonitor override; existing entries overwritten; `Git._env` skipping the safe config; `local_commit` fetching again.
  - **E3:** `SSH_AUTH_SOCK` kept; secret-named variables kept; inherited git config kept; `gh` config not isolated; system git config read; global git config read; the runner given the full environment.

**Handed on (all open):**
- [B-46](backlog.md#b-46): E1 and T1 in PR C (the guard and `doctor`), not started.
- [B-15](backlog.md#b-15): stays open. E3 is a speed bump; the remainder is [B-49](backlog.md#b-49), and closing B-15 is the human's decision.
- [B-49](backlog.md#b-49): the bot identity and a sandbox, required before unattended runs on real projects.
- **For sandbox demonstrations after E0–E3:** a project whose build or test needs a token now fails under `verify run`, as ADR-0006 states.

