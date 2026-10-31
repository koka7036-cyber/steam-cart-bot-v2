"""Conservative classification of Steam trade-offer HTTP responses.

Only a confirmed offer ID is treated as created. Explicit client rejection is
retryable; malformed or incomplete success responses remain uncertain.
"""


def classify_steam_trade_offer_response(status_code, payload):
    """Return (outcome, message, offer_id) without assuming malformed success is failure."""
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        return (
            "unknown",
            "Steam вернул ответ с неизвестным HTTP-статусом; результат создания предложения неясен.",
            None,
        )

    if status_code >= 500:
        return (
            "unknown",
            f"Steam вернул HTTP {status_code}; результат создания предложения неясен.",
            None,
        )

    if 400 <= status_code < 500:
        return "failed", f"Steam отклонил запрос (HTTP {status_code}).", None

    if not 200 <= status_code < 300:
        return (
            "unknown",
            f"Steam вернул HTTP {status_code} без подтверждения результата; повтор запрещён.",
            None,
        )

    if not isinstance(payload, dict):
        return (
            "unknown",
            "Steam вернул успешный HTTP-ответ с некорректной структурой; результат создания предложения неясен.",
            None,
        )

    if "tradeofferid" in payload:
        raw_offer_id = payload.get("tradeofferid")
        if isinstance(raw_offer_id, bool) or not isinstance(raw_offer_id, (str, int)):
            return (
                "unknown",
                "Steam вернул некорректный ID предложения; результат создания неясен.",
                None,
            )
        offer_id = str(raw_offer_id).strip()
        if not offer_id.isdigit() or int(offer_id) <= 0:
            return (
                "unknown",
                "Steam вернул некорректный ID предложения; результат создания неясен.",
                None,
            )
        return "created", f"Предложение Steam #{offer_id} создано.", offer_id

    error_text = payload.get("strError")
    if isinstance(error_text, str) and error_text.strip():
        return "failed", f"Steam отклонил обмен: {error_text.strip()[:240]}", None

    return (
        "unknown",
        "Steam не вернул ID предложения и не подтвердил отказ; результат создания неясен.",
        None,
    )
