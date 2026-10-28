from funpay_orders import extract_steam_trade_url


def test_extracts_one_valid_steam_trade_url():
    url = "https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc"
    assert extract_steam_trade_url(url) == url


def test_rejects_two_steam_trade_urls_separated_by_literal_backslash_n():
    a = "https://steamcommunity.com/tradeoffer/new/?partner=123&token=abc"
    b = "https://steamcommunity.com/tradeoffer/new/?partner=456&token=def"
    assert extract_steam_trade_url(a + "\\\\n" + b) is None


def test_rejects_http_and_missing_token():
    assert extract_steam_trade_url(
        "http://steamcommunity.com/tradeoffer/new/?partner=123&token=abc"
    ) is None
    assert extract_steam_trade_url(
        "https://steamcommunity.com/tradeoffer/new/?partner=123"
    ) is None
