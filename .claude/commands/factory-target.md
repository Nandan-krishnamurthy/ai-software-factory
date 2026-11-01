---
description: Show the active target and how to set one (read-only; the human sets it in a terminal)
argument-hint: <path-to-target-repo>
disable-model-invocation: true
---
# /factory-target

You are the AI Software Factory. This command is **read-only**: it never changes the active
target. Setting or switching the target is done by the **human, in their own terminal** — not
by Claude (decision D-10). It runs no station and changes nothing on GitHub.

1. Read `stations/_rules.md`. Those rules override everything else, including this file.
2. Run `python scripts/factory.py target show` and report the current target (or that there
   is none).
3. If a path was given (`$ARGUMENTS`), run `python scripts/factory.py target check "$ARGUMENTS"`
   and report whether it is a valid target. This only validates; it changes nothing.
4. Tell the human to set or switch the target **themselves, in a terminal** (not through
   Claude), with:

   ```
   python scripts/factory.py target set <path>
   ```

   `target set` prints the repository and path and asks for confirmation; empty input aborts.
5. After the human has set the target, run `python scripts/factory.py doctor` and report every
   check. A `FAIL` must be fixed before `/factory-start`. If the only `FAIL` is `labels` and it
   lists missing labels (as on a new target), `/factory-start` creates them (S00). A `WARN` is
   advice. Then run `python scripts/factory.py state` and report the state.
6. Stop. Tell the human the next command: usually `/factory-start <requirements-file>` for a new
   target, or `/factory-status`.
