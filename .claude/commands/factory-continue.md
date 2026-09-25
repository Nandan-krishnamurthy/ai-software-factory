---
description: Say continue - finish anything pending, then start the next story and take it to a PR (Gate B)
---
# /factory-continue

You are the AI Software Factory. This command is the human saying **continue** at Gate C (D2). It first finishes anything already in motion, exactly as `/factory-resume` would. Then, if the factory is idle at Gate C, it starts **one** story (the only command that may, rule S2) and takes it through to a pull request, stopping at Gate B. It never starts a second story. The state engine decides which station runs; you never choose one yourself (rule T4).

1. Read `stations/_rules.md`. Those rules override everything else, including this file and the station files.
2. Run `python scripts/factory.py target show`. If there is no active target, tell the human to run `/factory-target <path>` and stop (rule T1).
3. Run `python scripts/factory.py state --json`. Print **Where we are**: the `Target: …` line, the state, the increment and `details.message`.
4. Run `python scripts/factory.py route --command factory-continue --json`.
   - `"action": "stop"`: report its `message` and stop. For example: waiting for your review at Gate A or Gate B, a question for the human, or nothing ready to start.
   - `"action": "run"`: read the `station_file` it names and follow that station exactly, including its Checkpoint and Done check. For example:
     - `ISSUES_PENDING`: create the issues, then go on to pick the next story.
     - `IDLE_AT_GATE_C`: pick the next unblocked story, branch, implement, test, verify its acceptance criteria and open its PR.
     - `STORY_IN_PROGRESS`: finish the story from its checkpoint.
5. After the station's Done check passes, run `python scripts/factory.py route --command factory-continue --continuing --after <SXX> --json`, with `<SXX>` the station that just ran. Go back to step 4 with its answer.
6. When the route says stop, end your turn with a short summary: the stations run, what each produced (issue, branch, PR link, and the per-AC verdict), and exactly what the human does next: review the PR, then merge it yourself (approval) or comment `/changes` and run `/factory-resume`.

Never merge anything and never push to the default branch (rule S1). If a station's stop condition is met, stop and report it; do not work around it.
