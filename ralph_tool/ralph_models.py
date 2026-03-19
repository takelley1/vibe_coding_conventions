"""Shared Ralph dataclasses and exceptions."""

from __future__ import annotations

import dataclasses
from pathlib import Path


class RalphError(RuntimeError):
    """Raised when command execution should stop with a non-zero exit."""


@dataclasses.dataclass(frozen=True)
class LoopOptions:
    """Parsed options for the loop command."""

    prompt: str
    implementer_prompt_path: str
    reviewer_prompt_path: str
    max_iterations: int
    completion_promise: str
    weekly_limit_hours: str
    weekly_quota_reserve_percent: int
    max_review_cycles: int
    max_transient_retries: int
    initial_backoff_seconds: int
    max_backoff_seconds: int
    codex_args: list[str]
    no_weekly_pacing: bool = False


@dataclasses.dataclass(frozen=True)
class CommandResult:
    """Result from a command runner invocation."""

    returncode: int
    stderr: str
    stdout: str = ""


@dataclasses.dataclass(frozen=True)
class RetryAttempt:
    """Transient retry metadata for a single retry attempt."""

    attempt_number: int
    classification: str
    delay_seconds: int
    stderr_summary: str


@dataclasses.dataclass(frozen=True)
class ExecResult:
    """Successful execution details for a codex invocation."""

    message: str
    elapsed_seconds: int
    retry_attempts: tuple[RetryAttempt, ...] = ()
    stderr: str = ""
    returncode: int = 0


@dataclasses.dataclass(frozen=True)
class RunContext:
    """Per-run artifact and git baseline context."""

    run_id: str
    run_dir: Path
    baseline_commit: str | None
    baseline_note: str | None


class RalphExecError(RalphError):
    """Execution failure with artifact-friendly metadata."""

    def __init__(
        self,
        message: str,
        *,
        failure_reason: str,
        stderr: str = "",
        retry_attempts: tuple[RetryAttempt, ...] = (),
        elapsed_seconds: int = 0,
    ) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason
        self.stderr = stderr
        self.retry_attempts = retry_attempts
        self.elapsed_seconds = elapsed_seconds


@dataclasses.dataclass(frozen=True)
class InnerLoopResult:
    """Summary for an implementer inner loop."""

    termination_reason: str
    iterations_run: int
    promise_matched: bool
    elapsed_seconds: int
    last_message_text: str = ""
    retry_attempts: tuple[RetryAttempt, ...] = ()
    last_stderr: str = ""


@dataclasses.dataclass(frozen=True)
class ReviewerResult:
    """Summary for a reviewer pass."""

    status: str
    promise_matched: bool
    elapsed_seconds: int
    last_message_text: str = ""
    retry_attempts: tuple[RetryAttempt, ...] = ()
    last_stderr: str = ""
