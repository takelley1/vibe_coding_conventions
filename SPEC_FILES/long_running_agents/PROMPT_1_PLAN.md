##########
Run this prompt in /plan mode. This will give a spec for a long-running agent. Then after that run the PROMPT_2_IMPLEMENT.md prompt.
Fill in everything that has $VAR_NAME to customize this prompt.
##########














You are Codex acting as a senior staff engineer and tech lead. Build a polished $APP

Core goals

* This must be impressive to non-engineers in a live demo ($FEATURES)
* This must also be impressive to engineers (clean architecture, strong types, tests, $FEATURES).
* You will run for hours: plan first, then implement milestone by milestone. Do not skip the planning phase.

Hard requirements

* Local run experience: one command to start (document exact commands). Must run on macOS with $TECH_STACK
* Tech stack: $TECH_STACK. Use only open source dependencies.
* Runs fully locally: no external hosted services.
* Every milestone must include verification steps (tests, lint, typecheck, deterministic snapshots).
* $FEATURE

Deliverable
A repo that contains:

* A working implementing the features below
* A short architecture doc explaining the data model, rendering pipeline, and $FEATURES
* Scripts: dev, build, test, lint, typecheck, export
* A `Documentation.md` file capturing the full implementation plan and ongoing notes

Product spec (build this)

A) $FEATURE_1 - use ChatGPT to create this list

* $DESCRIPTION

B) $FEATURE_2 - use ChatGPT to create this list

* $DESCRIPTION

Process requirements (follow strictly)

1. PLANNING FIRST (write this file before coding anything):

   * Plan with a milestone plan (at least 14 milestones) that will take hours.
   * For each milestone include: scope, key files/modules, acceptance criteria, and commands to verify.
   * Include a “risk register” with top technical risks and mitigation plans.
   * Include an “architecture overview” section describing:
     * data model
     * overall features
     * client-server approach
     * operations model
     * $FEATURE

2. SCAFFOLD SECOND:

   * $SCAFFOLD

3. IMPLEMENT THIRD:

   * Implement one milestone at a time.
   * After each milestone: run verification commands, fix issues, commit with a clear message.
   * Keep diffs reviewable and avoid giant unstructured changes.

4. UX polish throughout:

   * Clean, modern UI with subtle animations.

5. If you hit complexity choices:

   * Prefer correctness and determinism over extra features.
   * Document tradeoffs and decisions in `Documentation.md` as you go.

Start now.
First, create the plan with the complete plan, risk register, demo script, and architecture overview.
