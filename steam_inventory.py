"""Safe pagination for the Steam Community inventory endpoint."""
from collections.abc import Callable
from typing import Any


class SteamInventoryPaginationError(RuntimeError):
    """Raised when Steam returns an incomplete or inconsistent inventory page."""


class SteamInventoryRateLimitError(RuntimeError):
    """Raised when Steam asks the client to slow down."""


def collect_inventory_pages(
    fetch_page: Callable[[str | None], dict[str, Any]],
    *,
    max_pages: int = 100,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fetch and combine every inventory page, failing closed on partial results.

    fetch_page receives None for the first page and the previous page's
    last_assetid for each subsequent request. No partial result is returned
    when pagination fails, a cursor repeats, or the page limit is exceeded.
    """
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages должен быть положительным целым числом")

    assets: list[dict[str, Any]] = []
    descriptions: dict[str, dict[str, Any]] = {}
    seen_assets: dict[str, dict[str, Any]] = {}
    seen_cursors: set[str] = set()
    cursor: str | None = None

    for _page_number in range(1, max_pages + 1):
        page = fetch_page(cursor)
        if not isinstance(page, dict) or not page.get("success"):
            raise SteamInventoryPaginationError(
                "Steam вернул неуспешную страницу инвентаря."
            )

        page_assets = page.get("assets", [])
        page_descriptions = page.get("descriptions", [])
        if not isinstance(page_assets, list) or not isinstance(page_descriptions, list):
            raise SteamInventoryPaginationError(
                "Steam вернул некорректный формат assets/descriptions."
            )

        for asset in page_assets:
            if not isinstance(asset, dict) or asset.get("assetid") is None:
                raise SteamInventoryPaginationError(
                    "В ответе Steam найден предмет без корректного assetid."
                )
            asset_id = str(asset["assetid"]).strip()
            if not asset_id.isdigit():
                raise SteamInventoryPaginationError(
                    "Steam вернул некорректный assetid; кэш не обновлён."
                )
            previous_asset = seen_assets.get(asset_id)
            if previous_asset is not None:
                # Some inventory implementations may repeat the boundary item.
                # Ignore an identical copy, but reject conflicting data.
                if previous_asset != asset:
                    raise SteamInventoryPaginationError(
                        "Steam вернул разные данные для одного assetid; кэш не обновлён."
                    )
                continue
            seen_assets[asset_id] = asset
            assets.append(asset)

        for description in page_descriptions:
            if not isinstance(description, dict):
                raise SteamInventoryPaginationError(
                    "Steam вернул некорректное описание предмета."
                )
            class_id = description.get("classid")
            instance_id = description.get("instanceid")
            if class_id is None or instance_id is None:
                raise SteamInventoryPaginationError(
                    "В описании предмета Steam отсутствуют classid/instanceid."
                )
            descriptions[f"{class_id}_{instance_id}"] = description

        has_more = page.get("more_items") in (1, True, "1")
        if not has_more:
            return assets, descriptions

        next_cursor = str(page.get("last_assetid") or "").strip()
        if not next_cursor.isdigit():
            raise SteamInventoryPaginationError(
                "Steam сообщил о следующей странице, но не вернул last_assetid."
            )
        if next_cursor == cursor or next_cursor in seen_cursors:
            raise SteamInventoryPaginationError(
                "Steam повторил курсор пагинации; загрузка остановлена."
            )

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    raise SteamInventoryPaginationError(
        f"Превышен лимит страниц инвентаря Steam ({max_pages}); кэш не обновлён."
    )
