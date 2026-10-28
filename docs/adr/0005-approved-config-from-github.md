# ADR-0005: The approved config is read from GitHub, never from the clone's local refs

| | |
|---|---|
| **Status** | Proposed in the B-28 PR; accepted when the human merges it |
| **Decided** | 2026-10-23: B-28 is due before T8.1 ([backlog.md](../backlog.md#b-28)). 2026-10-28: B-28 runs as a standalone hardening task before T8.1 (`097efb85#173`, 2026-10-28T10:52:41Z). The design below is proposed in the PR and decided by its merge |
| **Recorded** | 2026-10-28 |
| **Scope** | Where `verify run`, `verify check`, `verify map`, `verdict check`, `pr render` and `pr check` find the approved `.factory/config.json`, and the default-branch commit their diffs are taken against |
| **Supersedes** | Where [ADR-0004](0004-configured-commands-bash-approved-only.md) decision 2 reads the default branch from (`origin/HEAD`). The rest of ADR-0004 stands |

## Context

ADR-0004 made "approved" mean the config on the default branch on `origin`, which only a PR the human merged changes. The code found that branch through the clone's **local** refs ([B-28](../backlog.md#b-28)):
- `default_ref` read the symbolic ref `origin/HEAD`;
- `approved_config` read the config at the remote-tracking ref it named (`origin/main`).

Anything that can run git in the target can repoint those refs: the model through Bash, since the guard allows `remote set-head`, `symbolic-ref`, `update-ref` and `remote set-url`, and the project's own test code, which `verify run` runs with bash outside the guard. After one of these commands, the story branch's own config is read as approved. Its commands run and pass, its `test_reports` are trusted, and the diff base, `max_diff_lines` and `ci.required` are the branch's own. A fix in the guard alone cannot close this, because the test code does not go through the guard.

Probing while designing the fix found two more local mechanisms with the same effect (git 2.52, 2026-10-28): a **replace ref** (`git replace`) makes one commit read as another, contents and parents both, and a **graft file** (`.git/info/grafts`) changes a commit's parents. Either can make the default branch's commit show the story's config, or move a merge base so that a diff hides part of the change.

## Decision

1. **GitHub is the source of truth.** The default branch's name, its head commit and `.factory/config.json` at that commit are what the GitHub API reports for the repository that `/factory-target` recorded (`target.json`): `repos/<R>`, `repos/<R>/git/ref/heads/<D>` and `repos/<R>/contents/.factory/config.json?ref=<SHA>`. No local ref is read for any of them.
2. **The config must agree with GitHub.** Its `repo` must be the recorded repository, and its `default_branch` must be the branch GitHub names.
3. **`origin` must still name the recorded repository.** `ls-remote` (the story branch's head) and `fetch` use it, so the clone's `origin` URL, with any `insteadOf` rewrite as git applies it, must be the same GitHub repository.
4. **The evidence records the commit, and every consumer checks it.** `config_source` is `<branch>@<full SHA>`. `verify check`, `verify map`, `verdict check`, `pr render` and `pr check` reject evidence whose source is not a commit of GitHub's default branch: it must be the head, or an ancestor of the head according to GitHub's compare API.
5. **Diffs use GitHub's head, by SHA.** `verify map` and `pr render` diff against the head commit GitHub reports. If the clone does not have it, they fetch it by its SHA; git checks a fetched object against its name, so a fetch can only give that commit or nothing.
6. **The factory's git ignores replace refs and grafts.** Every git call the factory makes runs with `GIT_NO_REPLACE_OBJECTS=1` and `GIT_GRAFT_FILE` set to a path that cannot exist.
7. **Fail closed.** If GitHub cannot be reached or gives a malformed answer, if the config is missing or invalid, if a name does not match, if the origin is another repository, or if the commit cannot be fetched, then nothing runs and no evidence is accepted. The reason is stated.

## Consequences

- `verify run` and the checks need GitHub, which every station already uses for the checkpoint. Each command makes three more API calls, plus one comparison when the default branch has moved on.
- Evidence recorded before this change names a local ref (`origin/main@abc1234`). It is rejected with "run `verify run` again". No story was in progress when this was written: Task Tracker was at `INCREMENT_COMPLETE`, and both M7 sandboxes were at Gate A.
- Repointing `origin/HEAD` or `origin/main` changes nothing the factory trusts. The guard is not changed. Blocking those commands remains optional defence in depth and is left to T9.5 ([B-45](../backlog.md#b-45)).
- The approval still rests on the default branch changing only through merged PRs. The default branch has no branch protection yet ([B-24](../backlog.md#b-24), T9.6).

## Evidence

- Code: `approved_config`, `check_origin`, `local_commit`, `source_problems` and `check_trusted` in `scripts/factory/evidence.py`; `Git._env` in `scripts/factory/git.py`; the consumers in `scripts/factory/cli.py` and `scripts/factory/prbody.py`.
- Tests: `tests/test_config_source.py`. With real git on a throwaway clone it covers `update-ref`, `remote set-head`, `symbolic-ref`, a forged `origin/main` that is not on the remote, `git replace`, grafts (the graft file and `replace --graft`), `remote set-url`, `remote.origin.url` and `insteadOf`. With fakes it covers each GitHub failure and each malformed answer, and the rejection of a forged source by every consumer. A static test checks that no factory module reads `origin/HEAD`, `origin/main` or `refs/remotes`.
- Before the change, the replace-ref and graft tests failed on their assertions, and the other new tests could not run because `run_verification` took no GitHub source.

## Not decided here

- Whether the guard should also block rewriting `refs/remotes/origin/*` and `remote set-head` in the target: that is B-28's optional criterion 6, left to T9.5 ([B-45](../backlog.md#b-45)).
- Objects already in the clone are not re-hashed when read, so someone who can rewrite `.git/objects` (or the commit-graph file) can still change what a local diff shows. The approved config itself is read from GitHub and is not affected ([B-45](../backlog.md#b-45)).
