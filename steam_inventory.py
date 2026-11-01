"""Safe pagination for the Steam Community inventory endpoint."""
from collections.abc import Callable
from typing import Any


class SteamInventoryPaginationError(RuntimeError):
    """Raised when Steam returns an incomplete or inconsistent inventory page."""


class SteamInventoryRateLimitError(RuntimeError):
    """Raised when Steam asks the client to slow down."""

    def __init__(self, message: str = "HTTP 429", retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.retry_after_seconds = parse_retry_after(retry_after)


def parse_retry_after(value: str | None, now: float | None = None) -> int | None:
    """Parse Retry-After delta-seconds or HTTP-date; never return a negative wait."""
    import math
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            current = datetime.fromtimestamp(
                now if now is not None else datetime.now(timezone.utc).timestamp(),
                tz=timezone.utc,
            )
            seconds = (retry_at.astimezone(timezone.utc) - current).total_seconds()
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    if not math.isfinite(seconds):
        return None
    return max(0, math.ceil(seconds))



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
            if (
                not isinstance(asset, dict)
                or asset.get("assetid") is None
                or asset.get("classid") is None
                or asset.get("instanceid") is None
            ):
                raise SteamInventoryPaginationError(
                    "В ответе Steam у предмета отсутствует assetid/classid/instanceid."
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
            for asset in assets:
                description_key = f"{asset['classid']}_{asset['instanceid']}"
                if description_key not in descriptions:
                    raise SteamInventoryPaginationError(
                        "Для одного или нескольких предметов Steam не вернул описание; кэш не обновлён."
                    )
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
