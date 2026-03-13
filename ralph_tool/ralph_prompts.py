"""Prompt and reviewer contract helpers for Ralph."""

from __future__ import annotations

import re
from pathlib import Path

from ralph_models import RalphError


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


def build_reviewer_prompt(
    agent_prompt: str,
    user_prompt: str,
    completion_promise: str,
    changed_files: list[str] | None = None,
    changed_files_note: str | None = None,
) -> str:
    """Compose reviewer prompt payload with deterministic completion requirement."""

    parts = [agent_prompt.rstrip(), "", "<ralph_user_prompt>", user_prompt.strip(), "</ralph_user_prompt>"]
    parts.extend(
        [
            "",
            "<ralph_changed_files>",
            "Changed files from latest implementer pass:",
        ]
    )
    if changed_files_note:
        parts.append(f"NOTE: {changed_files_note}")
    if changed_files:
        parts.extend(changed_files)
    else:
        parts.append("NONE")
    parts.append("</ralph_changed_files>")
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
