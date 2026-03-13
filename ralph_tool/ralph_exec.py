"""Codex execution and retry helpers for Ralph."""

from __future__ import annotations

import re
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from ralph_models import CommandResult, ExecResult, RalphError, RalphExecError, RetryAttempt
from ralph_usage import is_usage_limit_error, parse_limit_wait_seconds


def summarize_stderr(stderr_text: str, limit: int = 160) -> str:
    """Build a compact single-line stderr summary."""

    summary = " ".join(stderr_text.split())
    if len(summary) <= limit:
        return summary
    return summary[: limit - 3] + "..."


def classify_transient_failure(stderr_text: str, returncode: int) -> str | None:
    """Classify a transient execution failure."""

    if is_usage_limit_error(stderr_text):
        return "usage_limit"

    haystack = stderr_text.lower()
    network_patterns = [
        r"timed?\s*out",
        r"timeout",
        r"connection reset",
        r"connection refused",
        r"connection aborted",
        r"temporary failure",
        r"temporarily unavailable",
        r"broken pipe",
        r"network is unreachable",
        r"name or service not known",
        r"nodename nor servname provided",
        r"could not resolve",
        r"dns",
        r"eai_again",
        r"tls",
        r"ssl",
        r"socket hang up",
    ]
    if any(re.search(pattern, haystack) for pattern in network_patterns):
        return "network"
    if returncode < 0:
        return "subprocess_interrupted"
    return None


def compute_backoff_delay(attempt_number: int, initial_backoff_seconds: int, max_backoff_seconds: int) -> int:
    """Compute capped exponential backoff delay for the next retry."""

    initial = max(1, initial_backoff_seconds)
    maximum = max(initial, max_backoff_seconds)
    delay = initial * (2 ** max(0, attempt_number - 1))
    return min(delay, maximum)


def run_codex_exec(
    prompt: str,
    codex_args: list[str],
    *,
    state_dir: Path,
    last_message_file: Path,
    err_file: Path,
    ansi_color_reset: str,
    color_reset_interval_seconds: float,
    popen_module: object = subprocess,
    selectors_module: object = selectors,
    time_module: object = time,
    sys_module: object = sys,
) -> CommandResult:
    """Execute a codex run, stream output live, and capture stderr for retry logic."""

    state_dir.mkdir(parents=True, exist_ok=True)
    command = ["codex", "exec", *codex_args, "--output-last-message", str(last_message_file)]
    print("Ralph: starting codex exec...")

    stderr_parts: list[str] = []
    stdout_parts: list[str] = []
    stdout_buffer = ""
    stderr_buffer = ""
    process = None
    selector = None
    last_color_reset = time_module.monotonic()
    try:
        process = popen_module.Popen(
            command,
            stdin=popen_module.PIPE,
            stdout=popen_module.PIPE,
            stderr=popen_module.PIPE,
            text=True,
            bufsize=1,
        )
        if process.stdin is not None:
            process.stdin.write(prompt)
            process.stdin.close()

        selector = selectors_module.DefaultSelector()
        if process.stdout is not None:
            selector.register(process.stdout, selectors_module.EVENT_READ, "stdout")
        if process.stderr is not None:
            selector.register(process.stderr, selectors_module.EVENT_READ, "stderr")

        while selector.get_map():
            events = selector.select(timeout=0.2)
            for key, _ in events:
                chunk = key.fileobj.read(1)
                stream_name = key.data
                if chunk == "":
                    selector.unregister(key.fileobj)
                    continue
                if stream_name == "stdout":
                    sys_module.stdout.write(chunk)
                    sys_module.stdout.flush()
                    stdout_buffer += chunk
                    stdout_parts.append(chunk)
                    while "\n" in stdout_buffer:
                        _, stdout_buffer = stdout_buffer.split("\n", 1)
                else:
                    sys_module.stderr.write(chunk)
                    sys_module.stderr.flush()
                    stderr_buffer += chunk
                    while "\n" in stderr_buffer:
                        line, stderr_buffer = stderr_buffer.split("\n", 1)
                        stderr_parts.append(line + "\n")
            now = time_module.monotonic()
            if now - last_color_reset >= color_reset_interval_seconds:
                sys_module.stdout.write(ansi_color_reset)
                sys_module.stdout.flush()
                sys_module.stderr.write(ansi_color_reset)
                sys_module.stderr.flush()
                last_color_reset = now

        if stderr_buffer:
            stderr_parts.append(stderr_buffer)

        returncode = process.wait()
        stderr_text = "".join(stderr_parts)
        err_file.write_text(stderr_text, encoding="utf-8")
        return CommandResult(returncode=returncode, stderr=stderr_text, stdout="".join(stdout_parts))
    except KeyboardInterrupt as exc:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except popen_module.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        raise RalphError("Ralph interrupted by user during codex exec") from exc
    finally:
        sys_module.stdout.write(ansi_color_reset)
        sys_module.stdout.flush()
        sys_module.stderr.write(ansi_color_reset)
        sys_module.stderr.flush()
        if selector is not None:
            selector.close()


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
    run_codex_exec_fn: Callable[[str, list[str]], CommandResult],
    record_usage_segment_fn: Callable[[int, int], None],
    last_message_file: Path,
    time_module: object = time,
    classify_transient_failure_fn: Callable[[str, int], str | None] = classify_transient_failure,
    parse_limit_wait_seconds_fn: Callable[[str], int] = parse_limit_wait_seconds,
    compute_backoff_delay_fn: Callable[[int, int, int], int] = compute_backoff_delay,
    summarize_stderr_fn: Callable[[str, int], str] = summarize_stderr,
    warn_fn: Callable[[str], None] | None = None,
) -> ExecResult:
    """Run codex with transient retries and return execution details."""

    if warn_fn is None:
        warn_fn = lambda message: print(f"WARN: {message}", file=sys.stderr)

    retry_attempts: list[RetryAttempt] = []
    last_stderr = ""
    while True:
        refresh_fn()
        enforce_fn()
        started_epoch = int(time_module.time())
        result = run_codex_exec_fn(prompt, codex_args)
        ended_epoch = int(time_module.time())
        elapsed_seconds = max(0, ended_epoch - started_epoch)
        last_stderr = result.stderr

        if result.returncode == 0:
            record_usage_segment_fn(started_epoch, ended_epoch)
            refresh_fn()
            if not last_message_file.exists():
                raise RalphExecError(
                    "codex exec did not write last message file",
                    failure_reason="missing_last_message",
                    stderr=result.stderr,
                    retry_attempts=tuple(retry_attempts),
                    elapsed_seconds=elapsed_seconds,
                )
            message = last_message_file.read_text(encoding="utf-8", errors="ignore")
            return ExecResult(
                message=message,
                elapsed_seconds=elapsed_seconds,
                retry_attempts=tuple(retry_attempts),
                stderr=result.stderr,
                returncode=result.returncode,
            )

        refresh_fn()
        classification = classify_transient_failure_fn(result.stderr, result.returncode)
        if classification is not None and len(retry_attempts) < max_transient_retries:
            if classification == "usage_limit":
                wait_seconds = parse_limit_wait_seconds_fn(result.stderr)
                warn_fn(f"codex usage limit reached; sleeping {wait_seconds}s before retry")
            else:
                wait_seconds = compute_backoff_delay_fn(
                    len(retry_attempts) + 1,
                    initial_backoff_seconds,
                    max_backoff_seconds,
                )
                warn_fn(f"transient codex failure ({classification}); sleeping {wait_seconds}s before retry")
            retry_attempts.append(
                RetryAttempt(
                    attempt_number=len(retry_attempts) + 1,
                    classification=classification,
                    delay_seconds=wait_seconds,
                    stderr_summary=summarize_stderr_fn(result.stderr, 160),
                )
            )
            sleep_fn(wait_seconds)
            continue

        failure_reason = "codex_exec_failed"
        if classification is not None and len(retry_attempts) >= max_transient_retries:
            failure_reason = f"transient_retry_exhausted:{classification}"
        raise RalphExecError(
            "codex exec failed",
            failure_reason=failure_reason,
            stderr=last_stderr,
            retry_attempts=tuple(retry_attempts),
            elapsed_seconds=elapsed_seconds,
        )
