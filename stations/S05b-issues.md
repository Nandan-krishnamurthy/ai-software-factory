---
id: S05b
name: Create issues
allowed_from: [GATE_A]
next: GATE_C
---
# S05b Create issues

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation (`<T>`, `<R>`, `<D>`, `<INC>`, `<SCRATCH>`) is as in [S00](S00-intake.md). `<N>` is the merged Planning PR's number.

## Purpose
After the human has approved the plan by merging the Planning PR (Gate A), create one GitHub issue per story, then stop at Gate C.

## Preconditions
- `python scripts/factory.py state --json` reports `ISSUES_PENDING` with `next_station` `S05b`. Use its `increment` as `<INC>`.
- `gh pr list --repo <R> --head factory/plan-<INC> --state merged --json number` lists the merged Planning PR `<N>`. The human merged it: the factory only observes merges.
- `git -C <T> status --porcelain` prints nothing. Otherwise report the files and stop.

## Inputs
- `docs/factory/increments/<INC>/05-stories.md` on `<D>`: the approved version. `issues sync` reads it from GitHub itself.
- `python scripts/factory.py issues sync --dry-run --increment <INC>`: the plan.

## Steps
1. Run `git -C <T> switch <D>` and `git -C <T> pull --ff-only`, so the local clone has the approved documents.
2. Run `python scripts/factory.py issues sync --dry-run --increment <INC>` and read the plan.
3. Run `python scripts/factory.py issues sync --increment <INC>`. It creates only the missing issues, in dependency order, labelled `factory:story` and `status:ready`, so running it again is safe.
4. Run `git -C <T> branch -d factory/plan-<INC>` to remove the local planning branch. If git refuses (the branch is not fully merged), leave it and mention it.
5. If step 3 created any issues, post a summary on the Planning PR:
   - Write it to `<SCRATCH>/issues-<INC>.md`: the issues created, with their numbers and titles, and which stories are ready to start (those with `Blocked by: None`).
   - Run `python scripts/factory.py comment --pr <N> --kind reply --body-file <SCRATCH>/issues-<INC>.md`.
6. Stop at **Gate C**. Tell the human the issues are ready, and that the factory starts the first story only when they say continue (`/factory-continue`). Never pick a story in this station (rule S2).

## Outputs
- One GitHub issue per story on `<R>`, labelled `factory:story` and `status:ready`, with the `factory:story` marker and `Blocked by` translated to issue numbers.
- One marked summary reply on the Planning PR (only when issues were created).

## Checkpoint
The issues themselves are the checkpoint. `issues sync` finds existing issues by their `factory:story` marker and creates only the missing ones, so an interrupted run is finished simply by running this station again. Nothing is committed: the default branch only changes through merged PRs (rule S1).

## Stop conditions
- `issues sync` reports a contract problem in the approved `05-stories.md`. The merged plan cannot be changed here: report the problem and stop. The fix needs a new Planning PR.
- `issues sync` refuses because labels are missing: run `python scripts/factory.py labels ensure`, then run step 3 again.
- `issues sync` reports several issues with the same story marker: report them and stop. A human must remove the extra marker.
- `git -C <T> pull --ff-only` fails: report it and stop. Never reset the default branch.

## Done check
- [ ] `python scripts/factory.py issues sync --dry-run --increment <INC>` reports `0 to create`.
- [ ] `python scripts/factory.py state --json` reports `IDLE_AT_GATE_C` (or `NEEDS_HUMAN` if no story is ready, which must be reported to the human).
