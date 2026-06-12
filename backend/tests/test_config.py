import os
import tempfile

import yaml

from app.config import PrismConfig, load_config


def test_load_config_from_yaml():
    yaml_content = {
        "review": {
            "budget": {"max_per_review_usd": 0.30, "max_tokens_per_call": 2048},
            "agents": {"expert_model": "deepseek-v4-flash", "judge_model": "deepseek-v4-pro"},
            "filters": {"min_confidence": 0.5, "severity_threshold": "WARNING"},
            "skip": ["*.lock", "*.snap"],
        },
        "github": {"webhook_secret": ""},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.review.budget.max_per_review_usd == 0.30
        assert cfg.review.budget.max_tokens_per_call == 2048
        assert cfg.review.agents.expert_model == "deepseek-v4-flash"
        assert cfg.review.agents.judge_model == "deepseek-v4-pro"
        assert cfg.review.filters.min_confidence == 0.5
        assert cfg.review.filters.severity_threshold == "WARNING"
        assert cfg.review.skip == ["*.lock", "*.snap"]
    finally:
        os.unlink(tmp_path)


def test_load_config_defaults():
    yaml_content = {}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.review.budget.max_per_review_usd == 0.50
        assert cfg.review.budget.max_tokens_per_call == 4096
        assert cfg.review.agents.expert_model == "deepseek-v4-flash"
        assert cfg.review.filters.min_confidence == 0.6
        assert cfg.review.filters.severity_threshold == "WARNING"
        assert cfg.review.skip == ["*.lock", "*.snap", "*.min.js"]
    finally:
        os.unlink(tmp_path)


def test_load_config_file_not_found(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    cfg = load_config("/nonexistent/prism.yaml")
    assert cfg.deepseek_api_key == "sk-test"
    assert cfg.review.budget.max_per_review_usd == 0.50


def test_env_overrides_yaml(monkeypatch):
    yaml_content = {
        "review": {
            "budget": {"max_per_review_usd": 0.30},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        tmp_path = f.name

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-from-env")

    try:
        cfg = load_config(tmp_path)
        assert cfg.deepseek_api_key == "sk-from-env"
        assert cfg.github_token == "ghp-from-env"
        assert cfg.review.budget.max_per_review_usd == 0.30
    finally:
        os.unlink(tmp_path)


def test_webhook_secret_from_env_overrides_yaml(monkeypatch):
    yaml_content = {
        "github": {"webhook_secret": "from-yaml"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        tmp_path = f.name

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "from-env")

    try:
        cfg = load_config(tmp_path)
        assert cfg.github_webhook_secret == "from-env"
    finally:
        os.unlink(tmp_path)


def test_prism_config_model():
    cfg = PrismConfig(
        deepseek_api_key="sk-test",
        github_token="ghp-test",
        github_webhook_secret="secret123",
        redis_url="redis://localhost:6379/1",
    )
    assert cfg.deepseek_api_key == "sk-test"
    assert cfg.github_webhook_secret == "secret123"
    assert cfg.redis_url == "redis://localhost:6379/1"
    assert cfg.review.budget.max_per_review_usd == 0.50


def test_webhook_secret_bytes():
    cfg = PrismConfig(deepseek_api_key="sk-test", github_webhook_secret="abc")
    assert cfg.webhook_secret_bytes == b"abc"
