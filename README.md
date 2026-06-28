<div align="center">

<img src="https://img.shields.io/badge/PRism-AI_PR_Review-6366f1?style=for-the-badge" alt="PRism" />

**开源自部署 · 少报但准 · 每条有据可查**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-239_passed-22c55e?style=flat-square)](#开发验证)

[快速开始](#快速开始) · [工作原理](#工作原理) · [与竞品对比](#与竞品对比) · [部署](#github-app-自动审查) · [配置](#配置)

</div>

---

## 是什么

PRism 是一个开源自部署的 AI PR 审查工具。安装到 GitHub 仓库后，每次 PR 打开或更新时自动运行，把审查结果以 inline comment + summary comment 的形式写回 PR 评论区。

**核心设计原则：宁可漏报，不能误报。**

每条 finding 必须引用 diff 中真实存在的代码行作为证据，程序验证后才输出。没有证据的 finding 直接丢弃。

```
PR opened / synchronized
        │
        ▼
┌───────────────────────────────────────────┐
│              ReviewGraph                  │
│                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Security │ │ Quality  │ │  Perf    │  │  ← 三 Agent 并行
│  └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │             │            │        │
│       └─────────────┴────────────┘        │
│                     │                     │
│              ┌──────▼──────┐              │
│              │  Judge 去重  │              │  ← 规则去重 + 语义去重
│              └──────┬──────┘              │
│                     │                     │
│           ┌─────────▼──────────┐          │
│           │  Evidence 验证门控  │          │  ← 行号必须真实存在
│           └─────────┬──────────┘          │
│                     │                     │
│         ┌───────────▼───────────┐         │
│         │   Blast Radius 补充   │         │  ← 跨文件调用方分析
│         └───────────┬───────────┘         │
└─────────────────────┼─────────────────────┘
                      │
                      ▼
          GitHub PR inline comments
              + summary comment
```

---

## 与竞品对比

|  | **PR-Agent** | **CodeRabbit** | **GitHub Copilot** | **PRism** |
|--|:--:|:--:|:--:|:--:|
| 部署方式 | 云服务 / 自部署 | 云服务 | 云服务 | **开源自部署** |
| 定价 | 按用量 | credits 制，耗尽阻塞 merge | 订阅制 | **免费** |
| 重复评论 | ❌ 高频投诉 #1 | ⚠️ 不可控 | ✅ | ✅ dismiss 旧评论 |
| 幻觉控制 | 依赖模型自评 | ⚠️ 误报率最高 | ✅ 低置信度抑制 | ✅ **程序验证行号** |
| 跨文件分析 | diff-only | 向量语义兜底 | agentic grep | ✅ **tree-sitter 调用图** |
| 动态调用 | ❌ | ❌ | ⚠️ 慢且贵 | ❌ 诚实声明边界 |
| 可审计 | ⚠️ | ❌ 闭源 | ❌ 闭源 | ✅ **每条 finding 有 evidence** |

> **PR-Agent 最高频投诉**（GitHub issue #2037、#1833、#2402）：每次 push 重复发同样的评论。  
> **CodeRabbit 被横评点名**：highest false-positive rate，credits 耗尽后 PR status check 变红阻塞 merge queue。

---

## 快速开始

### CLI 模式（30 秒上手）

```bash
git clone https://github.com/EnJoy810/PRism.git
cd PRism/backend
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填入 LLM API Key：

```bash
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com   # 任何 OpenAI-compatible 接口
LLM_MODEL=deepseek-v4-flash
```

运行：

```bash
python -m app.cli review https://github.com/owner/repo/pull/42

# 私有仓库
python -m app.cli review https://github.com/owner/repo/pull/42 --token ghp_xxx
```

**输出示例：**

```
## PRism Review: fix: update token validation logic

**风险等级**: HIGH
**推荐**: REQUEST_CHANGES
**文件变更**: 3 | +47 -12
**问题数**: 2

### 1. [🔴 ERROR] verify_token 新增 strict 参数无默认值，破坏所有调用方

- **文件**: `auth/token.py:23`
- **描述**: 函数签名从 verify_token(token, user_id) 改为
  verify_token(token, user_id, strict)，strict 无默认值。
  b.py:6 和 c.py:14 的调用方未更新，运行时 TypeError。
- **置信度**: 0.95
- **证据**: `def verify_token(token: str, user_id: int, strict: bool) -> bool:`
```

### Docker 模式（GitHub App 自动审查）

```bash
cp backend/.env.example backend/.env
# 填入完整配置（见下方 GitHub App 配置节）
docker compose up --build
```

启动三个服务：FastAPI webhook server（:8000）、ARQ worker、Redis。

---

## 工作原理

### 三 Agent 并行

每次 PR 审查启动三个独立 Agent，各有侧重：

| Agent | 关注点 | 典型 finding |
|-------|--------|-------------|
| **Security** | 权限绕过、注入、认证削弱 | 删除了校验逻辑、新增了未过滤的输入路径 |
| **Quality** | 接口破坏、空指针、行为回归 | 函数签名变更导致调用方 TypeError |
| **Performance** | N+1 查询、内存泄漏、阻塞 IO | 循环内新增了 DB 查询 |

三 Agent 输出合并后经过两轮去重：**规则去重**（相同文件+行号+类别）→ **Judge 语义去重**（LLM 判断描述相似的 finding 是否是同一个问题）。

### Evidence 验证

每条 finding 必须提供 `evidence` 字段，引用 diff 中的具体代码片段。验证逻辑：

1. 检查引用的行号是否在 diff 的新增行范围内
2. 检查引用的代码片段是否真实出现在 diff 中
3. 验证失败 → finding 丢弃，不输出

这是 PRism 误报率控制的核心机制。LLM 的 confidence 是 soft gate，程序验证是 hard gate。

### 跨文件调用图（Blast Radius）

```
PR diff 中识别被修改的函数
        │
        ▼
tree-sitter 解析仓库 Python/JS/TS 文件
        │
        ▼
SQLite 存储调用关系（nodes + edges）
        │
        ▼
BFS depth=2 找到所有调用方
        │
        ▼
调用方代码作为 [CROSS-FILE CONTEXT] 注入 Agent prompt
        │
        ▼
Agent 分析调用方是否因接口变更受影响
```

clone 失败或 index 失败时自动降级为 diff-only，主链路不依赖跨文件分析成功。

---

## GitHub App 自动审查

### 1. 创建 GitHub App

进入 GitHub **Settings → Developer settings → GitHub Apps → New GitHub App**：

- **Webhook URL**: `https://your-domain.com/api/webhook`
- **Webhook secret**: 生成一个随机字符串，稍后填入配置
- **Repository permissions**:
  - Contents: `Read-only`
  - Metadata: `Read-only`
  - Pull requests: `Read and write`
  - Issues: `Read and write`（用于权限错误通知）
- **Subscribe to events**: `Pull requests`、`Issue comments`

生成私钥（`.pem` 文件），记录 App ID。

### 2. 配置环境变量

```bash
# LLM（任何 OpenAI-compatible 接口）
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash

# GitHub App
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_FILE=/run/secrets/github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Redis
REDIS_URL=redis://localhost:6379/0
```

### 3. 启动服务

```bash
docker compose up --build
```

本地调试时用 [ngrok](https://ngrok.com) 或 [smee.io](https://smee.io) 将 GitHub webhook 转发到 `http://localhost:8000/api/webhook`。

### 4. 安装到仓库

在 GitHub App 页面 → Install App → 选择目标仓库。

安装完成后，目标仓库的每次 PR `opened` 或 `synchronize` 事件会自动触发审查。

---

## 配置

### 完整环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_API_KEY` | ✅ | OpenAI-compatible LLM API key |
| `LLM_BASE_URL` | 否 | API endpoint，默认 DeepSeek |
| `LLM_MODEL` | 否 | 模型名称，默认 `deepseek-v4-flash` |
| `GITHUB_TOKEN` | CLI 私有仓库 | Personal access token |
| `GITHUB_APP_ID` | GitHub App 模式 | App ID |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App 模式 | 私钥内容（或用 `_FILE` 指定路径） |
| `GITHUB_APP_PRIVATE_KEY_FILE` | GitHub App 模式 | 私钥文件路径（推荐） |
| `GITHUB_WEBHOOK_SECRET` | GitHub App 模式 | Webhook 签名密钥 |
| `REDIS_URL` | Worker 模式 | 默认 `redis://localhost:6379/0` |

### prism.yaml

```yaml
llm:
  api_key: ""                        # 优先使用 LLM_API_KEY 环境变量
  base_url: https://api.deepseek.com
  model: deepseek-v4-flash

review:
  budget:
    max_per_review_usd: 0.50         # 单次 review 费用上限
    max_tokens_per_call: 16384
  agents:
    expert_model: deepseek-v4-flash  # 三 Agent 使用的模型
    judge_model: deepseek-v4-pro     # Judge 去重使用的模型
  filters:
    min_confidence: 0.7              # 低于此置信度的 finding 过滤
    severity_threshold: WARNING      # INFO 级别默认不输出
  skip:
    - "*.lock"
    - "*.snap"
    - "*.min.js"
    - "dist/**"
    - "vendor/**"
```

---

## 项目结构

```
PRism/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口，health check + webhook 路由
│   │   ├── worker.py            # ARQ worker，消费审查队列
│   │   ├── graph.py             # ReviewGraph，编排全流程
│   │   ├── cli.py               # CLI 入口
│   │   ├── auth.py              # GitHub App JWT + installation token
│   │   ├── config.py            # prism.yaml + 环境变量配置
│   │   ├── agents/
│   │   │   ├── security.py      # Security Agent
│   │   │   ├── quality.py       # Quality Agent
│   │   │   ├── performance.py   # Performance Agent
│   │   │   ├── judge.py         # Judge 去重 Agent
│   │   │   └── base.py          # BaseAgent，LLM 调用 + response 解析
│   │   ├── models/              # Pydantic schema
│   │   ├── routers/
│   │   │   └── webhook.py       # webhook 入口，签名验证 + 幂等去重
│   │   └── services/
│   │       ├── github.py        # GitHub API 数据获取
│   │       ├── github_review.py # PR 评论写回，dismiss 旧评论
│   │       ├── llm.py           # OpenAI-compatible 调用，重试 + token 预算
│   │       ├── context.py       # 符号定义检索
│   │       ├── repo.py          # shallow clone + LRU 缓存
│   │       ├── indexer.py       # tree-sitter → SQLite 调用图
│   │       ├── blast_radius.py  # BFS 调用方查找
│   │       └── sast.py          # Semgrep wrapper（可选）
│   ├── tests/                   # 239 个测试
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
└── prism.yaml
```

---

## 开发验证

```bash
cd backend

# Lint
.venv/bin/ruff check app/ tests/

# 测试（239 个，约 20s）
.venv/bin/python -m pytest tests/ -v

# 本地 CLI 测试
python -m app.cli review https://github.com/owner/repo/pull/42
```

---

## 架构决策

几个关键的技术选型，每个都有具体依据：

**为什么用调用图而不是向量 RAG？**  
向量搜索的是"语义相似的代码"，不是"实际调用了这个函数的代码"。"谁调用了 `verify_token`"用向量找，会返回所有处理 token 的代码，大量误报。调用图是精确匹配，没有语义噪声。（参考：Greptile 也选择了图而非向量，但用 Neo4j；PRism 用 SQLite，更轻量）

**为什么不用 LSP？**  
LSP 启动慢（需要热身）、有状态（难并发）、多语言要启多个进程。工程成本远超收益，当前场景 tree-sitter 静态解析够用。

**为什么 evidence 用程序验证而不是 LLM 自评？**  
LLM 对幻觉的 confidence 也很高。一个根本不存在的函数调用，LLM 会给 0.9 confidence。程序验证行号是否真实存在于 diff 新增行，是 hard gate，不依赖模型自评。

**为什么只做 BFS depth=2？**  
"When More Retrieval Hurts"（SWE-PRBench）：上下文越多，模型表现反而更差。depth=3 的 token 量可能超出 context 上限且噪声指数级增加。接受 depth=2 的边界，不假装能解决更深的链路。

---

## 路线图

- [x] 三 Agent 并行 + Judge 去重
- [x] Evidence 程序验证
- [x] GitHub App 全链路（webhook → ARQ → worker → PR 评论）
- [x] tree-sitter 调用图跨文件分析
- [x] Webhook 幂等 + 重复评论去重
- [x] post_comment 重试 + 失败 fallback
- [ ] Go / Java 跨文件分析（当前支持 Python / JS / TS）
- [ ] Linter + LLM 混合（Bandit/Semgrep 先扫，LLM 补逻辑漏洞）
- [ ] Map-Reduce per-caller 分析（解决多调用方 position bias）
- [ ] 多语言支持（Go、Java）

---

## 开源协议

MIT © 2026 [enjoy810](https://github.com/EnJoy810)

<!-- test: trigger prism self-review -->

 
 
 
x
x
x
