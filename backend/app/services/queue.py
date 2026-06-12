from pydantic import BaseModel


class ReviewJob(BaseModel):
    pr_url: str
    event: str
    installation_id: int | None = None
    github_token: str | None = None


async def enqueue_review(job: ReviewJob, redis_url: str = "redis://localhost:6379/0") -> None:
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url)
    await r.lpush("review_queue", job.model_dump_json())
    await r.aclose()
