"""Offline classification of locally stored Steam session metadata."""

import math
import time
from typing import Any

DEFAULT_LOCAL_TTL_SECONDS = 43200


def classify_session_metadata(
    metadata: Any,
    now: float | None = None,
    ttl_seconds: float = DEFAULT_LOCAL_TTL_SECONDS,
) -> str:
    """Classify local session metadata; this never contacts or verifies Steam."""
    metadata = metadata if isinstance(metadata, dict) else {}
    if not metadata.get("steamLoginSecure"):
        return "missing_cookie"

    timestamp = metadata.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return "invalid_or_missing_timestamp"
    if not math.isfinite(timestamp):
        return "invalid_or_missing_timestamp"

    current_time = time.time() if now is None else now
    if isinstance(current_time, bool) or not isinstance(current_time, (int, float)):
        raise TypeError("now must be a finite number")
    if not math.isfinite(current_time):
        raise ValueError("now must be a finite number")

    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, (int, float))
        or not math.isfinite(ttl_seconds)
        or ttl_seconds <= 0
    ):
        raise ValueError("ttl_seconds must be a positive finite number")

    if timestamp > current_time:
        return "future_timestamp"
    if current_time - timestamp >= ttl_seconds:
        return "expired_local_ttl"
    return "fresh_by_local_ttl"
