from unittest.mock import AsyncMock, patch

import pytest

from app.graph import ReviewGraph
from app.worker import review_job


@pytest.mark.asyncio
async def test_review_job_runs_graph_and_posts():
    ctx = {"config": AsyncMock()}
    ctx["config"].github_token = "ghp_test"

    with (
        patch.object(ReviewGraph, "run", new_callable=AsyncMock) as mock_run,
        patch.object(ReviewGraph, "post_comment", new_callable=AsyncMock) as mock_post,
    ):
        mock_run.return_value = {
            "summary": "Test",
            "risk_level": "LOW",
            "issues": [],
            "stats": {"files_changed": 1, "additions": 1, "deletions": 0, "issues_by_severity": {"ERROR": 0, "WARNING": 0, "INFO": 0}},
            "merge_recommendation": "APPROVE",
            "skipped_agents": [],
        }

        await review_job(ctx, pr_url="https://github.com/owner/repo/pull/1", event="pull_request.opened")

        mock_run.assert_awaited_once_with(
            pr_url="https://github.com/owner/repo/pull/1",
            github_token="ghp_test",
        )
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_job_skips_comment_without_token():
    ctx = {"config": AsyncMock()}
    ctx["config"].github_token = ""

    with (
        patch.object(ReviewGraph, "run", new_callable=AsyncMock) as mock_run,
        patch.object(ReviewGraph, "post_comment", new_callable=AsyncMock) as mock_post,
    ):
        mock_run.return_value = {"issues": [], "risk_level": "LOW", "merge_recommendation": "APPROVE", "summary": "", "stats": {}, "skipped_agents": []}

        await review_job(ctx, pr_url="https://github.com/owner/repo/pull/1", event="pull_request.opened")

        mock_run.assert_awaited_once_with(
            pr_url="https://github.com/owner/repo/pull/1",
            github_token=None,
        )
        mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_job_handles_graph_exception():
    ctx = {"config": AsyncMock()}
    ctx["config"].github_token = "ghp_test"

    with patch.object(ReviewGraph, "run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("API failure")

        await review_job(ctx, pr_url="https://github.com/owner/repo/pull/1", event="pull_request.opened")

        mock_run.assert_awaited_once_with(
            pr_url="https://github.com/owner/repo/pull/1",
            github_token="ghp_test",
        )
