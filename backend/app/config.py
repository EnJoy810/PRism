import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    max_per_review_usd: float = 0.50
    max_tokens_per_call: int = 4096


class AgentConfig(BaseModel):
    expert_model: str = "deepseek-v4-flash"
    judge_model: str = "deepseek-v4-pro"


class FilterConfig(BaseModel):
    min_confidence: float = 0.6
    severity_threshold: Literal["ERROR", "WARNING", "INFO"] = "WARNING"


class ReviewConfig(BaseModel):
    budget: BudgetConfig = BudgetConfig()
    agents: AgentConfig = AgentConfig()
    filters: FilterConfig = FilterConfig()
    skip: list[str] = Field(default_factory=lambda: ["*.lock", "*.snap", "*.min.js"])


class GithubConfig(BaseModel):
    webhook_secret: str = ""


class PrismConfig(BaseModel):
    deepseek_api_key: str
    github_token: str = ""
    github_webhook_secret: str = ""
    redis_url: str = "redis://localhost:6379/0"
    review: ReviewConfig = ReviewConfig()
    github: GithubConfig = GithubConfig()

    @property
    def webhook_secret_bytes(self) -> bytes:
        return self.github_webhook_secret.encode()


def load_config(path: str | Path | None = None) -> PrismConfig:
    path = Path(path) if path else Path.cwd() / "prism.yaml"

    data: dict = {}
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    review_data = data.get("review", {})
    github_data = data.get("github", {})

    return PrismConfig(
        deepseek_api_key=_env_or("DEEPSEEK_API_KEY", ""),
        github_token=_env_or("GITHUB_TOKEN", ""),
        github_webhook_secret=_env_or(
            "GITHUB_WEBHOOK_SECRET", github_data.get("webhook_secret", "")
        ),
        redis_url=_env_or("REDIS_URL", "redis://localhost:6379/0"),
        review=ReviewConfig(
            budget=BudgetConfig(**(review_data.get("budget", {}))),
            agents=AgentConfig(**(review_data.get("agents", {}))),
            filters=FilterConfig(**(review_data.get("filters", {}))),
            skip=review_data.get("skip", ["*.lock", "*.snap", "*.min.js"]),
        ),
        github=GithubConfig(
            webhook_secret=_env_or(
                "GITHUB_WEBHOOK_SECRET", github_data.get("webhook_secret", "")
            )
        ),
    )


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key, default)
