# Requirements: 003-priority-filter

This increment changes an existing project. These requirements describe the **change** (the delta), not the whole system. Every requirement of the earlier increments stays in force unless it is listed under "Changed or retired requirements".

## Current system
The change request ([00-prd.md](00-prd.md)) asks for a filter by priority. Priority itself already exists and is Done (see [01-codebase-analysis.md](01-codebase-analysis.md)):

- REQ-004 and REQ-010: a task has an optional priority of exactly Low, Medium or High, set when it is created and set, changed or cleared later (`src/domain/task.ts`: `Priority`, `PRIORITIES`).
- REQ-007: the app has exactly two views, Active (not-done tasks) and Completed (done tasks), chosen with two toggle buttons in a group labelled "Show" (`src/domain/filter.ts`, `src/ui/render.ts`). The app opens on Active, and the view is not stored.
- REQ-012: in both views, tasks are listed by due date ascending, undated tasks last, ties in creation order; priority does not affect the order (`src/domain/sort.ts`).
- REQ-016, REQ-017: every interactive element, including the view controls, is keyboard-operable and has an accessible name.
- REQ-019: changes are reflected in the UI within 100 ms with 500 tasks stored.

No filter by priority exists. Adding a task already switches the view back to Active (`src/app/controller.ts`).

At Gate A, the reviewer asked on [Planning PR #33](https://github.com/Nandan-krishnamurthy/task-tracker-factory-test/pull/33) to "Remember the priority filter across reloads". That answers the change request's open question and overrides its non-goal "Remembering the filter across reloads": the chosen filter is now remembered (REQ-035, REQ-036).

## Functional
- **REQ-027** (PRD §Functional requirements FR-011, §Decisions): Both views show a priority filter with exactly five choices, in this order: "All", "High", "Medium", "Low" and "No priority". When the app opens and no filter choice is remembered (REQ-035), "All" is chosen.
- **REQ-028** (PRD §Functional requirements FR-012, §User journeys): A task is listed only if it is in the current view and matches the chosen filter: "All" matches every task, "High", "Medium" and "Low" match the tasks with that priority, and "No priority" matches the tasks that have none.
- **REQ-029** (PRD §Functional requirements FR-013, §Non-goals): The tasks listed under any filter choice keep the REQ-012 order; choosing a filter never reorders them.
- **REQ-030** (PRD §Functional requirements FR-014): When the user switches between Active and Completed, the chosen filter stays chosen and applies to the view now shown.
- **REQ-031** (PRD §Functional requirements FR-015): After a task's priority is set, changed or cleared (REQ-010), or a task is completed or reopened (REQ-005, REQ-006), the list shows exactly the tasks of the current view that match the chosen filter, as part of the same action and without a reload.
- **REQ-032** (PRD §Functional requirements FR-016): Adding a task while a choice other than "All" is chosen chooses "All", so the new task is listed.
- **REQ-035** (PRD §Open questions, §Assumptions requiring validation; Gate A feedback on PR #33): The chosen filter is remembered in the browser: after a reload, or when the app is opened again in the same browser, the last chosen filter is chosen again and applied to the view.
- **REQ-036** (PRD §Open questions; Gate A feedback on PR #33): When the remembered filter choice is missing or is not one of the five choices, the app opens with "All" chosen, shows no error, and loads and lists the tasks exactly as it would without it.

## Non-functional
- **REQ-033** (PRD §Non-functional requirements, §Decisions): Each filter choice can be reached and operated with the keyboard alone, has an accessible name, and exposes whether it is the chosen one to assistive technology in the same way as the Active/Completed controls; the page has no automated accessibility (axe) violations in either view with any choice chosen.
- **REQ-034** (PRD §Non-functional requirements): With 500 tasks stored, choosing a filter is reflected in the list within 100 ms of the user's action.

## Changed or retired requirements
- REQ-007: changed by REQ-028 (each view now lists only its tasks that match the chosen filter; with "All", the default, it lists exactly what it did before). The two views themselves are unchanged: "All" is a filter choice, not a third view, so 001-initial's decision that there is no "All" view still holds.
- REQ-016, REQ-017: their list of interactive elements now also includes the priority filter choices (REQ-033).
- REQ-013, REQ-014, REQ-020: unchanged. The remembered filter is kept apart from the task data, so the stored tasks, their format `task-tracker:v1` and its all-or-nothing check are not affected (REQ-036).

## Unchanged behaviour to protect
The stories must keep these tests passing:

- REQ-004, REQ-010 (create and edit priority): `tests/e2e/due-date-priority.spec.ts`, `tests/e2e/edit-due-date-priority.spec.ts`, `src/domain/task.test.ts`, `src/app/controller.test.ts`.
- REQ-005, REQ-006, REQ-007 (complete, reopen, views): `tests/e2e/complete-and-views.spec.ts`, `src/domain/filter.test.ts`. With "All" chosen, both views behave exactly as today.
- REQ-012 (order): `tests/e2e/sort-by-due-date.spec.ts`, `src/domain/sort.test.ts`. Priority still does not affect the order.
- REQ-013, REQ-014, REQ-020 (persistence and corrupted data): `tests/e2e/persistence.spec.ts`, `tests/e2e/storage-failures.spec.ts`, `src/storage/taskStore.test.ts`. The stored format `task-tracker:v1` does not change.
- REQ-016, REQ-017 (keyboard use and accessible names): `tests/e2e/accessibility.spec.ts`.
- REQ-018, REQ-019 (no network requests; changes within 100 ms with 500 tasks): `tests/e2e/latency-and-network.spec.ts`.
- REQ-021 (static build): `tests/e2e/skeleton.spec.ts` and `npm run build`.
- REQ-022 to REQ-026 (the "Overdue" label): `tests/e2e/overdue.spec.ts`, `src/ui/render.test.ts`.

## Assumptions
- The filter is remembered (REQ-035), reversing the change request's assumption that it is not saved. It is remembered in this browser's local storage, like the tasks (REQ-014), but apart from the task data, and once for the app, not separately per view.
- If remembering the choice fails (for example, storage is full or disabled), the filter still applies until the page is closed, and no warning is shown, because no task data is at risk. The existing warning for failed task saves (REQ-013) is unchanged.
- Only the priority filter is remembered: the app still opens on the Active view (REQ-007).
- The choices are labelled exactly "All", "High", "Medium", "Low" and "No priority", in that order, and appear as a second group of controls beside Active/Completed (PRD §Decisions).
- A filter choice that matches no task in the current view shows an empty list, as an empty view does today; no extra message is added (the PRD's Non-goals and Functional requirements ask for none).
- Adding a task keeps today's behaviour of switching to the Active view (`src/app/controller.ts`), and also chooses "All" (REQ-032), which is then the remembered choice.
- Deleting a task (REQ-011) needs no new rule: a deleted task is in neither view, whatever the filter.
- No new dependency is added, and the app still makes no network requests (REQ-018); both are existing constraints, not new requirements.

## Out of scope
- Changing the sort order, or sorting or grouping by priority (PRD §Non-goals): REQ-012 stays as it is (REQ-029).
- Counts per priority (PRD §Non-goals): not asked for.
- Changing how a priority is set, edited or stored (PRD §Non-goals): REQ-004 and REQ-010 stay as they are.
- Remembering the view (Active or Completed) across reloads: not asked for; the app still opens on Active (REQ-007).

## Open questions
None. The question "Should the chosen priority filter be remembered across reloads?" was answered **yes** by the reviewer at Gate A on PR #33 (REQ-035, REQ-036).

## PRD coverage
| PRD section | Requirements |
|---|---|
| Change request: Filter tasks by priority | REQ-027, REQ-028, REQ-029, REQ-030, REQ-031, REQ-032, REQ-033, REQ-034, REQ-035, REQ-036 |
| Problem | REQ-027, REQ-028 |
| Goals | REQ-027, REQ-028 |
| Non-goals | Out of scope (REQ-029 keeps the order unchanged), except "Remembering the filter across reloads", which the Gate A feedback on PR #33 brought into scope: REQ-035, REQ-036 |
| User journeys | REQ-027, REQ-028 |
| Journey 5: Focus on one priority | REQ-027, REQ-028, REQ-029 |
| Functional requirements | REQ-027, REQ-028, REQ-029, REQ-030, REQ-031, REQ-032 |
| Non-functional requirements | REQ-033, REQ-034 (no new dependencies and no network requests: existing REQ-018) |
| Constraints and assumptions | REQ-028 (existing REQ-004, REQ-007) |
| Verified constraints | REQ-028 (existing REQ-004, REQ-007) |
| Assumptions requiring validation | REQ-035, REQ-036 (the assumption that the filter is not saved was reversed at Gate A); REQ-028 |
| Decisions | REQ-027, REQ-028, REQ-033 |
| Open questions | REQ-035, REQ-036 (answered at Gate A) |
