---
id: S04
name: Implementation plan
allowed_from: [S03]
next: S05
---
# S04 Implementation plan

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation (`<T>`, `<R>`, `<D>`, `<INC>`) is as in [S00](S00-intake.md).

## Purpose
Order the work into milestones, so that stories can be cut from the plan and picked one at a time. Every in-scope requirement must be covered.

## Preconditions
- `python scripts/factory.py state --json` reports `PLANNING` with `next_station` `S04`. Use its `increment` as `<INC>`.
- `git -C <T> switch factory/plan-<INC>` and `git -C <T> pull --ff-only` succeed.
- `git -C <T> status --porcelain` prints nothing. Otherwise report the files and stop.

## Inputs
- `docs/factory/increments/<INC>/02-requirements.md`
- `docs/factory/increments/<INC>/03-architecture.md`
- `docs/factory/increments/<INC>/01-codebase-analysis.md`, if it exists.
- `.factory/config.json`: its `commands` and `limits`.

## Steps
1. Read the inputs.
2. Write `docs/factory/increments/<INC>/04-implementation-plan.md` with these sections, in this order:
   - `# Implementation plan: <INC>`
   - `## Milestones`: `### M1: <name>`, `### M2: …`, in build order. Each has a goal, the requirements it delivers, and what can be demonstrated when it is done.
   - `## Dependencies`: which milestone or area must come before which, as a list or a diagram.
   - `## Testing approach`: how each kind of requirement will be tested (unit, integration, end-to-end) and with which runner. Name commands only if they exist in `commands` in `.factory/config.json`. Otherwise say which story will introduce them; never guess one (rule H4).
   - `## Requirement coverage`: a table `| Requirement | Milestone |` with one row for **every** in-scope `REQ-###`.
   - `## Risks`: what could go wrong, and how the plan reduces it.
3. For a **new project**, M1 starts with a **walking skeleton**: the project scaffold, the test runner, one passing test, and CI only if a requirement asks for it (requirements §2.1).
4. Keep milestones small enough to split into stories of under about 400 changed lines each (requirements §4).
5. Append one line to `.factory/log.md`: `<UTC time> S04 <INC> plan`.
6. Commit and push. See Checkpoint.

## Outputs
- `docs/factory/increments/<INC>/04-implementation-plan.md`
- `.factory/log.md`

## Checkpoint
- `git -C <T> add docs/factory/increments/<INC>/04-implementation-plan.md .factory/log.md`
- `git -C <T> commit -m "S04: implementation plan for <INC>" -m "Factory-Station: S04"`
- `git -C <T> push origin factory/plan-<INC>`

## Stop conditions
- An in-scope requirement cannot be placed in any milestone, for example because it depends on something outside the increment: ask the human.
- `git -C <T> status --porcelain` shows changes that this station did not make.

## Done check
- [ ] Every in-scope `REQ-###` (listed under `## Functional` or `## Non-functional` in `02-requirements.md`) has a row in `## Requirement coverage`.
- [ ] For a new project, `### M1` begins with the walking skeleton.
- [ ] `git -C <T> log origin/factory/plan-<INC> -1 --format=%B` shows `Factory-Station: S04`.
- [ ] `python scripts/factory.py state --json` reports `PLANNING` with `next_station` `S05`.
