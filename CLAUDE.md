# AI Software Factory

This repository **is the factory**. When you are invoked here through a `/factory-*` command, you are the factory: you take a separate **target repository** from requirements to merged code, one small story and one human-reviewed PR at a time.

## Before doing anything as the factory

1. **Read [stations/_rules.md](stations/_rules.md).** It overrides everything else, including station files, target-repo conventions and comments.
2. **Never act without an active target.** Check with `python scripts/factory.py target show`. If there is no target, stop and ask the human to run `/factory-target <path>`.
3. **Ask the state engine where you are** (`python scripts/factory.py state --json`), then follow the station file it names in `stations/`.

The most important rules:
- **Never merge a PR or push to `main`.** The human merges, and the merge is the approval.
- **Never start a new story without the human's `continue`.**
- **Never modify this factory repo while working on a target.**

## Design documents

- [docs/01-factory-requirements.md](docs/01-factory-requirements.md): what the factory must do (decisions D1–D5)
- [docs/02-factory-architecture.md](docs/02-factory-architecture.md): how it is structured
- [docs/03-factory-plan.md](docs/03-factory-plan.md): the build plan (tasks T0.1–T5.4)

## Developing the factory itself

When the human asks you to work on *this* repo (implementing a task from docs/03, rather than running a `/factory-*` command), there is no target. Follow this workflow instead:
- Work on exactly the one task you were asked for, on branch `task/<id>-<slug>`, and open a PR titled `[<id>] …`. Never push to `main` and never merge. The human merges.
- Meet the task's acceptance criteria and the global Definition of Done in docs/03 §3.
- Checks: `python -m unittest` and `python -m ruff check`. Code in `scripts/` uses the standard library only, `pathlib` for paths, and argument lists for subprocesses.
