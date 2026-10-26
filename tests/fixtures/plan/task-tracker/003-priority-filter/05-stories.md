# Stories: 003-priority-filter

Stories are cut from [04-implementation-plan.md](04-implementation-plan.md), in build order. Each is meant to be reviewable in about 15 minutes and to leave `main` working. `Blocked by` lists the stories that must be merged first.

## M1: Filter the view by priority

### STORY-015: Filter the current view by priority
- Traces to: REQ-027, REQ-028, REQ-029, REQ-030
- Blocked by: None
- Milestone: M1
#### Story
As an individual user, I want to list only the tasks of one priority in the current view so that I can focus on what matters most without scanning the whole list.
#### Acceptance criteria
- AC1: Given the app has just opened, when the Active or the Completed view is shown, then a group of five buttons labelled "All", "High", "Medium", "Low" and "No priority" is shown in that order, and "All" is the pressed one.
- AC2: Given a view with tasks of High, Medium and Low priority and a task with no priority, when the user chooses "High", "Medium" or "Low", then only that view's tasks with that priority are listed; when the user chooses "No priority", then only that view's tasks without a priority are listed; and when the user chooses "All", then every task of the view is listed.
- AC3: Given three High-priority tasks, two with different due dates and one with none, when the user chooses "High", then they are listed soonest due first and the undated one last, as in REQ-012, and tasks with equal due dates keep their creation order.
- AC4: Given "High" is chosen in the Active view, when the user switches to the Completed view and back, then "High" stays the pressed choice and each view lists only its own High-priority tasks.
- AC5: Given the existing tests, when the test command runs, then every existing unit and end-to-end test still passes, and with "All" chosen both views list exactly the tasks they listed before this change, in the same order.
#### Out of scope
- Keeping the filter right after a task's priority is edited or a task is added, and the accessibility and speed checks of the filter (STORY-016).
- Remembering the filter across reloads (STORY-017).
- Any change to the stored format `task-tracker:v1`, to `View` or to the sort order.
#### Technical notes
- `domain/filter.ts`: add `PriorityFilter = 'all' | Priority | 'none'`, `PRIORITY_FILTERS` (`['all', 'high', 'medium', 'low', 'none']`) and the pure `tasksForPriority(tasks, filter)`, which keeps the input order and never mutates it. `View` and `tasksForView` stay unchanged.
- `app/controller.ts`: add `readonly priorityFilter?: PriorityFilter` to `AppState` (absent means `'all'`), start on `'all'`, and add `setPriorityFilter(filter)`. `setView` keeps the filter.
- `ui/render.ts`: a second group `<div id="task-priority-filter" role="group" aria-label="Priority">` after the "Show" group, with five `<button type="button" data-priority-filter="…">` toggle buttons; `render` sets `aria-pressed` and lists `sortTasks(tasksForPriority(tasksForView(tasks, view), filter))`.
- `ui/events.ts`: a click listener per filter button calls `controller.setPriorityFilter`.
- No new dependencies.
#### Test plan
- Unit (`src/domain/filter.test.ts`): `tasksForPriority` for "All", each priority and "No priority", that it keeps the input order and does not mutate its input (AC2, AC3). Controller: starts on `'all'`, `setPriorityFilter` changes it, `setView` keeps it (AC1, AC4). Render: exactly one filter button pressed, and only matching rows listed in sorted order (AC1 to AC3).
- End-to-end: add tasks of each priority and none with different due dates; check the five buttons and the default (AC1); choose each filter and check the rows (AC2) and their order (AC3); complete a High task, switch views with "High" chosen and back (AC4).

## M2: Filter updates, accessibility and speed

### STORY-016: Keep the priority filter right as tasks change, accessibly and fast
- Traces to: REQ-031, REQ-032, REQ-033, REQ-034
- Blocked by: STORY-015
- Milestone: M2
#### Story
As a user who relies on the keyboard or a screen reader, and who changes tasks often, I want the priority filter to stay correct, usable and fast so that the list always shows what I chose.
#### Acceptance criteria
- AC1: Given "High" is chosen and a High-priority task is listed, when the user changes its priority to Low or clears it, then it leaves the list as part of the same action; given a Low-priority task, when its priority is changed to High, then it appears; and when a listed High-priority active task is completed, then it leaves the Active list and is listed in the Completed view while "High" is chosen there.
- AC2: Given "Low" is chosen, when the user adds a task, then "All" becomes the pressed choice and the new task is listed; and when an add is rejected because the title is empty, then "Low" stays chosen.
- AC3: Given the filter buttons, when the user uses only the keyboard, then each can be reached with Tab and chosen with Enter or Space, each has an accessible name equal to its label, and only the chosen one reports `aria-pressed="true"`.
- AC4: Given each filter choice in turn, in the Active and in the Completed view, when axe scans the page, then it reports no violations.
- AC5: Given 500 tasks are stored, when the user chooses a filter, then the list shows the result within 100 ms of the user's action.
#### Out of scope
- The filter controls and the matching rule themselves (STORY-015).
- Remembering the filter across reloads (STORY-017).
#### Technical notes
- `app/controller.ts`: a successful `addTask` sets `priorityFilter: 'all'` next to `view: 'active'`; a rejected one leaves both as they are.
- Every other action already re-renders with the current filter, so AC1 should need no new code beyond tests; fix any gap the tests find.
- Accessibility: reuse `tests/e2e/accessibility.spec.ts` (existing `@axe-core/playwright`), finding the buttons by role and name.
- Speed: measure as `tests/e2e/latency-and-network.spec.ts` does (500 stored tasks, median of five runs).
- No new dependencies.
#### Test plan
- Unit: the controller resets the filter on a successful add and keeps it on a rejected one (AC2); after an edit or a toggle, the rendered rows match the filter (AC1).
- End-to-end: edit, clear and complete tasks with "High" chosen (AC1); add a task with "Low" chosen, and try an empty title (AC2); keyboard-only use and `aria-pressed` (AC3); axe scans for each choice in both views (AC4); the 500-task latency measurement for a filter change (AC5).

## M3: Remember the filter

### STORY-017: Remember the priority filter across reloads
- Traces to: REQ-027, REQ-035, REQ-036
- Blocked by: STORY-015
- Milestone: M3
#### Story
As a user who always works on one priority, I want the app to remember my priority filter so that I do not have to choose it again every time I open the app.
#### Acceptance criteria
- AC1: Given the user has chosen "High", when the page is reloaded, then "High" is the pressed choice and the view lists only its High-priority tasks.
- AC2: Given the user has chosen "Low", when the app is opened in a new page of the same browser, then "Low" is the pressed choice.
- AC3: Given nothing has been remembered yet, when the app opens, then "All" is the pressed choice and every task of the view is listed.
- AC4: Given the remembered filter value is not one of the five choices, when the app opens, then "All" is the pressed choice, no error is shown, and the stored tasks are loaded and listed exactly as without it.
- AC5: Given tasks are stored, when the user chooses filters and reloads, then the stored task data under `task-tracker:v1` is unchanged, and every existing persistence and storage-failure test still passes.
#### Out of scope
- The filter controls and the matching rule (STORY-015), and resetting to "All" when a task is added (STORY-016).
- Remembering the view (Active or Completed): the app still opens on Active.
- A warning when remembering the filter fails (architecture decision 8).
#### Technical notes
- New `src/storage/filterStore.ts`: `FILTER_KEY = 'task-tracker:priority-filter'`, `loadPriorityFilter(storage)` (a valid stored value, else `'all'`; never throws) and `savePriorityFilter(storage, filter)` (returns whether the write worked; never throws). It never reads or writes `task-tracker:v1`.
- `app/controller.ts`: `ControllerDeps` gains `priorityFilter?: PriorityFilter`; the first state uses it (`'all'` when absent); `update()` saves the filter only when it changed, and ignores a failed save.
- `main.ts`: passes `priorityFilter: loadPriorityFilter(localStorage)` to `createController`.
- No new dependencies.
#### Test plan
- Unit (`src/storage/filterStore.test.ts`): `loadPriorityFilter` for each of the five values, a missing value, an unknown value and a `getItem` that throws (AC3, AC4); `savePriorityFilter` with a working and a throwing `setItem`. Controller: starts from the remembered choice, saves when the filter changes, and does not save when it does not (AC1, AC5).
- End-to-end: choose "High" and reload (AC1); choose "Low" and open a new page in the same browser context (AC2); a first visit (AC3); an unknown value under `task-tracker:priority-filter` (AC4); the `task-tracker:v1` value before and after choosing filters and reloading (AC5).
