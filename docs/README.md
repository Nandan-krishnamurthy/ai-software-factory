# Factory documentation

This folder documents the factory itself. The documents a target repository gets are described in [templates/README.md](../templates/README.md).

## Index

| Document | Answers | Kind |
|---|---|---|
| [01-factory-requirements.md](01-factory-requirements.md) | What the factory must do: decisions D1–D5, gates, success criteria 1–8 | Living: changed only when a requirement changes |
| [02-factory-architecture.md](02-factory-architecture.md) | How the factory is built: layers, state engine, data model, safety | Living: kept in line with the code by each task |
| [03-factory-plan.md](03-factory-plan.md) | Tasks T0.1–T5.4 (M0–M5), the task format and the global Definition of Done (§3) | Specification, complete |
| [04-task-tracker-test-plan.md](04-task-tracker-test-plan.md) | How to prove success criteria 1–8 on real repositories | Runbook |
| [05-roadmap-m6-m9.md](05-roadmap-m6-m9.md) | Tasks T6.1–T9.9 (M6–M9) | Specification, verbatim original with a separate header |
| [progress.md](progress.md) | What each milestone demo showed | Record, one entry per milestone |
| [task-log.md](task-log.md) | What happened when each task from T6.1 on was built: decisions, deviations, review findings, evidence | Record, one entry per task |
| [backlog.md](backlog.md) | Known gaps, open issues, deferred work, accepted limitations | Living list |
| [adr/](#architecture-decision-records) | Decisions that span tasks, with their context and evidence | Records |

Outside this folder: [README.md](../README.md) (install and usage), [CLAUDE.md](../CLAUDE.md) (how Claude Code works in this repo) and [stations/_rules.md](../stations/_rules.md) (the rules the factory follows on a target).

## Where things stand

The latest milestone is the last entry in [progress.md](progress.md). The latest task is the last entry in [task-log.md](task-log.md), which also names the next one. Tasks run strictly in order ([ADR-0001](adr/0001-strict-sequential-roadmap.md)).

## Where each kind of fact lives

| Question | Source of truth | Not here |
|---|---|---|
| What must a task deliver? | Its section in [03](03-factory-plan.md) (T0.1–T5.4) or [05](05-roadmap-m6-m9.md) (T6.1–T9.9) | The task log, the PR |
| In what order do tasks run? | [ADR-0001](adr/0001-strict-sequential-roadmap.md): strictly sequential | The original roadmap's closing section, which is superseded |
| What was decided while building a task, and how did it deviate? | [task-log.md](task-log.md), citing the PR and the decision | The specification text |
| What is known to be missing, broken or deferred? | [backlog.md](backlog.md) | Task specifications |
| Why is the factory shaped this way across tasks? | [adr/](#architecture-decision-records) | — |
| What does the factory do today? | The code and its tests, described by [02](02-factory-architecture.md) and the [README](../README.md) | Specifications, which say what was asked for |
| What rules does the factory follow on a target? | [stations/_rules.md](../stations/_rules.md) | — |
| Did a milestone demo pass? | [progress.md](progress.md) | — |

## Rules

1. **Specifications are not edited to match what was built.** The task sections of 03 and 05 stay as written. A deviation, an addition or an approved change is recorded in the task log with its source ([task-log.md](task-log.md), "What this log is for").
2. **The roadmap in 05 is verbatim.** Only its header, above the `roadmap:original:start` marker, may change ([ADR-0001](adr/0001-strict-sequential-roadmap.md), [ADR-0002](adr/0002-m6-m9-roadmap-provenance.md)).
3. **Each task updates the documents it affects in the same PR** (03 §3, Definition of Done item 7): the README for usage, station files, 02 if the design changed, 01 if a requirement changed. From T6.1 on, the task's PR also adds or updates its task-log entry and any backlog items it creates, changes or resolves.
4. **Backlog items are never deleted.** They are resolved (with the PR) or accepted. Recording an item does not decide it ([backlog.md](backlog.md), "Rules").
5. **Records state their source.** A task-log entry, a backlog item or an ADR cites a merged PR, a commit, a committed document, the code or a test, or a dated human decision. What cannot be sourced is reported as a gap, not filled in.
6. **When documents disagree:** for what the factory does today, the code and tests win; for what a task must deliver, an approved decision in the task log or an ADR wins over the specification text. Any other disagreement is raised with the human, not resolved by choosing one. Either way it is a documentation bug: fix it in a PR, or record it in the backlog.

## Architecture decision records

| ADR | Decision | Status |
|---|---|---|
| [0001](adr/0001-strict-sequential-roadmap.md) | Strictly sequential roadmap execution | Accepted |
| [0002](adr/0002-m6-m9-roadmap-provenance.md) | The M6–M9 roadmap: rationale and provenance | Accepted |
| [0003](adr/0003-plugin-packaging-in-t9.md) | Plugin packaging and target-root invocation belong to T9 | Accepted, work planned |
| [0004](adr/0004-configured-commands-bash-approved-only.md) | Configured commands run with Bash, and only approved commands run | Accepted, implemented in T6.1; where it reads the default branch from is superseded by 0005 |
| [0005](adr/0005-approved-config-from-github.md) | The approved config is read from GitHub, never from the clone's local refs | Accepted (PR #56, `d666b6f`) |

**Writing an ADR.** Use the next free four-digit number and the sections of the existing ADRs: a header table (Status, Decided, Recorded), Context, Decision, Consequences, Evidence, and gaps where there are any. An accepted ADR is not rewritten. A later decision that replaces it is a new ADR, and the old one's Status becomes "Superseded by ADR-NNNN". Decisions that concern one task only belong in the task log instead.
