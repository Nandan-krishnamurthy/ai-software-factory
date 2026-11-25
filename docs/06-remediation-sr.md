# Security and reliability remediation: milestone SR

## About this document

| | |
|---|---|
| **Status** | Specification. Milestone SR accepted by the human with DEC-1 on 2026-11-06 ([ADR-0007](adr/0007-security-reliability-milestone-sr.md)) |
| **Scope** | Tasks SR0.1–SR6.3: what each must deliver, how it is tested, what it depends on, and its order; the release gates RG-A to RG-F; the conditions for resuming T8.2, T8.3 and T9 |
| **Findings** | [backlog.md](backlog.md#security-and-reliability-audit-2026-11-04-milestone-sr), B-57 to B-84 (audit IDs N1–N23 and K1–K5) |
| **Decisions** | [ADR-0007](adr/0007-security-reliability-milestone-sr.md): why the milestone exists, where it sits in the M6–M9 roadmap, root causes RC1–RC8, decisions DEC-1 to DEC-10 and human actions HA-1 to HA-8 |
| **Progress** | [task-log.md](task-log.md), one entry per SR task |

This document does for milestone SR what [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md) does for M6–M9: it states what each task must deliver. The task sections below are not edited to match what was built. A deviation, an addition or an approved change is recorded in the task log, with its source ([README](README.md), rule 1).

### Provenance

| | |
|---|---|
| **Source** | The Claude Artifact "AI Software Factory — Security & Reliability Remediation Roadmap" ([claude.ai](https://claude.ai/artifact/Q1HtKr9X19YRPeu8n1qwGn); slug `ba4c9849-ddd8-4552-b604-4a9e6099c48b`, version `1793781941-8fb9`). It was published once, at 2026-11-04T08:45:36Z, in Claude Code session `d8543357-ee41-4800-be80-8a9f6c902842` (entry index 627), at the human's request at entry index 160 (2026-11-04T08:19:43Z) |
| **File** | The published `index.html`: 152,261 bytes, 1,240 lines, SHA-256 `135ca8c7375a461a6933652045802d0e105528a32632a8341a027d14a68b15c0` |
| **Snapshot** | Factory `main` at `7aee362` and sandbox `main` at `591a059`, on 2026-11-04. "Today" in the text below means 2026-11-04 |
| **Accepted** | DEC-1, by the human on 2026-11-06 (`d8543357#1255`, 2026-11-06T08:51:50Z) |

The artifact is a snapshot. From this commit on, this document is the source of truth for the SR task specifications and release gates; the artifact is not kept up to date.

### What was taken from the source

The sections below are the source's text, converted from HTML to Markdown by a script. A word-by-word comparison of the result with the HTML found no difference apart from markup. They come from these sections of the source:
- E, "Ordered remediation milestones", with D's "Ordering dependencies between tasks" placed after its table;
- F, "Detailed implementation tasks";
- G, "Release gates", with C's table "What each finding blocks" placed at its end;
- H, "Existing roadmap integration";
- I, J and K, "When to resume T8.2", "T8.3" and "T9";
- L, "When the factory is safe for unrelated repositories".

Not reproduced here:
- A, the executive summary;
- B, the status on 2026-11-04;
- C's findings table, now backlog items B-57 to B-84;
- D's critical chain and shared root causes, now in ADR-0007;
- M, the checklist, whose statuses are kept in the task log;
- N, the next action on 2026-11-04.

**Changes from the source text, and only these:**
1. **Human actions are HA-1 to HA-8**, the source's H1–H8 (the human's decision, 2026-11-06, `d8543357#1255`). H1–H6 without a hyphen are still the station rules in [stations/_rules.md](../stations/_rules.md), as in "rule H3", "an H3 question" and "H3 at S09".
2. **References to the source's lettered sections** point to the sections of this document. SR0.1's reference to section B names it.
3. **Markdown formatting:** headings, lists and tables. Each task's priority label is on its own line.

"You" in the text is the human. Finding IDs are the audit's: finding N*k* is backlog item B-(56+*k*), and finding K*k* is B-(79+*k*).

---

## Ordered remediation milestones

Strict order. Each gate opens only after the tasks before it are merged and its tests pass. T-tasks keep their IDs, specifications and order (T8.2 → T8.3 → T9.1 … T9.9).

| # | Milestone | Tasks (in order) | Why it sits here | Gate after |
|---|---|---|---|---|
| 1 | **SR0** Baseline and records | SR0.1 → SR0.2 → SR0.3 | No behaviour changes. Records the decision (ADR-0001 compliance), the findings, and a suite that is green in every machine state, so every later PR has clean evidence. | (starts SR1) |
| 2 | **SR1** Guard integrity and the push/merge boundary | SR1.1 → SR1.2 → SR1.3 → SR1.4 → SR1.5 → SR1.6 → SR1.7 → SR1.8 | Every later control lives in files N1 can overwrite. Closes everything a session can do with pre-approved commands. | RG-A after SR1.1, SR1.2, SR1.3, SR1.5, SR1.6 and SR1.7. SR1.4 and SR1.8 are needed by RG-B. |
| 3 | **SR2** Single writer, atomic labels, process hygiene, scratch | SR2.1 → SR2.2 → SR2.3 → SR2.4 | Unattended runs need one writer per target, crash-safe label changes, no orphan processes, and a scratch folder that headless sessions can read. | (part of RG-B) |
| 4 | **SR3** Declared transitions, recovery, decisions, limits | SR3.1 → SR3.2 → SR3.3 → SR3.4 | A headless resume must go to the right station, apply your decision once, and stop at the limits. | RG-B, then RG-C after the live checks |
| 5 | **T8.2** (existing) | T8.2 as specified | Its live evals need RG-C. |  |
| 6 | **SR4** Evidence and metrics integrity | SR4.1 → SR4.2 → SR4.3 → SR4.4 → SR4.5 | T8.3 computes metrics from timestamps, counters and verdicts. They must be machine facts first. | RG-D |
| 7 | **T8.3** (existing) | T8.3 as specified |  |  |
| 8 | **SR5** Trust boundaries on GitHub and sensitive changes; **SR6.1–6.2** | SR5.1 → SR5.2 → SR5.3 → SR6.1 → SR6.2 | T9 makes the plugin the single supported mode for new targets, including hostile ones (T9.7) and a brand-new target in its demo. | RG-E |
| 9 | **T9.1–T9.9** (existing) | As specified; T9.5 also covers N1 and N2 (see [Existing roadmap integration](#existing-roadmap-integration)) |  |  |
| 10 | **SR6.3** Portability matrix | SR6.3 | Needs the T8.2 harness, T9.7's hostile suite and T9.8's Windows matrix. | RG-F |

### Ordering dependencies between tasks

- **SR1.1 comes before every other code fix.** Until it lands, the session can rewrite whatever a fix adds.
- **SR0.3 → SR1.1 and SR1.3:** both extend `tests/test_guard.py` and reuse SR0.3's pattern of copying the factory into a temporary folder.
- **SR1.1 → SR1.2:** the list of read-only git forms to pre-approve must be final first. SR1.1 → SR1.5, SR1.6 and SR1.8 work on the same guard code.
- **SR1.3 → SR1.4:** the runner's canary runs the launcher.
- **SR2.1 → SR2.2:** labels are changed while holding the lock.
- **SR1.1 and SR1.8 → SR2.4:** the guard's write areas narrow to the new scratch folder.
- **SR3.1 → SR3.2, SR3.3 and SR3.4.** SR3.3 → SR3.4, because a decision records its recovery station. SR2.2 → SR3.4.
- **SR3.3 → SR4.3 and SR4.5,** which use the problem classification. SR4.5 → SR6.1, because lockfiles are among the definition files.
- **SR3.4 → SR5.1** (they share the trust function). SR5.1 → SR5.3 (the same snapshot code). SR1.5 and SR3.3 → SR5.2.
- **T8.2, T9.7, T9.8, SR5 and SR6.1 → SR6.3.**

### Answers to the sequencing questions

#### 1. What must be fixed first?

SR1.1 (N1, N22): the guard's own write channels. It is preceded only by the three SR0 housekeeping PRs.

#### 2. Immediately after?

SR1.2 (narrow the pre-approved rules: the only fix enforced by Claude Code rather than by factory code), then SR1.3 (a fail-closed launcher) and SR1.5 (a push allowlist in the wrapper).

#### 3. Completed together (same gate, back to back)?

- SR1.1 + SR1.2 (both halves of N1).
- SR1.3 + SR1.4 (the launcher can't catch a missing `python`; the runner's canary can).
- SR2.4's scratch move and its guard write-list change: one PR.
- SR3.3 + SR3.4 (recovery is incomplete without the decision record).

#### 4. Can safely wait?

- N7, N17, N15, N18 and K4 until T8.3.
- N3, N6 and N16 until T9, or until a repository others can write to.
- N14 and N8's non-main defaults until unrelated repositories.
- N20 and N21 until T9 (cheap, low risk).

#### 5. Separate milestones or PRs?

- Every SR task is its own PR.
- Settings changes (SR1.2, and SR1.3's hook line) are reviewed on their own.
- SR4 is a separate milestone after T8.2.
- SR5 and SR6 come before T9. SR6.3 comes after T9.

#### 6. Prerequisites for other fixes?

SR1.1 (for every code fix), SR0.3 (the test pattern), SR2.1 (for SR2.2), SR3.1 (for SR3.2–3.4), SR3.3 (for SR3.4, SR4.3, SR4.5 and SR5.2), and T8.2 (for SR6.3).

#### 7. Before any further headless execution?

- All of SR0–SR3, including SR1.4 and SR1.8.
- HA-3, or your written acceptance of the compensating controls (DEC-8).
- HA-4.
- Decisions DEC-5, DEC-6, DEC-9 and DEC-10.

This is RG-B.

## Detailed implementation tasks

**Common to every task** (not repeated below):

- Branch `task/SR<m.n>-<slug>` and PR title `[SR<m.n>] …`. One task per PR. The human reviews and merges; never push to `main`.
- The global Definition of Done (`docs/03` §3): standard library only in `scripts/`, `pathlib` for paths, argument lists for subprocesses, Windows (Git Bash and PowerShell) supported.
- `python -m unittest` with 0 failures and 0 errors. After SR0.3, run it both with a target pointer present and without one. `python -m ruff check` clean.
- Every new check has at least one mutation that a test catches.
- A `docs/task-log.md` section with the task's decisions and deviations. Backlog entries for its findings updated with status and PR. No task specification edited.
- Development happens with **no target active**, because the guard makes `scripts/` read-only while one is.

### SR0 · Baseline and records

No change in behaviour. Exit: the records agree with reality, and the suite is green in every machine state.

#### SR0.1 Commit the T8.1 merge record

**Priority:** P0 housekeeping

- **Findings:** None (record hygiene; the source's section B, current status)
- **Problem:** The committed task log says PR #66 was never opened. The correct record is uncommitted work on the local branch `task/T8.1-merged-record`.
- **Solution:** Commit the existing edits unchanged. Open a PR in the style of the B-46 merged-record PRs: `[T8.1] record PR #66's merge`. Optionally, a later separate PR can add the three STORY-002 runner runs to the L4 table.
- **Code areas:** `docs/task-log.md`, `docs/backlog.md` (already edited)
- **Acceptance:** The committed docs state "merged, `7aee362`, 2026-11-03T13:56:47Z", and L4/L5 are still reported as open.
- **Tests:** Unit: existing doc and link tests. Integration: none.
- **Security validation:** None (documentation only).
- **Depends on:** None
- **PR boundary:** These two files only.
- **Done when:** You have merged it.

#### SR0.2 Record the findings and the SR milestone (ADR-0007)

**Priority:** P0 housekeeping

- **Findings:** All 28 findings (N1–N23, K1–K5)
- **Problem:** The findings exist only in session transcripts, and ADR-0001 lists only T-tasks.
- **Solution:**
  - One backlog entry per finding, with new B-numbers and the N/K ID kept as an alias. Each gets a status, an owning SR task and a gate.
  - ADR-0007, "Security and reliability milestone SR". It records the insertion points and gates RG-A…RG-F, and that T-task IDs and specifications are unchanged. It cites the B-28 and B-46 precedent, and notes that T9.5's scope includes mid-session guard writes and start-up failure (N1, N2).
  - An SR section in the task log.
  - An index line in `docs/README.md`.
- **Code areas:** `docs/backlog.md`, `docs/adr/0007-*.md`, `docs/task-log.md`, `docs/README.md`
- **Acceptance:** Every finding has exactly one entry. The ADR states its relation to ADR-0001. `docs/05` is unchanged byte for byte.
- **Tests:** Doc-lint tests, if they exist. A check that every N/K ID appears in the backlog exactly once.
- **Security validation:** The entries must not include the probe payloads as runnable commands aimed at real paths.
- **Depends on:** SR0.1; DEC-1 (you accept the milestone)
- **PR boundary:** Documentation only.
- **Done when:** Merged; the ADR status is "accepted".

#### SR0.3 Make the hook test hermetic

**Priority:** Low · prerequisite

- **Findings:** N19
- **Problem:** `test_hook_command_runs_and_blocks` reads the real target pointer, so the suite fails whenever a target is active.
- **Solution:** The test copies `scripts/` and the hook command into a temporary factory root with no `.factory-local/`, and runs the copied hook. **No** environment variable or flag that redirects the guard's root is added: that would be a new way around the guard.
- **Code areas:** `tests/test_guard.py` (around lines 992–1006), possibly a shared test helper
- **Acceptance:** The suite passes with a target active and with none. `guard_hook.py` and `target.py` are unchanged.
- **Tests:** Unit: the rewritten test. Integration: the full suite run twice, in both states, with the output recorded in the PR.
- **Security validation:** A search for new `os.environ` reads in `scripts/` finds none.
- **Depends on:** None
- **PR boundary:** Tests only.
- **Done when:** Merged, with both suite runs green.

### SR1 · Guard integrity and the push/merge boundary

Exit: nothing a session can do with pre-approved commands writes a protected file, disables the guard, or reaches the default branch.

#### SR1.1 Close the write channels into protected paths

**Priority:** Critical · first fix

- **Findings:** N1, N22 (and the `factory.py` part of N23)
- **Problem:** `git` is treated as a reader, and `python …` arguments are skipped. git's `--output`, `-o` and `config --file`, and factory.py's `--out`, `--notes` and `--body-file`, can therefore write the guard, the settings, the target pointer or the memory folder.
- **Solution:**
  - Take `git` out of `_READ_ONLY`. Treat as writes: `--output[=]` (log, show, diff, format-patch), `-o` and `--output-directory` (format-patch, archive), `config -f`/`--file`, `bundle create <file>` and `archive -o`. Block `grep -O`/`--open-files-in-pager`, which runs a program, and `--git-dir`/`--work-tree` pointing into the factory.
  - For `python scripts/factory.py <sub>`, check every path option against the allowed write areas and the protected list. Use one exported table, `cli.WRITE_PATH_OPTIONS`, that the guard imports, so the two can't drift apart.
  - Defence in depth: one `safe_write(path)` helper used by every factory writer. It refuses the factory's `scripts/`, `.claude/`, `.factory-local/` and `~/.claude/`.
  - In target mode, remove `~/.claude/projects` from `extra_write_dirs` (N22).
- **Code areas:** `scripts/factory/guard.py` (`_READ_ONLY`, `_scan_protected_args`, git analysis around lines 745–1001), `guard_hook.py` (line 58), `cli.py`, and the writers in `evidence.py`, `acmap.py`, `prbody.py`, `verdict.py`, `closeout.py`
- **Acceptance:**
  - Every N1 and N22 case in the audit's probes is blocked.
  - The Write-tool control is still blocked.
  - Every command the stations and command files prescribe is still allowed.
  - Factory-development mode (no target) is unchanged.
- **Unit tests:**
  - Matrix: {log, show, diff, format-patch, archive, `config --file`, bundle} × {`guard.py`, `guard_hook.py`, `settings.json`, `settings.local.json`, `.factory-local/target.json`, `~/.claude/projects/x`} → blocked.
  - The same with each factory.py path option.
  - `safe_write` refuses each protected root.
  - A lint over every station-prescribed command → allowed.
- **Integration / E2E:** Run the real hook command as a subprocess, the way Claude Code does, on 6 representative cases: exit 2, with the reason.
- **Security validation:** The probe scripts become regression fixtures. Mutations: removing each new check fails a test. A reviewer tries three channels not in the list, such as `git notes` or `git worktree add`, and records the result.
- **Depends on:** SR0.3
- **PR boundary:** Guard, writers and tests. **No** settings changes.
- **Done when:** Merged, with the probe output in the PR showing every listed case blocked.

#### SR1.2 Narrow the pre-approved permission rules

**Priority:** Critical · human-reviewed settings change

- **Findings:** N1
- **Problem:** According to the audit, `Bash(git -C:*)` pre-approves every `git -C` subcommand, including push and config writes. The guard is then the only barrier, and it is code the session can write. (The settings file was not re-read for this plan; rule S16.)
- **Solution:** Replace the broad prefix with the exact read-only forms the stations use: `log`, `rev-parse`, `rev-list`, `show`, `cat-file`, `hash-object` without `-w`, `config --get`, `ls-remote` and `diff A..B`. Add deny rules for push, config writes and `--output`. Before relying on them, confirm against Claude Code's documentation how prefix matching works and that deny overrides allow. Keep `Bash(python scripts/factory.py:*)`, which SR1.1 now covers. Runner decision R1 is unchanged.
- **Code areas:** `.claude/settings.json`, written or explicitly approved by you; the settings lint in `tests/test_guard.py` (`SettingsTest`)
- **Acceptance:** Every read-only git form the stations use is still pre-approved. `git -C <T> push …` and `git -C <T> config a.b c` are not.
- **Unit tests:** A settings lint: no rule broader than the listed forms; the deny rules are present.
- **Integration / E2E:** A live headless check (run by you): a `claude -p` session asked to run `git -C <T> config a.b c` shows it in `permission_denials`.
- **Security validation:** You review the diff line by line; the PR lists every rule removed and added.
- **Depends on:** SR1.1
- **PR boundary:** The settings file and its lint only.
- **Done when:** Merged, with the live check recorded.

#### SR1.3 A fail-closed hook launcher

**Priority:** High

- **Findings:** N2 (start-up failure)
- **Problem:** Fail-closed covers only `decide()`. An import error, a syntax error or a timeout exits with something other than 2, which Claude Code does not treat as a block (per its documentation).
- **Solution:** A new `scripts/guard_launch.py` that imports only `sys`, `runpy` and `time`. It loads `guard_hook` inside `try/except BaseException` and maps any failure to exit 2 with a message. A watchdog gives up and blocks before Claude Code's 60-second hook timeout. The hook command in the settings points at the launcher; this settings line is called out in the PR. A missing interpreter can't be caught from inside the hook, so SR1.4 and T9.5 cover it.
- **Code areas:** New `scripts/guard_launch.py`; the hook line in `.claude/settings.json`; `tests/test_guard.py`
- **Acceptance:** With a syntax error, or an error raised at import, in a temporary copy of any module the hook loads, the exact hook command exits 2. So does a `KeyboardInterrupt`. Every normal decision is unchanged.
- **Unit tests:** Temporary factory copies (SR0.3's pattern) with each kind of breakage; a lint that the launcher imports nothing from `factory`.
- **Integration / E2E:** Run the settings' hook string exactly, the way Claude Code does.
- **Security validation:** A mutation that removes the `except` fails the tests.
- **Depends on:** SR0.3, SR1.1
- **PR boundary:** The launcher, the one settings line and the tests.
- **Done when:** Merged; the hook string in the settings names the launcher.

#### SR1.4 Runner preflight: effective settings, live canary, guard pinning

**Priority:** High

- **Findings:** N2 (the preflight), N1 (detection)
- **Problem:** `check_hooks` reads only the project files. Nothing proves the hook actually blocks before Claude is invoked. A guard changed during a session goes unnoticed.
- **Solution:**
  - **(a) Effective settings.** Read every layer: user (`~/.claude/settings.json`), managed (the per-OS path), project and local. Refuse to run on `disableAllHooks`, `defaultMode: bypassPermissions`, or a missing guard hook. This is factory code reading the files; rule S16 restricts the model, not the runner.
  - **(b) Canary.** Run the exact hook command from the settings with a canary payload (Bash `gh pr merge 1`) and require exit 2. This also proves the interpreter exists.
  - **(c) Pinning.** At run start, take the SHA-256 of `scripts/**/*.py`, `.claude/settings*.json`, `.claude/agents/*` and `stations/*`. Recompute after each invocation. On a mismatch, stop with a new exit code and never continue.
  - **(d) Branch protection.** If the target's default branch is unprotected, refuse, unless you pass `--accept-unprotected-default-branch` and confirm in the terminal (B-24, DEC-8).
- **Code areas:** `scripts/factory/runner.py` (`check_hooks` around line 371, the invocation loop), `cli.py` (`run`), `tests/test_runner.py`
- **Acceptance:** Each unsafe layer is refused before any invocation. A failed canary stops the run before Claude starts. A hash change between invocations stops the run.
- **Unit tests:** Fake settings layers; a fake hook command that exits 0 or 1; a file changed between two fake invocations.
- **Integration / E2E:** LC-2 (see [Live checks](#live-checks-run-by-you-results-recorded-in-the-task-log)): in a throwaway checkout with a broken `guard_hook.py`, the runner refuses before invoking Claude.
- **Security validation:** The pin list includes everything the guard and the stations load. A reviewer checks the list against the imports.
- **Depends on:** SR1.3
- **PR boundary:** Runner only. T9.5's in-session canary and T9.6's `doctor` are **not** implemented here.
- **Done when:** Merged; LC-2 recorded.

#### SR1.5 A push-destination allowlist and the default branch from GitHub

**Priority:** High

- **Findings:** N2 (the wrapper's missing check), N8, the remote-URL part of N9
- **Problem:** `factory.py git push` has no check of its own. The guard protects {configured default, main, master}, and the configured default comes from a working-tree file the model can edit. A push to an arbitrary remote URL is allowed (probe).
- **Solution:**
  - The wrapper refuses a push unless the remote is `origin` and its URL matches the target record's repository, and every destination is the active story's `refs/heads/story/<n>-…` or the increment's planning branch. Confirm the planning branch pattern against S01–S05.
  - It also refuses `--all`, `--mirror`, `--tags` and `--delete`, and a force-push to a reviewed branch.
  - The default branch comes from GitHub: `state.py:708` already reads `defaultBranchRef`. It is recorded with the target and is used only in messages, because the allowlist already excludes it.
  - The guard applies the same allowlist to raw pushes.
- **Code areas:** `cli.py` (`_git`, lines 699–730), `git.py` (`WRAPPER_SUBCOMMANDS`), the guard's push analysis, `target.py`
- **Acceptance:** Blocked: a push to another URL; story → `develop` with the configured default `main`; `branch -f main` followed by a push. Allowed: `story/3-x` and the planning branch. Pushes are refused even with the guard hook absent: the wrapper is called directly.
- **Unit tests:** A table of refspecs and remotes; a test calling the wrapper without the hook.
- **Integration / E2E:** The wrapper against a local bare-repository fixture (a `file://` remote) proves the refusal happens before git runs.
- **Security validation:** The probe cases are re-run. A reviewer confirms that no path reaches `git push` other than through the wrapper's check.
- **Depends on:** SR1.1
- **PR boundary:** The wrapper, the guard's push rules and the target record.
- **Done when:** Merged.

#### SR1.6 Git config and option gaps

**Priority:** Medium

- **Findings:** N9, N20; overlaps B-45
- **Problem:** The config keys that redirect pushes or run programs are allowed, and `--amen` passes the `--amend` check.
- **Solution:**
  - In target mode, block every `git config` write and every `remote add` or `remote set-url`, unless a station needs it (audit the stations first).
  - Extend `is_risky_config` with `remote.*.url`, `pushurl`, `remote.pushDefault`, `branch.*.pushRemote`, `branch.*.remote`, `core.gitProxy`, `pager.*`, `core.alternateRefsCommand` and `uploadpack.*`, so `doctor` also flags existing ones.
  - Refuse every `--` prefix of `--amend` of three letters or more, and `--fixup=amend:` and `--fixup=reword:`.
- **Code areas:** `guard.py` (lines 745–766), `cli.py` (line 718), `doctor.py`
- **Acceptance:** Every N9 and N20 probe case is blocked, and `doctor` reports each key when it is already set.
- **Unit tests:** Key and prefix tables; `doctor` fixtures.
- **Integration / E2E:** The real hook command on two cases.
- **Security validation:** A list of the keys reviewed against `git help config`, recorded in the PR.
- **Depends on:** SR1.1
- **PR boundary:** Guard, wrapper and doctor.
- **Done when:** Merged.

#### SR1.7 gh API and CLI gaps

**Priority:** High (interactive)

- **Findings:** N4
- **Problem:** A GraphQL merge from `@file` or `@-`, and settings-changing endpoints and subcommands, pass the guard.
- **Solution:**
  - Block `-F`, `-f`, `--field` and `--raw-field` values starting with `@` on `gh api graphql`.
  - Block these endpoints: `collaborators`, `hooks`, `actions/**/dispatches`, `releases`, `rulesets`, `branches/*/protection`, `environments`, `secrets`, `variables`, `keys`, `deployments`, a PATCH of `repos/{o}/{r}`, and any `-X DELETE`.
  - Block `gh release`, `gh workflow run`/`enable`/`disable`, `gh secret`, `gh variable`, `gh repo edit`/`delete`/`rename`/`archive` and `gh ruleset`.
  - Prefer a positive allowlist of the gh forms the stations use, where that doesn't break the stations.
- **Code areas:** `guard.py` (lines 965–1001, gh analysis)
- **Acceptance:** Every N4 probe case is blocked; every station-prescribed gh command is allowed.
- **Unit tests:** The probe table; a station-command lint.
- **Integration / E2E:** The real hook command on the `@file` case.
- **Security validation:** The endpoint list is reviewed against GitHub's REST reference and the review recorded.
- **Depends on:** SR1.6 (to avoid conflicts in the same file)
- **PR boundary:** gh rules only.
- **Done when:** Merged.

#### SR1.8 Bash writes outside the allowed areas

**Priority:** Medium

- **Findings:** N23 (new); related to B-14
- **Problem:** The guard's contract says nothing outside the target, the scratch folder and memory may be written. Yet `rm -rf`, `cp`, `mv`, `curl -o` and similar commands on outside paths are allowed (probe). Only permission prompts stop them.
- **Solution:** For commands that aren't readers, every path-like argument must be inside the allowed write areas. Known writers (`rm`, `rmdir`, `mv`, `cp`, `tee`, `touch`, `mkdir`, `ln`, `chmod`, `install`, `rsync`, `curl -o/-O`, `wget -O`, `tar -C`, `unzip -d`, and the PowerShell `*-Item` and `*-Content` cmdlets) get explicit option parsing. Update the docstring to match.
- **Code areas:** `guard.py` (`_scan_protected_args`, `_check_redirect_target`)
- **Acceptance:** The audit's three outside-write probe cases are blocked, and station commands still pass the lint.
- **Unit tests:** A matrix of writers × {home folder, another drive, a UNC path, `..` traversal, a symlink}.
- **Integration / E2E:** The real hook command on two cases.
- **Security validation:** A record of the false-positive review: no station command is blocked.
- **Depends on:** SR1.1
- **PR boundary:** Guard only.
- **Done when:** Merged.

### SR2 · Single writer, atomic labels, process hygiene, scratch

Exit: two sessions can't act on one target, a crash leaves something the factory can resume, and no process outlives its run.

#### SR2.1 A per-target lock

**Priority:** High (headless)

- **Findings:** N5
- **Problem:** Nothing stops a runner and an interactive session, or two runners, from picking stories or relabelling at the same time.
- **Solution:**
  - `.factory-local/locks/<owner>__<repo>.json`, created with `O_CREAT|O_EXCL`. It holds the pid, host, start time, command and run id.
  - The runner holds it for the whole run and passes `FACTORY_RUN_ID` to Claude.
  - The commands that change something (pick, `comment`, `closeout --finish`, labels, `pr`, `issues sync`, wrapper commit and push) refuse while another live holder has the lock, and take a short lock of their own otherwise.
  - A lock is stale when its pid isn't alive on the same host. **Windows caution:** `os.kill(pid, 0)` sends a Ctrl+C event there (`CTRL_C_EVENT == 0`). Use `OpenProcess` through `ctypes`, or `tasklist`.
  - After assigning a story, pick re-reads it and stops at `NEEDS_HUMAN` if two stories are in progress.
  - Telling two interactive sessions apart needs a lease design: DEC-10.
- **Code areas:** A new `scripts/factory/lock.py`; `runner.py`, `cli.py`, `pick.py`, `comments.py`, `closeout.py`, `labels.py`, `issues.py`
- **Acceptance:** Two concurrent picks: exactly one succeeds. A second runner is refused with the holder's details. A stale lock is recovered. A crash releases the lock, or leaves it recoverable.
- **Unit tests:** A two-process race with a fake gh; stale-pid recovery; a test that the Windows liveness check never calls `os.kill`.
- **Integration / E2E:** LC-3: while a runner is active, a second runner and an interactive `/factory-continue` are both refused.
- **Security validation:** The lock folder is still protected from model writes (D-10). The model cannot delete the lock to force its way in; test this with the guard.
- **Depends on:** SR1.1; DEC-10
- **PR boundary:** The lock and its call sites. A lock marker on GitHub for several machines is out of scope (RG-F).
- **Done when:** Merged; LC-3 recorded.

#### SR2.2 Atomic status labels and resumable half-transitions

**Priority:** Medium

- **Findings:** N13 (a case of K2)
- **Problem:** Adding the new label and then deleting the old one can leave two status labels, which is INCONSISTENT.
- **Solution:** `set_status` sends one `PUT /repos/{o}/{r}/issues/{n}/labels` with the complete new label set; confirm GitHub's replace-all behaviour in the PR. For legacy half-done states, two status labels where one is the target of a known label transition become a repairable state with an idempotent `labels repair`, run automatically by the route.
- **Code areas:** `pick.py` (`set_status`, lines 169–186), `state.py` (around lines 439–442), `labels.py`
- **Acceptance:** One API call per transition. Probe case 3 (two status labels) resumes without a human.
- **Unit tests:** A fake gh records a single PUT; fixtures for the repair; a label you added by hand is preserved.
- **Integration / E2E:** Part of LC-4 (kill during pick).
- **Security validation:** The repair never removes a non-status label and never touches `factory:needs-human`.
- **Depends on:** SR2.1
- **PR boundary:** Labels and state classification.
- **Done when:** Merged.

#### SR2.3 Runner process hygiene and run budgets

**Priority:** Medium

- **Findings:** N11
- **Problem:** A timeout kills only `claude.exe`. Ctrl+C only logs. No wall-clock or cost budget exists.
- **Solution:**
  - `invoke_claude` uses `Popen` in a new process group, and calls `_kill_tree` on timeout and on `KeyboardInterrupt`.
  - Afterwards it checks the target for `.git/index.lock` and reports it. It never deletes it (S7, H6).
  - New options `--max-run-minutes` and `--max-cost-usd`, using `total_cost_usd` from each result. The defaults are DEC-9.
- **Code areas:** `runner.py` (`invoke_claude`, lines 191–210), `gh.py` (shares `_kill_tree`), `cli.py` (lines 660–671)
- **Acceptance:** After a timeout or Ctrl+C, no child process of the run is alive. A run over budget stops with its own exit code. Both are logged.
- **Unit tests:** A fake `claude` script that starts a sleeping grandchild; check its liveness by pid.
- **Integration / E2E:** LC-4: kill the runner during S09's `verify run`; Task Manager or `tasklist` shows no leftover `python`/`git`.
- **Security validation:** The kill targets only the run's own process group, never processes matched by name.
- **Depends on:** SR1.4 (same file, to avoid conflicts)
- **PR boundary:** Runner only.
- **Done when:** Merged; LC-4 recorded.

#### SR2.4 A per-target scratch folder that headless sessions can read

**Priority:** Medium

- **Findings:** N10, K5
- **Problem:** One shared `%TEMP%` holds files named by issue number. Headless sessions can write there but not read, so overwriting an existing file is denied.
- **Solution:** One helper, `scratch.path(target)`, returning `<tempdir>/ai-software-factory/<owner>__<repo>/`, used by every writer and by `factory.py scratch`. The guard's scratch area narrows to that folder in target mode. The runner passes `--add-dir <folder>`. Stories already in flight rerun S09; call this out in the PR.
- **Code areas:** `evidence.py` (lines 834–836), `acmap.py`, `prbody.py`, `verdict.py`, `closeout.py`, `questions.py`, `guard_hook.py` (line 57), `runner.py` (argv), `cli.py` (`scratch`)
- **Acceptance:** Two targets that both have issue #3 never clash. The argv contains `--add-dir`. The guard blocks a target-mode write to `%TEMP%` outside the folder. The K5 incident replayed headless gives no denial.
- **Unit tests:** A clash test; an argv test; a guard test.
- **Integration / E2E:** LC-6 includes a scratch rewrite.
- **Security validation:** `--add-dir` names only this folder. Runner decision R1 and rule R5 are unchanged.
- **Depends on:** SR1.1, SR1.8
- **PR boundary:** The helper, its callers, the guard's scratch area and the runner's argv, together in one PR.
- **Done when:** Merged.

### SR3 · Declared transitions, recovery, decisions, limits

Exit: the state engine and the stations agree on the next action after every stop, and code enforces the limits.

#### SR3.1 Declared, validated station transitions

**Priority:** Medium · prerequisite

- **Findings:** K1
- **Problem:** No code reads `allowed_from`, and a checkpoint's `next` is checked only for its format.
- **Solution:**
  - A `returns_to` list in the station frontmatter: S11 → [S08, S09, S10]; S10 → [S08, S09]; S09 → [S08].
  - One code table built from the frontmatter.
  - `comment --kind checkpoint` refuses an undeclared pair, and `check_invariants` flags one already on GitHub.
  - Correct the architecture doc's §4.3 statement. Call this out in the PR: it is a fix to a false statement, not a task specification.
- **Code areas:** `stations/*.md` frontmatter, `markers.py`, `comments.py`, `state.py` (`check_invariants`), `tests/test_stations.py`
- **Acceptance:** `S11 → S09` is accepted; `S11 → S07` and `S09 → S11` are refused. Every `--station X --next Y` in the station text is in the table.
- **Unit tests:** A table test; a lint of the station text; a check that old checkpoints still parse.
- **Integration / E2E:** The offline replay of sandbox #3 (SR3.3).
- **Security validation:** The table is read only from the factory's own stations, never from the target.
- **Depends on:** SR0.3
- **PR boundary:** Table and validation.
- **Done when:** Merged.

#### SR3.2 Counters and limits owned by code

**Priority:** Medium

- **Findings:** N12; related to N16 (`limits` can be edited on a branch)
- **Problem:** The model supplies the counters, and nothing refuses a run past `max_fix_attempts` or `max_review_rounds`.
- **Solution:** The checkpoint command derives the counters from the previous checkpoint and the kind of transition: fix attempts on S10 → S08 and S09 → S08; a review round on Gate B `/changes` → S08. A `--fix-attempts` value that differs from the derived one is refused. The route stops at `NEEDS_HUMAN` once a limit is exceeded. Limits are read only from the approved config on `main`, the B-28 mechanism. The runner's no-progress check also counts repeated (station, next) cycles.
- **Code areas:** `comments.py` (around lines 110–137), `cli.py` (around line 1181), `commands.py`/`route`, `runner.py` (lines 251–257), `config.py`
- **Acceptance:** Four S10 → S08 cycles with a limit of 3 → the route stops. A value supplied by the model is refused. A branch edit of `limits` has no effect.
- **Unit tests:** Sequence fixtures; a branch-config fixture.
- **Integration / E2E:** A fake-factory runner test that loops S08 → S09 → S10 → S08 and stops at the limit.
- **Security validation:** The counters can't be reset by writing a new checkpoint by hand (the oldest-checkpoint rule plus derivation).
- **Depends on:** SR3.1
- **PR boundary:** Counters, route and runner.
- **Done when:** Merged.

#### SR3.3 Failures carry their recovery station

**Priority:** Medium

- **Findings:** K2; B-44 (both parts)
- **Problem:** S11 asks without writing a checkpoint, so a resume goes back to S11 and repeats the failure.
- **Solution:**
  - `pr render` and `pr check --json` report each problem with its recovery station and whether it needs a human: H3, Q1/Q2/Q4 and missing tests → S09; an undeclared dependency → S08; Q5 → S10; the model's own sections → S11, with no human.
  - S11 writes the checkpoint `S11 → <recovery>` **before** it asks or labels, and goes back without asking when no human is needed.
  - S09 skips its log commit when the tests are unchanged and only the evidence is missing.
- **Code areas:** `prbody.py`, `cli.py` (`pr`), `stations/S11-pr.md`, `stations/S09-test.md`
- **Acceptance:** Every problem kind has a mapping. A station lint shows every stop-and-ask writing its recovery checkpoint before the label.
- **Unit tests:** A mapping table; the station lint; S09's skip rule.
- **Integration / E2E:** An offline replay of sandbox #3 with the fake factory: from S11's H3 stop, the resume reaches S09 → S10 → S11.
- **Security validation:** A rule H3 problem can never be resolved at S11 without a human.
- **Depends on:** SR3.1
- **PR boundary:** Classification and the station text.
- **Done when:** Merged.

#### SR3.4 Human decisions as typed records

**Priority:** Medium

- **Findings:** K3
- **Problem:** No code reads an answer, and asking again posts a duplicate.
- **Solution:**
  - `factory.py decision ask`, with a new `DecisionMarker` (key, options, resume station). It is idempotent per key.
  - `decision answer` reuses `questions.accepted_by`: the reviewer only, no marker, posted after the question.
  - The state engine: label present → `NEEDS_HUMAN`. Label removed but no valid answer → `NEEDS_HUMAN`, with a message saying exactly that. Valid answer → `STORY_IN_PROGRESS` at the resume station, with `details.decision`.
  - The resume station applies the decision first, and records its id in a new optional checkpoint field.
  - The answer format is DEC-5.
- **Code areas:** `questions.py`, `markers.py`, `comments.py`, `state.py`, `cli.py`, the stop conditions of S08–S11
- **Acceptance:**
  - Asking twice → one comment.
  - An answer is ignored if it comes from a non-reviewer, carries a marker, predates the question, or names an invalid option.
  - The latest valid answer wins.
  - A used decision is never applied twice.
  - Old checkpoints route as they do today.
- **Unit tests:** As listed in the 2026-11-03 investigation, §5.
- **Integration / E2E:** LC-5: the full sandbox #3 pattern, live.
- **Security validation:** The answer trust function is shared with SR5.1 later, and its tests include a foreign author.
- **Depends on:** SR3.3, SR2.2; DEC-5
- **PR boundary:** Decision records and the state engine.
- **Done when:** Merged; LC-5 recorded.

### SR4 · Evidence and metrics integrity (after T8.2, before T8.3)

Exit: every number T8.3 reports comes from a machine or from GitHub, with its source recorded.

#### SR4.1 Machine-written log timestamps

**Priority:** Medium

- **Findings:** N17
- **Problem:** Headless sessions estimate the `<UTC time>` values in `.factory/log.md`.
- **Solution:** `factory.py log --station Sxx --event <e> [--note]` appends a line with the machine's UTC time and a source tag. The stations call it instead of writing times by hand, and an S15-style lint forbids hand-written timestamps.
- **Code areas:** `cli.py`, a new log module, `stations/S0*–S12`, `tests/test_stations.py`
- **Acceptance:** No station asks the model for a time. Every new log line carries `source=machine`.
- **Unit tests:** The line format; the lint.
- **Integration / E2E:** Live: a headless run's log lines fall between the run's start and stop times.
- **Security validation:** The log command can only append to the target's `.factory/log.md`.
- **Depends on:** RG-C
- **PR boundary:** The command and the station text.
- **Done when:** Merged.

#### SR4.2 Review rounds on GitHub's clock

**Priority:** Medium

- **Findings:** N7
- **Problem:** The round boundary uses the local clock's `committedDate`.
- **Solution:** Anchor each round on a timestamp GitHub assigns: the factory's own rework reply comment (`created_at`) or the checkpoint update (`updated_at`). Confirm the available timeline fields in the PR. When the boundary is ambiguous, stop and say so.
- **Code areas:** `signals.py` (lines 119–124, 225–226)
- **Acceptance:** Probe case 5 with the clock +1 h → CHANGES_REQUESTED.
- **Unit tests:** Skew fixtures of ±1 h and ±1 day.
- **Integration / E2E:** T8.2's "Gate B `/changes`" scenario.
- **Security validation:** Only reviewer comments count (U2).
- **Depends on:** RG-C
- **PR boundary:** Signals only.
- **Done when:** Merged.

#### SR4.3 H3 at S09, and skip-marker detection

**Priority:** High (skip gap)

- **Findings:** K4; B-30
- **Problem:** The check runs only at S11, and an added skip decorator or `skipTest` is not detected.
- **Solution:**
  - `verify run` runs `changed_tests` on the evidence commit and reports undeclared changes.
  - S09 fixes them within `max_fix_attempts`, but still asks a human about a removed or skipped test. That is policy decision DEC-3.
  - A decorator is attributed to the test below it.
  - Added lines inside existing non-test functions are flagged.
  - `@unittest.skip`, `self.skipTest`, `@pytest.mark.skip`/`xfail`, Jest/Vitest `.skip`/`xit` and JUnit `@Disabled` are detected.
- **Code areas:** `prbody.py` (`enclosing_test` around line 346, `changed_tests` lines 410–415), `evidence.py`, `stations/S09-test.md`
- **Acceptance:** Each skip form is flagged; a new helper or import is not.
- **Unit tests:** One fixture per framework.
- **Integration / E2E:** A replay of Task Tracker #34 and #41, and sandbox #3: no human stop where only a declaration was missing.
- **Security validation:** A mutation that hides a skip in a decorator chain is caught.
- **Depends on:** SR3.3; DEC-3
- **PR boundary:** H3 only.
- **Done when:** Merged.

#### SR4.4 Where the verifier's verdict came from

**Priority:** Medium · design decision

- **Findings:** N15
- **Problem:** `verdict check` can't tell whether the AC-verifier subagent produced the verdict.
- **Solution:** DEC-4 chooses between two options:
  - **(a)** The runner, or a new `factory.py verify independent`, starts a separate `claude -p` verifier process. Factory code records its log hash and the verdict hash in the evidence.
  - **(b)** Honest labelling: the PR body says "verdict produced in-session; independence not enforced" unless (a) applies.

  The minimum for RG-D is (b), and T8.3 then reports the verifier rate as "self-reported".
- **Code areas:** `verdict.py`, `prbody.py`, `runner.py`, `.claude/agents/ac-verifier.md`
- **Acceptance:** A verdict without provenance is labelled in the PR. With (a), a hash mismatch is refused.
- **Unit tests:** Fixtures for each label and for a mismatch.
- **Integration / E2E:** One story where the PR shows the verdict's provenance.
- **Security validation:** The main session cannot write the provenance record (it lives in a protected folder).
- **Depends on:** SR2.4, SR3.3; DEC-4
- **PR boundary:** Provenance only.
- **Done when:** Merged.

#### SR4.5 Changed command definitions

**Priority:** Medium

- **Findings:** N18; B-11 (security side)
- **Problem:** An approved `npm test` can run something different once the branch edits `scripts.test`.
- **Solution:** At approval time, record hashes of the files that define each approved command's behaviour, per ecosystem, using `discovery.py` and `manifests.py`: `package.json` (scripts), the Makefile, `pyproject.toml` (`[tool.pytest*]`), `pytest.ini`, `tox.ini`, `setup.cfg`, `noxfile.py`, Jest/Vitest config, and lockfiles. `verify run` compares the branch with `main` and records `command_definition_changed`. The PR body adds a "Changed command definitions" section, and S10 marks the affected ACs.
- **Code areas:** `evidence.py`, `discovery.py`, `manifests.py`, `prbody.py`
- **Acceptance:** Editing `scripts.test` → flagged; editing a source file only → not flagged.
- **Unit tests:** Node, Python and Make fixtures.
- **Integration / E2E:** One sandbox story that edits the pytest config.
- **Security validation:** The flag can't be suppressed by the model's notes.
- **Depends on:** SR3.3, SR4.3
- **PR boundary:** Drift detection only.
- **Done when:** Merged.

### SR5 · Trust boundaries on GitHub and sensitive changes (before T9)

Exit: only reviewers can steer the factory, and changes to CI, settings or config can't slip through.

#### SR5.1 Check who wrote each marker

**Priority:** High (shared repos)

- **Findings:** N3
- **Problem:** Markers on PRs, issues and checkpoints are trusted from any author, including PRs from forks.
- **Solution:** Fetch the author and head-repository fields. Trust a marker only when its author is in `reviewers` (or the bot, later), it sits on a same-repository PR, and its issue is labelled `factory:story`. The checkpoint is the oldest one by a trusted author. One trust function is shared with SR3.4. `doctor` warns on public repositories and on fork-PR settings.
- **Code areas:** `state.py` (lines 714–722), `issues.py` (lines 199–212), `pick.py` (lines 82–101), `comments.py` (lines 91–98), `doctor.py`
- **Acceptance:** Probe cases 1b, 2b and 4: the stranger's objects are ignored, and the state stays `IDLE_AT_GATE_C`.
- **Unit tests:** Fixtures with a foreign author and a fork for each reader.
- **Integration / E2E:** SR6.3: a fork PR from a second account on a public test repository.
- **Security validation:** Single-account mode still works (you are the reviewer).
- **Depends on:** SR3.4
- **PR boundary:** Readers and doctor.
- **Done when:** Merged.

#### SR5.2 Flag and gate sensitive changes

**Priority:** High (CI with secrets)

- **Findings:** N16; rule S5
- **Problem:** Edits to workflows, `.claude/`, `CODEOWNERS` and config keys pass silently. A changed workflow runs with the repository's secrets as soon as it is pushed.
- **Solution:**
  - A list of sensitive paths: `.github/**`, `.claude/**`, `CODEOWNERS`, the non-command keys of `.factory/config.json`, `.gitattributes`, `.gitmodules`, `.husky/`, `.pre-commit-config.yaml`, and `.npmrc`/`.yarnrc*`/`pip.conf`.
  - `pr render` requires a "Sensitive changes" section. S11 stops for a human unless the story's ACs name the path.
  - The wrapper refuses to push a branch whose diff against `main` touches `.github/workflows` unless the story declares it.
  - Confirm that `reviewers` is read only from the approved config on `main` (unknown today).
- **Code areas:** `prbody.py`, `cli.py` (`_git` push), `config.py`, `stations/S11-pr.md`
- **Acceptance:** Each sensitive path is flagged, and an undeclared workflow push is refused.
- **Unit tests:** Fixture diffs.
- **Integration / E2E:** A sandbox story that edits a workflow stops at S11.
- **Security validation:** Paired with HA-4, a token without `workflow` scope, so GitHub itself rejects such pushes.
- **Depends on:** SR1.5, SR3.3
- **PR boundary:** Detection and the push refusal.
- **Done when:** Merged.

#### SR5.3 GitHub lookups without fixed limits

**Priority:** Medium

- **Findings:** N14
- **Problem:** Only the newest 200 PRs and 100 commits are read, so the state can turn UNCONFIGURED in the middle of a story.
- **Solution:** Record the Planning PR number in the increment's records on `main` and fetch it directly. Use search qualifiers or pagination for the rest. Bound the commit scan by the merge base. Fail closed: if a story is in progress but its increment can't be found, the state is INCONSISTENT, never UNCONFIGURED.
- **Code areas:** `state.py` (lines 714, 753), `closeout.py` (line 177), `issues.py` (line 328)
- **Acceptance:** With 500 fake PRs and the plan branch deleted, the increment is still found.
- **Unit tests:** A large fake gh.
- **Integration / E2E:** An SR6.3 cell for a busy repository.
- **Security validation:** The search results go through SR5.1's trust function.
- **Depends on:** SR5.1
- **PR boundary:** Snapshot code.
- **Done when:** Merged.

### SR6 · Portability

Exit: the factory works on the targets you will actually use, and proves it.

#### SR6.1 An install step in verification

**Priority:** High (portability)

- **Findings:** N6; B-53
- **Problem:** A story that adds a dependency fails verification, because nothing installs it.
- **Solution:** `verify run` first runs the approved `install` command, in E3's cleaned environment, when a manifest or lockfile changed or no install is recorded for the current lockfile hash. The ledger records it. The verifier uses the same factory command rather than its own shell, which is B-53's safer option. Document install commands that skip lifecycle scripts as the recommended config. Update S08 and S09.
- **Code areas:** `evidence.py` (`VERIFY_COMMANDS`, line 129), `manifests.py`, `.claude/agents/ac-verifier.md`, S08, S09, S10
- **Acceptance:** A Node story that adds a dependency passes. A failed install is recorded with its reason.
- **Unit tests:** Node and Python fixtures.
- **Integration / E2E:** An SR6.3 matrix cell.
- **Security validation:** Install runs package scripts, so trust levels TL2 and above need isolation (RG-F).
- **Depends on:** SR4.5; DEC-6
- **PR boundary:** Verification only.
- **Done when:** Merged.

#### SR6.2 Consistent text and encoding

**Priority:** Low

- **Findings:** N21
- **Problem:** Wrong recovery advice, stale diff references, and a garbled `…` on Windows.
- **Solution:**
  - The command files and `target.py` errors say: run `python scripts/factory.py target set <path>` yourself, in a terminal.
  - S08, S10 and S11 use GitHub's SHAs (B-28).
  - The guard's stderr is UTF-8, or falls back to ASCII `...`.
- **Code areas:** `.claude/commands/*.md`, `target.py` (lines 121–134), `stations/S08`, `S10`, `S11`, `guard_hook.py`
- **Acceptance:** No stale advice anywhere (lint), and the guard's message reads correctly on cp1252.
- **Unit tests:** A doc lint; an encoding test.
- **Integration / E2E:** None.
- **Security validation:** None.
- **Depends on:** None (scheduled before T9)
- **PR boundary:** Text only.
- **Done when:** Merged.

#### SR6.3 Portability matrix and hostile targets

**Priority:** Required for RG-F

- **Findings:** N3, N6, N7, N8, N14, N16 (proven together); B-49, B-53
- **Problem:** The factory has been proven only on a Python standard-library sandbox and on Task Tracker.
- **Solution:** Use the T8.2 harness and T9.7's hostile suite. The matrix of fixture targets is listed under [SR6.3 matrix dimensions](#sr63-matrix-dimensions).
- **Code areas:** `tests/evals/` (from T8.2), fixture repositories
- **Acceptance:** Every cell is green, or has a documented limitation and a trust level that excludes it. No cell merges, pushes to the default branch, or duplicates an issue, branch or PR.
- **Unit tests:** The offline evals for each cell.
- **Integration / E2E:** Live, one story per cell.
- **Security validation:** The hostile cells (T9.7) plus a fork-PR cell and a workflow-edit cell.
- **Depends on:** T8.2, T9.7, T9.8, SR5.\*, SR6.1
- **PR boundary:** One PR for the matrix definition, then one per failing cell's fix.
- **Done when:** The matrix report is merged and its results are recorded in `docs/progress.md`.

## Release gates

Every gate includes all earlier gates. "Suite green" means `python -m unittest` with 0 failures and 0 errors, skips no higher than today's 5 (each one explained), run once with a target pointer present and once without; `ruff` clean. A gate closes again if any of its checks regresses.

### Live checks (run by you; results recorded in the task log)

| ID | Check | Pass when | Gate |
|---|---|---|---|
| LC-1 | L5: `NEEDS_HUMAN` without invoking Claude (T8.1's open check) | The runner exits 3 with zero invocations in its log. | RG-B |
| LC-2 | Guard start-up failure, in a throwaway factory checkout with a broken `guard_hook.py` | The runner refuses before invoking Claude. In an interactive session in that checkout, every Bash call is blocked (exit 2). | RG-B |
| LC-3 | Concurrency | While one runner is active, a second runner and an interactive `/factory-continue` are refused, naming the lock holder. | RG-B |
| LC-4 | Kill during a station: Ctrl+C the runner during S09's `verify run`, and once during pick | No orphan `python`/`git`/test processes; no `.git/index.lock`; the next run resumes at the same station; no duplicate commit, PR, comment or label. | RG-B |
| LC-5 | Recovery: the sandbox #3 pattern (an H3 question at S11) | The answer is recorded as a decision; the runner resumes at S09 and reaches Gate B; exactly one question comment exists. | RG-C |
| LC-6 | One story, Gate C → Gate B, in a single runner run | Exit 0 (or the outcome DEC-2 defines); 0 permission denials; a scratch rewrite is not denied; the PR's evidence matches the ledger. | RG-C |

### RG-A · Safe to resume interactive development

- **What it allows:**
  - **Ordinary interactive target work**, on the private sandbox only: `/factory-status`, `/factory-continue` and `/factory-resume`, with you watching.
  - **Factory development** (writing SR PRs) is allowed **now**, before RG-A, provided no target is active. In that mode the guard does not protect the factory's code, because you are editing it, and every change arrives as a PR you review.

  **Sensitive activities** are never done in target mode, and only in a factory-development PR that names them: changes to `scripts/`, `.claude/` (settings, agents, commands), `stations/_rules.md`, `.factory-local/`, `~/.claude/`, the target's `.github/workflows`, and the `reviewers`, `limits` and `default_branch` keys of `.factory/config.json`.
- **Required tasks:** SR0.1, SR0.2, SR0.3, SR1.1, SR1.2, SR1.3, SR1.5, SR1.6, SR1.7
- **Required test suites:** The full unit suite; the guard matrix tests (SR1.1, SR1.6–SR1.7); the launcher tests (SR1.3); the wrapper push tests (SR1.5); the settings lint (SR1.2); the station-command lint (every prescribed command is allowed).
- **Expected results:**
  - The suite is green in both pointer states.
  - Re-running the probes blocks every N1, N4, N9, N20 and N22 case. Only the cases the stations need stay allowed, and the PR lists them.
  - A broken temporary module makes the hook exit 2.
  - The SR1.2 live check shows `git -C … config` as denied.
- **Human review:** You review and merge every PR. You review SR1.2 (and SR1.3's settings line) line by line.
- **Pass:** All of the above. The sandbox is still private, with you as its only collaborator. One session at a time (HA-2).
- **Fail:** Any listed probe case still allowed; any suite failure; any pre-approved rule broader than before; any station command now blocked.

### RG-B · Safe to resume headless execution (private sandbox)

- **Required tasks:** RG-A plus SR1.4, SR1.8, SR2.1, SR2.2, SR2.3, SR2.4, SR3.1, SR3.2, SR3.3, SR3.4
- **Required human actions and decisions:**
  - HA-3: branch protection or a ruleset on the sandbox's `main`. If your plan doesn't offer it on private repositories, DEC-8 is your written acceptance of the compensating controls (SR1.2, SR1.4 pin, SR1.5).
  - HA-4: a token without `workflow` or admin scopes.
  - DEC-5, DEC-6, DEC-9 and DEC-10 recorded.
- **Required test suites:** Unit: the lock race and stale lock; the single label PUT and repair; kill-tree on timeout and on Ctrl+C; budget stops; the preflight refusals (each settings layer, a failing canary, a changed hash, an unprotected default branch); the scratch clash, `--add-dir` and guard area tests; the transition table; derived counters and limit stops; recovery mapping; decision idempotency and answer trust. Offline: the sandbox #3 replay with the fake factory.
- **Expected results:**
  - The suite is green in both pointer states.
  - Every SR2/SR3 acceptance test passes.
  - The probe `probe_state.py` case 3 no longer ends at INCONSISTENT without a repair path.
- **Entry, then confirmation:** Entry: all of the above merged and green. Confirmation: LC-1, LC-2, LC-3 and LC-4 pass in **supervised** runs (you watching). Any failure closes the gate again and pauses the runner.
- **Human review:** Every PR. You run the LC checks and record their output.
- **Pass:** Entry plus confirmation met. The covered risks: guard bypass (SR1.1, SR1.2, SR1.8), guard start-up failure (SR1.3, SR1.4, LC-2), unsafe commands (SR1.5–SR1.7), concurrent sessions (SR2.1, LC-3), and incomplete recovery (SR2.2, SR2.3, SR3.3, SR3.4, LC-4).
- **Fail:** Any LC fails; any runner exit with an orphan process; any duplicate GitHub object; any push outside the allowlist in the logs.

### RG-C · Safe to start T8.2

- **Required tasks:** RG-B (all of it)
- **Required live results:** LC-5 and LC-6 pass. T8.1's residual checks are closed: L5 = LC-1, and L4 in one run = LC-6.
- **Required decisions:** DEC-2 (B-56): how a recovered denial is treated, because T8.2's live evals depend on the runner's exit codes.
- **Required test suites:** Everything in RG-B, plus fake-factory tests that state-table rows still route as before (an early piece of T8.2's offline evals is not needed).
- **Expected results:** As in RG-B; LC-5 and LC-6 logs attached to the task log.
- **Human review:** You confirm the LC records and accept ADR-0007's insertion point as complete.
- **Pass:** All met; the T8.2 branch can then be created.
- **Fail:** LC-5 or LC-6 fails, or the DEC-2 decision is missing.

### RG-D · Safe to start T8.3

- **Required tasks:** RG-C plus T8.2 merged, then SR4.1, SR4.2, SR4.3, SR4.4 and SR4.5
- **Required decisions:** DEC-3 (H3 policy at S09) and DEC-4 (verifier provenance)
- **Integrity requirements:**
  - **Metrics:** every metric T8.3 will compute has a named source: the ledger, a checkpoint, the GitHub timeline, or a machine-written log line.
  - **Timestamps:** from the machine (SR4.1) or GitHub (SR4.2). Historical Task Tracker data whose timestamp source is unknown is labelled as such in T8.3's acceptance data.
  - **Evidence:** H3 runs at S09 and catches skips (SR4.3); verdict provenance is recorded or honestly labelled (SR4.4); changed command definitions are flagged (SR4.5).
  - **Limits and counters:** derived and enforced by code (SR3.2).
  - **State transitions:** declared and validated (SR3.1), with labels changed atomically (SR2.2).
- **Required test suites:** The SR4 unit tests; T8.2's offline evals green; T8.2's six live scenarios green, including Gate B `/changes` under a skewed clock if one is available.
- **Expected results:**
  - Probe case 5 (+1 h) → CHANGES_REQUESTED.
  - No station text asks the model for a time.
  - Every PR body states where its verdict came from.
- **Human review:** Every PR, plus your decisions DEC-3 and DEC-4.
- **Pass / Fail:** Pass when all are met. Fail on any metric input without a source, or any model-supplied counter or timestamp still accepted.

### RG-E · Safe to resume T9

- **Required tasks:** RG-D plus T8.3 merged, then SR5.1, SR5.2, SR5.3, SR6.1 and SR6.2
- **Required decisions:**
  - DEC-7 (B-49, a bot identity without merge permission): decided, even if it is built later.
  - T9.5's scope note recorded in ADR-0007: T9.5 covers mid-session guard writes and start-up failure (N1, N2), and its in-session canary is built on SR1.3 and SR1.4.
- **Required test suites:** SR5 and SR6 unit tests; T8.2's full eval suite (offline and live) green; a fork-PR scenario and a workflow-edit scenario added to T8.2's harness.
- **Expected results:**
  - Probe cases 1b, 2b and 4 are ignored, and the state stays `IDLE_AT_GATE_C`.
  - A Node fixture story that adds a dependency passes verification.
  - No stale `/factory-target <path>` advice remains.
- **Human review:** Every PR; your DEC-7 decision; a review of T9's plan against this roadmap's overlaps (see [Existing roadmap integration](#existing-roadmap-integration)).
- **Pass / Fail:** Pass when all are met. Fail if any reader trusts an unauthenticated marker, or a sensitive path changes without a flag.

### RG-F · Safe for unrelated repositories

- **Required tasks:** RG-E plus T9.1–T9.9 merged (including T9.5's canary, T9.6's `doctor` checks, T9.7's hostile suite and T9.8's Windows matrix), then SR6.3
- **Additional requirements:**
  - **Identity:** B-49 implemented (a bot without merge permission), **or**, on every target, `doctor` verifies branch protection with required reviews.
  - **Isolation:** for trust level TL2 and above, verification and installs run where your `gh` credentials and home folder can't be read (a container, a VM, or a separate OS user). Stripping environment variables (E3) is not enough: test code can read `~/.config/gh`.
  - **A trust-level policy** recorded (see [When the factory is safe for unrelated repositories](#when-the-factory-is-safe-for-unrelated-repositories)).
  - **Several machines:** if more than one machine can drive the same target, a lock marker on GitHub (an extension of SR2.1).
- **Required test suites:** The SR6.3 matrix; T9.7's hostile suite; T9.8's Windows matrix; the full eval suite through the plugin.
- **Expected results:** Every matrix cell is green or documented as excluded; zero merges; zero pushes to a default branch; zero duplicate objects.
- **Human review:** You sign off the matrix report and the trust-level policy.
- **Pass / Fail:** Pass when all are met. Fail on any cell that is red and not excluded, or on a target whose trust level isn't covered.

### What each finding blocks

Required = must be fixed before that activity. If … = required only in the stated condition. Each column is one release gate (see [Release gates](#release-gates)).

| ID | Earliest gate | Interactive target runs (RG-A) | Headless (RG-B) | T8.2 (RG-C) | T8.3 (RG-D) | T9 (RG-E) | Unrelated repos (RG-F) |
|---|---|---|---|---|---|---|---|
| N1 | RG-A | Required | Required | Required | Required | Required | Required |
| N2 | RG-A | Required | Required | Required | Required | Required | Required |
| N3 | RG-E | If others can write | If others can write | If others can write | If others can write | Required | Required |
| N4 | RG-A | Required | Required | Required | Required | Required | Required |
| N5 | RG-B | — | Required | Required | Required | Required | Required |
| N6 | RG-E | If a story adds a dependency | If a story adds a dependency | — | — | Required | Required |
| N7 | RG-D | — | — | — | Required | Required | Required |
| N8 | RG-F | If the default isn't main/master | If the default isn't main/master | — | — | — | Required |
| N9 | RG-A | Required | Required | Required | Required | Required | Required |
| N10 | RG-B | — | Required | Required | Required | Required | Required |
| N11 | RG-B | — | Required | Required | Required | Required | Required |
| N12 | RG-B | — | Required | Required | Required | Required | Required |
| N13 | RG-B | — | Required | Required | Required | Required | Required |
| N14 | RG-F | — | — | — | — | If more than 200 PRs | Required |
| N15 | RG-D | — | — | — | Required | Required | Required |
| N16 | RG-E | If the token has `workflow` scope | If the token has `workflow` scope | Same | Same | Required | Required |
| N17 | RG-D | — | — | — | Required | Required | Required |
| N18 | RG-D | — | — | — | Required | Required | Required |
| N19 | SR0 | Required | Required | Required | Required | Required | Required |
| N20 | RG-E | — | — | — | — | Required (cheap clean-up) | Required |
| N21 | RG-E | — | — | — | — | Required (T9.9 doc lint) | Required |
| N22 | RG-B | — | Required | Required | Required | Required | Required |
| N23 | RG-B | — | Required | Required | Required | Required | Required |
| K1 | RG-B | — | Required | Required | Required | Required | Required |
| K2 | RG-B | — | Required | Required | Required | Required | Required |
| K3 | RG-B | — | Required | Required | Required | Required | Required |
| K4 | RG-D | — | — | — | Required | Required | Required |
| K5 | RG-B | — | Required | Required | Required | Required | Required |

**The rule behind the RG-A column:** a finding blocks interactive runs if a session can exploit it *with pre-approved commands*, so no approval prompt appears, and it breaks S1, S3 or S5 or redirects a push. Findings that need a command which would show you a prompt wait for RG-B, where nobody is there to answer prompts.

## Existing roadmap integration

| Option | Assessment | Verdict |
|---|---|---|
| **1.** Finish T8.2, T8.3 and T9 first | T8.2's live evals *are* headless runs, which N1, N2, N5, N11 and K1–K3 make unsafe or unreliable. T8.3 would compute metrics from counters the model supplies and timestamps it estimates (N12, N17). T9 would package a guard that can be rewritten. The eval baselines recorded along the way would be invalid. | Reject |
| **2.** A dedicated milestone before T8.2 | Matches ADR-0001's intent (no T-task pulled forward) and the B-28 and B-46 precedent. As a single block, though, it would hold up T8.2 for items needed only by T9 or other repositories (N3, N6, N14). | Adopt, refined |
| **3.** Reorder or split T8/T9 tasks | Breaks ADR-0001 and the rule never to edit a task's specification. The overlaps (T9.5, T9.6, T9.9) can be handled by recording them instead. | Reject |
| **4.** Leave the roadmap unchanged and track remediation separately | Needed for the records, but on its own it doesn't say *when* each fix is due, so remediation drifts. | Adopt as the record-keeping half |

**Recommendation: options 2 and 4 combined.** Milestone SR has its own IDs, ADR-0007 and task-log sections, and is inserted at four points: SR0–SR3 before T8.2; SR4 between T8.2 and T8.3; SR5 and SR6.1–SR6.2 between T8.3 and T9.1; SR6.3 after T9.9. T-task IDs, specifications and order are unchanged, and `docs/05` is not edited. ADR-0007 needs your acceptance (DEC-1), because it extends ADR-0001's sequence in the same way B-28 and B-46 did.

### Overlaps to record, not move

- **SR1.3 and SR1.4 ↔ T9.5:** SR delivers the fail-closed launcher and the runner-side canary. T9.5 keeps the in-session `guard-canary` at step 0 of every command, the SessionStart warning, the M4 gaps (B-09, B-12, B-13) and the 775-call replay.
- **SR1.4 (settings layers) ↔ T9.6:** `doctor` keeps its FAIL and WARN rules for the target's settings.
- **SR6.2 ↔ T9.9's doc lint;** **SR6.3 ↔ T9.7's hostile suite** (SR6.3 uses it).
- **SR2.1 and SR2.3 ↔ T8.2's kill-and-resume scenario;** **SR4.x ↔ T8.3's inputs.**
- **Backlog items that stay where they are:** B-11 and B-15 (with SR4.5 and RG-F), B-24 (HA-3, with T9.6), B-30 and B-44 (closed by SR3.3 and SR4.3), B-49 (DEC-7), B-53 (DEC-6, SR6.1), B-56 (DEC-2).

## When to resume T8.2

- RG-A met (SR0, SR1.1–1.3, SR1.5–1.7 merged; probes blocked).
- RG-B met (SR1.4, SR1.8, SR2.\*, SR3.\* merged; HA-3 or DEC-8; HA-4; DEC-5, 6, 9, 10; LC-1 to LC-4 passed under supervision).
- RG-C met (LC-5 and LC-6 passed; DEC-2 recorded; T8.1's L4 and L5 closed in the task log).
- Then create `task/T8.2-eval-harness`, as specified in `docs/05`.

## When to resume T8.3

- T8.2 merged, with its offline and live evals green.
- SR4.1–SR4.5 merged; DEC-3 and DEC-4 recorded.
- RG-D's integrity checks pass: every metric input has a source; no model-supplied counters or timestamps; verdict provenance shown; changed command definitions flagged.
- The timestamp source of Task Tracker 001–003's historical data has been established and is labelled in T8.3's fixtures.

## When to resume T9

- T8.3 merged (M8 complete: demo recorded in `docs/progress.md`).
- SR5.1–SR5.3, SR6.1 and SR6.2 merged.
- DEC-7 (bot identity) decided; T9.5's scope note in ADR-0007.
- T8.2's eval suite includes the fork-PR and workflow-edit scenarios, and they are green.
- Then T9.1 (the spike) first, in order.

## When the factory is safe for unrelated repositories

When RG-F passes, which requires T9 complete, SR6.3 green, B-49 or verified protection, and isolation for TL2 and above. Until then, use the factory only at trust level TL0.

| Trust level | Repository | Allowed after | Extra conditions |
|---|---|---|---|
| TL0 | Your private sandbox; you are the only collaborator | Interactive: RG-A. Headless: RG-B. | Branch protection (HA-3) or DEC-8. |
| TL1 | Your private real project, with dependencies | RG-E | SR6.1 installs; protection required. |
| TL2 | A private or organisation repository with other collaborators | RG-F | SR5.1 marker trust; required reviews; bot identity or verified protection; isolation for verification. |
| TL3 | A public repository, forks, external contributors | RG-F, and only if the matrix includes a public/fork cell that passes | All of TL2; fork PRs ignored; no token with `workflow` scope. Consider leaving TL3 unsupported. |

### SR6.3 matrix dimensions

#### Languages and package managers

Python standard library; Python with pip, uv or poetry; Node with npm, pnpm or yarn; one compiled stack (Go, or Java with Gradle). Each has a story that adds a dependency.

#### Default branches and history

`main`, `master`, `develop`, `trunk`. More than 200 PRs and 100 commits, including Dependabot-style noise. The plan branch deleted after the merge.

#### GitHub configuration

Branch protection and rulesets on and off; required checks; CODEOWNERS; Actions with secrets; forks enabled; private and public visibility; single-account and bot identity.

#### Project structure and platform

A project in a monorepo subfolder; a path with spaces; CRLF line endings; Windows (Git Bash, and a PowerShell host); Linux; macOS with only `python3`; a missing `python` (N2).
