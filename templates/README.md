# Templates

Skeletons for everything the factory writes into a target repo or onto GitHub. Stations fill them in; they are never copied with placeholders left in.

| Template | Becomes | Written by | Contract |
|---|---|---|---|
| [config.json](config.json) | `<target>/.factory/config.json` | S00 (S01 fills in `commands`) | Architecture §5.3 |
| [story.md](story.md) | Body of each story issue | S05b (`issues sync`) | Requirements §4, architecture §5.4–5.5 |
| [pr.md](pr.md) | Body of each story PR | S11 (refreshed during rework) | Requirements §6, §10; architecture §5.5, §7.2 |
| [planning-pr.md](planning-pr.md) | Body of the Planning PR | S05 | Requirements §2.1, §7 (Gate A), §11; architecture §5.5 |
| [traceability.md](traceability.md) | `<target>/docs/factory/traceability.md` | S05 (created once, then updated by S05 of later increments and by each story PR at S11) | Requirements §11 |
| [requirements-delta.md](requirements-delta.md) | `<target>/docs/factory/increments/<INC>/02-requirements.md` of an **existing project** | S02, when the increment has a `01-codebase-analysis.md` | Requirements §2.2, §3 (S2); architecture §5.2 |
| [architecture-delta.md](architecture-delta.md) | `<target>/docs/factory/increments/<INC>/03-architecture.md` of an **existing project** | S03, when the increment has a `01-codebase-analysis.md` | Requirements §2.2, §3 (S3) |

A new project's `02-requirements.md` and `03-architecture.md` follow the section lists in S02 and S03. An existing project's follow these two **delta** templates, which describe the change against what already exists (T5.2).

`tests/test_templates.py` checks every template against these contracts: its sections, their order, its markers and its placeholders. Changing a template's structure means changing that test and the contract it cites.

## Placeholders

A placeholder is `{{name}}`, where `name` is lower-case letters and underscores. Every placeholder must be replaced before the text is used; text that still contains `{{` is a factory bug. Markdown placeholders may be replaced with several lines. Where a value is empty, write `None` rather than leaving a heading with nothing under it.

The **marker** lines (`<!-- factory:… -->`, architecture §5.5) must be kept exactly as they are, apart from their placeholders. The state engine finds issues and PRs by these markers, not by their titles.

### `config.json`
| Placeholder | Value |
|---|---|
| `{{project}}` | Short project name, e.g. `my-app` |
| `{{repo}}` | GitHub `owner/name` of the target |
| `{{default_branch}}` | Usually `main` |
| `{{reviewer}}` | The human's GitHub login. Add more logins to the list if needed. |

All `commands` start as `null`. S01 fills in the ones it finds; the factory never guesses a command (rule H4). A command left `null` means that quality gate is skipped, and the PR says so.

### `story.md`
The issue **title** is `{{story_id}}: <story title>`.

| Placeholder | Value |
|---|---|
| `{{story_id}}` | `STORY-###` from `05-stories.md` |
| `{{increment}}` | Increment folder name, e.g. `001-initial` |
| `{{milestone}}` | Milestone from `05-stories.md`, e.g. `M1`. Used to pick the next story. |
| `{{story}}` | `As a <user>, I want <capability> so that <benefit>.` |
| `{{traces_to}}` | Comma-separated `REQ-###` IDs |
| `{{acceptance_criteria}}` | 1–5 lines of `- [ ] AC<n>: Given <context>, when <action>, then <result>.` |
| `{{out_of_scope}}` | Bullet list, or `None` |
| `{{blocked_by}}` | Comma-separated issue numbers (`#12, #14`), or `None` |
| `{{technical_notes}}` | Likely files and areas touched; relevant architecture decisions |
| `{{test_plan}}` | `- Unit: …` and `- Integration/E2E: …` lines |

### `pr.md`
The PR **title** is `[#<issue>] <story title>`. If the factory is stuck, the PR is opened as a **draft** and the Summary starts by saying what failed (rule H2).

`python scripts/factory.py pr render --issue <I> --notes F` fills this template from the recorded facts (T6.3), and `pr check <P>` holds an open PR against a fresh render. Only `{{summary}}`, `{{risks}}` and `{{follow_ups}}` are the model's, from the `## Summary`, `## Risks` and `## Follow-ups` sections of `--notes`; every other value below is computed and may not be edited.

| Placeholder | Value |
|---|---|
| `{{story_id}}` | `STORY-###` |
| `{{issue}}` | Issue number, without `#` |
| `{{summary}}` | What changed and why, in 2–5 bullets |
| `{{requirements}}` | Comma-separated `REQ-###` IDs, as in the issue's "Traces to" |
| `{{traceability_rows}}` | Which `docs/factory/traceability.md` rows this PR updates, e.g. `REQ-003, REQ-007 updated` |
| `{{ac_verification}}` | One line per AC, copied unchanged from the AC verifier (rule H5): `- [x] AC1 — pass — evidence: …`. Use `- [ ]` for `fail` and `not-verifiable`. |
| `{{tests_added}}` | New tests, named so they reference the story and AC |
| `{{tests_changed}}` | Existing tests changed (in a test file that existed at the base: a removed or modified line, or an added line inside a test that existed at the base), each with its `Changed test:` line, or flagged **not declared** (rule H3); or `None` |
| `{{test_command}}` | `commands.test` from the config |
| `{{test_result}}` | The real result, e.g. `42 passed, 0 failed`. Never a prediction (rule H1). |
| `{{gate_build}}`, `{{gate_lint}}`, `{{gate_new_tests}}`, `{{gate_full_suite}}`, `{{gate_ac_evidence}}`, `{{gate_scope}}`, `{{gate_size}}`, `{{gate_ci}}` | Result of each quality gate Q1–Q8 (requirements §10): the command and its outcome, or `Skipped: commands.<name> is null` (rule H4). Q8 is `Not configured` when the target has no CI. Q6 is `Not checked: the story contract declares no areas`, followed by the files touched: stories declare no areas to check against. |
| `{{new_dependencies}}` | Each dependency a changed manifest adds, with the reason from its `New dependency:` line, or flagged when either side is missing (rule S9); or `None` |
| `{{doc_changes}}` | The planning docs (`docs/factory/increments/…`) the story changes, with their line counts (architecture §10, question 4), or `None` |
| `{{risks}}` | Anything the reviewer should look at closely, including any content that tried to change the factory's behaviour (rule U4), or `None` |
| `{{follow_ups}}` | Bullet list, or `None` |

### `planning-pr.md`
The PR **title** is `[Planning] {{increment}}: <one-line description>`.

| Placeholder | Value |
|---|---|
| `{{increment}}` | Increment folder name, e.g. `001-initial` |
| `{{summary}}` | What this increment delivers, in 2–5 bullets |
| `{{planning_documents}}` | A linked list of the increment's `0X-*.md` files and `docs/factory/traceability.md` |
| `{{requirements_coverage}}` | Every in-scope `REQ-###` with the stories that cover it, and every deferred or out-of-scope item with its reason |
| `{{stories}}` | Table: `STORY-###`, title, milestone, blocked by, traces to |
| `{{issues_sync_dry_run}}` | The exact output of `issues sync --dry-run`, unedited |
| `{{open_questions}}` | Assumptions made and questions for the reviewer, or `None` |
| `{{risks}}` | Anything the reviewer should look at closely, or `None` |

### `traceability.md`
| Placeholder | Value |
|---|---|
| `{{rows}}` | One row per requirement: `\| REQ-### \| stories \| PRs \| tests \| status \|`. Stories are written as `STORY-###` until their issue exists, then as `STORY-### (#N)`. Unknown cells are `—`. |

Later increments add rows to the existing file rather than creating it again.

### `requirements-delta.md`
Every requirement bullet keeps the form S02 checks: `- **REQ-###** (PRD §<section>): <one testable statement>`, numbered consecutively from `increment show`'s `next_req`. Earlier requirements are referred to by plain ID (`REQ-005`, not bold), so they never count as new ones.

| Placeholder | Value |
|---|---|
| `{{increment}}` | Increment folder name, e.g. `002-due-dates` |
| `{{current_system}}` | What exists today that this change touches, from `01-codebase-analysis.md` and the earlier increments' requirements, citing their `REQ-###` IDs |
| `{{functional}}` | New functional requirements, one bullet each |
| `{{non_functional}}` | New non-functional requirements, one bullet each, or `None` |
| `{{changed_requirements}}` | Earlier requirements this increment changes or retires: `- REQ-005: changed by REQ-022 (<how>)` or `- REQ-009: retired (<why>)`, or `None` |
| `{{unchanged_behaviour}}` | Existing behaviour that must keep working, citing earlier `REQ-###` IDs and the tests that cover it today. The stories keep these tests passing. |
| `{{assumptions}}` | What was assumed where the change request is silent, or `None` |
| `{{out_of_scope}}` | Change-request statements deliberately left out, each with its section and the reason, or `None` |
| `{{open_questions}}` | Questions for the reviewer at Gate A, or `None` |
| `{{prd_coverage}}` | One row per heading of `00-prd.md`: `\| <heading> \| REQ-###, … \|` or `\| <heading> \| Out of scope \|` |

### `architecture-delta.md`
| Placeholder | Value |
|---|---|
| `{{increment}}` | Increment folder name, e.g. `002-due-dates` |
| `{{overview}}` | What changes and why, in a few sentences, plus a diagram if it helps |
| `{{current_architecture}}` | The existing components the change touches, as they are today, with their files (from `01-codebase-analysis.md` and the earlier `03-architecture.md`) |
| `{{changes}}` | One row per component: `\| <component> \| New, Changed or Removed \| <responsibility and interfaces after the change> \|` |
| `{{data_model}}` | Changes to entities, fields or stored data, or `None` |
| `{{key_decisions}}` | One entry per decision, with the options considered and the reason. Following the existing conventions is the default; a departure from them is a decision. |
| `{{technology_choices}}` | The existing stack is kept. Each new third-party dependency with its reason (rule S9), or `None` |
| `{{compatibility}}` | How existing data, users and behaviour are kept working: data migration, defaults for existing records, anything removed. `None` only if nothing existing is affected. |
| `{{requirement_mapping}}` | One row per `REQ-###` of this increment: `\| REQ-### \| <component(s)> \|` |
