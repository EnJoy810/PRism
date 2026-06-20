from unittest.mock import AsyncMock, patch

import pytest

from app.graph import ReviewGraph


@pytest.mark.asyncio
async def test_post_comment_calls_github_review():
    graph = ReviewGraph()
    mock_result = {
        "summary": "Fix auth bug",
        "risk_level": "MEDIUM",
        "issues": [
            {
                "file": "src/auth.ts",
                "line": 10,
                "title": "SQL injection",
                "description": "User input not sanitized",
                "severity": "ERROR",
                "confidence": 0.95,
                "category": "security",
                "diff_snippet": "+ const query = `SELECT * FROM users WHERE id = ${input}`",
            }
        ],
        "stats": {"files_changed": 3, "additions": 50, "deletions": 10, "issues_by_severity": {"ERROR": 1, "WARNING": 0, "INFO": 0}},
        "merge_recommendation": "REQUEST_CHANGES",
        "skipped_agents": [],
        "diff": "+ const x = 1\n- const y = 2",
        "event": "",
    }

    with patch("app.services.github_review.post_review_to_github", new_callable=AsyncMock) as mock_github:
        mock_github.return_value = {"html_url": "https://github.com/owner/repo/pull/1#pullrequestreview-123", "inline_count": 1}

        result = await graph.post_comment(
            mock_result,
            pr_url="https://github.com/owner/repo/pull/1",
            github_token="ghp_test",
        )

        assert result["html_url"] == "https://github.com/owner/repo/pull/1#pullrequestreview-123"
        assert result["inline_count"] == 1
        mock_github.assert_awaited_once()
