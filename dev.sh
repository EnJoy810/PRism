#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"

# ── 颜色 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[PRism]${NC} $1"; }
warn() { echo -e "${YELLOW}[PRism]${NC} $1"; }
err()  { echo -e "${RED}[PRism]${NC} $1"; }

# ── 环境检查 ─────────────────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  log "创建 .env 配置..."
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  err "请先填写 $BACKEND/.env 中的 DEEPSEEK_API_KEY，然后重新运行"
  exit 1
fi

if grep -Eq "^(LLM_API_KEY=your_llm_api_key|DEEPSEEK_API_KEY=sk-your_)" "$BACKEND/.env"; then
  err "LLM_API_KEY 或 DEEPSEEK_API_KEY 尚未填写，请编辑 $BACKEND/.env"
  exit 1
fi

# ── Python 虚拟环境 ──────────────────────────────────
if [ ! -d "$BACKEND/.venv" ]; then
  log "创建 Python 虚拟环境..."
  python3 -m venv "$BACKEND/.venv"
  log "安装后端依赖..."
  "$BACKEND/.venv/bin/pip" install -q -e ".[dev]"
fi

# ── 启动后端 ─────────────────────────────────────────
log "启动后端 http://localhost:8000 ..."
"$BACKEND/.venv/bin/uvicorn" app.main:app --reload --port 8000 --app-dir "$BACKEND"

# 如需同时启动 Worker（消费 Webhook 队列），另开终端运行：
# cd backend && python -m app.worker
