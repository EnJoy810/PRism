"""ARQ background worker for consuming review_queue."""

import asyncio

from app.config import load_config


async def startup(ctx):
    cfg = load_config()
    ctx["config"] = cfg


async def shutdown(ctx):
    pass


async def review_job(ctx, pr_url: str, event: str, installation_id: int | None = None):
    _ = ctx["config"]
    print(f"Processing review: {pr_url} (event={event})")


class WorkerSettings:
    functions = [review_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None  # set in main()

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
