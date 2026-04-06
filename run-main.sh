#!/usr/bin/env bash
# Root-level shortcut — delegates to scripts/run-main.sh.
# Usage: ./run-main.sh [os-node-args...]
# Mirrors: run-main.cmd

set -euo pipefail

exec "$(dirname "${BASH_SOURCE[0]}")/scripts/run-main.sh" "$@"
