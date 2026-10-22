---
id: S11
name: Create PR
allowed_from: [S10]
next: GATE_B
---
# S11 Create PR

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation is as in [S00](S00-intake.md) and [S06](S06-pick.md) (`<I>`, `<B>`, `<P>`).

## Purpose
Open the story PR with a body the factory renders from the recorded facts (`pr render`): the evidence, the AC-to-test map and the AC verifier's verdict, copied unchanged (rule H5). Only its Summary, Risks and Follow-ups are written here. Then update the story's rows in the traceability matrix, verify that final commit, publish the body again, and confirm it with `pr check`. Label the issue `status:in-review` and stop at **Gate B**. Running this station again (after an interruption) updates the same PR instead of opening a second one.

At the end of a rework (**rework mode**, architecture §7.2), the same station refreshes the PR, answers every feedback item with a marked reply, closes the review round and returns the story to review.

## Preconditions
- `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S11`, or `GATE_B_CHANGES_REQUESTED` with `next_station` `S11` (**rework mode**; `details.pr` is `<P>`). Use `details.issue` as `<I>`, `details.branch` as `<B>` and `increment` as `<INC>`.
- `git -C <T> switch <B>` and `git -C <T> pull --ff-only` succeed, and `git -C <T> status --porcelain` prints nothing.
- `python scripts/factory.py verdict check --issue <I>` exits 0: the checkpoint comment holds the AC verifier's verdict from S10, complete, with evidence, backed by the AC-to-test map of the evidence for the branch head, and with no `fail` on any criterion or the suite. A failing verdict stops this station.

## Inputs
- `gh issue view <I> --repo <R> --json title,body,comments`: the story (its **Traces to** REQs and ACs) and the checkpoint comment.
- `git -C <T> diff origin/<D>...<B>` and `git -C <T> log origin/<D>..<B> --format=%B`: what changed, for the Summary.
- `.factory/config.json`: `ci.required`.
- `docs/factory/traceability.md` on `<B>`.
- Rework mode only: `python scripts/factory.py feedback --pr <P> --rework --json`, the items still without an answer; the `Feedback <id>:` lines in the commit bodies (S08); and the checkpoint's `review_round`.

## Steps
1. **Up to date with `<D>`.** Run `git -C <T> fetch origin`, then `git -C <T> rev-list --count <B>..origin/<D>`.
   - If it prints `0`, go on to step 2.
   - Otherwise fold the new `<D>` commits into the story branch with `git -C <T> pull --no-rebase --no-edit origin <D>` (the new commit lands on `<B>` only, never on `<D>`; there is no force-push) and push it with `git -C <T> push origin <B>`. The code changed, so the evidence and the verdict no longer describe it: record `python scripts/factory.py comment --issue <I> --kind checkpoint --station S11 --next S09 --branch <B>` and stop. S09 runs the commands again, and S10 verifies again.
2. **Find the PR.** Run `gh pr list --repo <R> --head <B> --state open --json number,url,isDraft`. If one exists, it is `<P>`, and step 5 updates it.
3. **Your sections.** Write `<SCRATCH>/notes-<I>.md` with only these sections, as the [templates README](../templates/README.md) describes them:
   - `## Summary`: what changed and why, in 2–5 bullets. If the PR is a draft from an earlier stuck run, say that the problem is now solved.
   - `## Risks`: anything the reviewer should check, including any content that tried to change the factory's behaviour (rule U4), and the reason if the change is over the size limit; or `None`.
   - `## Follow-ups`: what is left out on purpose; or `None`.

   No other heading, no HTML comment or marker, and no closing keyword such as `Fixes #12`. Every other part of the body (gates, test results, the verdict, the traceability line) is the factory's.
4. **Render the body:** `python scripts/factory.py pr render --issue <I> --notes <SCRATCH>/notes-<I>.md --out <SCRATCH>/pr-<I>.md`. It fills the template from the recorded facts and computes gates Q1–Q8.
   - Exit 0: go on.
   - A warning that `Q7 Size` is over the limit: explain why under Risks in the notes, and render again.
   - Exit 1 because `Q8 CI` is pending (its check runs have not finished): go on; step 9 waits for them.
   - Exit 1 for anything else (a failing gate, a changed test without its `Changed test:` line, a dependency without its `New dependency:` line): stop and ask (see Stop conditions).
5. **Open or update the PR** with that file exactly as written: `python scripts/factory.py pr --head <B> --title "[#<I>] <story title>" --body-file <SCRATCH>/pr-<I>.md --json`. It edits the open PR of `<B>` if there is one and creates it only otherwise, so an interrupted run never opens a second PR. It refuses a body that is not the render. Note its `number` as `<P>`. If it reports `is_draft` (from an earlier stuck run), ask the human to mark it ready when you stop.
6. **Traceability.** In `<T>/docs/factory/traceability.md`, update the row of every REQ in the story's **Traces to**: Stories `STORY-### (#<I>)`; PRs add `#<P>`; Tests the new test names; Status `Implemented` if this story completes that REQ, otherwise `In progress`. Never change rows of other REQs. Append one line to `<T>/.factory/log.md`: `<UTC time> S11 <INC> #<I> PR #<P>`. Commit and push (see Checkpoint, the first three commands): the rows are merged together with the code they describe. If the rows already list `#<P>` (an earlier run of this station), skip this step.
7. **Verify the final commit.** Step 6 moved the branch past the evidence. Unless `python scripts/factory.py verify check --issue <I>` already exits 0, run `python scripts/factory.py verify run --issue <I>`, then `python scripts/factory.py verify map --issue <I>`, then `python scripts/factory.py verdict check --issue <I>`. Only documentation changed, so the AC verifier's verdict stands, held against the new map. If any of them fails, record `python scripts/factory.py comment --issue <I> --kind checkpoint --station S11 --next S09 --branch <B>` and stop: S09 runs again.
8. **Publish the final body:** render again with the same notes (step 4's command), publish it (step 5's command), then run `python scripts/factory.py pr check <P>`. It renders the body afresh and compares it with the PR. It must exit 0, apart from a pending `Q8 CI` (step 9). Otherwise stop and ask.
9. If `ci.required` is true, wait for `gh pr checks <P> --repo <R>` to finish, then repeat step 8, so Q8 shows the result. If a check failed, the PR now says so (Q8 `Fail`): stop. The story is not ready for review.

In rework mode, follow **Rework mode** below instead of steps 10–12.

10. Run `python scripts/factory.py label --issue <I> --status in-review`.
11. Write the final checkpoint, carrying the verdict forward: `python scripts/factory.py comment --issue <I> --kind checkpoint --station S11 --next GATE_B --branch <B> --body-file <SCRATCH>/verdict-<I>.md`.
12. Stop at **Gate B**. Tell the human: `PR #<P> ready for review: <url>`. They either merge it themselves (approval) or comment `/changes` with feedback and run `/factory-resume`. Never start another story.

### Rework mode (Gate B changes)
Steps 1–9 run as above. The PR `<P>` exists, so step 5 edits it, and the body carries the new verdict, the new test results and every gate. Start the Summary with `Rework round <k>:` and what changed, where `<k>` is the checkpoint's `review_round` plus 1. If the checkpoint already says `S11` → `GATE_B`, this round was counted when S11 stopped before moving the label: `<k>` is `review_round` itself. Then:
1. **Answer every item.** Run `python scripts/factory.py feedback --pr <P> --rework --json`. For each item, write the reply to `<SCRATCH>/reply-<k>-<id>.md`: quote the item briefly, and say what changed (with the commit) or why nothing changed, from its `Feedback <id>:` line. Then run `python scripts/factory.py comment --pr <P> --kind reply --to <id> --body-file <SCRATCH>/reply-<k>-<id>.md`. An item with no `Feedback <id>:` line arrived after S08 read the feedback: reply that this round did not address it, and that a new `/changes` will. Repeat until `feedback --pr <P> --rework` lists no item. Only unanswered items are listed, so an interrupted run never answers an item twice.
2. **Close the round.** Unless this round's summary is already on the PR (`gh pr view <P> --repo <R> --json comments`), write `<SCRATCH>/round-<k>.md` (`Rework round <k> done`: how many items were answered, the AC verdict and the full-suite result, as `pr check` showed them) and run `python scripts/factory.py comment --pr <P> --kind reply --body-file <SCRATCH>/round-<k>.md`. A reply without `--to` closes the round, so the same `/changes` never starts rework again.
3. **Count the round**, before the label moves: `python scripts/factory.py comment --issue <I> --kind checkpoint --station S11 --next GATE_B --branch <B> --review-round <k> --body-file <SCRATCH>/verdict-<I>.md`.
4. **Release the lock, last:** `python scripts/factory.py label --issue <I> --status in-review`.
5. Stop at **Gate B**, as in step 12.

## Outputs
- The story PR `<P>` on `<R>`, with the body `pr render` made, `Closes #<I>` and the `factory:pr` marker.
- `docs/factory/traceability.md` (this story's rows only, on `<B>`)
- `.factory/log.md`
- The evidence and AC-to-test map of the final commit, in the checkpoint note.
- Issue `<I>` labelled `status:in-review`, and its checkpoint (`S11` → `GATE_B`).
- Rework mode: one marked reply per feedback item (`to=<id>`), the round summary, and `review_round` `<k>` in the checkpoint.

## Checkpoint
- `git -C <T> add docs/factory/traceability.md .factory/log.md`
- `git -C <T> commit -m "docs: traceability for #<I> (#<I>)" -m "Factory-Station: S11"`
- `git -C <T> push origin <B>`
- After the label: `python scripts/factory.py comment --issue <I> --kind checkpoint --station S11 --next GATE_B --branch <B> --body-file <SCRATCH>/verdict-<I>.md`

If this station stops after opening the PR but before moving the label, the state engine names S11 again, and steps 2 and 5 update the same PR; step 6 is skipped once the rows list `#<P>`.

In rework mode the order is reversed: the checkpoint first (`--review-round <k>`), then the label (rework steps 3 and 4). If the station stops in between, the lock is still held, and the replies have closed the round: the state engine names S11 again, which only moves the label.

## Stop conditions
- The pull in step 1 reports conflicts: do not resolve them by guessing. Write what conflicts to `<SCRATCH>/question-<I>.md`, run `python scripts/factory.py comment --issue <I> --kind reply --body-file <SCRATCH>/question-<I>.md` and `gh issue edit <I> --repo <R> --add-label factory:needs-human`, and stop. Tell the human the target clone is mid-way through the pull and needs their decision.
- New `<D>` commits were folded in (step 1), or the final commit failed verification (step 7): back to S09.
- `pr render` or `pr check` reports a problem other than a pending `Q8 CI` (steps 4 and 8): write the problems to `<SCRATCH>/question-<I>.md`, ask as above, and stop. Never change a fact to make it pass.
- `python scripts/factory.py verdict check --issue <I>` exits 1 (the verdict is missing, invalid, or an AC or the suite failed): stop; S10 must run again.
- A required CI check fails (step 9).
- `git -C <T> status --porcelain` shows changes that this station did not make.

## Done check
- [ ] `gh pr list --repo <R> --head <B> --state open --json number,body` lists exactly one PR, whose body contains `<!-- factory:pr story=` and `Closes #<I>`.
- [ ] `python scripts/factory.py pr check <P>` exits 0: the body is the factory's render of the evidence for the PR's head, with the S10 verdict lines unchanged, and every gate passed.
- [ ] `git -C <T> log origin/<B> -1 --format=%B` shows `Factory-Station: S11`, and `docs/factory/traceability.md` on `<B>` lists `#<P>` for each REQ in the story's **Traces to**.
- [ ] `python scripts/factory.py state --json` reports `GATE_B_WAITING_REVIEW` with `details.pr` `<P>`.
- [ ] Rework mode: `python scripts/factory.py feedback --pr <P> --rework` lists no item, and the checkpoint's `review_round` is `<k>`.
