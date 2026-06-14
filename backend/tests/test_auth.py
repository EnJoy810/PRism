from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import create_jwt, get_installation_token

_rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_DUMMY_PRIVATE_KEY = _rsa_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


@pytest.fixture
def mock_config():
    with patch("app.auth.load_config") as mock_load:
        cfg = type("Config", (), {
            "github_app_id": 123456,
            "github_app_private_key": _DUMMY_PRIVATE_KEY,
        })()
        mock_load.return_value = cfg
        yield mock_load


class TestCreateJWT:
    def test_returns_string(self, mock_config):
        token = create_jwt()
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_raises_without_app_id(self):
        with (
            patch("app.auth.load_config") as mock_load,
        ):
            cfg = type("Config", (), {
                "github_app_id": None,
                "github_app_private_key": _DUMMY_PRIVATE_KEY,
            })()
            mock_load.return_value = cfg
            with pytest.raises(ValueError, match="github_app_id"):
                create_jwt()

    def test_raises_without_private_key(self):
        with (
            patch("app.auth.load_config") as mock_load,
        ):
            cfg = type("Config", (), {
                "github_app_id": 123456,
                "github_app_private_key": "",
            })()
            mock_load.return_value = cfg
            with pytest.raises(ValueError, match="github_app_private_key"):
                create_jwt()


class TestGetInstallationToken:
    @pytest.mark.asyncio
    async def test_returns_token(self, mock_config):
        mock_token = "v1.installation.token.abc"
        mock_expires = "2026-06-15T00:00:00Z"

        async def mock_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.json = MagicMock(return_value={
                "token": mock_token,
                "expires_at": mock_expires,
            })
            resp.raise_for_status = MagicMock()
            resp.status_code = 201
            return resp

        with (
            patch("app.auth.create_jwt", return_value="fake-jwt"),
            patch("httpx.AsyncClient") as MockClient,
        ):
            client = AsyncMock()
            client.post = mock_post
            MockClient.return_value.__aenter__.return_value = client

            result = await get_installation_token(42)

        assert result == mock_token

    @pytest.mark.asyncio
    async def test_caches_token(self, mock_config):
        mock_token = "v1.cached.token"

        call_count = 0

        async def mock_post(url, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.json = MagicMock(return_value={
                "token": mock_token,
                "expires_at": "2099-12-31T00:00:00Z",
            })
            resp.raise_for_status = MagicMock()
            resp.status_code = 201
            return resp

        with (
            patch("app.auth.create_jwt", return_value="fake-jwt"),
            patch("httpx.AsyncClient") as MockClient,
        ):
            client = AsyncMock()
            client.post = mock_post
            MockClient.return_value.__aenter__.return_value = client

            token1 = await get_installation_token(99)
            token2 = await get_installation_token(99)

        assert token1 == token2 == mock_token
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_expired_token_renewed(self, mock_config):
        mock_token_old = "v1.token.old"
        mock_token_new = "v1.token.new"

        call_count = 0

        async def mock_post(url, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            expires = "2020-01-01T00:00:00Z" if call_count == 1 else "2099-12-31T00:00:00Z"
            token = mock_token_old if call_count == 1 else mock_token_new
            resp = MagicMock()
            resp.json = MagicMock(return_value={
                "token": token,
                "expires_at": expires,
            })
            resp.raise_for_status = MagicMock()
            resp.status_code = 201
            return resp

        with (
            patch("app.auth.create_jwt", return_value="fake-jwt"),
            patch("httpx.AsyncClient") as MockClient,
            patch("app.auth.time") as mock_time,
        ):
            mock_time.time.return_value = 9999999999
            client = AsyncMock()
            client.post = mock_post
            MockClient.return_value.__aenter__.return_value = client

            token1 = await get_installation_token(77)
            token2 = await get_installation_token(77)

        assert token1 == mock_token_old
        assert token2 == mock_token_new
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_installations_different_tokens(self, mock_config):
        async def mock_post(url, *args, **kwargs):
            inst_id = url.rsplit("/", 2)[-2]
            resp = MagicMock()
            resp.json = MagicMock(return_value={
                "token": f"token-for-{inst_id}",
                "expires_at": "2099-12-31T00:00:00Z",
            })
            resp.raise_for_status = MagicMock()
            resp.status_code = 201
            return resp

        with (
            patch("app.auth.create_jwt", return_value="fake-jwt"),
            patch("httpx.AsyncClient") as MockClient,
        ):
            client = AsyncMock()
            client.post = mock_post
            MockClient.return_value.__aenter__.return_value = client

            token_a = await get_installation_token(100)
            token_b = await get_installation_token(200)

        assert token_a != token_b

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, mock_config):
        async def mock_post(url, *args, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock(side_effect=Exception("401 Unauthorized"))
            resp.status_code = 401
            return resp

        with (
            patch("app.auth.create_jwt", return_value="fake-jwt"),
            patch("httpx.AsyncClient") as MockClient,
        ):
            client = AsyncMock()
            client.post = mock_post
            MockClient.return_value.__aenter__.return_value = client

            with pytest.raises(Exception, match="401"):
                await get_installation_token(9999)
