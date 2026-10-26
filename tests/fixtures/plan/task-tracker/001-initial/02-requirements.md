# Requirements: 001-initial

Derived from [00-prd.md](00-prd.md) (Task Tracker PRD, status Approved, 2026-09-11). Section references are to the PRD's headings; `FR-###` are the PRD's own functional requirement IDs.

## Functional

- **REQ-001** (PRD §Functional requirements FR-001, §Journey 1): When the user enters a non-empty title and submits the add-task form, a new active task with that title appears in the active list without a page reload.
- **REQ-002** (PRD §Functional requirements FR-009): When the user submits the add-task form with an empty or whitespace-only title, no task is created and a visible validation message is shown next to the title field.
- **REQ-003** (PRD §Functional requirements FR-002, §Journey 1): The user can optionally give a due date (a calendar date) when creating a task; the created task shows that due date, and a task created without one shows no due date.
- **REQ-004** (PRD §Functional requirements FR-003, §Verified constraints, §Decisions): The user can optionally give a priority of exactly Low, Medium or High when creating a task; the created task shows that priority, and a task created without one shows no priority.
- **REQ-005** (PRD §Functional requirements FR-004, §Journey 2): When the user marks an active task complete (via a checkbox), it disappears from the active view and appears in the completed view.
- **REQ-006** (PRD §Functional requirements FR-004, §Journey 2): When the user marks a completed task incomplete, it disappears from the completed view and appears in the active view.
- **REQ-007** (PRD §Functional requirements FR-007, §Goals, §Desired outcomes): The user can switch between an Active view that lists only not-done tasks and a Completed view that lists only done tasks; the app opens on the Active view, and the current view is clearly indicated.
- **REQ-008** (PRD §Functional requirements FR-005, §Journey 3): The user can change the title of an existing task (active or completed); the new title is shown immediately, and saving an empty or whitespace-only title is rejected with a visible validation message, keeping the old title.
- **REQ-009** (PRD §Functional requirements FR-002, FR-005, §Journey 3): The user can set, change or clear the due date of an existing task (active or completed), and the change is shown immediately.
- **REQ-010** (PRD §Functional requirements FR-003, FR-005, §Journey 3): The user can set, change or clear the priority (Low, Medium, High) of an existing task (active or completed), and the change is shown immediately.
- **REQ-011** (PRD §Functional requirements FR-006, §Journey 3): When the user deletes a task (active or completed), it is immediately removed and appears in neither view.
- **REQ-012** (PRD §Functional requirements FR-010, §Verified constraints, §Decisions): In both views, tasks are listed by due date ascending (soonest first), tasks without a due date come after all dated tasks, and tasks with the same due date (or both without one) keep their creation order, oldest first.
- **REQ-013** (PRD §Functional requirements FR-008, §Non-functional requirements Reliability): Every create, edit, complete, reopen and delete is saved to the browser's local storage as part of the same user action, so that closing the tab or browser straight afterwards loses nothing.
- **REQ-014** (PRD §Functional requirements FR-008, §Journey 4, §Desired outcomes): When the app is opened again in the same browser on the same device, all saved tasks are shown automatically, with the same titles, statuses, due dates and priorities, without any user action.
- **REQ-015** (PRD §Desired outcomes, §Non-goals, §Verified constraints): Opening the app shows the add-task form straight away; there is no sign-up, login or other setup step.

## Non-functional

- **REQ-016** (PRD §Non-functional requirements Accessibility): Every interactive element (add-task form and its fields, complete checkbox, edit, delete, and the Active/Completed filter controls) can be reached and operated with the keyboard alone.
- **REQ-017** (PRD §Non-functional requirements Accessibility): Every interactive element listed in REQ-016 has an accessible name that identifies it (for a per-task control, including which task it acts on), and validation messages are announced to assistive technology.
- **REQ-018** (PRD §Non-functional requirements Security/privacy, §Verified constraints): After the page has loaded, the app makes no network requests; task data is never sent anywhere, and no personal data is collected.
- **REQ-019** (PRD §Non-functional requirements Performance): Creating, editing, completing, reopening or deleting a task is reflected in the UI within 100 ms of the user's action.
- **REQ-020** (PRD §Non-functional requirements Supportability): If the stored task data is missing, unreadable or malformed, the app starts with an empty task list and remains fully usable instead of crashing.
- **REQ-021** (PRD §Verified constraints, §Rollout and rollback): The app is a client-side web application whose production build is a set of static files that can be served by any static web host, with no backend.

## Assumptions

- A title made only of whitespace counts as empty (REQ-002, REQ-008). Titles are trimmed before saving. No maximum title length is enforced.
- "Optional" due date and priority can also be **removed** later by editing (REQ-009, REQ-010).
- Any calendar date may be used as a due date, including past dates. Overdue tasks get no special treatment (reminders and notifications are non-goals).
- Priority does not affect the sort order; only due date and creation order do (REQ-012). The PRD's default order is the only order: there is no user-selectable sort.
- There are exactly two views, Active and Completed, and no "All" view (PRD §Goals: "filtered by status: active and completed"). The app opens on Active (REQ-007).
- Deleting a task happens immediately, with no confirmation dialog and no undo (REQ-011).
- `localStorage` is the persistence mechanism (PRD §Assumptions requiring validation). If a save fails (for example, the storage quota is full or storage is disabled), the app keeps working in memory and shows a visible warning that changes may not be saved.
- Corrupted stored data is not deleted when it is read; it is replaced the next time the user saves a change (REQ-020).
- Supported browsers are the current stable versions of Chrome/Edge, Firefox and Safari (PRD §Assumptions requiring validation: no matrix was given). Automated end-to-end tests run on Chromium.
- The 100 ms target (REQ-019) is checked in automated end-to-end tests on a developer machine, with a list of up to 500 tasks. The PRD sets no maximum list size, and no limit is enforced.
- Multi-tab consistency is not handled: two open tabs may overwrite each other's changes (PRD §Non-goals).

## Out of scope

- User accounts, sign-in or any authentication (PRD §Non-goals): explicit non-goal; REQ-015 requires their absence.
- Syncing or accessing tasks from more than one device or browser (PRD §Non-goals): explicit non-goal.
- Sharing tasks or workspaces, or assigning tasks to others (PRD §Non-goals): explicit non-goal.
- Projects, boards, tags or any grouping beyond one personal list (PRD §Non-goals): explicit non-goal.
- Notes or free-text descriptions on a task (PRD §Non-goals, §Verified constraints): explicit non-goal.
- Notifications or reminders for due dates (PRD §Non-goals, §Risks and mitigations): explicit non-goal.
- Offline conflict resolution and multi-tab consistency guarantees (PRD §Non-goals): explicit non-goal.
- Success measures (PRD §Success measures): they are post-launch measurements (first 30 days after launch) and are not built. REQ-015 supports the "time to first task" measure; REQ-013, REQ-014 and REQ-020 support the "data loss" measure.
- Deploying or releasing the app (PRD §Rollout and rollback): the factory never deploys (factory rule S8). REQ-021 keeps the build deployable as static files; rollout and rollback are the human's.
- Disclosure of the local-only data-loss risk (PRD §Risks and mitigations): the PRD's mitigation is that the non-goal is "explicit and disclosed"; no in-app notice is required. See Open questions.

## Open questions

These are not blocking; planning uses the assumptions above. Answer at Gate A with `/changes` if any assumption is wrong.

1. Should whitespace-only titles be rejected like empty ones? (Assumed: yes.)
2. Can a due date or priority be removed from a task once it is set? (Assumed: yes.)
3. Should deleting a task ask for confirmation or offer undo? (Assumed: neither; it is immediate.)
4. When two tasks have the same due date, or neither has one, what order should they appear in? (Assumed: creation order, oldest first. Priority is not used.)
5. Which browsers must be supported? (Assumed: current Chrome/Edge, Firefox, Safari; automated tests on Chromium.)
6. Should the app show a notice that tasks live only in this browser, as a disclosure for the data-loss risk? (Assumed: no in-app notice.)

## PRD coverage

| PRD section | Requirements |
|---|---|
| Product Requirements Document: Task Tracker (title, status, owner) | Out of scope |
| Problem | REQ-001, REQ-005, REQ-006, REQ-013, REQ-014, REQ-015 |
| Users and context | REQ-014, REQ-015 |
| Desired outcomes | REQ-007, REQ-014, REQ-015 |
| Goals | REQ-001, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-013, REQ-014 |
| Non-goals | Out of scope |
| User journeys | REQ-001 to REQ-014 (see each journey) |
| Journey 1: Capture a new task | REQ-001, REQ-002, REQ-003, REQ-004 |
| Journey 2: Complete or reopen a task | REQ-005, REQ-006, REQ-007 |
| Journey 3: Edit or delete a task | REQ-008, REQ-009, REQ-010, REQ-011 |
| Journey 4: Return to the app later | REQ-013, REQ-014 |
| Functional requirements | FR-001 → REQ-001; FR-002 → REQ-003, REQ-009; FR-003 → REQ-004, REQ-010; FR-004 → REQ-005, REQ-006; FR-005 → REQ-008, REQ-009, REQ-010; FR-006 → REQ-011; FR-007 → REQ-007; FR-008 → REQ-013, REQ-014; FR-009 → REQ-002; FR-010 → REQ-012 |
| Non-functional requirements | REQ-013, REQ-016, REQ-017, REQ-018, REQ-019, REQ-020 |
| Success measures | Out of scope |
| Constraints and assumptions | REQ-004, REQ-012, REQ-013, REQ-015, REQ-018, REQ-021 |
| Verified constraints | REQ-004, REQ-012, REQ-015, REQ-018, REQ-021 |
| Assumptions requiring validation | REQ-013 (see Assumptions) |
| Risks and mitigations | Out of scope |
| Rollout and rollback | REQ-021 |
| Decisions | REQ-004, REQ-012, REQ-013, REQ-014, REQ-015 |
| Open questions | Out of scope |
| Approval | Out of scope |
