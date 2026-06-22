import json
import logging
import os
import re

import stamina
from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from app.config import load_config
from app.models.review import (
    MergeRecommendation,
    ReviewIssue,
    ReviewResult,
    RiskArea,
    Severity,
    WalkthroughEntry,
)

try:
    from langsmith.wrappers import wrap_openai
except ImportError:
    wrap_openai = None

logger = logging.getLogger(__name__)

_UNSET = object()

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"




class BudgetExceededError(Exception):
    pass


class _SkipRetry(Exception):
    def __init__(self, original: Exception):
        self.original = original


class TokenBudget:
    def __init__(self, max_tokens_per_call: int = 4096):
        self.max_tokens_per_call = max_tokens_per_call
        self.total_tokens = 0
        self.call_count = 0

    @property
    def exceeded(self) -> bool:
        return False

    def would_exceed_call(self, estimated_tokens: int) -> bool:
        return estimated_tokens > self.max_tokens_per_call

    def record(self, tokens: int) -> None:
        self.total_tokens += tokens
        self.call_count += 1

    def reset(self) -> None:
        self.total_tokens = 0
        self.call_count = 0


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        budget: TokenBudget | None | object = _UNSET,
    ):
        cfg = load_config()
        resolved_model = model or cfg.llm.model or MODEL
        resolved_base = base_url or cfg.llm.base_url or BASE_URL
        resolved_key = (
            api_key
            or cfg.llm.api_key
            or cfg.deepseek_api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or "sk-placeholder"
        )
        raw_client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_base,
            max_retries=0,
        )
        if wrap_openai is not None:
            self.client = wrap_openai(raw_client)
        else:
            self.client = raw_client
        self.model = resolved_model
        if budget is _UNSET:
            self.budget = TokenBudget(max_tokens_per_call=cfg.review.budget.max_tokens_per_call)
        else:
            self.budget = budget
        self.total_tokens = 0

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        top_p: float = 1.0,
        stream: bool = False,
        estimated_tokens: int | None = None,
    ) -> str:
        if estimated_tokens is None:
            estimated_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4

        if self.budget is not None:
            if self.budget.would_exceed_call(estimated_tokens):
                raise BudgetExceededError(
                    f"Budget exceeded: {estimated_tokens} > "
                    f"{self.budget.max_tokens_per_call}"
                )

        create_kwargs: dict = dict(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            stream=stream,
        )
        if max_tokens is not None:
            create_kwargs["max_tokens"] = max_tokens

        if stream:
            response = await self.client.chat.completions.create(**create_kwargs)
            return await self._handle_stream(response)

        try:
            content = await self._call_llm(create_kwargs)
            return content
        except _SkipRetry as e:
            raise e.original  # type: ignore[misc]

    @stamina.retry(
        on=(RateLimitError, APIStatusError, APITimeoutError, ValueError),
        attempts=5,
        timeout=45.0,
    )
    async def _call_llm(self, create_kwargs: dict) -> str:
        try:
            response = await self.client.chat.completions.create(**create_kwargs)
        except APIStatusError as e:
            if e.status_code is not None and 400 <= e.status_code < 500 and e.status_code != 429:
                raise _SkipRetry(e) from e
            raise
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("empty response")
        self._track_usage(response)
        return content

    def _track_usage(self, response) -> None:
        if usage := getattr(response, "usage", None):
            tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
            self.total_tokens += tokens
            if self.budget is not None:
                self.budget.record(tokens)

    async def _handle_stream(self, response) -> str:
        full = ""
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full += delta
            if usage := getattr(chunk, "usage", None):
                tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
                self.total_tokens += tokens
                if self.budget is not None:
                    self.budget.record(tokens)
        return full

SYSTEM_PROMPT = """你是一位资深软件工程师，正在做代码审查。找出真正的缺陷，而不是风格问题。
用中文回答。

严重级别（必须严格遵守）：
- ERROR: 代码中存在违背 PR 意图的 bug；或 PR 描述中完全未提及的破坏性副作用；或安全漏洞、数据丢失风险
- WARNING: PR 描述中已说明的行为变更、但缺乏验证证据；性能问题；缺少错误处理
- INFO: 微小改进、文档建议（仅当显式请求时）

核心判断原则：
1. 【先从 diff 推断意图，再用 PR 描述交叉验证】从代码本身得出结论，而不是把 PR 描述当答案往代码上套
2. PR 描述中已明确说明的预期变更，即使影响面广，最高只能报 WARNING（缺乏验证证据），不能报 ERROR
3. 区分"这个变更本身有 bug"和"这个变更依赖下游适配"——后者是 WARNING 不是 ERROR
4. 每个问题必须有具体触发场景（什么输入/条件 → 什么后果），没有触发场景不得上报
5. 提供可执行的具体建议，不写"需要验证""建议检查"等空话
6. 如果 diff 实现了意图且没有明显缺陷，直接说无问题，不要为了显示工作量凑问题
7. 除非显式请求，不报 INFO"""

SECURITY_PROMPT = """你是一位专注于安全审计的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: SQL 注入、XSS、CSRF、敏感信息泄露、认证授权缺陷、命令注入
- WARNING: 输入验证不足、HTTPS 缺失、权限控制不严、不安全随机数
- INFO: 安全最佳实践建议（仅当显式请求时）

规则：
1. 只关注安全相关的问题，忽略风格和性能
2. 每个问题提供具体的攻击场景和修复方法
3. 如果未发现安全问题，直接说：本次变更未发现安全风险"""

PERFORMANCE_PROMPT = """你是一位专注于性能优化的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: N+1 查询、内存泄漏、死锁、大对象重复创建、同步阻塞 IO
- WARNING: 不必要的循环、缓存缺失、懒加载缺失、批量操作可优化
- INFO: 微小性能改进建议（仅当显式请求时）

规则：
1. 只关注性能相关的问题，忽略安全和风格
2. 提供数据量级估算（如：1000 次请求时，这个循环会…）
3. 如果未发现性能问题，直接说：本次变更未发现性能风险"""

MAINTAINABILITY_PROMPT = """你是一位关注代码可维护性的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: 明显的设计缺陷、职责边界混乱、状态管理不一致
- WARNING: 重复代码、过长函数、命名混乱、缺少类型约束、过度耦合
- INFO: 代码组织建议、TS 类型优化、注释位置（仅当显式请求时）

规则：
1. 只关注可维护性和代码质量，忽略安全和性能
2. 每次指出问题给出重构方向（如：建议抽离为独立函数）
3. 如果代码质量良好，直接说：本次变更代码质量良好"""

PERSPECTIVE_MAP = {
    "default": SYSTEM_PROMPT,
    "security": SECURITY_PROMPT,
    "performance": PERFORMANCE_PROMPT,
    "maintainability": MAINTAINABILITY_PROMPT,
}

JUDGE_SYSTEM_PROMPT = """你是一个挑剔的代码审查质量控制员。
你的职责是反驳那些可能是误报的问题，只保留真正有价值的发现。

对每个问题，你要判断：
- CONFIRM：问题确实存在，有充分的 diff 证据支持，影响功能/安全/性能
- REJECT：问题是臆测的、diff 中找不到直接证据、或者是正常写法被误判

宁可漏报，不可误报。"""

REVIEW_PROMPT_TEMPLATE = """基准分支: {base_branch} → {head_branch}
变更文件: {files}

=== 代码变更（Diff）===
规则：只审查以 + 开头的新增行。以 - 开头的删除行仅作上下文，不要对删除的代码报问题。
{diff}
=== PR 意图说明（交叉验证用，不能作为放过问题的理由，也不能反过来用它制造不存在的问题）===
标题: {title}
描述: {description}

===

请按以下两阶段格式输出：

第一阶段：<think> 标签内写分析过程，长度不限。
先从代码 diff 本身推断这个 PR 在做什么，再对照 PR 意图说明验证推断是否一致，最后说真正的风险点在哪。不要把 PR 描述当答案，要从代码推理出答案。

第二阶段：紧接着输出 JSON（字段名英文，内容中文）：
{{
  "summary": "PR做了什么 + 整体质量判断，结论前置",
  "risk_level": "HIGH|MEDIUM|LOW",
  "walkthrough": [
    {{"file": "path/to/file.ts", "summary": "说明此文件改了什么"}}
  ],
  "issues": [
    {{
      "severity": "ERROR|WARNING|INFO",
      "file": "path/to/file.ts",
      "line": 42,
      "title": "问题标题",
      "description": "必须包含：（1）具体触发场景——什么输入/条件/操作会触发；（2）触发后的具体后果。缺少触发场景的问题不得上报。",
      "suggestion": "可执行的具体步骤。不写'建议验证''需要确认'等空话，给出验证的具体方法或修复的具体代码方向。",
      "confidence": 0.0到1.0，你对这个问题真实存在的把握，低于0.75请勿上报
    }}
  ],
  "priority_files": ["最多5个，按重要性排序，只列核心逻辑文件，CI/配置/lock文件不列"],
  "risk_areas": [
    {{
      "level": "HIGH|MEDIUM|LOW",
      "file": "path/to/file.ts",
      "title": "风险标题",
      "impact": "具体场景下的具体后果，不写'可能有问题'这种模糊描述"
    }}
  ],
  "merge_recommendation": {{
    "decision": "APPROVE|REQUEST_CHANGES|COMMENT（由后端根据issue严重程度决定，此处填你认为合理的值供参考）",
    "confidence": 0到100，你对整体分析结论的把握程度，有不确定的地方诚实给低分,
    "reasons": ["每条是具体的合并风险或通过理由，不重复、不凑数、不写'存在风险'这种废话"]
  }}
}}

--- 参考示例（真实PR标注）---

输入diff摘要（只展示关键+行）：
+ // usePositionCollector.ts:63
+ const mappedPositions = positions  // 原先此处调用 mapSubquestionPositionsToA3ThreeSheet
+ const mappedResult = finalResult   // 原先此处调用 mapPositionDataPageIdxForA3Three

+ // paperSize.ts
+ return Math.round((PAGE_WIDTH * 2) / 3)  // 原先无 Math.round

+ // a3Merger.ts:103
+ const overlap = PAGE_POINT * 2 + ANCHOR_POINT_SIZE  // 原先是 + ANCHOR_POINT_SIZE / 2

PR意图说明：统一A3Three与A4/A3的定位逻辑，page_idx直接为栏序号(0/1/2)，不再做全局坐标换算。

正确输出：
<think>
从diff看：大量换算代码被删掉，mappedPositions直接等于positions，说明坐标体系从全局换算改成了局部坐标。对照PR描述，完全吻合。真正的问题不是"改了坐标体系"本身——这是有意的——而是有没有证据证明后端扫描模块已经跟着改了page_idx的解析方式。overlap从/2改成全值，符合PR说明的overlap定义，但缺回归截图。Math.round是合理的亚像素修复，风险极低。CI升级和npmrc与核心逻辑无关，不报。
</think>
{{
  "summary": "删除A3Three全局坐标换算层，统一为局部坐标体系，净删173行。代码与PR意图吻合，主要风险是后端page_idx语义适配缺少验证证据。",
  "risk_level": "MEDIUM",
  "walkthrough": [
    {{"file": "src/feature/design-exam/hooks/export/usePositionCollector.ts", "summary": "删除全局坐标换算和page_idx÷3映射，直接使用局部坐标"}},
    {{"file": "src/feature/design-exam/utils/position/a3three.ts", "summary": "删除三个已无调用方的坐标换算工具函数"}},
    {{"file": "src/feature/design-exam/utils/export/a3Merger.ts", "summary": "overlap计算：ANCHOR_POINT_SIZE/2 → ANCHOR_POINT_SIZE"}},
    {{"file": "src/feature/design-exam/constants/paperSize.ts", "summary": "getPageWidth加Math.round，修复493.333px亚像素问题"}}
  ],
  "issues": [
    {{
      "severity": "WARNING",
      "file": "src/feature/design-exam/hooks/export/usePositionCollector.ts",
      "line": 63,
      "title": "page_idx语义变更缺下游适配证据",
      "description": "page_idx含义从"物理页序号（栏序号÷3）"改为"栏序号（0/1/2）"。触发场景：用A3Three模式导出答题卡，若后端扫描识别模块仍按旧语义把page_idx当物理页序号解析，A3Three全部题目的定位坐标都会错位，批改结果错误。",
      "suggestion": "在本地跑一次A3Three答题卡完整链路：前端导出 → 后端识别 → 确认题目坐标正确。或在PR描述中附上后端对应变更的commit链接。",
      "confidence": 0.88
    }},
    {{
      "severity": "WARNING",
      "file": "src/feature/design-exam/utils/export/a3Merger.ts",
      "line": 103,
      "title": "overlap修正缺视觉回归验证",
      "description": "overlap从PAGE_POINT*2+ANCHOR_POINT_SIZE/2改为PAGE_POINT*2+ANCHOR_POINT_SIZE，影响相邻两栏定位点重叠区域大小。触发场景：导出A3Three答题卡后扫描，若overlap值算错，定位点识别会偏移，导致所有题目坐标漂移。修改方向符合PR描述，但无截图或测试证明对齐正确。",
      "suggestion": "导出A3Three答题卡PDF，在图像编辑器量取第0栏和第1栏公共定位点的实际重叠像素，与overlap计算值（PAGE_POINT*2+ANCHOR_POINT_SIZE）对比是否一致。",
      "confidence": 0.80
    }}
  ],
  "priority_files": [
    "src/feature/design-exam/hooks/export/usePositionCollector.ts",
    "src/feature/design-exam/utils/export/a3Merger.ts",
    "src/feature/design-exam/utils/position/a3three.ts"
  ],
  "risk_areas": [
    {{
      "level": "MEDIUM",
      "file": "src/feature/design-exam/hooks/export/usePositionCollector.ts",
      "title": "page_idx语义变更需后端同步",
      "impact": "后端若未适配，A3Three扫描识别时所有题目定位偏移，批改结果全错"
    }},
    {{
      "level": "LOW",
      "file": "src/feature/design-exam/constants/paperSize.ts",
      "title": "像素取整的轻微累积误差",
      "impact": "三栏各取整后总宽可能与容器实际宽度差1px，特定缩放比下出现缝隙"
    }}
  ],
  "merge_recommendation": {{
    "decision": "COMMENT",
    "confidence": 78,
    "reasons": [
      "代码逻辑正确实现了PR描述的目标，无明显bug",
      "缺少后端page_idx适配的验证证据",
      "overlap修正缺少视觉回归截图"
    ]
  }}
}}

--- 示例结束 ---

格式规则：
- <think> 内只写自然语言，不写 JSON
- </think> 后直接输出 JSON，不加 markdown 代码块标记
- issues[].line 必须是 diff 中实际存在的 + 行的新文件绝对行号
- issues[].confidence < 0.75 的问题不要输出"""


def _make_client(api_key: str | None = None, base_url: str | None = None) -> AsyncOpenAI:
    cfg = load_config()
    resolved_key = (
        api_key
        or cfg.llm.api_key
        or cfg.deepseek_api_key
        or os.environ.get("DEEPSEEK_API_KEY")
        or "sk-placeholder"
    )
    resolved_base = base_url or cfg.llm.base_url or BASE_URL
    raw = AsyncOpenAI(
        api_key=resolved_key,
        base_url=resolved_base,
        max_retries=0,
    )
    if wrap_openai is not None:
        return wrap_openai(raw)
    return raw


def _extract_json(text: str) -> str:
    text = text.strip()
    fence_m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence_m:
        return fence_m.group(1).strip()
    return text


def _get_system_prompt(perspective: str = "default") -> str:
    return PERSPECTIVE_MAP.get(perspective, SYSTEM_PROMPT)


def _build_prompt(pr_context: dict) -> str:
    return REVIEW_PROMPT_TEMPLATE.format(
        title=pr_context["title"],
        description=pr_context["description"][:500],
        base_branch=pr_context["base_branch"],
        head_branch=pr_context["head_branch"],
        files=", ".join(pr_context["files"][:20]),
        diff=pr_context["diff"][:60000],
        file_contents_section="",
    )


def extract_diff_snippet(diff: str, file_path: str, line_num: int | None, context: int = 3) -> str | None:
    if not file_path or line_num is None:
        return None

    in_file = False
    hunk_lines: list[tuple[int | None, str]] = []
    current_new_line = 0

    for raw in diff.split('\n'):
        if raw.startswith('+++ b/'):
            in_file = (raw[6:] == file_path)
            hunk_lines = []
            current_new_line = 0
            continue
        if not in_file:
            continue
        if raw.startswith('@@'):
            m = re.search(r'\+(\d+)', raw)
            if m:
                current_new_line = int(m.group(1)) - 1
            hunk_lines.append((None, raw))
            continue
        if raw.startswith('+'):
            current_new_line += 1
            hunk_lines.append((current_new_line, raw))
        elif raw.startswith('-'):
            hunk_lines.append((None, raw))
        elif raw.startswith(' '):
            current_new_line += 1
            hunk_lines.append((current_new_line, raw))

    if not hunk_lines:
        return None

    target_idx = next((i for i, (ln, _) in enumerate(hunk_lines) if ln == line_num), None)
    if target_idx is None:
        return None

    start = max(0, target_idx - context)
    end = min(len(hunk_lines), target_idx + context + 1)
    return '\n'.join(raw for (_, raw) in hunk_lines[start:end])


async def judge_issues(
    diff: str,
    issues: list[ReviewIssue],
    pr_description: str = "",
    client: LLMClient | None = None,
) -> list[ReviewIssue]:
    if not issues:
        return issues

    llm = client or LLMClient()
    issues_text = "\n".join(
        f"{i+1}. [{issue.severity}] {issue.file}:{issue.line or '?'} — {issue.title}: {issue.description}"
        for i, issue in enumerate(issues)
    )
    description_section = f"\nPR 意图说明（用于判断问题是否属于有意的行为变更）:\n{pr_description[:300]}\n" if pr_description else ""
    prompt = f"""以下是对一个 PR 的代码审查发现的问题列表。请逐一判断每个问题是 CONFIRM 还是 REJECT。
{description_section}
判断标准：
- CONFIRM：diff 中有直接代码证据，且问题不是 PR 描述中已说明的有意变更
- REJECT：diff 中找不到直接证据；或问题描述的行为是 PR 描述中明确说明的预期结果；或是正常写法被误判

Diff（前 40000 字符）:
{diff[:40000]}

待验证问题：
{issues_text}

返回 JSON 数组：[{{"index": 1, "verdict": "CONFIRM"}}, ...]
只返回 JSON 数组，不要其他内容。"""

    try:
        content = await llm.chat(
            model=llm.model, max_tokens=512, temperature=0.2,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _extract_json(content)
        verdicts = json.loads(raw)
        confirmed = {v["index"] for v in verdicts if isinstance(v, dict) and v.get("verdict") == "CONFIRM"}
        if not confirmed:
            return issues
        return [issue for i, issue in enumerate(issues, 1) if i in confirmed]
    except Exception:
        return issues


async def analyze_pr(pr_context: dict, include_style: bool = False, perspective: str = "default", review_type: str = "all", model: str = MODEL, api_key: str | None = None, base_url: str | None = None) -> ReviewResult:
    type_to_perspective = {"all": "default", "bugs": "default", "security": "security", "performance": "performance"}
    effective_perspective = type_to_perspective.get(review_type, perspective)

    client = LLMClient(api_key=api_key, model=model, base_url=base_url)
    prompt = _build_prompt(pr_context)

    content = await client.chat(
        model=model, max_tokens=4096, temperature=1.0, top_p=1.0,
        messages=[
            {"role": "system", "content": _get_system_prompt(effective_perspective)},
            {"role": "user", "content": prompt},
        ],
    )

    raw = _extract_json(content)
    data = json.loads(raw)

    issues = [ReviewIssue(**issue) for issue in data.get("issues", [])]
    if not include_style:
        issues = [i for i in issues if i.severity != Severity.INFO]

    # confidence 过滤：低置信度问题直接丢弃
    min_conf = load_config().review.filters.min_confidence
    issues = [i for i in issues if i.confidence >= min_conf]

    # Judge 二次验证（传入 PR 描述供判断有意变更）
    issues = await judge_issues(pr_context["diff"], issues, pr_context.get("description", ""))

    # 为每个 issue 提取 diff 片段
    for issue in issues:
        if issue.diff_snippet is None:
            issue.diff_snippet = extract_diff_snippet(pr_context["diff"], issue.file, issue.line)

    walkthrough = [WalkthroughEntry(**w) for w in data.get("walkthrough", [])]

    priority_files = data.get("priority_files", [])
    risk_areas_data = data.get("risk_areas", [])
    risk_areas = [RiskArea(**r) for r in risk_areas_data if isinstance(r, dict)]

    # 规则兜底：decision 由 issue severity 决定，不依赖 LLM 判断
    has_error = any(i.severity == Severity.ERROR for i in issues)
    has_warning = any(i.severity == Severity.WARNING for i in issues)
    forced_decision = "REQUEST_CHANGES" if has_error else ("COMMENT" if has_warning else "APPROVE")
    mr_data = data.get("merge_recommendation")
    if isinstance(mr_data, dict):
        mr_data["decision"] = forced_decision
        merge_recommendation = MergeRecommendation(**mr_data)
    else:
        merge_recommendation = MergeRecommendation(decision=forced_decision, confidence=70, reasons=[])

    stats = pr_context["stats"]
    stats.issues_by_severity = {
        "ERROR": sum(1 for i in issues if i.severity == Severity.ERROR),
        "WARNING": sum(1 for i in issues if i.severity == Severity.WARNING),
        "INFO": sum(1 for i in issues if i.severity == Severity.INFO),
    }

    return ReviewResult(
        pr_url=pr_context.get("pr_url", ""),
        summary=data.get("summary", ""),
        risk_level=data.get("risk_level", "LOW"),
        walkthrough=walkthrough,
        issues=issues,
        stats=stats,
        priority_files=priority_files,
        risk_areas=risk_areas,
        merge_recommendation=merge_recommendation,
    )


CURSOR_PATH_SYSTEM_PROMPT = """You are analyzing a code diff for a reviewer.
List the line numbers (1-indexed) that contain actual code changes.
Focus on +/- lines. Prioritize logic changes over imports/boilerplate.
Return a JSON array of integers, e.g. [5, 23, 8, 41]."""


def _fallback_cursor_path(diff_lines: list[str]) -> list[int]:
    add_del: list[int] = []
    other: list[int] = []
    for i, line in enumerate(diff_lines):
        stripped = line.lstrip()
        if stripped.startswith('--- ') or stripped.startswith('+++ ') or stripped.startswith('@@'):
            other.append(i + 1)
        elif line.startswith('+') or line.startswith('-'):
            add_del.append(i + 1)
        else:
            other.append(i + 1)
    return (add_del + other)[:15]


async def generate_cursor_path(diff_lines: list[str]) -> list[int]:
    llm = LLMClient()
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(diff_lines))
    prompt = f"Diff lines:\n{numbered}\n\nReturn only a JSON array of the most interesting line numbers in reading order."

    try:
        content = await llm.chat(
            model=llm.model, max_tokens=150, temperature=0.3,
            messages=[
                {"role": "system", "content": CURSOR_PATH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _extract_json(content)
        path = json.loads(raw)
        if isinstance(path, list) and len(path) > 0 and all(isinstance(i, int) for i in path):
            valid = [i for i in path if 1 <= i <= len(diff_lines)]
            if valid:
                return valid[:15]
    except Exception:
        pass

    return _fallback_cursor_path(diff_lines)


async def stream_analyze_pr(pr_context: dict, perspective: str = "default", model: str = MODEL, api_key: str | None = None, base_url: str | None = None):
    llm = LLMClient(api_key=api_key, model=model, base_url=base_url)
    prompt = _build_prompt(pr_context)

    stream = await llm.client.chat.completions.create(
        model=model, max_tokens=4096, temperature=1.0, top_p=1.0, stream=True,
        messages=[
            {"role": "system", "content": _get_system_prompt(perspective)},
            {"role": "user", "content": prompt},
        ],
    )

    # 状态机：解析 <think>...</think> 和后续 JSON 两个阶段
    THINK_START = "<think>"
    THINK_END = "</think>"
    phase = "before_think"
    buf = ""

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue

        buf += delta

        if phase == "before_think":
            if THINK_START in buf:
                buf = buf[buf.index(THINK_START) + len(THINK_START):]
                phase = "thinking"

        if phase == "thinking":
            if THINK_END in buf:
                idx = buf.index(THINK_END)
                if idx > 0:
                    yield json.dumps({"type": "thinking", "delta": buf[:idx]})
                buf = buf[idx + len(THINK_END):]
                phase = "result"
            else:
                # 只保留 len(THINK_END)-1 个字符作为边界缓冲，其余立即 yield
                safe_len = len(buf) - (len(THINK_END) - 1)
                if safe_len > 0:
                    yield json.dumps({"type": "thinking", "delta": buf[:safe_len]})
                    buf = buf[safe_len:]

        elif phase == "result":
            yield json.dumps({"type": "result", "delta": delta})
            buf = ""

    # 兜底：模型未输出 <think> 标签时，buf 中积累的内容全部作为 result
    if phase != "result" and buf.strip():
        yield json.dumps({"type": "result", "delta": buf})
