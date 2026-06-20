# PRism 调用图跨文件分析 — 收尾计划

> 目标：在现有 diff-only review 基础上，加入 tree-sitter + SQLite 调用图，让 AI 能看到被改函数的调用方，从而发现跨文件 bug。
>
> **主链路不依赖本功能**：调用图是增强，任何阶段失败都静默降级回 diff-only，不影响基本 review 流程。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| `repo.py` | 已存在 | shallow clone + 缓存基础能力已落地 |
| `indexer.py` | 已存在 | tree-sitter -> SQLite 基础能力已落地 |
| `blast_radius.py` | 已存在 | BFS depth=2 + token budget 基础能力已落地 |
| `graph.py` 集成 | 已接入 | 调用图、SAST、verification 与 Agent 并行准备 |
| 真实 PR 评测 | 未完成 | 需用 20 个真实 PR 建立 precision/SNR 基线 |

后续执行时以实际代码状态为准，不重复实现已存在模块；重点放在最终门禁、真实 PR 评测和部署验证。

---

## 整体架构

```
PR webhook 触发
    │
    ├─ [并行] diff-only review（已有，不改）
    │
    └─ [并行] 调用图准备
           │
           ├─ 1. repo.py：shallow clone head.sha → 本地缓存
           ├─ 2. indexer.py：tree-sitter 解析 → SQLite 调用图
           └─ 3. blast_radius.py：BFS 找调用方
                  │
                  └─ 4. graph.py：把 blast radius 结果注入 agent_context
```

---

## 第一阶段：调用图（PR 1-5）

### PR 1：依赖安装 + 基础配置

`backend/pyproject.toml` 新增：
```toml
"tree-sitter>=0.23.0",
"tree-sitter-python>=0.23.0",
"tree-sitter-javascript>=0.23.0",
"tree-sitter-typescript>=0.23.0",
```

验证：`python -c "import tree_sitter; import tree_sitter_python; print('ok')"`

### PR 2：repo.py — 仓库克隆与缓存

新建 `backend/app/services/repo.py`。shallow clone PR 的 head commit，LRU 淘汰，双重检查锁。token 不出现在日志。失败返回 None，调用方降级。

新增 `backend/tests/test_repo.py`。

### PR 3：indexer.py — tree-sitter 调用图构建

新建 `backend/app/services/indexer.py`。扫描本地仓库，解析 Python/JS/TS 文件，写入 SQLite（nodes + edges 表）。增量更新（file_hash 不变跳过）。跳过 node_modules/vendor/dist/test 文件。

新增 `backend/tests/test_indexer.py`。

### PR 4：blast_radius.py — BFS 调用方查找

新建 `backend/app/services/blast_radius.py`。给定被改函数名 BFS depth=2 找调用方，token budget ≤ diff 的 50%，visited set 防循环。

新增 `backend/tests/test_blast_radius.py`。

### PR 5：graph.py 集成

修改 `backend/app/graph.py` 和 `backend/app/services/github.py`。并行启动调用图准备，blast radius 结果注入 agent_context，prompt 加 `[CROSS-FILE CONTEXT]` 段落。

### 各 PR 验收

| PR | 通过条件 |
|----|---------|
| PR 1 | `python -c "import tree_sitter_python"` 无报错 |
| PR 2 | `pytest tests/test_repo.py` 全绿 |
| PR 3 | `pytest tests/test_indexer.py` 全绿 |
| PR 4 | `pytest tests/test_blast_radius.py` 全绿 |
| PR 5 | `pytest tests/ -v` 全绿；CLI 日志有 blast radius 输出 |

---

## 评测：建立 SNR 基线

第一阶段完成后做，不跳过。找 20 个真实 PR（选不同仓库），用 CLI 跑 PRism，逐条标注：

| 分类 | 含义 |
|------|------|
| 真 bug | 确实有问题，不改会出事 |
| 有用建议 | 重构、可读性提升 |
| 噪声 | 没错但没价值（变量改名、加空行） |
| 误报 | 完全说错了 |

算 precision/recall/SNR。结果决定第二阶段做什么——如果 precision 已经 > 80%，优先级调高召回率；如果 precision < 60%，优先补 linter。

---

## 第二阶段：最终发布门禁 + 真实评测

已完成的主链路是 `Scope -> Investigate -> Gate -> Comment`：先圈范围，再并行调查，最后统一门禁，只把少量有证据的问题发出去。

### 为什么做

真实用户不会容忍 AI 在 PR 里乱说。调用图、SAST、verification 都只是帮 AI 查；最终能不能评论，必须由程序门禁决定。

### 已落地

- SAST findings 直接进 Judge 输入，LLM Agent 全失败时仍可继续输出确定性 finding
- 大 diff 按 token 预算分批，避免单次超过 `max_tokens_per_call`
- Judge evidence 必须匹配 diff 新增行
- Judge 后还有最终发布门禁：过滤无 evidence、非新增行、INFO、重复 finding

### 验证

```bash
cd backend
pytest tests/test_sast.py tests/test_blast_radius.py tests/test_indexer.py tests/test_graph.py tests/test_judge.py -q
ruff check app/ tests/
```

---

## 文件变更汇总

| 文件 | 操作 |
|------|------|
| `backend/pyproject.toml` | 修改（加依赖） |
| `backend/app/services/repo.py` | 新建 |
| `backend/tests/test_repo.py` | 新建 |
| `backend/app/services/indexer.py` | 新建 |
| `backend/tests/test_indexer.py` | 新建 |
| `backend/app/services/blast_radius.py` | 新建 |
| `backend/tests/test_blast_radius.py` | 新建 |
| `backend/app/graph.py` | 修改 |
| `backend/app/services/github.py` | 修改（加 head_sha） |
| `backend/app/agents/*.py` | 修改（blast_radius prompt + linter 集成） |
| `backend/app/services/sast.py` | 新建 |

---

## 已知边界（不修复，接受）

- 动态调用（Python `getattr`，JS Proxy）：静态分析追不到，不做 false claim
- 跨语言调用（Python 调 JS）：不支持
- Go 语言：本期不加 tree-sitter-go
- 超大仓库（>1GB）：clone 超时 120s 后降级，不影响基本 review
- 匿名函数（`lambda`，`() => {}`）：部分能捕获，部分追不到，接受
- 评测标注依赖人工，不在 pipeline 里自动化
