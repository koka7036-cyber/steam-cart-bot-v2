"""Regression tests for safe Steam inventory pagination."""
import pytest

from steam_inventory import (
    SteamInventoryPaginationError,
    collect_inventory_pages,
)


def asset(asset_id):
    return {"assetid": str(asset_id), "classid": "100", "instanceid": "0"}


def description(name):
    return {
        "classid": "100",
        "instanceid": "0",
        "market_hash_name": name,
        "tags": [],
    }


def test_collect_inventory_pages_returns_single_page():
    calls = []

    def fetch_page(cursor):
        calls.append(cursor)
        return {
            "success": 1,
            "assets": [asset(1), asset(2)],
            "descriptions": [description("Card")],
            "more_items": 0,
        }

    assets, descriptions = collect_inventory_pages(fetch_page)

    assert calls == [None]
    assert [item["assetid"] for item in assets] == ["1", "2"]
    assert descriptions["100_0"]["market_hash_name"] == "Card"


def test_collect_inventory_pages_follows_last_assetid_and_merges_pages():
    calls = []
    pages = [
        {
            "success": 1,
            "assets": [asset(1)],
            "descriptions": [description("Card A")],
            "more_items": 1,
            "last_assetid": "1",
        },
        {
            "success": 1,
            "assets": [asset(2)],
            "descriptions": [
                {
                    "classid": "200",
                    "instanceid": "0",
                    "market_hash_name": "Card B",
                    "tags": [],
                }
            ],
            "more_items": 0,
        },
    ]

    def fetch_page(cursor):
        calls.append(cursor)
        return pages.pop(0)

    assets, descriptions = collect_inventory_pages(fetch_page)

    assert calls == [None, "1"]
    assert [item["assetid"] for item in assets] == ["1", "2"]
    assert set(descriptions) == {"100_0", "200_0"}


def test_collect_inventory_pages_rejects_missing_next_cursor():
    with pytest.raises(SteamInventoryPaginationError, match="не вернул last_assetid"):
        collect_inventory_pages(
            lambda cursor: {
                "success": 1,
                "assets": [asset(1)],
                "descriptions": [description("Card")],
                "more_items": 1,
            }
        )


def test_collect_inventory_pages_rejects_repeated_cursor():
    pages = [
        {
            "success": 1,
            "assets": [asset(1)],
            "descriptions": [description("Card")],
            "more_items": 1,
            "last_assetid": "1",
        },
        {
            "success": 1,
            "assets": [asset(2)],
            "descriptions": [description("Card")],
            "more_items": 1,
            "last_assetid": "1",
        },
    ]

    with pytest.raises(SteamInventoryPaginationError, match="повторил курсор"):
        collect_inventory_pages(lambda cursor: pages.pop(0))


def test_collect_inventory_pages_deduplicates_identical_page_boundary_assets():
    pages = [
        {
            "success": 1,
            "assets": [asset(1)],
            "descriptions": [description("Card")],
            "more_items": 1,
            "last_assetid": "1",
        },
        {
            "success": 1,
            "assets": [asset(1), asset(2)],
            "descriptions": [description("Card")],
            "more_items": 0,
        },
    ]

    assets, _ = collect_inventory_pages(lambda cursor: pages.pop(0))

    assert [item["assetid"] for item in assets] == ["1", "2"]


def test_collect_inventory_pages_rejects_conflicting_duplicate_asset_ids():
    pages = [
        {
            "success": 1,
            "assets": [asset(1)],
            "descriptions": [description("Card")],
            "more_items": 1,
            "last_assetid": "1",
        },
        {
            "success": 1,
            "assets": [{**asset(1), "classid": "999"}],
            "descriptions": [description("Card")],
            "more_items": 0,
        },
    ]

    with pytest.raises(SteamInventoryPaginationError, match="разные данные для одного assetid"):
        collect_inventory_pages(lambda cursor: pages.pop(0))


def test_collect_inventory_pages_does_not_return_partial_data_at_page_limit():
    with pytest.raises(SteamInventoryPaginationError, match="Превышен лимит страниц"):
        collect_inventory_pages(
            lambda cursor: {
                "success": 1,
                "assets": [asset(1)],
                "descriptions": [description("Card")],
                "more_items": 1,
                "last_assetid": str(1 if cursor is None else int(cursor) + 1),
            },
            max_pages=1,
        )


def test_collect_inventory_pages_rejects_unsuccessful_page():
    with pytest.raises(SteamInventoryPaginationError, match="неуспешную страницу"):
        collect_inventory_pages(lambda cursor: {"success": 0})


def test_collect_inventory_pages_rejects_invalid_asset_ids():
    with pytest.raises(SteamInventoryPaginationError, match="некорректный assetid"):
        collect_inventory_pages(
            lambda cursor: {
                "success": 1,
                "assets": [{"assetid": "not-a-number", "classid": "100", "instanceid": "0"}],
                "descriptions": [],
                "more_items": 0,
            }
        )

def test_collect_inventory_pages_raises_when_a_later_page_fails():
    def fetch_page(cursor):
        if cursor is None:
            return {
                "success": 1,
                "assets": [asset(1)],
                "descriptions": [description("Card")],
                "more_items": 1,
                "last_assetid": "1",
            }
        raise RuntimeError("second page unavailable")

    with pytest.raises(RuntimeError, match="second page unavailable"):
        collect_inventory_pages(fetch_page)


def test_collect_inventory_pages_rejects_assets_without_matching_descriptions():
    with pytest.raises(SteamInventoryPaginationError, match="не вернул описание"):
        collect_inventory_pages(
            lambda cursor: {
                "success": 1,
                "assets": [asset(1)],
                "descriptions": [],
                "more_items": 0,
            }
        )


def test_collect_inventory_pages_rejects_assets_without_class_or_instance_id():
    with pytest.raises(SteamInventoryPaginationError, match="assetid/classid/instanceid"):
        collect_inventory_pages(
            lambda cursor: {
                "success": 1,
                "assets": [{"assetid": "1", "classid": "100"}],
                "descriptions": [description("Card")],
                "more_items": 0,
            }
        )


def test_retry_after_seconds_accepts_delta_seconds():
    from steam_inventory import retry_after_seconds

    assert retry_after_seconds("45") == 45


def test_retry_after_seconds_accepts_http_date():
    from datetime import datetime, timezone
    from steam_inventory import retry_after_seconds

    now = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert retry_after_seconds("Sun, 01 Nov 2026 10:02:30 GMT", now=now) == 150


def test_retry_after_seconds_uses_default_for_missing_or_invalid_value():
    from steam_inventory import DEFAULT_RETRY_AFTER_SECONDS, retry_after_seconds

    assert retry_after_seconds(None) == DEFAULT_RETRY_AFTER_SECONDS
    assert retry_after_seconds("not-a-date") == DEFAULT_RETRY_AFTER_SECONDS


def test_retry_after_seconds_clamps_extreme_values():
    from steam_inventory import MAX_RETRY_AFTER_SECONDS, retry_after_seconds

    assert retry_after_seconds("999999") == MAX_RETRY_AFTER_SECONDS
    assert retry_after_seconds("-10") == 1


