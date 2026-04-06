#!/usr/bin/env bash
# Run pip inside the project virtualenv.
# Usage: ./scripts/venv-pip.sh install <package>
# Mirrors: scripts/venv-pip.cmd

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[error] Virtual environment python not found: $PY" >&2
    echo "[hint]  Create it first: python3 -m venv .venv" >&2
    exit 1
fi

exec "$PY" -m pip "$@"
