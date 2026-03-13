"""Codex execution and retry helpers for Ralph."""

from __future__ import annotations

import dataclasses
import re
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from ralph_models import CommandResult, ExecResult, RalphError, RalphExecError, RetryAttempt
from ralph_usage import is_usage_limit_error, parse_limit_wait_seconds

ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_CYAN = "\033[36m"
ANSI_DIM = "\033[2m"
DIFF_FENCE_RE = re.compile(r"^\s*```(?:diff|patch)\s*$")


@dataclasses.dataclass
class _DiffColorState:
    """Track whether the current stream is inside a diff block."""

    in_diff_fence: bool = False
    in_raw_diff: bool = False


def _is_raw_diff_header(line: str) -> bool:
    """Return True when a line clearly starts a unified diff block."""

    return line.startswith(("diff --git ", "--- ", "+++ ", "@@ "))


def _looks_like_raw_diff_line(line: str) -> bool:
    """Return True for lines that belong to unified diff output."""

    if line == "":
        return True
    prefixes = (
        "diff --git ",
        "index ",
        "--- ",
        "+++ ",
        "@@ ",
        "new file mode ",
        "deleted file mode ",
        "similarity index ",
        "rename from ",
        "rename to ",
        "old mode ",
        "new mode ",
        "Binary files ",
        "\\ No newline at end of file",
        "+",
        "-",
        " ",
    )
    return line.startswith(prefixes)


def _diff_line_ansi(line: str) -> str | None:
    """Choose an ANSI color for a single diff line."""

    if "\033[" in line:
        return None
    if line.startswith("diff --git "):
        return ANSI_CYAN
    if line.startswith(("index ", "new file mode ", "deleted file mode ", "similarity index ", "rename from ", "rename to ", "old mode ", "new mode ", "Binary files ", "\\ No newline at end of file")):
        return ANSI_DIM
    if line.startswith("--- "):
        return ANSI_RED
    if line.startswith("+++ "):
        return ANSI_GREEN
    if line.startswith("@@ "):
        return ANSI_CYAN
    if line.startswith("+") and not line.startswith("+++ "):
        return ANSI_GREEN
    if line.startswith("-") and not line.startswith("--- "):
        return ANSI_RED
    return None


def _render_diff_line(line: str, *, state: _DiffColorState, ansi_color_reset: str) -> str:
    """Render a line with ANSI styling when it belongs to a diff block."""

    stripped = line.strip()
    if state.in_diff_fence:
        if stripped == "```":
            state.in_diff_fence = False
            return line
        ansi = _diff_line_ansi(line)
        return f"{ansi}{line}{ansi_color_reset}" if ansi else line

    if DIFF_FENCE_RE.match(line):
        state.in_diff_fence = True
        return line

    if _is_raw_diff_header(line):
        state.in_raw_diff = True
    elif state.in_raw_diff and not _looks_like_raw_diff_line(line):
        state.in_raw_diff = False

    if not state.in_raw_diff:
        return line

    ansi = _diff_line_ansi(line)
    return f"{ansi}{line}{ansi_color_reset}" if ansi else line


def _write_rendered_chunk(
    chunk: str,
    *,
    buffer: str,
    state: _DiffColorState,
    write_fn: Callable[[str], None],
    flush_fn: Callable[[], None],
    ansi_color_reset: str,
    capture_line_fn: Callable[[str], None] | None = None,
) -> str:
    """Write a chunk to a stream, coloring diff lines when possible."""

    buffer += chunk
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        if capture_line_fn is not None:
            capture_line_fn(line + "\n")
        write_fn(_render_diff_line(line, state=state, ansi_color_reset=ansi_color_reset) + "\n")
        flush_fn()
    return buffer


def _flush_rendered_buffer(
    buffer: str,
    *,
    state: _DiffColorState,
    write_fn: Callable[[str], None],
    flush_fn: Callable[[], None],
    ansi_color_reset: str,
) -> None:
    """Flush a trailing unterminated line to the stream."""

    if not buffer:
        return
    write_fn(_render_diff_line(buffer, state=state, ansi_color_reset=ansi_color_reset))
    flush_fn()


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
    stdout_color_state = _DiffColorState()
    stderr_color_state = _DiffColorState()
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
                    stdout_parts.append(chunk)
                    stdout_buffer = _write_rendered_chunk(
                        chunk,
                        buffer=stdout_buffer,
                        state=stdout_color_state,
                        write_fn=sys_module.stdout.write,
                        flush_fn=sys_module.stdout.flush,
                        ansi_color_reset=ansi_color_reset,
                    )
                else:
                    stderr_buffer = _write_rendered_chunk(
                        chunk,
                        buffer=stderr_buffer,
                        state=stderr_color_state,
                        write_fn=sys_module.stderr.write,
                        flush_fn=sys_module.stderr.flush,
                        ansi_color_reset=ansi_color_reset,
                        capture_line_fn=stderr_parts.append,
                    )
            now = time_module.monotonic()
            if now - last_color_reset >= color_reset_interval_seconds:
                sys_module.stdout.write(ansi_color_reset)
                sys_module.stdout.flush()
                sys_module.stderr.write(ansi_color_reset)
                sys_module.stderr.flush()
                last_color_reset = now

        if stderr_buffer:
            stderr_parts.append(stderr_buffer)
        _flush_rendered_buffer(
            stdout_buffer,
            state=stdout_color_state,
            write_fn=sys_module.stdout.write,
            flush_fn=sys_module.stdout.flush,
            ansi_color_reset=ansi_color_reset,
        )
        _flush_rendered_buffer(
            stderr_buffer,
            state=stderr_color_state,
            write_fn=sys_module.stderr.write,
            flush_fn=sys_module.stderr.flush,
            ansi_color_reset=ansi_color_reset,
        )

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
