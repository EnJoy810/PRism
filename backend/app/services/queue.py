import redis.asyncio as aioredis
from pydantic import BaseModel


class ReviewJob(BaseModel):
    pr_url: str
    event: str
    installation_id: int | None = None
    github_token: str | None = None


async def enqueue_review(job: ReviewJob, redis: aioredis.Redis) -> None:
    await redis.lpush("review_queue", job.model_dump_json())
