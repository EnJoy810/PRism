from arq.connections import ArqRedis
from pydantic import BaseModel
from redis import asyncio as aioredis  # noqa: F401


class ReviewJob(BaseModel):
    pr_url: str
    event: str
    installation_id: int | None = None
    github_token: str | None = None


async def enqueue_review(job: ReviewJob, redis: ArqRedis) -> None:
    if isinstance(redis, ArqRedis):
        await redis.enqueue_job(
            "review_job",
            job.pr_url,
            job.event,
            job.installation_id,
        )
        return

    await redis.lpush("review_queue", job.model_dump_json())
