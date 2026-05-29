#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ── 颜色 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[PRism]${NC} $1"; }
warn() { echo -e "${YELLOW}[PRism]${NC} $1"; }
err()  { echo -e "${RED}[PRism]${NC} $1"; }

# ── 环境检查 ─────────────────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  warn ".env 不存在，从 .env.example 复制..."
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  err "请先填写 $BACKEND/.env 中的 DEEPSEEK_API_KEY，然后重新运行"
  exit 1
fi

if grep -q "your_deepseek_api_key_here" "$BACKEND/.env"; then
  err "DEEPSEEK_API_KEY 尚未填写，请编辑 $BACKEND/.env"
  exit 1
fi

# ── Python 虚拟环境 ──────────────────────────────────
if [ ! -d "$BACKEND/.venv" ]; then
  log "创建 Python 虚拟环境..."
  python3 -m venv "$BACKEND/.venv"
  log "安装后端依赖..."
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

# ── 前端依赖 ─────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  log "安装前端依赖..."
  (cd "$FRONTEND" && pnpm install --silent)
fi

# ── 启动 ─────────────────────────────────────────────
log "启动后端 http://localhost:8000 ..."
"$BACKEND/.venv/bin/uvicorn" app.main:app --reload --port 8000 --app-dir "$BACKEND" &
BACKEND_PID=$!

log "启动前端 http://localhost:5173 ..."
(cd "$FRONTEND" && pnpm dev) &
FRONTEND_PID=$!

log "PRism 已启动（Ctrl+C 退出）"
log "前端: http://localhost:5173"
log "后端: http://localhost:8000/docs"

# Ctrl+C 同时关闭两个进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; log '已停止'" INT TERM
wait
