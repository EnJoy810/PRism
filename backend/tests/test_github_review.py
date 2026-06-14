from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.review import ReviewIssue, ReviewResult, ReviewStats
from app.services.github_review import _format_inline_body, post_review_to_github

SAMPLE_RESULT = ReviewResult(
    pr_url="https://github.com/owner/repo/pull/1",
    summary="Review summary",
    risk_level="MEDIUM",
    issues=[
        ReviewIssue(file="a.ts", line=10, title="Bug", severity="ERROR", description="desc"),
    ],
    stats=ReviewStats(files_changed=1, additions=1, deletions=0, issues_by_severity={"ERROR": 1, "WARNING": 0, "INFO": 0}),
)


class TestFormatInlineBody:
    def test_with_suggestion(self):
        issue = ReviewIssue(
            file="a.ts", line=10, title="Test", severity="ERROR",
            description="desc", suggestion="fix it",
        )
        body = _format_inline_body(issue)
        assert "fix it" in body

    def test_without_suggestion(self):
        issue = ReviewIssue(file="a.ts", line=10, title="Test", severity="ERROR", description="desc")
        body = _format_inline_body(issue)
        assert "建议" not in body


class TestPostReviewRetry:
    @patch("app.services.github_review.httpx.AsyncClient")
    async def test_success_no_retry(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"html_url": "http://example.com"}
        mock_client.post.return_value = mock_resp

        result = await post_review_to_github(
            "owner", "repo", 1, "token", SAMPLE_RESULT, {"a.ts": {10: 5}},
        )
        assert result["html_url"] == "http://example.com"
        assert mock_client.post.call_count == 1

    @patch("app.services.github_review.httpx.AsyncClient")
    async def test_retry_on_503_then_succeed(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=503),
        )
        ok_resp = MagicMock()
        ok_resp.json.return_value = {"html_url": "http://example.com"}

        mock_client.post.side_effect = [fail_resp, fail_resp, ok_resp]

        result = await post_review_to_github(
            "owner", "repo", 1, "token", SAMPLE_RESULT, {"a.ts": {10: 5}},
        )
        assert result["html_url"] == "http://example.com"
        assert mock_client.post.call_count == 3

    @patch("app.services.github_review.httpx.AsyncClient")
    async def test_retry_exhausted_raises(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=503),
        )
        mock_client.post.return_value = fail_resp

        with pytest.raises(httpx.HTTPStatusError):
            await post_review_to_github(
                "owner", "repo", 1, "token", SAMPLE_RESULT, {"a.ts": {10: 5}},
            )
        assert mock_client.post.call_count == 3
