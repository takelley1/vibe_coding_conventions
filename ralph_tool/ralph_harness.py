#!/usr/bin/env python3
"""Ralph harness engine implemented in Python 3.12.

This module preserves the original CLI surface while adding reviewer-gated looping.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import random
import selectors
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.markdown import Markdown

import ralph_cli
import ralph_exec
import ralph_prompts
import ralph_usage
from ralph_models import (
    CommandResult,
    ExecResult,
    InnerLoopResult,
    LoopOptions,
    RalphError,
    RalphExecError,
    RetryAttempt,
    ReviewerResult,
    RunContext,
)

STATE_DIR = Path(".codex")
STATE_FILE = STATE_DIR / "ralph-loop.local.md"
LAST_MESSAGE_FILE = STATE_DIR / "ralph-last-message.txt"
USAGE_FILE = STATE_DIR / "ralph-usage.local.json"
ERR_FILE = STATE_DIR / "ralph-last-error.log"
RUNS_DIR = STATE_DIR / "runs"
PROJECT_ROOT = Path(os.environ.get("RALPH_REPO_ROOT", Path(__file__).resolve().parent.parent)).resolve()

DEFAULT_IMPLEMENTER_PROMPT_FILE = PROJECT_ROOT / "SPEC_FILES/smart_agents/2_SPEC_IMPLEMENTER.md"
DEFAULT_REVIEWER_PROMPT_FILE = PROJECT_ROOT / "SPEC_FILES/smart_agents/3_SPEC_REVIEWER.md"

CODEX_SESSIONS_DIR = Path(os.environ.get("CODEX_SESSIONS_DIR", str(Path.home() / ".codex/sessions")))

FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
DEFAULT_FIVE_HOUR_LIMIT_SECONDS = FIVE_HOUR_WINDOW_SECONDS
WEEK_WINDOW_SECONDS = 7 * 24 * 60 * 60
ANSI_COLOR_RESET = "\033[0m"
COLOR_RESET_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_TRANSIENT_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_SECONDS = 2
DEFAULT_MAX_BACKOFF_SECONDS = 30


def err(message: str) -> None:
    """Print an error message to stderr."""

    print(f"ERROR: {message}", file=sys.stderr)


def warn(message: str) -> None:
    """Print a warning message to stderr."""

    print(f"WARN: {message}", file=sys.stderr)


def require_cmd(command: str) -> None:
    """Validate that a command is available in PATH."""

    if not shutil_which(command):
        raise RalphError(f"Required command not found in PATH: {command}")


def shutil_which(command: str) -> str | None:
    """Small wrapper to support direct patching in tests."""

    from shutil import which

    return which(command)


def now_iso_utc() -> str:
    """Return current UTC timestamp in RFC3339-like format."""

    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_duration_hms(total_seconds: int) -> str:
    """Format seconds as hours, minutes, and seconds."""

    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"


def format_resume_time(now_epoch: int, wait_seconds: int) -> str:
    """Format the local planned resume time."""

    resume_at = dt.datetime.fromtimestamp(now_epoch + max(0, wait_seconds)).astimezone()
    return resume_at.strftime("%Y-%m-%d %I:%M:%S %p %Z")


def quote_frontmatter(value: object) -> str:
    """Serialize a scalar for YAML-like frontmatter."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse frontmatter and return values plus body."""

    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, content
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, content

    raw: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        raw[key.strip()] = value.strip()
    body = "\n".join(lines[end + 1 :])
    return raw, body


def decode_frontmatter_value(value: str) -> str:
    """Decode a frontmatter scalar value into display form."""

    if value in {"null", ""}:
        return ""
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def read_frontmatter_value(path: Path, key: str) -> str:
    """Read a single frontmatter key from the state file."""

    if not path.exists():
        return ""
    raw, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    return decode_frontmatter_value(raw.get(key, ""))


def write_state_file(
    *,
    prompt: str,
    max_iterations: int,
    max_review_cycles: int,
    weekly_quota_reserve_percent: int,
    no_weekly_pacing: bool,
    completion_promise: str,
    codex_args_serialized: str,
    run_id: str = "",
    artifact_dir: str = "",
) -> None:
    """Write loop state file with frontmatter."""

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "iteration": 1,
        "review_cycle": 1,
        "max_iterations": max_iterations,
        "max_review_cycles": max_review_cycles,
        "weekly_quota_reserve_percent": weekly_quota_reserve_percent,
        "no_weekly_pacing": no_weekly_pacing,
        "completion_promise": completion_promise or None,
        "codex_args": codex_args_serialized or None,
        "run_id": run_id or None,
        "artifact_dir": artifact_dir or None,
        "started_at": now_iso_utc(),
    }
    header_lines = ["---"]
    for key, value in payload.items():
        header_lines.append(f"{key}: {quote_frontmatter(value)}")
    header_lines.append("---")
    text = "\n".join(header_lines) + "\n\n" + prompt
    STATE_FILE.write_text(text, encoding="utf-8")


def update_state_value(key: str, value: int | str) -> None:
    """Update a single frontmatter key in state file."""

    if not STATE_FILE.exists():
        return
    raw, body = parse_frontmatter(STATE_FILE.read_text(encoding="utf-8"))
    raw[key] = quote_frontmatter(value)

    lines = ["---"]
    for existing_key, existing_value in raw.items():
        lines.append(f"{existing_key}: {existing_value}")
    lines.append("---")
    STATE_FILE.write_text("\n".join(lines) + "\n\n" + body, encoding="utf-8")


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    """Write JSON with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text_file(path: Path, text: str) -> None:
    """Write UTF-8 text with directory creation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def generate_run_id(now: dt.datetime | None = None) -> str:
    """Create a mostly-sortable unique run id."""

    current = now or dt.datetime.now(dt.timezone.utc)
    suffix = f"{os.getpid()}-{random.randint(1000, 9999)}"
    return current.strftime("%Y%m%dT%H%M%SZ") + "-" + suffix


def build_run_context() -> RunContext:
    """Create run directory and baseline git context."""

    run_id = generate_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    baseline_commit, baseline_note = detect_git_baseline(PROJECT_ROOT)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        baseline_commit=baseline_commit,
        baseline_note=baseline_note,
    )


def run_manifest_payload(
    *,
    options: LoopOptions,
    run_context: RunContext,
    current_review_cycle: int,
    final_outcome: str,
    failure_reason: str | None = None,
    ended_at: str | None = None,
) -> dict[str, object]:
    """Build top-level run manifest payload."""

    return {
        "artifact_dir": str(run_context.run_dir),
        "baseline_commit": run_context.baseline_commit,
        "baseline_note": run_context.baseline_note,
        "codex_args": options.codex_args,
        "completion_promise": options.completion_promise,
        "current_review_cycle": current_review_cycle,
        "ended_at": ended_at,
        "failure_reason": failure_reason,
        "final_outcome": final_outcome,
        "implementer_prompt_path": options.implementer_prompt_path,
        "initial_backoff_seconds": options.initial_backoff_seconds,
        "max_backoff_seconds": options.max_backoff_seconds,
        "max_iterations": options.max_iterations,
        "max_review_cycles": options.max_review_cycles,
        "max_transient_retries": options.max_transient_retries,
        "prompt": options.prompt,
        "reviewer_prompt_path": options.reviewer_prompt_path,
        "run_id": run_context.run_id,
        "started_at": read_frontmatter_value(STATE_FILE, "started_at"),
        "weekly_limit_hours": options.weekly_limit_hours,
        "weekly_quota_reserve_percent": options.weekly_quota_reserve_percent,
        "no_weekly_pacing": options.no_weekly_pacing,
    }


def write_run_manifest(
    *,
    options: LoopOptions,
    run_context: RunContext,
    current_review_cycle: int,
    final_outcome: str,
    failure_reason: str | None = None,
    ended_at: str | None = None,
) -> None:
    """Persist the run manifest."""

    write_json_file(
        run_context.run_dir / "run_manifest.json",
        run_manifest_payload(
            options=options,
            run_context=run_context,
            current_review_cycle=current_review_cycle,
            final_outcome=final_outcome,
            failure_reason=failure_reason,
            ended_at=ended_at,
        ),
    )


def detect_git_baseline(repo_root: Path) -> tuple[str | None, str | None]:
    """Detect baseline commit for diff-aware review."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return None, f"git unavailable: {exc}"

    if completed.returncode != 0:
        note = completed.stderr.strip() or "not a git worktree"
        return None, note
    return completed.stdout.strip(), None


def collect_changed_files(repo_root: Path, baseline_commit: str | None) -> tuple[list[str], str | None]:
    """Collect repo-relative changed file paths since baseline commit."""

    if not baseline_commit:
        return [], "diff unavailable: no baseline commit"
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", baseline_commit, "--"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [], f"git unavailable: {exc}"

    if completed.returncode != 0:
        note = completed.stderr.strip() or "git diff failed"
        return [], note
    changed_files = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return changed_files, None


def write_exec_artifacts(
    *,
    cycle_dir: Path,
    prefix: str,
    prompt_text: str,
    last_message_text: str,
    stderr_text: str,
    result_payload: dict[str, object],
) -> None:
    """Write per-cycle execution artifacts."""

    write_text_file(cycle_dir / f"{prefix}_prompt.txt", prompt_text)
    write_text_file(cycle_dir / f"{prefix}_last_message.txt", last_message_text)
    write_text_file(cycle_dir / f"{prefix}_stderr.log", stderr_text)
    write_json_file(cycle_dir / f"{prefix}_result.json", result_payload)


def run_codex_exec(prompt: str, codex_args: list[str]) -> CommandResult:
    """Execute a codex run, stream output live, and capture stderr for retry logic."""

    return ralph_exec.run_codex_exec(
        prompt,
        codex_args,
        state_dir=STATE_DIR,
        last_message_file=LAST_MESSAGE_FILE,
        err_file=ERR_FILE,
        ansi_color_reset=ANSI_COLOR_RESET,
        color_reset_interval_seconds=COLOR_RESET_INTERVAL_SECONDS,
        popen_module=subprocess,
        selectors_module=selectors,
        time_module=time,
        sys_module=sys,
    )


def run_with_retries(
    *,
    prompt: str,
    codex_args: list[str],
    refresh_fn: Callable[[], None],
    enforce_fn: Callable[[], None],
    sleep_fn: Callable[[int], None],
    max_transient_retries: int,
    initial_backoff_seconds: int,
    max_backoff_seconds: int,
) -> ExecResult:
    """Run codex with transient retries and return execution details."""

    return ralph_exec.run_with_retries(
        prompt=prompt,
        codex_args=codex_args,
        refresh_fn=refresh_fn,
        enforce_fn=enforce_fn,
        sleep_fn=sleep_fn,
        max_transient_retries=max_transient_retries,
        initial_backoff_seconds=initial_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        run_codex_exec_fn=run_codex_exec,
        record_usage_segment_fn=lambda start_epoch, end_epoch: ralph_usage.record_usage_segment(
            start_epoch,
            end_epoch,
            usage_file=USAGE_FILE,
            five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
            week_window_seconds=WEEK_WINDOW_SECONDS,
        ),
        last_message_file=LAST_MESSAGE_FILE,
        time_module=time,
        classify_transient_failure_fn=ralph_exec.classify_transient_failure,
        parse_limit_wait_seconds_fn=ralph_usage.parse_limit_wait_seconds,
        compute_backoff_delay_fn=ralph_exec.compute_backoff_delay,
        summarize_stderr_fn=ralph_exec.summarize_stderr,
        warn_fn=warn,
    )


def markdown_table(headers: list[str], values: list[str]) -> str:
    """Build a markdown table string."""

    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    row = "| " + " | ".join(values) + " |"
    return "\n".join([head, sep, row])


def print_inner_status_table(console: Console, *, review_cycle: int, result: InnerLoopResult, next_action: str) -> None:
    """Render inner-loop status as Rich markdown."""

    table = markdown_table(
        ["review_cycle", "iterations", "termination", "promise", "elapsed_s", "next_action"],
        [
            str(review_cycle),
            str(result.iterations_run),
            result.termination_reason,
            "matched" if result.promise_matched else "not_matched",
            str(result.elapsed_seconds),
            next_action,
        ],
    )
    console.print(Markdown("### Inner Loop Status\n\n" + table))


def print_outer_status_table(console: Console, *, review_cycle: int, result: ReviewerResult, decision: str) -> None:
    """Render reviewer status as Rich markdown."""

    table = markdown_table(
        ["review_cycle", "review_status", "promise", "decision", "elapsed_s"],
        [
            str(review_cycle),
            result.status,
            "matched" if result.promise_matched else "not_matched",
            decision,
            str(result.elapsed_seconds),
        ],
    )
    console.print(Markdown("### Outer Loop Status\n\n" + table))


def run_inner_loop(
    *,
    loop_prompt: str,
    codex_args: list[str],
    completion_promise: str,
    max_iterations: int,
    refresh_fn: Callable[[], None],
    enforce_fn: Callable[[], None],
    sleep_fn: Callable[[int], None],
    max_transient_retries: int,
    initial_backoff_seconds: int,
    max_backoff_seconds: int,
) -> InnerLoopResult:
    """Run implementer loop until completion promise or iteration cap."""

    iteration = 1
    total_elapsed = 0
    last_message_text = ""
    all_retry_attempts: list[RetryAttempt] = []
    last_stderr = ""

    while True:
        if not STATE_FILE.exists():
            raise SystemExit(0)

        print(f"Ralph iteration {iteration}")
        update_state_value("iteration", iteration)
        exec_result = run_with_retries(
            prompt=loop_prompt,
            codex_args=codex_args,
            refresh_fn=refresh_fn,
            enforce_fn=enforce_fn,
            sleep_fn=sleep_fn,
            max_transient_retries=max_transient_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )
        total_elapsed += exec_result.elapsed_seconds
        last_message_text = exec_result.message
        last_stderr = exec_result.stderr
        all_retry_attempts.extend(exec_result.retry_attempts)

        promise_text = ralph_prompts.extract_promise_text(exec_result.message)
        if promise_text == completion_promise:
            return InnerLoopResult(
                termination_reason="completion_promise",
                iterations_run=iteration,
                promise_matched=True,
                elapsed_seconds=total_elapsed,
                last_message_text=last_message_text,
                retry_attempts=tuple(all_retry_attempts),
                last_stderr=last_stderr,
            )

        if max_iterations > 0 and iteration >= max_iterations:
            return InnerLoopResult(
                termination_reason="max_iterations",
                iterations_run=iteration,
                promise_matched=False,
                elapsed_seconds=total_elapsed,
                last_message_text=last_message_text,
                retry_attempts=tuple(all_retry_attempts),
                last_stderr=last_stderr,
            )

        if not STATE_FILE.exists():
            raise SystemExit(0)

        iteration += 1


def run_reviewer_once(
    *,
    reviewer_prompt: str,
    codex_args: list[str],
    completion_promise: str,
    refresh_fn: Callable[[], None],
    enforce_fn: Callable[[], None],
    sleep_fn: Callable[[int], None],
    max_transient_retries: int,
    initial_backoff_seconds: int,
    max_backoff_seconds: int,
) -> ReviewerResult:
    """Run a single reviewer pass and parse mandatory status output."""

    exec_result = run_with_retries(
        prompt=reviewer_prompt,
        codex_args=codex_args,
        refresh_fn=refresh_fn,
        enforce_fn=enforce_fn,
        sleep_fn=sleep_fn,
        max_transient_retries=max_transient_retries,
        initial_backoff_seconds=initial_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )
    status = ralph_prompts.parse_review_status(exec_result.message)
    if status is None:
        raise RalphError("reviewer output missing 'Overall status' line")
    promise_text = ralph_prompts.extract_promise_text(exec_result.message)
    return ReviewerResult(
        status=status,
        promise_matched=promise_text == completion_promise,
        elapsed_seconds=exec_result.elapsed_seconds,
        last_message_text=exec_result.message,
        retry_attempts=exec_result.retry_attempts,
        last_stderr=exec_result.stderr,
    )


def run_loop(options: LoopOptions, *, console: Console, sleep_fn: Callable[[int], None] = time.sleep) -> int:
    """Execute full reviewer-gated loop flow."""

    require_cmd("codex")

    weekly_limit_seconds = -1 if options.weekly_limit_hours == "auto" else int(options.weekly_limit_hours) * 3600
    codex_args_serialized = shlex.join(options.codex_args) if options.codex_args else ""
    run_context = build_run_context()

    write_state_file(
        prompt=options.prompt,
        max_iterations=options.max_iterations,
        max_review_cycles=options.max_review_cycles,
        weekly_quota_reserve_percent=options.weekly_quota_reserve_percent,
        no_weekly_pacing=options.no_weekly_pacing,
        completion_promise=options.completion_promise,
        codex_args_serialized=codex_args_serialized,
        run_id=run_context.run_id,
        artifact_dir=str(run_context.run_dir),
    )
    write_run_manifest(
        options=options,
        run_context=run_context,
        current_review_cycle=1,
        final_outcome="running",
    )

    ralph_usage.ensure_usage_state(
        weekly_limit_seconds,
        state_dir=STATE_DIR,
        usage_file=USAGE_FILE,
        default_five_hour_limit_seconds=DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
        five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
        week_window_seconds=WEEK_WINDOW_SECONDS,
    )
    ralph_usage.refresh_codex_rate_limits(
        usage_file=USAGE_FILE,
        codex_sessions_dir=CODEX_SESSIONS_DIR,
        default_five_hour_limit_seconds=DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
        five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
        week_window_seconds=WEEK_WINDOW_SECONDS,
    )
    enforce_limits = lambda: ralph_usage.enforce_usage_limits(
        usage_file=USAGE_FILE,
        format_duration_hms=format_duration_hms,
        format_resume_time=format_resume_time,
        weekly_quota_reserve_percent=options.weekly_quota_reserve_percent,
        no_weekly_pacing=options.no_weekly_pacing,
    )

    implementer_agent_prompt = ralph_prompts.read_prompt_file(Path(options.implementer_prompt_path))
    reviewer_agent_prompt = ralph_prompts.read_prompt_file(Path(options.reviewer_prompt_path))
    implementer_prompt = ralph_prompts.build_implementer_prompt(
        implementer_agent_prompt,
        options.prompt,
        options.completion_promise,
    )

    review_cycle = 1
    try:
        while True:
            if not STATE_FILE.exists():
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome="cancelled",
                    ended_at=now_iso_utc(),
                )
                print("Ralph loop cancelled.")
                return 0
            update_state_value("review_cycle", review_cycle)
            cycle_dir = run_context.run_dir / f"review_cycle_{review_cycle:03d}"

            try:
                inner_result = run_inner_loop(
                    loop_prompt=implementer_prompt,
                    codex_args=options.codex_args,
                    completion_promise=options.completion_promise,
                    max_iterations=options.max_iterations,
                    refresh_fn=lambda: ralph_usage.refresh_codex_rate_limits(
                        usage_file=USAGE_FILE,
                        codex_sessions_dir=CODEX_SESSIONS_DIR,
                        default_five_hour_limit_seconds=DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
                        five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
                        week_window_seconds=WEEK_WINDOW_SECONDS,
                    ),
                    enforce_fn=enforce_limits,
                    sleep_fn=sleep_fn,
                    max_transient_retries=options.max_transient_retries,
                    initial_backoff_seconds=options.initial_backoff_seconds,
                    max_backoff_seconds=options.max_backoff_seconds,
                )
            except RalphExecError as exc:
                write_exec_artifacts(
                    cycle_dir=cycle_dir,
                    prefix="implementer",
                    prompt_text=implementer_prompt,
                    last_message_text="",
                    stderr_text=exc.stderr,
                    result_payload={
                        "elapsed_seconds": exc.elapsed_seconds,
                        "failure_reason": exc.failure_reason,
                        "retry_attempts": [dataclasses.asdict(item) for item in exc.retry_attempts],
                        "returncode": 1,
                        "termination_reason": "error",
                    },
                )
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome="failed",
                    failure_reason=exc.failure_reason,
                    ended_at=now_iso_utc(),
                )
                raise

            changed_files, changed_files_note = collect_changed_files(PROJECT_ROOT, run_context.baseline_commit)
            write_exec_artifacts(
                cycle_dir=cycle_dir,
                prefix="implementer",
                prompt_text=implementer_prompt,
                last_message_text=inner_result.last_message_text,
                stderr_text=inner_result.last_stderr,
                result_payload={
                    "changed_files": changed_files,
                    "changed_files_note": changed_files_note,
                    "elapsed_seconds": inner_result.elapsed_seconds,
                    "failure_reason": None,
                    "iterations_run": inner_result.iterations_run,
                    "promise_matched": inner_result.promise_matched,
                    "retry_attempts": [dataclasses.asdict(item) for item in inner_result.retry_attempts],
                    "returncode": 0,
                    "termination_reason": inner_result.termination_reason,
                },
            )
            print_inner_status_table(
                console,
                review_cycle=review_cycle,
                result=inner_result,
                next_action="run_reviewer",
            )

            if not STATE_FILE.exists():
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome="cancelled",
                    ended_at=now_iso_utc(),
                )
                print("Ralph loop cancelled.")
                return 0

            reviewer_prompt = ralph_prompts.build_reviewer_prompt(
                reviewer_agent_prompt,
                options.prompt,
                options.completion_promise,
                changed_files,
                changed_files_note,
            )
            try:
                reviewer_result = run_reviewer_once(
                    reviewer_prompt=reviewer_prompt,
                    codex_args=options.codex_args,
                    completion_promise=options.completion_promise,
                    refresh_fn=lambda: ralph_usage.refresh_codex_rate_limits(
                        usage_file=USAGE_FILE,
                        codex_sessions_dir=CODEX_SESSIONS_DIR,
                        default_five_hour_limit_seconds=DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
                        five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
                        week_window_seconds=WEEK_WINDOW_SECONDS,
                    ),
                    enforce_fn=enforce_limits,
                    sleep_fn=sleep_fn,
                    max_transient_retries=options.max_transient_retries,
                    initial_backoff_seconds=options.initial_backoff_seconds,
                    max_backoff_seconds=options.max_backoff_seconds,
                )
            except RalphExecError as exc:
                write_exec_artifacts(
                    cycle_dir=cycle_dir,
                    prefix="reviewer",
                    prompt_text=reviewer_prompt,
                    last_message_text="",
                    stderr_text=exc.stderr,
                    result_payload={
                        "decision": "fail",
                        "elapsed_seconds": exc.elapsed_seconds,
                        "failure_reason": exc.failure_reason,
                        "promise_matched": False,
                        "retry_attempts": [dataclasses.asdict(item) for item in exc.retry_attempts],
                        "status": "ERROR",
                    },
                )
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome="failed",
                    failure_reason=exc.failure_reason,
                    ended_at=now_iso_utc(),
                )
                raise
            except RalphError as exc:
                write_exec_artifacts(
                    cycle_dir=cycle_dir,
                    prefix="reviewer",
                    prompt_text=reviewer_prompt,
                    last_message_text=LAST_MESSAGE_FILE.read_text(encoding="utf-8", errors="ignore")
                    if LAST_MESSAGE_FILE.exists()
                    else "",
                    stderr_text=ERR_FILE.read_text(encoding="utf-8", errors="ignore") if ERR_FILE.exists() else "",
                    result_payload={
                        "decision": "fail",
                        "elapsed_seconds": 0,
                        "failure_reason": "reviewer_contract_error",
                        "promise_matched": False,
                        "retry_attempts": [],
                        "status": "ERROR",
                    },
                )
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome="failed",
                    failure_reason="reviewer_contract_error",
                    ended_at=now_iso_utc(),
                )
                raise

            decision = "retry_implementer"
            failure_reason = None
            final_outcome = "running"

            if reviewer_result.status in {"PASS", "PASS WITH NITS"} and reviewer_result.promise_matched:
                decision = "stop"
                final_outcome = "completed"
            elif reviewer_result.status in {"PASS", "PASS WITH NITS"} and not reviewer_result.promise_matched:
                decision = "fail"
                final_outcome = "failed"
                failure_reason = "reviewer_missing_promise"
            elif reviewer_result.status != "FAIL":
                decision = "fail"
                final_outcome = "failed"
                failure_reason = "unrecognized_reviewer_status"
            elif options.max_review_cycles > 0 and review_cycle >= options.max_review_cycles:
                decision = "max_review_cycles_reached"
                final_outcome = "failed"
                failure_reason = "max_review_cycles_reached"

            write_exec_artifacts(
                cycle_dir=cycle_dir,
                prefix="reviewer",
                prompt_text=reviewer_prompt,
                last_message_text=reviewer_result.last_message_text,
                stderr_text=reviewer_result.last_stderr,
                result_payload={
                    "decision": decision,
                    "elapsed_seconds": reviewer_result.elapsed_seconds,
                    "failure_reason": failure_reason,
                    "promise_matched": reviewer_result.promise_matched,
                    "retry_attempts": [dataclasses.asdict(item) for item in reviewer_result.retry_attempts],
                    "status": reviewer_result.status,
                },
            )

            if final_outcome == "completed":
                print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision=decision)
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome=final_outcome,
                    ended_at=now_iso_utc(),
                )
                print(f"Ralph loop complete: <promise>{options.completion_promise}</promise>")
                STATE_FILE.unlink(missing_ok=True)
                return 0

            if final_outcome == "failed":
                print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision=decision)
                write_run_manifest(
                    options=options,
                    run_context=run_context,
                    current_review_cycle=review_cycle,
                    final_outcome=final_outcome,
                    failure_reason=failure_reason,
                    ended_at=now_iso_utc(),
                )
                STATE_FILE.unlink(missing_ok=True)
                if failure_reason == "reviewer_missing_promise":
                    raise RalphError("reviewer satisfied status missing required completion promise tag")
                if failure_reason == "unrecognized_reviewer_status":
                    raise RalphError(f"unrecognized reviewer status: {reviewer_result.status}")
                raise RalphError(f"reviewer unsatisfied after {options.max_review_cycles} review cycles")

            print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision=decision)
            write_run_manifest(
                options=options,
                run_context=run_context,
                current_review_cycle=review_cycle,
                final_outcome=final_outcome,
            )
            review_cycle += 1
    finally:
        sys.stdout.write(ANSI_COLOR_RESET)
        sys.stdout.flush()
        sys.stderr.write(ANSI_COLOR_RESET)
        sys.stderr.flush()


def cmd_cancel() -> int:
    """Cancel active Ralph loop."""

    if not STATE_FILE.exists():
        print("No active Ralph loop found.")
        return 0

    iteration = read_frontmatter_value(STATE_FILE, "iteration")
    STATE_FILE.unlink(missing_ok=True)
    if iteration:
        print(f"Cancelled Ralph loop (was at iteration {iteration}).")
    else:
        print("Cancelled Ralph loop.")
    return 0


def usage_summary_lines() -> list[str]:
    """Return usage summary lines for status command."""

    try:
        state = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ["  usage_limits: unavailable"]

    now = int(time.time())
    epoch = int(state.get("epoch", now))
    five_window = int(state.get("five_hour_window_seconds", FIVE_HOUR_WINDOW_SECONDS))
    five_limit = int(state.get("five_hour_limit_seconds", DEFAULT_FIVE_HOUR_LIMIT_SECONDS))
    week_window = int(state.get("weekly_window_seconds", WEEK_WINDOW_SECONDS))
    week_limit = int(state.get("weekly_limit_seconds", 0))
    week_mode = str(state.get("weekly_limit_mode", "auto"))
    primary_reset = int(state.get("codex_primary_resets_at", 0))
    secondary_reset = int(state.get("codex_secondary_resets_at", 0))
    primary_pct = state.get("codex_primary_used_percent")
    secondary_pct = state.get("codex_secondary_used_percent")
    segments = state.get("segments", [])
    reserve_text = read_frontmatter_value(STATE_FILE, "weekly_quota_reserve_percent") if STATE_FILE.exists() else ""
    no_weekly_pacing_text = read_frontmatter_value(STATE_FILE, "no_weekly_pacing") if STATE_FILE.exists() else ""

    if primary_reset > now:
        five_end = primary_reset
        five_start = five_end - five_window
    else:
        five_period = (now - epoch) // five_window
        five_start = epoch + five_period * five_window
        five_end = five_start + five_window

    used_five = ralph_usage._overlap_sum(segments if isinstance(segments, list) else [], five_start, five_end)

    lines = [f"  5h_usage: {used_five}s / {five_limit}s"]
    if isinstance(primary_pct, (int, float)):
        lines.append(f"  5h_usage_percent: {float(primary_pct):.1f}%")

    if week_limit > 0:
        weekly_metrics = ralph_usage.weekly_usage_metrics(state, now, week_window_seconds=WEEK_WINDOW_SECONDS)
        used_week = int(weekly_metrics["used_week"])
        lines.append(f"  weekly_usage: {used_week}s / {week_limit}s")
        lines.append(f"  weekly_mode: {week_mode}")
    elif week_mode == "auto":
        lines.append("  weekly_usage: auto-detecting")
    else:
        lines.append("  weekly_usage: disabled")

    if isinstance(secondary_pct, (int, float)):
        lines.append(f"  weekly_usage_percent: {float(secondary_pct):.1f}%")

    weekly_metrics = ralph_usage.weekly_usage_metrics(state, now, week_window_seconds=WEEK_WINDOW_SECONDS)
    remaining_percent = weekly_metrics["remaining_percent"]
    remaining_source = str(weekly_metrics["remaining_percent_source"])
    if isinstance(remaining_percent, (int, float)):
        label = "weekly_remaining_percent"
        if remaining_source:
            label += f" ({remaining_source})"
        lines.append(f"  {label}: {float(remaining_percent):.1f}%")
    if reserve_text:
        lines.append(f"  weekly_quota_reserve_percent: {reserve_text}")
    if no_weekly_pacing_text:
        lines.append(f"  no_weekly_pacing: {no_weekly_pacing_text}")

    return lines


def cmd_status() -> int:
    """Show current loop status."""

    if not STATE_FILE.exists():
        print("No active Ralph loop found.")
        return 0
    if USAGE_FILE.exists():
        ralph_usage.refresh_codex_rate_limits(
            usage_file=USAGE_FILE,
            codex_sessions_dir=CODEX_SESSIONS_DIR,
            default_five_hour_limit_seconds=DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
            five_hour_window_seconds=FIVE_HOUR_WINDOW_SECONDS,
            week_window_seconds=WEEK_WINDOW_SECONDS,
        )

    iteration = read_frontmatter_value(STATE_FILE, "iteration")
    review_cycle = read_frontmatter_value(STATE_FILE, "review_cycle")
    max_iterations = read_frontmatter_value(STATE_FILE, "max_iterations")
    max_review_cycles = read_frontmatter_value(STATE_FILE, "max_review_cycles")
    weekly_quota_reserve_percent = read_frontmatter_value(STATE_FILE, "weekly_quota_reserve_percent")
    no_weekly_pacing = read_frontmatter_value(STATE_FILE, "no_weekly_pacing")
    completion_promise = read_frontmatter_value(STATE_FILE, "completion_promise")
    started_at = read_frontmatter_value(STATE_FILE, "started_at")
    codex_args = read_frontmatter_value(STATE_FILE, "codex_args")
    run_id = read_frontmatter_value(STATE_FILE, "run_id")
    artifact_dir = read_frontmatter_value(STATE_FILE, "artifact_dir")

    print("Ralph loop active")
    print(f"  review_cycle: {review_cycle or '?'}")
    print(f"  iteration: {iteration or '?'}")
    print(f"  max_review_cycles: {max_review_cycles or '?'}")
    print(f"  max_iterations: {max_iterations or '?'}")
    print(f"  weekly_quota_reserve_percent: {weekly_quota_reserve_percent or '0'}")
    print(f"  no_weekly_pacing: {no_weekly_pacing or 'false'}")
    print(f"  completion_promise: {completion_promise or 'none'}")
    print(f"  started_at: {started_at or '?'}")
    print(f"  run_id: {run_id or '?'}")
    print(f"  artifact_dir: {artifact_dir or '?'}")
    if codex_args:
        print(f"  codex_args: {codex_args}")

    if USAGE_FILE.exists():
        for line in usage_summary_lines():
            print(line)

    return 0


def cmd_loop(args: list[str], *, console: Console) -> int:
    """Handle the loop subcommand."""

    stdin_text = ralph_cli.parse_stdin_if_needed(args, stdin=sys.stdin)
    options = ralph_cli.parse_loop_args(
        args,
        stdin_text,
        default_implementer_prompt_file=DEFAULT_IMPLEMENTER_PROMPT_FILE,
        default_reviewer_prompt_file=DEFAULT_REVIEWER_PROMPT_FILE,
        default_max_transient_retries=DEFAULT_MAX_TRANSIENT_RETRIES,
        default_initial_backoff_seconds=DEFAULT_INITIAL_BACKOFF_SECONDS,
        default_max_backoff_seconds=DEFAULT_MAX_BACKOFF_SECONDS,
        read_prompt_file=ralph_prompts.read_prompt_file,
    )
    return run_loop(options, console=console)


def main(argv: list[str] | None = None) -> int:
    """Program entrypoint."""

    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "help"
    rest = args[1:] if args else []

    if command in {"help", "-h", "--help"}:
        print(ralph_cli.usage_text())
        return 0

    if command in {"loop", "start"}:
        return cmd_loop(rest, console=Console())

    if command in {"cancel", "stop"}:
        return cmd_cancel()

    if command == "status":
        return cmd_status()

    err(f"Unknown command: {command}")
    print(ralph_cli.usage_text())
    return 1
