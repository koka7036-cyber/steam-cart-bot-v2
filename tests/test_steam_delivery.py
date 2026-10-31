"""Tests for conservative Steam trade-offer response classification."""

import pytest

from steam_delivery import classify_steam_trade_offer_response


def test_valid_offer_id_confirms_created_offer():
    assert classify_steam_trade_offer_response(
        200, {"tradeofferid": "123456789012345678"}
    ) == (
        "created",
        "Предложение Steam #123456789012345678 создано.",
        "123456789012345678",
    )


def test_explicit_steam_error_is_a_definite_rejection():
    outcome, message, offer_id = classify_steam_trade_offer_response(
        200, {"strError": "Inventory is private"}
    )

    assert outcome == "failed"
    assert "Inventory is private" in message
    assert offer_id is None


@pytest.mark.parametrize("payload", [None, [], "ok", 17, True])
def test_non_object_success_payload_is_uncertain(payload):
    outcome, _message, offer_id = classify_steam_trade_offer_response(200, payload)

    assert outcome == "unknown"
    assert offer_id is None


def test_success_payload_without_offer_id_or_explicit_error_is_uncertain():
    outcome, _message, offer_id = classify_steam_trade_offer_response(
        200, {"success": True}
    )

    assert outcome == "unknown"
    assert offer_id is None


@pytest.mark.parametrize("offer_id", ["", "abc", "0", 0, True, None, []])
def test_malformed_offer_id_is_uncertain(offer_id):
    outcome, _message, result_id = classify_steam_trade_offer_response(
        200, {"tradeofferid": offer_id, "strError": ""}
    )

    assert outcome == "unknown"
    assert result_id is None


def test_http_client_error_is_a_definite_rejection():
    outcome, message, offer_id = classify_steam_trade_offer_response(403, None)

    assert outcome == "failed"
    assert "HTTP 403" in message
    assert offer_id is None


def test_http_server_error_remains_uncertain():
    outcome, message, offer_id = classify_steam_trade_offer_response(
        503, {"strError": "temporary failure"}
    )

    assert outcome == "unknown"
    assert "HTTP 503" in message
    assert offer_id is None


def test_redirect_without_final_success_is_uncertain():
    outcome, _message, offer_id = classify_steam_trade_offer_response(302, None)

    assert outcome == "unknown"
    assert offer_id is None
