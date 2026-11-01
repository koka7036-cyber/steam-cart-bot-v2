from funpay_orders import count_cancelled_orders, funpay_cold_start_blockers, filter_reserved_assets, funpay_release_refund_block_reason


def test_dashboard_counts_refunded_and_cancelled_orders_once():
    orders = [
        {"status": "cancelled"},
        {"status": "offer_sent", "funpay_refunded": True},
        {"status": "refunded"},
        {"status": "completed"},
        {"status": "retry_required"},
    ]
    assert count_cancelled_orders(orders) == 3


def test_dashboard_does_not_double_count_refund_flag_and_cancelled_status():
    assert count_cancelled_orders([{"status": "cancelled", "funpay_refunded": True}]) == 1


def test_cancelled_order_is_terminal_for_cold_start():
    assert funpay_cold_start_blockers({"order": {"status": "cancelled", "reservation": None}}) == []


def test_cancelled_order_reservation_remains_hidden_until_ledger_is_cleared():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {"cancelled": {"status": "cancelled", "reservation": {"asset_ids": ["12345"]}}}
    filtered = filter_reserved_assets(cache, orders=orders)
    assert filtered["games"]["Game"]["Card"] == ["23456"]

def test_cancelled_order_without_reservation_releases_no_additional_assets():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {
        "cancelled": {
            "status": "cancelled",
            "reservation": None,
        }
    }

    filtered = filter_reserved_assets(cache, orders=orders)

    assert filtered["games"]["Game"]["Card"] == ["12345", "23456"]


def test_cancelled_order_with_reservation_blocks_cold_start():
    assert funpay_cold_start_blockers({
        "cancelled_with_legacy_reservation": {
            "status": "cancelled",
            "reservation": {"asset_ids": ["12345"]},
        }
    }) == [("cancelled_with_legacy_reservation", "cancelled")]



def test_fprelease_refund_guard_blocks_refund_flag_without_offer_id():
    record = {
        "status": "review",
        "funpay_refunded": True,
        "reservation": {"asset_ids": ["123"]},
    }
    reason = funpay_release_refund_block_reason(record)
    assert isinstance(reason, str) and "возврат FunPay" in reason


def test_fprelease_refund_guard_blocks_all_refund_statuses():
    for status in ("refund_review", "refunded", "refunded_cancelled"):
        reason = funpay_release_refund_block_reason({
            "status": status,
            "funpay_refunded": False,
            "reservation": {"asset_ids": ["123"]},
        })
        assert isinstance(reason, str) and reason.strip()


def test_fprelease_refund_guard_allows_normal_unreffunded_reservation():
    assert funpay_release_refund_block_reason({
        "status": "reserved",
        "funpay_refunded": False,
        "reservation": {"asset_ids": ["123"]},
    }) is None


def test_fprelease_refund_guard_rejects_invalid_record():
    assert funpay_release_refund_block_reason(None)


def test_funpay_ledger_integrity_notifier_is_explicitly_fail_closed():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    start = source.index("def notify_funpay_ledger_integrity(")
    end = source.index("\n\ndef load_funpay_orders()", start)
    notifier = source[start:end]

    assert "повреждён или недоступен" in notifier
    assert "не заменялся пустым" in notifier
    assert "Резервирование, обработка заказов и выдача остановлены" in notifier
    assert "bot.send_message(admin_id, message)" in notifier
    assert "logging.critical(" in notifier


def test_funpay_background_worker_notifies_admin_and_never_rebuilds_corrupt_ledger():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    start = source.index("def funpay_background_worker():")
    end = source.index("# --- МОДУЛЬ 3:", start)
    worker = source[start:end]

    assert "except FunPayLedgerIntegrityError:" in worker
    assert 'notify_funpay_ledger_integrity(db.get("admin_id"), "восстановление после перезапуска")' in worker
    assert 'load_funpay_orders()' not in worker.split("last_ping_time = 0", 1)[1].split("while True:", 1)[0]
    assert "load_funpay_order_ledger" not in worker
    assert "        return\n    except Exception:" in worker



def test_funpay_admin_commands_catch_ledger_integrity_without_skipping_normal_paths():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    expected = {
        "def funpay_cold_start_cmd(message):": 'notify_funpay_ledger_integrity(message.chat.id, "/fpcoldstart")',
        "def funpay_offer_resolve_cmd(message):": 'notify_funpay_ledger_integrity(message.chat.id, "/fpofferresolve")',
        "def funpay_release_cmd(message):": 'notify_funpay_ledger_integrity(message.chat.id, "/fprelease")',
        "def show_funpay_dashboard(message):": 'notify_funpay_ledger_integrity(message.chat.id, "панель FunPay")',
    }
    for function, notification in expected.items():
        start = source.index(function)
        next_handler = source.find("\\n@bot.", start + len(function))
        block = source[start:next_handler if next_handler >= 0 else len(source)]
        assert "except FunPayLedgerIntegrityError:" in block
        assert notification in block
        assert "        return\\n    except" not in block

    cold_start_start = source.index("def funpay_cold_start_cmd")
    cold_start_end = source.index("\\n@bot.", cold_start_start)
    cold_start = source[cold_start_start:cold_start_end]
    assert "funpay_cold_start_blockers(orders)" in cold_start

    offer_start = source.index("def funpay_offer_resolve_cmd")
    offer_end = source.index("\\n@bot.", offer_start)
    assert 'record["status"] = "completed"' in source[offer_start:offer_end]

    release_start = source.index("def funpay_release_cmd")
    release_end = source.index("\\n@bot.", release_start)
    release = source[release_start:release_end]
    assert "funpay_release_refund_block_reason(record)" in release
    assert 'record["status"] = "cancelled"' in release
