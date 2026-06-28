"""Per-installation webhook rate limiting."""

import logging

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 20


async def is_rate_limited(
    redis,
    installation_id: int | None,
    window_seconds: int,
    max_requests: int = _MAX_REQUESTS,
) -> bool:
    """Return True if this installation has exceeded the rate limit.

    Uses a sliding counter in Redis. Each installation gets an independent
    bucket that resets every window_seconds seconds.
    Returns False (allow) when Redis is unavailable.
    """
    if redis is None:
        return False
    key = f"prism:rate:limit:{installation_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count > max_requests


async def get_rate_limit_info(
    redis,
    installation_id: int | None,
    window_seconds: int = _WINDOW_SECONDS,
    max_requests: int = _MAX_REQUESTS,
) -> dict:
    """Return current rate limit state for an installation.

    Returns a dict with keys: count, limit, remaining, window_seconds.
    Returns zeroed-out dict when Redis is unavailable.
    """
    if redis is None:
        return {"count": 0, "limit": max_requests, "remaining": max_requests, "window_seconds": window_seconds}
    key = f"prism:rate:limit:{installation_id}"
    raw = await redis.get(key)
    count = int(raw) if raw is not None else 0
    return {
        "count": count,
        "limit": max_requests,
        "remaining": max(0, max_requests - count),
        "window_seconds": window_seconds,
    }
