#!/bin/sh
# Container start: create the secrets once, upgrade the schema, serve.
set -eu

cd "$(dirname "$0")/../backend"

for dir in "$(dirname "$SKETCHMAKER_ENV_FILE")" "$DATA_DIR"; do
  if [ ! -w "$dir" ]; then
    echo "error: $dir is not writable by user $(id -u). Use the named volumes in docker-compose.yml, or chown a bind mount to 10001." >&2
    exit 1
  fi
done

if [ ! -f "$SKETCHMAKER_ENV_FILE" ]; then
  python -m app.cli init --secrets-only
fi

# Reads and validates the configuration: a bad value stops here with a clear message.
CONFIG="$(python -c 'from app.config import settings as s; print(s.HOST, s.PORT, s.TRUSTED_PROXIES or "-")')"
# Split into three words, with globbing off: TRUSTED_PROXIES may be "*".
set -f
# shellcheck disable=SC2086
set -- $CONFIG
set +f

python -m app.cli migrate

if [ "$3" = "-" ]; then
  exec uvicorn app.main:app --host "$1" --port "$2" --workers 1 --no-server-header --no-proxy-headers
fi
exec uvicorn app.main:app --host "$1" --port "$2" --workers 1 --no-server-header --proxy-headers --forwarded-allow-ips "$3"
