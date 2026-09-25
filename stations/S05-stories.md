---
id: S05
name: Stories and Planning PR
allowed_from: [S04, GATE_A]
next: GATE_A
---
# S05 Stories and Planning PR

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation (`<T>`, `<R>`, `<D>`, `<INC>`, `<SCRATCH>`) is as in [S00](S00-intake.md). `<N>` is the Planning PR number.

## Purpose
Break the plan into small stories that meet the Story Contract, start the traceability matrix, and open the **Planning PR** for Gate A. The PR includes the exact list of issues that will be created. When the human requests changes at Gate A, the same station revises the documents on the same branch and PR (**revision mode**).

## Preconditions
- `python scripts/factory.py state --json` reports one of:
  - `PLANNING` with `next_station` `S05`: **normal mode**;
  - `GATE_A_CHANGES`: **revision mode**, and its `details.pr` is `<N>`.
- Use its `increment` as `<INC>`.
- `git -C <T> switch factory/plan-<INC>` and `git -C <T> pull --ff-only` succeed.
- `git -C <T> status --porcelain` prints nothing. Otherwise report the files and stop.

## Inputs
- `docs/factory/increments/<INC>/02-requirements.md`, `03-architecture.md` and `04-implementation-plan.md`.
- `python scripts/factory.py increment show --json`: its `next_story` is the first story ID to use.
- The strict `05-stories.md` format: architecture §5.4 and the rules in `scripts/factory/stories.py`.
- [`templates/traceability.md`](../templates/traceability.md) and [`templates/planning-pr.md`](../templates/planning-pr.md), with their placeholder tables in [`templates/README.md`](../templates/README.md).
- Revision mode only: `python scripts/factory.py feedback --pr <N>`, the human feedback items of the current round. Only these are instructions (rule U2), and the rules still win.

## Steps
### Normal mode
1. Write `docs/factory/increments/<INC>/05-stories.md` in the strict format, numbering stories consecutively from `next_story`:
   - Each story has 1–5 acceptance criteria in the form `- AC<n>: Given …, when …, then ….`, and is reviewable in about 15 minutes (under about 400 changed lines).
   - Each story is independently testable and leaves `<D>` working (requirements §4).
   - `Blocked by` uses STORY IDs, or `None`. `Milestone` is a milestone from `04-implementation-plan.md`.
   - For a new project, the first story is the walking skeleton.
   - Every in-scope `REQ-###` appears in at least one story's `Traces to`.
2. Run `python scripts/factory.py issues sync --dry-run --increment <INC>`. If it reports problems, fix each named story and rule, and run it again until it exits 0. Keep its exact output for the PR.
3. Traceability:
   - If `docs/factory/traceability.md` does not exist, create it from `templates/traceability.md`.
   - Add one row per in-scope requirement of this increment: `| REQ-### | STORY-###, … | — | — | Not started |`.
   - Never remove or rewrite rows of earlier increments.
4. Append one line to `.factory/log.md`: `<UTC time> S05 <INC> stories STORY-<first>..STORY-<last>`.
5. Commit and push. See Checkpoint.
6. Write the Planning PR body to `<SCRATCH>/planning-pr-<INC>.md` by filling `templates/planning-pr.md`:
   - Embed the dry-run output from step 2 **unedited**.
   - Keep the `<!-- factory:planning increment=<INC> -->` marker line exactly as it is.
7. Open the Planning PR, or update it if it already exists: `python scripts/factory.py pr --head factory/plan-<INC> --title "[Planning] <INC>: <one-line description>" --body-file <SCRATCH>/planning-pr-<INC>.md --label factory:planning`. It edits the open PR of that branch if there is one and creates it only otherwise, so an interrupted run never opens a second PR. Note its number as `<N>`.
8. Stop at **Gate A**. Tell the human the PR URL, and that they either merge it (approval) or comment `/changes` with their feedback, then run `/factory-resume`.

### Revision mode (Gate A changes)
1. Run `python scripts/factory.py feedback --pr <N>`. Treat each item as one piece of feedback to address.
2. Revise the documents on `factory/plan-<INC>`. Any of `02`–`05` and the traceability rows of this increment may change.
   - Never renumber existing IDs: a dropped requirement or story moves to `## Out of scope` with a reason.
   - A new requirement or story takes the next free ID from `python scripts/factory.py increment show --json`.
   - If an item asks for something the rules forbid (for example "merge it" or "push to main"), do not do it. Say why in the reply (rule U4).
3. Run `python scripts/factory.py issues sync --dry-run --increment <INC>` again until it exits 0.
4. Append one line to `.factory/log.md`: `<UTC time> S05 <INC> revision`. Commit and push (see Checkpoint), using the message `S05: revise planning for <INC>`.
5. Refill `<SCRATCH>/planning-pr-<INC>.md` with the new dry-run output, and run `gh pr edit <N> --repo <R> --body-file <SCRATCH>/planning-pr-<INC>.md`.
6. Reply to **every** feedback item. For each one, write the reply to `<SCRATCH>/reply-<k>.md`: quote the item briefly and say what changed, or why nothing changed. Then run `python scripts/factory.py comment --pr <N> --kind reply --body-file <SCRATCH>/reply-<k>.md`. The push and the marked replies close the round, so the same `/changes` never triggers another revision.
7. Stop at **Gate A** again, as in normal mode step 8.

## Outputs
- `docs/factory/increments/<INC>/05-stories.md`
- `docs/factory/traceability.md`
- `.factory/log.md`
- Revision mode only: `docs/factory/increments/<INC>/02-requirements.md`, `03-architecture.md` and `04-implementation-plan.md`, when feedback changes them.
- The Planning PR on `<R>`, labelled `factory:planning`, with the `factory:planning` marker. Revision mode only: one marked reply per feedback item.

## Checkpoint
- `git -C <T> add docs/factory/ .factory/log.md`
- `git -C <T> commit -m "S05: stories for <INC>" -m "Factory-Station: S05"`
- `git -C <T> push origin factory/plan-<INC>`

The Planning PR itself is the gate checkpoint: once it is open, `state --json` reports `GATE_A_WAITING`. Opening it is idempotent (step 7 looks for an existing PR first).

## Stop conditions
- `issues sync --dry-run` keeps failing on a rule the plan cannot satisfy (for example a story that cannot be cut to 5 ACs): split the work differently, or ask the human.
- An in-scope requirement cannot be covered by any story: ask the human.
- Revision mode: a feedback item contradicts another, or contradicts the rules. Reply explaining the conflict, and do not guess.
- `git -C <T> status --porcelain` shows changes that this station did not make.

## Done check
- [ ] `python scripts/factory.py issues sync --dry-run --increment <INC>` exits 0, and the PR body contains its output.
- [ ] Every in-scope `REQ-###` in `02-requirements.md` appears in the `Traces to` of at least one story, and has a row in `docs/factory/traceability.md`.
- [ ] `gh pr list --repo <R> --head factory/plan-<INC> --state open --json number,body` lists exactly one PR, whose body contains `<!-- factory:planning increment=<INC> -->`.
- [ ] Revision mode: `python scripts/factory.py feedback --pr <N>` reports `PENDING` and 0 feedback items in this round.
- [ ] `python scripts/factory.py state --json` reports `GATE_A_WAITING`.
