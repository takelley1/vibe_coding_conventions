# AGENTS.md

## Repository Identity
- Project: OpenDwarf (browser-based dwarf-fortress-style simulation).

## Subagents
- If you spawn subagents, always use the latest GPT model available

## Cross-Cutting Priorities
- Performance and testability are paramount in every task.
- Every changed production file (Rust/TypeScript/WASM-facing logic) MUST be objectively testable.
- Coverage for written production code MUST remain at least 95%. This includes both server and client code coverage.
- Total workspace code coverage at or above 95% is a hard validity requirement for every change.
- If total code coverage is below 95%, the change is not valid and must not be treated as complete.
- Source files MUST stay under 2000 lines. Split files proactively before they approach the limit.

## Technical Constraints
- Languages:
  - Rust: simulation core, authoritative server, protocol, bench/perf tests.
  - TypeScript: web client render/UI/network.
- Runtime/platform:
  - Desktop Chrome/Firefox baseline.
- WASM threading:
  - Cross-origin isolation (COOP/COEP compatible configuration) is required.

## Rust Style Guide (Mandatory)
- Formatting/lint:
  - `cargo fmt --all` and `cargo clippy --workspace --all-targets --all-features -- -D warnings` are required gates.
- API and type design:
  - Prefer explicit domain types/enums over magic numbers or free-form strings.
  - Keep modules cohesive and avoid god-modules; split by capability boundaries.
  - Prefer `Result<T, E>` with typed error enums over panics for recoverable failures.
- Determinism/perf-sensitive code:
  - Avoid hidden non-determinism (`HashMap` iteration assumptions, wall-clock dependence, unordered side effects).
  - Document tick/budget assumptions in code where behavior depends on them.
- Rust doc-comment formatting:
  - Use `///` for item docs and `//!` for module-level docs on all production code files.
  - All public exports and non-trivial internal functions MUST carry doc comments in the mandated format.
  - First line MUST be a short imperative summary sentence ending with a period.
  - Add `# Arguments`, `# Returns`, and `# Errors` sections where applicable.
  - Include deterministic/performance invariants in doc comments for simulation/server hot-path APIs.
  - Keep doc examples minimal and compile-valid when included.

## TypeScript Style Guide (Mandatory)
- Formatting/lint:
  - `npm --prefix web run lint`, `npm --prefix web run typecheck`, and `npm --prefix web run format:check` are required gates.
- Type-system usage:
  - Prefer strict, explicit types and discriminated unions over `any`/implicit shape assumptions.
  - Do not bypass type safety with unchecked casts unless justified and documented.
  - Keep pure logic in small testable functions and isolate side effects at boundaries.
- Browser/e2e expectations:
  - Acceptance tests must validate production behavior, not synthetic inline page mocks.
  - Performance-sensitive code paths must expose measurable assertions, not placeholder pass checks.
- TS/JSDoc formatting:
  - Public exports and non-trivial logic MUST use JSDoc `/** ... */`, including internal functions in production files when the implementation is not self-explanatory.
  - First line MUST be a concise summary sentence ending with a period.
  - Use `@param`, `@returns`, and `@throws` when applicable.
  - Document units/constraints for performance-relevant values (for example ms, ticks, FPS).
  - Keep comments factual and implementation-specific; no placeholder TODO docstrings in completed leaves.

## Mandatory Red/Green TDD Workflow
All implementation work MUST follow red/green/refactor:

1. Red
- Write or update the test for the active requirement.
- Run the test to verify it fails.

2. Green
- Implement the smallest possible change to pass the failing test.
- Re-run the same tests until passing.
- Avoid unrelated behavior changes.

3. Refactor
- Refactor for clarity/performance without changing behavior.
- Re-run the tests and local gates.

## TDD Guardrails
- If scaffolding is missing, create the minimal failing harness test first.
- Never remove a test just to pass gates.
- If a bug is mentioned, write a regression test that reproduces it before changing production code.

## Global Quality Gates
- Tests:
  - `cargo test --workspace && npm --prefix web run test:unit && npm --prefix web run test:e2e`
- Lint:
  - `cargo clippy --workspace --all-targets --all-features -- -D warnings && npm --prefix web run lint`
- Typecheck:
  - `npm --prefix web run typecheck`
- Formatting: `./scripts/format.sh`
- Coverage: `./scripts/coverage_client.sh && ./scripts/coverage_server.sh`
- Testability Trace:
  - `python3 scripts/verify_testability_map.py --repo-root /home/akelley/OpenDwarf --map /home/akelley/OpenDwarf/testing/testability_map.yaml`
- Performance:
  - `cargo test -p core_sim --test perf_tick_budget && cargo test -p server --test net_tick_budget && cargo test -p core_sim --test path_budget && cargo test -p core_sim --test mining_scale_budget && cargo test -p core_sim --test labor_scale_budget && cargo test -p core_sim --test combat_scale_budget && npm --prefix web run test:e2e -- --grep "@perf-smoke" --project=chromium --project=firefox`
- Convenience Scripts:
  - `bash scripts/install_deps.sh --help && bash scripts/lint.sh --help && bash scripts/format.sh --help && bash scripts/test.sh --help && bash scripts/coverage_server.sh --help && bash scripts/coverage_client.sh --help && bash scripts/benchmark.sh --help && bash scripts/perf.sh --help && bash scripts/run_server.sh --help`
- Commit Evidence:
  - `git rev-parse --verify HEAD && git show --name-only --pretty='' HEAD`

## Commit and Branch Expectations
- Use the main branch.
- Commit style should remain `milestone: short summary`.
- Every commit subject MUST include the milestone number it belongs to, for example `milestone 137: short summary`.
- The commit body should be a longer description in paragraph form discussing in more detail what the change was. Keep it at most 3 sentences.
- Keep commits scoped to the active task.
- Commit after every meaningful change before moving to the next task.
- Record commit evidence using:
  - `git rev-parse --verify HEAD`
  - `git show --name-only --pretty='' HEAD`
- Right before you finish your task and return control to the user, run `scripts/notify.sh`. This is a notification script that tells the user that you are finished and ready to receive commands again.

## Browser Tooling
- Use the Playwright CLI wrapper at `/home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh` for real browser interaction.
- If the wrapper is not executable, invoke it through `bash`.
- Use `open`, `snapshot`, `click`, `mousemove`, `mousedown`, `mouseup`, `eval`, `console`, `network`, and `screenshot` for iterative client debugging.
- Use `screenshot` plus `functions.view_image` to inspect the actual rendered game before changing code again.
- Keep Playwright session artifacts in `.playwright-cli/` and repo-side browser artifacts under `output/playwright/` when a task needs committed evidence.
- Prefer direct browser interaction against the live app when validating click, drag, selection, camera, reconnect, or animation behavior.
- Example CLI flows:
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh open 'http://127.0.0.1:4173/?transport=live'`
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh snapshot`
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh click e9`
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh screenshot`
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh eval 'document.body.getAttribute("data-app-entrypoint-ready")'`
  - `bash /home/akelley/.codex/skills/playwright/scripts/playwright_cli.sh open 'http://127.0.0.1:4173/?transport=live' --headed`

## Local Debugging Notes
- When running headed browser checks from tmux or another non-graphical shell, explicitly set `DISPLAY=:1` if a desktop X server is already available.
- If headed Playwright still fails to attach to the desktop session, fall back to `xvfb-run -a` rather than silently switching to headless mode.
- The live app path for browser validation is usually `http://127.0.0.1:4173/?transport=live`; the Rust server usually listens on `127.0.0.1:4100`.

## Skill Routing For OpenDwarf
- When routing work to a local skill in plans, notes, or handoffs, always use the `$`-prefixed skill name.
- Use `$playwright` for real-browser validation that must exercise the actual app rather than inline mocks: session boot, multiplayer UI, reconnect flows, browser regression reproduction, screenshot capture, trace collection, and acceptance checks tied to production browser behavior. Keep artifacts under `output/playwright/`.
- These skills supplement OpenDwarf's spec-first workflow. They do not replace the active task's red/green/refactor commands, required Evidence blocks, coverage thresholds, browser/performance gates, or the exact commands listed in `SPEC.md`.

## General
- This project is critical -- please focus!
- Don't be obsequious, sycophantic, excessively apologetic, overly verbose, or overly polite.
- Don't say things like "Certainly!", "Absolutely!", "Of course!", "Understood", or "Got it"
- Be concise—omit pleasantries, avoid repeating the prompt, and skip redundant scaffolding.

## Code Style
- Always prioritize the simplest solution over complexity.
- Code must be easy to read and understand.
- Ensure all lines DO NOT have trailing whitespace.
- Keep code as simple as possible. Avoid unnecessary complexity.
- Follow DRY and YAGNI coding principles.
- Follow SOLID principles (e.g. single responsibility, dependency inversion) where applicable.
- DO NOT over-engineer code!
- Never duplicate code.
- Never write placeholder code, empty asserts that are always true, trivial tests, or otherwise useless non-production code.
- Code files should be kept under 2000 lines.

## Variables
- Use meaningful names for variables, functions, etc. Names should reveal intent. Don't use short names for variables.

## Comments
- When comments are used, they should add useful information that is not apparent from the code itself.

## Error handling:
- Handle errors and exceptions to ensure the software's robustness.

## Functions:
- Functions should be small and do one thing. They should not exceed about 20 lines.
- Function names should describe what they do.
- Prefer fewer arguments in functions. Aim for less than about 5.

## Security:
- Follow input sanitization, parameterized queries, and avoiding hardcoded secrets.

## For bash/zsh/fish code only:
- Follow all shellcheck conventions and rules.
- Handle errors gracefully.
- Use `/usr/bin/env bash` in the shebang line.
- Use `set -euo pipefail`.
- Use `[[ ]]` instead of `[ ]`.
- Use `"$()"` instead of `` ``.
- Use `"${VAR}"` instead of `"$VAR"`.
- Don't use arrays unless absolutely necessary.
- Use `printf` instead of `echo`.
- Encapsulate functionality in functions.
- Output to JSON by default rather than plaintext.

## Examples

<Shell>
    - Correct shebang example:
        <example>
        #!/usr/bin/env bash
        </example>

    - Correct shell options example:
        <example>
        set -euo pipefail
        </example>

    - Correct if-statement formatting example:
        <example>
        if [[ -z "${URL}" ]]; then
          exit 1
        fi
        </example>

    - Correct subshell example:
        <example>
        STATUS_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${URL}")"
        </example>
</Shell>

</instructions>
