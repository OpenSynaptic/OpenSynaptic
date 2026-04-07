#!/usr/bin/env python3
"""Standalone wrapper for the shared integration test suite."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def main() -> int:
    _ensure_import_path()
    from opensynaptic.services.test_plugin.integration_test import main as shared_main

    return int(shared_main())


if __name__ == "__main__":
    raise SystemExit(main())

