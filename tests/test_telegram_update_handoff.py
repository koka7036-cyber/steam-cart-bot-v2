from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_project_file(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def test_telegram_update_handoff_is_written_before_bot_exits():
    source = read_project_file("bot.py")
    assert 'UPDATE_REQUEST_PATH = os.path.join(BASE_DIR, ".bot_update_expected_sha.txt")' in source
    assert "os.replace(temp_request, UPDATE_REQUEST_PATH)" in source
    assert "update_restart_requested = True" in source
    assert "raise SystemExit(43 if update_restart_requested else 42)" in source

    callback_start = source.index(
        '@bot.callback_query_handler(func=lambda call: bool(call.data) and call.data.startswith("bot_update_"))'
    )
    callback_end = source.index("# --- МОДУЛЬ 2:", callback_start)
    callback = source[callback_start:callback_end]
    assert "pending_bot_update_by_chat.get(chat_id) != expected_sha" in callback
    assert "subprocess.Popen(" not in callback


def test_windows_controller_updates_only_after_python_exits_and_restarts():
    runner = read_project_file("run_bot.ps1")
    python_launch = runner.index("& py -3 (Join-Path $PSScriptRoot 'bot.py')")
    update_branch = runner.index("if ($exitCode -eq 43)")
    updater_call = runner.index("-File $updateScript -WaitForBot -ExpectedSha $expectedSha")
    assert python_launch < update_branch < updater_call
    assert "while ($exitCode -eq 42)" in runner
    assert "Remove-Item -LiteralPath $requestFile" in runner


def test_updater_revalidates_expected_sha_and_has_a_check_only_mode():
    updater = read_project_file("update_bot.ps1")
    assert "if ($ExpectedSha -and $remoteSha -ne $ExpectedSha)" in updater
    assert "if ($CheckOnly)" in updater
    assert "UPDATE_AVAILABLE:" in updater
    assert "CURRENT:" in updater
    assert "GitHub returned an invalid commit SHA." in updater


def test_updater_checks_candidate_files_before_copy_and_preserves_rollback():
    updater = read_project_file("update_bot.ps1")
    assert "py -3 -m compileall -q $source.FullName" in updater
    assert "[System.Management.Automation.Language.Parser]::ParseFile" in updater
    assert "Copy failed; rolling back from" in updater
    assert "WriteAllText($Marker" in updater


def test_new_github_token_is_saved_only_after_api_and_sha_validation():
    updater = read_project_file("update_bot.ps1")
    api_index = updater.index("Invoke-RestMethod -Uri $commitUrl")
    sha_index = updater.index("GitHub returned an invalid commit SHA.")
    save_index = updater.index(
        "[CardBot.CredentialManager]::Write($CredentialTarget, 'github-readonly', $githubToken)"
    )
    assert api_index < sha_index < save_index
    assert "SteamCardsBot-GitHubReadOnly" in updater
