import hashlib
import hmac

from app.routers.webhook import verify_hmac_signature


class TestVerifyHMAC:
    def test_valid_signature(self):
        secret = "my_webhook_secret"
        body = b'{"action": "opened", "pull_request": {}}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_hmac_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        secret = "my_webhook_secret"
        body = b'{"action": "opened"}'
        bad_sig = "sha256=" + "0" * 64
        assert verify_hmac_signature(body, bad_sig, secret) is False

    def test_missing_header_returns_false(self):
        assert verify_hmac_signature(b"{}", None, "secret") is False
        assert verify_hmac_signature(b"{}", "", "secret") is False

    def test_wrong_secret(self):
        secret = "correct_secret"
        body = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(b"wrong_secret", body, hashlib.sha256).hexdigest()
        assert verify_hmac_signature(body, sig, secret) is False

    def test_invalid_prefix(self):
        assert verify_hmac_signature(b"{}", "md5=abc123", "secret") is False
