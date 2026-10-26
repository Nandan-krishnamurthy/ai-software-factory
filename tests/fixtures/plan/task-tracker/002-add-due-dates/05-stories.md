# Stories: 002-add-due-dates

Stories are cut from [04-implementation-plan.md](04-implementation-plan.md), in build order. Each is meant to be reviewable in about 15 minutes and to leave `main` working. `Blocked by` lists the stories that must be merged first.

## M1: Overdue label

### STORY-013: Show an "Overdue" label on active tasks whose due date has passed
- Traces to: REQ-022, REQ-023, REQ-024, REQ-025
- Blocked by: None
- Milestone: M1
#### Story
As an individual user, I want active tasks whose due date has passed to be marked "Overdue" so that I can see at a glance what I am late on.
#### Acceptance criteria
- AC1: Given today is 2026-10-07 on the device, when the Active view shows a task due 2026-10-06, then that task's row shows the text "Overdue" next to its due date.
- AC2: Given today is 2026-10-07 on the device, when the Active view shows a task due 2026-10-07, a task due 2026-10-08 and a task with no due date, then none of these rows shows "Overdue".
- AC3: Given an active task due before today that shows "Overdue", when the user marks it complete, then its row in the Completed view shows no "Overdue" label, and when the user reopens it, then its row in the Active view shows "Overdue" again.
- AC4: Given an active task due before today that shows "Overdue", when the user edits its due date to a later date than today or clears it, then the label disappears as part of the same action; and given a task due after today, when its due date is changed to a date before today, then the label appears.
- AC5: Given the existing tests, when the test command runs, then every existing unit and end-to-end test still passes, and the list order (REQ-012) and the `Due <date>` text are unchanged.
#### Out of scope
- Styling of the label and the accessibility audit of it (STORY-014).
- A "Due today" label, a separate overdue view or filter, and a live update at midnight (assumptions in `02-requirements.md`).
- Any change to the stored format `task-tracker:v1`.
#### Technical notes
- `domain/task.ts`: add `localDate(now: Date): string` (local `YYYY-MM-DD` from `getFullYear`/`getMonth`/`getDate`, never `toISOString`) and `isOverdue(task, today): boolean` (not completed, has a due date, and `dueDate < today`).
- `app/controller.ts`: add `readonly today?: string` to `AppState` and set `today: localDate(now())` on every state passed to `render`, including the first.
- `ui/render.ts`: `taskItem(task, today)` appends `<span class="task-overdue">Overdue</span>` after the `<time class="task-due">` when `isOverdue` is true; no `today` means no label.
- E2E tests fix the browser date with Playwright's clock API (`page.clock`), already part of `@playwright/test`. No new dependencies.
- Existing e2e tests use dates in 2026 that may now be in the past, so their rows may show the label. If an existing assertion breaks, update it and explain it in the PR (rule H3).
#### Test plan
- Unit: `localDate` for times just after midnight and just before midnight local time; `isOverdue` for yesterday, today, tomorrow, no due date and a completed task; the controller includes `today` in rendered states; `render` shows the label only for overdue tasks and none when `today` is absent.
- End-to-end: with the clock fixed to 2026-10-07, add tasks due 2026-10-06, 2026-10-07, 2026-10-08 and none, and check the labels; complete and reopen the overdue task; edit its due date forwards, clear it, and edit another task's date backwards.

## M2: Overdue styling and accessibility

### STORY-014: Style the "Overdue" label accessibly and audit it
- Traces to: REQ-026
- Blocked by: STORY-013
- Milestone: M2
#### Story
As a user who relies on a screen reader or has low vision, I want the overdue marker to be readable text with enough contrast so that I get the same information as everyone else.
#### Acceptance criteria
- AC1: Given an overdue active task, when the page is shown, then the "Overdue" label has a distinct style defined for `.task-overdue` in `index.html`, and its text and background meet WCAG AA contrast.
- AC2: Given an overdue active task in the Active view, when axe scans the page (including the colour-contrast rule), then it reports no violations.
- AC3: Given a completed task with a past due date in the Completed view, when axe scans the page, then it reports no violations.
- AC4: Given an overdue task titled "Pay rent", when its list item's accessible text is read, then it includes both "Pay rent" and "Overdue".
#### Out of scope
- Any change to when the label is shown (STORY-013).
- Icons or colour-only indicators.
#### Technical notes
- One CSS rule for `.task-overdue` in the inline `<style>` of `index.html`, for example bold text in a dark red that passes AA on the page background. No external fonts or resources (REQ-018).
- Extend `tests/e2e/accessibility.spec.ts` (existing `@axe-core/playwright`), fixing the clock as in STORY-013.
#### Test plan
- End-to-end: axe scans of the Active view with an overdue task and the Completed view with a past-dated completed task; an assertion that the overdue row's text contains the title and "Overdue"; a check that `.task-overdue` has a computed style different from the plain row text.
