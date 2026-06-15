<div align="center">
  <h1>PRism</h1>
  <p><strong>AI 驱动的 Pull Request 代码审查助手</strong></p>
  <p>GitHub App + CLI，多 Agent 并行审查，低噪声 PR 评论</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
    <img src="https://img.shields.io/badge/DeepSeek-V4_Flash-4A90D9?style=flat-square" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
  </p>
</div>

---

## 项目简介

PRism 是一款自部署 AI PR Review 工具，目标是在 GitHub PR 评论区输出少而准的审查结果。当前产品形态不是 Web Dashboard，而是 GitHub App 自动审查 + CLI 本地测试。LLM 调用走 OpenAI-compatible 接口，默认配置可切换为 DeepSeek 或其他兼容模型。

### 使用形态

| 形态 | 用途 | 状态 |
|------|------|------|
| CLI | 本地输入 PR URL，输出 Markdown 审查结果 | 已实现 |
| GitHub App | PR 打开/同步后自动审查，写回 PR 评论区 | 已实现 |
| 前端页面 | 旧版贴 URL 审查 UI | 已废弃，`frontend/` 仅保留参考 |

### 能力状态

| 能力 | 状态 | 说明 |
|------|------|------|
| 三 Agent 并行审查 | 已实现 | Security / Quality / Performance 并行分析 |
| Judge 去重与 severity gating | 已实现 | INFO 默认过滤，减少噪声 |
| Evidence 程序验证 | 已实现 | finding 必须引用 diff 新增行中的真实片段 |
| GitHub App Webhook + Worker | 已实现 | FastAPI 接收 webhook，ARQ Worker 消费队列 |
| SAST 增强 | 已有基础模块 | `services/sast.py` 封装 Semgrep，缺工具时静默降级 |
| 调用图跨文件分析 | 进行中 | tree-sitter + SQLite + BFS 模块已存在，仍需持续集成和评测 |
| BlockDiff 函数级 diff | 规划中 | 把 unified diff 转为函数级新旧对比 |

---

## 核心差异

| 对比项 | PR-Agent | CodeRabbit | PRism |
|--------|----------|------------|-------|
| 部署方式 | 云服务 / 自部署 | 云服务 | 开源自部署 |
| 结果 UI | PR 评论区 | PR 评论区 | PR 评论区 |
| 重复评论控制 | 高频投诉 | 闭源不可控 | 规则去重 + Judge 语义去重 |
| 幻觉控制 | 主要依赖模型输出 | 闭源不可控 | evidence 行号/片段程序验证 |
| 跨文件分析 | diff-only 为主 | 向量/轻量图混合 | tree-sitter 调用图，失败降级 diff-only |
| 产品策略 | 功能多 | 零摩擦商业服务 | 少报、准报、可自部署 |

---

## 快速开始

### 环境要求

- Python 3.12+
- OpenAI-compatible LLM API Key
- Redis（GitHub App / Worker 模式需要）

### CLI 模式

```bash
git clone https://github.com/EnJoy810/PRism.git
cd PRism/backend
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 或 DEEPSEEK_API_KEY
python -m app.cli review https://github.com/owner/repo/pull/42
```

私有仓库可传入 GitHub token：

```bash
python -m app.cli review https://github.com/owner/repo/pull/42 --token ghp_xxx
```

### Docker 模式

```bash
docker compose up --build
```

启动内容：

- FastAPI API: `http://localhost:8000`
- ARQ Worker: 消费审查队列
- Redis: 队列依赖

### GitHub App 自动审查

1. 在 GitHub 创建 GitHub App：Settings -> Developer settings -> GitHub Apps -> New GitHub App
2. Webhook URL 设置为：`https://your-domain.com/api/webhook`
3. 订阅事件：`Pull requests`、`Issue comments`
4. 生成私钥并安装到目标仓库
5. 配置环境变量：

```bash
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
GITHUB_APP_ID=your_app_id
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...
GITHUB_WEBHOOK_SECRET=your_webhook_secret
REDIS_URL=redis://localhost:6379/0
```

---

## 审查流程

```text
GitHub PR opened/synchronized
        |
        v
FastAPI webhook verifies signature
        |
        v
ARQ queue job
        |
        v
ReviewGraph
        |
        +--> fetch PR diff / metadata / changed files
        +--> prepare optional context / SAST / blast radius
        +--> run Security + Quality + Performance agents in parallel
        +--> rule dedupe
        +--> Judge semantic grouping + severity gating
        +--> evidence validation
        |
        v
GitHub PR inline comments + summary comment
```

### 上下文策略

| 层级 | 内容 | 状态 |
|------|------|------|
| L1 | PR diff + metadata | 已实现 |
| L2 | 符号定义/短上下文 | 已实现基础能力 |
| L3 | 本地调用图 blast radius | 进行中 |
| L4 | SAST 确定性扫描 | 已有基础模块，按环境降级 |

原则：Prompt 明确区分 `[DIFF]` 与 `[CONTEXT]`，只对 diff 新增行报问题，避免把上下文文件误报成 PR 问题。

---

## 项目结构

```text
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── worker.py            # ARQ worker
│   ├── graph.py             # ReviewGraph 编排
│   ├── cli.py               # CLI 入口
│   ├── auth.py              # GitHub App JWT + installation token
│   ├── config.py            # prism.yaml + env 配置
│   ├── agents/              # Security / Quality / Performance / Judge
│   ├── models/              # Pydantic schema
│   ├── routers/             # webhook / review routes
│   └── services/
│       ├── github.py        # GitHub API 数据获取
│       ├── github_review.py # PR 评论写回
│       ├── llm.py           # DeepSeek/OpenAI-compatible 调用
│       ├── context.py       # 符号上下文
│       ├── repo.py          # shallow clone + 缓存
│       ├── indexer.py       # tree-sitter -> SQLite
│       ├── blast_radius.py  # BFS 调用方查找
│       └── sast.py          # Semgrep wrapper
├── tests/
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```

---

## 配置

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_API_KEY` | 是 | OpenAI-compatible LLM API key |
| `LLM_BASE_URL` | 否 | OpenAI-compatible API endpoint |
| `LLM_MODEL` | 否 | LLM model name |
| `DEEPSEEK_API_KEY` | 兼容旧配置 | `LLM_API_KEY` 未设置时作为 fallback |
| `GITHUB_TOKEN` | CLI 私有仓库时 | Personal access token |
| `GITHUB_APP_ID` | GitHub App 模式 | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App 模式 | GitHub App 私钥内容 |
| `GITHUB_WEBHOOK_SECRET` | GitHub App 模式 | Webhook 签名密钥 |
| `REDIS_URL` | Worker 模式 | Redis 地址，默认 `redis://localhost:6379/0` |

### prism.yaml

```yaml
llm:
  api_key: ""
  base_url: https://api.deepseek.com
  model: deepseek-v4-flash

review:
  budget:
    max_per_review_usd: 0.50
    max_tokens_per_call: 16384
  agents:
    expert_model: deepseek-v4-flash
    judge_model: deepseek-v4-pro
  filters:
    min_confidence: 0.7
    severity_threshold: WARNING
  skip:
    - "*.lock"
    - "*.snap"
    - "*.min.js"
```

---

## 开发验证

```bash
cd backend
.venv/bin/ruff check app/ tests/
.venv/bin/python -m pytest tests/ -v
```

如果本地未安装 mypy，可跳过类型检查；PR 合并前至少需要 lint 和测试通过。

---

## 文档索引

| 文档 | 用途 |
|------|------|
| `CLAUDE.md` | 当前项目事实源、约束、质量契约 |
| `ARCH.md` | 当前架构设计 |
| `PLAN_CALLGRAPH.md` | 调用图跨文件分析计划 |
| `RESEARCH_LOG.md` | 调研与决策对话原始记录 |
| `PLAN.md` | 早期阶段计划，作为历史记录 |
| `PRODUCT.md` | 早期 Web 产品语境，作为历史记录 |
| `AGENT_EVOLUTION.md` | 从 Web 工具转向 GitHub App 的演进记录 |

---

## 开源协议

MIT © 2026 enjoy810
