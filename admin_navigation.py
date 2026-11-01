"""Small per-chat navigation state for the Telegram admin keyboard."""
from __future__ import annotations

from collections import defaultdict


MAIN_MENU = "main"
TOP_LEVEL_SECTIONS = frozenset({"stock", "funpay", "playerok", "sales", "settings"})
NESTED_SECTIONS = frozenset({"steam_auth"})
SECTION_PARENTS = {"steam_auth": frozenset({"settings"})}


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
        if section == stack[-1]:
            return section

        if section in TOP_LEVEL_SECTIONS:
            # Selecting a top-level section always starts a fresh path.
            stack[:] = [MAIN_MENU, section]
            return section

        allowed_parents = SECTION_PARENTS.get(section, frozenset())
        if stack[-1] not in allowed_parents:
            return stack[-1]

        # Re-entering an existing nested screen rewinds to that screen rather
        # than duplicating it in the navigation history.
        if section in stack:
            stack[:] = stack[: stack.index(section) + 1]
        else:
            stack.append(section)
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
