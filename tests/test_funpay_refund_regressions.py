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
