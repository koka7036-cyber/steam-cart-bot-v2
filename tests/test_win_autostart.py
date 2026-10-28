from pathlib import Path


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def test_windows_auto_start_uses_scheduled_task_helper_not_registry_toggle():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    section = source.split("# --- МОДУЛЬ 1: АВТОЗАПУСК WINDOWS ---", 1)[1].split(
        "# --- МОДУЛЬ 2:", 1
    )[0]

    assert 'AUTOSTART_TASK_NAME = "CardBot - AutoStart"' in section
    assert "AUTOSTART_PS_SCRIPT_PATH" in section and "toggle_autostart_task.ps1" in section
    assert "subprocess.run" in section
    assert "winreg.DeleteValue" not in section
    assert "toggle_autostart()" in section


def test_autostart_command_checks_admin_chat_and_user_identity():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    handler = source.split('def handle_toggle_autostart(message):', 1)[1].split(
        '@bot.message_handler(commands=["fp"])', 1
    )[0]

    assert "message.chat.id != db.get(\"admin_id\")" in handler
    assert "message.from_user.id != db.get(\"admin_id\")" in handler
