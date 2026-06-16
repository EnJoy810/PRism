from unittest.mock import AsyncMock, patch

import pytest

from app.graph import (
    ReviewGraph,
    _changed_node_ids_from_diff,
    _split_into_batches,
    _verification_findings,
    split_diff_by_file,
)
from app.services.evidence import publication_gate


@pytest.mark.asyncio
async def test_graph_returns_expected_structure():
    graph = ReviewGraph()

    mock_pr_context = {
        "title": "Fix auth bug",
        "description": "Fixes the authentication issue",
        "diff": "diff --git a/src/auth.ts b/src/auth.ts\n+++ b/src/auth.ts\n@@ -0,0 +1,1 @@\n+ const x = 1",
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
                    line=1,
                    title="SQL injection",
                    description="User input not sanitized",
                    severity="ERROR",
                    confidence=0.95,
                    category="security",
                    evidence=["const x = 1"],
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
                    "line": 1,
                    "title": "SQL injection",
                    "description": "User input not sanitized",
                    "severity": "ERROR",
                    "confidence": 0.95,
                    "category": "security",
                    "evidence": ["const x = 1"],
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


def test_changed_body_line_maps_to_enclosing_function(tmp_path):
    import sqlite3

    db = tmp_path / "index.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            file TEXT,
            name TEXT,
            start_line INTEGER,
            end_line INTEGER,
            code TEXT,
            file_hash TEXT
        );
        INSERT INTO nodes VALUES (7, 'src/app.py', 'handle', 10, 20, 'def handle(): pass', 'h1');
    """)
    conn.commit()
    conn.close()
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -14,2 +14,3 @@ def handle():
 old_call()
+new_call()
 unchanged()
"""

    assert _changed_node_ids_from_diff(db, diff) == {7}


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

    @pytest.mark.asyncio
    async def test_large_diff_uses_multi_round_even_with_few_files(self):
        graph = ReviewGraph()
        ctx = {
            "title": "large diff",
            "description": "",
            "diff": "diff --git a/a.py b/a.py\n+++ b/a.py\n" + "+x = 1\n" * 66000,
            "files": ["a.py"],
            "stats": None,
        }

        with (
            patch.object(graph, "_run_single", AsyncMock(return_value={"mode": "single"})),
            patch.object(graph, "_run_multi", AsyncMock(return_value={"mode": "multi"})),
        ):
            result = await graph.run(pr_url="", context=ctx)

        assert result == {"mode": "multi"}

    def test_split_into_batches_splits_single_large_file_by_token_budget(self):
        ctx = {
            "title": "large diff",
            "description": "",
            "diff": "diff --git a/a.py b/a.py\n+++ b/a.py\n" + "+x = 1\n" * 66000,
            "files": ["a.py"],
            "stats": None,
        }

        batches = _split_into_batches(ctx, 30)

        assert len(batches) > 1
        assert all(len(batch["diff"]) // 4 <= 16384 for batch in batches)


class TestGitHubTokenPropagation:
    @pytest.mark.asyncio
    async def test_run_stores_github_token_in_context_for_internal_fetchers(self):
        graph = ReviewGraph()
        ctx = {
            "title": "private repo",
            "description": "",
            "diff": "+x",
            "files": ["a.py"],
            "stats": None,
        }
        captured = {}

        async def mock_fetch_symbol(context, _pr_url):
            captured["symbol_token"] = context.get("github_token")
            return {}

        async def mock_fetch_blast(context, _pr_url):
            captured["blast_token"] = context.get("github_token")
            return []

        async def mock_fetch_sast(context, _pr_url):
            captured["sast_token"] = context.get("github_token")
            return {}

        async def mock_fetch_verification(context, _pr_url):
            captured["verification_token"] = context.get("github_token")
            return {}

        with (
            patch.object(graph, "_fetch_symbol_context", mock_fetch_symbol),
            patch.object(graph, "_fetch_blast_radius", mock_fetch_blast),
            patch.object(graph, "_fetch_sast_findings", mock_fetch_sast),
            patch.object(graph, "_fetch_verification", mock_fetch_verification),
            patch.object(graph, "_run_single", AsyncMock(return_value={"issues": []})),
        ):
            await graph.run(pr_url="", context=ctx, github_token="ghs_installation")

        assert captured == {
            "symbol_token": "ghs_installation",
            "blast_token": "ghs_installation",
            "sast_token": "ghs_installation",
            "verification_token": "ghs_installation",
        }


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


class TestPublicationGate:
    def test_filters_info_and_fabricated_lines(self):
        """publication_gate 应过滤：INFO 级别、行号完全不在 diff 里的 finding。
        context 行上的 finding（如删除类 bug）应放行。"""
        from app.models.agent import FindingSchema

        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 old_call()
+new_call()
"""
        findings = [
            FindingSchema(
                file="app.py",
                line=2,
                title="Keep added issue",
                description="desc",
                severity="WARNING",
                confidence=0.9,
                category="quality",
                evidence=["new_call()"],
            ),
            FindingSchema(
                file="app.py",
                line=1,
                title="Context line issue",  # line=1 是 context 行，应放行（删除类 bug）
                description="desc",
                severity="ERROR",
                confidence=0.9,
                category="quality",
                evidence=["old_call()"],
            ),
            FindingSchema(
                file="app.py",
                line=999,  # 完全不在 diff 里的行号，应过滤
                title="Fabricated line issue",
                description="desc",
                severity="ERROR",
                confidence=0.9,
                category="quality",
                evidence=["old_call()"],
            ),
            FindingSchema(
                file="app.py",
                line=2,
                title="Info issue",
                description="desc",
                severity="INFO",
                confidence=0.9,
                category="quality",
                evidence=["new_call()"],
            ),
        ]

        gated = publication_gate(findings, diff)
        titles = [f.title for f in gated]

        assert "Keep added issue" in titles
        assert "Context line issue" in titles   # 删除类 bug 放行
        assert "Info issue" not in titles        # INFO 过滤
        assert "Fabricated line issue" not in titles  # 捏造行号过滤

    def test_deduplicates_same_file_line_and_title(self):
        from app.models.agent import FindingSchema

        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,1 @@
+new_call()
"""
        first = FindingSchema(
            file="app.py",
            line=1,
            title="Duplicate issue",
            description="desc",
            severity="WARNING",
            confidence=0.8,
            category="quality",
            evidence=["new_call()"],
        )
        second = first.model_copy(update={"severity": "ERROR", "confidence": 0.9})

        gated = publication_gate([first, second], diff)

        assert len(gated) == 1
        assert gated[0].severity == "ERROR"
        assert gated[0].confidence == 0.9


class TestSastIntegration:
    @pytest.mark.asyncio
    async def test_graph_passes_sast_findings_to_judge(self):
        graph = ReviewGraph()
        ctx = {
            "title": "sast",
            "description": "",
            "diff": "diff --git a/app.py b/app.py\n@@ -0,0 +1,1 @@\n+subprocess.run(cmd, shell=True)",
            "files": ["app.py"],
            "stats": None,
        }
        sast = {
            "security": [
                {
                    "file": "app.py",
                    "line": 1,
                    "title": "subprocess-shell-true",
                    "description": "shell=True",
                    "severity": "ERROR",
                    "confidence": 0.95,
                    "category": "security",
                    "impact_type": "security_risk",
                    "impact_statement": "shell command can be injected",
                    "evidence": ["+subprocess.run(cmd, shell=True)"],
                }
            ],
            "quality": [],
        }
        async def mock_agent_run(_diff, context):
            from app.models.agent import AgentResult, AgentStatus
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        captured_results = []

        async def mock_judge(results, **kwargs):
            captured_results.extend(results)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_sast_findings", AsyncMock(return_value=sast)),
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", mock_agent_run),
            patch.object(graph.performance_agent, "run", mock_agent_run),
            patch.object(graph.quality_agent, "run", mock_agent_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            await graph.run(pr_url="", context=ctx)

        assert any(
            result.findings and result.findings[0].title == "subprocess-shell-true"
            for result in captured_results
        )

    @pytest.mark.asyncio
    async def test_graph_includes_sast_findings_even_when_security_agent_fails(self):
        graph = ReviewGraph()
        ctx = {
            "title": "sast",
            "description": "",
            "diff": "diff --git a/app.py b/app.py\n@@ -0,0 +1,1 @@\n+subprocess.run(cmd, shell=True)",
            "files": ["app.py"],
            "stats": None,
        }
        sast = {
            "security": [
                {
                    "file": "app.py",
                    "line": 1,
                    "title": "subprocess-shell-true",
                    "description": "shell=True",
                    "severity": "ERROR",
                    "confidence": 0.95,
                    "category": "security",
                    "impact_type": "security_risk",
                    "impact_statement": "shell command can be injected",
                    "evidence": ["+subprocess.run(cmd, shell=True)"],
                }
            ],
            "quality": [],
        }

        from app.models.agent import AgentResult, AgentStatus

        async def mock_security_fail(*args, **kwargs):
            return AgentResult(status=AgentStatus.TIMEOUT, findings=[])

        async def mock_ok(*args, **kwargs):
            return AgentResult(status=AgentStatus.SUCCESS, findings=[])

        captured_results = []

        async def mock_judge(results, **kwargs):
            captured_results.extend(results)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_sast_findings", AsyncMock(return_value=sast)),
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", mock_security_fail),
            patch.object(graph.performance_agent, "run", mock_ok),
            patch.object(graph.quality_agent, "run", mock_ok),
            patch.object(graph.judge, "run", mock_judge),
        ):
            await graph.run(pr_url="", context=ctx)

        assert any(
            result.findings and result.findings[0].title == "subprocess-shell-true"
            for result in captured_results
        )

    @pytest.mark.asyncio
    async def test_graph_does_not_abort_when_all_llm_agents_fail_but_sast_has_findings(self):
        graph = ReviewGraph()
        ctx = {
            "title": "sast fallback",
            "description": "",
            "diff": "diff --git a/app.py b/app.py\n@@ -0,0 +1,1 @@\n+subprocess.run(cmd, shell=True)",
            "files": ["app.py"],
            "stats": None,
        }
        sast = {
            "security": [
                {
                    "file": "app.py",
                    "line": 1,
                    "title": "subprocess-shell-true",
                    "description": "shell=True",
                    "severity": "ERROR",
                    "confidence": 0.95,
                    "category": "security",
                    "impact_type": "security_risk",
                    "impact_statement": "shell command can be injected",
                    "evidence": ["+subprocess.run(cmd, shell=True)"],
                }
            ],
            "quality": [],
        }

        from app.models.agent import AgentResult, AgentStatus

        async def mock_budget_fail(*args, **kwargs):
            return AgentResult(
                status=AgentStatus.RUNTIME_ERROR,
                findings=[],
                error_message="Budget exceeded: 17105 > 16384",
            )

        captured_results = []

        async def mock_judge(results, **kwargs):
            captured_results.extend(results)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_sast_findings", AsyncMock(return_value=sast)),
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", mock_budget_fail),
            patch.object(graph.performance_agent, "run", mock_budget_fail),
            patch.object(graph.quality_agent, "run", mock_budget_fail),
            patch.object(graph.judge, "run", mock_judge),
        ):
            result = await graph.run(pr_url="", context=ctx)

        assert result["merge_recommendation"] == "APPROVE"
        assert any(
            item.status == AgentStatus.RUNTIME_ERROR
            and item.error_message == "Budget exceeded: 17105 > 16384"
            for item in captured_results
        )
        assert any(
            item.findings and item.findings[0].title == "subprocess-shell-true"
            for item in captured_results
        )
