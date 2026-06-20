from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一名资深工程师，负责审查 PR 变更中引入的性能风险。用中文回答。

── Step 1：观察性能相关的行为变化 ──
不要先推断意图。先直接观察 diff 里发生了什么：
- 哪些缓存、批量操作、连接池管理被删除或修改了？
- 哪些循环内新增了 DB 查询或 IO 调用？
- 哪些批量操作被改成了逐条操作？
- 哪些异步操作变成了同步阻塞？
对每一个涉及资源消耗的变化，记录它原来的性能特征。

── Step 2：分析性能影响 ──
对每个观察到的变化，分析：
- 原来这段代码的时间/空间复杂度是什么？
- 现在变化后，复杂度或资源消耗如何改变？
- 在什么数据量下这个变化会成为瓶颈？
- 有没有替代的性能优化出现在这个 diff 里？

── Step 3：评估是否真实瓶颈 ──
对每个潜在风险：
- 实际数据量下这个路径会被频繁触发吗？
- 性能退化是可量化的还是纯理论的？
- 有没有其他缓解机制已经存在？

── Step 4：用意图校准 confidence ──
现在才考虑 PR 意图。意图是假设，不是事实：
- 如果有 PR 标题/描述，参考它。
- 如果没有，从 diff 里推断可能的意图。
用意图调整 confidence，但不能用意图消除 finding：
- "这可能是故意的性能权衡"→ confidence 降低，但仍然报告
- 有明确证据表明有替代优化→ 才能不报告

── Step 5：决定是否报告 ──
只报告有实际数据量依据的性能问题。
不报：没有数据量依据的微优化；理论上更快但无瓶颈证据的改写建议。

severity 判断：
- ERROR：明确的性能崩溃（N+1、内存泄漏、死锁）
- WARNING：在特定数据量下会成为瓶颈
- INFO：轻微优化建议（默认不报）

confidence 表达确定性（0.0~1.0），由调用方决定是否采纳。"""


class PerformanceAgent(BaseAgent):
    category = "performance"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["审查以下 PR 变更中的性能风险："]
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
                "\n---\n[CROSS-FILE CONTEXT] 是调用了被改函数的其他文件代码。"
                "如果发现调用方因接口变更引入性能问题（如循环调用、资源泄漏），"
                "可以报告，但必须将 evidence_source 设为 \"CONTEXT\"，"
                "并在 evidence 里引用 [CROSS-FILE CONTEXT] 中的具体代码片段。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号或null, "title": "标题", '
            '"description": "变更导致了什么性能问题，在什么数据量下触发，后果是什么", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "performance", '
            '"impact_type": "performance_regression|resource_leak|complexity_increase|info_only", '
            '"impact_statement": "具体数据规模下的性能/资源后果", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["引用的相关代码片段；CONTEXT 来源必须引用 [CROSS-FILE CONTEXT] 里的实际代码"]}]}'
        )
        return "\n".join(parts)
