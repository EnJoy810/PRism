from unittest.mock import AsyncMock, patch

import pytest

from app.graph import ReviewGraph, _verification_findings, split_diff_by_file


@pytest.mark.asyncio
async def test_graph_returns_expected_structure():
    graph = ReviewGraph()

    mock_pr_context = {
        "title": "Fix auth bug",
        "description": "Fixes the authentication issue",
        "diff": "+ const x = 1\n- const y = 2",
        "files": ["src/auth.ts"],
        "stats": None,
        "base_branch": "main",
        "head_branch": "fix/auth",
        "file_contents": {},
        "author_name": "testuser",
        "author_avatar": "",
        "updated_at": "",
        "created_at": "",
        "commits": 1,
        "files_detail": [],
    }

    async def mock_fetch(*args, **kwargs):
        return mock_pr_context

    async def mock_security_run(*args, **kwargs):
        from app.models.agent import AgentResult, AgentStatus, FindingSchema
        return AgentResult(
            status=AgentStatus.SUCCESS,
            findings=[
                FindingSchema(
                    file="src/auth.ts",
                    line=10,
                    title="SQL injection",
                    description="User input not sanitized",
                    severity="ERROR",
                    confidence=0.95,
                    category="security",
                )
            ],
        )

    mock_empty_run = AsyncMock(
        return_value=__import__("app.models.agent", fromlist=["AgentResult"]).AgentResult(
            status=__import__("app.models.agent", fromlist=["AgentStatus"]).AgentStatus.SUCCESS,
            findings=[],
        )
    )

    async def mock_judge_run(*args, **kwargs):
        return {
            "findings": [
                {
                    "file": "src/auth.ts",
                    "line": 10,
                    "title": "SQL injection",
                    "description": "User input not sanitized",
                    "severity": "ERROR",
                    "confidence": 0.95,
                    "category": "security",
                }
            ],
            "merge_recommendation": "REQUEST_CHANGES",
            "skipped_agents": [],
        }

    with (
        patch.object(graph, "fetch_pr_context", mock_fetch),
        patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
        patch.object(graph.security_agent, "run", mock_security_run),
        patch.object(graph.performance_agent, "run", mock_empty_run),
        patch.object(graph.quality_agent, "run", mock_empty_run),
        patch.object(graph.judge, "run", mock_judge_run),
    ):
        result = await graph.run(pr_url="https://github.com/owner/repo/pull/1")

    assert "summary" in result
    assert "risk_level" in result
    assert "issues" in result
    assert "merge_recommendation" in result
    assert len(result["issues"]) == 1
    assert result["issues"][0]["severity"] == "ERROR"
    assert result["merge_recommendation"] == "REQUEST_CHANGES"


@pytest.mark.asyncio
async def test_graph_handles_empty_findings():
    graph = ReviewGraph()

    mock_pr_context = {
        "title": "Refactor",
        "description": "Code cleanup",
        "diff": "+ const x = 1",
        "files": ["src/util.ts"],
        "stats": None,
        "base_branch": "main",
        "head_branch": "refactor",
        "file_contents": {},
        "author_name": "testuser",
        "author_avatar": "",
        "updated_at": "",
        "created_at": "",
        "commits": 1,
        "files_detail": [],
    }

    async def mock_fetch(*args, **kwargs):
        return mock_pr_context

    async def mock_empty_run(*args, **kwargs):
        from app.models.agent import AgentResult, AgentStatus
        return AgentResult(status=AgentStatus.SUCCESS, findings=[])

    async def mock_judge_run(*args, **kwargs):
        return {
            "findings": [],
            "merge_recommendation": "APPROVE",
            "skipped_agents": [],
        }

    with (
        patch.object(graph, "fetch_pr_context", mock_fetch),
        patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
        patch.object(graph.security_agent, "run", mock_empty_run),
        patch.object(graph.performance_agent, "run", mock_empty_run),
        patch.object(graph.quality_agent, "run", mock_empty_run),
        patch.object(graph.judge, "run", mock_judge_run),
    ):
        result = await graph.run(pr_url="https://github.com/owner/repo/pull/2")

    assert result["merge_recommendation"] == "APPROVE"
    assert len(result["issues"]) == 0


@pytest.mark.asyncio
async def test_graph_handles_agent_failure():
    graph = ReviewGraph()

    async def mock_fetch(*args, **kwargs):
        return {
            "title": "Test",
            "description": "",
            "diff": "+ x",
            "files": ["a.ts"],
            "stats": None,
            "base_branch": "main",
            "head_branch": "test",
            "file_contents": {},
            "author_name": "u",
            "author_avatar": "",
            "updated_at": "",
            "created_at": "",
            "commits": 1,
            "files_detail": [],
        }

    from app.models.agent import AgentResult, AgentStatus

    async def mock_security_fail(*args, **kwargs):
        return AgentResult(status=AgentStatus.TIMEOUT, findings=[])

    async def mock_ok_run(*args, **kwargs):
        return AgentResult(status=AgentStatus.SUCCESS, findings=[])

    async def mock_judge_run(*args, **kwargs):
        return {
            "findings": [],
            "merge_recommendation": "APPROVE",
            "skipped_agents": ["security"],
        }

    with (
        patch.object(graph, "fetch_pr_context", mock_fetch),
        patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
        patch.object(graph.security_agent, "run", mock_security_fail),
        patch.object(graph.performance_agent, "run", mock_ok_run),
        patch.object(graph.quality_agent, "run", mock_ok_run),
        patch.object(graph.judge, "run", mock_judge_run),
    ):
        result = await graph.run(pr_url="https://github.com/owner/repo/pull/3")

    assert result["merge_recommendation"] == "APPROVE"
    assert len(result["issues"]) == 0


SAMPLE_DIFF = """diff --git a/a.ts b/a.ts
--- a/a.ts
+++ b/a.ts
@@ -1 +1 @@
-old
+new
diff --git a/b.ts b/b.ts
--- a/b.ts
+++ b/b.ts
@@ -1 +1 @@
-old
+new
"""


class TestSplitDiffByFile:
    def test_splits_two_files(self):
        chunks = split_diff_by_file(SAMPLE_DIFF)
        assert set(chunks.keys()) == {"a.ts", "b.ts"}
        assert "a.ts" in chunks["a.ts"]
        assert "b.ts" in chunks["b.ts"]

    def test_empty_diff(self):
        assert split_diff_by_file("") == {}

    def test_single_file(self):
        diff = "diff --git a/x.ts b/x.ts\n--- a/x.ts\n+++ b/x.ts\n@@ -1 +1 @@\n-x\n+y\n"
        chunks = split_diff_by_file(diff)
        assert list(chunks.keys()) == ["x.ts"]
        assert "y" in chunks["x.ts"]

    def test_file_without_diff_marker_skipped(self):
        assert split_diff_by_file("some random text") == {}


class TestMultiRoundBatching:
    @pytest.mark.asyncio
    async def test_small_pr_single_round(self):
        from unittest.mock import patch

        from app.models.agent import AgentResult, AgentStatus

        graph = ReviewGraph()
        ctx = {
            "title": "small",
            "description": "",
            "diff": "+x",
            "files": [f"f{i}.ts" for i in range(5)],
            "stats": None,
        }

        async def mock_agent_run(*args, **kwargs):
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        async def mock_judge(*args, **kwargs):
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph.security_agent, "run", mock_agent_run),
            patch.object(graph.performance_agent, "run", mock_agent_run),
            patch.object(graph.quality_agent, "run", mock_agent_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            single = await graph._run_single(ctx, "", 0.0)
            multi = await graph._run_multi(ctx, "", 0.0)
        assert single["issues"] == multi["issues"]

    @pytest.mark.asyncio
    async def test_multi_round_runs_same_number_of_agents(self):
        graph = ReviewGraph()

        ctx = {
            "title": "big",
            "description": "",
            "diff": SAMPLE_DIFF,
            "files": [f"f{i}.ts" for i in range(35)],
            "stats": None,
        }

        call_count = 0

        async def counting_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            from app.models.agent import AgentResult, AgentStatus
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        async def mock_judge(*args, **kwargs):
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", counting_run),
            patch.object(graph.performance_agent, "run", counting_run),
            patch.object(graph.quality_agent, "run", counting_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            result = await graph.run(pr_url="", context=ctx)

        assert call_count == 6
        assert result["merge_recommendation"] == "APPROVE"


class TestVerificationIntegration:
    @pytest.mark.asyncio
    async def test_graph_passes_verification_to_judge(self):
        graph = ReviewGraph()
        ctx = {
            "title": "verify imports",
            "description": "",
            "diff": "+import { Search } from 'lucide-react'",
            "files": ["src/App.tsx"],
            "stats": None,
        }
        verification = {
            "imports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "lucide-react",
                    "status": "pass",
                    "detail": "dependencies",
                }
            ]
        }

        async def mock_agent_run(*args, **kwargs):
            from app.models.agent import AgentResult, AgentStatus
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        judge_kwargs = {}

        async def mock_judge(*args, **kwargs):
            judge_kwargs.update(kwargs)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_verification", AsyncMock(return_value=verification)),
            patch.object(graph.security_agent, "run", mock_agent_run),
            patch.object(graph.performance_agent, "run", mock_agent_run),
            patch.object(graph.quality_agent, "run", mock_agent_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            await graph.run(pr_url="", context=ctx)

        assert judge_kwargs["verification"] == verification

    def test_verification_findings_include_failed_imports(self):
        verification = {
            "imports": [
                {
                    "file": "src/App.tsx",
                    "line": 3,
                    "module": "@/components/Missing",
                    "statement": "import Missing from '@/components/Missing'",
                    "status": "fail",
                    "detail": "@/components/Missing not found from src/App.tsx",
                }
            ]
        }

        findings = _verification_findings(verification)

        assert len(findings) == 1
        assert findings[0].file == "src/App.tsx"
        assert findings[0].line == 3
        assert findings[0].title == "Unresolved import"
        assert findings[0].severity == "ERROR"
        assert findings[0].confidence == 1.0
        assert findings[0].evidence == ["import Missing from '@/components/Missing'"]

    def test_verification_findings_include_failed_named_exports(self):
        verification = {
            "exports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "@/components",
                    "symbol": "MarketingNavbar",
                    "statement": "import { MarketingNavbar } from '@/components'",
                    "status": "fail",
                    "detail": "MarketingNavbar is not exported by src/components/index.ts",
                }
            ]
        }

        findings = _verification_findings(verification)

        assert len(findings) == 1
        assert findings[0].title == "Missing named export"
        assert findings[0].impact_statement == "Importing MarketingNavbar from @/components fails at build time."
        assert findings[0].evidence == ["import { MarketingNavbar } from '@/components'"]

    def test_verification_findings_ignore_unknown_results(self):
        verification = {
            "imports": [
                {
                    "file": "src/App.tsx",
                    "line": 3,
                    "module": "@/components/Button",
                    "statement": "import Button from '@/components/Button'",
                    "status": "unknown",
                    "detail": "path alias is not configured",
                }
            ],
            "exports": [
                {
                    "file": "src/App.tsx",
                    "line": 4,
                    "module": "./components",
                    "symbol": "Button",
                    "statement": "import { Button } from './components'",
                    "status": "unknown",
                    "detail": "export * re-export requires recursive resolution",
                }
            ],
        }

        assert _verification_findings(verification) == []

    @pytest.mark.asyncio
    async def test_graph_includes_verifier_findings_in_judge_input(self):
        graph = ReviewGraph()
        ctx = {
            "title": "verify imports",
            "description": "",
            "diff": "diff --git a/src/App.tsx b/src/App.tsx\n@@ -1,0 +1,1 @@\n+import Missing from '@/components/Missing'",
            "files": ["src/App.tsx"],
            "stats": None,
        }
        verification = {
            "imports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "@/components/Missing",
                    "statement": "import Missing from '@/components/Missing'",
                    "status": "fail",
                    "detail": "@/components/Missing not found from src/App.tsx",
                }
            ]
        }

        async def mock_agent_run(*args, **kwargs):
            from app.models.agent import AgentResult, AgentStatus
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        captured_results = []

        async def mock_judge(results, **kwargs):
            captured_results.extend(results)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_verification", AsyncMock(return_value=verification)),
            patch.object(graph.security_agent, "run", mock_agent_run),
            patch.object(graph.performance_agent, "run", mock_agent_run),
            patch.object(graph.quality_agent, "run", mock_agent_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            await graph.run(pr_url="", context=ctx)

        verifier_results = [
            result for result in captured_results
            if result.findings and result.findings[0].title == "Unresolved import"
        ]
        assert len(verifier_results) == 1
        assert verifier_results[0].findings[0].title == "Unresolved import"
