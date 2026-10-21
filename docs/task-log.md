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
| **PR** | none yet |
| **Status** | **Not started.** No decisions have been made. |

**Inputs already recorded** (to settle before or during T6.5; none are decided):
- [B-01](backlog.md#b-01) the walking-skeleton story's unapproved commands (PR #36);
- [B-02](backlog.md#b-02) the interim S10/S11 fail-closed stop, which ends with T6.5 (PR #37);
- [B-03](backlog.md#b-03) bookkeeping commits that move the branch head past the evidence (PR #38);
- [B-04](backlog.md#b-04) the rendered-body attribution/footer conflict (PR #38), **unresolved**;
- [B-05](backlog.md#b-05), [B-06](backlog.md#b-06) and [B-07](backlog.md#b-07): analysis from 2026-10-21 of the current station text. Not decisions.
