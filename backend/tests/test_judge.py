from app.agents.judge import JudgeAgent, _guess_category
from app.models.agent import AgentResult, AgentStatus, FindingSchema, JudgeVerdict


def _finding(
    file: str,
    line: int | None,
    title: str,
    severity: str = "WARNING",
    confidence: float = 0.9,
    category: str = "security",
) -> FindingSchema:
    return FindingSchema(
        file=file,
        line=line,
        title=title,
        description=f"desc for {title}",
        severity=severity,
        confidence=confidence,
        category=category,
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
    def test_low_confidence_downgraded(self):
        f = _finding("a.ts", 10, "Low confidence", "ERROR", 0.3)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result[0].severity == "WARNING"  # ERROR → downgraded

    def test_high_confidence_unchanged(self):
        f = _finding("a.ts", 10, "Good finding", "ERROR", 0.9)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result[0].severity == "ERROR"

    def test_very_low_confidence_downgraded_once(self):
        f = _finding("a.ts", 10, "Very low", "ERROR", 0.15)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result[0].severity == "WARNING"

    def test_warning_downgraded(self):
        f = _finding("a.ts", 10, "Low warning", "WARNING", 0.3)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.6)
        assert result[0].severity == "INFO"

    def test_custom_threshold(self):
        f = _finding("a.ts", 10, "Borderline", "ERROR", 0.7)
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([f], min_confidence=0.8)
        assert result[0].severity == "WARNING"  # 0.7 < 0.8, downgraded

    def test_empty_findings(self):
        judge = JudgeAgent(api_key="sk-test")
        result = judge.reduce_noise([], min_confidence=0.6)
        assert result == []


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
