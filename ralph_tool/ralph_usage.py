"""Usage quota and pacing helpers for Ralph."""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from statistics import median
from typing import Callable, Iterable

FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
DEFAULT_FIVE_HOUR_LIMIT_SECONDS = FIVE_HOUR_WINDOW_SECONDS
WEEK_WINDOW_SECONDS = 7 * 24 * 60 * 60


def ensure_usage_state(
    weekly_limit_seconds: int,
    *,
    state_dir: Path,
    usage_file: Path,
    default_five_hour_limit_seconds: int = DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
    five_hour_window_seconds: int = FIVE_HOUR_WINDOW_SECONDS,
    week_window_seconds: int = WEEK_WINDOW_SECONDS,
    now_epoch: int | None = None,
) -> None:
    """Ensure usage budget state file exists and is normalized."""

    now = int(time.time() if now_epoch is None else now_epoch)
    state_dir.mkdir(parents=True, exist_ok=True)

    state: dict[str, object] = {}
    if usage_file.exists():
        try:
            state = json.loads(usage_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    epoch = int(state.get("epoch", now))
    segments = state.get("segments", [])
    max_keep_start = now - max(five_hour_window_seconds, week_window_seconds)

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
        "five_hour_limit_seconds": default_five_hour_limit_seconds,
        "five_hour_window_seconds": five_hour_window_seconds,
        "weekly_limit_seconds": weekly_limit,
        "weekly_window_seconds": week_window_seconds,
        "weekly_limit_mode": weekly_mode,
        "segments": clean,
    }
    usage_file.write_text(json.dumps(updated, separators=(",", ":")), encoding="utf-8")


def refresh_codex_rate_limits(
    *,
    usage_file: Path,
    codex_sessions_dir: Path,
    default_five_hour_limit_seconds: int = DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
    five_hour_window_seconds: int = FIVE_HOUR_WINDOW_SECONDS,
    week_window_seconds: int = WEEK_WINDOW_SECONDS,
    now_epoch: int | None = None,
) -> None:
    """Refresh usage state from latest Codex session telemetry if available."""

    now = int(time.time() if now_epoch is None else now_epoch)
    state: dict[str, object] = {}
    if usage_file.exists():
        try:
            state = json.loads(usage_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    latest_path: Path | None = None
    latest_mtime = -1.0
    if codex_sessions_dir.is_dir():
        for path in codex_sessions_dir.rglob("*.jsonl"):
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
        usage_file.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
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
        usage_file.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
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
    p_window = safe_int(
        getattr(primary, "get", lambda *_: 300)("window_minutes", 300),
        int(state.get("five_hour_window_seconds", five_hour_window_seconds)),
    ) * 60
    s_window = safe_int(
        getattr(secondary, "get", lambda *_: 10080)("window_minutes", 10080),
        int(state.get("weekly_window_seconds", week_window_seconds)),
    ) * 60
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
    five_limit_seconds = int(state.get("five_hour_limit_seconds", default_five_hour_limit_seconds))

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

    usage_file.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")


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


def weekly_usage_metrics(
    state: dict[str, object],
    now: int,
    *,
    week_window_seconds: int = WEEK_WINDOW_SECONDS,
) -> dict[str, object]:
    """Derive weekly usage metrics from telemetry and local runtime state."""

    epoch = int(state.get("epoch", now))
    week_window = int(state.get("weekly_window_seconds", week_window_seconds))
    week_limit = int(state.get("weekly_limit_seconds", 0))
    secondary_reset = int(state.get("codex_secondary_resets_at", 0))
    secondary_pct = state.get("codex_secondary_used_percent")
    segments = state.get("segments", [])

    if secondary_reset > now:
        week_end = secondary_reset
        week_start = week_end - week_window
    else:
        week_period = (now - epoch) // week_window if week_window > 0 else 0
        week_start = epoch + week_period * week_window
        week_end = week_start + week_window

    used_week = _overlap_sum(segments if isinstance(segments, list) else [], week_start, week_end)
    telemetry_remaining_percent: float | None = None
    if isinstance(secondary_pct, (int, float)):
        telemetry_remaining_percent = max(0.0, 100.0 - float(secondary_pct))

    computed_remaining_percent: float | None = None
    if week_limit > 0:
        computed_remaining_percent = max(0.0, 100.0 - ((used_week / week_limit) * 100.0))

    remaining_percent = telemetry_remaining_percent
    remaining_percent_source = "telemetry" if telemetry_remaining_percent is not None else ""
    if remaining_percent is None and computed_remaining_percent is not None:
        remaining_percent = computed_remaining_percent
        remaining_percent_source = "computed"

    return {
        "computed_remaining_percent": computed_remaining_percent,
        "remaining_percent": remaining_percent,
        "remaining_percent_source": remaining_percent_source,
        "secondary_reset": secondary_reset,
        "used_week": used_week,
        "week_end": week_end,
        "week_limit": week_limit,
        "week_start": week_start,
        "week_window": week_window,
    }


def compute_usage_wait_seconds(
    state: dict[str, object],
    now: int,
    weekly_quota_reserve_percent: int = 0,
    *,
    default_five_hour_limit_seconds: int = DEFAULT_FIVE_HOUR_LIMIT_SECONDS,
    five_hour_window_seconds: int = FIVE_HOUR_WINDOW_SECONDS,
) -> tuple[int, str]:
    """Compute throttling wait seconds from current usage state."""

    epoch = int(state.get("epoch", now))
    five_window = int(state.get("five_hour_window_seconds", five_hour_window_seconds))
    five_limit = int(state.get("five_hour_limit_seconds", default_five_hour_limit_seconds))
    primary_used_pct = float(state.get("codex_primary_used_percent", -1.0))
    secondary_used_pct = float(state.get("codex_secondary_used_percent", -1.0))
    primary_resets_at = int(state.get("codex_primary_resets_at", 0))
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

    weekly_metrics = weekly_usage_metrics(state, now)
    week_limit = int(weekly_metrics["week_limit"])
    week_window = int(weekly_metrics["week_window"])
    week_start = int(weekly_metrics["week_start"])
    week_end = int(weekly_metrics["week_end"])
    used_week = int(weekly_metrics["used_week"])
    remaining_percent = weekly_metrics["remaining_percent"]

    if week_limit > 0 and week_window > 0:
        elapsed = max(0, now - week_start)
        if (
            weekly_quota_reserve_percent > 0
            and remaining_percent is not None
            and remaining_percent <= float(weekly_quota_reserve_percent)
        ):
            reserve_wait = max(0, week_end - now)
            if reserve_wait > wait_for or wait_for == 0:
                wait_for = reserve_wait
                reason = "weekly reserve threshold reached"
        if used_week >= week_limit:
            weekly_wait = max(0, week_end - now)
            if weekly_wait > wait_for:
                wait_for = weekly_wait
                reason = "weekly budget exhausted"
        else:
            target = (week_limit * elapsed) / week_window
            if used_week > target and week_limit > 0:
                next_ok = week_start + math.ceil((used_week * week_window) / week_limit)
                if next_ok > now:
                    pacing_wait = next_ok - now
                    if pacing_wait > wait_for:
                        wait_for = pacing_wait
                        reason = "weekly pacing"
        secondary_resets_at = int(weekly_metrics["secondary_reset"])
        if secondary_used_pct >= 99.5 and secondary_resets_at > now:
            telemetry_wait = secondary_resets_at - now
            if telemetry_wait > wait_for:
                wait_for = telemetry_wait
                reason = "weekly limit exhausted"

    return wait_for, reason


def enforce_usage_limits(
    *,
    usage_file: Path,
    format_duration_hms: Callable[[int], str],
    format_resume_time: Callable[[int, int], str],
    sleep_fn: Callable[[int], None] = time.sleep,
    weekly_quota_reserve_percent: int = 0,
) -> None:
    """Block until current usage budgets allow execution."""

    while True:
        now = int(time.time())
        try:
            state = json.loads(usage_file.read_text(encoding="utf-8"))
        except Exception:
            return

        wait_seconds, reason = compute_usage_wait_seconds(
            state,
            now,
            weekly_quota_reserve_percent=weekly_quota_reserve_percent,
        )
        if wait_seconds <= 0:
            return
        print(
            "Ralph throttling:"
            f" {reason}. Sleeping {format_duration_hms(wait_seconds)}."
            f" Planned resume: {format_resume_time(now, wait_seconds)}."
        )
        sleep_fn(wait_seconds)


def record_usage_segment(
    start_epoch: int,
    end_epoch: int,
    *,
    usage_file: Path,
    five_hour_window_seconds: int = FIVE_HOUR_WINDOW_SECONDS,
    week_window_seconds: int = WEEK_WINDOW_SECONDS,
    now_epoch: int | None = None,
) -> None:
    """Record execution segment into usage state."""

    if end_epoch <= start_epoch:
        return
    now = int(time.time() if now_epoch is None else now_epoch)

    state: dict[str, object] = {}
    if usage_file.exists():
        try:
            state = json.loads(usage_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    segments = state.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    segments.append([start_epoch, end_epoch])

    max_keep = now - max(
        int(state.get("five_hour_window_seconds", five_hour_window_seconds)),
        int(state.get("weekly_window_seconds", week_window_seconds)),
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
    usage_file.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")


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

    import re

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
