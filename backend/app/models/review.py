from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class WalkthroughEntry(BaseModel):
    file: str
    summary: str


class ReviewIssue(BaseModel):
    severity: Severity
    file: str
    line: int | None = None
    position: int | None = None
    title: str
    description: str
    suggestion: str | None = None
    diff_snippet: str | None = None
    confidence: float = 1.0
    impact_type: str | None = None
    impact_statement: str | None = None


class ReviewStats(BaseModel):
    files_changed: int
    additions: int
    deletions: int
    issues_by_severity: dict[str, int] = {}


class RiskArea(BaseModel):
    level: str  # "HIGH" | "MEDIUM" | "LOW"
    file: str
    title: str
    impact: str


class MergeRecommendation(BaseModel):
    decision: str  # "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
    confidence: int  # 0-100
    reasons: list[str]


class ReviewResult(BaseModel):
    pr_url: str
    summary: str
    risk_level: str
    walkthrough: list[WalkthroughEntry] = []
    issues: list[ReviewIssue]
    stats: ReviewStats
    priority_files: list[str] = []
    risk_areas: list[RiskArea] = []
    merge_recommendation: MergeRecommendation | None = None


class ReviewRequest(BaseModel):
    pr_url: str
    github_token: str | None = None
    perspective: str = "default"
    options: dict | None = None
    review_type: str = "all"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class PostReviewRequest(BaseModel):
    pr_url: str
    github_token: str
    result: dict
