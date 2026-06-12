from app.services.queue import ReviewJob


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
