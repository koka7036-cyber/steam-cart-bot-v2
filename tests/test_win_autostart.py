from pathlib import Path


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def test_windows_autostart_status_and_toggle_use_scheduled_task_not_registry():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    section = source.split("# --- МОДУЛЬ 1: АВТОЗАПУСК WINDOWS ---", 1)[1].split(
        "# --- МОДУЛЬ 2:", 1
    )[0]

    assert "schtasks" in section
    assert "CardBot - AutoStart" in section
    assert "winreg." not in section
    assert "subprocess.run" in section
    assert "start.bat" in section


def test_autostart_command_checks_admin_user_identity():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    handler = source.split('def handle_toggle_autostart(message):', 1)[1].split(
        '@bot.message_handler(commands=["fp"])', 1
    )[0]

    assert "message.chat.id != db[\"admin_id\"]" in handler
    assert "message.from_user.id != db[\"admin_id\"]" in handler
