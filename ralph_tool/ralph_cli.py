"""CLI parsing helpers for Ralph."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from ralph_models import LoopOptions, RalphError


def usage_text() -> str:
    """Return top-level usage text."""

    return """Ralph Wiggum for Codex

Usage:
  ralph loop [PROMPT...] [--prompt PATH] [--reviewer-prompt PATH] [--max-iterations N] [--completion-promise TEXT] [--weekly-limit-hours N|auto] [--weekly-quota-reserve N] [--no-weekly-pacing] [--max-review-cycles N] [--max-transient-retries N] [--initial-backoff-seconds N] [--max-backoff-seconds N] [--] [codex exec args]
  ralph cancel
  ralph status
  ralph help

Notes:
  - PROMPT is the user task request and can be omitted if provided via stdin.
  - --prompt overrides the implementer prompt template file for loop passes.
  - --reviewer-prompt overrides the reviewer prompt template file for outer review.
  - If positional PROMPT and stdin are absent, --prompt file contents are used as PROMPT text.
  - --weekly-quota-reserve preserves the last N% of weekly quota; 0 disables it.
  - --no-weekly-pacing disables the straight-line weekly pacing throttle.
  - Ralph writes structured run artifacts under .codex/runs/<run_id>/.
  - Use -- to pass flags directly to `codex exec` (e.g., -- --model o3).
"""


def loop_help_text() -> str:
    """Return loop subcommand help text."""

    return """ralph loop

Usage:
  ralph loop [PROMPT...] [--prompt PATH] [--reviewer-prompt PATH] [--max-iterations N] [--completion-promise TEXT] [--weekly-limit-hours N|auto] [--weekly-quota-reserve N] [--no-weekly-pacing] [--max-review-cycles N] [--max-transient-retries N] [--initial-backoff-seconds N] [--max-backoff-seconds N] [--] [codex exec args]

Options:
  --prompt PATH             Implementer prompt template file (default: SPEC_FILES/smart_agents/2_SPEC_IMPLEMENTER.md)
  --reviewer-prompt PATH    Reviewer prompt template file (default: SPEC_FILES/smart_agents/3_SPEC_REVIEWER.md)
  --max-iterations N        Max implementer iterations per inner loop (default: unlimited)
  --completion-promise TEXT Promise phrase expected from implementer and reviewer (default: DONE)
  --weekly-limit-hours N|auto
                            Weekly runtime budget in hours, or auto-detect from Codex telemetry
                            (default: $RALPH_WEEKLY_LIMIT_HOURS, or auto)
  --weekly-quota-reserve N  Preserve the last N percent of weekly quota; 0 disables it
                            (default: 0)
  --no-weekly-pacing        Disable straight-line weekly pacing throttle
  --max-review-cycles N     Max outer reviewer cycles before failing (default: 5; 0 means unlimited)
  --max-transient-retries N Max transient codex exec retries (default: 3)
  --initial-backoff-seconds N
                            Initial transient retry backoff in seconds (default: 2)
  --max-backoff-seconds N   Max transient retry backoff in seconds (default: 30)
  -h, --help                Show this help

Notes:
  - PROMPT is the user task request and can be provided via stdin if omitted.
  - If PROMPT and stdin are omitted, --prompt file contents become the PROMPT text.
  - Reviewer prompts include changed file paths from the latest implementer pass when git is available.
  - Ralph enforces a 5-hour runtime budget per 5-hour window and sleeps until reset.
  - Weekly pacing is auto-detected by default and can be overridden with a numeric hour budget.
  - Weekly quota reserve is a hard lower bound and does not replace normal weekly pacing unless --no-weekly-pacing is set.
  - Pass Codex flags after -- (e.g., -- --model o3 --sandbox workspace-write).
"""


def parse_loop_args(
    args: list[str],
    stdin_text: str | None,
    *,
    default_implementer_prompt_file: Path,
    default_reviewer_prompt_file: Path,
    default_max_transient_retries: int,
    default_initial_backoff_seconds: int,
    default_max_backoff_seconds: int,
    read_prompt_file: Callable[[Path], str],
) -> LoopOptions:
    """Parse loop command arguments without argparse to preserve passthrough behavior."""

    max_iterations = 0
    completion_promise = "DONE"
    weekly_limit_hours = os.environ.get("RALPH_WEEKLY_LIMIT_HOURS", "auto")
    weekly_quota_reserve_percent = 0
    no_weekly_pacing = False
    max_review_cycles = 5
    max_transient_retries = default_max_transient_retries
    initial_backoff_seconds = default_initial_backoff_seconds
    max_backoff_seconds = default_max_backoff_seconds
    implementer_prompt_path = str(default_implementer_prompt_file)
    reviewer_prompt_path = str(default_reviewer_prompt_file)
    prompt_option_path: str | None = None
    prompt_parts: list[str] = []
    codex_args: list[str] = []

    index = 0
    while index < len(args):
        token = args[index]
        if token in {"-h", "--help"}:
            print(loop_help_text())
            raise SystemExit(0)
        if token == "--":
            codex_args = args[index + 1 :]
            break
        if token == "--max-iterations":
            if index + 1 >= len(args):
                raise RalphError("--max-iterations requires a number")
            if not re.fullmatch(r"\d+", args[index + 1]):
                raise RalphError("--max-iterations must be a non-negative integer")
            max_iterations = int(args[index + 1])
            index += 2
            continue
        if token == "--completion-promise":
            if index + 1 >= len(args):
                raise RalphError("--completion-promise requires a value")
            completion_promise = args[index + 1]
            index += 2
            continue
        if token == "--prompt":
            if index + 1 >= len(args):
                raise RalphError("--prompt requires a file path")
            prompt_option_path = args[index + 1]
            implementer_prompt_path = prompt_option_path
            index += 2
            continue
        if token == "--reviewer-prompt":
            if index + 1 >= len(args):
                raise RalphError("--reviewer-prompt requires a file path")
            reviewer_prompt_path = args[index + 1]
            index += 2
            continue
        if token == "--weekly-limit-hours":
            if index + 1 >= len(args):
                raise RalphError("--weekly-limit-hours requires a number")
            candidate = args[index + 1]
            if not (candidate == "auto" or re.fullmatch(r"\d+", candidate)):
                raise RalphError("--weekly-limit-hours must be 'auto' or a non-negative integer")
            weekly_limit_hours = candidate
            index += 2
            continue
        if token == "--weekly-quota-reserve":
            if index + 1 >= len(args):
                raise RalphError("--weekly-quota-reserve requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--weekly-quota-reserve must be an integer between 0 and 100")
            reserve = int(candidate)
            if reserve > 100:
                raise RalphError("--weekly-quota-reserve must be between 0 and 100")
            weekly_quota_reserve_percent = reserve
            index += 2
            continue
        if token == "--no-weekly-pacing":
            no_weekly_pacing = True
            index += 1
            continue
        if token == "--max-review-cycles":
            if index + 1 >= len(args):
                raise RalphError("--max-review-cycles requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--max-review-cycles must be a non-negative integer")
            max_review_cycles = int(candidate)
            index += 2
            continue
        if token == "--max-transient-retries":
            if index + 1 >= len(args):
                raise RalphError("--max-transient-retries requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--max-transient-retries must be a non-negative integer")
            max_transient_retries = int(candidate)
            index += 2
            continue
        if token == "--initial-backoff-seconds":
            if index + 1 >= len(args):
                raise RalphError("--initial-backoff-seconds requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--initial-backoff-seconds must be a non-negative integer")
            initial_backoff_seconds = int(candidate)
            index += 2
            continue
        if token == "--max-backoff-seconds":
            if index + 1 >= len(args):
                raise RalphError("--max-backoff-seconds requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--max-backoff-seconds must be a non-negative integer")
            max_backoff_seconds = int(candidate)
            index += 2
            continue

        prompt_parts.append(token)
        index += 1

    prompt = " ".join(prompt_parts).strip()
    if not prompt and stdin_text is not None:
        prompt = stdin_text
    if not prompt and prompt_option_path is not None:
        prompt = read_prompt_file(Path(prompt_option_path))
        implementer_prompt_path = str(default_implementer_prompt_file)
    if not prompt:
        raise RalphError("No prompt provided (pass PROMPT args or pipe via stdin)")

    for arg in codex_args:
        if arg in {"--output-last-message", "-o"}:
            raise RalphError("Do not pass --output-last-message/-o; Ralph uses it internally")

    if not (weekly_limit_hours == "auto" or re.fullmatch(r"\d+", weekly_limit_hours)):
        raise RalphError("RALPH_WEEKLY_LIMIT_HOURS must be 'auto' or a non-negative integer")

    return LoopOptions(
        prompt=prompt,
        implementer_prompt_path=implementer_prompt_path,
        reviewer_prompt_path=reviewer_prompt_path,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
        weekly_limit_hours=weekly_limit_hours,
        weekly_quota_reserve_percent=weekly_quota_reserve_percent,
        no_weekly_pacing=no_weekly_pacing,
        max_review_cycles=max_review_cycles,
        max_transient_retries=max_transient_retries,
        initial_backoff_seconds=initial_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        codex_args=codex_args,
    )


def parse_stdin_if_needed(args: list[str], *, stdin: object) -> str | None:
    """Read stdin when prompt args are absent and stdin is piped."""

    if args:
        return None
    if stdin.isatty():
        return None
    return stdin.read()
