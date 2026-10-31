"""Small, dependency-free order ledger helpers for the FunPay watcher.

The ledger deliberately stores no Steam trade URL, passwords, or session data.
It records only the minimum data required to match payment notifications and
keep one reservation per order.
"""
from __future__ import annotations

import copy
import hashlib
import html
import re
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse


OPEN_STATUSES = {"awaiting_input", "input_received", "reserved", "review", "retry_required", "sending", "delivery_uncertain", "refund_review"}

def count_cancelled_orders(orders) -> int:
    """Count cancelled/refunded FunPay orders once, including legacy refund flags."""
    if isinstance(orders, dict):
        values = orders.values()
    elif isinstance(orders, (list, tuple)):
        values = orders
    else:
        return 0
    return sum(
        1 for order in values
        if isinstance(order, dict) and (
            order.get("status") in {"cancelled", "refunded", "refunded_cancelled"}
            or order.get("funpay_refunded") is True
        )
    )




def restore_reserved_assets(cache: dict, reservation: dict) -> dict | None:
    """Return a safely restored cache, or None without mutating input on invalid data.

    The reservation must contain unique asset IDs and a matching location for
    every ID. Validation completes before a copy is changed, so malformed data
    can never partially restore stock.
    """
    if not isinstance(cache, dict) or not isinstance(reservation, dict):
        return None
    games = cache.get("games")
    if not isinstance(games, dict) or not games:
        return None

    asset_ids = reservation.get("asset_ids")
    locations = reservation.get("asset_locations")
    if not isinstance(asset_ids, list) or not asset_ids:
        return None
    if not isinstance(locations, list) or not locations or len(asset_ids) != len(locations):
        return None

    normalized_ids = []
    for asset_id in asset_ids:
        value = str(asset_id)
        if not value.isdigit() or value in normalized_ids:
            return None
        normalized_ids.append(value)

    normalized_locations = []
    location_ids = []
    for item in locations:
        if not isinstance(item, dict):
            return None
        game = item.get("game")
        card = item.get("card")
        asset_id = str(item.get("asset_id", ""))
        if not isinstance(game, str) or not game.strip():
            return None
        if not isinstance(card, str) or not card.strip():
            return None
        if not asset_id.isdigit() or asset_id in location_ids:
            return None
        location_ids.append(asset_id)
        normalized_locations.append({"game": game, "card": card, "asset_id": asset_id})

    if set(normalized_ids) != set(location_ids):
        return None

    restored = copy.deepcopy(cache)
    restored_games = restored["games"]
    for item in normalized_locations:
        game_cards = restored_games.get(item["game"], {})
        if item["game"] in restored_games and not isinstance(game_cards, dict):
            return None
        if item["card"] in game_cards and not isinstance(game_cards[item["card"]], list):
            return None

    for item in normalized_locations:
        game_cards = restored_games.setdefault(item["game"], {})
        card_assets = game_cards.setdefault(item["card"], [])
        if item["asset_id"] not in [str(value) for value in card_assets]:
            card_assets.append(item["asset_id"])

    restored["total_cards"] = sum(
        len(asset_ids)
        for cards in restored_games.values()
        if isinstance(cards, dict)
        for asset_ids in cards.values()
        if isinstance(asset_ids, list)
    )
    return restored


STEAM_TRADE_URL_RE = re.compile(
    r"https?://steamcommunity\.com/tradeoffer/new/\?[^\s<>\"'\\]+",
    re.IGNORECASE,
)
_ALLOWED_TEXT_EXTENSIONS = {".txt", ".text", ".csv", ".log"}
_MAX_TEXT_ATTACHMENT_BYTES = 64 * 1024


def extract_steam_trade_url(text: str) -> str | None:
    """Extract exactly one valid Steam Trade URL; reject off-host or ambiguous input."""
    candidates = STEAM_TRADE_URL_RE.findall(html.unescape(text or ""))
    normalized = []
    for candidate in candidates:
        candidate = candidate.rstrip(".,;:!?)]}\"'")
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "steamcommunity.com"
            and parsed.path.rstrip("/") == "/tradeoffer/new"
            and query.get("partner", [""])[0].isdigit()
            and query.get("token", [""])[0]
        ):
            normalized.append(candidate)
    unique = list(dict.fromkeys(normalized))
    return unique[0] if len(unique) == 1 else None


def _is_text_filename(value: str) -> bool:
    if not value:
        return False
    path = urlparse(value).path
    return any(path.lower().endswith(ext) for ext in _ALLOWED_TEXT_EXTENSIONS)


def _is_trusted_funpay_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "funpay.com" or host.endswith(".funpay.com"))


class _AttachmentLinkParser(HTMLParser):
    """Collect only download links that look like in-chat file attachments."""

    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = {key.lower(): (value or "") for key, value in attrs}
        class_tokens = (attrs.get("class", "") + " " + attrs.get("data-type", "")).lower()
        label = " ".join(attrs.get(key, "") for key in ("title", "aria-label", "data-name", "data-filename", "download"))
        href = attrs.get("href", "")
        inherited_context = any(item[1] for item in self._stack)
        own_context = bool(re.search(r"(?:attachment|chat-msg-file|file-upload|file-attachment|chat-msg-item)", class_tokens))
        filename_hint = _is_text_filename(label) or _is_text_filename(href)
        is_file_link = tag.lower() == "a" and bool(href) and (
            inherited_context or own_context or filename_hint or "download" in attrs
        )
        if is_file_link:
            self.links.append((href, label or href))
        if tag.lower() not in self._VOID_TAGS:
            self._stack.append((tag.lower(), inherited_context or own_context))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return


class _FunPaySystemAlertParser(HTMLParser):
    """Extract standalone FunPay system alert blocks, including alerts outside chat-msg wrappers."""

    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = None
        self._depth = 0
        self.fragments = []

    @staticmethod
    def _is_system_alert(tag, attrs):
        if tag.lower() not in {"div", "section"}:
            return False
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("role", "").lower() == "alert":
            return True
        classes = set(values.get("class", "").split())
        return {"alert-with-icon", "alert-info"}.issubset(classes)

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if self._parts is None and self._is_system_alert(tag, attrs):
            self._parts = [raw]
            self._depth = 0 if tag.lower() in self._VOID_TAGS else 1
            if self._depth == 0:
                self.fragments.append(raw)
                self._parts = None
            return
        if self._parts is not None:
            self._parts.append(raw)
            if tag.lower() not in self._VOID_TAGS:
                self._depth += 1

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if self._parts is None and self._is_system_alert(tag, attrs):
            self.fragments.append(raw)
        elif self._parts is not None:
            self._parts.append(raw)

    def handle_endtag(self, tag):
        if self._parts is None:
            return
        self._parts.append(f"</{tag}>")
        self._depth -= 1
        if self._depth <= 0:
            self.fragments.append("".join(self._parts))
            self._parts = None
            self._depth = 0

    def handle_data(self, data):
        if self._parts is not None:
            self._parts.append(data)

    def handle_entityref(self, name):
        if self._parts is not None:
            self._parts.append(f"&{name};")

    def handle_charref(self, name):
        if self._parts is not None:
            self._parts.append(f"&#{name};")

    def handle_comment(self, data):
        if self._parts is not None:
            self._parts.append(f"<!--{data}-->")


def extract_funpay_system_alert_fragments(html_document: str) -> list[str]:
    """Return trusted role=alert / FunPay alert-with-icon blocks from a chat page."""
    parser = _FunPaySystemAlertParser()
    try:
        parser.feed(html_document or "")
        parser.close()
    except Exception:
        return []
    return list(parser.fragments)


class _LastChatMessageParser(HTMLParser):
    """Extract the most recent top-level FunPay chat message without mixing old text into a new attachment."""

    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _MESSAGE_CLASSES = {"chat-msg", "chat-msg-item", "chat-msg-container", "chat-msg-wrapper"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._parts = None
        self.messages = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        class_value = ""
        for key, value in attrs:
            if key.lower() == "class":
                class_value = value or ""
                break
        classes = set(class_value.split())
        is_message = (
            tag.lower() in {"div", "li"} and bool(classes & self._MESSAGE_CLASSES)
        ) or _FunPaySystemAlertParser._is_system_alert(tag, attrs)

        if self._parts is None and is_message:
            self._parts = [raw]
            self._depth = 0 if tag.lower() in self._VOID_TAGS else 1
            if self._depth == 0:
                self.messages.append(raw)
                self._parts = None
            return

        if self._parts is not None:
            self._parts.append(raw)
            if tag.lower() not in self._VOID_TAGS:
                self._depth += 1

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        class_value = ""
        for key, value in attrs:
            if key.lower() == "class":
                class_value = value or ""
                break
        classes = set(class_value.split())
        is_message = (
            tag.lower() in {"div", "li"} and bool(classes & self._MESSAGE_CLASSES)
        ) or _FunPaySystemAlertParser._is_system_alert(tag, attrs)
        if self._parts is None and is_message:
            self.messages.append(raw)
        elif self._parts is not None:
            self._parts.append(raw)

    def handle_endtag(self, tag):
        if self._parts is None:
            return
        self._parts.append(f"</{tag}>")
        self._depth -= 1
        if self._depth <= 0:
            self.messages.append("".join(self._parts))
            self._parts = None
            self._depth = 0

    def handle_data(self, data):
        if self._parts is not None:
            self._parts.append(data)

    def handle_entityref(self, name):
        if self._parts is not None:
            self._parts.append(f"&{name};")

    def handle_charref(self, name):
        if self._parts is not None:
            self._parts.append(f"&#{name};")

    def handle_comment(self, data):
        if self._parts is not None:
            self._parts.append(f"<!--{data}-->")



def extract_chat_message_fragments(html_document: str) -> list[str]:
    """Return all top-level chat message wrappers in chronological page order."""
    parser = _LastChatMessageParser()
    try:
        parser.feed(html_document or "")
        parser.close()
    except Exception:
        return []
    return list(parser.messages)


def parse_funpay_history_payload(payload: dict, expected_chat_id: str | None = None) -> dict:
    """Parse the official FunPay chat/history JSON response using numeric authors.

    FunPayAPI's public parser identifies system messages by author == 0 and the
    private-chat interlocutor from chat.node.name.split("-")[2]. Never infer a
    buyer message from CSS classes or message wording alone.
    """
    if not isinstance(payload, dict):
        raise ValueError("FunPay chat/history response is not a JSON object.")
    chat = payload.get("chat")
    if not isinstance(chat, dict):
        raise ValueError("FunPay chat/history response has no chat object.")
    node = chat.get("node")
    if not isinstance(node, dict):
        raise ValueError("FunPay chat/history response has no chat node.")
    if expected_chat_id is not None:
        returned_node_id = node.get("id")
        if returned_node_id is not None and str(returned_node_id) != str(expected_chat_id):
            raise ValueError("FunPay returned a different chat node.")

    node_name = str(node.get("name") or "")
    name_parts = node_name.split("-")
    buyer_id = None
    if len(name_parts) >= 3 and name_parts[2].isdigit():
        buyer_id = int(name_parts[2])

    raw_messages = chat.get("messages")
    if not isinstance(raw_messages, list):
        raise ValueError("FunPay chat history messages are missing or invalid.")

    messages = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        try:
            author_id = int(raw.get("author"))
        except (TypeError, ValueError):
            author_id = None
        message_id_raw = raw.get("id")
        try:
            message_id = int(message_id_raw)
        except (TypeError, ValueError):
            message_id = None
        fragment = raw.get("html")
        if not isinstance(fragment, str):
            fragment = ""
        text = compact_funpay_text(fragment)
        messages.append({
            "id": message_id,
            "author_id": author_id,
            "html": fragment,
            "text": text,
            "is_system": author_id == 0,
            "is_buyer": buyer_id is not None and author_id == buyer_id,
        })

    # FunPayAPI preserves the API's message order; sorting numeric IDs makes
    # the newest-event decision explicit and protects against reordered JSON.
    if messages and all(item["id"] is not None for item in messages):
        messages.sort(key=lambda item: item["id"])

    system_events = [
        item for item in messages
        if item["is_system"] and item["text"]
    ]
    latest = messages[-1] if messages else None
    latest_buyer = latest if latest and latest["is_buyer"] else None

    return {
        "chat_id": str(expected_chat_id) if expected_chat_id is not None else str(node.get("id") or ""),
        "node_name": node_name,
        "buyer_id": buyer_id,
        "messages": messages,
        "system_events": system_events,
        "latest_message": latest,
        "latest_buyer_message": latest_buyer,
    }


def extract_last_customer_message_fragment(html_document: str) -> str | None:
    """Return the latest timeline event only when it was authored by the buyer.

    A system alert at the end of the chat must not cause an older buyer URL or
    attachment to be replayed as if it were a new message.
    """
    fragments = extract_chat_message_fragments(html_document)
    if not fragments:
        return None
    latest = fragments[-1]
    return None if is_funpay_system_message(latest) else latest


def compact_funpay_text(value: str, max_chars: int | None = None) -> str:
    """Convert an HTML fragment to compact visible text without layout whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars is not None and max_chars >= 0 and len(text) > max_chars:
        suffix = "… [сообщение сокращено]"
        text = text[:max(0, max_chars - len(suffix))].rstrip() + suffix
    return text


def _safe_attachment_response_diagnostic(response) -> str:
    """Describe an unexpected HTML attachment response without leaking URLs or content."""
    status = getattr(response, "status_code", None)
    final_url = getattr(response, "url", "") or ""
    parsed = urlparse(final_url)
    safe_path = parsed.path[:120] or "/"
    history = getattr(response, "history", ()) or ()
    redirect_codes = ",".join(
        str(getattr(item, "status_code", "?")) for item in history[:5]
    ) or "none"
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
    login_path = bool(re.search(r"(?:login|auth|signin|account)", safe_path, re.IGNORECASE))
    return (
        f"HTTP={status if status is not None else 'unknown'}; "
        f"path={safe_path}; redirects={redirect_codes}; "
        f"content_type={content_type or 'unknown'}; login_path={'yes' if login_path else 'no'}"
    )


def download_text_attachment(session, attachment_url: str,
                            max_bytes: int = _MAX_TEXT_ATTACHMENT_BYTES) -> str:
    """Download one small, trusted FunPay text attachment and decode it safely.

    Redirects outside FunPay, HTML/login pages, oversized files and binary data
    are rejected before a trade URL can be extracted from the content. Unexpected
    HTML diagnostics contain only status/path/redirect metadata, never query
    strings, cookies, response body, or buyer-provided trade URLs.
    """
    if not _is_trusted_funpay_url(attachment_url):
        raise ValueError("Ссылка на вложение находится вне домена FunPay.")

    response = session.get(attachment_url, timeout=10, stream=True)
    try:
        response.raise_for_status()
        final_url = getattr(response, "url", attachment_url) or attachment_url
        if not _is_trusted_funpay_url(final_url):
            raise ValueError("FunPay перенаправил скачивание на недоверенный домен.")

        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("Content-Type", "")).lower()
        if "text/html" in content_type:
            diagnostic = _safe_attachment_response_diagnostic(response)
            raise ValueError(
                "FunPay вернул HTML вместо текстового файла. "
                f"Диагностика: {diagnostic}"
            )

        content_length = str(headers.get("Content-Length", "")).strip()
        if content_length.isdigit() and int(content_length) > max_bytes:
            raise ValueError(f"Текстовый файл превышает лимит {max_bytes} байт.")

        payload = bytearray()
        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            chunks = iterator(chunk_size=8192)
        else:
            chunks = (getattr(response, "content", b""),)

        for chunk in chunks:
            if not chunk:
                continue
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise ValueError(f"Текстовый файл превышает лимит {max_bytes} байт.")

        return decode_text_attachment(bytes(payload), max_bytes=max_bytes)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def extract_last_chat_message_fragment(html_document: str) -> str | None:
    """Return only the newest chat message wrapper, so an older URL cannot trigger delivery for a newer file."""
    parser = _LastChatMessageParser()
    try:
        parser.feed(html_document or "")
        parser.close()
    except Exception:
        return None
    return parser.messages[-1] if parser.messages else None



def extract_paid_order_events(html_document: str) -> list[tuple[str, str]]:
    """Return authenticated system payment alerts, whether or not they use chat-msg wrappers.

    FunPay can render its grey payment notification as a standalone alert block
    outside the normal chat message wrappers. Include those alerts but never
    infer payment from ordinary buyer-authored message text.
    """
    candidates = extract_chat_message_fragments(html_document)
    candidates.extend(extract_funpay_system_alert_fragments(html_document))
    events = []
    seen_text = set()
    for fragment in candidates:
        if not is_funpay_system_message(fragment):
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
        text = re.sub(r"\s+", " ", text).strip()
        signature = text.casefold()
        if text and signature not in seen_text:
            seen_text.add(signature)
            events.append((fragment, text))
    return events

def extract_text_attachment_href(html_fragment: str, base_url: str) -> str | None:
    """Return one trusted FunPay-hosted text attachment URL from message HTML.

    A single matching attachment is required. External hosts, unrelated links,
    and ambiguous multiple attachments are rejected.
    """
    parser = _AttachmentLinkParser()
    try:
        parser.feed(html_fragment or "")
        parser.close()
    except Exception:
        return None
    candidates = []
    for href, _label in parser.links:
        resolved = urljoin(base_url, html.unescape(href.strip()))
        if _is_trusted_funpay_url(resolved):
            candidates.append(resolved)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


def decode_text_attachment(data: bytes, max_bytes: int = _MAX_TEXT_ATTACHMENT_BYTES) -> str:
    """Decode a small plain-text attachment; reject oversized or binary files."""
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Вложение не является двоичными данными.")
    if not data:
        raise ValueError("Текстовый файл пуст.")
    if len(data) > max_bytes:
        raise ValueError(f"Текстовый файл превышает лимит {max_bytes} байт.")
    payload = bytes(data)
    # UTF-16 must be detected by its BOM; otherwise CP1251's single-byte decoder
    # can parse UTF-16/incorrect binary bytes into plausible-looking gibberish.
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16",)
    else:
        # Do not guess UTF-16 without a BOM; arbitrary binary bytes can decode as gibberish.
        encodings = ("utf-8-sig", "cp1251")
    last_error = None
    for encoding in encodings:
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        if "\x00" in text:
            continue
        bad_controls = sum(1 for char in text if ord(char) < 32 and char not in "\r\n\t")
        if bad_controls:
            continue
        if text.strip():
            return text
    raise ValueError("Не удалось прочитать файл как обычный текст UTF-8/UTF-16/Windows-1251.") from last_error


def filter_reserved_assets(cache_data: dict, orders: dict | None = None,
                          vouchers: dict | None = None) -> dict:
    """Return a stock cache with assets belonging to pending/uncertain offers removed."""
    if not isinstance(cache_data, dict):
        return {}
    orders = orders if isinstance(orders, dict) else {}
    vouchers = vouchers if isinstance(vouchers, dict) else {}

    reserved_ids = set()
    for record in orders.values():
        if not isinstance(record, dict) or record.get("status") == "cancelled":
            continue
        reservation = record.get("reservation")
        if isinstance(reservation, dict):
            reserved_ids.update(
                str(asset_id) for asset_id in reservation.get("asset_ids", [])
                if str(asset_id)
            )

    reserved_voucher_states = {"sending", "uncertain", "sent", "created_unconfirmed"}
    for voucher in vouchers.values():
        if not isinstance(voucher, dict):
            continue
        if voucher.get("delivery_state") in reserved_voucher_states or (
            voucher.get("used") and voucher.get("trade_offer_id")
        ):
            reserved_ids.update(
                str(asset_id) for asset_id in voucher.get("reserved_asset_ids", [])
                if str(asset_id)
            )

    filtered = dict(cache_data)
    filtered_games = {}
    games = cache_data.get("games", {})
    if isinstance(games, dict):
        for game_name, cards in games.items():
            if not isinstance(cards, dict):
                continue
            filtered_cards = {}
            for card_name, asset_ids in cards.items():
                if not isinstance(asset_ids, list):
                    continue
                filtered_cards[card_name] = [
                    str(asset_id) for asset_id in asset_ids
                    if str(asset_id) not in reserved_ids
                ]
            filtered_games[game_name] = filtered_cards
    filtered["games"] = filtered_games
    filtered["total_cards"] = sum(
        len(asset_ids) for cards in filtered_games.values() for asset_ids in cards.values()
    )
    return filtered


def voucher_redemption_block_reason(voucher: dict) -> str | None:
    """Reject another redemption if a prior Steam offer may already exist."""
    if not isinstance(voucher, dict):
        return "Запись кода повреждена; автоматическая выдача небезопасна."
    state = str(voucher.get("delivery_state") or "").lower()
    if voucher.get("trade_offer_id") or state in {
        "sending", "uncertain", "sent", "created_unconfirmed"
    }:
        return (
            "У кода есть созданное или потенциально созданное Steam-предложение. "
            "Повторная выдача заблокирована, чтобы не отправить карточки дважды; проверь историю Steam."
        )
    if voucher.get("reserved_asset_ids") and state != "failed":
        return (
            "У кода есть зарезервированные карточки. Сначала проверь состояние предыдущей операции в Steam."
        )
    return None


def voucher_reset_block_reason(voucher: dict) -> str | None:
    """Reject a manual code reset when a Steam offer may already exist or the code is consumed."""
    offer_block = voucher_redemption_block_reason(voucher)
    if offer_block:
        return offer_block
    if voucher.get("used"):
        return (
            "Код уже отмечен использованным. Автоматический сброс запрещён: сначала вручную "
            "убедись, что предложение не создавалось и карточки вернулись в инвентарь."
        )
    return None


def funpay_cold_start_blockers(orders: dict) -> list[tuple[str, str]]:
    """Return unresolved FunPay orders that must stay in the journal to protect reservations."""
    blockers = []
    if not isinstance(orders, dict):
        return [("unknown", "invalid_ledger")]
    for key, record in orders.items():
        if not isinstance(record, dict):
            blockers.append((str(key), "invalid_record"))
            continue
        status = str(record.get("status", "unknown"))
        if status not in {"completed", "cancelled", "refunded"} or record.get("reservation"):
            blockers.append((str(key), status))
    return blockers


def inventory_cache_freshness_error(cache_data: dict, now: float | None = None,
                                    max_age_seconds: int = 6 * 60 * 60) -> str | None:
    """Fail closed when available-card counts come from a missing, future or stale cache."""
    if not isinstance(cache_data, dict):
        return "Кэш склада повреждён. Обнови кэш склада перед выдачей."
    updated_at = cache_data.get("updated_at")
    if not isinstance(updated_at, (int, float)) or isinstance(updated_at, bool) or updated_at <= 0:
        return "У кэша склада нет достоверного времени обновления. Нажми «🔄 Обновить кэш склада»."
    current_time = time.time() if now is None else float(now)
    age = current_time - float(updated_at)
    if age < -300:
        return "Время кэша склада выглядит некорректным. Обнови кэш склада перед выдачей."
    if age > max_age_seconds:
        hours = age / 3600
        return (
            f"Кэш склада устарел ({hours:.1f} ч). Выдача остановлена, чтобы не использовать "
            "устаревшие asset ID. Нажми «🔄 Обновить кэш склада»."
        )
    return None


def is_funpay_system_message(html_fragment: str) -> bool:
    """Trust payment text only inside FunPay's alert block used for system-authored messages."""
    if not html_fragment:
        return False
    if re.search(r"<[^>]+\brole\s*=\s*(['\"])alert\1", html_fragment, re.IGNORECASE):
        return True
    # HTML class order is not significant; require both trusted FunPay alert classes.
    for match in re.finditer(
        r"<[^>]+\bclass\s*=\s*(['\"])(.*?)\1",
        html_fragment,
        re.IGNORECASE | re.DOTALL,
    ):
        classes = set(match.group(2).split())
        if {"alert-with-icon", "alert-info"}.issubset(classes):
            return True
    return False

def extract_order_number(text: str) -> str | None:
    """Extract a FunPay order identifier (which may contain letters)."""
    match = re.search(
        r"(?:заказ(?:у|а|ом)?|order)\s*[№#]?\s*([A-Z0-9]{4,24})",
        text or "",
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def payment_key(node_id: str, text: str) -> str:
    """Return a stable fallback key for payment messages without an order number."""
    order_no = extract_order_number(text)
    if order_no:
        return f"fp-order-{order_no}"
    normalized = " ".join((text or "").lower().split())
    digest = hashlib.sha256(f"{node_id}|{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"fp-chat-{node_id}-{digest}"




def funpay_input_signature(
    node_id: str,
    sender_name: str,
    message_fragment: str,
    message_text: str = "",
    message_id: int | str | None = None,
) -> str:
    """Stable, non-reversible fingerprint for one incoming chat message.

    Include the rendered message fragment (which normally includes sender/time metadata)
    so the same URL sent in a new message is distinct, while polling the same message
    does not re-trigger delivery. The original URL is never stored by this helper.
    """
    raw_fragment = message_fragment or ""
    visible_fragment = html.unescape(re.sub(r"<[^>]+>", " ", raw_fragment))
    visible_fragment = re.sub(r"\s+", " ", visible_fragment).strip()
    text = re.sub(r"\s+", " ", (message_text or "").strip())
    stable_id_match = re.search(r"\bdata-(?:message-)?id\s*=\s*(['\"])(.*?)\1", raw_fragment, re.IGNORECASE)
    stable_id = str(message_id) if message_id is not None else (stable_id_match.group(2) if stable_id_match else "")
    digest = hashlib.sha256(f"{node_id}|{sender_name}|{stable_id}|{visible_fragment}|{text}".encode("utf-8", errors="replace")).hexdigest()
    return digest


def message_signature(sender_name: str, preview: str) -> str:
    """Create a stable signature without storing the message preview itself."""
    source = f"{sender_name or ''}:{preview or ''}".encode("utf-8", errors="replace")
    return hashlib.sha256(source).hexdigest()

def register_payment(orders: dict, *, node_id: str, buyer: str, text: str,
                     sets_per_item: int, quantity: int) -> tuple[dict, bool]:
    """Create exactly one record for a payment notification.

    Returns ``(record, created)``. A repeated FunPay notification reuses the
    existing record and can never create a second inventory reservation.
    """
    key = payment_key(node_id, text)
    existing = orders.get(key)
    if isinstance(existing, dict):
        # The order number is the stable FunPay identity. If FunPay exposes the
        # same still-unfulfilled payment under a new chat node, follow that
        # authenticated system event so the buyer's subsequent trade URL can match.
        if (
            existing.get("status") in {"awaiting_input", "input_received", "reserved", "review", "retry_required"}
            and not existing.get("steam_trade_offer_id")
            and str(existing.get("node_id")) != str(node_id)
        ):
            existing["node_id"] = str(node_id)
            existing["buyer"] = buyer
            existing["updated_at"] = int(time.time())
        return existing, False

    now = int(time.time())
    record = {
        "key": key,
        "funpay_order_number": extract_order_number(text),
        "node_id": str(node_id),
        "buyer": buyer,
        "sets_per_item": int(sets_per_item),
        "quantity": int(quantity),
        "sets_total": int(sets_per_item) * int(quantity),
        "status": "awaiting_input",
        "reservation": None,
        "input_kind": None,
        "input_received_at": None,
        "updated_at": now,
        "created_at": now,
        "notes": [],
    }
    orders[key] = record
    return record, True



def open_orders_for_chat(orders: dict, node_id: str) -> list[dict]:
    """Return all open orders for a chat in stable oldest-first order.

    The caller must not guess between multiple candidates; this list is used to
    present an explicit admin disambiguation choice.
    """
    candidates = [
        item for item in orders.values()
        if isinstance(item, dict)
        and str(item.get("node_id")) == str(node_id)
        and item.get("status") in OPEN_STATUSES
    ]
    return sorted(candidates, key=lambda item: (int(item.get("created_at", 0) or 0), str(item.get("key", ""))))


def find_open_order_for_chat(orders: dict, node_id: str) -> dict | None:
    """Return an order only when exactly one candidate exists in this chat.

    If multiple open orders exist, an incoming file/link cannot be reliably
    assigned to one of them from the chat id alone. Returning ``None`` forces
    manual review instead of silently attaching the input to the wrong order.
    """
    candidates = [
        item for item in orders.values()
        if isinstance(item, dict)
        and str(item.get("node_id")) == str(node_id)
        and item.get("status") in OPEN_STATUSES
    ]
    return candidates[0] if len(candidates) == 1 else None


def summarize_funpay_chat_diagnostics(timeline: dict, orders: dict, node_id: str) -> dict:
    """Build a read-only, URL-redacted summary of one live FunPay chat.

    The function never returns message text, attachment URLs, access tokens, or
    raw trade URLs. It is intended for an admin diagnostic command only.
    """
    if not isinstance(timeline, dict):
        raise ValueError("Invalid FunPay timeline.")
    orders = orders if isinstance(orders, dict) else {}
    latest = timeline.get("latest_message")
    latest_buyer = timeline.get("latest_buyer_message")

    if not isinstance(latest, dict):
        latest_summary = {
            "message_id": None,
            "author_id": None,
            "author_kind": "empty",
        }
    else:
        if latest.get("is_system"):
            author_kind = "system"
        elif latest.get("is_buyer"):
            author_kind = "buyer"
        elif latest.get("author_id") is None:
            author_kind = "unknown"
        else:
            author_kind = "other"
        latest_summary = {
            "message_id": latest.get("id"),
            "author_id": latest.get("author_id"),
            "author_kind": author_kind,
        }

    input_summary = {
        "message_id": None,
        "has_trade_url": False,
        "has_text_attachment": False,
    }
    if isinstance(latest_buyer, dict):
        fragment = str(latest_buyer.get("html") or "")
        text = str(latest_buyer.get("text") or "")
        input_summary = {
            "message_id": latest_buyer.get("id"),
            "has_trade_url": bool(
                extract_steam_trade_url(text) or extract_steam_trade_url(fragment)
            ),
            "has_text_attachment": bool(
                extract_text_attachment_href(
                    fragment,
                    f"https://funpay.com/chat/?node={node_id}",
                )
            ),
        }

    system_event_summaries = []
    for event in timeline.get("system_events", []):
        if not isinstance(event, dict):
            continue
        event_text = str(event.get("text") or "")
        order_number = extract_order_number(event_text)
        key = f"fp-order-{order_number}" if order_number else None
        record = orders.get(key) if key else None
        system_event_summaries.append({
            "message_id": event.get("id"),
            "order_number": order_number,
            "order_status": record.get("status") if isinstance(record, dict) else None,
            "order_node_matches": (
                str(record.get("node_id")) == str(node_id)
                if isinstance(record, dict) else False
            ),
            "author_id": event.get("author_id"),
        })

    chat_orders = [
        {
            "order_number": item.get("funpay_order_number") or item.get("key"),
            "status": item.get("status"),
            "sets_total": item.get("sets_total"),
            "has_reservation": isinstance(item.get("reservation"), dict),
        }
        for item in open_orders_for_chat(orders, node_id)
    ]

    return {
        "chat_id": str(node_id),
        "buyer_id": timeline.get("buyer_id"),
        "message_count": len(timeline.get("messages", [])),
        "latest": latest_summary,
        "latest_buyer_input": input_summary,
        "system_events": system_event_summaries,
        "open_orders": chat_orders,
    }


def mark_input_received(record: dict, input_kind: str) -> None:
    """Mark that input arrived without storing its sensitive contents."""
    # Repeated events must not overwrite the first input or move an order
    # backwards from review/delivered/cancelled to input_received.
    if record.get("status") not in {"awaiting_input", "reserved"}:
        return
    record["input_kind"] = input_kind
    record["input_received_at"] = int(time.time())
    record["updated_at"] = int(time.time())
    record["status"] = "input_received"
