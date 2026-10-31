"""Regression tests for crash-safe FunPay reservation reconciliation."""

from funpay_orders import filter_reserved_assets, restore_reserved_assets


def test_pending_refund_reservation_stays_excluded_until_cache_restore():
    """A refund status alone must not make reserved assets sellable."""
    cache = {"games": {"Game": {"Card A": ["101"], "Card B": ["102"]}}}
    reservation = {
        "asset_ids": ["101"],
        "asset_locations": [{"game": "Game", "card": "Card A", "asset_id": "101"}],
    }
    orders = {
        "fp-order-123": {
            "status": "refund_review",
            "funpay_refunded": True,
            "reservation": reservation,
        }
    }

    filtered = filter_reserved_assets(cache, orders=orders)

    assert filtered["games"]["Game"]["Card A"] == []
    assert filtered["games"]["Game"]["Card B"] == ["102"]
    assert cache["games"]["Game"]["Card A"] == ["101"]


def test_restored_asset_is_available_only_after_explicit_ledger_release():
    """Cache restoration and ledger release are separate steps; order of release matters."""
    cache = {"games": {"Game": {"Card A": []}}}
    reservation = {
        "asset_ids": ["101"],
        "asset_locations": [{"game": "Game", "card": "Card A", "asset_id": "101"}],
    }
    orders = {
        "fp-order-123": {
            "status": "refund_review",
            "funpay_refunded": True,
            "reservation": reservation,
        }
    }

    restored_cache = restore_reserved_assets(cache, reservation)
    assert restored_cache is not None

    # Before the ledger drops its reservation, the card must remain excluded.
    still_reserved = filter_reserved_assets(restored_cache, orders=orders)
    assert still_reserved["games"]["Game"]["Card A"] == []

    orders["fp-order-123"]["status"] = "refunded"
    orders["fp-order-123"]["reservation"] = None
    released = filter_reserved_assets(restored_cache, orders=orders)
    assert released["games"]["Game"]["Card A"] == ["101"]
