#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ── Config ──────────────────────────────────────────────────────────────────
SERVER_PORT=8000
GRADIO_PORT=7860
VENV=".venv"

# ── Helpers ─────────────────────────────────────────────────────────────────
kill_port() { lsof -ti:"$1" | xargs kill -9 2>/dev/null || true; }

wait_for() {
  local url="$1" timeout="${2:-120}" elapsed=0
  while [ "$elapsed" -lt "$timeout" ]; do
    if curl -s --max-time 2 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 3; elapsed=$((elapsed + 3))
    printf "  waiting… %ds\n" "$elapsed"
  done
  echo "ERROR: $url not reachable after ${timeout}s" >&2; return 1
}

# ── Stop ────────────────────────────────────────────────────────────────────
stop() {
  echo "Stopping…"
  kill_port $SERVER_PORT
  kill_port $GRADIO_PORT
  sleep 1
  echo "Stopped."
}

# ── Start ───────────────────────────────────────────────────────────────────
start() {
  stop

  if [ ! -d "$VENV" ]; then
    echo "Creating venv…"
    python3 -m venv "$VENV"
    source "$VENV/bin/activate"
    pip install -r requirements.txt
  else
    source "$VENV/bin/activate"
  fi

  local fresh="${1:-}"
  if [ "$fresh" = "--fresh" ]; then
    echo "Removing Chroma index…"
    rm -rf ./chroma
  fi

  echo "Starting backend on :$SERVER_PORT …"
  nohup uvicorn server.main:app --host 0.0.0.0 --port $SERVER_PORT \
    > /tmp/senate-server.log 2>&1 &
  echo "  PID $! → log: /tmp/senate-server.log"

  echo "Waiting for backend…"
  wait_for "http://localhost:$SERVER_PORT/health" 120

  echo "Starting Gradio on :$GRADIO_PORT …"
  DEBATE_API_BASE="http://localhost:$SERVER_PORT/v1/chat/completions" \
    nohup python3 gradio_app.py > /tmp/senate-gradio.log 2>&1 &
  echo "  PID $! → log: /tmp/senate-gradio.log"

  wait_for "http://localhost:$GRADIO_PORT" 30

  echo ""
  echo "✓ Backend:  http://localhost:$SERVER_PORT/health"
  echo "✓ Gradio:   http://localhost:$GRADIO_PORT"
  echo ""
  echo "Logs:"
  echo "  tail -f /tmp/senate-server.log"
  echo "  tail -f /tmp/senate-gradio.log"
  echo "  tail -f logs/debate.log          # live debate turns + RAG chunks"
}

# ── CLI ─────────────────────────────────────────────────────────────────────
case "${1:-start}" in
  start)   start "${2:-}" ;;
  stop)    stop ;;
  restart) start "${2:-}" ;;
  fresh)   start --fresh ;;
  logs)    tail -f /tmp/senate-server.log /tmp/senate-gradio.log ;;
  *)
    echo "Usage: $0 {start|stop|restart|fresh|logs}"
    echo ""
    echo "  start     Start backend + Gradio (reuse existing Chroma index)"
    echo "  stop      Kill both processes"
    echo "  restart   Stop then start"
    echo "  fresh     Stop, wipe Chroma, start (re-index embeddings)"
    echo "  logs      Tail both log files"
    exit 1
    ;;
esac
