from unittest.mock import AsyncMock, patch

import pytest

from app.agents.performance import PerformanceAgent
from app.agents.quality import QualityAgent
from app.agents.security import SecurityAgent


class TestSecurityAgent:
    def test_category(self):
        agent = SecurityAgent(api_key="sk-test")
        assert agent.category == "security"

    def test_build_prompt_contains_diff(self):
        agent = SecurityAgent(api_key="sk-test")
        prompt = agent.build_prompt("+ const x = 1")
        assert "+ const x = 1" in prompt
        assert "security" in prompt or "安全" in prompt

    def test_build_prompt_with_context(self):
        agent = SecurityAgent(api_key="sk-test")
        prompt = agent.build_prompt("+ foo", context={"pr_title": "Fix auth"})
        assert "Fix auth" in prompt

    @pytest.mark.asyncio
    async def test_run_with_mock(self):
        agent = SecurityAgent(api_key="sk-test")
        mock_response = (
            "<think>No security issues</think>\n"
            '{"findings": []}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ const x = 1")
            assert result.status.value == "success"
            assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_run_with_finding(self):
        agent = SecurityAgent(api_key="sk-test")
        mock_response = (
            "<think>SQL injection</think>\n"
            '{"findings": [{"file": "a.ts", "line": 5, "title": "SQL injection", '
            '"description": "desc", "severity": "ERROR", "confidence": 0.95, '
            '"category": "security"}]}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ db.query(userInput)")
            assert len(result.findings) == 1
            assert result.findings[0].category == "security"
            assert result.findings[0].severity == "ERROR"


class TestPerformanceAgent:
    def test_category(self):
        agent = PerformanceAgent(api_key="sk-test")
        assert agent.category == "performance"

    def test_build_prompt_contains_diff(self):
        agent = PerformanceAgent(api_key="sk-test")
        prompt = agent.build_prompt("+ for i in range(1000)")
        assert "for i in range(1000)" in prompt

    @pytest.mark.asyncio
    async def test_run_empty(self):
        agent = PerformanceAgent(api_key="sk-test")
        mock_response = (
            "<think>No perf issues</think>\n"
            '{"findings": []}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ const x = 1")
            assert result.status.value == "success"
            assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_run_with_finding(self):
        agent = PerformanceAgent(api_key="sk-test")
        mock_response = (
            "<think>N+1 query</think>\n"
            '{"findings": [{"file": "b.ts", "line": 10, "title": "N+1 query", '
            '"description": "desc", "severity": "ERROR", "confidence": 0.9, '
            '"category": "performance"}]}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ for user in users:")
            assert len(result.findings) == 1
            assert result.findings[0].category == "performance"


class TestQualityAgent:
    def test_category(self):
        agent = QualityAgent(api_key="sk-test")
        assert agent.category == "quality"

    def test_build_prompt_contains_diff(self):
        agent = QualityAgent(api_key="sk-test")
        prompt = agent.build_prompt("+ function foo()")
        assert "function foo()" in prompt

    def test_build_prompt_targets_correctness_regressions(self):
        agent = QualityAgent(api_key="sk-test")
        prompt = agent.build_prompt("+ const isOpen = !!openForm.in_reply_to_snippet")
        system = agent.system_prompt
        assert "logic bugs" in system or "correctness" in system
        assert "linter" in system  # must exclude linter-catchable issues
        assert "style" in system.lower() or "naming" in system.lower()

    @pytest.mark.asyncio
    async def test_run_empty(self):
        agent = QualityAgent(api_key="sk-test")
        mock_response = (
            "<think>No quality issues</think>\n"
            '{"findings": []}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ const x = 1")
            assert result.status.value == "success"
            assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_run_with_finding(self):
        agent = QualityAgent(api_key="sk-test")
        mock_response = (
            "<think>Duplicated code</think>\n"
            '{"findings": [{"file": "c.ts", "line": 3, "title": "Duplicated code", '
            '"description": "desc", "severity": "WARNING", "confidence": 0.85, '
            '"category": "quality"}]}'
        )
        with patch.object(agent.client, "chat", AsyncMock(return_value=mock_response)):
            result = await agent.run(diff="+ function foo() { return 1 }")
            assert len(result.findings) == 1
            assert result.findings[0].category == "quality"
