<!-- factory:planning increment={{increment}} -->
Planning for increment `{{increment}}`. No issues exist and no code has been written yet. Issues are created only after you merge this PR (Gate A).

## Summary
{{summary}}

## Planning documents
{{planning_documents}}

## Requirements coverage
{{requirements_coverage}}

## Stories
{{stories}}

## Issues to be created
Output of `python scripts/factory.py issues sync --dry-run` on this branch:

```text
{{issues_sync_dry_run}}
```

## Assumptions and open questions
{{open_questions}}

## Risks / notes for reviewer
{{risks}}

## How to review (Gate A)
- **To request changes:** comment on this PR with `/changes` on the first line, followed by your feedback. Then run `/factory-resume`. The factory revises the documents on this same branch and replies to each point.
- **To approve:** merge this PR yourself. Your merge is the approval. The factory never merges.
- After merging, run `/factory-resume` to create the issues. The factory then stops and waits for `/factory-continue` before starting the first story.
