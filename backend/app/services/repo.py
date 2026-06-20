"""Shallow clone and cache management for PR repositories.

Cache layout: {CACHE_DIR}/{owner}/{repo}/{head_sha}/
Each entry is a complete shallow clone at the PR's head commit.
LRU eviction when total cache exceeds MAX_CACHE_GB.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("PRISM_REPO_CACHE", "/tmp/prism_repos"))
MAX_CACHE_GB = 10
_clone_locks: dict[str, asyncio.Lock] = {}


def _cache_path(owner: str, repo: str, head_sha: str) -> Path:
    return CACHE_DIR / owner / repo / head_sha


def _clone_url(owner: str, repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"


def _redact_token(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "***")


async def ensure_repo(
    owner: str,
    repo: str,
    head_sha: str,
    token: str,
) -> Path | None:
    """返回本地克隆路径，失败返回 None（调用方降级处理）。"""
    cache_path = _cache_path(owner, repo, head_sha)

    if cache_path.exists():
        logger.info("repo cache hit: %s/%s@%s", owner, repo, head_sha[:8])
        return cache_path

    lock_key = f"{owner}/{repo}/{head_sha}"
    if lock_key not in _clone_locks:
        _clone_locks[lock_key] = asyncio.Lock()

    async with _clone_locks[lock_key]:
        if cache_path.exists():
            return cache_path

        try:
            await _clone_by_fetch(owner, repo, head_sha, token, cache_path)
            _evict_if_needed()
            return cache_path
        except Exception as e:
            logger.warning("clone failed for %s/%s@%s: %s", owner, repo, head_sha[:8], e)
            if cache_path.exists():
                shutil.rmtree(cache_path, ignore_errors=True)
            return None


async def _clone_by_fetch(
    owner: str,
    repo: str,
    head_sha: str,
    token: str,
    dest: Path,
) -> None:
    url = _clone_url(owner, repo, token)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    async def run(*args: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(_redact_token(stderr.decode(errors="replace"), token)[:500])

    # GitHub does not allow fetching arbitrary SHAs by default.
    # Clone the default branch first (shallow), then fetch the exact SHA.
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth=1", url, str(dest),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(_redact_token(stderr.decode(errors="replace"), token)[:500])

    # Deepen to reach head_sha if it's not the tip of the default branch.
    fetch_proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(dest), "fetch", "--depth=1", "origin", head_sha,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, _ = await asyncio.wait_for(fetch_proc.communicate(), timeout=120)
    if fetch_proc.returncode == 0:
        await run("git", "-C", str(dest), "checkout", head_sha)
    await _set_public_remote(owner, repo, dest, token)


async def _set_public_remote(owner: str, repo: str, dest: Path, token: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(dest),
        "remote",
        "set-url",
        "origin",
        f"https://github.com/{owner}/{repo}.git",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(_redact_token(stderr.decode(errors="replace"), token)[:500])


def _evict_if_needed() -> None:
    if not CACHE_DIR.exists():
        return
    total_bytes = sum(
        f.stat().st_size
        for f in CACHE_DIR.rglob("*")
        if f.is_file()
    )
    if total_bytes < MAX_CACHE_GB * 1024 ** 3:
        return

    entries = sorted(
        [p for p in CACHE_DIR.glob("*/*/*") if p.is_dir()],
        key=lambda p: p.stat().st_atime,
    )
    for entry in entries:
        if total_bytes < MAX_CACHE_GB * 1024 ** 3 * 0.8:
            break
        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        shutil.rmtree(entry, ignore_errors=True)
        total_bytes -= size
        logger.info("evicted repo cache: %s", entry)
