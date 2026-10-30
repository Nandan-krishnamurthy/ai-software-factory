---
id: S10
name: Verify acceptance criteria
allowed_from: [S09]
next: S11
---
# S10 Verify acceptance criteria

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation is as in [S00](S00-intake.md) and [S06](S06-pick.md) (`<I>`, `<B>`).

## Purpose
Have every acceptance criterion checked by someone other than the implementer: the **`ac-verifier` subagent** (`.claude/agents/ac-verifier.md`, architecture §4.5). It sees only the criteria, the diff and the test commands, re-runs the tests, and returns `pass`, `fail` or `not-verifiable` for each criterion, with evidence. Its word is not the only proof: first `verify map` maps each criterion to the tests named after it and their results in the run S09 recorded, and `verdict check` holds the verdict against that map. The verdict is stored on the issue, so the PR shows it **unchanged** (rule H5).

## Preconditions
- `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S10`, or `GATE_B_CHANGES_REQUESTED` with `next_station` `S10` (a rework, see [S08](S08-implement.md): the same steps apply). Use `details.issue` as `<I>`, `details.branch` as `<B>` and `increment` as `<INC>`.
- `git -C <T> switch <B>` and `git -C <T> pull --ff-only` succeed, and `git -C <T> status --porcelain` prints nothing.
- `python scripts/factory.py verify check --issue <I>` exits 0: the checkpoint holds S09's evidence for the head of `<B>` on `origin`. Otherwise S09 must run again: record `python scripts/factory.py comment --issue <I> --kind checkpoint --station S10 --next S09 --branch <B>` and stop.
- The `ac-verifier` subagent is available (`.claude/agents/ac-verifier.md` in the factory repo). If it is not, stop: never verify your own work in its place.

## Inputs
- The acceptance criteria from `gh issue view <I> --repo <R> --json body` (the lines `- [ ] AC<n>: …`).
- The diff: `git -C <T> diff origin/<D>...<B>`.
- The test commands: `commands.test` (and `commands.build`, `commands.lint`, `commands.typecheck`) from `.factory/config.json` on `<B>`, and the target path `<T>`.
- The checkpoint's `fix_attempts` (`gh issue view <I> --repo <R> --json comments`) and `limits.max_fix_attempts`.

## Steps
1. **Map the recorded run:** `python scripts/factory.py verify map --issue <I>`. It finds the tests named `#<I> AC<n>` in the branch diff and their results in S09's recorded run, and stores the map in the checkpoint beside the evidence. It runs no tests.
   - Exit 0: go to step 2. An AC shown as `missing` is not an error here: the verdict must then be `not-verifiable` with manual steps, or `verdict check` refuses it.
   - Exit 1 (a mapped test failed): this counts as a failed attempt. Save its output to `<SCRATCH>/map-<I>.md` and go to step 5 with that file in place of the verdict.
   - An `error:` saying that the clone does not have the default branch's head: run `git -C <T> fetch origin`, then run step 1 again. This is not a failed attempt: the factory never fetches by itself (ADR-0006).
   - An `error:`: report it exactly and stop.
2. Start the `ac-verifier` subagent with **only** the inputs above: the acceptance criteria, the diff, the commands and `<T>`. Do not give it your reasoning, your own verdict, the map or the conversation (architecture §4.5).
3. Write its answer, **unchanged**, to `<SCRATCH>/verdict-<I>.md`: one line per criterion (`- [x] AC<n> — pass — evidence: …`, `- [ ] AC<n> — fail — evidence: …`, `- [ ] AC<n> — not-verifiable — manual steps: …`), then its `Suite:` line. Never edit, complete or soften it.
4. Run `python scripts/factory.py verdict check --issue <I> --file <SCRATCH>/verdict-<I>.md`. It checks the verdict's form and holds it against the map: a `pass` needs a mapped test that passed in the recorded run.
   - `INVALID` (a criterion missing, out of order, or without evidence; no `Suite` line; a verdict the map contradicts): start the verifier again once with the same inputs, asking for the exact format. If the second answer is still invalid, stop and ask the human (see Stop conditions). Never fix the verdict yourself.
   - `FAILING` (exit 1): go to step 5.
   - `OK` (exit 0): go to step 6.
5. **If any criterion is `fail`, or `Suite: fail`**: this counts as a failed attempt. Let `k` be the checkpoint's `fix_attempts` plus 1.
   - If `k` ≤ `limits.max_fix_attempts`: record it with `python scripts/factory.py comment --issue <I> --kind checkpoint --station S10 --next S08 --branch <B> --fix-attempts <k> --body-file <SCRATCH>/verdict-<I>.md`, and stop this station. S08 fixes the code, with the verdict as its input, and S09 and S10 run again.
   - Otherwise record it with the same command (so the failing verdict is in the checkpoint note, and the draft PR shows it), then follow **Stuck** in [S09](S09-test.md) (Stop conditions), steps 2–7.
6. `not-verifiable` is allowed only where S09 wrote the reason and manual steps; the PR states it and leaves the box unchecked.
7. Store the verdict. See Checkpoint.

## Outputs
- The AC-to-test map, in the checkpoint note beside the evidence (`verify map`).
- The checkpoint on issue `<I>` (`S10` → `S11`), with the verifier's per-AC verdict as its note.

## Checkpoint
Nothing is committed: the code has not changed since S09. The verdict is kept on GitHub, in the checkpoint comment's note, where the evidence and the map stay:
- `python scripts/factory.py comment --issue <I> --kind checkpoint --station S10 --next S11 --branch <B> --body-file <SCRATCH>/verdict-<I>.md`

## Stop conditions
- The `ac-verifier` subagent is not available: report it and stop. Self-verification is not a substitute.
- The verifier's answer is still `INVALID` after one retry: write the problems `verdict check` printed to `<SCRATCH>/question-<I>.md`, run `python scripts/factory.py comment --issue <I> --kind reply --body-file <SCRATCH>/question-<I>.md` and `gh issue edit <I> --repo <R> --add-label factory:needs-human`, and stop.
- A criterion fails after `limits.max_fix_attempts` attempts: **Stuck**, as in S09.
- `git -C <T> status --porcelain` shows changes that this station did not make.

## Done check
- [ ] `python scripts/factory.py verdict check --issue <I>` (which reads the verdict, the map and the evidence from the checkpoint comment) prints `OK` and exits 0: one line per criterion, each with evidence, nothing failed, and every `pass` backed by the map.
- [ ] `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S11` (in a rework: `GATE_B_CHANGES_REQUESTED` with `next_station` `S11`).
