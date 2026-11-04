#!/usr/bin/env bash
# The same as: uv run run.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v uv >/dev/null 2>&1 || { echo "error: uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
exec uv run "$ROOT/run.py" "$@"
