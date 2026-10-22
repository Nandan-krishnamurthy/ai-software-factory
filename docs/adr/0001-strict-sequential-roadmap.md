# ADR-0001: Strictly sequential roadmap execution

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-10-08 (sequential order); 2026-10-21 (commit the roadmap verbatim) |
| **Recorded** | 2026-10-22 |
| **Related** | [ADR-0002](0002-m6-m9-roadmap-provenance.md), [ADR-0003](0003-plugin-packaging-in-t9.md) |

## Context

The original M6–M9 roadmap ([05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md)) ends with a section, "Does the order T6 → T7 → T8 → T9 need to change?", that recommends running T9.1 (the plugin spike) alongside M6 and pulling T7.1 (structured ID allocation) forward, before the M6 demo.

## Decision

1. **Tasks run strictly in order:** T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9. Every task stays in its own milestone. The roadmap's recommendation to pull T9.1 and T7.1 forward is **rejected**.
2. **A dependency problem is handled when its milestone is reached**, not by reordering the roadmap.
3. **The original text is not edited.** The superseded closing section stays in the roadmap verbatim, as historical text. Later decisions and deviations are recorded outside it: in the roadmap's header, in [task-log.md](../task-log.md), in [backlog.md](../backlog.md) and in ADRs.

## Consequences

- The roadmap's text can be read as originally written. Readers must check the roadmap header and the task log for what has since been decided; the closing section's recommendation is not the plan.
- Work that a task would find convenient to pull forward is deferred instead. Examples already recorded:
  - T6.2 kept S10/S11 failing closed until T6.5 rather than wiring the stations early (decision `12c41339#617`, [B-02](../backlog.md#b-02)).
  - T6.4 shows "no evidence recorded" at Gate B because T6.5 has not wired the stations (decision `c878c238#106` item 5).
  - The T7.1 ID-scanner bug stays open until T7.1 ([B-18](../backlog.md#b-18)), although the M6 demo runs a new increment on Task Tracker, where the original roadmap warns it "can strike again".
- Documentation-only changes, such as the four-PR documentation migration (PR #40 onwards), are outside the T0–T9 sequence and do not reorder it.

## Evidence

- Roadmap header, "Later decisions": the rejection, at `1bcf8818#1053`, 2026-10-08T06:36:54Z ([05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md)).
- [task-log.md](../task-log.md), "Roadmap-level decisions": the sequential order, and the decision to commit the roadmap verbatim with later decisions kept separately (`c878c238#1586`, 2026-10-21T16:53:43Z).
- [03-factory-plan.md](../03-factory-plan.md) header, "Next milestones": M6–M9 "run strictly in order after M5".
- [PR #40](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/40) (merge `2d95b7c`): the roadmap committed byte for byte, with the closing section kept and marked as superseded.

## Not decided here

The original closing section also states two further constraints: M6 before M8 (T8.3 reads the T6.1 ledger), and writing engine calls uniformly as `python scripts/factory.py …` until T9.3. The rejection recorded above concerns pulling T9.1 and T7.1 forward. The repository does not record whether these two constraints were separately adopted. The first is satisfied by the sequential order anyway.
