---
description: Report where the factory is and what is waiting on you (read-only)
---
# /factory-status

You are the AI Software Factory. This command only reports. It runs no station, and changes nothing locally or on GitHub.

1. Read `stations/_rules.md`. Those rules override everything else, including this file.
2. Run `python scripts/factory.py target show`. If there is no active target, tell the human to run `/factory-target <path>` and stop (rule T1).
3. Run `python scripts/factory.py state --json`. Start your report with the `Target: …` line it prints (rule T2).
4. Run `python scripts/factory.py increment show` for the current increment and the next free IDs.
5. If the state is `GATE_A_WAITING`, run `python scripts/factory.py feedback --pr <N>` (with `<N>` from `details.pr`) and report how many comments are waiting without a `/changes`.
6. Report, in this order:
   - **One line: what the human does next.** Base it on `waiting_on` and `details.message`, e.g. "Review Planning PR #N: merge it to approve, or comment /changes."
   - The state, the increment and the next station.
   - The commands allowed now (`allowed_commands`).
   - Any `details.problems` or `details.items`, listed as they are.
7. Stop.
