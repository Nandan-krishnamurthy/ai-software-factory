# ADR-0003: Plugin packaging and target-root invocation belong to T9

| | |
|---|---|
| **Status** | Accepted. The work itself is **planned, not started**. |
| **Decided** | 2026-10-08 |
| **Recorded** | 2026-10-22 |
| **Related** | [ADR-0001](0001-strict-sequential-roadmap.md), [ADR-0002](0002-m6-m9-roadmap-provenance.md) |

## Context

- The factory today runs in **checkout mode** ([02-factory-architecture.md](../02-factory-architecture.md) §3): Claude Code is opened in the factory repo, `/factory-target <path>` records the target in the gitignored `.factory-local/target.json`, and the target is added to `permissions.additionalDirectories` in `.claude/settings.local.json`.
- The architecture kept "a plugin, run from the target" as a **future packaging option** (§3, "Why not the alternatives"; §11, "Plugin packaging"). Requirement D3 packages the MVP as Claude Code skills and slash commands.
- The original roadmap recommended running the T9.1 plugin spike early, alongside M6, because its results could affect how M6–M8 write commands and station text.

## Decision

1. **Plugin packaging and target-root invocation are milestone M9, tasks T9.1–T9.9**, as specified in [05-roadmap-m6-m9.md](../05-roadmap-m6-m9.md):
   - T9.1 plugin spike and decision record;
   - T9.2 manifest and components; T9.3 plugin-root path resolution; T9.4 target-root invocation;
   - T9.5 guard liveness canary and fail-closed hardening; T9.6 `doctor` safety checks; T9.7 hostile-target suite; T9.8 Windows verification;
   - T9.9 plugin as the single supported mode, with the documentation rewrite.
2. **None of it is pulled forward**, including the T9.1 spike ([ADR-0001](0001-strict-sequential-roadmap.md)). It starts after M8, which it depends on: T9.7 uses the T8.2 eval harness, and T9.9 switches the T8.1 runner's adapter.
3. **Until T9.9 lands, checkout mode is the only supported mode**, and the documentation describes it as such.

## Status of the work (2026-10-22)

| | |
|---|---|
| **Completed** | Nothing of M9. The repository has no `.claude-plugin/`, `hooks/` or `bin/` folder, and no `CLAUDE_PLUGIN_ROOT` reference. Commands are in `.claude/commands/`; `/factory-target` and `.factory-local/target.json` are in use. |
| **Planned** | T9.1–T9.9, after M8. |
| **Already done elsewhere, not plugin work** | Some findings the roadmap assigns to M9 are tracked in the backlog: guard gaps for T9.5 ([B-09](../backlog.md#b-09) to [B-13](../backlog.md#b-13)) and branch protection for T9.6 ([B-24](../backlog.md#b-24)). They are open. |

## Consequences

- Any risk the spike would have found early (plugin command naming, whether a target's `disableAllHooks` silences the guard, Windows path and shim behaviour) is found only at T9.1. Rework in M6–M8 text is possible; under ADR-0001 it is handled then.
- New command and station text written before T9 targets checkout mode.
- No task before T9 adds plugin manifests, hooks in plugin form or target-root resolution.

## Gaps

- The roadmap's closing section suggests that M6–M8 write every engine call as `python scripts/factory.py …` and every station path as `stations/…`, so that T9.3's rewrite is mechanical. That section is superseded on ordering, and the repository does not record whether this suggestion was adopted as a rule (see [ADR-0001](0001-strict-sequential-roadmap.md), "Not decided here").
- Whether B-10, B-11, B-14 and B-15 belong to T9.5 is a scope decision for that task ([backlog.md](../backlog.md), "Guard gaps").
