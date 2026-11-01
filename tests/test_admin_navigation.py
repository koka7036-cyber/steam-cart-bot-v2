from admin_navigation import AdminNavigation

MAIN = "main"
STOCK = "stock"
FUNPAY = "funpay"
PLAYEROK = "playerok"
SALES = "sales"
SETTINGS = "settings"
STEAM_AUTH = "steam_auth"


def test_open_section_and_return_to_main():
    nav = AdminNavigation()
    assert nav.current(100) == MAIN
    assert nav.open(100, SETTINGS) == SETTINGS
    assert nav.back(100) == MAIN
    assert nav.current(100) == MAIN


def test_nested_steam_auth_returns_to_settings_not_main():
    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert nav.back(100) == SETTINGS
    assert nav.current(100) == SETTINGS
    assert nav.back(100) == MAIN


def test_back_from_top_level_section_returns_to_main():
    nav = AdminNavigation()
    nav.open(100, FUNPAY)
    assert nav.back(100) == MAIN


def test_chat_navigation_state_is_isolated():
    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(200, FUNPAY)
    assert nav.current(100) == SETTINGS
    assert nav.current(200) == FUNPAY


def test_unknown_section_does_not_mutate_navigation_state():
    nav = AdminNavigation()
    assert nav.open(100, "unknown") == MAIN
    assert nav.current(100) == MAIN


def test_nested_section_cannot_open_without_its_parent():
    nav = AdminNavigation()
    assert nav.open(100, STEAM_AUTH) == MAIN
    assert nav.current(100) == MAIN


def test_nested_screen_cannot_open_from_another_top_level_section():
    nav = AdminNavigation()
    nav.open(100, FUNPAY)
    assert nav.open(100, STEAM_AUTH) == FUNPAY
    assert nav.current(100) == FUNPAY


def test_reopening_existing_parent_unwinds_nested_screen():
    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert nav.open(100, SETTINGS) == SETTINGS
    assert nav.back(100) == MAIN


def test_cancel_command_keeps_user_on_current_steam_screen():
    from admin_navigation import cancel_password_prompt

    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert cancel_password_prompt(nav, 100, "/cancel") == STEAM_AUTH
    assert nav.current(100) == STEAM_AUTH


def test_back_command_during_password_prompt_returns_to_settings():
    from admin_navigation import cancel_password_prompt

    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert cancel_password_prompt(nav, 100, "⬅️ Назад") == SETTINGS
    assert nav.current(100) == SETTINGS


def test_main_menu_command_during_password_prompt_resets_navigation():
    from admin_navigation import cancel_password_prompt

    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert cancel_password_prompt(nav, 100, "🏠 Главное меню") == MAIN
    assert nav.current(100) == MAIN


def test_ordinary_password_text_is_not_treated_as_navigation():
    from admin_navigation import cancel_password_prompt

    nav = AdminNavigation()
    nav.open(100, SETTINGS)
    nav.open(100, STEAM_AUTH)
    assert cancel_password_prompt(nav, 100, "not-a-menu-command") is None
    assert nav.current(100) == STEAM_AUTH
