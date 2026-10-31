"""Read-only queue policy for the Cloud Codex dispatcher.

This module validates GitHub issue-shaped records supplied by a separate
read-only adapter. It never calls GitHub, executes Codex, or mutates state.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

ELIGIBLE_LABELS = frozenset({"codex-ready"})
BLOCKED_LABELS = frozenset({"do-not-automate", "needs-human", "blocked"})
PROTECTED_PATHS = (
    ".github/",
    ".env",
    "secrets",
    "runtime",
    "data/",
    "inventory",
    "orders",
    "steam_session",
    "funpay",
    "playerok",
    "start.bat",
    "run_bot.ps1",
    "configure_playerok.ps1",
    "repair_updater.bat",
    "update_bot.ps1",
    "install_autostart.ps1",
    "toggle_autostart_task.ps1",
    "setup_windows.ps1",
)
MAX_TASK_CHARS = 1000
MAX_TITLE_CHARS = 160
MAX_ISSUE_BODY_CHARS = 6000
MAX_ISSUE_NUMBER = 2_147_483_647

_WORD = re.compile(r"\b(?:implement|fix|add|refactor|test|document|audit)\b", re.I)
_PATH = re.compile(r"(?:^|\s)([A-Za-z0-9_./-]+(?:\.[A-Za-z0-9_-]+)?)(?:$|\s|[,;:])")


@dataclass(frozen=True)
class QueueDecision:
    issue_number: int
    title: str
    eligible: bool
    reason: str
    priority: int = 0


def _labels(issue: Mapping[str, Any]) -> set[str]:
    raw = issue.get("labels") or []
    if not isinstance(raw, (list, tuple)):
        return set()
    result: set[str] = set()
    for label in raw:
        if isinstance(label, str):
            result.add(label.strip().lower())
        elif isinstance(label, Mapping) and isinstance(label.get("name"), str):
            result.add(label["name"].strip().lower())
    return result


def _is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip().lower()
    if not normalized or normalized.startswith("/"):
        return True
    parts = normalized.split("/")
    if any(part in {"..", ".git", ".github"} for part in parts):
        return True
    normalized = normalized.lstrip("./")
    return any(
        normalized == item or normalized.startswith(item.rstrip("/") + "/")
        for item in PROTECTED_PATHS
    )


def _requested_protected_operation(text: str) -> bool:
    """Conservatively block direct protected-action requests, not prohibitions."""
    lowered = text.lower()
    # Strip explicit negative instructions before the positive-intent check.
    candidate = re.sub(
        r"\b(?:do\s+not|don't|never|without|no)\b[^.!?;]{0,180}",
        " ",
        lowered,
        flags=re.I,
    )
    patterns = (
        r"\b(?:implement|add|enable|perform|execute|send|submit)\b[^\n.]{0,120}\b(?:live|real)\s+sales?\b",
        r"\b(?:implement|add|enable|perform|execute|send|submit)\b[^\n.]{0,120}\bsteam\s+post\b",
        r"\b(?:implement|add|enable|perform|execute)\b[^\n.]{0,120}\b(?:funpay|playerok)\s+mutations?\b",
        r"\b(?:implement|add|enable)\b[^\n.]{0,120}\bautomatic\s+delivery\b",
        r"\b(?:modify|change|read|write|delete|expose)\b[^\n.]{0,120}\b(?:runtime\s+data|order\s+ledger|inventory\s+cache|credentials?|secrets?)\b",
        r"\b(?:modify|change|enable|install)\b[^\n.]{0,120}\b(?:auto[- ]?start|deployment\s+scripts?)\b",
    )
    return any(re.search(pattern, candidate, re.I) for pattern in patterns)


def validate_issue(issue: Mapping[str, Any]) -> QueueDecision:
    """Fail-closed validation for one GitHub issue-shaped mapping."""
    number = issue.get("number")
    title = issue.get("title")
    body = issue.get("body") or ""
    state = str(issue.get("state") or "").lower()
    labels = _labels(issue)

    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= MAX_ISSUE_NUMBER:
        return QueueDecision(0, "", False, "invalid issue number")
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_CHARS:
        return QueueDecision(number, "", False, "invalid or oversized title")
    if state != "open":
        return QueueDecision(number, title, False, "issue is not open")
    if labels & BLOCKED_LABELS:
        return QueueDecision(number, title, False, "issue has a blocking label")
    if not (labels & ELIGIBLE_LABELS):
        return QueueDecision(number, title, False, "missing explicit codex-ready label")
    if not isinstance(body, str) or len(body) > MAX_ISSUE_BODY_CHARS:
        return QueueDecision(number, title, False, "invalid or oversized issue body")

    task_text = f"{title}\n{body}"
    if _requested_protected_operation(task_text):
        return QueueDecision(number, title, False, "issue requests a protected operation or data change")

    # Only inspect an explicit allowlist block. Prose may mention protected
    # filenames as examples or prohibitions and must not be treated as targets.
    file_block = re.search(
        r"(?im)^files\s+to\s+change\s*:\s*(.*?)(?=^\S[^\n]*:\s*$|\Z)",
        body,
        re.S,
    )
    if not file_block:
        return QueueDecision(number, title, False, "missing explicit Files to change allowlist")
    declared_paths = [
        token.strip().strip("`'\"")
        for token in re.split(r"[\s,;]+", file_block.group(1))
        if token.strip().strip("`'\"")
    ]
    if not declared_paths or any(_is_protected_path(path) for path in declared_paths):
        return QueueDecision(number, title, False, "declared file path is protected or invalid")

    if not _WORD.search(task_text):
        return QueueDecision(number, title, False, "task is not clearly actionable")
    if len(body.strip()) < 80:
        return QueueDecision(number, title, False, "task description is too short to define scope")

    priority = 0
    if "priority:critical" in labels or "priority:high" in labels:
        priority = 3
    elif "priority:medium" in labels:
        priority = 2
    elif "priority:low" in labels:
        priority = 1
    return QueueDecision(number, title.strip(), True, "eligible", priority)


def select_next_task(issues: Iterable[Mapping[str, Any]]) -> QueueDecision | None:
    """Choose one issue deterministically; never dispatch more than one."""
    eligible = [decision for decision in (validate_issue(item) for item in issues) if decision.eligible]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (-item.priority, item.issue_number))
    return eligible[0]
