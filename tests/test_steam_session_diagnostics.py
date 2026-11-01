import pytest

from steam_session_diagnostics import classify_session_metadata


COOKIE = "local-test-cookie"


def metadata(timestamp=100):
    return {"steamLoginSecure": COOKIE, "timestamp": timestamp}


def test_missing_cookie_and_non_mapping_metadata():
    assert classify_session_metadata({"timestamp": 100}, now=100) == "missing_cookie"
    assert classify_session_metadata(None, now=100) == "missing_cookie"
    assert classify_session_metadata({}, now=100) == "missing_cookie"


def test_invalid_or_missing_timestamp():
    assert classify_session_metadata({"steamLoginSecure": COOKIE}, now=100) == "invalid_or_missing_timestamp"
    assert classify_session_metadata(metadata("100"), now=100) == "invalid_or_missing_timestamp"
    assert classify_session_metadata(metadata(True), now=100) == "invalid_or_missing_timestamp"
    assert classify_session_metadata(metadata(float("nan")), now=100) == "invalid_or_missing_timestamp"
    assert classify_session_metadata(metadata(float("inf")), now=100) == "invalid_or_missing_timestamp"
    assert classify_session_metadata(metadata(float("-inf")), now=100) == "invalid_or_missing_timestamp"


def test_future_timestamp():
    assert classify_session_metadata(metadata(101), now=100) == "future_timestamp"


def test_ttl_boundaries():
    assert classify_session_metadata(metadata(100), now=100) == "fresh_by_local_ttl"
    assert classify_session_metadata(metadata(100), now=100 + 43200 - 1) == "fresh_by_local_ttl"
    assert classify_session_metadata(metadata(100), now=100 + 43200) == "expired_local_ttl"
    assert classify_session_metadata(metadata(100), now=100 + 43200 + 1) == "expired_local_ttl"


@pytest.mark.parametrize("now", [True, "100", float("nan"), float("inf"), float("-inf")])
def test_invalid_now_is_rejected(now):
    with pytest.raises((TypeError, ValueError)):
        classify_session_metadata(metadata(100), now=now)


@pytest.mark.parametrize("ttl", [True, 0, -1, float("nan"), float("inf"), "43200"])
def test_invalid_ttl_is_rejected(ttl):
    with pytest.raises(ValueError):
        classify_session_metadata(metadata(100), now=100, ttl_seconds=ttl)
