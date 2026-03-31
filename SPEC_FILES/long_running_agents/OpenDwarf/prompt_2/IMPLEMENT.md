Implement all milestones relevant to the voxel rebuild and minecraft syle map
Now implement the entire project end-to-end. Be liberal with your use of subagents.

Non-negotiable constraint

* Do not stop after a milestone to ask me questions or wait for confirmation.
* Proceed through every milestone in your plan at `PLAN.md` until the whole project is complete and fully validated.

Execution rules (follow strictly)

* Treat the plan at `PLAN.md` as the source of truth. If anything is ambiguous, make a reasonable decision and record it in `Documentation.md` before coding.
* Implement deliberately with small, reviewable commits. Avoid bundling unrelated changes.
  * You are to loop through each milestone, one at a time from `PLAN.md`
  * For each milestone, spawn a planner agent to plan the milestone, then spawn one or more implementer agents to implement the milestone (e.g. one implementer agent for writing tests, one implementer agent for writing code to pass tests, one implementer agent for fixing bugs, etc.), then spawn a reviewer agent to review the implementation. Continue in this loop until the reviewer agent considers the milestone to be implemented fully.

* After every milestone:

  * run verification commands (lint, typecheck, unit tests, snapshots, and any integration checks)
  * spawn a reviewer agent to check everything that was implemented to verify it passes the intent of the milestone and is playable
  * fix all failures immediately
  * add or update tests that cover the milestone’s core behavior
  * commit with a clear message that references the milestone name

* If a bug is discovered at any point:

  * write a failing test that reproduces it (using a subagent)
  * fix the bug
  * confirm the test now passes
  * record a short note in `Documentation.md` under “Implementation Notes”

Validation requirements

* Determinism is required for server behavior and the client.
* Everything that can be parallelized should be parallelized for performance reasons. Use as many cores as possible, use GPU whenever possible.
* All tests at every milestone must pass.
* Run verification tests with subagents.

Documentation requirements

* Create `Documentation.md` and keep it concise and useful. Update it as you implement so it matches reality.
* At the end, ensure `Documentation.md` includes:

  * what the app is
  * local setup and dev start
  * how to run tests, lint, typecheck
  * repo structure overview
  * troubleshooting section (top issues and fixes)
  * technical decisions you made throughout the process and the reasoning for your choices

Completion criteria (do not stop until all are true)

* All milestones in the plan are implemented and checked off.
* `Documentation.md` is accurate and complete.
* All features from all milestones are playable in-game from the client and visible to the player. All relevant features are implemented and surfaced in the client UI.
* All tests pass

Start now by implementing the next unimplemented UI related milestone in `PLAN.md`. Continue until everything (e.g. all UI milestones) is finished.
