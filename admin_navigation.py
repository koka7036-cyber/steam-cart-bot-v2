"""Small per-chat navigation state for the Telegram admin keyboard."""
from __future__ import annotations

from collections import defaultdict


MAIN_MENU = "main"
TOP_LEVEL_SECTIONS = frozenset({"stock", "funpay", "playerok", "sales", "settings"})
NESTED_SECTIONS = frozenset({"steam_auth"})


class AdminNavigation:
    """Track a separate navigation stack for each administrator chat."""

    def __init__(self) -> None:
        self._stacks: dict[int, list[str]] = defaultdict(lambda: [MAIN_MENU])

    def current(self, chat_id: int) -> str:
        stack = self._stacks.get(chat_id)
        return stack[-1] if stack else MAIN_MENU

    def open(self, chat_id: int, section: str) -> str:
        if section not in TOP_LEVEL_SECTIONS and section not in NESTED_SECTIONS:
            return self.current(chat_id)
        stack = self._stacks[chat_id]
        if stack[-1] == section:
            return section
        # Re-entering a section should not create repeated copies in history.
        if section in stack:
            stack[:] = stack[: stack.index(section) + 1]
        elif section in NESTED_SECTIONS and stack[-1] in TOP_LEVEL_SECTIONS:
            stack.append(section)
        elif section in TOP_LEVEL_SECTIONS:
            stack[:] = [MAIN_MENU, section]
        else:
            # A nested screen is only valid from one of its parent sections.
            return stack[-1]
        return stack[-1]

    def back(self, chat_id: int) -> str:
        stack = self._stacks[chat_id]
        if len(stack) > 1:
            stack.pop()
        return stack[-1]

    def reset(self, chat_id: int) -> str:
        self._stacks[chat_id] = [MAIN_MENU]
        return MAIN_MENU

    def clear(self, chat_id: int) -> None:
        self._stacks.pop(chat_id, None)
