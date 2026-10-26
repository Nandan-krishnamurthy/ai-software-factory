# Requirements: 002-add-due-dates

This increment changes an existing project. These requirements describe the **change** (the delta), not the whole system. Every requirement of the earlier increments stays in force unless it is listed under "Changed or retired requirements".

## Current system
The change request ([00-prd.md](00-prd.md)) is one line: "Add due dates to tasks". Increment 001-initial already delivered due dates, and every one of these requirements is Done (see [01-codebase-analysis.md](01-codebase-analysis.md)):

- REQ-003: an optional due date (`YYYY-MM-DD`) can be given when a task is created, and is shown on the task as `Due <date>` in a `<time>` element (`src/ui/render.ts`).
- REQ-009: the due date can be set, changed or cleared on an existing task.
- REQ-012: tasks are sorted by due date ascending, undated tasks last, and ties keep creation order (`src/domain/sort.ts`).
- REQ-014: due dates are stored in `localStorage` (`task-tracker:v1`) and restored when the app opens.

001-initial also assumed that "overdue tasks get no special treatment". Because the request as written was already met, the human was asked in the `/factory-start` session (2026-10-07) what this increment should deliver, and chose **overdue highlighting**: active tasks whose due date has passed are visibly marked as overdue. The requirements below describe that change.

## Functional
- **REQ-022** (PRD §Add due dates to tasks): In the Active view, a task whose due date is earlier than today's date (the device's local calendar date) shows a visible text label "Overdue" next to its due date.
- **REQ-023** (PRD §Add due dates to tasks): A task due today, due on a later date, or with no due date shows no "Overdue" label.
- **REQ-024** (PRD §Add due dates to tasks): A completed task shows no "Overdue" label, whatever its due date. Reopening a completed task whose due date has passed shows the label again.
- **REQ-025** (PRD §Add due dates to tasks): When the due date of a task is set, changed or cleared (REQ-009), its "Overdue" label appears or disappears to match the new date as part of the same action, without a page reload.

## Non-functional
- **REQ-026** (PRD §Add due dates to tasks): The overdue state is conveyed by text that is part of the task's content for assistive technology, not by colour or styling alone, and any styling added for it passes the existing automated accessibility audit (axe, including colour contrast) in both views.

## Changed or retired requirements
None. REQ-003, REQ-009, REQ-012 and REQ-014 stay in force unchanged. Only the 001-initial assumption "Overdue tasks get no special treatment" is superseded, by REQ-022 to REQ-026.

## Unchanged behaviour to protect
The stories must keep these tests passing:

- REQ-003, REQ-004 (create with due date and priority): `tests/e2e/due-date-priority.spec.ts`, `src/domain/task.test.ts`, `src/ui/render.test.ts`.
- REQ-009, REQ-010 (edit or clear due date and priority): `tests/e2e/edit-due-date-priority.spec.ts`, `src/domain/task.test.ts`, `src/app/controller.test.ts`.
- REQ-012 (order by due date, undated last, ties in creation order): `tests/e2e/sort-by-due-date.spec.ts`, `src/domain/sort.test.ts`. Overdue tasks are **not** moved or regrouped.
- REQ-005, REQ-006, REQ-007 (complete, reopen, views): `tests/e2e/complete-and-views.spec.ts`, `src/domain/filter.test.ts`.
- REQ-013, REQ-014, REQ-020 (persistence and corrupted data): `tests/e2e/persistence.spec.ts`, `tests/e2e/storage-failures.spec.ts`, `src/storage/taskStore.test.ts`. The stored format `task-tracker:v1` does not change.
- REQ-016, REQ-017 (keyboard use and accessible names): `tests/e2e/accessibility.spec.ts`.
- REQ-018, REQ-019 (no network requests; changes within 100 ms with 500 tasks): `tests/e2e/latency-and-network.spec.ts`.
- REQ-021 (static build): `tests/e2e/skeleton.spec.ts` and `npm run build`.

## Assumptions
- "Overdue" means a due date strictly before today's local date. A task due today is not overdue (REQ-023).
- "Today" is taken from the device clock in its local time zone whenever the list is rendered. The label is not updated live at midnight: an open page refreshes it on its next render (any user action) or reload.
- The label is the word "Overdue" in English, next to the existing `Due <date>` text. It may also get a distinct style, as long as REQ-026 holds.
- Overdue status is derived when rendering and never stored, so no data migration is needed.
- The Completed view never shows the label (REQ-024).
- Overdue tasks keep their position under REQ-012; no new sort order, filter or view is added.

## Out of scope
- Re-implementing due-date entry, editing, sorting or storage (PRD §Add due dates to tasks): already delivered by REQ-003, REQ-009, REQ-012 and REQ-014.
- Notifications or reminders for due or overdue tasks: a non-goal of the original PRD (001-initial, Out of scope) and not asked for.
- A "Due today" or "Due soon" label, a separate overdue view or filter, and a time of day on due dates: not chosen by the human for this increment.

## Open questions
These do not block planning; it continues on the assumptions above. Answer at Gate A with `/changes` if any assumption is wrong.

1. Should a task due **today** also be marked (for example "Due today")? (Assumed: no; only past dates are overdue.)
2. Should overdue tasks be moved to the top of the list? (Assumed: no; REQ-012 order is kept, and overdue tasks already come first because they have the earliest dates.)
3. Should the label update live at midnight while the page stays open with no interaction? (Assumed: no; it updates on the next render.)

## PRD coverage
| PRD section | Requirements |
|---|---|
| Add due dates to tasks (the whole change request; it has no headings) | REQ-022, REQ-023, REQ-024, REQ-025, REQ-026 (existing due-date behaviour: REQ-003, REQ-009, REQ-012, REQ-014) |
