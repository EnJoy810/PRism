from app.agents.base import BaseAgent
from app.models.agent import AgentResult

SYSTEM_PROMPT = """你是一位关注代码可维护性的资深工程师。用中文回答。

严重级别：
- ERROR: 新增代码会导致明确运行时错误、兼容性破坏、错误状态流转或不可恢复的数据/行为错误
- WARNING: 新增代码存在可验证后果，例如类型检查/CI 失败、调用方会被破坏、异常会被吞掉、资源生命周期错误、
  职责边界错误导致后续变更高概率出错
- INFO: 只改善可读性、一致性、命名、格式、注释、测试函数返回注解、轻微类型标注完整性的建议

规则：
- 只关注可维护性和代码质量，忽略安全和性能
- 默认不要上报 INFO；INFO 级别问题应返回空 findings
- 命名、标签名、格式、一致性、缺少 -> None、注释位置、轻微类型标注优化不得标为 WARNING
- WARNING/ERROR 必须说明具体可复现后果：哪个调用方、哪类输入、哪个检查或哪条执行路径会失败
- 每次指出问题给出重构方向
- 如果代码质量良好，直接返回空 findings"""


class QualityAgent(BaseAgent):
    category = "quality"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["审查以下 PR 变更中的代码质量问题："]
        if pr_title:
            parts.append(f"标题：{pr_title}")
        if pr_description:
            parts.append(f"描述：{pr_description[:500]}")
        if files:
            parts.append(f"变更文件：{', '.join(files[:20])}")
        if symbol_defs:
            def_lines = ["\n引用符号定义："]
            for sym, defn in list(symbol_defs.items())[:5]:
                def_lines.append(f"\n--- {sym} ---\n{defn}")
            parts.append("".join(def_lines))
        blast_section = ctx.get("blast_radius_section", "")
        if blast_section:
            parts.append(blast_section)
            parts.append(
                "\n---\n注意：[CROSS-FILE CONTEXT] 部分是调用了被改函数的其他文件代码，"
                "仅供判断影响范围，不要对这部分代码报问题。只报 [DIFF] 里新增行（+号开头）引入的问题。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号, "title": "标题", '
            '"description": "描述", "severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "quality", '
            '"impact_type": "runtime_error|type_check_failure|api_breakage|behavior_regression|style_only|info_only", '
            '"impact_statement": "具体运行时/类型检查/API/行为后果", '
            '"evidence": ["diff 中原文代码片段，直接复制 + 号开头的行内容"]}]}\n'
            "规则：evidence 必须是 diff 新增行（+号开头）的原文内容，直接复制粘贴，不加行号前缀；"
            "impact_type 必须描述实际后果；命名、格式、一致性、注释、轻微类型标注建议用 style_only 或 info_only；"
            "impact_statement 必须是可验证后果，不能只写可能/也许；"
            "如果无法提供 diff 中真实存在的代码片段作为证据，该问题不得上报"
        )
        return "\n".join(parts)

    async def run(self, diff: str, context: dict | None = None) -> AgentResult:
        result = await super().run(diff, context)
        sast = (context or {}).get("sast_findings", {}).get("quality", [])
        if sast:
            from app.models.agent import FindingSchema
            sast_findings = [FindingSchema(**f) for f in sast]
            result.findings.extend(sast_findings)
        return result
