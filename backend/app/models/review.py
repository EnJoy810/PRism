from enum import Enum
from pydantic import BaseModel


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ReviewIssue(BaseModel):
    severity: Severity
    file: str
    line: int | None = None
    title: str
    description: str
    suggestion: str | None = None


class ReviewStats(BaseModel):
    files_changed: int
    additions: int
    deletions: int
    issues_by_severity: dict[str, int]


class ReviewResult(BaseModel):
    pr_url: str
    summary: str
    risk_level: str
    issues: list[ReviewIssue]
    stats: ReviewStats


class ReviewRequest(BaseModel):
    pr_url: str
    github_token: str | None = None
    perspective: str = "default"
    options: dict | None = None


class PostReviewRequest(BaseModel):
    pr_url: str
    github_token: str
    result: dict
