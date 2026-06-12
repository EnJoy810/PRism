from app.models.agent import AgentResult, AgentStatus, FindingSchema


def test_finding_schema_minimal():
    f = FindingSchema(
        file="src/auth.ts",
        line=42,
        title="SQL injection",
        description="User input concatenated into query",
        severity="ERROR",
        confidence=0.95,
        category="security",
    )
    assert f.file == "src/auth.ts"
    assert f.line == 42
    assert f.severity == "ERROR"
    assert f.category == "security"
    assert f.diff_snippet is None


def test_finding_schema_full():
    f = FindingSchema(
        file="src/auth.ts",
        line=42,
        title="SQL injection",
        description="User input concatenated into query",
        severity="ERROR",
        confidence=0.95,
        category="security",
        diff_snippet="+  db.query('SELECT * FROM users WHERE id = ' + userId)",
    )
    assert f.diff_snippet is not None
    assert "SELECT" in f.diff_snippet


def test_finding_default_confidence():
    f = FindingSchema(
        file="src/auth.ts",
        line=10,
        title="Test",
        description="Test",
        severity="WARNING",
        confidence=0.8,
        category="performance",
    )
    assert f.confidence == 0.8


def test_agent_result_success():
    finding = FindingSchema(
        file="src/auth.ts",
        line=42,
        title="SQL injection",
        description="desc",
        severity="ERROR",
        confidence=0.95,
        category="security",
    )
    result = AgentResult(status=AgentStatus.SUCCESS, findings=[finding])
    assert result.status == AgentStatus.SUCCESS
    assert len(result.findings) == 1
    assert result.findings[0].title == "SQL injection"


def test_agent_result_empty_findings():
    result = AgentResult(status=AgentStatus.SUCCESS, findings=[])
    assert len(result.findings) == 0


def test_agent_result_timeout():
    result = AgentResult(status=AgentStatus.TIMEOUT, findings=[])
    assert result.status == AgentStatus.TIMEOUT


def test_agent_result_format_error():
    result = AgentResult(status=AgentStatus.FORMAT_ERROR, findings=[])
    assert result.status == AgentStatus.FORMAT_ERROR


def test_agent_status_values():
    assert AgentStatus.SUCCESS.value == "success"
    assert AgentStatus.TIMEOUT.value == "timeout"
    assert AgentStatus.FORMAT_ERROR.value == "format_error"
