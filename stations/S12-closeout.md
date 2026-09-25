---
id: S12
name: Close-out
allowed_from: [GATE_B]
next: GATE_C
---
# S12 Close-out

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation is as in [S00](S00-intake.md) and [S06](S06-pick.md) (`<I>`, `<B>`, `<P>`).

## Purpose
Close out a story after the human has merged its PR. Their merge is the approval (D5). Confirm the merge on GitHub, bring the local clone back to `<D>`, delete the local story branch, tell the human which stories are now unblocked, and mark the story `status:done`. This station **never merges** anything (D1, rule S1) and **never picks the next story** (D2, rule S2). It ends at **Gate C**. What happens next is decided by the command that ran it: `/factory-resume` stops there, and `/factory-continue` goes on to S06 (architecture §7.3).

## Preconditions
- `python scripts/factory.py state --json` reports `CLOSEOUT_PENDING` with `next_station` `S12`. Use `details.issue` as `<I>`, `details.pr` as `<P>`, `details.branch` as `<B>` and `increment` as `<INC>`.
- `git -C <T> status --porcelain` prints nothing. Otherwise report the files and stop; never discard the human's changes.

## Inputs
- `python scripts/factory.py closeout --issue <I> --json`: confirms that the story's PR is merged, and gives the PR, its branch `<B>`, its final head commit (`head_sha`), the merge commit (`merge_sha`) and the stories this close-out unblocks. Read-only.
- `gh issue view <I> --repo <R> --json comments`: whether this close-out's summary is already posted (a previous run was interrupted).

## Steps
1. **Confirm the merge.** Run `python scripts/factory.py closeout --issue <I> --json`. If it refuses, report its message exactly and stop: close-out runs only after a merge that the human made. Note `pr` (it must be `<P>`), `branch` (`<B>`), `head_sha`, `merge_sha` and `unblocked`.
2. **Local clone back to `<D>`:** run `git -C <T> fetch origin --prune`, `git -C <T> switch <D>` and `git -C <T> pull --ff-only`. The merged story is now in the local `<D>`.
3. **Delete the local story branch, but only the merged work.** If `git -C <T> branch --list <B>` lists it, compare `git -C <T> rev-parse <B>` with `head_sha`:
   - If they are equal, the branch holds exactly what the human reviewed and merged: run `git -C <T> branch -D <B>`. If the human squashed or rebased, git sees the branch as not merged, so `-d` would refuse.
   - If they differ, the branch has commits that are not in the PR: keep it, and say so in the summary.

   The remote branch is GitHub's to delete when the PR merges (requirements §9). If it still exists, mention it in the summary and leave it.
4. **Summary.** Unless this close-out's summary is already on the issue, write `<SCRATCH>/closeout-<I>.md`. It says that PR #`<P>` was merged by the human (with the merge commit), which stories are now unblocked (from `unblocked`, as `#<n> <title>`, or "none"), and anything from step 3. It ends with: say continue (`/factory-continue`) to start the next story. Then run `python scripts/factory.py comment --issue <I> --kind reply --body-file <SCRATCH>/closeout-<I>.md`.
5. **Mark the story done:** run `python scripts/factory.py closeout --issue <I> --finish`. It checks the merge again, closes the issue if the merge did not, and sets `status:done`. That label moves the state on from `CLOSEOUT_PENDING`, so every step above runs again if this station is interrupted before it.
6. **Checkpoint**, as a record. See Checkpoint.
7. Stop at **Gate C**. Never run `pick` here: the next story starts only when the human says continue.

## Outputs
- Issue `<I>`: closed, labelled `status:done` (and no other `status:*` label), with the close-out summary as a marked reply.
- The local clone on `<D>`, up to date, without the local branch `<B>` (unless it holds work that is not in the PR).
- The checkpoint on issue `<I>` (`S12` → `GATE_C`).

## Checkpoint
Nothing is committed: close-out changes no file, and the factory never commits to `<D>`. The `status:done` label set by `closeout --finish` (step 5) is the checkpoint the state engine reads. Afterwards, the checkpoint comment records the close-out:
- `python scripts/factory.py comment --issue <I> --kind checkpoint --station S12 --next GATE_C --branch <B> --sha <merge_sha>`

It is written after the label, never before: a story still labelled in progress or in review whose checkpoint said `GATE_C` would not be a valid state.

## Stop conditions
- `closeout --issue <I>` refuses: no merged PR for the story. Report it and stop.
- `git -C <T> status --porcelain` shows changes that this station did not make.
- `git -C <T> pull --ff-only` fails: the local `<D>` has diverged from `origin/<D>`. Report it and stop; never reset it.

## Done check
- [ ] `gh issue view <I> --repo <R> --json state,labels` shows `CLOSED` and `status:done` as the only `status:*` label.
- [ ] `git -C <T> branch --show-current` prints `<D>`, and `git -C <T> status --porcelain` prints nothing.
- [ ] `python scripts/factory.py state --json` reports `IDLE_AT_GATE_C`, or `INCREMENT_COMPLETE` if this was the last story, or `NEEDS_HUMAN` if every remaining story is blocked. It never reports `STORY_IN_PROGRESS`: S12 picks nothing.
