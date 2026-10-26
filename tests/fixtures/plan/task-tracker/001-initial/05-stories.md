# Stories: 001-initial

Stories are cut from [04-implementation-plan.md](04-implementation-plan.md), in build order. Each is meant to be reviewable in about 15 minutes and to leave `main` working. `Blocked by` lists the stories that must be merged first.

## M1: Walking skeleton and task capture

### STORY-001: Walking skeleton: TypeScript + Vite app with unit and end-to-end tests
- Traces to: REQ-021, REQ-018
- Blocked by: None
- Milestone: M1
#### Story
As the developer of Task Tracker, I want a minimal buildable app with working unit and end-to-end test runners so that every later story can be built and verified in the same way.
#### Acceptance criteria
- AC1: Given a fresh clone, when the install command and then the build command run, then the build succeeds and writes static files (`index.html` and its assets) to `dist/`.
- AC2: Given the scaffold, when `npm run typecheck` runs, then strict TypeScript checking passes with no errors.
- AC3: Given the scaffold, when the test command runs, then at least one Vitest unit test and one Playwright end-to-end test run and pass.
- AC4: Given the built app served locally, when the page opens, then it shows the heading "Task Tracker" and requests nothing except the page's own files.
- AC5: Given `.factory/config.json`, when this story is merged, then `commands.install`, `commands.build`, `commands.typecheck` and `commands.test` hold the exact commands run in this story, and `commands.lint` stays `null`.
#### Out of scope
- Any task features (STORY-002 onwards).
- CI workflows and deployment (no requirement asks for them).
- A linter.
#### Technical notes
- Dev dependencies, each with the reason given in `03-architecture.md` §Technology choices: `typescript`, `vite`, `vitest`, `jsdom`, `@playwright/test`. List them under "New dependencies" in the PR. `@axe-core/playwright` is added later, by the story that needs it.
- Layout: `index.html`, `src/main.ts`, `src/domain/`, `src/storage/`, `src/app/`, `src/ui/`, `tests/e2e/`. Unit tests sit next to the code as `*.test.ts`.
- `tsconfig.json` with `strict: true`, target ES2022. `index.html` loads no external resources (REQ-018).
- The Playwright config starts `vite preview` against the built output, so the end-to-end tests exercise the static build (REQ-021). Chromium only.
- `npm test` runs Vitest, then Playwright. The install command includes `npx playwright install chromium`.
- `package-lock.json` is generated. Say so in the PR, because it inflates the line count.
#### Test plan
- Unit: one Vitest test of a trivial pure function (for example the app title constant), proving the runner works.
- End-to-end: the page loads with the heading "Task Tracker", and a request listener records no requests to other origins.
- Build: the build command succeeds and `dist/index.html` exists.

### STORY-002: Add a task by title
- Traces to: REQ-001, REQ-002, REQ-015
- Blocked by: STORY-001
- Milestone: M1
#### Story
As an individual user, I want to type a task title and add it straight away so that I can capture a to-do within seconds, with no setup.
#### Acceptance criteria
- AC1: Given the app has just opened, when the page loads, then an add-task form with a labelled title field and an Add button is shown, with no sign-up, login or setup step.
- AC2: Given the add-task form, when the user types "Buy milk" and submits it with Enter or the Add button, then "Buy milk" appears in the task list without a page reload, and the title field is cleared.
- AC3: Given the add-task form, when the user submits an empty or whitespace-only title, then no task is added and a visible validation message says that a title is required.
- AC4: Given the validation message is shown, when the user then submits a valid title, then the task is added and the message disappears.
- AC5: Given a title with leading or trailing spaces, when it is submitted, then the task shows the trimmed title.
#### Out of scope
- Saving tasks across reloads (STORY-003): until then, tasks are lost on reload.
- Due date and priority (STORY-005).
#### Technical notes
- `domain/task.ts`: the full `Task` type from `03-architecture.md` §Data model (`dueDate` and `priority` are `null` for now), plus `validateTitle` and `createTask`, with `now` and `newId` injected.
- `app/controller.ts` holds `tasks` and the validation message. `ui/render.ts` and `ui/events.ts` render the form and the list.
- Use a native `<form>` with a `<label>` for the title input, so that Enter submits it and it is keyboard-operable from the start.
- The validation message sits in an `aria-live="polite"` element, referenced by the input's `aria-describedby`.
#### Test plan
- Unit: `validateTitle` (empty, whitespace, trimmed, valid); `createTask` appends in creation order with the injected id and time.
- Unit (jsdom): the controller's `addTask` updates state and calls `render`.
- End-to-end: add a task and see it listed without navigation; an empty title shows the message; the message clears after a valid add.

## M2: Persistence

### STORY-003: Save tasks and restore them when the app is reopened
- Traces to: REQ-013, REQ-014
- Blocked by: STORY-002
- Milestone: M2
#### Story
As an individual user, I want my tasks saved automatically so that they are still there when I come back to the app in the same browser.
#### Acceptance criteria
- AC1: Given the user has added tasks, when the page is reloaded, then the same tasks are shown, with the same titles, in the same order.
- AC2: Given the user has added tasks and closed the page, when the app is opened again in a new page of the same browser profile, then the tasks are shown without any user action.
- AC3: Given the user adds a task, when the add action has returned, then the `task-tracker:v1` entry in `localStorage` already contains that task.
- AC4: Given nothing has been stored yet (first visit), when the app opens, then it shows an empty list and no error.
#### Out of scope
- Corrupted data and failed writes (STORY-004).
#### Technical notes
- `storage/taskStore.ts`: `loadTasks(storage)` and `saveTasks(storage, tasks)` with the stored format `{ "version": 1, "tasks": [...] }` under the key `task-tracker:v1` (`03-architecture.md` §Data model).
- The controller calls `saveTasks` synchronously after every state change, before rendering: the single save path that every later action uses (REQ-013).
- `main.ts` loads the tasks before the first render. Inject `Storage` so that unit tests use an in-memory fake.
#### Test plan
- Unit: encode/decode round trip with all `Task` fields; `loadTasks` with no key returns an empty list; `saveTasks` writes the exact format.
- Unit (jsdom): after `addTask`, the fake storage holds the new task.
- End-to-end: add tasks, reload, and see them again; open a new page in the same browser context and see them again.

### STORY-004: Survive corrupted storage and failed saves
- Traces to: REQ-020, REQ-013
- Blocked by: STORY-003
- Milestone: M2
#### Story
As an individual user, I want the app to keep working even if its stored data is damaged or cannot be saved so that a storage problem never locks me out of my task list.
#### Acceptance criteria
- AC1: Given the `task-tracker:v1` entry holds text that is not valid JSON, when the app opens, then it shows an empty task list and the user can add a task.
- AC2: Given the stored value is valid JSON of the wrong shape (a wrong version, `tasks` not a list, or a task with an invalid field), when the app opens, then it shows an empty task list without crashing.
- AC3: Given saving to `localStorage` throws (for example, the quota is exceeded), when the user adds a task, then the task still appears, and a visible warning, announced to assistive technology, says that changes may not be saved.
- AC4: Given corrupted stored data, when the app opens and the user makes no change, then the stored value is left exactly as it was.
#### Out of scope
- Repairing partially valid data: decoding is all-or-nothing (`03-architecture.md` decision 5).
- Multi-tab consistency (a PRD non-goal).
#### Technical notes
- `loadTasks` validates every field (types, `priority` values, `YYYY-MM-DD` dates, `version === 1`) and returns `{tasks: [], problem}` on any failure. It never throws.
- `saveTasks` catches exceptions from `setItem` and returns `{ok: false, error}`. The controller shows the warning in an `aria-live` region and keeps the in-memory state.
#### Test plan
- Unit: a table of malformed stored values, each giving an empty list; `saveTasks` with a throwing fake `Storage` returns an error.
- End-to-end: seed a malformed value with `addInitScript`, open the app, see an empty list and add a task. Stub `setItem` to throw, add a task, and see the warning.

## M3: Due date, priority and ordering

### STORY-005: Set a due date and priority when adding a task
- Traces to: REQ-003, REQ-004
- Blocked by: STORY-003
- Milestone: M3
#### Story
As an individual user, I want to give a task an optional due date and priority when I add it so that I can see what is urgent and important.
#### Acceptance criteria
- AC1: Given the add-task form, when the user adds a task with a due date, then the task shows that date.
- AC2: Given the add-task form, when the user adds a task with priority Low, Medium or High, then the task shows that priority.
- AC3: Given the add-task form, when the user adds a task leaving the due date and priority empty, then the task shows neither a date nor a priority.
- AC4: Given a task with a due date and a priority, when the page is reloaded, then its due date and priority are unchanged.
- AC5: Given the priority control, when the user opens it, then the only choices are none, Low, Medium and High.
#### Out of scope
- Sorting by due date (STORY-006).
- Changing the date or priority after creation (STORY-009).
- Overdue highlighting and reminders (PRD non-goals).
#### Technical notes
- Use `<input type="date">` (value `YYYY-MM-DD`, stored as is) and a `<select>` with an empty "No priority" option. Both are labelled.
- Show the date in the user's locale format, but store only the ISO date string (`03-architecture.md` decision 4).
#### Test plan
- Unit: `createTask` with and without `dueDate` and `priority`; an invalid priority is rejected.
- End-to-end: add tasks with every combination, check what each shows, reload and check again.

### STORY-006: List tasks by due date, soonest first
- Traces to: REQ-012
- Blocked by: STORY-005
- Milestone: M3
#### Story
As an individual user, I want my tasks ordered by due date so that the most urgent ones are always at the top.
#### Acceptance criteria
- AC1: Given tasks due on 2026-10-03, 2026-10-01 and 2026-10-02, added in that order, when the list is shown, then they appear in the order 2026-10-01, 2026-10-02, 2026-10-03.
- AC2: Given tasks with and without due dates, when the list is shown, then every task without a due date appears after every task with one.
- AC3: Given two tasks with the same due date, or both without one, when the list is shown, then the one created first appears first.
- AC4: Given tasks with the same due date and different priorities, when the list is shown, then priority does not change their order.
- AC5: Given a sorted list, when the page is reloaded, then the order is the same.
#### Out of scope
- User-selectable sort orders (the PRD defines a single default order).
#### Technical notes
- `domain/sort.ts`: a stable sort over the creation-ordered array, comparing `dueDate` strings, with `null` last (`03-architecture.md` decision 6). The order is not stored.
#### Test plan
- Unit: `sortTasks` for the dated, undated, tie and priority cases; the input array is not mutated.
- End-to-end: add tasks in a scrambled order and check the rendered order before and after a reload.

## M4: Completing tasks and views

### STORY-007: Complete and reopen tasks, with Active and Completed views
- Traces to: REQ-005, REQ-006, REQ-007
- Blocked by: STORY-003
- Milestone: M4
#### Story
As an individual user, I want to tick tasks off and see open and done tasks separately so that I can tell at a glance what is left to do.
#### Acceptance criteria
- AC1: Given the app opens, when the page loads, then the Active view is selected and marked as current, and it lists only tasks that are not done.
- AC2: Given an active task, when the user ticks its checkbox, then it disappears from the Active view and appears in the Completed view.
- AC3: Given a completed task in the Completed view, when the user unticks its checkbox, then it disappears from the Completed view and appears in the Active view.
- AC4: Given the user switches to the Completed view, when it is shown, then only done tasks are listed and the Completed control is marked as current.
- AC5: Given a task has been completed, when the page is reloaded, then it is still completed.
#### Out of scope
- An "All" view (assumption in `02-requirements.md`).
- Remembering the selected view across reloads: the app always opens on Active.
#### Technical notes
- `domain/task.ts` `setCompleted`; `domain/filter.ts` `tasksForView`. Each view is sorted by `sortTasks` if it exists by then, or in creation order until STORY-006 is merged.
- The filter is a pair of buttons with `aria-pressed`, or a tab list, and must be keyboard-operable. The checkbox label names the task.
- Adding a task while the Completed view is shown switches to Active, so the new task is visible.
#### Test plan
- Unit: `setCompleted` both ways; `tasksForView` for each view.
- End-to-end: complete, check both views, reopen, check both views, and reload.

## M5: Editing and deleting

### STORY-008: Edit a task's title
- Traces to: REQ-008
- Blocked by: STORY-007
- Milestone: M5
#### Story
As an individual user, I want to correct a task's title so that my list stays accurate.
#### Acceptance criteria
- AC1: Given an active task, when the user chooses Edit, changes the title and saves, then the new title is shown immediately.
- AC2: Given a completed task in the Completed view, when the user edits its title and saves, then the new title is shown and the task stays completed.
- AC3: Given a task in edit mode, when the user saves an empty or whitespace-only title, then the save is rejected with a visible validation message, and the old title is kept.
- AC4: Given a task in edit mode, when the user presses Escape, then editing is cancelled, the old title is kept, and focus returns to that task's Edit button.
- AC5: Given a task whose title was edited, when the page is reloaded, then the new title is shown.
#### Out of scope
- Editing the due date and priority (STORY-009).
#### Technical notes
- Inline edit form in the task row (`03-architecture.md` decision 8): Enter saves, Escape cancels. Reuse `validateTitle`.
- `domain/task.ts` `updateTask(list, id, patch)`: the task keeps its position in the creation-ordered array.
#### Test plan
- Unit: `updateTask` on the title, with validation; the other fields are unchanged.
- End-to-end: edit in each view, reject an empty title, cancel with Escape and check focus, reload.

### STORY-009: Change or clear a task's due date and priority
- Traces to: REQ-009, REQ-010
- Blocked by: STORY-006, STORY-008
- Milestone: M5
#### Story
As an individual user, I want to change or remove a task's due date and priority so that they keep up with my plans.
#### Acceptance criteria
- AC1: Given a task in edit mode, when the user sets or changes the due date and saves, then the new date is shown and the task moves to its place in the due-date order.
- AC2: Given a task with a due date, when the user clears the due date and saves, then no date is shown and the task moves after all tasks that have a due date.
- AC3: Given a task in edit mode, when the user sets or changes the priority to Low, Medium or High and saves, then the new priority is shown.
- AC4: Given a task with a priority, when the user changes it to "No priority" and saves, then no priority is shown.
- AC5: Given a completed task whose due date and priority were changed, when the page is reloaded, then the changes are kept and the task is still completed.
#### Out of scope
- None
#### Technical notes
- Extend the inline edit form from STORY-008 with the same date input and priority select as the add-task form, pre-filled with the current values.
#### Test plan
- Unit: `updateTask` setting, changing and clearing `dueDate` and `priority`.
- End-to-end: change and clear each field, check the displayed value and the list position, and reload.

### STORY-010: Delete a task
- Traces to: REQ-011
- Blocked by: STORY-007
- Milestone: M5
#### Story
As an individual user, I want to delete tasks I no longer need so that my list only shows what matters.
#### Acceptance criteria
- AC1: Given an active task, when the user presses its Delete button, then the task is removed immediately and appears in neither view.
- AC2: Given a completed task in the Completed view, when the user presses its Delete button, then the task is removed immediately and appears in neither view.
- AC3: Given a task has been deleted, when the page is reloaded, then it does not reappear.
- AC4: Given the user deletes a task with the keyboard, when the task is removed, then focus moves to the next task's Delete button, or to the title field if no tasks remain in the view.
#### Out of scope
- A confirmation dialog or undo (assumption in `02-requirements.md`).
#### Technical notes
- `domain/task.ts` `deleteTask`. The Delete button's accessible name includes the task title.
#### Test plan
- Unit: `deleteTask` removes only the given id and leaves the others in order.
- End-to-end: delete from each view, reload, and check focus after a keyboard delete.

## M6: Accessibility and performance verification

### STORY-011: Accessibility audit: keyboard operation and accessible names
- Traces to: REQ-016, REQ-017
- Blocked by: STORY-006, STORY-009, STORY-010
- Milestone: M6
#### Story
As a keyboard or screen-reader user, I want every control to be reachable and clearly named so that I can manage my tasks without a mouse.
#### Acceptance criteria
- AC1: Given tasks in the Active view, the Completed view, and a task in edit mode, when axe scans each of these states, then it reports no violations.
- AC2: Given only a keyboard, when the user adds a task with a due date and priority, completes it, switches to Completed, edits it, reopens it and deletes it, then every step succeeds without a mouse.
- AC3: Given a task titled "Buy milk", when the accessible names of its checkbox, Edit button and Delete button are read, then each one includes "Buy milk".
- AC4: Given the user submits an empty title, when the validation message appears, then it is in a live region and is referenced by the title field's `aria-describedby`.
- AC5: Given keyboard navigation, when any interactive element has focus, then a visible focus indicator is shown.
#### Out of scope
- Screen-reader testing with real assistive technology: automated checks only.
#### Technical notes
- Add `@axe-core/playwright` as a dev dependency (reason: `03-architecture.md` §Technology choices), listed under "New dependencies" in the PR.
- Fix whatever the audit finds in `ui/`. Do not change behaviour covered by earlier stories.
#### Test plan
- End-to-end: axe scans of each state; a keyboard-only journey test; accessible-name assertions using `getByRole(..., { name })`.

### STORY-012: Verify UI latency and no network use across full journeys
- Traces to: REQ-019, REQ-018
- Blocked by: STORY-006, STORY-009, STORY-010
- Milestone: M6
#### Story
As an individual user, I want every change to show up instantly and my data never to leave my browser so that the app feels immediate and stays private.
#### Acceptance criteria
- AC1: Given 500 stored tasks, when the user adds a task, then it appears in the list within 100 ms (the median of 5 runs, measured inside the page).
- AC2: Given 500 stored tasks, when the user completes, reopens, edits and deletes a task, then each change is shown within 100 ms (the median of 5 runs each).
- AC3: Given the built app, when a full journey runs (add, complete, edit, delete, switch views, reload), then no network request is made except for the page's own files on load.
#### Out of scope
- Performance tuning beyond what is needed to meet the 100 ms target.
#### Technical notes
- Seed the 500 tasks with `addInitScript` into `localStorage`. Measure from the triggering event to the DOM update with `performance.now()` inside the page, to avoid cross-process timing noise.
- If a target is missed, profile and fix the render path in this story. If it cannot be met, stop and ask (rule H6).
#### Test plan
- End-to-end: the latency tests above, and a request log across the full journey asserting only same-origin static file requests at load time.
