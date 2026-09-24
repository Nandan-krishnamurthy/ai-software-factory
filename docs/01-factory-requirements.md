# 01 — AI Software Factory: MVP Requirements

| | |
|---|---|
| **Status** | Draft v3, with decisions D1–D5 applied |
| **Date** | 2026-09-24 |
| **Scope** | MVP of a reusable factory. Nothing is built yet. |
| **First test project** | Task Tracker (used to test the factory; it is not part of the factory) |

---

## 1. Purpose and problem

### Problem
When an AI agent is asked to "build the app", it tends to:
- produce large, unreviewable changes all at once,
- lose track of which requirement a piece of code satisfies,
- skip or fake tests,
- forget what it was doing when the session ends or hits a usage limit,
- act without a human checkpoint.

### Purpose
The factory is a **repeatable, human-gated workflow** that turns requirements into merged code **one small story at a time**, using normal engineering artifacts (GitHub Issues, branches, Pull Requests, tests).

The MVP needs to prove one thing: **an AI agent can reliably take a project from requirements to merged, tested code, one reviewed PR at a time, and pick up where it left off after an interruption.**

### Design principles
1. **Small steps.** One story → one branch → one PR.
2. **GitHub is the source of truth.** Anything needed to resume is stored in GitHub or committed to the repo, never only in the agent's memory.
3. **Humans hold the gates.** The factory proposes; a human approves.
4. **Traceable.** Every line of work can be traced back to a requirement.
5. **Reusable.** Nothing is specific to Task Tracker. Project-specific facts go in project config and docs.
6. **Boring tools.** `git`, `gh` CLI, the project's own test runner, and Claude Code.

### Confirmed decisions
| # | Decision |
|---|---|
| D1 | **The human merges.** After reviewing and approving a PR, the human merges it manually. The factory never merges. |
| D2 | **Explicit "continue".** After a merge, the factory waits until the human says `continue` before it starts the next story. |
| D3 | **Packaging.** The MVP is built as Claude Code skills/slash commands. Station logic is kept separate from how it is invoked, so headless automation (e.g. `claude -p`, scheduled runs, GitHub Actions) can be added later without rewriting the stations. |
| D4 | **Separate repositories.** The factory lives in its own repository (this one). It operates against a separate target repository, given as a local path. Target repos never contain factory code, only the factory's per-project config, planning docs and state (Appendix A). |
| D5 | **Single GitHub account; merge = approval.** For the MVP the factory uses the human's own GitHub login. GitHub does not let an author approve their own PR, so **the human's manual merge is the approval gate**. The human requests changes with a PR comment starting with `/changes`. The factory never merges automatically. The design must allow a separate bot account later, so that GitHub's real *Approve* / *Request changes* reviews can be used without redesigning the factory. |

---

## 2. Workflows

The factory has two entry points that meet at a shared **Story Loop**.

```
 NEW PROJECT                         EXISTING PROJECT
 PRD                                 Repo + new requirements
  │                                   │
  │                                   ▼
  │                          S1 Codebase Discovery
  │                                   │
  └──────────────┬────────────────────┘
                 ▼
        S2 Requirements
                 ▼
        S3 Architecture
                 ▼
        S4 Implementation Plan
                 ▼
        S5 Story Breakdown (draft) ──► Planning PR
                 ▼
     ══ GATE A: Human approves + merges Planning PR ══
                 ▼
        S5b Create GitHub Issues
                 ▼
   ┌─────────── STORY LOOP ───────────────────────────┐
   │  S6 Pick ONE unblocked story                     │
   │  S7 Create branch                                │
   │  S8 Implement                                    │
   │  S9 Write / run tests                            │
   │  S10 Verify acceptance criteria                  │
   │  S11 Create Pull Request                         │
   │  ══ GATE B: STOP — human reviews PR ══           │
   │      ├─ changes requested → back to S8           │
   │      └─ approved → HUMAN merges (factory waits)  │
   │  S12 Detect merge + close out story              │
   │  ══ GATE C: STOP — wait for human "continue" ══  │
   │      └─ "continue" → back to S6                  │
   └──────────────────────────────────────────────────┘
```

The factory runs from **this repository** and acts on a **separate target repository** (D4). Every path such as `docs/factory/…` or `.factory/…` in this document refers to the target repo unless it says otherwise.

### 2.1 New-project workflow (from a PRD)
1. The human puts the PRD in `docs/factory/00-prd.md` of the target repo. The repo may be empty apart from this file.
2. The factory runs S2 → S5 and produces requirements, architecture, a plan, and a story list.
3. The first story is always a **walking skeleton**: project scaffold, test runner, a single passing test, and CI if it is in scope.
4. **Gate A:** the planning docs are opened as a **Planning PR**. The human reviews it, approves and merges it. Issues are created in GitHub only after that merge.
5. The Story Loop runs.

### 2.2 Existing-project workflow (repo + new requirements)
1. The human points the factory at a local clone of an existing repo and puts the new requirements in `docs/factory/00-prd.md`. This can be a change request instead of a full PRD.
2. **S1 Codebase Discovery** runs first. It records the stack, structure, conventions, build/test commands, the current test status, and risky areas.
3. **The baseline must be green.** If the existing tests fail, the factory stops and reports it. The factory will not build on a broken baseline without explicit human approval.
4. S2 → S5 run the same way as for a new project. Requirements and architecture describe the **change** (delta), not the whole system. Stories must follow the existing conventions.
5. Gate A, then the Story Loop.

---

## 3. Factory stations

Each station is a discrete, re-runnable step. Every station writes its output to a known place so that a later session can see it has already run.

Planning artifacts live in the **target repo** under `docs/factory/`. The factory never pushes to the target's default branch, so S0–S5 are committed on a branch named `factory/plan` and reach `main` through the Planning PR (Gate A).

Each station is exposed as a Claude Code slash command (D3), for example `/factory-plan`, `/factory-next`, `/factory-resume` and `/factory-status`. Section 3 defines what the stations do. Command names and packaging are decided in the architecture document.

| # | Station | Inputs | Outputs | Done when |
|---|---|---|---|---|
| S0 | **Intake / Setup** | Target repo path, PRD/requirements, project config | `.factory/config.json`, `docs/factory/00-prd.md`, GitHub labels created, `factory/plan` branch | Config valid; `gh` authenticated; labels exist |
| S1 | **Codebase Discovery** *(existing only)* | Existing repo | `docs/factory/01-codebase-analysis.md` (stack, layout, conventions, build/test/lint commands, baseline test result, hotspots) | Doc exists; baseline test status recorded |
| S2 | **Requirements** | PRD, codebase analysis | `docs/factory/02-requirements.md` with numbered `REQ-###` items (functional + non-functional), assumptions, out-of-scope | Every PRD statement maps to a REQ or to out-of-scope |
| S3 | **Architecture** | Requirements, codebase analysis | `docs/factory/03-architecture.md` (components, data model, key decisions with rationale, tech choices) | Every REQ has a home in the design |
| S4 | **Implementation Plan** | Requirements, architecture | `docs/factory/04-implementation-plan.md` (ordered milestones, dependency graph, testing approach) | Plan covers all in-scope REQs |
| S5 | **Story Breakdown** | Plan | `docs/factory/05-stories.md` (draft stories following §4), initial `docs/factory/traceability.md`, Planning PR opened | Each story meets the Story Contract; all REQs covered |
| — | **Gate A** | Planning PR | Human approves **and merges** the Planning PR | Planning PR merged |
| S5b | **Create Issues** | Merged `05-stories.md` | One GitHub Issue per story, labelled per §4 | Every story has exactly one issue |
| S6 | **Pick Story** | Open issues + labels | Selected issue labelled `status:in-progress` and assigned | Exactly one story in progress |
| S7 | **Branch** | Selected issue | Branch `story/<issue#>-<slug>` from the latest default branch | Branch exists and is pushed |
| S8 | **Implement** | Story, architecture, codebase | Commits on the story branch | Code compiles/lints |
| S9 | **Test** | Story acceptance criteria | New or updated tests; full test-suite result | All tests pass locally |
| S10 | **Verify AC** | Story ACs, test results | AC checklist with evidence for each AC (test name, command output, or screenshot) | Every AC is marked pass with evidence |
| S11 | **Create PR** | Branch, AC evidence | `docs/factory/traceability.md` row updated in the same PR; GitHub PR that follows §6; issue labelled `status:in-review` | PR open; CI (if any) green |
| — | **Gate B** | PR | Human reviews. To request changes: comment `/changes` (D5). To approve: **merge the PR manually** (D1, D5). | PR merged by a human |
| S12 | **Close-out** | Merged PR (detected, not performed) | Issue `status:done` (it auto-closes via `Closes #`); local `main` updated; summary comment listing newly unblocked stories | Merge confirmed on GitHub |
| — | **Gate C** | Close-out summary | Human says `continue` (D2) | Explicit instruction received |

**Rework path:** when changes are requested at Gate B, the factory reads every review comment, goes back to S8 on the **same branch**, pushes new commits, replies to each comment with what changed, and asks for review again. It does not open a new PR.

---

## 4. Story / Issue contract

Every story is a GitHub Issue with this structure. S5 must reject (split or rewrite) any story that does not fit it.

```markdown
## Story
As a <user>, I want <capability> so that <benefit>.

## Traces to
REQ-003, REQ-007

## Acceptance criteria
- [ ] AC1: Given <context>, when <action>, then <result>.
- [ ] AC2: ...

## Out of scope
- ...

## Dependencies
Blocked by: #12, #14   (or "None")

## Technical notes
Likely files/areas touched; relevant architecture decisions.

## Test plan
- Unit: ...
- Integration/E2E: ...

## Definition of done
- [ ] All ACs verified with evidence
- [ ] Tests added and full suite passing
- [ ] No lint/type errors
- [ ] Docs updated if behaviour changed
```

**Sizing rules**
- A story should produce a PR that a human can review in about 15 minutes. Target: **< ~400 changed lines**, excluding generated files.
- 1–5 acceptance criteria. More than that means the story should be split.
- A story must be independently testable and leave the default branch in a working state.

**Labels**
| Label | Meaning |
|---|---|
| `factory:story` | Issue managed by the factory |
| `status:ready` | Approved; can be picked once its dependencies are done |
| `status:blocked` | Has open dependencies or is waiting on a human answer |
| `status:in-progress` | Currently being implemented (acts as a lock) |
| `status:in-review` | PR open, waiting at Gate B |
| `status:changes-requested` | Human requested changes |
| `status:done` | PR merged by the human; close-out complete |

**"Unblocked"** means: labelled `status:ready`, and every issue listed under "Blocked by" is closed. When more than one story is unblocked, the factory picks the lowest milestone first, then the lowest issue number.

---

## 5. Branching strategy

- **Default branch** (`main`) is protected. The factory never commits or pushes to it directly.
- **One branch per story:** `story/<issue#>-<short-slug>`, e.g. `story/14-add-task-due-date`.
- Branches are cut from the **latest** `main`. Before opening the PR, the factory rebases (or merges `main` in) and re-runs the tests.
- Commit messages reference the issue: `feat: add due date field (#14)`.
- No force-push after the PR has been reviewed. Before review, force-pushing to the factory's own story branch is allowed.
- After the human merges, GitHub deletes the remote branch automatically (§9 repo setting). At S12 the factory deletes its local copy.
- **Planning branch:** `factory/plan` holds S0–S5 output and is merged through the Planning PR. If planning docs need a later revision, it is done on `factory/plan-<n>` through a new PR.
- **One story in progress at a time** in the MVP. This avoids conflicts and keeps review simple.

---

## 6. Pull Request workflow

**Title:** `[#<issue>] <story title>`

**Body template:**
```markdown
Closes #<issue>

## Summary
What changed and why, in 2–5 bullets.

## Traceability
Requirements: REQ-003, REQ-007
Story: #<issue>

## Acceptance criteria verification
- [x] AC1 — evidence: `tests/tasks.test.ts › sets due date` passes
- [x] AC2 — evidence: ...

## Tests
- Added: ...
- Full suite: `<command>` → N passed, 0 failed

## Risks / notes for reviewer
- ...

## Out of scope / follow-ups
- ...
```

**Rules**
- The PR is opened as **ready for review** only after S9 and S10 pass. If the factory is stuck, it opens a **draft** PR and explains the problem.
- The factory writes the AC evidence itself. The human reviewer checks that evidence; they do not have to reconstruct it.
- If any step failed, the factory says so clearly in the PR. It must never claim a test passed when it did not run.

---

## 7. Human approval gates

The MVP has three mandatory gates. At each one the factory **stops and ends its turn**. It does not poll or wait in a loop; the human restarts it with a command.

| Gate | When | Human action | Factory behaviour |
|---|---|---|---|
| **A — Plan approval** | After S5, before any issue is created or any code is written | Review the Planning PR. Comment `/changes`, or approve by **merging** it (D5) | Stops. On requested changes, revises the docs on `factory/plan` and asks again. Once the PR is merged, the next run starts at S5b. |
| **B — PR review** | After S11, for every story | Comment `/changes`, or approve by **merging** (D5) | Stops. On `/changes`, the next run goes back to S8 rework. Closing the PR without merging marks the story as needing a human decision. The factory never merges (D1). |
| **C — Continue** | After S12 close-out | Say `continue` (e.g. run `/factory-next`) | Stops and shows which stories are now unblocked. Does not pick a new story until told to (D2). |

**Other stop conditions.** The factory stops and asks when:
- a requirement is ambiguous or conflicts with another,
- the baseline tests are red,
- a story turns out much larger than estimated (it should be split),
- it needs a new external dependency, credentials, paid service, or infrastructure change,
- tests still fail after a bounded number of fix attempts (e.g. 3).

**Merge authority.** Only the human merges, for both the Planning PR and story PRs (D1). The factory never runs `gh pr merge` or pushes to the default branch.

**Continue authority.** Running `/factory-resume` never starts a new story by itself. It finishes the station already in progress, or reports which gate it is waiting at. Only an explicit `continue` moves past Gate C (D2).

---

## 8. Resume and recovery

A Claude session can end at any point (usage limit, crash, closed terminal). The factory must be able to continue from that point without redoing or duplicating work.

### 8.1 Where state lives
| State | Location |
|---|---|
| Which planning stations are done | Presence of `docs/factory/0X-*.md` files on `factory/plan` (pushed) |
| Gate A approval | Planning PR merged |
| Gate C (continue) | Not stored. Absence of any `in-progress`/`in-review` story means "idle, waiting for continue" |
| Story status | Issue labels (§4) |
| Current work in progress | Story branch (pushed) + a checkpoint comment on the issue |
| PR / review status | GitHub PR state and reviews |
| Run log | `.factory/log.md` (append-only, committed on the story branch) |

**Nothing needed for resume may exist only in the conversation context.**

### 8.2 Checkpointing
At the end of each station inside the Story Loop, the factory:
1. commits and **pushes** its work,
2. posts or updates one checkpoint comment on the issue:
   `Factory checkpoint: S9 Test complete. Next: S10. Branch: story/14-... @ <sha>`.

### 8.3 Resume procedure (`/factory-resume`)
1. Read `.factory/config.json` from the target repo path.
2. Reconcile against GitHub, checking in this order:
   - Planning PR not yet merged? → Continue from the first missing `docs/factory/` artifact, or report "waiting at Gate A".
   - Planning merged but issues missing? → S5b.
   - Is a story `status:in-review`? → Check the PR:
     - **Merged** → run S12 close-out, then stop at Gate C.
     - **Changes requested** → S8 rework.
     - **Closed without merge** → report "story rejected" and stop for a human decision.
     - *(Future bot mode only: **Approved, not merged** → report "approved, waiting for you to merge" and stop.)*
     - **No review yet** → report "waiting for review" and stop.
   - Is a story `status:in-progress`? → Check out its branch, read the last checkpoint, and continue from the next station.
   - Otherwise → report "idle at Gate C, say `continue` to start the next story" and stop. **Do not pick a story.**
3. Before doing anything, print a short "here is where I am" summary.

### 8.4 Idempotency rules
- Before creating an issue, branch, or PR, the factory checks whether one already exists and reuses it.
- Issue creation is keyed by story ID (e.g. `STORY-007` in the issue body), so a re-run does not create duplicates.
- Uncommitted local changes found on resume are reported to the human. They are not silently discarded.

---

## 9. GitHub integration

- **Tooling:** `git` + `gh` CLI, authenticated as a user or bot with repo scope. No custom GitHub App in the MVP.
- **Target repo:** a local clone at a path given to the factory, with a GitHub remote. The factory runs `git`/`gh` inside that path. Its own repo is never modified during a run.
- **Used for:** labels, issues (create, label, comment), branches, PRs (create, comment, read reviews and merge state), and reading CI status checks. **Not used for merging.**
- **Recommended repo settings** (the human sets these up; the factory checks and warns):
  - Branch protection on `main`: PR required, 1 approving review, status checks required (if CI exists).
  - Squash merge enabled; automatically delete head branches.
- **Tracking issue (optional):** one pinned issue, "🏭 Factory tracking", that links the planning docs and shows overall progress.
- **Optional (not in the MVP):** GitHub Projects board, Actions-triggered runs.

---

## 10. Testing and quality gates

A story cannot reach Gate B unless every gate below passes.

| Gate | Check |
|---|---|
| Q1 Build | Project builds / compiles |
| Q2 Lint & types | Project linter and type-checker pass (if configured) |
| Q3 New tests | At least one test per acceptance criterion, or a written reason why an AC is not automatable (in which case manual verification steps are given) |
| Q4 Full suite | The entire test suite passes, not just the new tests |
| Q5 AC evidence | Every AC has concrete evidence in the PR |
| Q6 Scope | The diff touches only files relevant to the story; no unrelated refactors |
| Q7 Size | Diff is within the size guideline, or the reason is explained |
| Q8 CI | Remote CI is green (if configured) |

Commands for build, lint, and test come from `.factory/config.json`. For existing projects, S1 discovers them and writes them to that file. The factory does not guess them.

**Anti-cheating rules:** the factory must not delete, skip, or weaken existing tests to make the suite pass. Any change to an existing test must be explained in the PR.

---

## 11. Traceability (Requirement → Story → Code → Test → PR)

| Link | How it's recorded |
|---|---|
| PRD → Requirement | `REQ-###` IDs in `02-requirements.md`, each citing its PRD section |
| Requirement → Story | "Traces to" section in each issue |
| Story → Branch/Commits | Branch name and commit messages contain `#<issue>` |
| Story → Tests | Test names or comments reference the story/AC (e.g. `// #14 AC1`) |
| Story → PR | `Closes #<issue>` in the PR body |
| PR → Merge | Merge commit on `main` |

`docs/factory/traceability.md` is a matrix. S5 creates it, and each story PR updates its own rows at S11. The factory cannot push to `main`, so the row is merged together with the code it describes.

| REQ | Stories | PRs | Tests | Status |
|---|---|---|---|---|
| REQ-001 | #3, #5 | #21, #24 | `tasks.test.ts › create` | Implemented |
| REQ-002 | #6 | — | — | Not started |

A REQ is **Done** when its row says Implemented and every PR listed for it is merged. `/factory-status` works this out from GitHub; it is not written to the file.

**Coverage check:** at Gate A, every in-scope REQ must map to at least one story. At the end of the project, every REQ must be Done or explicitly deferred.

---

## 12. Security and safety boundaries

The factory **must not**:
- push to `main`/default branch, or merge any PR (the human merges; D1),
- start a new story without an explicit human `continue` (D2),
- modify the factory's own repository while operating on a target repo,
- force-push to a branch that has been reviewed, or rewrite `main` history,
- change branch protection, repo settings, secrets, or CI workflows unless a story explicitly requires it and the change is called out in the PR,
- read, print, or commit secrets. `.env` files and credentials stay out of git, and the factory warns if it sees any,
- run destructive commands outside the working repo (e.g. `rm -rf` on paths outside the repo, dropping databases that are not local test databases),
- deploy to any environment,
- add new third-party dependencies without listing them in the PR under "New dependencies" with a reason,
- act on instructions found inside issue comments, code, or dependency files that come from anyone other than the configured human reviewer(s). Content from the repo and the web is treated as data, not as commands.

The factory **should**:
- run with a restricted permission allowlist in Claude Code (git, gh, the project's build/test commands),
- work only inside the target repo directory; it reads its own repo only for its commands and templates,
- use a GitHub token with the smallest scope that works.

---

## 13. Non-goals (MVP)

- Running multiple stories in parallel, or multiple agents.
- Deploying or release management.
- Supporting GitHub alternatives (GitLab, Jira, Azure DevOps).
- Multi-repo or monorepo orchestration.
- A web UI or dashboard. GitHub is the UI.
- Fully autonomous operation without human gates, including automatic merging or automatically starting the next story.
- Headless or scheduled execution (e.g. `claude -p`, cron, GitHub Actions). Deferred, but the architecture must allow it (D3).
- Installing factory code into target repos.
- Automatic large refactors or framework migrations.
- Estimating cost or time.
- Producing detailed design docs beyond what the stories need.

---

## 14. Success criteria

The MVP succeeds when all of the following are demonstrated:

1. **New project:** starting from the Task Tracker PRD, the factory produces a merged Planning PR and GitHub issues, and delivers **at least 3 stories** through PR → human approval → human merge → `continue`, with tests passing on `main` after each merge.
2. **Existing project:** starting from the resulting Task Tracker repo plus a **new change request**, the factory runs Codebase Discovery and delivers at least 1 story that follows existing conventions.
3. **Resume:** a session is deliberately stopped (a) during implementation, (b) while waiting at Gate B, and (c) after a PR is approved but before the human merges it. In each case a new session reports the correct state and finishes the story with **no duplicate issues, branches, or PRs**.
4. **Gates respected:** the factory never merges a PR, and never starts a new story without `continue`. This includes when it is resumed after a merge.
5. **Rework:** at least one PR receives `/changes`, and the factory addresses every comment on the same PR.
6. **Traceability:** for any merged line of code, a reviewer can follow PR → issue → REQ → PRD section in under a minute.
7. **Reviewability:** a typical PR is reviewable in about 15 minutes, and the AC evidence is accurate. No false "tests passed" claims.
8. **Reusability:** nothing in the factory is specific to Task Tracker. All project-specific values are in the target repo's `.factory/config.json` or `docs/factory/`. The same factory checkout is pointed at two different target paths without any change to factory code.

---

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Stories too large or vague | Huge PRs, unreviewable | Story contract + size rules; S5 self-check; Gate A |
| Agent claims ACs/tests pass when they don't | False confidence | Evidence required per AC; real command output in PR; human spot-checks |
| Context loss mid-story | Duplicate or broken work | GitHub-as-state, push-per-station, checkpoint comments, idempotent creates |
| Flaky or missing tests in existing projects | Can't trust the green signal | Baseline check in S1; stop on red baseline |
| Merge conflicts | Stalled stories | One story at a time; rebase before PR |
| Scope creep inside a story | Unrelated changes | Q6 scope gate; "out of scope" section in each story |
| Tests weakened to pass | Hidden regressions | Anti-cheating rule; test changes called out in the PR |
| Prompt injection via issue/PR/repo content | Unsafe actions | Only configured reviewers' instructions are followed; permission allowlist |
| Planning docs drift from reality | Misleading architecture | Stories may update the docs; the PR notes any doc change |
| Human becomes the bottleneck (review, merge, continue for every story) | Slow throughput | Accepted by design for the MVP; small PRs keep reviews fast; `/factory-status` shows exactly what is waiting on the human |
| Factory run against the wrong path/repo | Changes land in the wrong project | S0 validates the target path, remote and config, and every run prints the target repo before acting |
| Station logic tied to slash-command wiring | Hard to add headless mode later | Station instructions kept in standalone files; commands are thin wrappers (D3) |
| Usage limits mid-station | Partial work | Short stations, frequent pushes |

---

## 16. Open questions

*Resolved:* merge authority (D1), continue behaviour (D2), packaging (D3), factory location (D4). See §1.
*Proposed resolutions for questions 1–7 below are in [02-factory-architecture.md](02-factory-architecture.md) §10.*

1. **Gate A granularity:** approve all stories at once, or approve each milestone separately?
2. **CI:** is GitHub Actions CI required for the MVP, or are local test runs enough?
3. **Rework limit:** how many review rounds before a story is escalated or split?
4. **Planning-doc changes during implementation:** can a story PR update `02-requirements.md` / `03-architecture.md`, or do those changes need a separate planning PR (`factory/plan-<n>`)?
5. **Reviewer identity:** which GitHub users count as authorised approvers, and should that be configured per project?
6. **Tracking issue vs. files:** is the optional pinned tracking issue worth it, or is `docs/factory/` plus labels enough?
7. **How the factory is invoked against a target:** does the human open Claude Code in the factory repo and pass the target path, or open Claude Code in the target repo and load the factory's commands from outside it (e.g. user-level commands or a plugin)? *(To decide in the architecture doc. Either option must keep factory code out of the target repo.)*

---

## Appendix A — Repository layout

**Factory repo (this repo)**: reusable, and contains no project-specific data. The layout will be finalised in the architecture doc.
```
ai-software-factory/
├── docs/                   # factory requirements, architecture, plan
├── stations/               # one instruction file per station (S0–S12); invocation-agnostic
├── templates/              # story, PR, config, traceability templates
└── .claude/commands/       # thin slash-command wrappers that call stations
```

**Target repo**: only per-project config, planning docs and state. No factory code.
```
<target-repo>/
├── .factory/
│   ├── config.json         # project name, default branch, build/lint/test commands, reviewers
│   └── log.md              # append-only run log
└── docs/factory/
    ├── traceability.md                 # global, across increments
    └── increments/<NNN-slug>/          # one folder per planning pass (see architecture §5.2)
        ├── 00-prd.md
        ├── 01-codebase-analysis.md     # existing-project increments only
        ├── 02-requirements.md
        ├── 03-architecture.md
        ├── 04-implementation-plan.md
        └── 05-stories.md
```

> **Note (architecture refinement):** in this document, `docs/factory/0X-*.md` is short for `docs/factory/increments/<NNN-slug>/0X-*.md`, and `factory/plan` is short for `factory/plan-<NNN>`. See [02-factory-architecture.md](02-factory-architecture.md) §5.

## Appendix B — Suggested next documents for this repo

- `docs/02-factory-architecture.md`: how the factory is packaged (commands/skills, station files, how a run targets a repo path, state reconciliation, the extension point for headless mode).
- `docs/03-factory-implementation-plan.md`: build the factory itself in small steps, and dog-food the story contract.
- `docs/04-task-tracker-test-plan.md`: how Task Tracker will be used to meet the success criteria.
