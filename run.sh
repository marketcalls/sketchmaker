#!/usr/bin/env bash
# One command to run Sketchmaker: ./run.sh
#
#   ./run.sh --preflight   do everything except start the server
#
# Environment: SKIP_FRONTEND_BUILD=1 keeps whatever is in frontend/dist.
# SKETCHMAKER_ENV_FILE points at a different .env (default backend/.env).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
ENV_FILE="${SKETCHMAKER_ENV_FILE:-$BACKEND/.env}"

PREFLIGHT=0
if [ "${1:-}" = "--preflight" ]; then
  PREFLIGHT=1
fi

fail() { echo "error: $*" >&2; exit 1; }
warn() { echo "warning: $*" >&2; }

command -v uv >/dev/null 2>&1 || fail "uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/"
command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 \
  || warn "ffmpeg and ffprobe were not found: video tools and studio renders will fail until they are installed."

cd "$BACKEND"
uv sync --frozen --quiet
PY="$BACKEND/.venv/bin/python"

if [ ! -f "$ENV_FILE" ]; then
  "$PY" -m app.cli init
fi

# Reads and validates the configuration: a bad .env stops here with a clear message.
CONFIG="$("$PY" -c 'from app.config import settings as s; print(s.HOST, s.PORT, s.TRUSTED_PROXIES or "-")')"
read -r HOST PORT TRUSTED_PROXIES <<<"$CONFIG"

needs_build() {
  [ -f "$FRONTEND/dist/index.html" ] || return 0
  [ -n "$(find "$FRONTEND/src" "$FRONTEND/public" "$FRONTEND/index.html" "$FRONTEND/package.json" \
    -newer "$FRONTEND/dist/index.html" -print -quit 2>/dev/null)" ]
}

if [ "${SKIP_FRONTEND_BUILD:-0}" = "1" ]; then
  echo "Skipping the frontend build (SKIP_FRONTEND_BUILD=1)."
elif needs_build; then
  command -v node >/dev/null 2>&1 || fail "node is not installed, and the frontend needs building."
  command -v npm >/dev/null 2>&1 || fail "npm is not installed, and the frontend needs building."
  echo "Building the frontend..."
  cd "$FRONTEND"
  [ -d node_modules ] || npm ci
  npm run build
  cd "$BACKEND"
else
  command -v node >/dev/null 2>&1 || warn "node was not found. The current frontend build is up to date, so this run does not need it."
fi

"$PY" -m app.cli migrate

if [ "$PREFLIGHT" = "1" ]; then
  echo "Preflight passed. Would serve on $HOST:$PORT."
  exit 0
fi

if [ "$TRUSTED_PROXIES" = "-" ]; then
  PROXY_ARGS=(--no-proxy-headers)
else
  PROXY_ARGS=(--proxy-headers --forwarded-allow-ips "$TRUSTED_PROXIES")
fi

exec "$BACKEND/.venv/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --workers 1 --no-server-header "${PROXY_ARGS[@]}"
