# PRism — CLAUDE.md

> AI-powered PR Review Assistant. Backend: FastAPI + Python 3.12. GitHub App deployment.

## 产品形态（2026-06 确定）

- **交互**：GitHub App 安装 → PR 打开/同步自动审查 → 结果写在 PR 评论区（inline comment + summary comment）→ @mention 对话
- **前端**：无。`frontend/` deprecated，审查结果 UI = GitHub PR 页面本身
- **本地测试**：CLI entry point（`python -m app.cli`），输出 markdown 到终端
- **部署**：Docker 镜像到服务器，收 webhook、跑 review、写 PR 评论
- **认证**：GitHub App（私钥 + installation_id 换 token），替代 personal token

## 项目结构

- `backend/` — FastAPI，全部 Python，无前端依赖
  - `app/main.py` — API 服务（health check + webhook 入口）
  - `app/worker.py` — ARQ worker，消费审查队列
  - `app/graph.py` — ReviewGraph，编排三 Agent + Judge
  - `app/agents/` — Bug/Security/Quality Agent + JudgeAgent
  - `app/services/` — github.py（GitHub API）、llm.py（LLM 调用）、context.py（符号检索）
  - `app/models/` — Pydantic schema
  - `app/routers/` — webhook.py + review.py（CLI 用保留）
  - `app/auth.py` — GitHub App JWT + installation token 交换
  - `app/cli.py` — 本地测试 CLI，`prism review <pr-url>`
  - `app/config.py` + `prism.yaml` — 配置
- `frontend/` — **deprecated**，仅保留作为参考不移除

## 启动命令

```bash
# 后端（API 服务）
cd backend && uvicorn app.main:app --reload --port 8000

# Worker（消费 Webhook 审查队列）
cd backend && python -m app.worker

# Docker 一键启动（API + Worker + Redis）
docker compose up --build

# CLI 本地测试
cd backend && python -m app.cli review https://github.com/owner/repo/pull/42
```

## 核心约束

### 后端
- 所有 LLM 调用走 `app/services/llm.py`，不在 router 层直接调用 openai SDK
- Severity Gating 在 `JudgeAgent` 内执行，INFO 级别默认过滤
- GitHub 数据获取走 `app/services/github.py`，router 层不直接调用 httpx
- 编排走 `app/graph.py`（ReviewGraph），不直接在 router 层编排 Agent
- Webhook 队列消费走 `app/worker.py`（ARQ），不直接用 BackgroundTasks
- GitHub App 认证走 `app/auth.py`，不在其他模块直接处理 JWT
- 配置走 `app/config.py` + `prism.yaml`，不硬编码在代码里

### 通用
- 禁止 `--no-verify`
- commit 格式：`<type>(<scope>): <描述>`

## 架构决策

### 上下文策略
- **函数级 chunk**（非完整 diff 给 LLM）：结构化短 prompt > 长 prompt，SWE-PRBench 数据支撑
- **符号级一跳检索**（非文件级、非多跳）：确定性检索控制深度边界，GA 论文"When More Retrieval Hurts"支撑
- **文件级内容废弃**：`fetch_pr_context` 不再拉 `file_contents`，SWE-PRBench 证实加文件上下文降低所有模型表现

### 幻觉控制
- **程序验证 evidence 有效性**（非 LLM 自评）：要求 LLM 输出引用具体行号，程序验证行号是否存在、变量是否真实出现过
- **Evidence 字段**：`FindingSchema.evidence` 存储引用的代码行号/片段，空 evidence 直接丢弃
- **Confidence 过滤**：双重机制 — LLM 自评 + 程序验证交叉检查

### Judge 策略
- **两遍去重**：规则去重（80% 显式重复）→ 按文件分组 → Judge 语义分组 + 统一打分
- **Judge 输入按文件切分**：每次调用 token 量可控，用小模型处理剩余语义重叠
- **编排顺序**：三 Agent 并行 → 规则去重 → 按文件分组 → Judge 批量处理 → severity 过滤 → 输出

### 编排
- **asyncio.gather 并行执行三 Agent**（短期）
- **后续评估 LangGraph**（若需要更复杂的编排控制）

### 可观测性
- **LangSmith tracing** + 结构化日志（graph.py 各阶段计时）

### 模型
- **Expert Agent**：deepseek-v4-flash（快、便宜、足够）
- **Judge Agent**：deepseek-v4-pro（需要更可靠的判断）
- Token 预算硬上限，总上下文不超过 16K

## 关于竞品的面试要点

### 竞品技术方案速查

CodeRabbit:
- 方案：diff + 40+ linter + 代码图实验
- 缺点：不做全量索引，系统级感知弱
- 面试可讲：CodeRabbit $84M 融资但技术深度远不如 Greptile，证明市场覆盖比技术深度重要

GitHub Copilot Code Review:
- 方案：diff + agentic 架构全仓上下文检索（semantic search + grep + usage tracing）
- 缺点：GitHub only，定价不可预测
- 面试可讲：大型平台做 PR review 的"静默优先"策略（suppress 低置信度评论）

Greptile:
- 方案：Graph 全量索引 + Agent Swarm，$29M 融资
- 缺点：慢，贵，需 clone 全仓库
- 面试可讲：monorepo 场景的 cross-file bug 检测是独家卖点

Qodo:
- 方案：多 agent 并行（bug/security/quality/coverage）+ Context Engine 多仓索引
- 缺点：设置复杂
- 面试可讲：多 Agent 编排的架构选择

Merlin:
- 方案：Rust + ReAct loop + RAG pipeline + 19 tool 调度
- 缺点：极早期
- 面试可讲：Rust 单二进制的性能优势 + ReAct loop 的 tool 冲突解决

AgnusAi:
- 方案：Tree-sitter 符号图（Postgres 后端）+ blast radius 三级深度
- 缺点：solo dev，仅 3★
- 面试可讲：不 clone 全仓库做 cross-file 分析的轻量方案可比

### 面试词库

| 黑话 | 大白话 |
|------|--------|
| 代码上下文 | 改一个文件，你知道它影响到哪些别的文件 |
| Blast radius | 改了 A，B/C/D 会不会跟着挂 |
| Signal-to-noise | 评论里有用和没用各占多少 |
| 噪声控制 | 怎么把没用的评论过滤掉，不让开发者嫌吵 |
| RAG pipeline | 先搜一下有没有相关的历史 review 或代码，再给 LLM 看 |
| ReAct loop | LLM 自己决定下一步用什么工具 |
| Agent orchestration | 多个 agent 怎么做分工，谁先跑谁后跑 |
| Incremental 索引 | 不是全量重扫代码库，只更新改动的部分 |
| Token budget | 每次调用给 LLM 多少上下文，超了怎么办 |

## 构建验证

```bash
# 后端
.venv/bin/ruff check app/ tests/ && .venv/bin/python -m pytest tests/ -v

# 前端（无）
```

## AI 全量编码质量契约

### 原则

不要把 AI 写的代码当真，直到有客观证据证明它对。

### 规则 1：写测试先于写实现（TDD with AI Agents）

```
Red（写失败测试）→ 你确认测试正确 → Green（最小实现让它通过）→ 你确认 AI 没偷改测试 → Refactor
```

- 每步开工前我会问：主人，这步先写测试还是先实现？
- 我写测试（Red）后你先审，测试通过了你签字，我再写实现（Green）
- **严禁 AI 在 Green 阶段修改测试代码**。如果实现需要通过改测试来变绿，说明合约（测试）错了，你重订合约
- Refactor 阶段不改行为，只改质量（lint/type/命名/抽取）

### 规则 2：七层质量门

| 层 | 捕获什么 | PRism 具体工具 | 谁执行 |
|----|---------|---------------|--------|
| 1. Lint | 风格漂移、死代码、幻觉 import | `ruff check app/ tests/` | AI |
| 2. Type Check | 类型漂移、`any` 回退 | `mypy app/ --strict`（若安装） | AI |
| 3. 安全扫描 | 硬编码密钥、SQL 注入 | 无 SAST 工具时不强推 | — |
| 4. 测试覆盖 | 新代码未覆盖、回归 | `pytest tests/ -v --cov=app/` | AI |
| 5. 边界一致 | 跨模块接口不匹配 | 编译时由类型系统保证 | 自动 |
| 6. 对抗 LLM 审查 | 幻觉 API、遗漏边缘情况、过度工程 | 你换一个模型（Claude 或其他）审我 diff | 你 |
| 7. 最终签字 | 业务逻辑正确性 | 你看 diff，确认 AI 没改测试、没偷跑 | 你 |

每层只管前一层漏掉的东西。第 7 层你砍掉可以，但前 6 层我跑。

**门禁**：PR 合并前必须跑通第 1 + 第 4 层。若第 2 层工具（mypy）不存在则跳过。

### 规则 3：AI 改过的文件一律视为未测试

场景：我改了 `llm.py` → 为了编译通过改了 `main.py` 的 import → 顺手改了 `test_llm.py` 的 mock。

规则：
- 我不修改任何测试文件，除非你明确要求我修（且此时你需要重审测试）
- 我改过的文件，相关测试全部重跑
- 你在 diff 里确认我没有偷改测试来匹配实现

### 规则 4：Builder 和 Validator 隔离

我写代码（Builder），你审或者用不同模型审我输出（Validator）。

执行方式：
- 我不审自己的代码
- 每个 PR 的 diff，你换一个模型（Claude 或其他）扫一遍，专门找：幻觉 API、遗漏的边缘情况、过度工程
- 审出来的问题归入 PR 的 issues，不改好不合入

### 规则 5：每 PR 是独立可验证单元

PLAN.md 的 6 个 PR 已按此拆分，每 PR 符合：
- **改 ≤3 个核心文件**（例外：纯新增配置/测试不计入）
- **独立可验证**：有测试或手动验证方式
- **不改测试**：除非 PR 本身是"改测试"
- **主分支可运行**：PR 合入后 `uvicorn app.main:app --reload` 能启动

### 仲裁机制

我违反以上任何规则时，你：
1. 说"规则 X 违反"
2. 我立即停止当前操作
3. 你给出修正方向，我照做