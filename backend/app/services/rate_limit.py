"""Per-installation webhook rate limiting."""

import logging

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 20

# Track request counts per installation for observability.
_request_counts: dict[int, int] = {}


async def is_rate_limited(redis, installation_id: int | None) -> bool:
    """Return True if this installation has exceeded the rate limit.

    Uses a sliding counter in Redis. Each installation gets an independent
    bucket that resets every _WINDOW_SECONDS seconds.
    Returns False (allow) when Redis is unavailable.
    """
    if redis is None:
        return False
    key = f"prism:rate:limit:{installation_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _WINDOW_SECONDS)

    # Update local metrics counter.
    _request_counts[installation_id] = _request_counts.get(installation_id, 0) + 1
    logger.debug("rate_limit: installation=%d count=%d", installation_id.bit_length(), count)

    return count > _MAX_REQUESTS
