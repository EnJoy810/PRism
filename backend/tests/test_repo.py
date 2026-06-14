from unittest.mock import patch

import pytest

from app.services.repo import _cache_path, ensure_repo


def test_cache_path():
    p = _cache_path("owner", "repo", "abc123")
    assert str(p).endswith("owner/repo/abc123")


@pytest.mark.asyncio
async def test_ensure_repo_returns_none_on_clone_failure():
    with patch("app.services.repo._clone", side_effect=RuntimeError("network error")):
        result = await ensure_repo("owner", "repo", "abc123", "token")
    assert result is None


@pytest.mark.asyncio
async def test_ensure_repo_cache_hit():
    sha = "deadbeef"
    cache = _cache_path("o", "r", sha)
    cache.mkdir(parents=True, exist_ok=True)
    try:
        result = await ensure_repo("o", "r", sha, "token")
        assert result == cache
    finally:
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
