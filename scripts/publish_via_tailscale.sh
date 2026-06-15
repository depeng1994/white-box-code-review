#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${DB_PATH:-$ROOT_DIR/data/review_board.sqlite3}"
PORT="${PORT:-8090}"
HOST="${HOST:-127.0.0.1}"
TS_DIR="${TS_DIR:-$HOME/.tailscale}"
TS_SOCKET="${TS_SOCKET:-$TS_DIR/tailscaled.sock}"
TS_STATE="${TS_STATE:-$TS_DIR/tailscaled.state}"
TS_LOG="${TS_LOG:-$TS_DIR/logs/tailscaled-live.log}"
BOARD_LOG="${BOARD_LOG:-$ROOT_DIR/data/review_board_server.log}"
TOKEN_ENV="${TOKEN_ENV:-GITCODE_API_TOKEN}"

mkdir -p "$ROOT_DIR/data" "$TS_DIR/logs"

ensure_board() {
  if ! curl -fsS "http://${HOST}:${PORT}/" >/dev/null 2>&1; then
    nohup "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/backend/review_board.py" \
      --db "$DB_PATH" serve --host "$HOST" --port "$PORT" \
      >"$BOARD_LOG" 2>&1 &
    sleep 3
  fi

  curl -fsS "http://${HOST}:${PORT}/api/dashboard?period=month" >/dev/null
}

ensure_tailscaled() {
  if ! tailscale --socket="$TS_SOCKET" status >/dev/null 2>&1; then
    nohup tailscaled \
      --tun=userspace-networking \
      --state="$TS_STATE" \
      --socket="$TS_SOCKET" \
      >"$TS_LOG" 2>&1 &
    sleep 3
  fi
}

ensure_logged_in() {
  if ! tailscale --socket="$TS_SOCKET" status >/dev/null 2>&1; then
    tailscale --socket="$TS_SOCKET" up
  fi
}

publish_serve() {
  tailscale --socket="$TS_SOCKET" serve --bg "$PORT"
}

show_result() {
  tailscale --socket="$TS_SOCKET" serve status
  tailscale --socket="$TS_SOCKET" status
}

main() {
  if [[ -z "${!TOKEN_ENV:-}" ]]; then
    echo "warning: ${TOKEN_ENV} is not set; dashboard sync API may not be able to refresh data" >&2
  fi

  ensure_board
  ensure_tailscaled
  ensure_logged_in
  publish_serve
  show_result
}

main "$@"
