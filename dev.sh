#!/usr/bin/env bash
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────
CYAN='\033[0;36m'  GREEN='\033[0;32m'  RED='\033[0;31m'
YELLOW='\033[1;33m'  NC='\033[0m'

FRONTEND_PORT=${FRONTEND_PORT:-4180}
BACKEND_PORT=${BACKEND_PORT:-8100}

PIDS=()

# ── Cleanup ──────────────────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Shutting down…${NC}"

  # Send SIGTERM to every tracked child
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  # Give them 3 s to exit gracefully, then SIGKILL stragglers
  local waited=0
  while (( waited < 3 )); do
    local alive=0
    for pid in "${PIDS[@]}"; do
      kill -0 "$pid" 2>/dev/null && alive=1
    done
    (( alive == 0 )) && break
    sleep 0.5
    (( waited++ )) || true
  done

  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      echo -e "${RED}Force-killing PID $pid${NC}"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done

  # Kill anything still listening on our ports (defensive)
  for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
    lsof -ti :"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
  done

  echo -e "${GREEN}All processes stopped.${NC}"
}

trap cleanup EXIT INT TERM HUP

# ── Pre-flight checks ───────────────────────────────────────────────
check_port() {
  if lsof -ti :"$1" &>/dev/null; then
    echo -e "${RED}Port $1 is already in use.${NC}"
    echo "  $(lsof -ti :"$1" | head -1 | xargs ps -p 2>/dev/null | tail -1)"
    exit 1
  fi
}

check_port "$FRONTEND_PORT"
check_port "$BACKEND_PORT"

if [[ ! -d frontend/node_modules ]]; then
  echo -e "${CYAN}Installing frontend dependencies…${NC}"
  npm --prefix frontend install
fi

if [[ ! -f backend/venv/bin/python ]]; then
  echo -e "${RED}Backend venv not found at backend/venv.${NC}"
  echo "Create it with:  python3 -m venv backend/venv && backend/venv/bin/pip install -e backend"
  exit 1
fi

# ── Start services ───────────────────────────────────────────────────
echo -e "${CYAN}Starting backend  → http://localhost:${BACKEND_PORT}${NC}"
./backend/venv/bin/python -m uvicorn app.main:app \
  --app-dir backend --reload --port "$BACKEND_PORT" &
PIDS+=($!)

echo -e "${CYAN}Starting frontend → http://localhost:${FRONTEND_PORT}${NC}"
npm --prefix frontend run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" &
PIDS+=($!)

echo -e "${GREEN}Both services running. Press Ctrl+C to stop.${NC}"

# ── Wait for any child to exit ───────────────────────────────────────
# If one crashes the trap fires and cleans up the other.
wait -n "${PIDS[@]}" 2>/dev/null || true
echo -e "${YELLOW}A process exited unexpectedly — cleaning up.${NC}"
