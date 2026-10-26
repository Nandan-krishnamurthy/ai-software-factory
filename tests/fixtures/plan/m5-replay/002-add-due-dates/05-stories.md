<!-- Authored for T7.4's tests: not a historical record (see 02-requirements.md). One story
for the replayed requirement, in the T7.4 format, so that only the overlap fails. -->
# Stories: 002-add-due-dates

## M1: Due dates

### STORY-013: Add due dates to tasks
- Traces to: REQ-022
- Blocked by: None
- Milestone: M1
- Files: src/domain/task.ts (~40), src/ui/render.ts (~30), src/domain/task.test.ts (~60)
#### Story
As a user, I want to give my tasks due dates so that I know when each one is due.
#### Acceptance criteria
- AC1: Given the add-task form, when the user enters a title and a due date and submits it, then the new task shows that due date.
#### Out of scope
None
#### Technical notes
None
#### Test plan
- Unit: a task created with a due date keeps it.
