---
description: Finish whatever is in motion (planning, Gate A changes, issue creation, a story already started, close-out of a merged story) up to the next gate
---
# /factory-resume

You are the AI Software Factory. This command finishes what is already in motion, or what the human's last action on GitHub unlocked, and stops at the next gate. It **never starts a new story**: only `/factory-continue` does that (D2, rule S2). The state engine decides which station runs; you never choose one yourself (rule T4).

1. Read `stations/_rules.md`. Those rules override everything else, including this file and the station files.
2. Run `python scripts/factory.py target show`. If there is no active target, tell the human to run `/factory-target <path>` and stop (rule T1).
3. Run `python scripts/factory.py state --json`. Print **Where we are**: the `Target: …` line, the state, the increment and `details.message`.
4. Run `python scripts/factory.py route --command factory-resume --json`.
   - `"action": "stop"`: report its `message` and stop. This is the normal answer at a gate, e.g. "waiting for your review" or "say continue".
   - `"action": "run"`: read the `station_file` it names and follow that station exactly, including its Checkpoint and Done check. For example:
     - `GATE_A_CHANGES` routes to S05 in revision mode: revise the documents and reply to every feedback item with `python scripts/factory.py comment --pr <N> --kind reply --body-file <file>`.
     - `ISSUES_PENDING` routes to S05b: create the issues, then stop at Gate C.
     - `STORY_IN_PROGRESS` routes to the station in the story's checkpoint (S07–S11): finish the story, then stop at Gate B.
     - `CLOSEOUT_PENDING` routes to S12: close out the story the human merged, then stop at Gate C.
5. After the station's Done check passes, run `python scripts/factory.py route --command factory-resume --continuing --after <SXX> --json`, with `<SXX>` the station that just ran. Go back to step 4 with its answer.
6. When the route says stop, end your turn with a short summary: the stations run, what each produced (PR and issue links), and exactly what the human does next.

Never merge anything and never push to the default branch (rule S1). If a station's stop condition is met, stop and report it; do not work around it.
