<div align="center">

<img src="https://img.shields.io/badge/PRism-AI_PR_Review-6366f1?style=for-the-badge" alt="PRism" />

**开源自部署 · 少报但准 · 每条有据可查**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-290_passed-22c55e?style=flat-square)](#开发验证)

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
┌────────────────────────────────────────────────┐
│                  ReviewGraph                   │
│                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Security │  │ Quality  │  │  Perf    │     │  ← 三 Agent 并行
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│       └─────────────┴─────────────┘            │
│                      │                         │
│               ┌──────▼──────┐                  │
│               │  Judge 去重  │                  │  ← 规则去重 + 语义去重
│               └──────┬──────┘                  │
│                      │                         │
│            ┌─────────▼──────────┐              │
│            │  Evidence 验证门控  │              │  ← 行号必须真实存在于 diff
│            └─────────┬──────────┘              │
│                      │                         │
│         ┌────────────▼────────────┐            │
│         │  Caller-Aware 跨文件分析 │            │  ← AST → 调用方 → LLM 验证
│         └────────────┬────────────┘            │
└──────────────────────┼─────────────────────────┘
                       │
                       ▼
         GitHub PR inline comments（blocking / non-blocking 分级）
                   + summary comment
```

---

## 评测表现

在 [CodeReviewBench](https://github.com/kodustech/codereviewbench)（13 个 Python 样本，47 个精确行号标注的 bug）上的实测结果：

| 指标 | 数值 |
|------|------|
| **Precision** | 45.3% |
| **Recall** | 72.3% |
| **F1** | 55.7% |
| TP / FP / FN | 34 / 41 / 13 |

行业对照：纯 LLM 方案精确率约 65%，PRism 召回导向设计在 evidence 验证的约束下，把漏报（FN）控制在 13 个（27.7%）。

**实测案例**（[CollabDoc#1](https://github.com/EnJoy810/CollabDoc/pull/1)）：PR 新增了 `bulkCreateShareLinks` 和 `getDocumentStats` 两个方法，PRism 输出 6 条 finding：

- 🔴 **[blocking]** 权限只检查第一个文档，其余文档可被越权创建分享链接
- 🔴 **[blocking]** `updated_at` 可能为 null，调用 `.toISOString()` 导致 500
- 🟡 **[non-blocking]** N+1 INSERT，应改用 `createMany`
- 🟡 **[non-blocking]** 统计查询未过滤 `is_deleted: false`，与 count 不一致
- 🟡 **[non-blocking]** 全量拉取后在 JS 聚合，应改为 SQL GROUP BY
- 🟡 **[non-blocking]** 密码哈希复用（设计局限，非 bug）

---

## 与竞品对比

|  | **PR-Agent** | **CodeRabbit** | **GitHub Copilot** | **PRism** |
|--|:--:|:--:|:--:|:--:|
| 部署方式 | 云服务 / 自部署 | 云服务 | 云服务 | **开源自部署** |
| 定价 | 按用量 | credits 制，耗尽阻塞 merge | 订阅制 | **免费** |
| 重复评论 | ❌ 高频投诉 #1 | ⚠️ 不可控 | ✅ | ✅ dismiss 旧评论 |
| 幻觉控制 | 依赖模型自评 | ⚠️ 误报率最高 | ✅ 低置信度抑制 | ✅ **程序验证行号** |
| 跨文件分析 | diff-only | 向量语义兜底 | agentic grep | ✅ **tree-sitter 调用图** |
| caller-aware 检测 | ❌ | ❌ | ⚠️ 慢且贵 | ✅ **AST gate + LLM 验证** |
| 动态调用 | ❌ | ❌ | ⚠️ 部分覆盖 | ❌ 诚实声明边界 |
| 可审计 | ⚠️ | ❌ 闭源 | ❌ 闭源 | ✅ **每条 finding 有 evidence** |

> **PR-Agent 最高频投诉**（GitHub issue #2037、#1833、#2402）：每次 push 重复发同样的评论。  
> **CodeRabbit 被横评点名**：highest false-positive rate，credits 耗尽后 PR status check 变红阻塞 merge queue。

---

## 快速开始

### CLI 模式（30 秒上手）

```bash
git clone https://github.com/EnJoy810/PRism.git
cd PRism/backend
pip install -e ".[dev]"
cp .env.example .env
```

编辑 `.env`，填入 LLM API Key：

```bash
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com   # 任何 OpenAI-compatible 接口
LLM_MODEL=deepseek-chat
```

运行：

```bash
python -m app.cli review https://github.com/owner/repo/pull/42

# 私有仓库
python -m app.cli review https://github.com/owner/repo/pull/42 --token ghp_xxx
```

**输出示例：**

```
## PRism Review: feat(documents): add bulk share links

**风险等级**: HIGH | **推荐**: REQUEST_CHANGES | **问题数**: 6

---

### [🔴 blocking] Permission check only on first document in bulk share

- **文件**: `server/src/modules/documents/documents.service.ts:167`
- **描述**: bulkCreateShareLinks 只对 documentIds[0] 检查权限，
  其余文档跳过。拥有任意一个文档 MANAGE 权限的用户可对其他文档
  创建任意权限的分享链接。
- **置信度**: 0.95
- **证据**: `const firstPerm = await this.getEffectivePermission(documentIds[0], userId);`
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

### Blocking / Non-Blocking 分级

每条 finding 带有优先级标签，帮助开发者快速判断哪些必须处理：

- 🔴 **[blocking]**：运行时错误、安全漏洞、接口破坏——合并前必须修复
- 🟡 **[non-blocking]**：性能问题、设计缺陷、不一致——建议处理但不阻塞合并

### Evidence 验证

每条 finding 必须提供 `evidence` 字段，引用 diff 中的具体代码片段。验证逻辑：

1. 检查引用的行号是否在 diff 的新增行范围内
2. 检查引用的代码片段是否真实出现在 diff 中
3. 验证失败 → finding 丢弃，不输出

LLM 的 confidence 是 soft gate，程序验证是 hard gate。

### Caller-Aware 跨文件分析

diff-only 工具看不到"改了函数 A，调用方 B 会不会崩"。PRism 的三层架构：

```
1. AST Gate（tree-sitter 静态分析）
   └─ 判断被修改的函数是否存在"不安全参数用法"
      （如：直接用参数作为 dict key，None 会崩）
        │
        ▼ 通过 gate
2. 1-hop Caller Fetch（SQLite 调用图 BFS depth=1）
   └─ 找到所有直接调用方，取调用处代码片段
        │
        ▼
3. LLM 验证
   └─ 分析每个调用方是否传入了危险值（None、错误类型）
      仅在调用方真实传入危险值时报告
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
- **Subscribe to events**: `Pull requests`

生成私钥（`.pem` 文件），记录 App ID。

### 2. 分享给他人使用

在 App 设置页将 App 改为 **Public**，生成公开安装链接：

```
https://github.com/apps/<your-app-slug>/installations/new
```

对方点击链接，选择自己的仓库安装，自动触发 webhook 到你的服务器。

### 3. 配置环境变量

```bash
# LLM（任何 OpenAI-compatible 接口）
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# GitHub App
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_FILE=/run/secrets/github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Redis
REDIS_URL=redis://localhost:6379/0
```

### 4. 启动服务

```bash
docker compose up --build
```

本地调试时用 [ngrok](https://ngrok.com) 或 [smee.io](https://smee.io) 将 GitHub webhook 转发到 `http://localhost:8000/api/webhook`。

---

## 配置

### prism.yaml

```yaml
llm:
  api_key: ""                        # 优先使用 LLM_API_KEY 环境变量
  base_url: https://api.deepseek.com
  model: deepseek-chat

review:
  budget:
    max_per_review_usd: 0.50         # 单次 review 费用上限
    max_tokens_per_call: 16384
  agents:
    expert_model: deepseek-chat      # 三 Agent 使用的模型
    judge_model: deepseek-reasoner   # Judge 去重使用的模型（推荐推理模型）
  filters:
    min_confidence: 0.7              # 低于此置信度的 finding 过滤
    severity_threshold: WARNING      # INFO 级别默认不输出
  skip:
    - "*.lock"
    - "*.snap"
    - "*.min.js"
    - "dist/**"
    - "vendor/**"
  callgraph_enabled: true            # false 时退化为 diff-only 模式
```

### 完整环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_API_KEY` | ✅ | OpenAI-compatible LLM API key |
| `LLM_BASE_URL` | 否 | API endpoint，默认 DeepSeek |
| `LLM_MODEL` | 否 | 模型名称 |
| `GITHUB_TOKEN` | CLI 私有仓库 | Personal access token |
| `GITHUB_APP_ID` | GitHub App 模式 | App ID |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App 模式 | 私钥内容（或用 `_FILE` 指定路径） |
| `GITHUB_APP_PRIVATE_KEY_FILE` | GitHub App 模式 | 私钥文件路径（推荐） |
| `GITHUB_WEBHOOK_SECRET` | GitHub App 模式 | Webhook 签名密钥 |
| `REDIS_URL` | Worker 模式 | 默认 `redis://localhost:6379/0` |

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
│   │   │   ├── quality.py       # Quality Agent（排除 linter 能报的）
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
│   │       ├── blast_radius.py  # BFS 调用方查找 + caller-aware 分析
│   │       ├── evidence.py      # evidence 行号验证门控
│   │       └── rate_limit.py    # 按 installation 限流
│   ├── tests/                   # 290 个测试
│   ├── Dockerfile
│   └── pyproject.toml
├── eval/
│   ├── run_eval.py              # 评测脚本，支持真实 PR 和 synthetic diff
│   ├── import_codereviewbench.py# CodeReviewBench 数据导入
│   └── prs_codereviewbench_py.yaml  # 13 个 Python 评测样本
├── docker-compose.yml
└── prism.yaml
```

---

## 开发验证

```bash
cd backend

# Lint
.venv/bin/ruff check app/ tests/

# 测试（290 个，约 25s）
.venv/bin/python -m pytest tests/ -v

# 本地 CLI 测试
python -m app.cli review https://github.com/owner/repo/pull/42

# 运行评测（需要 LLM API key）
cd ../eval
python run_eval.py --dataset prs_codereviewbench_py.yaml --out runs/
```

---

## 架构决策

**为什么用调用图而不是向量 RAG？**  
向量搜索的是"语义相似的代码"，不是"实际调用了这个函数的代码"。"谁调用了 `verify_token`"用向量找，会返回所有处理 token 的代码，大量误报。调用图是精确匹配，没有语义噪声。（Greptile 也选择了图而非向量，但用 Neo4j；PRism 用 SQLite，更轻量）

**为什么 caller-aware 需要三层而不是直接 LLM？**  
直接把所有调用方喂给 LLM 有两个问题：(1) token 爆炸，(2) 调用方很多时 LLM 对前几个 caller 更敏感（position bias）。AST Gate 先过滤"函数体本身不存在危险用法"的情况，1-hop fetch 控制 context 深度，最后 LLM 只分析真正可疑的调用方。

**为什么 evidence 用程序验证而不是 LLM 自评？**  
LLM 对幻觉的 confidence 也很高。一个根本不存在的函数调用，LLM 会给 0.9 confidence。程序验证行号是否真实存在于 diff 新增行，是 hard gate，不依赖模型自评。

**为什么 Quality Agent 要排除 linter 能报的？**  
真人 reviewer 不会在 code review 里说"变量名不好"——那是 linter 的工作。Quality Agent 专注 linter 看不到的：逻辑漏洞、边界 case、接口设计问题。减少 FP，提升 SNR。

---

## 路线图

- [x] 三 Agent 并行 + Judge 去重
- [x] Evidence 程序验证（行号 hard gate）
- [x] GitHub App 全链路（webhook → ARQ → worker → PR 评论）
- [x] tree-sitter 调用图跨文件分析
- [x] Caller-aware bug 检测（AST gate + LLM 验证）
- [x] Blocking / non-blocking 分级标注
- [x] Webhook 幂等 + 重复评论去重
- [x] 按 installation 限流
- [x] CodeReviewBench 评测框架（F1 55.7%）
- [ ] Go / Java 跨文件分析（当前支持 Python / JS / TS）
- [ ] Linter + LLM 混合（Bandit/Semgrep 先扫，LLM 补逻辑漏洞）
- [ ] Map-Reduce per-caller 分析（解决多调用方 position bias）

---

## 开源协议

MIT © 2026 [enjoy810](https://github.com/EnJoy810)
