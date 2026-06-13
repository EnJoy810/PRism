# PRism 架构设计

> AI 驱动的 PR Review 助手。多 Agent 并行审查，裁判汇总去重，自托管可部署。

---

## 系统架构

```
GitHub Webhook（opened / synchronized / issue_comment @prism-bot）
  │
  ▼
验证 HMAC 签名 → 返回 202（10 秒内）
  │
  ▼
Redis 队列（ARQ Worker）
  │
  ▼
ReviewGraph（自定义 asyncio.gather 编排）
  │
  ├── fetch_context（获取 PR diff + 元数据 + 文件列表 + 调用链）
  │
  ├── [安全 Agent]    ────┐
  ├── [性能 Agent]    ────┤── 并行执行，DeepSeek V4 Flash
  ├── [代码规范 Agent] ──┘
  │
  ├── Judge Agent（裁判）── 去重 / 降噪 / 严重级别校准 / 合并建议
  │                     ── 更强模型（DeepSeek V4 Pro 或 Claude）
  │                     ── 任一 Agent 超时/失败，跳过并标注
  │
  └── post_comment（写回 GitHub PR 评论区）
               可选：SSE 流推送给 Web Dashboard
```

### 阶段对应关系

- Phase 1：Webhook 接入 + Redis 队列 + GitHub App 认证
- Phase 2：多 Agent 图编排（ReviewGraph — asyncio.gather 并行） + 裁判 Agent + 容错 + 成本护栏
- Phase 3（独立）：Web Dashboard 历史记录 + 配置面板

Phase 1 和 Phase 2 合并为一个版本发布，不拆。

---

## Agent 设计

### 三个专家 Agent

| Agent | System Prompt 职责 | 输出 |
|-------|-------------------|------|
| 安全 | SQL 注入、XSS、CSRF、敏感信息泄露、认证缺陷、命令注入 | `list[Finding]` |
| 性能 | N+1 查询、内存泄漏、死锁、大对象重复创建、同步阻塞 IO | `list[Finding]` |
| 代码规范 | 设计缺陷、职责边界混乱、重复代码、过长函数、过度耦合 | `list[Finding]` |

每个 Agent 只关注自己的领域，忽略其他维度。通过 System Prompt 强制执行。

### 两阶段提示（解决 JSON 格式不稳定）

1. Agent 先自由推理（chain-of-thought，`<think>` 标签），不限长度
2. 再将推理结果交给同一 Agent，提取结构化 JSON 输出

JSON 格式由 `Pydantic FindingSchema` 定义，Agent 出口做 Pydantic 校验。校验失败时标记"该 Agent 结果格式异常，已跳过"。

### 裁判 Agent

职责（按执行顺序）：
1. 去重：同一行报相同问题的只保留严重级别最高的
2. 重新分类：走错分区的问题挪到正确分区
3. 降噪：置信度 < 0.6 的降一级标注
4. 合并建议：根据最终 issue 严重级别确定 APPROVE / REQUEST_CHANGES / COMMENT

裁判不做模糊判断，全部规则驱动。规则写在 prompt 里，不出自由裁量。
裁判使用比专家更强的模型。

---

## 上下文策略

不克隆完整仓库，只获取：
- PR diff（unified diff 格式）
- PR 元数据（标题、描述、base_branch、head_branch）
- 变更文件列表（含每个文件的增删行数）
- 关联 commit 信息
- Level 3（规划中）：GitHub GraphQL 调用链分析

超长 PR 处理：
- Diff > 100KB 时截断前 100KB
- 文件列表自动分页拉取（GitHub API per_page=100）
- PR > 30 个文件或 diff 被截断时自动启用多轮次分批审查：
  每批 ≤30 个文件，各批并发运行 3 个 Agent，结果汇总后由 Judge 统一去重
- 取变更最多的前 3 个文件获取完整内容供 Agent 参考

### 范围限定

LLM-only 审查不跑静态分析工具。这是有意识的设计决策：
- 不做 sandbox 避免了 linter/SAST 的安装、版本管理、超时控制、输出解析等基础设施
- 代价：安全审查召回率有上限。文档诚实说明这一段。

---

## 容错策略

### Agent 超时/失败（Option B）

任一 Agent 超时或返回格式错误：
- 裁判用其他 Agent 的已有结果继续输出
- 在最终评论中标注"XX Agent 本次未返回"
- 不中断其他 Agent，不整次报废

### LLM API 调用容错

- 每次 LLM 调用包装在带重试的 Client 中
- 重试策略：指数退避，最多 3 次，退避间隔 1s / 2s / 4s
- 区分错误类型：
  - 429（限流）→ 等待后重试
  - 500 / 502 / 503（服务端）→ 等待后重试
  - 401（认证失败）→ 不重试，直接报错
  - 空响应 / 乱码 → 重试

### GitHub API 容错

- post_comment 重试：指数退避，最多 3 次，退避间隔 1s / 2s / 4s
- 重试完仍然失败时，异常上抛由 Worker 层记录日志

---

## 成本护栏

审查开始前预检：
1. 估算本次审查的 token 消耗（基于 diff 大小 + Agent 数量）
2. 估算结果超过阈值时拒绝执行，返回 4xx

审查执行中监控：
1. TokenBudget 每次 LLM 调用前做 token 预算预检
2. 每次 LLM 调用后累加实时消耗到总预算
3. 超过阈值时熔断停止后续调用，返回已有结果
4. token 消耗和预算均输出到日志

预算阈值从配置文件读取，不是硬编码。

---

## 流式输出

SSE 事件类型：

| 事件 | 触发时机 | 内容 |
|------|---------|------|
| `diff` | fetch_context 完成 | PR diff 片段 + 元数据 |
| `thinking` | 裁判 Agent 推理中 | 裁判的 thinking token 流 |
| `result` | 裁判输出结果 | 增量结果片段 |
| `done` | 全部完成 | 最终的完整 ReviewResult JSON |

不做三个 Agent 分别流式展示。三个 Agent 跑完只需数秒，人眼来不及追踪。差异化在于裁判汇总过程的可视化，不是每个 Agent 的 thinking。

---

## 部署

### docker compose

```yaml
services:
  api:       # FastAPI 后端
  worker:    # ARQ Worker（消费审查队列）
  redis:     # 队列 + 缓存
  web:       # Next.js 前端（可选，依赖 Phase 3）
```

### 配置文件暴露

```yaml
# prism.yaml（示例）
review:
  budget:
    max_per_review_usd: 0.50
    max_tokens_per_call: 4096
  agents:
    expert_model: deepseek-v4-flash
    judge_model: deepseek-v4-pro
  filters:
    min_confidence: 0.6
    severity_threshold: WARNING
  skip:
    - "*.lock"
    - "*.snap"
    - "*.min.js"
```

---

## 工程质量

- Pydantic v2 校验所有 Agent 输入输出
- 三个专家 Agent、裁判 Agent、fetch_context 各有独立单元测试
- CI 自动跑（pytest + ruff）
- 结构化日志：每个节点执行前后打印（Agent 名称、耗时、token 数、结果摘要）
- LangSmith 免费版追踪每条 trace（Phase 2）

---

## 不做的事

- SQLite Checkpoint — 审查跑完就出结果，没有等待恢复的场景，写入无意义
- BackgroundTasks — 进程回收丢任务，直接上 Redis 队列
- 前端分 Agent 展示 thinking token — 工程复杂度 > 展示价值
- 超长 PR 按优先级排序 — 改为多轮 round-robin 分批审查
- 用户侧记忆/反馈学习 — 独立功能，未来再评估
- 完整仓库克隆 — 不做 sandbox 所以不需要

---

## 目录结构计划

```
backend/app/
├── main.py                  # FastAPI app 入口
├── config.py                # 配置读取（prism.yaml + 环境变量）
│
├── routers/
│   ├── review.py            # /api/review, /api/review/stream
│   └── webhook.py           # /api/webhook（GitHub App 入口）
│
├── services/
│   ├── llm.py               # LLM Client（重试、预算、tracing）
│   ├── github.py            # GitHub API（fetch_pr_context、parse_pr_url）
│   ├── github_review.py     # GitHub Review API（post_comment）
│   └── queue.py             # ARQ Worker + Redis 连接
│
├── agents/
│   ├── base.py              # Agent 基类（两阶段提示、Pydantic 校验）
│   ├── security.py          # 安全审查 Agent
│   ├── performance.py       # 性能审查 Agent
│   ├── quality.py           # 代码规范 Agent
│   └── judge.py             # 裁判 Agent（去重/降噪/合并）
│
├── graph.py                 # ReviewGraph 编排（fetch → parallel agents → judge → post）
│
└── models/
    ├── review.py            # ReviewRequest / ReviewResult / ReviewIssue
    └── agent.py             # FindingSchema / AgentResult / JudgeVerdict
```
