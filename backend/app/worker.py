"""ARQ background worker for consuming review_queue."""

import asyncio
import logging

from app.auth import get_installation_token
from app.config import load_config
from app.graph import ReviewGraph

logger = logging.getLogger(__name__)


async def startup(ctx):
    cfg = load_config()
    ctx["config"] = cfg


async def shutdown(ctx):
    pass


async def _resolve_token(config, installation_id: int | None) -> str | None:
    if installation_id:
        try:
            token = await get_installation_token(installation_id)
            logger.info("Using installation token for installation %d", installation_id)
            return token
        except Exception as e:
            logger.warning(
                "Failed to get installation token for %s: %s — falling back to config token",
                installation_id, e,
            )
    token = config.github_token
    if token:
        return token
    return None


async def review_job(ctx, pr_url: str, event: str, installation_id: int | None = None):
    config = ctx["config"]
    logger.info("Processing review: %s (event=%s)", pr_url, event)

    token = await _resolve_token(config, installation_id)
    if not token:
        logger.warning(
            "No token available for %s — review result available in logs only", pr_url
        )

    try:
        graph = ReviewGraph()
        result = await graph.run(pr_url=pr_url)

        if token:
            try:
                await graph.post_comment(result, pr_url, token)
                logger.info("Review comment posted for %s", pr_url)
            except Exception as e:
                logger.error("Failed to post review comment for %s: %s", pr_url, e)
        else:
            logger.info("No token — review result available in logs only")

        logger.info(
            "Review complete: %s — %d issues, risk=%s, decision=%s",
            pr_url,
            len(result.get("issues", [])),
            result.get("risk_level", "N/A"),
            result.get("merge_recommendation", "N/A"),
        )
    except Exception as e:
        logger.error("Review failed for %s: %s", pr_url, e)


class WorkerSettings:
    functions = [review_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None

    @classmethod
    def from_url(cls, redis_url: str):
        from arq.connections import RedisSettings
        cls.redis_settings = RedisSettings.from_dsn(redis_url)
        return cls


def main():
    cfg = load_config()
    settings = WorkerSettings.from_url(cfg.redis_url)
    from arq import run_worker
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
