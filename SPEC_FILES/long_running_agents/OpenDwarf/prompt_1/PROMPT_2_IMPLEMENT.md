##########
Run this AFTER running the PROMPT_1_PLAN.md prompt. This will tell the long-running agent to implement the plan.
Fill in everything that has $VAR_NAME to customize this prompt.
##########










Now implement the entire project end-to-end.

Non-negotiable constraint

* Do not stop after a milestone to ask me questions or wait for confirmation.
* Proceed through every milestone in your plan until the whole project is complete and fully validated.

Execution rules (follow strictly)

* Treat the plan as the source of truth. If anything is ambiguous, make a reasonable decision and record it in `Documentation.md` before coding.
* Implement deliberately with small, reviewable commits. Avoid bundling unrelated changes.

* After every milestone:

  * run verification commands (lint, typecheck, unit tests, snapshots, and any integration checks)
  * fix all failures immediately
  * add or update tests that cover the milestone’s core behavior
  * commit with a clear message that references the milestone name

* If a bug is discovered at any point:

  * write a failing test that reproduces it
  * fix the bug
  * confirm the test now passes
  * record a short note in `Documentation.md` under “Implementation Notes”

Validation requirements

* Determinism is required for server behavior and the client.

Documentation requirements

* Create `Documentation.md` and keep it concise and useful. Update it as you implement so it matches reality.
* At the end, ensure `Documentation.md` includes:

  * what the app is
  * local setup and dev start
  * how to run tests, lint, typecheck
  * repo structure overview
  * troubleshooting section (top issues and fixes)
  * $FEATURE

Completion criteria (do not stop until all are true)

* All milestones in the plan are implemented and checked off.
* `Documentation.md` is accurate and complete.
* The full vertical slice is playable and all features are implemented and surfaced in the client UI.

Start now by implementing the plan and beginning Milestone 1. Continue until everything is finished.
