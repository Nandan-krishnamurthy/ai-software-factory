# ADR-0002: The M6–M9 roadmap: rationale and provenance

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-10-08 (roadmap written and approved for sequential execution); 2026-10-21 (committed) |
| **Recorded** | 2026-10-22 |
| **Related** | [ADR-0001](0001-strict-sequential-roadmap.md) |

## Context

- [03-factory-plan.md](../03-factory-plan.md) covers M0–M5 only. By M5 the MVP was implemented and its demos recorded in [progress.md](../progress.md) (M5 record: [PR #35](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/35)).
- The M2–M5 demos left findings with no owning task, for example the ID scanner counting prose mentions, the Gate A `/changes` round never demonstrated, no branch protection on `main`, and the M4 guard gaps ([progress.md](../progress.md)).
- Before PR #40, the plan for the work after M5 existed only in a Claude Code session, and task PRs #36–#39 cited a roadmap that was not in the repository.

## Decision

1. **M6–M9 (tasks T6.1–T9.9) is the plan after M5**, in the text written in a Claude Code session on 2026-10-08, at the human's request, and approved for sequential execution ([ADR-0001](0001-strict-sequential-roadmap.md)).
2. **The repository is the source of truth for it.** It is committed verbatim in [05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md), between the `roadmap:original` markers, with a provenance header written separately.

## Rationale

As stated in the roadmap itself:
- **M6, Deterministic Verification & Review:** facts in a PR come from the factory's code, not from model-written text (success criterion 7).
- **M7, Plans & Target Knowledge:** plans correct by construction, and durable knowledge of each target across increments.
- **M8, Headless Runner, Evals & Metrics:** unattended runs between gates, never past them, and a regression harness that M9 depends on.
- **M9, Plugin Packaging & Target-Root Invocation:** install once, run from the target's root, at least as safe as the current checkout mode (see [ADR-0003](0003-plugin-packaging-in-t9.md)).
- Every open finding from M2–M5 is assigned to a task (the roadmap's open-findings table; their current state is tracked in [backlog.md](../backlog.md), "Earlier findings assigned by the roadmap" and "Guard gaps").
- The global Definition of Done and the invariants of docs/03 apply unchanged: the human merges every PR, one story per explicit `continue`, a fail-closed guard, no factory code in the target.

## Provenance

Recorded in the roadmap header and verified in [PR #40](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/40):
- **Source:** session `1bcf8818-42c6-44aa-82e5-e187c8b50c7e`, JSONL line index 1046, message `msg_011CfpGXNArSnLxXKkQBxurn`, `2026-10-08T06:09:00.993Z`. Requested by the user prompt at line index 1032, which gave the milestone names T6–T9.
- **Integrity:** SHA-256 `9e061a4b6b6e9e33c31044a48191b1f1706c55fba4f87125168d1fc57a1ca533` of the original text. Recomputed from the committed blob on 2026-10-22: it matches. An independent copy is in session `1848d76a…`, line index 81.
- **Committed:** by decision `c878c238#1586` (2026-10-21T16:53:43Z), in PR #40, merge commit `2d95b7c`.

## Consequences

- Each M6–M9 task is specified by its section in docs/05. What happened when it was built (decisions, deviations, review findings) goes in [task-log.md](../task-log.md), never into the original text.
- Deviations already recorded: T6.3 Q6 is "not checked" because the story contract declares no areas ([B-08](../backlog.md#b-08)); T6.4's timed human walk moved to the M6 demo ([B-17](../backlog.md#b-17)).
- The roadmap's closing section on order is superseded ([ADR-0001](0001-strict-sequential-roadmap.md)) but kept.

## Gaps

- The repository records that the human supplied the M6–M9 milestone names, but **not why those four themes were chosen** or where they came from. The rationale above is the roadmap's own stated goals, not the human's motivation.
- The session logs cited above are not in the repository. The provenance relies on PR #40's recorded verification and on the SHA-256, which anyone can recompute from the committed file.
