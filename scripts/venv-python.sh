#!/usr/bin/env bash
# Run a Python command using the project virtualenv.
# Usage: ./scripts/venv-python.sh [python-args...]
# Mirrors: scripts/venv-python.cmd

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[error] Virtual environment python not found: $PY" >&2
    echo "[hint]  Create it first: python3 -m venv .venv" >&2
    exit 1
fi

exec "$PY" "$@"
