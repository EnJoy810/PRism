# PRism — AGENTS.md

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
- `app/services/` — github.py（GitHub API）、llm.py（OpenAI-compatible LLM 调用）、context.py（符号检索）
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

### 跨文件分析（2026-06 敲定，待实现）

**方案**：tree-sitter + SQLite 调用图 + BFS blast radius

**为什么不用向量 RAG**：向量是语义相似，代码调用关系是精确匹配。"谁调用了这个函数"用向量找会返回语义相近但没有调用关系的代码，精度不够。调用图直接查，没有噪声。

**为什么不用 LSP**：LSP 启动慢（需要热身）、有状态（难并发）、多语言要启多个进程。工程成本远超收益，当前场景不值得。

**为什么不用向量做动态调用兜底（短期）**：动态调用是行业未解问题，CodeRabbit/Greptile/Qodo 都追不到，接受这个边界比假装能解决更诚实。向量留作后续迭代。

**实现模块**：
- `app/services/repo.py` — shallow clone（`head.sha` 而非默认分支）+ LRU 缓存管理
- `app/services/indexer.py` — tree-sitter 解析 → SQLite（nodes + edges），增量更新（file_hash 比对）
- `app/services/blast_radius.py` — BFS depth=2，visited set 防死循环，50% diff token 上限剪枝
- `app/services/context.py` — 修改：优先走本地调用图，fallback GitHub Search API

**工程约束**：
- clone 用 `head.sha`，不用默认分支（老 PR 用最新代码是错的）
- clone 与 review 并行，clone 失败自动退化成 diff-only，主链路不依赖 clone 成功
- installation token 不出现在日志（clone URL 含 token，clone 完立刻抹掉）
- 跳过 `node_modules/`、`vendor/`、`dist/`、`test_*.py`、`*.test.ts`
- 单文件解析失败跳过，不中断整体
- 按 `repo@sha` 隔离 SQLite 文件，防并发写冲突
- Prompt 明确标注 `[DIFF]` vs `[CONTEXT]`，只对 DIFF 部分报问题

**动态调用边界声明**：静态分析的天然盲区，不做 false claim，PR 评论中标注"动态调用未覆盖"。

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
- LLM 调用使用 OpenAI-compatible 接口，配置来源为 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 或 `prism.yaml` 的 `llm` 段
- **Expert Agent**：默认读取配置中的 `review.agents.expert_model`
- **Judge Agent**：默认读取配置中的 `review.agents.judge_model`
- Token 预算硬上限，总上下文不超过 16K

## 产品定位（2026-06 确定）

**一句话**：PR-Agent 报太多太吵，CodeRabbit 误报率高还要收费。PRism 开源自部署，报得少，每条有据可查。

**核心差异化**：
- PR-Agent 最高频投诉是重复评论（GitHub issue #2037、#1833、#2402）→ PRism 两遍去重解决
- CodeRabbit 被横评点名"最高误报率"，且 credits 耗尽会阻塞 merge → PRism evidence 验证 + 开源自部署解决
- 所有 diff-only 工具看不到跨文件影响 → PRism 调用图解决

**不做的事**：向量 RAG、LSP、多平台（GitLab/Bitbucket）、历史 PR 记忆——等有用户反馈再说

---

## 完整功能规划

### 已完成
- GitHub App 全链路（webhook → ARQ 队列 → Worker → PR 评论）
- 三 Agent 并行（Security/Quality/Performance）+ Judge 两遍去重
- Evidence 程序验证（行号必须真实存在于 diff 新增行）
- Severity 过滤（INFO 默认不报）
- OpenAI-compatible LLM 配置（兼容 DeepSeek fallback）

### 第一阶段：调用图跨文件分析（进行中）
见 PLAN_CALLGRAPH.md。`repo.py`、`indexer.py`、`blast_radius.py` 基础模块已存在，仍需集成验证和真实 PR 评测。
解决"改了 A，B 跟着挂，工具看不到"的结构性缺陷。

### 第二阶段：BlockDiff — 改给 AI 看的 diff 格式
把 unified diff（加减号行）改成函数级新旧对比：
```
函数 process_order 改动了：
旧版本：接收一个参数，返回 tax
新版本：接收两个参数，新增调用 apply_discount
```
tree-sitter 已装（调用图用），共用解析结果，工程量中等。
没有任何竞品在做，有 arxiv 2604.27296 论文支撑。

### 第三阶段：Linter + LLM 并行
和 CodeRabbit 同一架构判断：
- Bandit（Python 安全）/ Semgrep 先扫，确定性问题直接进 findings，不过 LLM
- LLM 负责找规则扫不到的逻辑漏洞
- 两路合并进 Judge 统一去重
纯 LLM 精确率 65%，混合方案接近 90%，arxiv 2411.03079 数据支撑。

### 开源发布时机
调用图做完后发布 Show HN。那时能说：
1. 开源自部署，不被商业配额绑架
2. 每条问题有行号证据，程序验证
3. 能看到跨文件影响
4. 报得少，不会两周后被开发者无视

---

## 面试技术亮点叙事

```
发现 diff-only 的缺陷（跨文件看不到）
    → 调研四个竞品，选调用图不选向量（"When More Retrieval Hurts"论文）
        → 幻觉控制：evidence 程序验证，不让 LLM 自评
            → 信噪比优先：CR-Bench 数据，追召回率会毁掉 SNR
                → Linter 并行：和 CodeRabbit 同判断，各干各擅长的
```

每个决策都有依据：论文数据 / 竞品 issue 数据 / 横评数据。不是"我觉得这样好"。

---

## 关于竞品的面试要点

### 竞品技术方案速查

CodeRabbit:
- 方案：diff + 40+ linter + LanceDB 向量 RAG + 轻量代码图
- 动态调用处理：向量语义兜底（不追调用链，用语义相似性覆盖）
- 缺点：向量对代码精度不够，动态调用是兜底不是真正解决
- 面试可讲：$84M 融资证明市场存在；混合向量+图是合理工程选择，PRism 选纯图是精度优先

GitHub Copilot Code Review:
- 方案：diff + agentic 架构（agent 自主决定用 semantic search / grep / usage tracing）
- 动态调用处理：agent 主动 grep 搜索用法，最接近真正解决，但慢且贵
- 缺点：GitHub only，定价不可预测，agentic 方案 token 消耗大
- 面试可讲：agentic 探索 vs 预建索引的 trade-off；"静默优先"策略（suppress 低置信度评论）

Greptile:
- 方案：全量 clone + Neo4j 图数据库 + 语义搜索混合，$29M 融资，声称 82% bug catch rate
- 动态调用处理：静态图，追不到动态调用，但支持多跳图遍历（A→B→C），链路比 PRism 深
- 缺点：慢，贵，需 clone 全仓库，Neo4j 运维成本高
- 面试可讲：PRism 与 Greptile 同一技术判断（图 > 向量），但更轻量（SQLite vs Neo4j）

Qodo:
- 方案：多 agent 并行（bug/security/quality/coverage）+ Context Engine 多仓索引（向量）
- 动态调用处理：向量语义兜底，同 CodeRabbit
- 缺点：设置复杂，Context Engine 实现细节未公开
- 面试可讲：多 Agent 编排架构；向量对代码场景的精度局限

Merlin:
- 方案：Rust + ReAct loop + RAG pipeline + 19 tool 调度
- 缺点：极早期
- 面试可讲：Rust 单二进制的性能优势 + ReAct loop 的 tool 冲突解决

AgnusAi:
- 方案：Tree-sitter 符号图（Postgres 后端）+ blast radius 三级深度
- 缺点：solo dev，仅 3★
- 面试可讲：不 clone 全仓库做 cross-file 分析的轻量方案可比

### 真实用户痛点数据（2026-06 调研）

PR-Agent GitHub Issues 高频投诉（按评论数排序）：
- #2037 重复 inline comment（每次 push 重新报同样问题）
- #1833 同一 code block 重复 improve 建议
- #2402 GitLab 上 persistent suggestions 被重复创建
- #2042 大 PR 处理失败（不是降级，是直接报错）
- 大量配置项不生效（ignore 规则、环境变量被忽略）

CodeRabbit 用户痛点（无公开 issue tracker，来自横评和社区）：
- 被横评点名"highest false-positive rate"
- credits 耗尽后 PR status check 变红，阻塞 merge queue
- 闭源，问题修没修用户不知道

行业数据：
- 工具上线两周后开发者开始无视 AI 评论（DevOpsDigest）
- Greptile 上线初期只有 19% 评论被处理，加过滤后到 55%
- CR-Bench：最好单次调用 SNR=5.1，召回率 27%；激进方案召回率 33% 但 SNR 崩到 1.9
- 纯 LLM 精确率 65.5%，SAST+LLM 混合接近 90%（arxiv 2411.03079）

### 动态调用行业现状（2026-06）
没有任何竞品真正解决了动态调用问题：
- 向量兜底（CodeRabbit、Qodo）：语义相似，不是精确追踪
- 静态图多跳（Greptile）：链路深，但动态调用同样追不到
- agentic grep（Copilot）：最接近解决，但慢且贵，不适合批量 PR
- PRism 选择：接受静态分析边界，专注把精确调用图做好，不做 false claim

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
| 6. 对抗 LLM 审查 | 幻觉 API、遗漏边缘情况、过度工程 | 你换一个模型（Codex 或其他）审我 diff | 你 |
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
- 每个 PR 的 diff，你换一个模型（Codex 或其他）扫一遍，专门找：幻觉 API、遗漏的边缘情况、过度工程
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
