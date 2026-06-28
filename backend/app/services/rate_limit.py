"""Per-installation webhook rate limiting."""

import logging

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 20


async def is_rate_limited(redis, installation_id: int | None) -> bool:
    """Return True if this installation has exceeded the rate limit.

    Uses a sliding counter in Redis. Each installation gets an independent
    bucket that resets every _WINDOW_SECONDS seconds.
    """
    key = f"prism:rate:limit:{installation_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _WINDOW_SECONDS)
    return count > _MAX_REQUESTS
