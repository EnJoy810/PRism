import os
import re
import time
from collections import deque

import httpx

from app.models.review import ReviewStats


class GitHubRateLimiter:
    """Token-bucket style rate limiter for GitHub API calls.

    Tracks request timestamps within a sliding window and enforces
    a maximum request count per window.
    """

    def __init__(self, max_requests: int = 5000, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def is_allowed(self) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] >= cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) < self.max_requests:
            self._timestamps.append(now)
            return True
        return False

    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] >= cutoff:
            self._timestamps.popleft()
        return max(0, self.max_requests - len(self._timestamps))

    def reset_at(self) -> float:
        if not self._timestamps:
            return time.time()
        return self._timestamps[0] + self.window_seconds


_default_rate_limiter = GitHubRateLimiter()


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    pattern = r"github\.com/([^/]+)/([^/]+)/pulls?/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


async def fetch_pr_context(
    owner: str, repo: str, pr_number: int, token: str | None = None
) -> dict:
    effective_token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        pr_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()

        diff_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={**headers, "Accept": "application/vnd.github.v3.diff"},
        )
        diff_resp.raise_for_status()
        diff_text = diff_resp.text

        # Paginate through all files
        files_data: list[dict] = []
        page = 1
        while True:
            files_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            files_resp.raise_for_status()
            page_data = files_resp.json()
            if not page_data:
                break
            files_data.extend(page_data)
            page += 1

    stats = ReviewStats(
        files_changed=pr_data["changed_files"],
        additions=pr_data["additions"],
        deletions=pr_data["deletions"],
        issues_by_severity={"ERROR": 0, "WARNING": 0, "INFO": 0},
    )

    return {
        "title": pr_data["title"],
        "description": pr_data.get("body") or "",
        "diff": diff_text,
        "files": [f["filename"] for f in files_data],
        "stats": stats,
        "head_sha": pr_data["head"]["sha"],
        "base_branch": pr_data["base"]["ref"],
        "head_branch": pr_data["head"]["ref"],
        "author_name": pr_data["user"]["login"],
        "author_avatar": pr_data["user"]["avatar_url"],
        "updated_at": pr_data["updated_at"],
        "created_at": pr_data.get("created_at", ""),
        "commits": pr_data.get("commits", 0),
        "files_detail": [
            {
                "filename": f["filename"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "status": f.get("status", "modified"),  # added / modified / removed / renamed
                "patch": f.get("patch", ""),             # 该文件自己的 diff，无截断
            }
            for f in files_data
        ],
    }


def get_pr_author(pr_data: dict) -> str:
    """Return the PR author login."""
    return pr_data.get("user", {}).get("login", "unknown")
