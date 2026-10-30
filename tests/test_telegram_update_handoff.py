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


def test_autostart_embedded_helper_matches_utf8_bom_script_and_refreshes_stale_copy():
    bot_source = read_project_file("bot.py")
    helper_file = read_project_file("toggle_autostart_task.ps1")
    marker = '_AUTOSTART_HELPER_FALLBACK = r"""'
    start = bot_source.index(marker) + len(marker)
    end = bot_source.index('"""', start)
    embedded = bot_source[start:end].replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    deployed = helper_file.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")

    assert embedded == deployed
    assert 'encoding="utf-8-sig"' in bot_source
    assert "os.replace(temp_path, helper_path)" in bot_source
    assert "New-Object System.Text.UTF8Encoding($false)" in deployed


def test_update_check_lock_is_released_on_startup_and_worker_failures():
    source = read_project_file("bot.py")
    start = source.index("def _release_bot_update_lock()")
    end = source.index("@bot.callback_query_handler", start)
    update_block = source[start:end]
    assert "def _release_bot_update_lock()" in update_block
    assert "finally:\n        release_once()" in update_block
    assert "status = bot.send_message(" in update_block
    assert "worker.start()" in update_block
    assert "except Exception:\n        _release_bot_update_lock()" in update_block


def test_legacy_warehouse_button_label_routes_to_stock_menu():
    source = read_project_file("bot.py")
    assert '"📦 Склад": "stock"' in source


def test_funpay_watcher_selects_last_customer_message_and_bounds_telegram_notice():
    source = read_project_file("bot.py")
    start = source.index("def funpay_check_unread_chats")
    end = source.index("def funpay_background_worker", start)
    watcher = source[start:end]
    assert "extract_last_customer_message_fragment(detail_html)" in watcher
    assert "if not last_message_html or (not full_text.strip() and not attachment_href and not has_file):" in watcher
    assert "compact_funpay_text(safe_text, max_chars=900)" in watcher
    assert "payment_events = extract_paid_order_events(detail_html)" in watcher
    assert "download_text_attachment(" in watcher
    assert 'input_kind = "text_attachment"' in watcher
    assert "seen_input_events[node_id] = input_signature" in watcher
    assert "is_funpay_refund_notification(payment_text)" in watcher



def test_funpay_order_flow_supports_text_attachments_refunds_and_exact_admin_selection():
    source = read_project_file("bot.py")
    assert "def register_funpay_refund(" in source
    assert "restore_reservation_to_cache(reservation)" in source
    assert 'record["status"] = "refund_review"' in source
    assert "selected_order_key=selected_order_key" in source
    assert 'call.data.startswith("fporderselect:")' in source
    assert "pending_funpay_input_selections" in source
    assert "Вложение не распознано как текстовый файл FunPay" in source


def test_telegram_polling_uses_supported_sync_timeout_arguments():
    source = read_project_file("bot.py")
    polling_line = next(line for line in source.splitlines() if "bot.infinity_polling(" in line)
    assert "timeout=45" in polling_line
    assert "skip_pending=False" in polling_line
    assert "request_timeout" not in polling_line
    assert "apihelper.SESSION_TIME_TO_LIVE = 5 * 60" in source


def test_refunded_orders_are_not_recreated_from_later_payment_history():
    source = read_project_file("bot.py")
    start = source.index("def register_funpay_payment")
    end = source.index("def register_funpay_refund", start)
    payment = source[start:end]
    assert 'if order_number and str(order_number).upper() in refunds:' in payment
    assert 'return None, False' in payment


def test_funpay_watcher_uses_structured_history_and_numeric_author_filtering():
    source = read_project_file("bot.py")
    start = source.index("def funpay_check_unread_chats")
    end = source.index("def handle_funpay_order_selection", start)
    watcher = source[start:end]

    assert 'https://funpay.com/chat/history' in watcher
    assert "parse_funpay_history_payload(" in watcher
    assert 'timeline["system_events"]' in watcher
    assert 'timeline["latest_buyer_message"]' in watcher
    assert "message_id=latest_buyer_message.get('id')" in watcher
    assert "extract_paid_order_events(" not in watcher
    assert "extract_last_customer_message_fragment(" not in watcher


def test_funpay_payment_events_are_only_accepted_from_structured_system_author():
    source = read_project_file("funpay_orders.py")
    parser_start = source.index("def parse_funpay_history_payload")
    parser_end = source.index("def extract_last_customer_message_fragment", parser_start)
    parser = source[parser_start:parser_end]

    assert "author_id == 0" in parser
    assert "author_id == buyer_id" in parser
    assert 'latest = messages[-1]' in parser
    assert 'latest_buyer = latest if latest and latest["is_buyer"] else None' in parser

