from enum import StrEnum

from pydantic import BaseModel


class AgentStatus(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FORMAT_ERROR = "format_error"


class FindingSchema(BaseModel):
    file: str
    line: int | None = None
    title: str
    description: str
    severity: str  # "ERROR" | "WARNING" | "INFO"
    confidence: float
    category: str  # "security" | "performance" | "quality"
    diff_snippet: str | None = None
    evidence: list[str] | None = None  # 引用的代码行号/片段，为空则丢弃
    token_cost: float = 0.0  # estimated LLM token cost attributed to this finding


class AgentResult(BaseModel):
    status: AgentStatus
    findings: list[FindingSchema]
    error_message: str | None = None


class JudgeVerdict(BaseModel):
    findings: list[FindingSchema]
    merge_recommendation: str
    skipped_agents: list[str]
