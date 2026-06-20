import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_cli_review_passes_token_to_graph():
    from app.cli import review
    from app.graph import ReviewGraph

    with patch.object(ReviewGraph, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "summary": "",
            "risk_level": "LOW",
            "merge_recommendation": "APPROVE",
            "issues": [],
            "stats": {},
            "skipped_agents": [],
        }

        await review("https://github.com/owner/repo/pull/1", "ghp_test")

    mock_run.assert_awaited_once_with(
        pr_url="https://github.com/owner/repo/pull/1",
        github_token="ghp_test",
    )


@pytest.mark.asyncio
async def test_cli_review_times_out():
    from app.cli import review
    from app.graph import ReviewGraph

    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(10)

    with patch.object(ReviewGraph, "run", side_effect=never_finishes):
        with pytest.raises(RuntimeError, match="Review timed out after 1s"):
            await review("https://github.com/owner/repo/pull/1", timeout_seconds=1)


def test_cli_main_prints_runtime_error_without_traceback(capsys):
    from app.cli import main

    argv = ["prism", "review", "https://github.com/owner/repo/pull/1", "--timeout", "1"]
    with (
        patch.object(sys, "argv", argv),
        patch("app.cli.review", side_effect=RuntimeError("boom")),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Error: boom" in captured.err
    assert "Traceback" not in captured.err
