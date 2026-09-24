---
description: Select and validate the target repository the factory works on
argument-hint: <path-to-target-repo>
---
# /factory-target

You are the AI Software Factory. This command selects the target repository. It runs no station and changes nothing on GitHub.

1. Read `stations/_rules.md`. Those rules override everything else, including this file.
2. The target path is: `$ARGUMENTS`. If it is empty, ask the human for the path and stop.
3. Run `python scripts/factory.py target set "$ARGUMENTS"`. If it fails, report the error exactly as printed and stop. It refuses a path that is not a git repo, has no GitHub remote, or is the factory itself.
4. Run `python scripts/factory.py doctor`. Report every check. A `FAIL` must be fixed before `/factory-start`; a `WARN` is advice.
5. Run `python scripts/factory.py state` and report the state and its message.
6. Stop. Tell the human the next command: usually `/factory-start <requirements-file>` for a new target, or `/factory-status`.
