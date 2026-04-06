#!/usr/bin/env bash
# Run the OpenSynaptic main entry point via the project virtualenv.
# Usage: ./scripts/run-main.sh [os-node-args...]
# Mirrors: scripts/run-main.cmd

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/venv-python.sh" -u "$ROOT/src/main.py" "$@"
