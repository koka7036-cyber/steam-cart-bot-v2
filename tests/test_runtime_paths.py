from pathlib import Path

from runtime_paths import resolve_runtime_paths


def test_runtime_paths_are_based_on_script_not_current_directory(tmp_path, monkeypatch):
    project = tmp_path / "folder with spaces" / "bot"
    project.mkdir(parents=True)
    script = project / "bot.py"
    script.write_text("# test fixture", encoding="utf-8")
    elsewhere = tmp_path / "unrelated-working-directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    base_dir, data_dir = resolve_runtime_paths(script)

    assert base_dir == project.resolve()
    assert data_dir == project.resolve()
    assert (data_dir / "vouchers.json").parent == project.resolve()


def test_moving_complete_folder_keeps_default_data_location(tmp_path):
    original = tmp_path / "before move" / "bot"
    original.mkdir(parents=True)
    script = original / "bot.py"
    script.write_text("# test fixture", encoding="utf-8")
    (original / "vouchers.json").write_text("[]", encoding="utf-8")

    moved = tmp_path / "after move" / "bot"
    moved.parent.mkdir(parents=True)
    original.rename(moved)

    base_dir, data_dir = resolve_runtime_paths(moved / "bot.py")

    assert base_dir == moved.resolve()
    assert data_dir == moved.resolve()
    assert (data_dir / "vouchers.json").read_text(encoding="utf-8") == "[]"


def test_configured_data_directory_is_respected(tmp_path):
    project = tmp_path / "bot"
    project.mkdir()
    configured = tmp_path / "separate data" / "cardbot"

    base_dir, data_dir = resolve_runtime_paths(project / "bot.py", configured)

    assert base_dir == project.resolve()
    assert data_dir == configured.resolve()
    assert data_dir.is_dir()
