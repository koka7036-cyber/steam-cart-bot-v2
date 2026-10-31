"""Read-only task queue policy for the Cloud Codex dispatcher.

This module deliberately does not call GitHub, start workflows, execute Codex,
or modify the repository. It validates issue-like records supplied by a
separate, least-privilege adapter.
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
    "run_bot.ps1",\n    "configure_playerok.ps1",\n    "repair_updater.bat",
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
_PATH = re.compile(r"(?:^|\s)([A-Za-z0-9_./-]+\.[A-Za-z0-9_-]+)(?:$|\s|[,;:])")


@dataclass(frozen=True)
class QueueDecision:
    issue_number: int
    title: str
    eligible: bool
    reason: str
    priority: int = 0


def _labels(issue: Mapping[str, Any]) -> set[str]:
    raw = issue.get("labels") or []
    result: set[str] = set()
    for label in raw:
        if isinstance(label, str):
            result.add(label.strip().lower())
        elif isinstance(label, Mapping) and isinstance(label.get("name"), str):
            result.add(label["name"].strip().lower())
    return result


def _is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip().lower().lstrip("./")
    if not normalized or normalized.startswith("/"):
        return True
    parts = normalized.split("/")
    if any(part in {"..", ".git", ".github"} for part in parts):
        return True
    return any(
        normalized == item or normalized.startswith(item.rstrip("/") + "/")
        for item in PROTECTED_PATHS
    )


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

    lowered = body.lower()
    if any(token in lowered for token in (
        "steam post", "live sale", "real sale", "funpay mutation",
        "playerok mutation", "automatic delivery", "auto-start",
        "runtime data", "order ledger", "inventory cache", "secret",
        "credential", "deployment script",
    )):
        return QueueDecision(number, title, False, "issue mentions a protected operation or data area")

    paths = _PATH.findall(body)
    if any(_is_protected_path(path) for path in paths):
        return QueueDecision(number, title, False, "issue references a protected path")

    # Require a bounded, actionable task statement. A generic request is not
    # safe to pass to an automated coding agent.
    if not _WORD.search(title + "\n" + body):
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
    decisions = [validate_issue(issue) for issue in issues]
    eligible = [decision for decision in decisions if decision.eligible]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (-item.priority, item.issue_number))
    return eligible[0]
