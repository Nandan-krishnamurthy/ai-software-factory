---
id: S10
name: Verify acceptance criteria
allowed_from: [S09]
next: S11
---
# S10 Verify acceptance criteria

Read [`stations/_rules.md`](_rules.md) before anything else. Where this file and the rules disagree, the rules win. Notation is as in [S00](S00-intake.md) and [S06](S06-pick.md) (`<I>`, `<B>`).

## Purpose
Have every acceptance criterion checked by someone other than the implementer: the **`ac-verifier` subagent** (`.claude/agents/ac-verifier.md`, architecture §4.5). It sees only the criteria, the diff and the test commands, re-runs the tests, and returns `pass`, `fail` or `not-verifiable` for each criterion, with evidence. Its verdict is stored on the issue, so S11 can copy it into the PR **unchanged** (rule H5).

## Preconditions
- `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S10`. Use `details.issue` as `<I>`, `details.branch` as `<B>` and `increment` as `<INC>`.
- `git -C <T> switch <B>` and `git -C <T> pull --ff-only` succeed, and `git -C <T> status --porcelain` prints nothing.
- The `ac-verifier` subagent is available (`.claude/agents/ac-verifier.md` in the factory repo). If it is not, stop: never verify your own work in its place.

## Inputs
- The acceptance criteria from `gh issue view <I> --repo <R> --json body` (the lines `- [ ] AC<n>: …`).
- The diff: `git -C <T> diff origin/<D>...<B>`.
- The test commands: `commands.test` (and `commands.build`, `commands.lint`, `commands.typecheck`) from `.factory/config.json`, and the target path `<T>`.
- The checkpoint's `fix_attempts` (`gh issue view <I> --repo <R> --json comments`) and `limits.max_fix_attempts`.

## Steps
1. Start the `ac-verifier` subagent with **only** the inputs above: the acceptance criteria, the diff, the commands and `<T>`. Do not give it your reasoning, your own verdict or the conversation (architecture §4.5).
2. Check that its answer has one line per acceptance criterion, in order, each with a verdict and concrete evidence: a test name that passed, a command and its output, or manual steps. A verdict without evidence is not accepted; ask the verifier again once, and otherwise treat that criterion as `not-verifiable`.
3. Write its answer, **unchanged**, to `<SCRATCH>/verdict-<I>.md`, one line per criterion in the PR form: `- [x] AC<n> — pass — evidence: …` for `pass`; `- [ ] AC<n> — fail — evidence: …` or `- [ ] AC<n> — not-verifiable — …` otherwise.
4. **If any criterion is `fail`**, or the verifier reports a test failure: this counts as a failed attempt. Let `k` be the checkpoint's `fix_attempts` plus 1.
   - If `k` ≤ `limits.max_fix_attempts`: record it with `python scripts/factory.py comment --issue <I> --kind checkpoint --station S10 --next S08 --branch <B> --fix-attempts <k> --body-file <SCRATCH>/verdict-<I>.md`, and stop this station. S08 fixes the code, with the verdict as its input, and S09 and S10 run again.
   - Otherwise follow **Stuck** in [S09](S09-test.md) (Stop conditions), including the verdict in the draft PR.
5. `not-verifiable` is allowed only where S09 wrote the reason and manual steps; the PR states it and leaves the box unchecked.
6. Store the verdict. See Checkpoint.

## Outputs
- The checkpoint on issue `<I>` (`S10` → `S11`), with the verifier's per-AC verdict as its note.

## Checkpoint
Nothing is committed: the code has not changed since S09. The verdict is kept on GitHub, in the checkpoint comment's note:
- `python scripts/factory.py comment --issue <I> --kind checkpoint --station S10 --next S11 --branch <B> --body-file <SCRATCH>/verdict-<I>.md`

## Stop conditions
- The `ac-verifier` subagent is not available: report it and stop. Self-verification is not a substitute.
- A criterion fails after `limits.max_fix_attempts` attempts: **Stuck**, as in S09.
- `git -C <T> status --porcelain` shows changes that this station did not make.

## Done check
- [ ] The checkpoint comment on issue `<I>` (`gh issue view <I> --repo <R> --json comments`) contains one verdict line per acceptance criterion, each with evidence.
- [ ] No criterion is `fail`.
- [ ] `python scripts/factory.py state --json` reports `STORY_IN_PROGRESS` with `next_station` `S11`.
