from unittest.mock import AsyncMock, patch

from app.agents.base import BaseAgent
from app.models.agent import AgentResult, AgentStatus


class _TestAgent(BaseAgent):
    category = "test"
    system_prompt = "You are a test agent."

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        return f"Review this diff:\n{diff}"


async def test_agent_returns_agent_result():
    agent = _TestAgent(api_key="sk-test")
    mock_response = (
        "<think>Analyzing...</think>\n"
        '{"findings": []}'
    )

    with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
        result = await agent.run(diff="+ const x = 1")
        assert isinstance(result, AgentResult)
        assert result.status == AgentStatus.SUCCESS
        assert result.findings == []


async def test_agent_parses_findings():
    agent = _TestAgent(api_key="sk-test")
    mock_response = (
        "<think>Found an issue</think>\n"
        '{"findings": ['
        '  {"file": "a.ts", "line": 5, "title": "Bug", "description": "desc",'
        '   "severity": "ERROR", "confidence": 0.9, "category": "test"}'
        "]}"
    )

    with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
        result = await agent.run(diff="+ const x = 1")
        assert result.status == AgentStatus.SUCCESS
        assert len(result.findings) == 1
        assert result.findings[0].title == "Bug"
        assert result.findings[0].severity == "ERROR"


async def test_agent_format_error_on_bad_json():
    agent = _TestAgent(api_key="sk-test")
    mock_response = "<think>Something</think>\nnot json at all"

    with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
        result = await agent.run(diff="+ const x = 1")
        assert result.status == AgentStatus.FORMAT_ERROR
        assert result.findings == []


async def test_agent_empty_findings():
    agent = _TestAgent(api_key="sk-test")
    mock_response = (
        "<think>No issues found</think>\n"
        '{"findings": []}'
    )

    with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
        result = await agent.run(diff="+ const x = 1")
        assert result.status == AgentStatus.SUCCESS
        assert result.findings == []


async def test_agent_passes_context_to_build_prompt():
    agent = _TestAgent(api_key="sk-test")
    mock_response = (
        "<think>ok</think>\n"
        '{"findings": []}'
    )

    with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
        result = await agent.run(diff="+ const x = 1", context={"pr_title": "Fix bug"})
        assert result.status == AgentStatus.SUCCESS
