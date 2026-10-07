---
description: Report where the factory is and what is waiting on you (read-only)
---
# /factory-status

You are the AI Software Factory. This command only reports. It runs no station, and changes nothing locally or on GitHub.

1. Read `stations/_rules.md`. Those rules override everything else, including this file.
2. Run `python scripts/factory.py target show`. If there is no active target, tell the human to run `/factory-target <path>` and stop (rule T1).
3. Run `python scripts/factory.py status`. Show its output to the human exactly as printed, in a code block: do not reorder, shorten or reinterpret it. It contains, in this order:
   - the `Target: …` line (rule T2);
   - **One line: what the human does next** (`Next: …`);
   - a `Hint: …` when a PR waiting for review has comments from the human but no `/changes`, which the factory does not act on (rule U3);
   - the state, increment, next station, who it is waiting on, the commands allowed now, and any items or problems;
   - the progress of the current increment's stories;
   - the **Done** status of each requirement: `Implemented` in `docs/factory/traceability.md` and every listed PR merged (requirements §11).
4. If the human asks for the next free IDs, also run `python scripts/factory.py increment show`.
5. Stop.
