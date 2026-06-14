from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一位专注于性能优化的资深工程师。用中文回答。

严重级别：
- ERROR: N+1 查询、内存泄漏、死锁、大对象重复创建、同步阻塞 IO
- WARNING: 不必要的循环、缓存缺失、懒加载缺失、批量操作可优化

规则：
- 只关注性能相关的问题，忽略安全和风格
- 提供数据量级估算（如：1000 次请求时，这个循环会…）
- 如果未发现性能问题，直接返回空 findings"""


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
                "\n---\n注意：[CROSS-FILE CONTEXT] 部分是调用了被改函数的其他文件代码，"
                "仅供判断影响范围，不要对这部分代码报问题。只报 [DIFF] 里新增行（+号开头）引入的问题。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号, "title": "标题", '
            '"description": "描述", "severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "performance", '
            '"evidence": ["diff 中原文代码片段，直接复制 + 号开头的行内容"]}]}\n'
            "规则：evidence 必须是 diff 新增行（+号开头）的原文内容，直接复制粘贴，不加行号前缀；"
            "如果无法提供 diff 中真实存在的代码片段作为证据，该问题不得上报"
        )
        return "\n".join(parts)
