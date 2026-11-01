from funpay_orders import count_cancelled_orders, funpay_cold_start_blockers, filter_reserved_assets


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


def test_cancelled_order_reservation_is_not_kept_as_open_stock_reservation():
    cache = {"games": {"Game": {"Card": ["asset-1", "asset-2"]}}}
    orders = {"cancelled": {"status": "cancelled", "reservation": {"asset_ids": ["asset-1"]}}}
    filtered = filter_reserved_assets(cache, orders=orders)
    assert filtered["games"]["Game"]["Card"] == ["asset-1", "asset-2"]


def test_cancelled_order_with_legacy_reservation_keeps_assets_hidden():
    cache = {"games": {"Game": {"Card": ["asset-1", "asset-2"]}}}
    orders = {
        "cancelled": {
            "status": "cancelled",
            "reservation": {"asset_ids": ["asset-1"]},
        }
    }

    filtered = filter_reserved_assets(cache, orders=orders)

    assert filtered["games"]["Game"]["Card"] == ["asset-2"]


def test_cancelled_order_without_reservation_releases_no_additional_assets():
    cache = {"games": {"Game": {"Card": ["asset-1", "asset-2"]}}}
    orders = {
        "cancelled": {
            "status": "cancelled",
            "reservation": None,
        }
    }

    filtered = filter_reserved_assets(cache, orders=orders)

    assert filtered["games"]["Game"]["Card"] == ["asset-1", "asset-2"]
