from unittest.mock import AsyncMock, patch

from app.services.queue import ReviewJob, enqueue_review


class TestReviewJob:
    def test_model(self):
        job = ReviewJob(
            pr_url="https://github.com/owner/repo/pull/1",
            event="synchronize",
            installation_id=123456,
        )
        assert job.pr_url == "https://github.com/owner/repo/pull/1"
        assert job.event == "synchronize"
        assert job.installation_id == 123456

    def test_defaults(self):
        job = ReviewJob(pr_url="https://github.com/owner/repo/pull/1", event="opened")
        assert job.installation_id is None
        assert job.github_token is None

    def test_serialize(self):
        job = ReviewJob(pr_url="https://github.com/owner/repo/pull/1", event="opened")
        d = job.model_dump()
        assert d["pr_url"] == "https://github.com/owner/repo/pull/1"
        assert d["event"] == "opened"


class TestEnqueueReview:
    @patch("app.services.queue.aioredis")
    async def test_enqueue_with_redis_instance(self, mock_aioredis):
        mock_redis = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis

        job = ReviewJob(pr_url="https://github.com/owner/repo/pull/1", event="opened")
        await enqueue_review(job, mock_redis)

        mock_redis.lpush.assert_awaited_once()
        args = mock_redis.lpush.await_args
        assert args is not None
        assert args[0][0] == "review_queue"

    @patch("app.services.queue.aioredis")
    async def test_enqueue_job_content(self, mock_aioredis):
        mock_redis = AsyncMock()
        job = ReviewJob(pr_url="https://github.com/owner/repo/pull/1", event="opened", installation_id=42)
        await enqueue_review(job, mock_redis)

        pushed = mock_redis.lpush.await_args[0][1]
        assert '"pr_url"' in pushed
        assert '"installation_id":42' in pushed
