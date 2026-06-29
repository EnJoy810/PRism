import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    max_per_review_usd: float = 0.50
    max_tokens_per_call: int = 16384


class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


class AgentConfig(BaseModel):
    expert_model: str = "deepseek-v4-flash"
    judge_model: str = "deepseek-v4-pro"


class FilterConfig(BaseModel):
    min_confidence: float = 0.7
    severity_threshold: Literal["ERROR", "WARNING", "INFO"] = "WARNING"


class StatsConfig(BaseModel):
    enabled: bool = True
    retention_days: int = 0
    max_records: int = 10000
    aggregate_interval_minutes: int = 60


class ReviewConfig(BaseModel):
    budget: BudgetConfig = BudgetConfig()
    agents: AgentConfig = AgentConfig()
    filters: FilterConfig = FilterConfig()
    skip: list[str] = Field(default_factory=lambda: ["*.lock", "*.snap", "*.min.js"])
    callgraph_backend: Literal["builtin", "codegraph"] = "builtin"
    callgraph_enabled: bool = True  # set to false to disable blast_radius entirely (diff-only mode)
    stats: StatsConfig = StatsConfig()


class GithubConfig(BaseModel):
    webhook_secret: str = ""
    app_id: int | None = None
    app_private_key: str = ""


class PrismConfig(BaseModel):
    deepseek_api_key: str
    github_token: str = ""
    github_webhook_secret: str = ""
    github_app_id: int | None = None
    github_app_private_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    review: ReviewConfig = ReviewConfig()
    github: GithubConfig = GithubConfig()
    llm: LLMConfig = LLMConfig()

    @property
    def webhook_secret_bytes(self) -> bytes:
        return self.github_webhook_secret.encode()


def load_config(path: str | Path | None = None) -> PrismConfig:
    if path:
        path = Path(path)
    else:
        cwd = Path.cwd()
        candidate = cwd / "prism.yaml"
        path = candidate if candidate.exists() else cwd.parent / "prism.yaml"

    data: dict = {}
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    review_data = data.get("review", {})
    github_data = data.get("github", {})
    llm_data = data.get("llm", {})

    github_app_id: int | None = None
    raw_id = _env_or("GITHUB_APP_ID", github_data.get("app_id") or "")
    if raw_id:
        github_app_id = int(raw_id)

    github_app_private_key = _env_or(
        "GITHUB_APP_PRIVATE_KEY", github_data.get("app_private_key") or ""
    )
    if not github_app_private_key:
        key_file = _env_or("GITHUB_APP_PRIVATE_KEY_FILE", "")
        if key_file:
            key_path = Path(key_file) if Path(key_file).is_absolute() else Path.cwd() / key_file
            if key_path.exists():
                github_app_private_key = key_path.read_text().strip()

    return PrismConfig(
        deepseek_api_key=_env_or("DEEPSEEK_API_KEY", ""),
        github_token=_env_or("GITHUB_TOKEN", ""),
        github_webhook_secret=_env_or(
            "GITHUB_WEBHOOK_SECRET", github_data.get("webhook_secret", "")
        ),
        github_app_id=github_app_id,
        github_app_private_key=github_app_private_key,
        redis_url=_env_or("REDIS_URL", "redis://localhost:6379/0"),
        review=ReviewConfig(
            budget=BudgetConfig(**(review_data.get("budget", {}))),
            agents=AgentConfig(**(review_data.get("agents", {}))),
            filters=FilterConfig(**(review_data.get("filters", {}))),
            skip=review_data.get("skip", ["*.lock", "*.snap", "*.min.js"]),
            callgraph_backend=review_data.get("callgraph_backend", "builtin"),
        ),
        github=GithubConfig(
            webhook_secret=_env_or(
                "GITHUB_WEBHOOK_SECRET", github_data.get("webhook_secret", "")
            )
        ),
        llm=LLMConfig(
            api_key=_env_or("LLM_API_KEY", llm_data.get("api_key", "")),
            base_url=_env_or(
                "LLM_BASE_URL", llm_data.get("base_url", "https://api.deepseek.com")
            ),
            model=_env_or("LLM_MODEL", llm_data.get("model", "deepseek-v4-flash")),
        ),
    )


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key, default)
