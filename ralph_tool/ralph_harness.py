#!/usr/bin/env python3
"""Ralph harness engine implemented in Python 3.12.

This module preserves the original CLI surface while adding reviewer-gated looping.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from statistics import median
from typing import Callable, Iterable

from rich.console import Console
from rich.markdown import Markdown

STATE_DIR = Path(".codex")
STATE_FILE = STATE_DIR / "ralph-loop.local.md"
LAST_MESSAGE_FILE = STATE_DIR / "ralph-last-message.txt"
USAGE_FILE = STATE_DIR / "ralph-usage.local.json"
ERR_FILE = STATE_DIR / "ralph-last-error.log"
PROJECT_ROOT = Path(os.environ.get("RALPH_REPO_ROOT", Path(__file__).resolve().parent.parent)).resolve()

DEFAULT_IMPLEMENTER_PROMPT_FILE = PROJECT_ROOT / "SPEC_FILES/smart_agents/2_SPEC_IMPLEMENTER.md"
DEFAULT_REVIEWER_PROMPT_FILE = PROJECT_ROOT / "SPEC_FILES/smart_agents/3_SPEC_REVIEWER.md"

CODEX_SESSIONS_DIR = Path(os.environ.get("CODEX_SESSIONS_DIR", str(Path.home() / ".codex/sessions")))

FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
DEFAULT_FIVE_HOUR_LIMIT_SECONDS = FIVE_HOUR_WINDOW_SECONDS
WEEK_WINDOW_SECONDS = 7 * 24 * 60 * 60


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
    max_review_cycles: int
    codex_args: list[str]


@dataclasses.dataclass(frozen=True)
class CommandResult:
    """Result from a command runner invocation."""

    returncode: int
    stderr: str


@dataclasses.dataclass(frozen=True)
class InnerLoopResult:
    """Summary for an implementer inner loop."""

    termination_reason: str
    iterations_run: int
    promise_matched: bool
    elapsed_seconds: int


@dataclasses.dataclass(frozen=True)
class ReviewerResult:
    """Summary for a reviewer pass."""

    status: str
    promise_matched: bool
    elapsed_seconds: int


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


def usage_text() -> str:
    """Return top-level usage text."""

    return """Ralph Wiggum for Codex

Usage:
  ralph loop [PROMPT...] [--prompt PATH] [--reviewer-prompt PATH] [--max-iterations N] [--completion-promise TEXT] [--weekly-limit-hours N|auto] [--max-review-cycles N] [--] [codex exec args]
  ralph cancel
  ralph status
  ralph help

Notes:
  - PROMPT is the user task request and can be omitted if provided via stdin.
  - --prompt overrides the implementer prompt template file for loop passes.
  - --reviewer-prompt overrides the reviewer prompt template file for outer review.
  - If positional PROMPT and stdin are absent, --prompt file contents are used as PROMPT text.
  - Use -- to pass flags directly to `codex exec` (e.g., -- --model o3).
"""


def loop_help_text() -> str:
    """Return loop subcommand help text."""

    return """ralph loop

Usage:
  ralph loop [PROMPT...] [--prompt PATH] [--reviewer-prompt PATH] [--max-iterations N] [--completion-promise TEXT] [--weekly-limit-hours N|auto] [--max-review-cycles N] [--] [codex exec args]

Options:
  --prompt PATH             Implementer prompt template file (default: SPEC_FILES/smart_agents/2_SPEC_IMPLEMENTER.md)
  --reviewer-prompt PATH    Reviewer prompt template file (default: SPEC_FILES/smart_agents/3_SPEC_REVIEWER.md)
  --max-iterations N        Max implementer iterations per inner loop (default: unlimited)
  --completion-promise TEXT Promise phrase expected from implementer and reviewer (default: DONE)
  --weekly-limit-hours N|auto
                            Weekly runtime budget in hours, or auto-detect from Codex telemetry
                            (default: $RALPH_WEEKLY_LIMIT_HOURS, or auto)
  --max-review-cycles N     Max outer reviewer cycles before failing (default: 5; 0 means unlimited)
  -h, --help                Show this help

Notes:
  - PROMPT is the user task request and can be provided via stdin if omitted.
  - If PROMPT and stdin are omitted, --prompt file contents become the PROMPT text.
  - Ralph enforces a 5-hour runtime budget per 5-hour window and sleeps until reset.
  - Weekly pacing is auto-detected by default and can be overridden with a numeric hour budget.
  - Pass Codex flags after -- (e.g., -- --model o3 --sandbox workspace-write).
"""


def now_iso_utc() -> str:
    """Return current UTC timestamp in RFC3339-like format."""

    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    completion_promise: str,
    codex_args_serialized: str,
) -> None:
    """Write loop state file with frontmatter."""

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "iteration": 1,
        "review_cycle": 1,
        "max_iterations": max_iterations,
        "max_review_cycles": max_review_cycles,
        "completion_promise": completion_promise or None,
        "codex_args": codex_args_serialized or None,
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


def extract_promise_text(text: str) -> str | None:
    """Extract the final <promise> tag text if present."""

    matches = re.findall(r"<promise>(.*?)</promise>", text, flags=re.DOTALL)
    if not matches:
        return None
    return " ".join(matches[-1].split())


def extract_promise_text_from_file(path: Path) -> str | None:
    """Extract promise text from a message file."""

    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    return extract_promise_text(text)


def parse_review_status(text: str) -> str | None:
    """Parse reviewer overall status from REVIEW.md-like output."""

    match = re.search(r"Overall status:\s*(PASS WITH NITS|PASS|FAIL)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper()


def ensure_usage_state(weekly_limit_seconds: int, now_epoch: int | None = None) -> None:
    """Ensure usage budget state file exists and is normalized."""

    now = int(time.time() if now_epoch is None else now_epoch)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    state: dict[str, object] = {}
    if USAGE_FILE.exists():
        try:
            state = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    epoch = int(state.get("epoch", now))
    segments = state.get("segments", [])
    max_keep_start = now - max(FIVE_HOUR_WINDOW_SECONDS, WEEK_WINDOW_SECONDS)

    clean: list[list[int]] = []
    if isinstance(segments, list):
        for item in segments:
            if not (isinstance(item, list) and len(item) == 2):
                continue
            try:
                start = int(item[0])
                end = int(item[1])
            except Exception:
                continue
            if end <= start or end <= max_keep_start:
                continue
            clean.append([start, end])

    if weekly_limit_seconds < 0:
        weekly_limit = int(state.get("weekly_limit_seconds", 0))
        weekly_mode = "auto"
    else:
        weekly_limit = weekly_limit_seconds
        weekly_mode = "manual"

    updated = {
        "version": 1,
        "epoch": epoch,
        "five_hour_limit_seconds": DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
        "five_hour_window_seconds": FIVE_HOUR_WINDOW_SECONDS,
        "weekly_limit_seconds": weekly_limit,
        "weekly_window_seconds": WEEK_WINDOW_SECONDS,
        "weekly_limit_mode": weekly_mode,
        "segments": clean,
    }
    USAGE_FILE.write_text(json.dumps(updated, separators=(",", ":")), encoding="utf-8")


def refresh_codex_rate_limits(now_epoch: int | None = None) -> None:
    """Refresh usage state from latest Codex session telemetry if available."""

    now = int(time.time() if now_epoch is None else now_epoch)
    state: dict[str, object] = {}
    if USAGE_FILE.exists():
        try:
            state = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    latest_path: Path | None = None
    latest_mtime = -1.0
    if CODEX_SESSIONS_DIR.is_dir():
        for path in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
            if "rollout-" not in path.name:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_path = path

    if latest_path is None:
        USAGE_FILE.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        return

    last_rate: dict[str, object] | None = None
    try:
        with latest_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                rate = payload.get("rate_limits")
                if isinstance(rate, dict) and "primary" in rate and "secondary" in rate:
                    last_rate = rate
    except Exception:
        last_rate = None

    if last_rate is None:
        USAGE_FILE.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        return

    primary = last_rate.get("primary") or {}
    secondary = last_rate.get("secondary") or {}

    def safe_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def safe_int(value: object, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    p_used = safe_float(getattr(primary, "get", lambda *_: 0.0)("used_percent", 0.0))
    s_used = safe_float(getattr(secondary, "get", lambda *_: 0.0)("used_percent", 0.0))
    p_window = safe_int(getattr(primary, "get", lambda *_: 300)("window_minutes", 300), int(state.get("five_hour_window_seconds", FIVE_HOUR_WINDOW_SECONDS))) * 60
    s_window = safe_int(getattr(secondary, "get", lambda *_: 10080)("window_minutes", 10080), int(state.get("weekly_window_seconds", WEEK_WINDOW_SECONDS))) * 60
    p_reset = safe_int(getattr(primary, "get", lambda *_: 0)("resets_at", 0), 0)
    s_reset = safe_int(getattr(secondary, "get", lambda *_: 0)("resets_at", 0), 0)

    state["five_hour_window_seconds"] = p_window
    state["weekly_window_seconds"] = s_window
    state["codex_primary_used_percent"] = p_used
    state["codex_secondary_used_percent"] = s_used
    state["codex_primary_resets_at"] = p_reset
    state["codex_secondary_resets_at"] = s_reset
    state["codex_rate_observed_at"] = now

    mode = str(state.get("weekly_limit_mode", "auto"))
    five_limit_seconds = int(state.get("five_hour_limit_seconds", DEFAULT_FIVE_HOUR_LIMIT_SECONDS))

    prev_p = state.get("last_primary_used_percent")
    prev_s = state.get("last_secondary_used_percent")
    prev_reset = int(state.get("last_secondary_resets_at", 0))

    if (
        mode == "auto"
        and isinstance(prev_p, (int, float))
        and isinstance(prev_s, (int, float))
        and prev_reset == s_reset
    ):
        dp = p_used - float(prev_p)
        ds = s_used - float(prev_s)
        if dp >= 0.25 and ds >= 0.02:
            estimate = five_limit_seconds * (dp / ds)
            if 6 * 60 * 60 <= estimate <= 14 * 24 * 60 * 60:
                estimates = state.get("weekly_limit_estimates_seconds", [])
                if not isinstance(estimates, list):
                    estimates = []
                estimates.append(int(round(estimate)))
                estimates = estimates[-24:]
                state["weekly_limit_estimates_seconds"] = estimates
                state["weekly_limit_seconds"] = int(round(median(estimates)))

    state["last_primary_used_percent"] = p_used
    state["last_secondary_used_percent"] = s_used
    state["last_secondary_resets_at"] = s_reset
    state["last_rate_sample_at"] = now

    USAGE_FILE.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")


def _overlap_sum(segments: Iterable[object], start: int, end: int) -> int:
    total = 0
    for item in segments:
        if not (isinstance(item, list) and len(item) == 2):
            continue
        try:
            segment_start = int(item[0])
            segment_end = int(item[1])
        except Exception:
            continue
        if segment_end <= start or segment_start >= end:
            continue
        total += max(0, min(segment_end, end) - max(segment_start, start))
    return total


def compute_usage_wait_seconds(state: dict[str, object], now: int) -> tuple[int, str]:
    """Compute throttling wait seconds from current usage state."""

    epoch = int(state.get("epoch", now))
    five_window = int(state.get("five_hour_window_seconds", FIVE_HOUR_WINDOW_SECONDS))
    five_limit = int(state.get("five_hour_limit_seconds", DEFAULT_FIVE_HOUR_LIMIT_SECONDS))
    week_window = int(state.get("weekly_window_seconds", WEEK_WINDOW_SECONDS))
    week_limit = int(state.get("weekly_limit_seconds", 0))
    primary_used_pct = float(state.get("codex_primary_used_percent", -1.0))
    secondary_used_pct = float(state.get("codex_secondary_used_percent", -1.0))
    primary_resets_at = int(state.get("codex_primary_resets_at", 0))
    secondary_resets_at = int(state.get("codex_secondary_resets_at", 0))
    segments = state.get("segments", [])

    wait_for = 0
    reason = "budget"

    if five_limit > 0 and five_window > 0:
        if primary_resets_at > now:
            five_end = primary_resets_at
            five_start = five_end - five_window
        else:
            five_period = (now - epoch) // five_window
            five_start = epoch + five_period * five_window
            five_end = five_start + five_window
        used_five = _overlap_sum(segments if isinstance(segments, list) else [], five_start, five_end)
        if used_five >= five_limit:
            wait_for = max(wait_for, five_end - now)
            reason = "5h budget exhausted"
        if primary_used_pct >= 99.5 and primary_resets_at > now:
            wait_for = max(wait_for, primary_resets_at - now)
            reason = "5h limit exhausted"

    if week_limit > 0 and week_window > 0:
        if secondary_resets_at > now:
            week_end = secondary_resets_at
            week_start = week_end - week_window
        else:
            week_period = (now - epoch) // week_window
            week_start = epoch + week_period * week_window
            week_end = week_start + week_window
        used_week = _overlap_sum(segments if isinstance(segments, list) else [], week_start, week_end)
        elapsed = max(0, now - week_start)
        if used_week >= week_limit:
            wait_for = max(wait_for, week_end - now)
            reason = "weekly budget exhausted"
        else:
            target = (week_limit * elapsed) / week_window
            if used_week > target and week_limit > 0:
                next_ok = week_start + math.ceil((used_week * week_window) / week_limit)
                if next_ok > now:
                    wait_for = max(wait_for, next_ok - now)
                    reason = "weekly pacing"
        if secondary_used_pct >= 99.5 and secondary_resets_at > now:
            wait_for = max(wait_for, secondary_resets_at - now)
            reason = "weekly limit exhausted"

    return wait_for, reason


def enforce_usage_limits(sleep_fn: Callable[[int], None] = time.sleep) -> None:
    """Block until current usage budgets allow execution."""

    while True:
        now = int(time.time())
        try:
            state = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return

        wait_seconds, reason = compute_usage_wait_seconds(state, now)
        if wait_seconds <= 0:
            return
        print(f"Ralph throttling: {reason}. Sleeping {wait_seconds}s.")
        sleep_fn(wait_seconds)


def record_usage_segment(start_epoch: int, end_epoch: int, now_epoch: int | None = None) -> None:
    """Record execution segment into usage state."""

    if end_epoch <= start_epoch:
        return
    now = int(time.time() if now_epoch is None else now_epoch)

    state: dict[str, object] = {}
    if USAGE_FILE.exists():
        try:
            state = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    segments = state.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    segments.append([start_epoch, end_epoch])

    max_keep = now - max(
        int(state.get("five_hour_window_seconds", FIVE_HOUR_WINDOW_SECONDS)),
        int(state.get("weekly_window_seconds", WEEK_WINDOW_SECONDS)),
    )

    clean: list[list[int]] = []
    for item in segments:
        if not (isinstance(item, list) and len(item) == 2):
            continue
        try:
            start = int(item[0])
            end = int(item[1])
        except Exception:
            continue
        if end <= start or end <= max_keep:
            continue
        clean.append([start, end])

    state["segments"] = clean
    USAGE_FILE.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")


def is_usage_limit_error(stderr_text: str) -> bool:
    """Return True when stderr text indicates a usage/rate limit condition."""

    haystack = stderr_text.lower()
    patterns = [
        r"usage limit",
        r"rate limit",
        r"quota",
        r"too many requests",
        r"limit.*reached",
        r"limit.*exceeded",
    ]
    return any(re.search(pattern, haystack) for pattern in patterns)


def parse_limit_wait_seconds(stderr_text: str) -> int:
    """Best-effort parse of retry delay from error text."""

    text = stderr_text.lower()
    best = 0
    for match in re.finditer(r"(\d+)\s*h(?:ours?)?\s*(\d+)?\s*m?(?:in(?:utes?)?)?", text):
        hours = int(match.group(1))
        minutes = int(match.group(2) or 0)
        best = max(best, hours * 3600 + minutes * 60)
    for match in re.finditer(r"(\d+)\s*m(?:in(?:ute)?s?)?\s*(\d+)?\s*s(?:ec(?:ond)?s?)?", text):
        minutes = int(match.group(1))
        seconds = int(match.group(2) or 0)
        best = max(best, minutes * 60 + seconds)
    for match in re.finditer(r"(\d+)\s*s(?:ec(?:ond)?s?)?", text):
        best = max(best, int(match.group(1)))
    return best if best > 0 else 300


def read_prompt_file(path: Path) -> str:
    """Read an agent prompt file with strict validation."""

    if not path.exists():
        raise RalphError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_implementer_prompt(agent_prompt: str, user_prompt: str, completion_promise: str) -> str:
    """Compose implementer prompt payload."""

    parts = [agent_prompt.rstrip(), "", "<ralph_user_prompt>", user_prompt.strip(), "</ralph_user_prompt>"]
    parts.extend(
        [
            "",
            "<ralph_completion_promise>",
            "When and only when all requested work for this loop is complete, emit exactly this tag on its own line:",
            f"<promise>{completion_promise}</promise>",
            "Do not emit that exact tag before completion.",
            "</ralph_completion_promise>",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def build_reviewer_prompt(agent_prompt: str, user_prompt: str, completion_promise: str) -> str:
    """Compose reviewer prompt payload with deterministic completion requirement."""

    parts = [agent_prompt.rstrip(), "", "<ralph_user_prompt>", user_prompt.strip(), "</ralph_user_prompt>"]
    parts.extend(
        [
            "",
            "<ralph_reviewer_completion_contract>",
            "You MUST output `Overall status: PASS` or `Overall status: PASS WITH NITS` only when implementation is satisfactory.",
            "If and only if you output one of those satisfied statuses, emit this exact tag on its own line:",
            f"<promise>{completion_promise}</promise>",
            "If status is FAIL, do not emit the promise tag.",
            "</ralph_reviewer_completion_contract>",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def run_codex_exec(prompt: str, codex_args: list[str]) -> CommandResult:
    """Execute a codex run and capture stderr for retry logic."""

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    command = ["codex", "exec", *codex_args, "--output-last-message", str(LAST_MESSAGE_FILE)]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    ERR_FILE.write_text(completed.stderr or "", encoding="utf-8")
    return CommandResult(returncode=completed.returncode, stderr=completed.stderr or "")


def run_with_retries(
    *,
    prompt: str,
    codex_args: list[str],
    refresh_fn: Callable[[], None],
    enforce_fn: Callable[[], None],
    sleep_fn: Callable[[int], None],
) -> tuple[str, int]:
    """Run codex with usage-limit retries and return message plus elapsed time."""

    while True:
        refresh_fn()
        enforce_fn()
        started_epoch = int(time.time())
        result = run_codex_exec(prompt, codex_args)
        ended_epoch = int(time.time())

        if result.returncode == 0:
            record_usage_segment(started_epoch, ended_epoch)
            refresh_fn()
            if not LAST_MESSAGE_FILE.exists():
                raise RalphError("codex exec did not write last message file")
            message = LAST_MESSAGE_FILE.read_text(encoding="utf-8", errors="ignore")
            return message, max(0, ended_epoch - started_epoch)

        refresh_fn()
        if is_usage_limit_error(result.stderr):
            wait_seconds = parse_limit_wait_seconds(result.stderr)
            warn(f"codex usage limit reached; sleeping {wait_seconds}s before retry")
            sleep_fn(wait_seconds)
            continue

        raise RalphError("codex exec failed")


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


def parse_loop_args(args: list[str], stdin_text: str | None) -> LoopOptions:
    """Parse loop command arguments without argparse to preserve passthrough behavior."""

    max_iterations = 0
    completion_promise = "DONE"
    weekly_limit_hours = os.environ.get("RALPH_WEEKLY_LIMIT_HOURS", "auto")
    max_review_cycles = 5
    implementer_prompt_path = str(DEFAULT_IMPLEMENTER_PROMPT_FILE)
    reviewer_prompt_path = str(DEFAULT_REVIEWER_PROMPT_FILE)
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
        if token == "--max-review-cycles":
            if index + 1 >= len(args):
                raise RalphError("--max-review-cycles requires a number")
            candidate = args[index + 1]
            if not re.fullmatch(r"\d+", candidate):
                raise RalphError("--max-review-cycles must be a non-negative integer")
            max_review_cycles = int(candidate)
            index += 2
            continue

        prompt_parts.append(token)
        index += 1

    prompt = " ".join(prompt_parts).strip()
    if not prompt and stdin_text is not None:
        prompt = stdin_text
    if not prompt and prompt_option_path is not None:
        # Allow --prompt to provide user prompt text when positional/stdin prompt is omitted.
        prompt = read_prompt_file(Path(prompt_option_path))
        implementer_prompt_path = str(DEFAULT_IMPLEMENTER_PROMPT_FILE)
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
        max_review_cycles=max_review_cycles,
        codex_args=codex_args,
    )


def run_inner_loop(
    *,
    loop_prompt: str,
    codex_args: list[str],
    completion_promise: str,
    max_iterations: int,
    refresh_fn: Callable[[], None],
    enforce_fn: Callable[[], None],
    sleep_fn: Callable[[int], None],
) -> InnerLoopResult:
    """Run implementer loop until completion promise or iteration cap."""

    iteration = 1
    total_elapsed = 0

    while True:
        if not STATE_FILE.exists():
            raise SystemExit(0)

        print(f"Ralph iteration {iteration}")
        update_state_value("iteration", iteration)
        message, elapsed = run_with_retries(
            prompt=loop_prompt,
            codex_args=codex_args,
            refresh_fn=refresh_fn,
            enforce_fn=enforce_fn,
            sleep_fn=sleep_fn,
        )
        total_elapsed += elapsed

        promise_text = extract_promise_text(message)
        if promise_text == completion_promise:
            return InnerLoopResult(
                termination_reason="completion_promise",
                iterations_run=iteration,
                promise_matched=True,
                elapsed_seconds=total_elapsed,
            )

        if max_iterations > 0 and iteration >= max_iterations:
            return InnerLoopResult(
                termination_reason="max_iterations",
                iterations_run=iteration,
                promise_matched=False,
                elapsed_seconds=total_elapsed,
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
) -> ReviewerResult:
    """Run a single reviewer pass and parse mandatory status output."""

    message, elapsed = run_with_retries(
        prompt=reviewer_prompt,
        codex_args=codex_args,
        refresh_fn=refresh_fn,
        enforce_fn=enforce_fn,
        sleep_fn=sleep_fn,
    )
    status = parse_review_status(message)
    if status is None:
        raise RalphError("reviewer output missing 'Overall status' line")
    promise_text = extract_promise_text(message)
    return ReviewerResult(
        status=status,
        promise_matched=promise_text == completion_promise,
        elapsed_seconds=elapsed,
    )


def run_loop(options: LoopOptions, *, console: Console, sleep_fn: Callable[[int], None] = time.sleep) -> int:
    """Execute full reviewer-gated loop flow."""

    require_cmd("codex")

    weekly_limit_seconds = -1 if options.weekly_limit_hours == "auto" else int(options.weekly_limit_hours) * 3600
    codex_args_serialized = shlex.join(options.codex_args) if options.codex_args else ""

    write_state_file(
        prompt=options.prompt,
        max_iterations=options.max_iterations,
        max_review_cycles=options.max_review_cycles,
        completion_promise=options.completion_promise,
        codex_args_serialized=codex_args_serialized,
    )

    ensure_usage_state(weekly_limit_seconds)
    refresh_codex_rate_limits()

    implementer_prompt = build_implementer_prompt(
        read_prompt_file(Path(options.implementer_prompt_path)),
        options.prompt,
        options.completion_promise,
    )
    reviewer_prompt = build_reviewer_prompt(
        read_prompt_file(Path(options.reviewer_prompt_path)),
        options.prompt,
        options.completion_promise,
    )

    review_cycle = 1
    while True:
        if not STATE_FILE.exists():
            print("Ralph loop cancelled.")
            return 0
        update_state_value("review_cycle", review_cycle)

        inner_result = run_inner_loop(
            loop_prompt=implementer_prompt,
            codex_args=options.codex_args,
            completion_promise=options.completion_promise,
            max_iterations=options.max_iterations,
            refresh_fn=refresh_codex_rate_limits,
            enforce_fn=enforce_usage_limits,
            sleep_fn=sleep_fn,
        )
        print_inner_status_table(
            console,
            review_cycle=review_cycle,
            result=inner_result,
            next_action="run_reviewer",
        )

        if not STATE_FILE.exists():
            print("Ralph loop cancelled.")
            return 0

        reviewer_result = run_reviewer_once(
            reviewer_prompt=reviewer_prompt,
            codex_args=options.codex_args,
            completion_promise=options.completion_promise,
            refresh_fn=refresh_codex_rate_limits,
            enforce_fn=enforce_usage_limits,
            sleep_fn=sleep_fn,
        )

        if reviewer_result.status in {"PASS", "PASS WITH NITS"} and reviewer_result.promise_matched:
            print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision="stop")
            print(f"Ralph loop complete: <promise>{options.completion_promise}</promise>")
            STATE_FILE.unlink(missing_ok=True)
            return 0

        if reviewer_result.status in {"PASS", "PASS WITH NITS"} and not reviewer_result.promise_matched:
            print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision="fail")
            STATE_FILE.unlink(missing_ok=True)
            raise RalphError("reviewer satisfied status missing required completion promise tag")

        if reviewer_result.status != "FAIL":
            print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision="fail")
            STATE_FILE.unlink(missing_ok=True)
            raise RalphError(f"unrecognized reviewer status: {reviewer_result.status}")

        if options.max_review_cycles > 0 and review_cycle >= options.max_review_cycles:
            print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision="max_review_cycles_reached")
            STATE_FILE.unlink(missing_ok=True)
            raise RalphError(f"reviewer unsatisfied after {options.max_review_cycles} review cycles")

        print_outer_status_table(console, review_cycle=review_cycle, result=reviewer_result, decision="retry_implementer")
        review_cycle += 1


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

    if primary_reset > now:
        five_end = primary_reset
        five_start = five_end - five_window
    else:
        five_period = (now - epoch) // five_window
        five_start = epoch + five_period * five_window
        five_end = five_start + five_window

    used_five = _overlap_sum(segments if isinstance(segments, list) else [], five_start, five_end)

    lines = [f"  5h_usage: {used_five}s / {five_limit}s"]
    if isinstance(primary_pct, (int, float)):
        lines.append(f"  5h_usage_percent: {float(primary_pct):.1f}%")

    if week_limit > 0:
        if secondary_reset > now:
            week_end = secondary_reset
            week_start = week_end - week_window
        else:
            week_period = (now - epoch) // week_window
            week_start = epoch + week_period * week_window
            week_end = week_start + week_window
        used_week = _overlap_sum(segments if isinstance(segments, list) else [], week_start, week_end)
        lines.append(f"  weekly_usage: {used_week}s / {week_limit}s")
        lines.append(f"  weekly_mode: {week_mode}")
    elif week_mode == "auto":
        lines.append("  weekly_usage: auto-detecting")
    else:
        lines.append("  weekly_usage: disabled")

    if isinstance(secondary_pct, (int, float)):
        lines.append(f"  weekly_usage_percent: {float(secondary_pct):.1f}%")

    return lines


def cmd_status() -> int:
    """Show current loop status."""

    if not STATE_FILE.exists():
        print("No active Ralph loop found.")
        return 0
    if USAGE_FILE.exists():
        refresh_codex_rate_limits()

    iteration = read_frontmatter_value(STATE_FILE, "iteration")
    review_cycle = read_frontmatter_value(STATE_FILE, "review_cycle")
    max_iterations = read_frontmatter_value(STATE_FILE, "max_iterations")
    max_review_cycles = read_frontmatter_value(STATE_FILE, "max_review_cycles")
    completion_promise = read_frontmatter_value(STATE_FILE, "completion_promise")
    started_at = read_frontmatter_value(STATE_FILE, "started_at")
    codex_args = read_frontmatter_value(STATE_FILE, "codex_args")

    print("Ralph loop active")
    print(f"  review_cycle: {review_cycle or '?'}")
    print(f"  iteration: {iteration or '?'}")
    print(f"  max_review_cycles: {max_review_cycles or '?'}")
    print(f"  max_iterations: {max_iterations or '?'}")
    print(f"  completion_promise: {completion_promise or 'none'}")
    print(f"  started_at: {started_at or '?'}")
    if codex_args:
        print(f"  codex_args: {codex_args}")

    if USAGE_FILE.exists():
        for line in usage_summary_lines():
            print(line)

    return 0


def parse_stdin_if_needed(args: list[str]) -> str | None:
    """Read stdin when prompt args are absent and stdin is piped."""

    if args:
        return None
    if sys.stdin.isatty():
        return None
    return sys.stdin.read()


def cmd_loop(args: list[str], *, console: Console) -> int:
    """Handle the loop subcommand."""

    stdin_text = parse_stdin_if_needed(args)
    options = parse_loop_args(args, stdin_text)
    return run_loop(options, console=console)


def main(argv: list[str] | None = None) -> int:
    """Program entrypoint."""

    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "help"
    rest = args[1:] if args else []

    if command in {"help", "-h", "--help"}:
        print(usage_text())
        return 0

    if command in {"loop", "start"}:
        return cmd_loop(rest, console=Console())

    if command in {"cancel", "stop"}:
        return cmd_cancel()

    if command == "status":
        return cmd_status()

    err(f"Unknown command: {command}")
    print(usage_text())
    return 1
