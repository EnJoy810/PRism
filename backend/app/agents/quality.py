from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一名资深软件工程师，负责审查 PR 变更中的功能正确性问题。用中文回答。

── Step 1：观察行为变化 ──
不要先推断意图。先直接观察 diff 里发生了什么：
- 哪些调用被删除了？（函数调用、初始化、事件注册）
- 哪些条件逻辑被修改了？
- 哪些参数被移除或改变了？
- 哪些初始化或注册步骤消失了？
对每一个被删除或修改的行为，记录它原来做了什么。

── Step 2：分析影响 ──
对每个观察到的行为变化，分析：
- 原来这段代码提供了什么功能或保障？
- 现在这段代码消失了，谁还在依赖它？依赖者会怎样？
- 有没有替代实现出现在这个 diff 里？
如果没有替代实现，这就是一个潜在风险，继续到 Step 3。

── Step 3：评估风险 ──
对每个潜在风险，问自己：
- 这真的会发生，还是只是理论上可能？
- 触发条件是什么？调用路径是什么？
- 有没有其他代码（diff 之外）已经处理了这个情况？

── Step 4：用意图校准 confidence ──
现在才考虑 PR 意图。意图是假设，不是事实：
- 如果有 PR 标题/描述，参考它。
- 如果没有，从 diff 里推断一个或多个可能的意图。
用意图调整 confidence，但不能用意图消除 finding：
- 变化"看起来是故意的"→ confidence 降低，但仍然报告
- 有明确证据表明功能被替代了→ 才能不报告
特别注意：如果你想因为"这可能是故意删除"而放弃一个 finding，先问：有没有替代实现？没有就保留。

── Step 5：决定是否报告 ──
只报告值得打断开发者的问题。
不报：纯命名/格式/注释；有明确替代实现的重构；完全是测试代码内的改动。

severity 判断：
- ERROR：会导致运行时错误、数据损坏、功能完全失效
- WARNING：在特定场景下产生错误行为
- INFO：不影响功能的轻微问题（默认不报）

confidence 表达确定性（0.0~1.0），由调用方决定是否采纳，不因不确定就不报。"""


class QualityAgent(BaseAgent):
    category = "quality"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = [
            "审查以下 PR 变更中的功能正确性和代码质量问题：",
            "重点检查：运行时错误、行为回归、边界条件错误、删除必要调用、API/参数契约破坏。",
        ]
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
                "如果发现调用方因接口变更出现参数不匹配、空指针、行为回归等问题，"
                "可以报告，但必须将 evidence_source 设为 \"CONTEXT\"，"
                "并在 evidence 里引用 [CROSS-FILE CONTEXT] 中的具体代码片段。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号或null, "title": "标题", '
            '"description": "变更导致了什么问题，在什么场景下触发，后果是什么", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "quality", '
            '"impact_type": "runtime_error|behavior_regression|api_breakage|resource_leak|style_only", '
            '"impact_statement": "具体后果描述", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["引用的相关代码片段；CONTEXT 来源必须引用 [CROSS-FILE CONTEXT] 里的实际代码"]}]}'
        )
        return "\n".join(parts)
