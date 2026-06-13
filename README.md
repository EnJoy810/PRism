<div align="center">
  <h1>🔷 PRism</h1>
  <p><strong>AI 驱动的 Pull Request 代码审查助手</strong></p>
  <p>粘贴 PR 链接，数秒内获得结构化、可执行的 Review 反馈</p>

  <p>
    <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
    <img src="https://img.shields.io/badge/DeepSeek-V4_Flash-4A90D9?style=flat-square" />
    <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
  </p>
</div>

---

## 项目简介

PRism 是一款 AI 辅助代码审查工具，基于 DeepSeek V4 分析 GitHub Pull Request。用户只需粘贴 PR 链接，即可获得严重程度分级的 Review 反馈、PR 级别风险评估和可操作修改建议。

> 多 Agent 架构：3 个专家 Agent（安全/性能/代码规范）并行审查，裁判 Agent 汇总去重降噪。

---

## 核心功能

| 功能 | 描述 |
|------|------|
| **智能上下文获取** | 不止拉取 diff，还获取 PR 元数据、commit 信息和文件列表 |
| **严重程度分级门控** | 确定性三级分类（ERROR / WARNING / INFO），低质量问题默认过滤 |
| **流式 Review 输出** | SSE 实时流式传输，一边分析一边展示思考过程和结果 |
| **误报控制** | System prompt 强制执行 85%+ 置信度阈值，要求每个问题附带具体代码位置和触发场景 |
| **风险评估** | PR 整体风险等级（HIGH / MEDIUM / LOW），高风险文件标注 |
| **合并建议** | 基于 review 结果给出 APPROVE / REQUEST_CHANGES / COMMENT 建议 |

---

## 系统架构

```
┌──────────────────────────────────────────────────────┐
│                      PRism                            │
│                                                        │
│  ┌──────────────┐   REST / SSE   ┌────────────────┐  │
│  │  React SPA   │◄──────────────►│  FastAPI 后端   │  │
│  │              │                │                │  │
│  │  • PR URL    │                │  ┌──────────┐  │  │
│  │  • 文件树    │                │  │  GitHub   │  │  │
│  │  • 流式渲染  │                │  │  Service  │  │  │
│  │  • 问题卡片  │                │  └─────┬────┘  │  │
│  │              │                │        │       │  │
│  └──────────────┘                │  ┌─────▼────┐  │  │
│                                  │  │  LLM     │  │  │
│                                  │  │  Service │  │  │
│                                  │  │ DeepSeek │  │  │
│                                  │  └──────────┘  │  │
│                                  └────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Node.js 20+ 和 pnpm
- Python 3.12+
- [DeepSeek API Key](https://platform.deepseek.com/api_keys)
- GitHub Personal Access Token（访问私有仓库时需要）

### 一键启动

```bash
git clone https://github.com/EnJoy810/PRism.git
cd PRism
bash dev.sh
```

`dev.sh` 会自动创建虚拟环境、安装依赖、从 `.env.example` 复制配置文件。启动后编辑 `backend/.env`，填入 DeepSeek API Key 和 GitHub Token：

```
DEEPSEEK_API_KEY=sk-your_deepseek_api_key
GITHUB_TOKEN=github_pat_your_token
```

重新运行 `bash dev.sh` 即可。

### 手动启动

```bash
# 后端
cd backend
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
pnpm install
pnpm dev
```

API Key 和 GitHub Token 也可在页面右上角 Settings 面板中配置，优先级高于环境变量。

打开 [http://localhost:5173](http://localhost:5173) 使用。

### Docker 一键启动

```bash
docker compose up --build
```

启动 API（8000）+ Worker + Redis 三服务。需在 `backend/.env` 中配置 `DEEPSEEK_API_KEY`。

### GitHub App 自动审查（Webhook 模式）

1. 在 GitHub 上创建 GitHub App：Settings → Developer settings → GitHub Apps → New GitHub App
2. 设置 Webhook URL：`https://your-domain.com/api/webhook`
3. 订阅事件：`Pull requests`、`Issue comments`
4. 生成私钥，在 GitHub App 设置页面安装到目标仓库
5. 配置环境变量：
   ```
   GITHUB_WEBHOOK_SECRET=your_webhook_secret
   GITHUB_TOKEN=ghp_your_pat
   ```
6. 启动 Worker：`python -m app.worker`

Webhook 自动处理 `pull_request.opened/synchronize` 和 `issue_comment`（含 `@prism-bot`）事件。

### LangSmith 可观测性

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_your_key
```

如已安装 `langsmith` SDK，OpenAI 调用自动追踪。graph.py 各阶段耗时日志在 Worker 日志中可见。

---

## 使用方式

1. 在左侧输入框粘贴 GitHub PR 链接（支持 `pull/` 和 `pulls/` 格式）
2. 如需访问私有仓库，在同一输入框下方填入 GitHub Token
3. 点击「开始 AI 审查」，等待流式输出
4. Review 完成后可查看：AI 摘要、风险分析、问题列表（支持按严重程度筛选）、合并建议
5. 结果可导出为 Markdown 报告或一键提交评论到 GitHub PR

---

## API 文档

### `GET /api/pr/meta`

获取 PR 元数据。

**参数：**
- `pr_url` — PR 链接
- `github_token` — （可选）GitHub Token

### `POST /api/review`

分析 PR 并返回结构化 JSON Review 结果。

**请求体：**
```json
{
  "pr_url": "https://github.com/owner/repo/pull/123",
  "github_token": "ghp_...",
  "api_key": "sk-...",
  "model": "deepseek-v4-flash",
  "options": {
    "include_style": false
  }
}
```

**响应：**
```json
{
  "code": "0",
  "data": {
    "summary": "本 PR 对用户鉴权模块进行了重构，整体质量良好。",
    "risk_level": "LOW",
    "issues": [
      {
        "severity": "WARNING",
        "file": "src/auth.ts",
        "line": 42,
        "title": "缺少输入校验",
        "description": "用户 ID 直接用于数据库查询，未做格式校验",
        "suggestion": "使用 Zod 或类似库对 userId 进行格式校验"
      }
    ],
    "stats": { "files_changed": 3, "additions": 120, "deletions": 45 }
  }
}
```

### `POST /api/review/stream`

请求体同上，返回 SSE 流式输出。事件类型：
- `diff` — PR diff 片段 + 元数据
- `thinking` — AI 思考过程（逐 token 推送）
- `result` — 增量结果片段

---

## 技术栈

**前端**
- React 18 + Vite 7 + TypeScript（strict 模式）
- Ant Design 5 + Tailwind CSS 3
- TanStack Query 5 + Zustand 5

**后端**
- FastAPI 0.115 + Python 3.12
- OpenAI SDK（DeepSeek V4 系列，OpenAI 兼容接口）
- httpx 异步调用 GitHub REST API
- Pydantic v2 数据校验

---

## 设计决策

### 为什么选择 DeepSeek V4？

DeepSeek V4 拥有 1M token 上下文窗口（Flash 型号），在代码理解和多文件审查任务上表现出色。使用 OpenAI 兼容接口，迁移成本极低，同时推理成本远低于同级别闭源模型。

### 为什么用确定性门控而不是让 LLM 判断严重程度？

LLM 自行分配严重级别不可靠——模型倾向于过度上报警告。PRism 使用确定性门控：只有当模型能给出具体代码位置和可操作建议时，该问题才通过 ERROR/WARNING 阈值。INFO 级别默认过滤，可通过 `include_style: true` 手动开启。

### 上下文获取策略

| 层级 | 获取内容 | 现状 |
|------|---------|------|
| L1 | 仅 PR diff | 大多数工具止步于此 |
| L2 | diff + 元数据 + 文件列表 | PRism（当前） |
| L3 | L2 + GitHub GraphQL 调用链分析 | PRism（规划中） |

---

## 视频演示

Demo 视频见百度网盘：

> 链接：https://pan.baidu.com/s/1fqYmnMlSW5qCqZ6ln8AFQg
> 提取码：1234

演示内容：
- 输入 GitHub PR 链接并获取 Review 结果
- 流式输出实时渲染效果
- 严重程度分级展示（ERROR / WARNING）
- 风险评估总览与合并建议

---

## 第三方依赖说明

| 依赖 | 用途 | 原创功能 |
|------|------|---------|
| `openai` SDK | 调用 DeepSeek V4 OpenAI 兼容接口 | Severity Gating、ReAct 提示词设计 |
| `httpx` | 异步调用 GitHub REST API | PR 上下文多层级获取策略 |
| `fastapi` | HTTP 服务框架 | SSE 流式输出端点 |
| `@tanstack/react-query` | 服务端状态管理 | — |
| `antd` | UI 组件库 | Review 结果可视化卡片 |
| `zustand` | 前端 UI 状态管理 | — |

---

## 后续规划

- [ ] 通过 GitHub GraphQL 获取调用链上下文（Level 3）
- [ ] PR 历史学习——识别仓库内的重复缺陷模式
- [ ] GitHub Actions 集成，支持 CI 自动 Review
- [ ] 团队规则自定义（`.prism.yml` 配置文件）

---

## 开源协议

MIT © 2026 enjoy810
