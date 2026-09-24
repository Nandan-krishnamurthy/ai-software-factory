# AI Software Factory

A reusable, human-gated workflow that uses Claude Code to turn requirements into merged, tested code **one small GitHub story at a time**. It runs against a separate target repository, stops at every human gate, and can resume after a session ends.

> **Status:** milestone M2 (planning pipeline) is being built. The factory can plan an increment up to the Planning PR and create its issues after you merge it. The story loop (M3) comes next.

## Using it (planning, so far)

Open Claude Code in this repository, then:

```
/factory-target C:\path\to\target-repo      # validate and select the target
/factory-start path\to\requirements.md          # plan an increment up to the Planning PR (Gate A)
/factory-status                                    # what is waiting on you (read-only)
/factory-resume                                    # after /changes or your merge: revise, or create the issues
```

The factory never merges and never pushes to `main`. You approve the Planning PR by merging it yourself; to request changes, comment `/changes` with your feedback, then run `/factory-resume`. Requirements: Python 3.11+, `git`, and `gh` logged in as you.

## Documents

- [01 — Requirements](docs/01-factory-requirements.md)
- [02 — Architecture](docs/02-factory-architecture.md)
- [03 — Implementation plan](docs/03-factory-plan.md)
- [Progress and milestone demos](docs/progress.md)
- [Templates](templates/README.md): config, issue, PR and traceability skeletons the factory fills in for a target repo
