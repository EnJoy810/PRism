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
    async def test_large_diff_uses_per_file(self):
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
            patch.object(graph, "_run_per_file", AsyncMock(return_value={"mode": "per-file"})),
        ):
            result = await graph.run(pr_url="", context=ctx)

        assert result == {"mode": "per-file"}

    @pytest.mark.asyncio
    async def test_small_diff_within_8000_uses_multi_round_when_batching_needed(self):
        graph = ReviewGraph()
        # 36 files triggers batch (BATCH_SIZE=30), diff ~3000 tokens
        ctx = {
            "title": "big",
            "description": "",
            "diff": SAMPLE_DIFF,
            "files": [f"f{i}.ts" for i in range(36)],
            "stats": None,
        }

        with (
            patch.object(graph, "_run_single", AsyncMock(return_value={"mode": "single"})),
            patch.object(graph, "_run_multi", AsyncMock(return_value={"mode": "multi"})),
            patch.object(graph, "_run_per_file", AsyncMock(return_value={"mode": "per-file"})),
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

    def test_context_source_bypasses_line_check_with_evidence(self):
        """evidence_source=CONTEXT 的 finding 不受行号门控限制，但 evidence 不能为空。"""
        from app.models.agent import FindingSchema

        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-def foo(x): return x
+def foo(): return 0
"""
        # 跨文件调用方，file 不在 diff 里，行号也不在 diff 里
        context_finding = FindingSchema(
            file="b.py",
            line=10,
            title="Caller passes arg that no longer exists",
            description="b.py calls foo(x) but foo() now takes no args",
            severity="ERROR",
            confidence=0.9,
            category="quality",
            evidence_source="CONTEXT",
            evidence=["result = foo(user_input)"],
        )
        # CONTEXT 来源但 evidence 为空，应被过滤
        context_no_evidence = FindingSchema(
            file="b.py",
            line=10,
            title="Hallucinated context finding",
            description="no evidence",
            severity="ERROR",
            confidence=0.9,
            category="quality",
            evidence_source="CONTEXT",
            evidence=[],
        )

        gated = publication_gate([context_finding, context_no_evidence], diff)
        titles = [f.title for f in gated]

        assert "Caller passes arg that no longer exists" in titles
        assert "Hallucinated context finding" not in titles


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


class TestPerFileSplitting:
    @staticmethod
    def _make_multifile_diff(file_count: int = 4) -> str:
        chunks = []
        for i in range(file_count):
            chunks.append(
                f"diff --git a/f{i}.py b/f{i}.py\n"
                f"--- a/f{i}.py\n"
                f"+++ b/f{i}.py\n"
                f"@@ -0,0 +1,1 @@\n+ x = {i}\n"
            )
        return "\n".join(chunks)

    def test_should_skip_diff_file_vendor(self):
        from app.graph import _should_skip_diff_file

        assert _should_skip_diff_file("vendor/lib/c.py")
        assert _should_skip_diff_file("node_modules/pkg/index.js")
        assert _should_skip_diff_file("dist/bundle.js")
        assert _should_skip_diff_file(".git/config")

    def test_should_skip_diff_file_lock(self):
        from app.graph import _should_skip_diff_file

        assert _should_skip_diff_file("package-lock.json")
        assert _should_skip_diff_file("yarn.lock")
        assert _should_skip_diff_file("Cargo.lock")
        assert _should_skip_diff_file("go.sum")

    def test_should_skip_diff_file_test_files(self):
        from app.graph import _should_skip_diff_file

        assert _should_skip_diff_file("tests/test_a.py")
        assert _should_skip_diff_file("src/app.test.ts")
        assert _should_skip_diff_file("src/util.spec.ts")
        assert _should_skip_diff_file("src/foo_test.py")
        assert _should_skip_diff_file("src/bar.test.js")

    def test_should_skip_diff_file_normal_files(self):
        from app.graph import _should_skip_diff_file

        assert not _should_skip_diff_file("src/app.py")
        assert not _should_skip_diff_file("src/util.ts")
        assert not _should_skip_diff_file("README.md")
        assert not _should_skip_diff_file("docker-compose.yml")
        assert not _should_skip_diff_file("Dockerfile")
        assert not _should_skip_diff_file("src/components/Button.tsx")

    def test_split_diff_by_file_empty(self):
        from app.graph import split_diff_by_file

        assert split_diff_by_file("") == {}

    def test_split_diff_by_file_single(self):
        from app.graph import split_diff_by_file

        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+ x = 1"
        result = split_diff_by_file(diff)
        assert result == {"a.py": diff}

    def test_split_diff_by_file_multiple(self):
        from app.graph import split_diff_by_file

        diff = self._make_multifile_diff(3)
        result = split_diff_by_file(diff)
        assert set(result.keys()) == {"f0.py", "f1.py", "f2.py"}


class TestPerFileExecution:
    @pytest.mark.asyncio
    async def test_per_file_routes_security_findings_through_judge(self):
        from app.graph import ReviewGraph
        from app.models.agent import AgentResult, AgentStatus, FindingSchema

        graph = ReviewGraph()

        diff_parts = [
            "diff --git a/f0.py b/f0.py\n--- a/f0.py\n+++ b/f0.py\n@@ -0,0 +1,1 @@\n+ x = 1",
            "diff --git a/f1.py b/f1.py\n--- a/f1.py\n+++ b/f1.py\n@@ -0,0 +1,1 @@\n+ y = 2",
        ]
        diff = "\n".join(diff_parts)

        ctx = {
            "title": "per-file test",
            "description": "",
            "diff": diff,
            "files": ["f0.py", "f1.py"],
            "stats": None,
        }

        call_order = []

        async def mock_agent(file: str, *args, **kwargs):
            call_order.append(file)
            return AgentResult(
                status=AgentStatus.SUCCESS,
                findings=[
                    FindingSchema(
                        file=file,
                        line=1,
                        title="Test finding",
                        description=f"Finding in {file}",
                        severity="WARNING",
                        confidence=0.5,
                        category="quality",
                        evidence=["x = 1"],
                    )
                ],
            )

        file_side_effects = {"f0.py": mock_agent, "f1.py": mock_agent}

        async def side_effect_run(diff, context):
            files = context.get("files", [])
            file = files[0] if files else "unknown"
            return await file_side_effects[file](file, diff, context)

        captured_judge_input: list = []

        async def mock_judge(results, **kwargs):
            captured_judge_input.extend(results)
            return {"findings": [], "merge_recommendation": "APPROVE", "skipped_agents": []}

        with (
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", side_effect_run),
            patch.object(graph.performance_agent, "run", side_effect_run),
            patch.object(graph.quality_agent, "run", side_effect_run),
            patch.object(graph.judge, "run", mock_judge),
        ):
            result = await graph._run_per_file(ctx, "", 0.0)

        assert result["merge_recommendation"] == "APPROVE"
        # Each file → 3 agents → 6 total results
        assert len(captured_judge_input) == 6

    @pytest.mark.asyncio
    async def test_per_file_single_file_failure_does_not_abort(self):
        from app.graph import ReviewGraph
        from app.models.agent import AgentResult, AgentStatus, FindingSchema

        graph = ReviewGraph()

        diff = (
            "diff --git a/f0.py b/f0.py\n--- a/f0.py\n+++ b/f0.py\n@@ -0,0 +1,1 @@\n+ x = 1\n"
            "diff --git a/f1.py b/f1.py\n--- a/f1.py\n+++ b/f1.py\n@@ -0,0 +1,2 @@\n+ y = 2\n+ z = 3\n"
        )
        ctx = {
            "title": "fails on f0",
            "description": "",
            "diff": diff,
            "files": ["f0.py", "f1.py"],
            "stats": None,
        }

        call_count = 0

        async def mock_run(diff_inner, context):
            nonlocal call_count
            files = context.get("files", [])
            file = files[0] if files else "unknown"
            if file == "f0.py":
                call_count += 1
                raise RuntimeError("agent crashed on f0")
            call_count += 1
            return AgentResult(
                status=AgentStatus.SUCCESS,
                findings=[
                    FindingSchema(
                        file=file,
                        line=1,
                        title="OK finding",
                        description="",
                        severity="WARNING",
                        confidence=0.5,
                        category="quality",
                        evidence=["y = 2"],
                    )
                ],
            )

        async def mock_judge(results, **kwargs):
            findings = []
            for r in results:
                if r.status == AgentStatus.SUCCESS:
                    findings.extend(r.findings)
            return {
                "findings": [
                    {"file": f.file, "line": f.line, "title": f.title,
                     "description": f.description, "severity": f.severity,
                     "confidence": f.confidence, "category": f.category,
                     "evidence": f.evidence}
                    for f in findings
                ],
                "merge_recommendation": "COMMENT",
                "skipped_agents": [],
            }

        with (
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
            patch.object(graph.security_agent, "run", mock_run),
            patch.object(graph.performance_agent, "run", mock_run),
            patch.object(graph.quality_agent, "run", mock_run),
            patch.object(graph.judge, "run", mock_judge),
            patch("app.graph.split_diff_by_file") as mock_split,
        ):
            mock_split.return_value = {
                "f0.py": "diff --git a/f0.py b/f0.py\n",
                "f1.py": "diff --git a/f1.py b/f1.py\n",
            }
            result = await graph._run_per_file(ctx, "", 0.0)

        assert result["merge_recommendation"] == "COMMENT"
        # f0 agents fail (3 calls), f1 agents succeed (3 calls) = 6 total
        assert call_count == 6

    @pytest.mark.asyncio
    async def test_per_file_all_fail_falls_back_to_single(self):
        from app.graph import ReviewGraph

        graph = ReviewGraph()

        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ a/a.py\n@@ -0,0 +1,1 @@\n+ x = 1"
        ctx = {
            "title": "all fail",
            "description": "",
            "diff": diff,
            "files": ["a.py"],
            "stats": None,
        }

        with (
            patch.object(graph, "_run_single", AsyncMock(return_value={"mode": "single"})),
            patch.object(graph.security_agent, "run", AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(graph.performance_agent, "run", AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(graph.quality_agent, "run", AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(graph, "_fetch_verification", AsyncMock(return_value={})),
        ):
            result = await graph._run_per_file(ctx, "", 0.0)

        assert result == {"mode": "single"}

    @pytest.mark.asyncio
    async def test_per_file_empty_after_filter_falls_back_to_single(self):
        from app.graph import ReviewGraph

        graph = ReviewGraph()

        diff = "diff --git a/node_modules/pkg.js b/node_modules/pkg.js\n--- a/node_modules/pkg.js\n+++ b/node_modules/pkg.js\n@@ -0,0 +1,1 @@\n+ x = 1"
        ctx = {
            "title": "all skip",
            "description": "",
            "diff": diff,
            "files": ["node_modules/pkg.js"],
            "stats": None,
        }

        with (
            patch.object(graph, "_run_single", AsyncMock(return_value={"mode": "single"})),
        ):
            result = await graph._run_per_file(ctx, "", 0.0)

        assert result == {"mode": "single"}


class TestCallerParameterCheck:
    """Tests for _run_caller_parameter_check (proactive caller-aware bug detection)."""

    @pytest.mark.asyncio
    async def test_detects_none_argument_passed_to_function(self):
        """Should report when a caller passes None to a function that uses it as dict key."""
        from unittest.mock import MagicMock
        from app.graph import ReviewGraph

        graph = ReviewGraph()

        blast_radius = [
            {
                "changed_fn": "app/limiter.py:_rate_limit",
                "callers": [
                    {
                        "file": "app/router.py",
                        "fn": "handle_request",
                        "start_line": 42,
                        "code": "def handle_request(req):\n    _rate_limit(None)  # no key provided\n    return do_work(req)",
                    }
                ],
            }
        ]
        diff = (
            "diff --git a/app/limiter.py b/app/limiter.py\n"
            "--- a/app/limiter.py\n+++ b/app/limiter.py\n"
            "@@ -1,3 +1,6 @@\n"
            "+def _rate_limit(key: str) -> None:\n"
            "+    counters = {}\n"
            "+    counters[key] += 1\n"
        )

        mock_json = (
            '{"issues": [{"caller_file": "app/router.py", "caller_fn": "handle_request", '
            '"line": 43, "arg": "None", "reason": "None used as dict key causes KeyError"}]}'
        )

        with patch("app.services.llm.LLMClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.chat = AsyncMock(return_value=mock_json)
            mock_llm_cls.return_value = mock_llm

            findings = await graph._run_caller_parameter_check(blast_radius, diff)

        assert len(findings) == 1
        assert findings[0].file == "app/router.py"
        assert "_rate_limit" in findings[0].title
        assert findings[0].severity == "WARNING"
        assert findings[0].confidence == 0.75

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_blast_radius(self):
        from app.graph import ReviewGraph
        graph = ReviewGraph()
        findings = await graph._run_caller_parameter_check([], "some diff")
        assert findings == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_diff(self):
        from app.graph import ReviewGraph
        graph = ReviewGraph()
        blast_radius = [{"changed_fn": "app/foo.py:bar", "callers": [{"file": "x.py", "fn": "f", "start_line": 1, "code": "bar(None)"}]}]
        findings = await graph._run_caller_parameter_check(blast_radius, "")
        assert findings == []

    @pytest.mark.asyncio
    async def test_skips_item_without_file_prefix(self):
        """Items without 'file:fn' format should be silently skipped."""
        from app.graph import ReviewGraph
        graph = ReviewGraph()
        blast_radius = [
            {
                "changed_fn": "bare_function_name",  # no file prefix
                "callers": [{"file": "x.py", "fn": "f", "start_line": 1, "code": "bare_function_name(None)"}],
            }
        ]
        diff = "diff --git a/foo.py b/foo.py\n+++ b/foo.py\n+def bare_function_name(): pass\n"
        findings = await graph._run_caller_parameter_check(blast_radius, diff)
        assert findings == []

    @pytest.mark.asyncio
    async def test_no_issue_returns_empty(self):
        """LLM returning empty issues list should produce no findings."""
        from unittest.mock import MagicMock
        from app.graph import ReviewGraph

        graph = ReviewGraph()
        blast_radius = [
            {
                "changed_fn": "app/utils.py:compute",
                "callers": [
                    {"file": "app/main.py", "fn": "run", "start_line": 10, "code": "compute(42)"}
                ],
            }
        ]
        diff = (
            "diff --git a/app/utils.py b/app/utils.py\n"
            "+++ b/app/utils.py\n"
            "+def compute(n: int) -> int:\n"
            "+    return n * 2\n"
        )

        with patch("app.services.llm.LLMClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.chat = AsyncMock(return_value='{"issues": []}')
            mock_llm_cls.return_value = mock_llm

            findings = await graph._run_caller_parameter_check(blast_radius, diff)

        assert findings == []
