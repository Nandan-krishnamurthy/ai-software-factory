<!-- factory:pr story={{story_id}} -->
Closes #{{issue}}

## Summary
{{summary}}

## Traceability
Requirements: {{requirements}}
Story: #{{issue}} ({{story_id}})
Traceability matrix: {{traceability_rows}}

## Acceptance criteria verification
{{ac_verification}}

## Tests
- Added: {{tests_added}}
- Changed existing tests: {{tests_changed}}
- Full suite: `{{test_command}}` → {{test_result}}

## Quality gates
| Gate | Result |
|---|---|
| Q1 Build | {{gate_build}} |
| Q2 Lint & types | {{gate_lint}} |
| Q3 New tests | {{gate_new_tests}} |
| Q4 Full suite | {{gate_full_suite}} |
| Q5 AC evidence | {{gate_ac_evidence}} |
| Q6 Scope | {{gate_scope}} |
| Q7 Size | {{gate_size}} |
| Q8 CI | {{gate_ci}} |

## New dependencies
{{new_dependencies}}

## Doc changes
{{doc_changes}}

## Risks / notes for reviewer
{{risks}}

## Out of scope / follow-ups
{{follow_ups}}

## How to review (Gate B)
- **To request changes:** comment on this PR with `/changes` on the first line, followed by your feedback. Then run `/factory-resume`. The factory reworks this same PR and replies to each point.
- **To approve:** merge this PR yourself. Your merge is the approval. The factory never merges.
- After merging, run `/factory-resume` to close out the story. The factory will not start the next story until you run `/factory-continue`.
