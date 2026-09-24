# Templates

Skeletons for everything the factory writes into a target repo or onto GitHub. Stations fill them in; they are never copied with placeholders left in.

| Template | Becomes | Written by | Contract |
|---|---|---|---|
| [config.json](config.json) | `<target>/.factory/config.json` | S00 (S01 fills in `commands`) | Architecture §5.3 |
| [story.md](story.md) | Body of each story issue | S05b (`issues sync`) | Requirements §4, architecture §5.4–5.5 |
| [pr.md](pr.md) | Body of each story PR | S11 (refreshed during rework) | Requirements §6, §10; architecture §5.5, §7.2 |
| [planning-pr.md](planning-pr.md) | Body of the Planning PR | S05 | Requirements §2.1, §7 (Gate A), §11; architecture §5.5 |
| [traceability.md](traceability.md) | `<target>/docs/factory/traceability.md` | S05 (created once, then updated by S05 of later increments and by each story PR at S11) | Requirements §11 |

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

| Placeholder | Value |
|---|---|
| `{{story_id}}` | `STORY-###` |
| `{{issue}}` | Issue number, without `#` |
| `{{summary}}` | What changed and why, in 2–5 bullets |
| `{{requirements}}` | Comma-separated `REQ-###` IDs, as in the issue's "Traces to" |
| `{{traceability_rows}}` | Which `docs/factory/traceability.md` rows this PR updates, e.g. `REQ-003, REQ-007 updated` |
| `{{ac_verification}}` | One line per AC, copied unchanged from the AC verifier (rule H5): `- [x] AC1 — pass — evidence: …`. Use `- [ ]` for `fail` and `not-verifiable`. |
| `{{tests_added}}` | New tests, named so they reference the story and AC |
| `{{tests_changed}}` | Existing tests changed, each with the reason (rule H3), or `None` |
| `{{test_command}}` | `commands.test` from the config |
| `{{test_result}}` | The real result, e.g. `42 passed, 0 failed`. Never a prediction (rule H1). |
| `{{gate_build}}`, `{{gate_lint}}`, `{{gate_new_tests}}`, `{{gate_full_suite}}`, `{{gate_ac_evidence}}`, `{{gate_scope}}`, `{{gate_size}}`, `{{gate_ci}}` | Result of each quality gate Q1–Q8 (requirements §10): the command and its outcome, or `Skipped: commands.<name> is null` (rule H4). Q8 is `Not configured` when the target has no CI. |
| `{{new_dependencies}}` | Each new third-party dependency with its reason (rule S9), or `None` |
| `{{doc_changes}}` | Corrective edits to planning docs (architecture §10, question 4), or `None` |
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
