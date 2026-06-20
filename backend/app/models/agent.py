from enum import StrEnum

from pydantic import BaseModel


class AgentStatus(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FORMAT_ERROR = "format_error"  # LLM 返回了无法解析的 JSON
    RUNTIME_ERROR = "runtime_error"  # 网络、认证、NameError 等非格式问题


class FindingSchema(BaseModel):
    file: str
    line: int | None = None
    title: str
    description: str
    severity: str  # "ERROR" | "WARNING" | "INFO"
    confidence: float
    category: str  # "security" | "performance" | "quality"
    # Actual consequence type. Findings without actionable impact are filtered by Judge.
    impact_type: str | None = None
    impact_statement: str | None = None
    diff_snippet: str | None = None
    evidence: list[str] | None = None  # 引用的代码行号/片段，为空则丢弃
    evidence_source: str = "DIFF"  # "DIFF" | "CONTEXT" — CONTEXT 表示来自 blast radius 跨文件上下文
    token_cost: float = 0.0  # estimated LLM token cost attributed to this finding


class AgentResult(BaseModel):
    status: AgentStatus
    findings: list[FindingSchema]
    error_message: str | None = None


class JudgeVerdict(BaseModel):
    findings: list[FindingSchema]
    merge_recommendation: str
    skipped_agents: list[str]
