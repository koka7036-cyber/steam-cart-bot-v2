"""Regression tests for safe FunPay order matching."""
from funpay_orders import (extract_chat_message_fragments, extract_last_chat_message_fragment, extract_last_customer_message_fragment, extract_steam_trade_url, filter_reserved_assets, find_open_order_for_chat, funpay_cold_start_blockers, funpay_input_signature, has_unsupported_funpay_attachment, FunPayLedgerIntegrityError, load_funpay_order_ledger, inventory_cache_freshness_error, is_funpay_system_message, mark_input_received, register_payment, voucher_redemption_block_reason, voucher_reset_block_reason)
from order_parser import detect_order_sets_and_quantity, is_funpay_refund_notification, is_paid_order_notification


def make_order(key, node_id="123", status="awaiting_input", updated_at=1):
    return {
        "key": key,
        "node_id": node_id,
        "status": status,
        "updated_at": updated_at,
        "input_kind": None,
        "input_received_at": None,
    }


def test_funpay_image_attachment_is_detected_as_unsupported_input():
    assert has_unsupported_funpay_attachment('<img src="/file/12345" alt="image">') is True


def test_funpay_file_attachment_is_detected_as_unsupported_input():
    assert has_unsupported_funpay_attachment('<div class="chat-msg-file">image.png</div>') is True


def test_funpay_plain_text_message_is_not_marked_as_attachment():
    assert has_unsupported_funpay_attachment('<div class="chat-message">Trade URL</div>') is False


def test_extract_steam_trade_url_accepts_plain_text_message():
    url = "https://steamcommunity.com/tradeoffer/new/?partner=123456&token=AbCdEf12"
    assert extract_steam_trade_url("Моя Steam Trade URL: " + url) == url


def test_extract_steam_trade_url_rejects_profile_link():
    assert extract_steam_trade_url("https://steamcommunity.com/profiles/123456") is None


def test_extract_steam_trade_url_rejects_missing_partner_or_token():
    assert extract_steam_trade_url("https://steamcommunity.com/tradeoffer/new/?partner=123456") is None
    assert extract_steam_trade_url("https://steamcommunity.com/tradeoffer/new/?token=AbCdEf12") is None


def test_extract_steam_trade_url_rejects_ambiguous_multiple_urls():
    first = "https://steamcommunity.com/tradeoffer/new/?partner=123456&token=AbCdEf12"
    second = "https://steamcommunity.com/tradeoffer/new/?partner=654321&token=ZyXwVu98"
    assert extract_steam_trade_url(first + " " + second) is None


def test_no_open_order_returns_none():
    assert find_open_order_for_chat({}, "123") is None


def test_single_open_order_is_returned():
    order = make_order("only")
    assert find_open_order_for_chat({"only": order}, "123") is order


def test_multiple_open_orders_in_same_chat_are_ambiguous():
    older = make_order("older", updated_at=10)
    newer = make_order("newer", updated_at=20)
    result = find_open_order_for_chat({"older": older, "newer": newer}, "123")
    assert result is None


def test_closed_order_is_not_considered_open():
    order = make_order("done", status="delivered")
    assert find_open_order_for_chat({"done": order}, "123") is None


def test_orders_from_another_chat_are_ignored():
    order = make_order("other", node_id="999")
    assert find_open_order_for_chat({"other": order}, "123") is None


def test_input_received_updates_status_and_input_kind():
    order = make_order("only")
    mark_input_received(order, "file_attachment")
    assert order["status"] == "input_received"
    assert order["input_kind"] == "file_attachment"
    assert isinstance(order["input_received_at"], int)


def test_repeated_input_does_not_overwrite_first_input():
    order = make_order("only")
    mark_input_received(order, "file_attachment")
    first_received_at = order["input_received_at"]
    mark_input_received(order, "chat_trade_url")
    assert order["input_kind"] == "file_attachment"
    assert order["input_received_at"] == first_received_at


def test_delivered_order_cannot_be_moved_back_by_late_input():
    order = make_order("done", status="delivered")
    mark_input_received(order, "file_attachment")
    assert order["status"] == "delivered"
    assert order["input_kind"] is None


def test_review_order_is_not_overwritten_by_late_input():
    order = make_order("review", status="review")
    mark_input_received(order, "chat_trade_url")
    assert order["status"] == "review"
    assert order["input_kind"] is None


def test_payment_registration_is_idempotent_for_order_number():
    orders = {}
    first, created_first = register_payment(
        orders, node_id="123", buyer="Buyer", text="Заказ #123456 оплачен",
        sets_per_item=5, quantity=2,
    )
    second, created_second = register_payment(
        orders, node_id="123", buyer="Buyer", text="Заказ #123456 оплачен повторно",
        sets_per_item=5, quantity=2,
    )
    assert created_first is True
    assert created_second is False
    assert first is second
    assert first["sets_total"] == 10
    assert len(orders) == 1


def test_different_explicit_order_numbers_do_not_collapse():
    orders = {}
    first, created_first = register_payment(
        orders, node_id="123", buyer="Buyer", text="Заказ #123456 оплачен",
        sets_per_item=1, quantity=1,
    )
    second, created_second = register_payment(
        orders, node_id="123", buyer="Buyer", text="Заказ #123457 оплачен",
        sets_per_item=1, quantity=1,
    )
    assert created_first and created_second
    assert first is not second
    assert len(orders) == 2


def test_message_signature_is_stable_and_does_not_expose_preview():
    from funpay_orders import message_signature
    preview = "https://steamcommunity.com/tradeoffer/new/?partner=123&token=secret"
    first = message_signature("Buyer", preview)
    assert first == message_signature("Buyer", preview)
    assert preview not in first
    assert "secret" not in first


def test_message_signature_changes_when_preview_changes():
    from funpay_orders import message_signature
    assert message_signature("Buyer", "payment") != message_signature("Buyer", "file attached")


def test_extract_steam_trade_url_from_plain_text():
    url = "https://steamcommunity.com/tradeoffer/new/?partner=123456&token=AbCdEf12"
    assert extract_steam_trade_url("Steam trade link: " + url) == url


def test_extract_steam_trade_url_rejects_non_steam_hosts():
    assert extract_steam_trade_url("https://example.com/tradeoffer/new/?partner=123&token=abc") is None


def test_extract_steam_trade_url_rejects_missing_token():
    assert extract_steam_trade_url("https://steamcommunity.com/tradeoffer/new/?partner=123") is None


def test_extract_steam_trade_url_rejects_ambiguous_multiple_links():
    a = "https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc"
    b = "https://steamcommunity.com/tradeoffer/new/?partner=456&token=def"
    assert extract_steam_trade_url(a + "\n" + b) is None


def test_retry_required_order_is_open_for_corrected_input():
    order = make_order("retry", status="retry_required")
    assert find_open_order_for_chat({"retry": order}, "123") is order


def test_extract_last_chat_message_fragment_does_not_reuse_old_trade_link_for_latest_file():
    old_url = "https://steamcommunity.com/tradeoffer/new/?partner=123&token=OLD"
    html_doc = (
        '<div class="chat-msg-item"><div class="chat-msg-text">' + old_url + '</div></div>'
        '<div class="chat-msg-item"><div class="chat-msg-file">'
        '<a href="/file/765" title="trade-url.txt">trade-url.txt</a>'
        '</div></div>'
    )
    fragment = extract_last_chat_message_fragment(html_doc)
    assert fragment is not None
    assert "token=OLD" not in fragment
    assert "trade-url.txt" in fragment

def test_extract_last_chat_message_fragment_returns_latest_text():
    html_doc = (
        '<div class="chat-msg-item"><div class="chat-msg-text">old</div></div>'
        '<div class="chat-msg-item"><div class="chat-msg-text">new</div></div>'
    )
    assert "new" in extract_last_chat_message_fragment(html_doc)
    assert "old" not in extract_last_chat_message_fragment(html_doc)


def test_restore_reserved_assets_is_idempotent():
    from funpay_orders import restore_reserved_assets

    cache = {"games": {"Game": {"Card A": ["10"]}}, "total_cards": 1}
    reservation = {
        "asset_ids": ["11", "12"],
        "asset_locations": [
            {"game": "Game", "card": "Card A", "asset_id": "11"},
            {"game": "Game", "card": "Card B", "asset_id": "12"},
        ],
    }

    once = restore_reserved_assets(cache, reservation)
    twice = restore_reserved_assets(once, reservation)

    assert once is not None
    assert twice is not None
    assert twice["games"]["Game"]["Card A"] == ["10", "11"]
    assert twice["games"]["Game"]["Card B"] == ["12"]
    assert twice["total_cards"] == 3
    assert cache["games"]["Game"]["Card A"] == ["10"]


def test_restore_reserved_assets_rejects_malformed_reservation_without_mutating_cache():
    from funpay_orders import restore_reserved_assets

    cache = {"games": {"Game": {"Card A": ["10"]}}, "total_cards": 1}
    before = {
        "games": {"Game": {"Card A": ["10"]}},
        "total_cards": 1,
    }
    malformed = {
        "asset_ids": ["11", "11"],
        "asset_locations": [
            {"game": "Game", "card": "Card A", "asset_id": "11"},
            {"game": "Game", "card": "Card B", "asset_id": "11"},
        ],
    }

    assert restore_reserved_assets(cache, malformed) is None
    assert cache == before


def test_filter_reserved_assets_excludes_pending_and_uncertain_offers():
    cache = {
        "total_cards": 4,
        "games": {
            "Game": {
                "Card A": ["1", "2"],
                "Card B": ["3", "4"],
            }
        },
    }
    orders = {
        "paid": {
            "status": "offer_sent",
            "reservation": {"asset_ids": ["1"], "asset_locations": []},
        },
        "uncertain": {
            "status": "delivery_uncertain",
            "reservation": {"asset_ids": ["3"], "asset_locations": []},
        },
    }
    filtered = filter_reserved_assets(cache, orders, {})
    assert filtered["games"]["Game"]["Card A"] == ["2"]
    assert filtered["games"]["Game"]["Card B"] == ["4"]
    assert filtered["total_cards"] == 2
    assert cache["games"]["Game"]["Card A"] == ["1", "2"]


def test_filter_reserved_assets_excludes_uncertain_voucher_assets():
    cache = {"games": {"Game": {"Card": ["1", "2", "3"]}}}
    vouchers = {
        "SET1-A": {
            "delivery_state": "uncertain",
            "reserved_asset_ids": ["2"],
        }
    }
    filtered = filter_reserved_assets(cache, {}, vouchers)
    assert filtered["games"]["Game"]["Card"] == ["1", "3"]


def test_order_creation_notification_is_not_treated_as_paid():
    assert not is_paid_order_notification("Создан заказ #123456: набор из 1 сета Steam")


def test_order_number_and_product_description_are_not_payment_proof():
    assert not is_paid_order_notification("Заказ #123456 — 1 сет карточек Steam")


def test_explicit_paid_order_notification_is_recognized():
    assert is_paid_order_notification("Покупатель оплатил заказ #123456: 1 сет карточек Steam")
    assert is_paid_order_notification("Покупатель CoolBuyer оплатил заказ #123456. Лот: 1 сет Steam")
    assert is_paid_order_notification("Buyer CoolBuyer paid for order #123456: 1 set of Steam cards")
    assert is_paid_order_notification("Order #123456 has been paid: 5 Steam card sets")
    assert is_paid_order_notification("Заказ успешно оплачен: 5 сетов Steam")
    assert is_paid_order_notification("Оплата получена, переведите товар покупателю")


def test_negative_payment_text_is_not_treated_as_paid():
    assert not is_paid_order_notification("Покупатель не оплатил заказ #123456: 1 сет Steam")
    assert not is_paid_order_notification("Оплата не прошла")


def test_system_message_requires_funpay_alert_marker():
    assert is_funpay_system_message('<div role="alert">Покупатель Alex оплатил заказ #ABC12345</div>')
    assert is_funpay_system_message(
        '<div class="alert alert-with-icon alert-info">Заказ оплачен</div>'
    )
    assert not is_funpay_system_message(
        '<div class="chat-msg-text">Покупатель Alex оплатил заказ #ABC12345</div>'
    )


def test_funpay_order_number_can_contain_letters():
    from funpay_orders import extract_order_number, payment_key
    text = "Покупатель Alex оплатил заказ #ABC12345. Лот: Steam cards"
    assert extract_order_number(text) == "ABC12345"
    assert payment_key("123", text) == "fp-order-ABC12345"


def test_cold_start_is_blocked_for_unresolved_orders_and_reservations():
    orders = {
        "completed": {"status": "completed", "reservation": None},
        "cancelled": {"status": "cancelled", "reservation": None},
        "paid": {"status": "reserved", "reservation": {"asset_ids": ["123"]}},
        "sent": {"status": "offer_sent", "reservation": {"asset_ids": ["456"]}},
        "review": {"status": "review", "reservation": None},
    }
    assert funpay_cold_start_blockers(orders) == [
        ("paid", "reserved"),
        ("sent", "offer_sent"),
        ("review", "review"),
    ]


def test_cold_start_allows_only_terminal_orders_without_reservations():
    assert funpay_cold_start_blockers({
        "completed": {"status": "completed", "reservation": None},
        "cancelled": {"status": "cancelled", "reservation": None},
    }) == []
    assert funpay_cold_start_blockers({
        "bad": {"status": "completed", "reservation": {"asset_ids": ["1"]}}
    }) == [("bad", "completed")]


def test_inventory_cache_freshness_guard():
    now = 1_800_000_000
    assert inventory_cache_freshness_error({"updated_at": now, "games": {}}, now=now) is None
    assert "устарел" in inventory_cache_freshness_error(
        {"updated_at": now - 7 * 3600, "games": {}}, now=now
    )
    assert "времени обновления" in inventory_cache_freshness_error({"games": {}}, now=now)
    assert "некорректным" in inventory_cache_freshness_error(
        {"updated_at": now + 600, "games": {}}, now=now
    )


def test_reset_blocks_used_or_previously_sent_vouchers():
    assert voucher_reset_block_reason({"used": True}) is not None
    assert voucher_reset_block_reason({"used": False, "delivery_state": "sending"}) is not None
    assert voucher_reset_block_reason({
        "used": False, "delivery_state": "uncertain", "reserved_asset_ids": ["123"]
    }) is not None
    assert voucher_reset_block_reason({
        "used": True, "delivery_state": "sent", "trade_offer_id": "987654"
    }) is not None
    assert voucher_reset_block_reason({
        "used": False, "delivery_state": "created_unconfirmed", "trade_offer_id": "987654"
    }) is not None


def test_reset_allows_unused_voucher_or_definite_failed_attempt():
    assert voucher_reset_block_reason({"used": False}) is None
    assert voucher_reset_block_reason({
        "used": False, "delivery_state": "failed", "delivery_error": "rejected"
    }) is None
    assert voucher_reset_block_reason(None) is not None


def test_redemption_guard_blocks_stale_reset_state_even_when_used_is_false():
    assert voucher_redemption_block_reason({
        "used": False, "delivery_state": "sent", "trade_offer_id": "987654"
    }) is not None
    assert voucher_redemption_block_reason({
        "used": False, "delivery_state": "created_unconfirmed", "reserved_asset_ids": ["1"]
    }) is not None
    assert voucher_redemption_block_reason({
        "used": False, "delivery_state": "sending", "reserved_asset_ids": ["1"]
    }) is not None


def test_redemption_guard_allows_new_or_definitely_failed_code():
    assert voucher_redemption_block_reason({"used": False}) is None
    assert voucher_redemption_block_reason({
        "used": False, "delivery_state": "failed"
    }) is None


def test_extract_chat_message_fragments_returns_all_messages_in_order():
    from funpay_orders import extract_chat_message_fragments

    html_doc = (
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Покупатель Buyer оплатил заказ #ABCD1234, Steam, 1 полный сет карточек</div></div>'
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123456&amp;token=AbCdEf12'
        '</div></div>'
    )
    fragments = extract_chat_message_fragments(html_doc)
    assert len(fragments) == 2
    assert "оплатил заказ #ABCD1234" in fragments[0]
    assert "token=AbCdEf12" in fragments[1]


def test_open_orders_for_chat_returns_candidates_oldest_first_for_manual_selection():
    from funpay_orders import open_orders_for_chat

    older = make_order("SW7M87P5", updated_at=10)
    older["created_at"] = 100
    newer = make_order("KUGQWJKH", updated_at=20)
    newer["created_at"] = 200
    other_chat = make_order("OTHER", node_id="999")
    other_chat["created_at"] = 50

    result = open_orders_for_chat(
        {"older": older, "newer": newer, "other": other_chat}, "123"
    )
    assert [item["key"] for item in result] == ["SW7M87P5", "KUGQWJKH"]


def test_open_orders_for_chat_excludes_closed_orders():
    from funpay_orders import open_orders_for_chat

    open_order = make_order("open")
    closed_order = make_order("closed", status="offer_sent")
    assert [item["key"] for item in open_orders_for_chat(
        {"open": open_order, "closed": closed_order}, "123"
    )] == ["open"]


def test_funpay_input_signature_is_stable_when_only_css_classes_change():
    first = '<div class="chat-msg unread"><span>17:23</span><p>https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc</p></div>'
    second = '<div class="chat-msg"><span>17:23</span><p>https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc</p></div>'
    assert funpay_input_signature("123", "Buyer", first, "trade URL") == funpay_input_signature("123", "Buyer", second, "trade URL")


def test_funpay_input_signature_distinguishes_a_new_message_with_same_url():
    first = '<div class="chat-msg"><span>17:23</span><p>same trade URL</p></div>'
    second = '<div class="chat-msg"><span>17:24</span><p>same trade URL</p></div>'
    assert funpay_input_signature("123", "Buyer", first, "same trade URL") != funpay_input_signature("123", "Buyer", second, "same trade URL")


def test_extract_paid_order_events_ignores_buyer_imitation_and_collects_system_events():
    from funpay_orders import extract_paid_order_events

    html_doc = (
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Покупатель Buyer оплатил заказ #ABCD1234: 1 сет Steam</div></div>'
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'Покупатель оплатил заказ #BAD99999: 5 сетов Steam'
        '</div></div>'
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Покупатель Other оплатил заказ #EFGH5678: 5 сетов Steam</div></div>'
    )
    events = extract_paid_order_events(html_doc)
    assert len(events) == 2
    assert "ABCD1234" in events[0][1]
    assert "EFGH5678" in events[1][1]
    assert all(is_funpay_system_message(fragment) for fragment, _ in events)


def test_payment_event_with_unrecognized_order_description_is_not_inferred():
    from funpay_orders import extract_paid_order_events

    html_doc = (
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Покупатель Buyer оплатил заказ #ABCD1234</div></div>'
    )
    events = extract_paid_order_events(html_doc)
    assert len(events) == 1
    assert detect_order_sets_and_quantity(events[0][1]) == (None, 1)


def test_extract_paid_order_events_detects_standalone_funpay_payment_alert():
    from funpay_orders import extract_paid_order_events

    html_doc = (
        '<div class="alert-info alert alert-with-icon">'
        '<div>Покупатель Koka20111 оплатил заказ #LB9EF7W7.</div>'
        '<div>Steam, Предметы, 1 ПОЛНЫЙ СЕТ КАРТОЧЕК STEAM | +100 XP | Карточки, 1 шт.</div>'
        '</div>'
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'Покупатель Koka20111 оплатил заказ #FAKE12345'
        '</div></div>'
    )
    events = extract_paid_order_events(html_doc)

    assert len(events) == 1
    fragment, text = events[0]
    assert is_funpay_system_message(fragment)
    assert "LB9EF7W7" in text
    assert detect_order_sets_and_quantity(text) == (1, 1)


def test_is_funpay_system_message_accepts_alert_classes_in_any_order():
    assert is_funpay_system_message(
        '<div class="alert-info alert-with-icon alert">Заказ оплачен</div>'
    )



def test_extract_last_customer_message_does_not_reuse_old_trade_after_refund_alert():
    trade = (
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc'
        '</div></div>'
    )
    refund = (
        '<div role="alert" class="alert alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div>'
    )
    html_doc = trade + refund

    # The newest timeline entry is the system refund, so there is no new buyer input.
    assert extract_last_customer_message_fragment(html_doc) is None
    assert "вернул деньги" in extract_last_chat_message_fragment(html_doc)
    # The historical URL remains in history but is not selected for delivery.
    assert extract_steam_trade_url(extract_last_customer_message_fragment(html_doc) or "") is None


def test_chat_timeline_preserves_order_of_buyer_message_and_standalone_alert():
    trade = (
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc'
        '</div></div>'
    )
    refund = (
        '<div role="alert" class="alert alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div>'
    )
    fragments = extract_chat_message_fragments(trade + refund)

    assert len(fragments) == 2
    assert "token=abc" in fragments[0]
    assert "вернул деньги" in fragments[1]


def test_funpay_refund_notification_is_recognized_but_not_as_payment():
    from order_parser import is_funpay_refund_notification

    refund = "Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7."
    payment = "Покупатель Koka20111 оплатил заказ #S8QXD5R4: 1 полный сет карточек Steam"
    assert is_funpay_refund_notification(refund)
    assert not is_funpay_refund_notification(payment)
    assert not is_paid_order_notification(refund)



def test_compact_funpay_text_collapses_blank_layout_and_truncates():
    from funpay_orders import compact_funpay_text

    source = "  FunPay   <div>оповещение</div>\n\n\n   Продавец   вернул деньги "
    assert compact_funpay_text(source) == "FunPay оповещение Продавец вернул деньги"
    shortened = compact_funpay_text("x" * 200, max_chars=80)
    assert len(shortened) <= 80
    assert shortened.endswith("[сообщение сокращено]")


def test_register_payment_rebinds_only_unfulfilled_order_to_current_chat():
    order = make_order("fp-order-ABCD1234", node_id="111")
    order["funpay_order_number"] = "ABCD1234"
    order["status"] = "reserved"
    orders = {order["key"]: order}

    record, created = register_payment(
        orders,
        node_id="222",
        buyer="Buyer",
        text="Покупатель Buyer оплатил заказ #ABCD1234: 1 полный сет Steam",
        sets_per_item=1,
        quantity=1,
    )

    assert not created
    assert record is order
    assert record["node_id"] == "222"
    assert record["buyer"] == "Buyer"


def test_register_payment_does_not_rebind_an_order_with_existing_offer():
    order = make_order("fp-order-ABCD1234", node_id="111", status="offer_sent")
    order["funpay_order_number"] = "ABCD1234"
    order["steam_trade_offer_id"] = "555"
    orders = {order["key"]: order}

    record, created = register_payment(
        orders,
        node_id="222",
        buyer="Buyer",
        text="Покупатель Buyer оплатил заказ #ABCD1234: 1 полный сет Steam",
        sets_per_item=1,
        quantity=1,
    )

    assert not created
    assert record["node_id"] == "111"

def test_screenshot_style_paid_notification_is_recognized_and_refund_is_not_payment():
    paid = (
        "Покупатель Koka20111 оплатил заказ #S8QXD5R4: Steam, Предметы, "
        "1 ПОЛНЫЙ СЕТ КАРТОЧЕК STEAM | +100 XP | Карточки, 1 шт."
    )
    refund = (
        "Продавец Koka2010 вернул деньги покупателю Koka20111 "
        "по заказу #LB9EF7W7."
    )
    assert is_paid_order_notification(paid)
    assert detect_order_sets_and_quantity(paid) == (1, 1)
    assert not is_paid_order_notification(refund)



def test_payment_history_extractor_keeps_paid_event_and_ignores_refund_alert():
    from funpay_orders import extract_paid_order_events

    html_doc = (
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Покупатель Koka20111 оплатил заказ #S8QXD5R4: Steam, Предметы, '
        '1 ПОЛНЫЙ СЕТ КАРТОЧЕК STEAM | +100 XP | Карточки, 1 шт.'
        '</div></div>'
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div></div>'
    )

    events = extract_paid_order_events(html_doc)
    paid = [text for _fragment, text in events if is_paid_order_notification(text)]

    assert len(paid) == 1
    assert "#S8QXD5R4" in paid[0]
    assert detect_order_sets_and_quantity(paid[0]) == (1, 1)



def test_system_refund_only_chat_has_no_customer_message():
    from funpay_orders import extract_last_customer_message_fragment

    refund = (
        '<div class="chat-msg-item"><div role="alert" class="alert alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div></div>'
    )
    assert extract_last_customer_message_fragment(refund) is None



def test_cold_start_treats_refunded_order_without_reservation_as_terminal():
    assert funpay_cold_start_blockers({
        "refunded": {"status": "refunded", "reservation": None}
    }) == []



def test_latest_refund_alert_is_not_hidden_by_a_previously_seen_buyer_message():
    from funpay_orders import extract_chat_message_fragments, extract_last_customer_message_fragment

    old_message = (
        '<div class="chat-msg-item"><div class="chat-msg-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=OLD'
        '</div></div>'
    )
    refund = (
        '<section role="alert" class="alert alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</section>'
    )
    fragments = extract_chat_message_fragments(old_message + refund)

    assert len(fragments) == 2
    assert "вернул деньги" in fragments[-1]
    assert extract_last_customer_message_fragment(old_message + refund) is None


def test_find_open_order_is_ambiguous_when_another_order_is_sending_or_uncertain():
    from funpay_orders import find_open_order_for_chat, open_orders_for_chat

    pending = make_order("pending", status="awaiting_input")
    uncertain = make_order("uncertain", status="delivery_uncertain")
    orders = {"pending": pending, "uncertain": uncertain}

    assert find_open_order_for_chat(orders, "123") is None
    assert {item["key"] for item in open_orders_for_chat(orders, "123")} == {
        "pending", "uncertain"
    }


def test_funpay_order_number_is_case_normalized_for_payment_and_refund_keys():
    from funpay_orders import extract_order_number, payment_key

    text = "Покупатель buyer оплатил заказ #abC123xy: 1 сет Steam"
    assert extract_order_number(text) == "ABC123XY"
    assert payment_key("123", text) == "fp-order-ABC123XY"


def test_payment_and_refund_alerts_are_returned_in_page_order():
    from funpay_orders import extract_paid_order_events

    paid = (
        '<div role="alert" class="alert alert-info">'
        'Покупатель Buyer оплатил заказ #ABC12345: 1 полный сет карточек Steam'
        '</div>'
    )
    refund = (
        '<div role="alert" class="alert alert-info">'
        'Продавец Seller вернул деньги покупателю Buyer по заказу #ABC12345.'
        '</div>'
    )
    events = extract_paid_order_events(paid + refund)

    assert len(events) == 2
    assert is_paid_order_notification(events[0][1])
    assert is_funpay_refund_notification(events[1][1])



def test_extract_order_number_supports_funpay_refund_wording():
    from funpay_orders import extract_order_number, payment_key

    refund = "Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7."
    paid = "Покупатель Koka20111 оплатил заказ #S8QXD5R4."

    assert extract_order_number(refund) == "LB9EF7W7"
    assert payment_key("297865070", refund) == "fp-order-LB9EF7W7"
    assert extract_order_number(paid) == "S8QXD5R4"


def test_extract_order_number_supports_other_russian_cases():
    from funpay_orders import extract_order_number

    assert extract_order_number("возврат заказа #ABCD1234") == "ABCD1234"
    assert extract_order_number("сообщение по заказом #ABCD1234") == "ABCD1234"


def _history_message(message_id, author_id, html):
    return {"id": message_id, "author": author_id, "html": html}


def _history_payload(messages, buyer_id=123456789):
    return {
        "chat": {
            "node": {
                "id": 297865070,
                "name": f"chat-76543210-{buyer_id}",
            },
            "messages": messages,
        }
    }


def test_structured_funpay_history_trusts_author_zero_for_system_refund():
    from funpay_orders import parse_funpay_history_payload

    refund = (
        '<div class="alert alert-with-icon alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div>'
    )
    buyer_url = (
        '<div class="message-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=buyerToken'
        '</div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(10, 0, refund),
            _history_message(11, 123456789, buyer_url),
        ]),
        expected_chat_id="297865070",
    )

    assert timeline["buyer_id"] == 123456789
    assert len(timeline["system_events"]) == 1
    assert "LB9EF7W7" in timeline["system_events"][0]["text"]
    assert timeline["latest_buyer_message"]["id"] == 11
    assert "token=buyerToken" in timeline["latest_buyer_message"]["html"]


def test_structured_funpay_history_does_not_reuse_old_buyer_url_after_refund():
    from funpay_orders import parse_funpay_history_payload

    old_url = (
        '<div class="message-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=oldToken'
        '</div>'
    )
    refund = (
        '<div class="alert alert-with-icon alert-info">'
        'Продавец Koka2010 вернул деньги покупателю Koka20111 по заказу #LB9EF7W7.'
        '</div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(10, 123456789, old_url),
            _history_message(11, 0, refund),
        ]),
        expected_chat_id="297865070",
    )

    assert timeline["latest_message"]["author_id"] == 0
    assert timeline["latest_buyer_message"] is None
    assert len(timeline["system_events"]) == 1


def test_structured_funpay_history_does_not_trust_buyer_imitation_of_paid_alert():
    from funpay_orders import parse_funpay_history_payload

    fake_payment = (
        '<div class="message-text">'
        'Покупатель оплатил заказ #FAKE12345: 5 полных сетов Steam'
        '</div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([_history_message(20, 123456789, fake_payment)]),
        expected_chat_id="297865070",
    )

    assert timeline["system_events"] == []
    assert timeline["latest_buyer_message"]["id"] == 20
    assert "FAKE12345" in timeline["latest_buyer_message"]["text"]


def test_structured_funpay_history_ignores_seller_message_as_buyer_input():
    from funpay_orders import parse_funpay_history_payload

    old_url = (
        '<div class="message-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=oldToken'
        '</div>'
    )
    seller_reply = '<div class="message-text">Спасибо, проверяю заказ.</div>'
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(10, 123456789, old_url),
            _history_message(11, 76543210, seller_reply),
        ]),
        expected_chat_id="297865070",
    )

    assert timeline["latest_message"]["author_id"] == 76543210
    assert timeline["latest_buyer_message"] is None


def test_structured_funpay_history_sorts_by_message_id_and_uses_latest_buyer_event():
    from funpay_orders import parse_funpay_history_payload

    old_url = '<div class="message-text">old</div>'
    latest_url = (
        '<div class="message-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=newToken'
        '</div>'
    )
    refund = (
        '<div class="alert alert-with-icon alert-info">'
        'Продавец вернул деньги покупателю по заказу #ABCD1234.'
        '</div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(12, 123456789, latest_url),
            _history_message(10, 0, refund),
            _history_message(11, 123456789, old_url),
        ]),
        expected_chat_id="297865070",
    )

    assert [item["id"] for item in timeline["messages"]] == [10, 11, 12]
    assert timeline["latest_buyer_message"]["id"] == 12
    assert "newToken" in timeline["latest_buyer_message"]["html"]


def test_structured_funpay_history_refuses_buyer_matching_when_peer_id_missing():
    import pytest
    from funpay_orders import parse_funpay_history_payload

    malformed = {
        "chat": {
            "node": {"id": 297865070, "name": "unknown-node-name"},
            "messages": [_history_message(1, 123456789, '<div class="message-text">url</div>')],
        }
    }
    timeline = parse_funpay_history_payload(malformed, expected_chat_id="297865070")

    assert timeline["buyer_id"] is None
    assert timeline["latest_buyer_message"] is None


def test_funpay_input_signature_uses_stable_message_id():
    fragment = '<div class="message-text">same trade URL</div>'
    first = funpay_input_signature("123", "Buyer", fragment, "same trade URL", message_id=100)
    repeated = funpay_input_signature("123", "Buyer", fragment, "same trade URL", message_id=100)
    second = funpay_input_signature("123", "Buyer", fragment, "same trade URL", message_id=101)

    assert first == repeated
    assert first != second




def test_extract_steam_trade_url_from_verified_funpay_anchor_href():
    from funpay_orders import extract_steam_trade_url

    fragment = (
        '<div class="message-text"><a href="https://steamcommunity.com/tradeoffer/new/'
        '?partner=123456&token=AbCdEf12">Открыть трейд</a></div>'
    )
    assert extract_steam_trade_url(fragment) == (
        "https://steamcommunity.com/tradeoffer/new/?partner=123456&token=AbCdEf12"
    )



def test_funpay_diagnostic_summarizes_order_match_without_exposing_trade_url():
    from funpay_orders import parse_funpay_history_payload, summarize_funpay_chat_diagnostics

    paid = (
        '<div class="alert alert-with-icon alert-info">'
        'Покупатель Buyer оплатил заказ #ABCD1234: 1 полный сет карточек Steam'
        '</div>'
    )
    buyer_url = (
        '<div class="message-text"><a href="https://steamcommunity.com/tradeoffer/new/'
        '?partner=123&token=PRIVATE_SECRET">Открыть трейд</a></div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(10, 0, paid),
            _history_message(11, 123456789, buyer_url),
        ]),
        expected_chat_id="297865070",
    )
    orders = {
        "fp-order-ABCD1234": {
            "key": "fp-order-ABCD1234",
            "funpay_order_number": "ABCD1234",
            "node_id": "297865070",
            "status": "reserved",
            "sets_total": 1,
            "reservation": {"asset_ids": ["123"]},
        }
    }

    result = summarize_funpay_chat_diagnostics(timeline, orders, "297865070")

    assert result["buyer_id"] == 123456789
    assert result["latest"]["author_kind"] == "buyer"
    assert result["latest_buyer_input"]["has_trade_url"] is True
    assert result["system_events"][0]["order_status"] == "reserved"
    assert result["system_events"][0]["order_node_matches"] is True
    assert result["open_orders"][0]["order_number"] == "ABCD1234"
    assert "PRIVATE_SECRET" not in repr(result)
    assert "steamcommunity.com" not in repr(result)


def test_funpay_diagnostic_does_not_reuse_old_buyer_url_after_latest_refund():
    from funpay_orders import parse_funpay_history_payload, summarize_funpay_chat_diagnostics

    old_url = (
        '<div class="message-text">'
        'https://steamcommunity.com/tradeoffer/new/?partner=123&token=OLD_SECRET'
        '</div>'
    )
    refund = (
        '<div class="alert alert-with-icon alert-info">'
        'Продавец Seller вернул деньги покупателю Buyer по заказу #ABCD1234.'
        '</div>'
    )
    timeline = parse_funpay_history_payload(
        _history_payload([
            _history_message(10, 123456789, old_url),
            _history_message(11, 0, refund),
        ]),
        expected_chat_id="297865070",
    )

    result = summarize_funpay_chat_diagnostics(timeline, {}, "297865070")

    assert result["latest"]["author_kind"] == "system"
    assert result["latest_buyer_input"]["message_id"] is None
    assert result["latest_buyer_input"]["has_trade_url"] is False
    assert "OLD_SECRET" not in repr(result)






def test_filter_reserved_assets_quarantines_all_stock_for_malformed_order_reservation():
    cache = {"total_cards": 2, "games": {"Game": {"Card A": ["12345", "23456"], "Card B": ["34567"]}}}
    orders = {"damaged": {"status": "reserved", "reservation": {"asset_ids": "12345"}}}
    filtered = filter_reserved_assets(cache, orders, {})
    assert filtered["games"] == {"Game": {"Card A": [], "Card B": []}}
    assert filtered["total_cards"] == 0
    assert cache["games"]["Game"]["Card A"] == ["12345", "23456"]


def test_filter_reserved_assets_quarantines_all_stock_for_malformed_voucher_reservation():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    vouchers = {"code": {"delivery_state": "uncertain", "reserved_asset_ids": "12345"}}
    filtered = filter_reserved_assets(cache, {}, vouchers)
    assert filtered["games"] == {"Game": {"Card": []}}
    assert filtered["total_cards"] == 0


def test_filter_reserved_assets_quarantines_duplicate_assets_across_orders():
    cache = {"total_cards": 2, "games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {
        "order-a": {"status": "reserved", "reservation": {"asset_ids": ["12345"]}},
        "order-b": {"status": "delivery_uncertain", "reservation": {"asset_ids": ["12345"]}},
    }
    filtered = filter_reserved_assets(cache, orders, {})
    assert filtered["games"] == {"Game": {"Card": []}}
    assert filtered["total_cards"] == 0
    assert cache["games"]["Game"]["Card"] == ["12345", "23456"]


def test_filter_reserved_assets_quarantines_order_voucher_asset_collision():
    cache = {"total_cards": 2, "games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {"order-a": {"status": "reserved", "reservation": {"asset_ids": ["12345"]}}}
    vouchers = {"voucher": {"delivery_state": "uncertain", "reserved_asset_ids": ["12345"]}}
    filtered = filter_reserved_assets(cache, orders, vouchers)
    assert filtered["games"] == {"Game": {"Card": []}}
    assert filtered["total_cards"] == 0


def test_filter_reserved_assets_quarantines_invalid_reservation_container_or_record():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    cases = [
        (["invalid-order-map"], {}),
        ({"bad": "not-a-record"}, {}),
        ({"bad": {"status": "reserved", "reservation": []}}, {}),
        ({}, ["invalid-voucher-map"]),
        ({}, {"bad": None}),
        ({}, {"bad": {"delivery_state": "uncertain", "reserved_asset_ids": []}}),
    ]
    for orders, vouchers in cases:
        filtered = filter_reserved_assets(cache, orders, vouchers)
        assert filtered["games"] == {"Game": {"Card": []}}
        assert filtered["total_cards"] == 0


def test_filter_reserved_assets_quarantines_duplicate_asset_ids_inside_one_reservation():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {"bad": {"status": "reserved", "reservation": {"asset_ids": ["12345", "12345"]}}}
    filtered = filter_reserved_assets(cache, orders, {})
    assert filtered["games"] == {"Game": {"Card": []}}
    assert filtered["total_cards"] == 0


def test_filter_reserved_assets_hides_reservation_on_cancelled_order_but_not_clean_cancelled_order():
    cache = {"games": {"Game": {"Card": ["12345", "23456"]}}}
    orders = {
        "cancelled-with-reservation": {
            "status": "cancelled",
            "reservation": {"asset_ids": ["12345"]},
        },
        "cancelled-clean": {"status": "cancelled", "reservation": None},
    }
    filtered = filter_reserved_assets(cache, orders, {})
    assert filtered["games"]["Game"]["Card"] == ["23456"]
    assert filtered["total_cards"] == 1



def test_load_funpay_order_ledger_initializes_only_when_file_is_missing(tmp_path):
    path = tmp_path / "funpay_orders.json"
    assert load_funpay_order_ledger(path) == {"orders": {}}


def test_load_funpay_order_ledger_reads_valid_orders_and_refunds(tmp_path):
    path = tmp_path / "funpay_orders.json"
    expected = {
        "orders": {"fp-order-1234": {"status": "reserved"}},
        "refunds": {},
    }
    path.write_text(__import__("json").dumps(expected), encoding="utf-8")
    assert load_funpay_order_ledger(path) == expected


def test_load_funpay_order_ledger_rejects_corrupt_existing_json(tmp_path):
    path = tmp_path / "funpay_orders.json"
    path.write_text('{"orders": ', encoding="utf-8")
    try:
        load_funpay_order_ledger(path)
    except FunPayLedgerIntegrityError:
        pass
    else:
        raise AssertionError("corrupt order ledger must never become an empty ledger")


def test_load_funpay_order_ledger_rejects_invalid_root_or_orders_container(tmp_path):
    path = tmp_path / "funpay_orders.json"
    for payload in ('[]', '{}', '{"orders": []}', '{"orders": {}, "refunds": []}'):
        path.write_text(payload, encoding="utf-8")
        try:
            load_funpay_order_ledger(path)
        except FunPayLedgerIntegrityError:
            continue
        raise AssertionError(f"invalid ledger structure was accepted: {payload}")



def test_load_funpay_order_ledger_rejects_directory_at_ledger_path(tmp_path):
    path = tmp_path / "funpay_orders.json"
    path.mkdir()
    try:
        load_funpay_order_ledger(path)
    except FunPayLedgerIntegrityError:
        pass
    else:
        raise AssertionError("a directory must not be treated as a missing ledger")


def test_restore_reserved_assets_quarantines_conflicting_asset_location():
    from funpay_orders import restore_reserved_assets

    cache = {"games": {"Game": {"Card A": ["10", "11"], "Card B": ["12"]}}, "total_cards": 3}
    reservation = {
        "asset_ids": ["11"],
        "asset_locations": [{"game": "Game", "card": "Card B", "asset_id": "11"}],
    }

    # A reservation cannot be restored into a different card while the same
    # Steam asset ID is already present elsewhere in the cached inventory.
    assert restore_reserved_assets(cache, reservation) is None
    assert cache["games"]["Game"]["Card A"] == ["10", "11"]


def test_restore_reserved_assets_rejects_duplicate_id_already_cached_in_same_location():
    from funpay_orders import restore_reserved_assets

    cache = {"games": {"Game": {"Card A": ["10", "11"]}}, "total_cards": 2}
    reservation = {
        "asset_ids": ["11"],
        "asset_locations": [{"game": "Game", "card": "Card A", "asset_id": "11"}],
    }

    restored = restore_reserved_assets(cache, reservation)
    assert restored is not None
    assert restored["games"]["Game"]["Card A"] == ["10", "11"]
    assert restored["total_cards"] == 2

