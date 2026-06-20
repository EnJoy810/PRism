from app.agents.judge import JudgeAgent, _guess_category
from app.models.agent import AgentResult, AgentStatus, FindingSchema


def _finding(
    file: str,
    line: int | None,
    title: str,
    severity: str = "WARNING",
    confidence: float = 0.9,
    category: str = "security",
    evidence: list[str] | None = None,
    impact_type: str | None = "runtime_error",
    impact_statement: str | None = "deterministic failure",
    description: str | None = None,
) -> FindingSchema:
    return FindingSchema(
        file=file,
        line=line,
        title=title,
        description=description or f"desc for {title}",
        severity=severity,
        confidence=confidence,
        category=category,
        evidence=evidence or [f"{file}:{line}"],
        impact_type=impact_type,
        impact_statement=impact_statement,
    )


class TestDedup:
    def test_duplicate_removed(self):
        f1 = _finding("a.ts", 10, "Bug", "ERROR")
        f2 = _finding("a.ts", 10, "Bug", "WARNING")
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2])
        assert len(merged) == 1
        assert merged[0].severity == "ERROR"

    def test_no_dedup_different_files(self):
        f1 = _finding("a.ts", 10, "Bug")
        f2 = _finding("b.ts", 10, "Bug")
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2])
        assert len(merged) == 2

    def test_no_dedup_different_titles(self):
        f1 = _finding("a.ts", 10, "Bug A")
        f2 = _finding("a.ts", 10, "Bug B")
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2])
        assert len(merged) == 2

    def test_no_dedup_different_lines(self):
        f1 = _finding("a.ts", 10, "Bug")
        f2 = _finding("a.ts", 20, "Bug")
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2])
        assert len(merged) == 2

    def test_same_line_different_title_not_deduped(self):
        f1 = _finding("a.ts", 10, "Memory leak")
        f2 = _finding("a.ts", 10, "Unused variable")
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2])
        assert len(merged) == 2

    def test_multiple_duplicates(self):
        f1 = _finding("a.ts", 10, "Bug", "ERROR", 0.95)
        f2 = _finding("a.ts", 10, "Bug", "WARNING", 0.8)
        f3 = _finding("a.ts", 10, "Bug", "INFO", 0.6)
        judge = JudgeAgent(api_key="sk-test")
        merged = judge.dedup([f1, f2, f3])
        assert len(merged) == 1
        assert merged[0].confidence == 0.95


class TestNoiseReduction:
    def test_low_confidence_discarded(self):
        f = _finding("a.ts", 10, "Low confidence", "ERROR", 0.3)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []  # discarded

    def test_high_confidence_kept(self):
        f = _finding("a.ts", 10, "Good finding", "ERROR", 0.9)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result[0].severity == "ERROR"

    def test_very_low_confidence_discarded(self):
        f = _finding("a.ts", 10, "Very low", "ERROR", 0.15)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_warning_discarded(self):
        f = _finding("a.ts", 10, "Low warning", "WARNING", 0.3)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_custom_threshold(self):
        f = _finding("a.ts", 10, "Borderline", "ERROR", 0.7)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.8)
        assert result == []  # 0.7 < 0.8, discarded

    def test_empty_findings(self):
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([], min_confidence=0.6)
        assert result == []


class TestImpactGate:
    def test_style_only_discarded_even_when_warning_high_confidence(self):
        f = _finding("a.ts", 10, "Naming style", "WARNING", 0.95, "quality", impact_type="style_only")
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_info_only_discarded_even_when_error(self):
        f = _finding("a.ts", 10, "Doc suggestion", "ERROR", 0.95, "quality", impact_type="info_only")
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_actionable_impact_types_are_kept(self):
        findings = [
            _finding("a.ts", 10, "Type check fails", "WARNING", 0.9, "quality", impact_type="type_check_failure"),
            _finding("b.ts", 20, "API break", "WARNING", 0.9, "quality", impact_type="api_breakage"),
            _finding("c.ts", 30, "Runtime bug", "WARNING", 0.9, "quality", impact_type="runtime_error"),
        ]
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise(findings, min_confidence=0.6)
        assert result == findings

    def test_actionable_impact_type_kept_despite_style_words(self):
        f = _finding(
            "a.ts",
            10,
            "Type annotation style breaks mypy",
            "WARNING",
            0.9,
            "quality",
            impact_type="type_check_failure",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == [f]

    def test_actionable_impact_requires_impact_statement(self):
        f = _finding(
            "a.ts",
            10,
            "Runtime bug",
            "WARNING",
            0.9,
            "quality",
            impact_type="runtime_error",
            impact_statement="",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_missing_impact_type_uses_legacy_noise_filter(self):
        f = _finding("a.ts", 10, "Runtime bug", "WARNING", 0.9, "quality", impact_type=None)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == [f]

    def test_frontend_idor_from_client_param_discarded_without_backend_evidence(self):
        f = _finding(
            "src/feature/homework/hooks/useCommonReplaceModal.ts",
            149,
            "缺少对 recommend_id 的权限校验（IDOR）",
            "WARNING",
            0.95,
            "security",
            impact_type="security_risk",
            impact_statement="攻击者可通过修改前端状态或直接发送 API 请求，在其他用户的题单中添加题目。",
            description="handleAppendCommonQuestion 直接使用推荐 ID 调用后端新增接口，未验证当前用户是否拥有该推荐的操作权限。",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_frontend_ssrf_from_url_param_discarded_without_server_sink(self):
        f = _finding(
            "src/pages/trace/TracePage.tsx",
            36,
            "未经验证的URL参数直接用于客户端导航",
            "WARNING",
            0.9,
            "security",
            impact_type="security_risk",
            impact_statement="攻击者可以构造包含特殊字符的 exam_id/grading_id 参数，可能导致服务器端请求伪造。",
            description="从 URL 查询参数中直接获取 exam_id 和 grading_id，并用于客户端导航。",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_frontend_xss_finding_kept(self):
        f = _finding(
            "src/components/Preview.tsx",
            20,
            "XSS via dangerouslySetInnerHTML",
            "ERROR",
            0.95,
            "security",
            impact_type="security_risk",
            impact_statement="Attacker-controlled script can execute in the browser.",
            description="User-controlled HTML is rendered with dangerouslySetInnerHTML.",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == [f]

    def test_backend_auth_finding_kept(self):
        f = _finding(
            "backend/app/routers/users.py",
            42,
            "Authorization check missing",
            "ERROR",
            0.95,
            "security",
            impact_type="security_risk",
            impact_statement="Authenticated users can query another user's database record.",
            description="API route handler uses user_id without permission check before database query.",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == [f]

    def test_performance_warning_micro_optimization_discarded_without_hard_evidence(self):
        f = _finding(
            "src/components/Button.tsx",
            18,
            "Memoize inline handler",
            "WARNING",
            0.9,
            "performance",
            impact_type="performance_regression",
            impact_statement="May be slightly slower.",
            description="useCallback could avoid unnecessary re-render and make this slightly faster.",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_performance_warning_numeric_estimate_is_not_hard_evidence(self):
        f = _finding(
            "src/feature/design-exam/panel/SectionOutlineSidebar.tsx",
            271,
            "editingTitle 引用变化导致所有列表项不必要的重新渲染",
            "WARNING",
            0.95,
            "performance",
            impact_type="performance_regression",
            impact_statement="若列表项为 50 个，每次键盘输入会触发约 50 次子组件重新渲染，可能导致输入响应延迟增加 30~50ms。",
            description="ExpandedSortableItem 组件使用了 React.memo，但父组件中 editingTitle 状态变化会导致不必要的重新渲染。",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == []

    def test_performance_warning_kept_with_hard_evidence(self):
        f = _finding(
            "backend/app/services/orders.py",
            88,
            "N+1 database query",
            "WARNING",
            0.9,
            "performance",
            impact_type="performance_regression",
            impact_statement="1000 rows produce 1000 SQL queries and increase p95 latency.",
            description="Loop issues one database query per row; 1000 rows produce 1000 SQL queries.",
        )
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result == [f]

    async def test_verified_existing_package_discards_missing_dependency_finding(self):
        f = _finding(
            "src/App.tsx",
            1,
            "Missing dependency lucide-react",
            "ERROR",
            0.95,
            "quality",
            evidence=["import { Search } from 'lucide-react'"],
            impact_type="runtime_error",
            impact_statement="Build fails because lucide-react is not installed.",
            description="The new import references lucide-react, but the package is not declared.",
        )
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[f])
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

        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run(
            [r],
            diff="+import { Search } from 'lucide-react'",
            verification=verification,
        )

        assert result["findings"] == []

    async def test_verified_missing_package_keeps_missing_dependency_finding(self):
        f = _finding(
            "src/App.tsx",
            1,
            "Missing dependency lucide-react",
            "ERROR",
            0.95,
            "quality",
            evidence=["import { Search } from 'lucide-react'"],
            impact_type="runtime_error",
            impact_statement="Build fails because lucide-react is not installed.",
            description="The new import references lucide-react, but the package is not declared.",
        )
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[f])
        verification = {
            "imports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "lucide-react",
                    "status": "fail",
                    "detail": "lucide-react not declared in package.json",
                }
            ]
        }

        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run(
            [r],
            diff="+import { Search } from 'lucide-react'",
            verification=verification,
        )

        assert len(result["findings"]) == 1

    async def test_verified_existing_export_discards_missing_export_finding(self):
        f = _finding(
            "src/App.tsx",
            1,
            "MarketingNavbar is not exported",
            "ERROR",
            0.95,
            "quality",
            evidence=["import { MarketingNavbar } from './components'"],
            impact_type="runtime_error",
            impact_statement="Build fails because MarketingNavbar is not exported.",
            description="The import references MarketingNavbar, but ./components does not export it.",
        )
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[f])
        verification = {
            "exports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "./components",
                    "symbol": "MarketingNavbar",
                    "status": "pass",
                    "detail": "named export found",
                }
            ]
        }

        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run(
            [r],
            diff="+import { MarketingNavbar } from './components'",
            verification=verification,
        )

        assert result["findings"] == []

    async def test_verified_missing_export_keeps_missing_export_finding(self):
        f = _finding(
            "src/App.tsx",
            1,
            "MarketingNavbar is not exported",
            "ERROR",
            0.95,
            "quality",
            evidence=["import { MarketingNavbar } from './components'"],
            impact_type="runtime_error",
            impact_statement="Build fails because MarketingNavbar is not exported.",
            description="The import references MarketingNavbar, but ./components does not export it.",
        )
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[f])
        verification = {
            "exports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "./components",
                    "symbol": "MarketingNavbar",
                    "status": "fail",
                    "detail": "MarketingNavbar is not exported by src/components/index.ts",
                }
            ]
        }

        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run(
            [r],
            diff="+import { MarketingNavbar } from './components'",
            verification=verification,
        )

        assert len(result["findings"]) == 1

    async def test_verified_existing_export_does_not_discard_behavior_finding(self):
        f = _finding(
            "src/App.tsx",
            1,
            "MarketingNavbar missing required prop",
            "ERROR",
            0.95,
            "quality",
            evidence=["import { MarketingNavbar } from './components'"],
            impact_type="runtime_error",
            impact_statement="Rendering fails because required props are omitted.",
            description="MarketingNavbar exists, but this call site omits a required prop.",
        )
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[f])
        verification = {
            "exports": [
                {
                    "file": "src/App.tsx",
                    "line": 1,
                    "module": "./components",
                    "symbol": "MarketingNavbar",
                    "status": "pass",
                    "detail": "named export found",
                }
            ]
        }

        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run(
            [r],
            diff="+import { MarketingNavbar } from './components'",
            verification=verification,
        )

        assert len(result["findings"]) == 1


class TestMergeRecommendation:
    def test_approve_no_issues(self):
        judge = JudgeAgent(api_key="sk-test")
        decision = judge.decide_merge([])
        assert decision == "APPROVE"

    def test_request_changes_on_error(self):
        f = _finding("a.ts", 10, "Critical bug", "ERROR")
        judge = JudgeAgent(api_key="sk-test")
        decision = judge.decide_merge([f])
        assert decision == "REQUEST_CHANGES"

    def test_comment_on_warning(self):
        f = _finding("a.ts", 10, "Minor issue", "WARNING")
        judge = JudgeAgent(api_key="sk-test")
        decision = judge.decide_merge([f])
        assert decision == "COMMENT"

    def test_approve_on_info_only(self):
        f = _finding("a.ts", 10, "Style", "INFO")
        judge = JudgeAgent(api_key="sk-test")
        decision = judge.decide_merge([f])
        assert decision == "APPROVE"

    def test_error_overrides_warning(self):
        f1 = _finding("a.ts", 10, "Critical", "ERROR")
        f2 = _finding("b.ts", 20, "Small", "WARNING")
        judge = JudgeAgent(api_key="sk-test")
        decision = judge.decide_merge([f1, f2])
        assert decision == "REQUEST_CHANGES"


class TestReclassification:
    def test_performance_keyword_reclassifies(self):
        f = _finding("a.ts", 10, "Slow query detected", severity="WARNING", category="security")
        judge = JudgeAgent(api_key="sk-test")
        result = judge._reclassify([f])
        assert result[0].category == "performance"

    def test_security_keyword_reclassifies(self):
        f = _finding("a.ts", 10, "SQL injection risk", severity="ERROR", category="quality")
        judge = JudgeAgent(api_key="sk-test")
        result = judge._reclassify([f])
        assert result[0].category == "security"

    def test_no_reclassify_if_no_keyword_match(self):
        f = _finding("a.ts", 10, "Generic issue", severity="INFO", category="quality")
        judge = JudgeAgent(api_key="sk-test")
        result = judge._reclassify([f])
        assert result[0].category == "quality"

    def test_no_keyword_no_match(self):
        guessed = _guess_category("random", "no keywords here", "security")
        assert guessed is None

    def test_guess_category_returns_none_on_same_category(self):
        guessed = _guess_category("memory leak in loop", "slow performance", "performance")
        assert guessed is None  # already in performance, no change


class TestSkippedAgents:
    async def test_all_success_no_skipped(self):
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[_finding("a.ts", 1, "X")])
        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run([r])
        assert result["skipped_agents"] == []

    async def test_failed_agent_is_skipped(self):
        r1 = AgentResult(status=AgentStatus.SUCCESS, findings=[_finding("a.ts", 1, "X")])
        r2 = AgentResult(status=AgentStatus.TIMEOUT, findings=[])
        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run([r1, r2])
        assert "agent_1" in result["skipped_agents"]

    async def test_all_failed_all_skipped(self):
        r1 = AgentResult(status=AgentStatus.FORMAT_ERROR, findings=[])
        r2 = AgentResult(status=AgentStatus.TIMEOUT, findings=[])
        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run([r1, r2])
        assert len(result["skipped_agents"]) == 2

    async def test_skipped_findings_not_in_result(self):
        r = AgentResult(status=AgentStatus.FORMAT_ERROR, findings=[_finding("a.ts", 1, "Should not appear")])
        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run([r])
        assert len(result["findings"]) == 0

    async def test_returns_judge_verdict_dump(self):
        r = AgentResult(status=AgentStatus.SUCCESS, findings=[_finding("a.ts", 1, "X")])
        judge = JudgeAgent(api_key="sk-test")
        result = await judge.run([r])
        assert "findings" in result
        assert "merge_recommendation" in result
        assert "skipped_agents" in result
