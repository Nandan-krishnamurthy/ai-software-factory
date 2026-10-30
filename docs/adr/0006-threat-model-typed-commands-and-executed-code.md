# ADR-0006: The threat model: commands the model types, and code the factory runs

| | |
|---|---|
| **Status** | Proposed in [PR #58](https://github.com/Nandan-krishnamurthy/ai-software-factory/pull/58) (PR B: B-46/B-15); accepted when the human merges it |
| **Decided** | 2026-10-30: the plan for F1, from the second adversarial review of PR #56, approved with decisions D1–D4 (`097efb85#1384`, 2026-10-30T05:53:47Z). PR B (E0, E2, E3) authorized in `097efb85#1670` (2026-10-30T06:58:13Z) |
| **Recorded** | 2026-10-30 |
| **Scope** | What the factory's safety layers protect against, and what they do not, before T8.1's runner works unattended between gates |
| **Supersedes** | [ADR-0005](0005-approved-config-from-github.md) decision 5's fetch ("if the clone does not have it, they fetch it by its SHA"), and the sentence of its decision 3 about that fetch. The rest of ADR-0005 stands |

## Context

The factory's first rule is that it never merges: the human merges, and the merge is the approval (D1, D5). Today that rests on the factory's own layers ([02-factory-architecture.md](../02-factory-architecture.md) §8):
- the station rules;
- the permission deny list;
- the guard hook, which vets every command the model types through Claude Code's Bash, PowerShell, Edit and Write tools.

In single-account mode (§9.3), GitHub cannot stop a merge made with the human's own credentials.

The adversarial reviews of PR #56 showed that the guard sees only half of what runs:
- **Settings typed commands can make:** a typed command can change settings that make a later command start a program. `git config core.sshCommand`, `core.hooksPath`, `include.path`, `filter.<x>.clean` and `core.fsmonitor` are all allowed today, and so are writes to `.git/hooks/` and `.git/config` ([B-46](../backlog.md#b-46)).
- **Code the model writes:** code the factory then runs is never seen by the guard at all. That covers test code in `verify run` (which inherits the whole environment, [B-15](../backlog.md#b-15)), hooks committed in the repository (such as husky), and package scripts ([B-11](../backlog.md#b-11)). It runs as the user, with the user's GitHub access.

T8.1's acceptance criterion "the runner can't merge (the guard is still active)" therefore needs a precise statement of what it covers.

## Decision

1. **Two kinds of risk, named separately.**
   - **A. Commands the model types.** The guard vets them. Its gaps, including settings that make git start a program and writes into `.git/` and `.factory-local/`, are closed by E1 ([B-46](../backlog.md#b-46), PR C).
   - **B. Code the model writes, which the factory runs.** No guard can vet it. It is narrowed by E3 (a cleaned environment for `verify run`), and closed only by a separate identity that cannot merge, plus a sandbox ([B-49](../backlog.md#b-49)).
2. **What "the runner can't merge" guarantees.**
   - **Covered:**
     - **every command the model types**, through the guard, once E1 is done;
     - **every git call the factory makes itself** (`Git`): no hook and no fsmonitor command runs there, because `core.hooksPath` points at a path that cannot exist and `core.fsmonitor` is off, as command-line config that outranks the repository's (E2). And the factory makes no network git call in the evidence path: `local_commit` no longer fetches, and a missing commit stops with "run `git fetch origin`" (D2).
   - **Not covered** until [B-49](../backlog.md#b-49): **model-written code that deliberately tries to merge.** Such code runs as the user and can reach the user's credential store.
3. **E3 is a speed bump, not isolation.** `verify run` gives every approved command `evidence.verification_env`:
   - no GitHub token or authentication helper;
   - no variable named like a secret;
   - no inherited command-line git config;
   - an empty `gh` config folder, an empty global git config, and no system git config;
   - no prompts.

   Neither `gh` nor git's credential helper is logged in for the commands. But code running as the user can still:
   - read the operating system's credential store (such as Windows Credential Manager);
   - read files in the user's home, such as `~/.ssh` and `~/.git-credentials`;
   - start `gh` or git with its own settings.

   E3 stops accidental or casual use of the credentials, not a deliberate attempt.
4. **When unattended running is allowed** (D3).
   - **After E0–E3, sandbox demonstrations only.** Controlled demonstrations on sandbox targets may run, with these limits documented in the demo record.
   - **Before unattended runs on real projects:** [B-49](../backlog.md#b-49), the separate bot identity without merge permission, is required.
5. **Hooks** (D1, option (b)).
   - **Already done:** the factory's own git calls run no hook (E2).
   - **E1 (PR C) will:**
     - block changes to the hook configuration;
     - make `doctor` report active hooks;
     - require hooks to be disabled on the git commands the model types that run them.
   - **What stays uncovered:** git that model-written code runs by itself during verification.

## Consequences

- `verify run`'s commands keep everything they had before except the user's credentials. A project's build or test that itself needs a token (a private registry, a cloud API) now fails under `verify run`. Its config must be changed, or the decision revisited.
- `verify map` and `pr render` stop with a fetch instruction when the clone lacks GitHub's head of the default branch. S10 tells the station to fetch and run the step again (it is not a failed attempt). S11 and S12 already fetch.
- `gh.run_command_line` requires an environment, so no configured command inherits the factory's whole environment by accident.
- The factory's own git calls ignore the repository's hooks and fsmonitor setting. A project that relies on hooks keeps them for the human's own commits. The factory's `ensure.ensure_branch` (`fetch`, `switch`, `pull`) runs none of them.

## Evidence

- Code: `git.with_config`, `git.SAFE_CONFIG` and `Git._env` in `scripts/factory/git.py`; `evidence.verification_env`, `evidence.local_commit` and `run_verification` in `scripts/factory/evidence.py`; `gh.run_command_line` in `scripts/factory/gh.py`; S10 step 1.
- **Tests,** `tests/test_factory_git_env.py`, with real git:
  - **Control:** hooks (`post-checkout`, `post-merge`, `reference-transaction`) and an fsmonitor script run for plain git during `status`, `diff`, `switch`, `fetch` and `pull`.
  - **The factory:** none of them runs for the same calls through `Git`, nor for `ensure.ensure_branch`.
  - **Inherited config:** `GIT_CONFIG_COUNT` entries are kept, and still outrank the repository's.
- **Tests,** `tests/test_verification_env.py`:
  - the cleaned environment, including lower-case names and inherited overrides;
  - every command of a `verify run` gets it;
  - live on a machine where `gh` is logged in and git has a credential helper: inside the cleaned environment, `gh auth status` reports not logged in, no helper is configured, no global or system config is read, and `git credential fill` produces no credential.
- **`tests/test_config_source.py`:** a missing commit stops with the fetch instruction, and no fetch is attempted even when one would work.
- The mutation results are in [task-log.md](../task-log.md).

## Not decided here

- The bot identity, the GitHub rule that keeps it from merging, and the sandbox: [B-49](../backlog.md#b-49). These need the human to sequence them, and possibly a paid GitHub plan for branch protection on private repositories.
- The guard work for risk A: E1 and T1 ([B-46](../backlog.md#b-46), PR C).
