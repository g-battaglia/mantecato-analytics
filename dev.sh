#!/usr/bin/env bash
set -eo pipefail

# ── Colours ──────────────────────────────────────────────────────────
CYAN=$'\033[0;36m'  GREEN=$'\033[0;32m'  RED=$'\033[0;31m'
YELLOW=$'\033[1;33m'  BOLD=$'\033[1m'  NC=$'\033[0m'

FRONTEND_PORT=${FRONTEND_PORT:-4180}
BACKEND_PORT=${BACKEND_PORT:-8100}

# ── Help ─────────────────────────────────────────────────────────────
do_help() {
  cat <<EOF
${BOLD}Usage:${NC}  ./dev.sh <command>

${BOLD}Commands:${NC}
  start        Start frontend (Vite) and backend (FastAPI) dev servers
  stop         Kill any processes on ports $FRONTEND_PORT / $BACKEND_PORT
  help, -h     Show this help

${BOLD}Environment:${NC}
  FRONTEND_PORT   Frontend port  (default: 4180)
  BACKEND_PORT    Backend port   (default: 8100)

${BOLD}Examples:${NC}
  ./dev.sh start                      # avvia tutto
  ./dev.sh stop                       # ferma tutto
  BACKEND_PORT=9000 ./dev.sh start    # backend su porta custom
EOF
}

# ── Stop ─────────────────────────────────────────────────────────────
do_stop() {
  local found=0
  for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
      found=1
      printf "%bKilling processes on port %s:%b %s\n" "$YELLOW" "$port" "$NC" "$pids"
      echo "$pids" | xargs kill -TERM 2>/dev/null || true
    fi
  done

  if (( found )); then
    sleep 1
    for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
      local pids
      pids=$(lsof -ti :"$port" 2>/dev/null || true)
      if [[ -n "$pids" ]]; then
        printf "%bForce-killing on port %s:%b %s\n" "$RED" "$port" "$NC" "$pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
      fi
    done
    printf "%bStopped.%b\n" "$GREEN" "$NC"
  else
    printf "%bNothing running on ports %s / %s.%b\n" "$GREEN" "$FRONTEND_PORT" "$BACKEND_PORT" "$NC"
  fi
}

# ── Start ────────────────────────────────────────────────────────────
do_start() {
  PIDS=()

  cleanup() {
    printf "\n%bShutting down…%b\n" "$YELLOW" "$NC"

    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
      kill -TERM "$pid" 2>/dev/null || true
    done

    local waited=0
    while (( waited < 6 )); do
      local alive=0
      for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
        kill -0 "$pid" 2>/dev/null && alive=1
      done
      (( alive == 0 )) && break
      sleep 0.5
      (( waited++ )) || true
    done

    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
      if kill -0 "$pid" 2>/dev/null; then
        printf "%bForce-killing PID %s%b\n" "$RED" "$pid" "$NC"
        kill -9 "$pid" 2>/dev/null || true
      fi
    done

    for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
      lsof -ti :"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
    done

    printf "%bAll processes stopped.%b\n" "$GREEN" "$NC"
  }

  trap cleanup EXIT INT TERM HUP

  # Pre-flight
  local port_busy=0
  for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
    if lsof -ti :"$port" &>/dev/null; then
      printf "%bPort %s is already in use.%b\n" "$RED" "$port" "$NC"
      port_busy=1
    fi
  done
  if (( port_busy )); then
    printf "%bRun %b./dev.sh stop%b first to free the ports.%b\n" "$YELLOW" "$CYAN" "$YELLOW" "$NC"
    exit 1
  fi

  if [[ ! -d frontend/node_modules ]]; then
    printf "%bInstalling frontend dependencies…%b\n" "$CYAN" "$NC"
    npm --prefix frontend install
  fi

  if [[ ! -f backend/venv/bin/python ]]; then
    printf "%bBackend venv not found at backend/venv.%b\n" "$RED" "$NC"
    echo "Create it with:  python3 -m venv backend/venv && backend/venv/bin/pip install -e backend"
    exit 1
  fi

  # Launch
  printf "%bStarting backend  → http://localhost:%s%b\n" "$CYAN" "$BACKEND_PORT" "$NC"
  ./backend/venv/bin/python -m uvicorn app.main:app \
    --app-dir backend --reload --port "$BACKEND_PORT" &
  PIDS+=($!)

  printf "%bStarting frontend → http://localhost:%s%b\n" "$CYAN" "$FRONTEND_PORT" "$NC"
  npm --prefix frontend run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" &
  PIDS+=($!)

  printf "%bBoth services running. Press Ctrl+C to stop.%b\n" "$GREEN" "$NC"

  wait -n "${PIDS[@]}" 2>/dev/null || true
  printf "%bA process exited unexpectedly — cleaning up.%b\n" "$YELLOW" "$NC"
}

# ── Route command ────────────────────────────────────────────────────
case "${1:-}" in
  start)           do_start ;;
  stop)            do_stop  ;;
  help|-h|--help)  do_help  ;;
  "")
    printf "%bMissing command.%b\n\n" "$RED" "$NC"
    do_help
    exit 1
    ;;
  *)
    printf "%bUnknown command: %s%b\n\n" "$RED" "$1" "$NC"
    do_help
    exit 1
    ;;
esac
