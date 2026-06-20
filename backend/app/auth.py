"""GitHub App authentication: JWT generation and installation token exchange."""

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from app.config import load_config

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TOKEN_CACHE: dict[int, tuple[str, float]] = {}  # installation_id -> (token, expires_at)


def _load_private_key() -> str:
    cfg = load_config()
    key = cfg.github_app_private_key
    if not key:
        raise ValueError(
            "github_app_private_key is not configured. "
            "Set GITHUB_APP_PRIVATE_KEY env var or github.app_private_key in prism.yaml"
        )
    return key


def _load_app_id() -> int:
    cfg = load_config()
    app_id = cfg.github_app_id
    if not app_id:
        raise ValueError(
            "github_app_id is not configured. "
            "Set GITHUB_APP_ID env var or github.app_id in prism.yaml"
        )
    return app_id


def create_jwt() -> str:
    app_id = _load_app_id()
    private_key = _load_private_key()
    now = datetime.now(UTC)
    payload = {
        "iat": int(now.timestamp()) - 60,
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "iss": str(app_id),
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    cached = _TOKEN_CACHE.get(installation_id)
    if cached:
        token, expires_at = cached
        if time.time() < expires_at - 300:
            return token

    jwt_token = create_jwt()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    expires_at_str = data.get("expires_at", "")
    if expires_at_str:
        expires_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        expires_at = expires_dt.timestamp()
    else:
        expires_at = time.time() + 3600

    _TOKEN_CACHE[installation_id] = (token, expires_at)
    logger.info(
        "Obtained installation token for installation %d, expires at %s",
        installation_id, expires_at_str,
    )
    return token
