# ADR-0007: Security and reliability milestone SR

| | |
|---|---|
| **Status** | Accepted: DEC-1, the human's decision of 2026-11-06 (`d8543357#1255`, 2026-11-06T08:51:50Z). Recorded by SR0.2 |
| **Decided** | 2026-11-06: DEC-1, milestone SR accepted. With it, three decisions on how SR0.2 records it: [06-remediation-sr.md](../06-remediation-sr.md) is the source of truth for the SR task specifications and release gates; the human actions are numbered HA-1 to HA-8; `CLAUDE.md` is not changed by SR0.2 ([B-85](../backlog.md#b-85)) |
| **Recorded** | 2026-11-06 |
| **Related** | [ADR-0001](0001-strict-sequential-roadmap.md) (extended, not superseded), [ADR-0002](0002-m6-m9-roadmap-provenance.md), [ADR-0006](0006-threat-model-typed-commands-and-executed-code.md); findings [B-57 to B-84](../backlog.md#security-and-reliability-audit-2026-11-04-milestone-sr) |

## Context

- **Two reviews found 28 problems** that the roadmap's tasks do not cover. They are recorded as backlog items [B-57 to B-84](../backlog.md#security-and-reliability-audit-2026-11-04-milestone-sr), each with its audit ID as an alias:
  - the security and reliability audit of 2026-11-04 (N1–N22), plus one problem found when its probe cases were re-run the same day (N23);
  - the root-cause investigation of five known reliability issues, 2026-11-03 (K1–K5).
- **One path is critical.** A session can overwrite the guard's own code, Claude Code's settings or the target pointer with commands that are already pre-approved ([B-57](../backlog.md#b-57), audit N1). Combined with the guard's fail-open start-up ([B-58](../backlog.md#b-58), N2) and the sandbox's unprotected `main` ([B-24](../backlog.md#b-24)), that reaches a push to `main` with no approval prompt. This was shown step by step with probes of pure functions; nothing was run end to end, and no exploitation has been observed. Until it is closed, every other control lives in files that a session can rewrite.
- **The other problems fall into three groups:**
  - safety rules that exist only in station text: limits, transitions, the verifier's independence, sensitive changes;
  - protections that unattended runs need and do not have: a lock, process cleanup, atomic label changes, a scratch folder per target;
  - a narrow test matrix: one Python standard-library sandbox and Task Tracker.
- **The next roadmap tasks depend on these protections.**
  - T8.2's live evals are headless runs.
  - T8.3 computes metrics from counters the model supplies and timestamps it estimates.
  - T9 packages the guard.
  - Eval baselines recorded before the fixes would not be valid.
- **ADR-0001 fixes the order** T0 → … → T9, with no task pulled forward and the roadmap text never edited. The task sections of [05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md) are not edited to match what is built ([README](../README.md), rules 1 and 2).
- **There is a precedent.** B-28 and B-46 ran as standalone hardening tasks before T8.1. They were recorded as backlog items with their own task-log sections, and the roadmap's order and text were unchanged ([task-log.md](../task-log.md#b-28-approved-config-from-github-not-local-refs), "B-28 runs as a standalone hardening task before T8.1").

## Decision

1. **Milestone SR is accepted (DEC-1).** Its tasks are SR0.1 to SR6.3. What each must deliver, how it is tested and what it depends on are specified in [06-remediation-sr.md](../06-remediation-sr.md), the source of truth for the SR tasks and the release gates. Each task:
   - is one PR, on branch `task/SR<m.n>-<slug>`, titled `[SR<m.n>] …`;
   - meets the global Definition of Done ([03-factory-plan.md](../03-factory-plan.md) §3);
   - records its decisions and deviations in [task-log.md](../task-log.md), and updates the backlog items of its findings.

   The human reviews and merges every PR.
2. **SR is inserted at four points.** Inside each point, the order is the one in [06-remediation-sr.md](../06-remediation-sr.md#ordered-remediation-milestones).

   | Point | SR tasks | Before | Release gate after |
   |---|---|---|---|
   | 1 | SR0.1–SR0.3, SR1.1–SR1.8, SR2.1–SR2.4, SR3.1–SR3.4, then the live checks LC-1 to LC-6 | T8.2 | RG-A, RG-B, RG-C |
   | 2 | SR4.1–SR4.5 | T8.3 (after T8.2) | RG-D |
   | 3 | SR5.1–SR5.3, SR6.1, SR6.2 | T9.1 (after T8.3) | RG-E |
   | 4 | SR6.3 | Any unrelated repository (after T9.9) | RG-F |

3. **Release gates RG-A to RG-F decide what may run.** Each gate includes all the earlier ones, and closes again if any of its checks regresses. They are not the factory's own Gates A, B and C. Their full requirements, test suites, pass and fail conditions are in [06-remediation-sr.md](../06-remediation-sr.md#release-gates).

   | Gate | Allows | Requires, in short |
   |---|---|---|
   | RG-A | Interactive target work on the private sandbox, with the human watching | SR0.1–SR0.3, SR1.1–SR1.3, SR1.5–SR1.7 |
   | RG-B | Headless execution on the private sandbox | RG-A, SR1.4, SR1.8, SR2.\*, SR3.\*; HA-3 or DEC-8; HA-4; DEC-5, DEC-6, DEC-9, DEC-10; LC-1 to LC-4 under supervision |
   | RG-C | Starting T8.2 | RG-B; LC-5 and LC-6; DEC-2 |
   | RG-D | Starting T8.3 | RG-C, T8.2, SR4.1–SR4.5; DEC-3, DEC-4 |
   | RG-E | Resuming T9 | RG-D, T8.3, SR5.1–SR5.3, SR6.1, SR6.2; DEC-7 |
   | RG-F | Repositories other than the private sandbox | RG-E, T9.1–T9.9, SR6.3; [B-49](../backlog.md#b-49) or verified branch protection; isolation for trust level TL2 and above |

   Factory development, meaning the SR PRs themselves, is allowed before RG-A, with no target active.
4. **SR extends ADR-0001; it does not replace it.**
   - The T-tasks keep their IDs, their specifications and their order: T8.2 → T8.3 → T9.1 … T9.9. No T-task is pulled forward, and none is split or reordered.
   - [05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md) is not edited, not even its header.
   - ADR-0001 stays accepted and is not edited.
   - SR tasks are inserted between T-tasks, as B-28 and B-46 were, at four fixed points instead of one.
5. **Where SR overlaps T-tasks, the overlap is recorded, not moved.** These notes state scope; they do not edit the T-task specifications.
   - **T9.5** also covers mid-session guard writes and start-up failure (N1, N2). Its in-session canary is built on SR1.3's fail-closed launcher and SR1.4's runner-side canary. T9.5 keeps the canary at step 0 of every command, the SessionStart warning, the M4 gaps (B-09, B-12, B-13) and the 775-call replay.
   - **T9.6:** `doctor` keeps its FAIL and WARN rules for the target's settings; SR1.4 reads the settings layers for the runner.
   - **T9.7 and T9.9:** SR6.3 uses T9.7's hostile suite; SR6.2's text fixes meet T9.9's doc lint.
   - **T8.2 and T8.3:** SR2.1 and SR2.3 serve T8.2's kill-and-resume scenario, and SR4 provides T8.3's inputs.
6. **Records and names.**
   - The findings are in the backlog (B-57 to B-84), with the audit IDs as aliases.
   - Each SR task gets its own task-log section. The status of the decisions and human actions is kept in the task log.
   - **Names:** DEC-*n* are decisions only the human makes; HA-*n* are actions only the human can take (the source's H1–H8, renamed so as not to clash with station rules H1–H6); LC-*n* are live checks; RG-A to RG-F are release gates.

## Root causes

From the remediation roadmap ([06-remediation-sr.md](../06-remediation-sr.md), "Provenance", section D). One fix can cover several findings, but each finding keeps its own acceptance test, so that a later regression in one of them still shows up. Finding IDs are the audit's: N*k* is [B-(56+*k*)](../backlog.md#security-and-reliability-audit-2026-11-04-milestone-sr), and K*k* is B-(79+*k*). N18, N21 and K4 have no shared root cause.

| Root cause | Findings | One fix for all? | Separate acceptance tests needed? |
|---|---|---|---|
| RC1 | **The guard runs in-band and can be changed:** it is code the session can write, in the same Python tree it guards. N1, N2, N22, N23 (and the part of N8 that reads the target config). | Partly. SR1.1 closes the write channels. Durable independence needs code outside the session's reach: the T9 plugin folder (T9.3, T9.4) plus SR1.4's hash pin. | Yes: one per write channel × protected path, and one per failure mode on start-up. |
| RC2 | **Block lists instead of allowlists** for commands with side effects: N4, N9, N20, the git half of N1, N16. | Yes, in principle. Allowlists for push destinations (SR1.5), git config writes (SR1.6) and gh endpoints (SR1.7) replace many patterns. | Yes: each probe case becomes a regression test. |
| RC3 | **Code trusts facts the model supplies:** N8 (default branch), N12 (counters), N15 (verdicts), N17 (timestamps), K3 (free-text answers). | No single fix. The principle is that code derives each fact from GitHub or the machine, never from the model's arguments. | Yes. |
| RC4 | **GitHub objects are trusted by marker,** without checking who wrote them: N3, N16 (the `reviewers` key), and K3's answers. | Yes: one trust function (reviewer author, same-repo PR, labelled issue) used by state, sync, pick, checkpoint and decisions. | Yes: one per reader. |
| RC5 | **Rules exist in prose, not code:** K1, K2, N12, N15, N16 (S5). | Partly. The transition table (SR3.1) is the base that SR3.2–SR3.4 build on. | Yes. |
| RC6 | **No single writer and no atomic steps:** N5, N13, N11. | No. They need a lock, an atomic label call and process-tree control, each separately. | Yes, plus one combined live kill-and-resume check (LC-4). |
| RC7 | **One shared, global scratch folder:** N10, K5. | Yes: one per-target folder helper, plus `--add-dir` for it. | Yes: a clash test (N10) and a headless overwrite test (K5). |
| RC8 | **A narrow test matrix:** N6, N7, N8, N14, N19, and the portability gaps. | No. Each needs its own fix; SR6.3 proves them together. | Yes, as matrix cells. |

**Why SR1.1 comes first.** Only two controls are enforced outside the factory's Python code: branch protection on GitHub (HA-3) and Claude Code's own permission rules (SR1.2). Every other control is code that a session can rewrite while N1 is open. So SR1.1 closes the write channels before any other code fix, and HA-3 (or DEC-8) is a requirement of RG-B.

## Task dependencies and sequencing

The full list is in [06-remediation-sr.md](../06-remediation-sr.md#ordering-dependencies-between-tasks), and each task states its own "Depends on". The dependencies that fix the order:
- SR0 changes no behaviour. SR0.1 records T8.1's merge; SR0.2 records this decision and the findings; SR0.3 makes the suite pass with and without a target pointer, so every later PR has clean evidence.
- SR1.1 comes before every other code fix. SR0.3 → SR1.1 and SR1.3, which reuse its temporary-factory test pattern. SR1.1 → SR1.2, SR1.5, SR1.6 and SR1.8, which work on the same guard code. SR1.3 → SR1.4.
- SR2.1 → SR2.2. SR1.1 and SR1.8 → SR2.4.
- SR3.1 → SR3.2, SR3.3 and SR3.4. SR3.3 and SR2.2 → SR3.4.
- SR3.3 → SR4.3 and SR4.5. SR4.5 → SR6.1.
- SR3.4 → SR5.1 → SR5.3. SR1.5 and SR3.3 → SR5.2.
- T8.2, T9.7, T9.8, SR5 and SR6.1 → SR6.3.

## Decisions DEC-1 to DEC-10

Only the human makes these. Their status is kept in [task-log.md](../task-log.md#milestone-sr-decisions-and-human-actions).

| ID | Decision | Needed by | Related |
|---|---|---|---|
| DEC-1 | Accept milestone SR and ADR-0007 | SR0 | This ADR. **Decided 2026-11-06** |
| DEC-2 | How rule R5 treats recovered denials | RG-C | [B-56](../backlog.md#b-56) |
| DEC-3 | Rule H3 policy: S09 fixes undeclared test changes itself | RG-D | SR4.3; [B-83](../backlog.md#b-83) |
| DEC-4 | Verifier provenance: a separate process (a) or labelling (b) | RG-D | SR4.4; [B-71](../backlog.md#b-71) |
| DEC-5 | The decision answer format (`/choose 1` or `1`) | RG-B | SR3.4; [B-82](../backlog.md#b-82) |
| DEC-6 | How headless runs get the configured commands | RG-B | [B-53](../backlog.md#b-53); SR6.1 |
| DEC-7 | A bot identity without merge permission | RG-E | [B-49](../backlog.md#b-49) |
| DEC-8 | If branch protection is unavailable: accept the compensating controls in writing | RG-B | HA-3; [B-24](../backlog.md#b-24) |
| DEC-9 | Runner budget defaults (wall-clock time, cost) | RG-B | SR2.3; [B-67](../backlog.md#b-67) |
| DEC-10 | Lease design for two interactive sessions | RG-B | SR2.1; [B-61](../backlog.md#b-61) |

## Human actions HA-1 to HA-8

Only the human can take these. Their status is kept in [task-log.md](../task-log.md#milestone-sr-decisions-and-human-actions).

| ID | Action | Needed by |
|---|---|---|
| HA-1 | Keep the headless runner paused until RG-B | RG-B |
| HA-2 | One factory session at a time until SR2.1 | RG-A |
| HA-3 | Branch protection or a ruleset on the sandbox's `main` (check the GitHub plan first) | RG-B |
| HA-4 | Check the `gh` token's scopes; drop `workflow` and admin scopes | RG-B |
| HA-5 | Clear the stale factory scratch files in `%TEMP%` before the next target-mode run (until SR2.4) | RG-A |
| HA-6 | Remove the target pointer, in a terminal, while developing the factory | SR0 |
| HA-7 | Optional: delete the remote branch `story/3-several-paths-stdin-options` on the sandbox | — |
| HA-8 | Review `~/.claude/projects/…/memory/` for unexpected entries before headless runs ([B-78](../backlog.md#b-78)) | RG-B |

## Relationship to existing backlog items

These items stay where they are; SR does not merge, close or rewrite them. Their cross-references were added by SR0.2.

| Item | Relationship |
|---|---|
| [B-11](../backlog.md#b-11) | Stays with T9.5's scope decision and RG-F. Its evidence side is [B-74](../backlog.md#b-74) (N18, SR4.5) |
| [B-14](../backlog.md#b-14) | The no-target case. The target-mode case is [B-79](../backlog.md#b-79) (N23, SR1.8) |
| [B-15](../backlog.md#b-15) | Unchanged; required by RG-F's isolation requirement, with B-49 |
| [B-24](../backlog.md#b-24) | HA-3 (or DEC-8) for RG-B; SR1.4's refusal of an unprotected default branch; [B-64](../backlog.md#b-64) (N8). Keeps T9.6 as its owner |
| [B-30](../backlog.md#b-30) | Part of K4, [B-83](../backlog.md#b-83). Owner: SR4.3 |
| [B-44](../backlog.md#b-44) | Part of K2, [B-81](../backlog.md#b-81). Owner: SR3.3 |
| [B-45](../backlog.md#b-45) | Overlaps [B-65](../backlog.md#b-65) (N9, SR1.6). Unchanged |
| [B-46](../backlog.md#b-46) | N1 ([B-57](../backlog.md#b-57)) and N9 ([B-65](../backlog.md#b-65)) are gaps in what it built. Its history and open follow-ups (D-6, D-8, finding 5) are unchanged |
| [B-49](../backlog.md#b-49) | DEC-7 for RG-E; built, or replaced by verified protection, for RG-F |
| [B-53](../backlog.md#b-53) | DEC-6 for RG-B; the install step is [B-62](../backlog.md#b-62) (N6, SR6.1) |
| [B-56](../backlog.md#b-56) | DEC-2 for RG-C |

## Consequences

- **What may run now.**
  - No target-mode session runs until RG-A, and the headless runner stays paused until RG-B (HA-1).
  - T8.2 starts only after RG-C. Its start is delayed by SR0–SR3 and the live checks, T8.3's by SR4, and T9's by SR5, SR6.1 and SR6.2.
- **SR tasks are developed with no target active** (HA-6), because the guard makes `scripts/` read-only while a target is active. In that mode the guard does not protect the factory's own code, so every change arrives as a PR the human reviews.
- **The records grow.** Every SR PR updates its findings' backlog items and adds a task-log section. After SR0.3, its test evidence is a suite run with a target pointer present and one without.
- **Two places can be out of date, and both are recorded.**
  - `CLAUDE.md` names only ADR-0001's T0 → … → T9 order, and no design document after docs/05 ([B-85](../backlog.md#b-85)).
  - The architecture document states two rules as enforced that no code enforces: `allowed_from` ([B-80](../backlog.md#b-80)) and the rework limits ([B-68](../backlog.md#b-68)). SR3.1 and SR3.2 correct them.
- **The remediation roadmap artifact is a snapshot of 2026-11-04.** [06-remediation-sr.md](../06-remediation-sr.md) replaces it as the source of truth, in the way [ADR-0002](0002-m6-m9-roadmap-provenance.md) made docs/05 the source of truth for M6–M9.

## Evidence

- **The findings and their sources:** [backlog.md](../backlog.md#security-and-reliability-audit-2026-11-04-milestone-sr), B-57 to B-84. Each cites the audit (`876b6b9d#523`, 2026-11-04T07:30:29Z), the investigation (`30230cfe#248`, 2026-11-03T16:18:10Z) or the probe re-run (`d8543357#627`, 2026-11-04T08:45:36Z), with code references at `7aee362`.
- **The specifications and gates:** [06-remediation-sr.md](../06-remediation-sr.md), with the source file's SHA-256 in its provenance.
- **The decision:** the human's message at `d8543357#1255` (2026-11-06T08:51:50Z), which approved DEC-1 and the three decisions on how SR0.2 records it.
- **The precedent:** the B-28 and B-46 sections of [task-log.md](../task-log.md); [ADR-0001](0001-strict-sequential-roadmap.md), "Consequences".
- **SR0.1 done:** [PR #67](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/67), merged 2026-11-06T08:33:40Z, merge commit `b62a0f0`.

## Not decided here

- DEC-2 to DEC-10, each due by the gate shown above.
- How each finding is fixed. Each SR task decides that within its specification, and records it in the task log.
- Changing `CLAUDE.md` ([B-85](../backlog.md#b-85)).
- Whether the remediation roadmap needs revising after a gate fails. A failing gate closes again and pauses the work it allows, but changing a task or a gate is a new decision, recorded in the task log or a new ADR.
