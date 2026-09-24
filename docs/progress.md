# Factory build progress

Milestone demo records, as required by the milestone Definition of Done in [03-factory-plan.md](03-factory-plan.md) §3: *"all tasks in the milestone are merged, **and** the milestone demo … has been run and its result recorded in `docs/progress.md`."*

---

## M1: State engine and safety core

| | |
|---|---|
| **Demo run** | 2026-09-24 |
| **Target** | `Nandan-krishnamurthy/factory-sandbox` (empty, disposable; prerequisite P2), cloned into the session scratch directory |
| **Factory code** | branch `task/T1.8-state-planning` (PR #10), which contains T0.1–T1.7 (merged) plus T1.8 |
| **Result** | ✅ **All demo steps passed.** One small issue was found and fixed (below). |

### Tasks
| Task | PR | Status |
|---|---|---|
| T0.1 Initialise the factory repo | (direct initial commit) | merged |
| T0.2 Python skeleton and test runner | #1 | merged |
| T0.3 `CLAUDE.md` and `_rules.md` | #2 | merged |
| T1.1 `gh.py`/`git.py` I/O layer + FakeGh | #3 | merged |
| T1.2 Config and target handling | #4 | merged |
| T1.3 Markers module | #5 | merged |
| T1.4 `doctor`, `labels ensure` | #6 | merged |
| T1.5 `comment` subcommand | #7 | merged |
| T1.6 Guard hook and settings.json | #8 | merged |
| T1.7 `signals.py` (single-account) | #9 | merged |
| T1.8 State reconciler, planning states | #10 | merged. **M1 is complete.** |

### Demo steps and results (plan §M1)

**1. `target set` → `doctor` → `labels ensure` → `state`**

| Command | Result |
|---|---|
| `factory.py target set <scratch>/sandbox` | ✅ `Target: …\scratchpad\sandbox (Nandan-krishnamurthy/factory-sandbox)`. It wrote `.factory-local/target.json` and `permissions.additionalDirectories`, and Claude Code picked up the added directory straight away. |
| `factory.py doctor` | ✅ `Doctor PASSED: 0 failed, 2 warning(s).` The two warnings are expected for an empty, unconfigured repo: `config` (no `.factory/config.json` yet) and `branch protection` (repo is empty). |
| `factory.py labels ensure` | ✅ `Labels: 0 created, 0 updated, 9 unchanged.` Idempotent; the labels had been created by the T1.4 integration run. |
| `factory.py state` | ✅ **`State: UNCONFIGURED`**, waiting on human, allowed `/factory-start, /factory-status`, "No increment has been started. Run /factory-start." |
| `factory.py state --json` (stdout only) | ✅ Pure JSON, `"state": "UNCONFIGURED"`, schema 1; the banner went to stderr. |

**2. Post a factory comment and a checkpoint** (on throwaway sandbox issue #2)

| Command | Result |
|---|---|
| `factory.py comment --issue 2 --kind reply --body-file -` | ✅ Comment created, stored by GitHub as `<!-- factory:reply -->` followed by the text. |
| `factory.py comment --issue 2 --kind checkpoint --station S08 --next S09` (no `--sha`) | ✅ Refused with `error: the target has no commits; pass --sha` (the sandbox has no commits yet). *This is where the ordering issue below was found.* |
| Checkpoint `S08→S09`, then `S09→S10`, with `--branch story/0-m1-demo --sha 0000000` | ✅ `created checkpoint comment`, then `updated checkpoint comment`, **same comment id**. The issue ends with exactly 2 comments (1 reply + 1 checkpoint), both marked. |

**3. Attempt a merge and a push to `main`; the guard must block both**

Each attempt was deliberately written so that it does **not** match a `permissions.deny` rule, leaving the guard as the only thing that could stop it. The merge targeted a PR number that doesn't exist (#999), so nothing could have been merged even if the guard had failed.

| Attempted tool call | Result |
|---|---|
| `cd <sandbox> && gh pr merge 999 --repo Nandan-krishnamurthy/factory-sandbox --squash` | ✅ **Blocked by the live hook:** `Blocked by the factory guard: \`gh pr merge\` is not allowed: the human merges (D1, rule S1)` |
| `git -C <sandbox> push origin HEAD:main` (pre-approved by the `git -C` allow rule) | ✅ **Blocked by the live hook:** `Blocked by the factory guard: the factory must never push to the default branch 'main'; changes reach it only when the human merges a PR (rules S1, D1)` |
| *(extra)* `Write docs/progress.md` in the factory repo while the target was active | ✅ **Blocked:** `the factory repo is read-only while a target is active (rule S3, D4)`. This record was therefore written after the target was deactivated. |

### Issue found and fixed
- **The `Target:` banner could print *after* an error message.** When stdout is a pipe it is buffered, but stderr isn't, so in step 2 the `error:` line appeared before the banner. Rule T2 says the banner comes first.
- **Fix (PR #10):** `cli.py` flushes the banner immediately.
- **Regression test:** `BannerOrderTest` runs the real CLI with stdout piped and stderr merged into it. It **fails without the fix**, reproducing the demo output exactly, and passes with it.

### Cleanup
- Sandbox issue #2 closed. The 9 factory labels stay on the sandbox (intended).
- The target was deactivated: the gitignored `.factory-local/target.json` and `.claude/settings.local.json` were removed (neither existed before the demo), and `factory.py target show` now reports no active target.
- Nothing was merged and nothing was pushed to `main` in any repo.

### Observations for later tasks
- In an empty target, `comment --kind checkpoint` can't default `--sha` (there is no HEAD), and `--branch` defaults to `main`. Real checkpoints run after S07 has created and pushed a story branch, so this only affects empty repos, but the S07+ stations (T3.3) should always pass `--branch` explicitly.
