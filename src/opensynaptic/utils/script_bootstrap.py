"""Helpers for bootstrapping workspace imports in standalone scripts."""

from __future__ import annotations

import sys
from pathlib import Path


def bootstrap_project_paths(anchor_file) -> Path | None:
    """Add project root and src/ to sys.path when Config.json is discoverable."""
    root = None
    for parent in Path(anchor_file).resolve().parents:
        if (parent / 'Config.json').exists():
            root = parent
            break
    if root is None:
        return None

    src = root / 'src'
    src_s = str(src)
    root_s = str(root)
    if src_s not in sys.path:
        sys.path.insert(0, src_s)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root

