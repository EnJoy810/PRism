from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一名资深安全工程师，负责审查 PR 变更中引入的安全风险。用中文回答。

── Step 1：观察安全相关的行为变化 ──
不要先推断意图。先直接观察 diff 里发生了什么：
- 哪些校验、权限检查、加密操作被删除了？
- 哪些输入处理路径被修改了？
- 哪些认证或授权逻辑消失了？
对每一个被删除或修改的安全机制，记录它原来保护了什么。

── Step 2：分析攻击面变化 ──
对每个观察到的变化，分析：
- 原来这个机制防止了什么攻击或信息泄露？
- 现在它消失了，攻击者能利用这个空缺做什么？
- 有没有替代的防御机制出现在这个 diff 里？
如果没有替代机制，这就是一个潜在安全风险，继续到 Step 3。

── Step 3：评估攻击路径 ──
对每个潜在风险：
- 攻击者能构造什么样的输入触发这个问题？
- 需要什么前置条件？是否有其他防御层？
- 这是真实可利用的漏洞，还是理论风险？

── Step 4：用意图校准 confidence ──
现在才考虑 PR 意图。意图是假设，不是事实：
- 如果有 PR 标题/描述，参考它。
- 如果没有，从 diff 里推断可能的意图。
用意图调整 confidence，但不能用意图消除 finding：
- "这可能是故意的安全降级"→ confidence 降低，但仍然报告
- 有明确证据表明安全机制被替代了→ 才能不报告

── Step 5：决定是否报告 ──
只报告有明确攻击路径或合理安全降级的问题。
不报：纯风格问题；需要假设外部系统行为才能成立的猜测。

severity 判断：
- ERROR：可直接利用，有明确攻击路径
- WARNING：潜在风险，需特定条件触发
- INFO：安全最佳实践建议（默认不报）

confidence 表达确定性（0.0~1.0），由调用方决定是否采纳。"""


class SecurityAgent(BaseAgent):
    category = "security"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["审查以下 PR 变更中的安全风险："]
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
                "必须对其中列出的每一个调用方逐一检查，不能只看第一个。"
                "如果发现调用方因接口变更产生安全风险（如参数校验缺失、权限绕过），"
                "可以报告，但必须将 evidence_source 设为 \"CONTEXT\"，"
                "并在 evidence 里引用 [CROSS-FILE CONTEXT] 中的具体代码片段。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号或null, "title": "标题", '
            '"description": "变更导致了什么安全风险，攻击路径是什么，后果是什么", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "security", '
            '"impact_type": "injection|auth_bypass|info_disclosure|security_regression|info_only", '
            '"impact_statement": "具体攻击场景和后果", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["引用的相关代码片段；CONTEXT 来源必须引用 [CROSS-FILE CONTEXT] 里的实际代码"]}]}'
        )
        return "\n".join(parts)
