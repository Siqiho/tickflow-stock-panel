#!/usr/bin/env bash
# one-trading — 一键启动前后端
#
# 用法:
#   ./dev.sh                          # 默认 backend:3018  frontend:3011
#   BACKEND_PORT=8000 ./dev.sh        # 改后端端口
#   FRONTEND_PORT=5173 ./dev.sh       # 改前端端口
#
# Ctrl-C 同时关闭两端。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT="${BACKEND_PORT:-3018}"
FRONTEND_PORT="${FRONTEND_PORT:-3011}"

dotenv_value() {
  local key="$1"
  [ -f "$ROOT/.env" ] || return 0
  awk -v wanted="$key" '
    index($0, wanted "=") == 1 {
      value = substr($0, length(wanted) + 2)
      sub(/[[:space:]]+#.*/, "", value)
      gsub(/^[[:space:]\047\"]+|[[:space:]\047\"]+$/, "", value)
      print value
      exit
    }
  ' "$ROOT/.env"
}

HERMES_RUNTIME_ENABLED="${ONE_TRADING_HERMES_RUNTIME_ENABLED:-$(dotenv_value ONE_TRADING_HERMES_RUNTIME_ENABLED)}"
HERMES_RUNTIME_ENABLED="${HERMES_RUNTIME_ENABLED:-false}"
HERMES_BASE_URL="${ONE_TRADING_HERMES_BASE_URL:-$(dotenv_value ONE_TRADING_HERMES_BASE_URL)}"
HERMES_BASE_URL="${HERMES_BASE_URL:-http://127.0.0.1:8651}"
HERMES_PORT="$HERMES_BASE_URL"
HERMES_PORT="${HERMES_PORT##*:}"
HERMES_PORT="${HERMES_PORT%/}"
if ! [[ "$HERMES_PORT" =~ ^[0-9]+$ ]] || [ "$HERMES_PORT" -lt 1 ] || [ "$HERMES_PORT" -gt 65535 ]; then
  echo "[dev] Hermes 端口无效: $HERMES_BASE_URL" >&2
  exit 1
fi

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
GRAY='\033[0;90m'
NC='\033[0m'

info()  { echo -e "${GRAY}[dev]${NC} $*"; }
ok()    { echo -e "${GREEN}[dev]${NC} $*"; }
warn()  { echo -e "${YELLOW}[dev]${NC} $*"; }
err()   { echo -e "${RED}[dev]${NC} $*" >&2; }

# ===== 1. 依赖检查 =====
require_cmd() {
  local cmd="$1" hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "$cmd 未安装"
    echo "       安装方式:$hint"
    exit 1
  fi
}

require_cmd uv   "curl -LsSf https://astral.sh/uv/install.sh | sh"
require_cmd pnpm "npm i -g pnpm   或   corepack enable && corepack prepare pnpm@9 --activate"

# ===== 2. 端口占用检查 —— 占用就直接 kill =====
free_port() {
  local name="$1" port="$2"
  local pids
  pids=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -z "$pids" ]; then
    return 0
  fi
  warn "端口 $port($name)被占用,kill 现有进程 PID: $(echo "$pids" | xargs)"
  # 先 TERM
  echo "$pids" | xargs kill 2>/dev/null || true
  sleep 1
  # 还活着就 KILL
  pids=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    warn "TERM 没杀掉,改用 KILL -9"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
  # 再确认一次
  pids=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    err "端口 $port 仍被占用 — kill 失败。请手动处理:lsof -i :$port"
    exit 1
  fi
  ok "端口 $port 已释放"
}
free_port backend  "$BACKEND_PORT"
free_port frontend "$FRONTEND_PORT"
if [ "$HERMES_RUNTIME_ENABLED" = "true" ]; then
  free_port hermes "$HERMES_PORT"
fi

# ===== 3. 首次依赖安装 =====
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  info "后端首次启动 — 安装 Python 依赖(约 1-2 分钟)..."
  ( cd "$BACKEND_DIR" && uv sync )
  ok "后端依赖装好了"
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  info "前端首次启动 — 安装 Node 依赖..."
  ( cd "$FRONTEND_DIR" && pnpm install )
  ok "前端依赖装好了"
fi

# ===== 4. 启动 + 日志前缀 =====
PIDS=()
CLEANING_UP=0

cleanup() {
  local exit_code="${1:-0}"
  if [ "$CLEANING_UP" -eq 1 ]; then
    exit "$exit_code"
  fi
  CLEANING_UP=1
  echo
  info "关闭服务..."
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  # 等子进程退出,避免孤儿
  wait 2>/dev/null || true
  ok "已退出"
  exit "$exit_code"
}
trap 'cleanup 0' INT TERM

# 用 awk 加前缀(macOS sed 没有 -u line-buffered,改用 awk + fflush 兼容)
prefix_awk() {
  awk -v p="$1" '{ print p $0; fflush() }'
}

echo
echo -e "${BLUE}╭──────────────────────────────────────────────╮${NC}"
echo -e "${BLUE}│${NC}  ${GREEN}one-trading${NC}                                 ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}                                              ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  backend   ${YELLOW}http://localhost:$BACKEND_PORT${NC}          ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  frontend  ${YELLOW}http://localhost:$FRONTEND_PORT${NC}          ${BLUE}│${NC}"
if [ "$HERMES_RUNTIME_ENABLED" = "true" ]; then
  echo -e "${BLUE}│${NC}  hermes    ${YELLOW}http://127.0.0.1:$HERMES_PORT${NC}          ${BLUE}│${NC}"
fi
echo -e "${BLUE}│${NC}                                              ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  Ctrl-C 同时关闭两端                          ${BLUE}│${NC}"
echo -e "${BLUE}╰──────────────────────────────────────────────╯${NC}"
echo

if [ "$HERMES_RUNTIME_ENABLED" = "true" ]; then
  (
    cd "$BACKEND_DIR"
    exec "$BACKEND_DIR/.venv/bin/python" scripts/start_local_hermes_gateway.py
  ) > >(prefix_awk "$(printf "${YELLOW}[hermes  ]${NC} ")") 2>&1 &
  PIDS+=("$!")

  info "等待 Hermes multiplex gateway 就绪..."
  hermes_ready=0
  for _attempt in $(seq 1 180); do
    if curl -fsS "http://127.0.0.1:$HERMES_PORT/health" >/dev/null 2>&1; then
      hermes_ready=1
      break
    fi
    sleep 0.25
  done
  if [ "$hermes_ready" -ne 1 ]; then
    err "Hermes multiplex gateway 启动超时"
    cleanup 1
  fi
  ok "Hermes multiplex gateway 已就绪"
fi

(
  cd "$BACKEND_DIR"
  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" 2>&1 \
    | prefix_awk "$(printf "${BLUE}[backend ]${NC} ")"
) &
PIDS+=("$!")

(
  cd "$FRONTEND_DIR"
  pnpm dev --host 0.0.0.0 --port "$FRONTEND_PORT" 2>&1 \
    | prefix_awk "$(printf "${GREEN}[frontend]${NC} ")"
) &
PIDS+=("$!")

# macOS 自带 Bash 3.2 没有 `wait -n`。轮询监督所有子进程，任一
# 退出都立即停止其余运行面，避免 Hermes 已掉线而页面仍假装正常。
while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" 2>/dev/null || true
      warn "其中一个进程退出,正在关闭其余服务..."
      cleanup 1
    fi
  done
  sleep 1
done
