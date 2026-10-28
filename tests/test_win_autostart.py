from pathlib import Path


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def test_windows_auto_start_uses_scheduled_task_helper_not_registry_toggle():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    section = source.split("# --- МОДУЛЬ 1: АВТОЗАПУСК WINDOWS ---", 1)[1].split(
        "# --- МОДУЛЬ 2:", 1
    )[0]

    assert 'AUTOSTART_TASK_NAME = "CardBot - AutoStart"' in section
    assert "AUTOSTART_PS_SCRIPT_PATH" in section and "toggle_autostart_task.ps1" in section
    assert "Get-ScheduledTask" in section
    assert "winreg.DeleteValue" not in section
    assert "toggle_autostart()" in section


def test_autostart_command_checks_admin_chat_and_user_identity():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    handler = source.split('def handle_toggle_autostart(message):', 1)[1].split(
        '@bot.message_handler(commands=["fp"])', 1
    )[0]

    assert 'message.chat.id != db.get("admin_id")' in handler
    assert 'message.from_user.id != db.get("admin_id")' in handler


def test_task_helper_removes_only_legacy_autostart_registry_value():
    helper = Path(__file__).resolve().parents[1] / "toggle_autostart_task.ps1"
    source = helper.read_text(encoding="utf-8")

    assert "Software\\Microsoft\\Windows\\CurrentVersion\\Run" in source
    assert "CardBotFarmAutostart" in source
    assert "DeleteValue" in source
    assert "DeleteSubKey" not in source
    assert "Register-ScheduledTask" in source
    assert "Disable-ScheduledTask" in source


def test_status_recognizes_legacy_registry_autostart_when_task_is_missing():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    section = source.split("# --- МОДУЛЬ 1: АВТОЗАПУСК WINDOWS ---", 1)[1].split(
        "# --- МОДУЛЬ 2:", 1
    )[0]

    assert "CardBotFarmAutostart" in section
    assert "CurrentVersion\\\\Run" in section


def test_task_helper_turns_off_legacy_autostart_before_creating_new_task():
    helper = Path(__file__).resolve().parents[1] / "toggle_autostart_task.ps1"
    source = helper.read_text(encoding="utf-8")

    assert "$legacyEnabled" in source
    assert "$null -eq $existing -and $legacyEnabled" in source
