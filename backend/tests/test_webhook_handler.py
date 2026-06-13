import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
_TEST_SECRET = "test-webhook-secret"


def make_signature(body: bytes, secret: str = _TEST_SECRET) -> str:
    import hashlib
    import hmac
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture(autouse=True)
def _set_env():
    old = os.environ.get("GITHUB_WEBHOOK_SECRET")
    os.environ["GITHUB_WEBHOOK_SECRET"] = _TEST_SECRET
    app.state.redis = None
    yield
    if old is None:
        del os.environ["GITHUB_WEBHOOK_SECRET"]
    else:
        os.environ["GITHUB_WEBHOOK_SECRET"] = old


class TestWebhookPullRequest:
    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_opened_enqueues(self, mock_enqueue):
        body = b'{"action": "opened", "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}, "installation": {"id": 123}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "accepted"}
        mock_enqueue.assert_awaited_once()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_synchronize_enqueues(self, mock_enqueue):
        body = b'{"action": "synchronize", "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}, "installation": {"id": 123}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 202

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_labeled_ignored(self, mock_enqueue):
        body = b'{"action": "labeled", "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        mock_enqueue.assert_not_awaited()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_closed_ignored(self, mock_enqueue):
        body = b'{"action": "closed", "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        mock_enqueue.assert_not_awaited()


class TestWebhookIssueComment:
    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_at_prism_bot_enqueues(self, mock_enqueue):
        body = (
            b'{"action": "created", "comment": {"body": "@prism-bot review this"},'
            b' "issue": {"pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}},'
            b' "installation": {"id": 456}}'
        )
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "accepted"}
        mock_enqueue.assert_awaited_once()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_without_bot_ignored(self, mock_enqueue):
        body = (
            b'{"action": "created", "comment": {"body": "nice PR"},'
            b' "issue": {"pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}}}'
        )
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        mock_enqueue.assert_not_awaited()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_edited_ignored(self, mock_enqueue):
        body = (
            b'{"action": "edited", "comment": {"body": "@prism-bot review this"},'
            b' "issue": {"pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}}}'
        )
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        mock_enqueue.assert_not_awaited()


class TestWebhookUnsupported:
    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_unsupported_event_ignored(self, mock_enqueue):
        body = b'{"action": "created"}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        mock_enqueue.assert_not_awaited()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_missing_pr_url_returns_400(self, mock_enqueue):
        body = b'{"action": "opened", "pull_request": {}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": make_signature(body),
            },
        )
        assert resp.status_code == 400
        assert "No pull_request URL" in resp.text
        mock_enqueue.assert_not_awaited()

    @patch("app.routers.webhook.enqueue_review", new_callable=AsyncMock)
    def test_invalid_signature_returns_401(self, mock_enqueue):
        body = b'{"action": "opened", "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"}}'
        resp = client.post(
            "/api/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
            },
        )
        assert resp.status_code == 401
        mock_enqueue.assert_not_awaited()
