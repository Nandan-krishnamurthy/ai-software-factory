---
id: S06
name: Pick story
allowed_from: [GATE_C]
next: S07
---
# S06 Pick story

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation (`<T>`, `<R>`, `<D>`, `<INC>`, `<SCRATCH>`) is as in [S00](S00-intake.md).

**Story notation** (used by S06–S11): `<I>` is the story's issue number and `<B>` its branch `story/<I>-<slug>`. `<P>` is the story's PR number. `python scripts/factory.py state --json` gives `<I>` as `details.issue`, and `<B>` as `details.branch` once S07 has written the first checkpoint.

## Purpose
Start exactly one story: apply the unblocked rule, assign the chosen issue and label it `status:in-progress`. This is the only station that starts a story, and only `/factory-continue` runs it (D2, rule S2).

## Preconditions
- `python scripts/factory.py state --json` reports `IDLE_AT_GATE_C` with `next_station` `S06`.
- This station is being run by `/factory-continue`. `/factory-resume` never runs it; if you are running any other command, stop.
- No story is in progress, in review or has changes requested (`pick` checks this again).

## Inputs
- The open story issues on `<R>` and their labels. `pick` reads them itself.

## Steps
1. Run `python scripts/factory.py pick --authorized-by-continue --json`.
   - It chooses the next unblocked story (oldest increment, then lowest milestone, then lowest issue number), assigns it and moves its label to `status:in-progress`. Running it again after an interruption picks the same story, or refuses because the story is already in progress.
   - If it refuses, report its message exactly and stop. Never choose a story yourself, and never change labels by hand to get past it.
2. Note `picked.number` as `<I>` and `picked.title`. Print: `Picked #<I> <title>`.
3. Do not write a checkpoint: the `status:in-progress` label is this station's checkpoint. The state engine then names S07.

## Outputs
- Issue `<I>` on `<R>`: assigned, labelled `status:in-progress` (and no other `status:*` label).

## Checkpoint
The `status:in-progress` label set by `pick` is the checkpoint. With no checkpoint comment yet, `state --json` reports `STORY_IN_PROGRESS` with `next_station` `S07` (the convention in `scripts/factory/state.py`). Nothing is committed.

## Stop conditions
- `pick` refuses: a story is already in flight, nothing is unblocked, or the flag is missing. Report its message and stop.
- `state --json` reports anything other than `IDLE_AT_GATE_C` before this station runs.

## Done check
- [ ] `gh issue view <I> --repo <R> --json labels,assignees` shows `status:in-progress` as the only `status:*` label, and an assignee.
- [ ] `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S07` and `details.issue` `<I>`.
