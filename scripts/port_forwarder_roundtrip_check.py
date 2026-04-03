#!/usr/bin/env python3
"""Port forwarder add/list/remove/list roundtrip validation."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def main() -> int:
    _ensure_import_path()

    from opensynaptic.services.port_forwarder.main import PortForwarder

    with tempfile.TemporaryDirectory(prefix="opensynaptic-pf-") as tmp:
        rules_path = Path(tmp) / "rules.json"

        cfg = PortForwarder.get_required_config()
        cfg["persist_rules"] = True
        cfg["rules_file"] = str(rules_path)

        plugin = PortForwarder(node=None, **cfg)

        before = plugin.handle_list(None)
        before_total = int(before.get("total", 0)) if isinstance(before, dict) else -1

        add_args = SimpleNamespace(
            from_protocol="UDP",
            to_protocol="TCP",
            to_host="127.0.0.1",
            to_port=19001,
            rule_set="default",
        )
        added = plugin.handle_add_rule(add_args)

        after_add = plugin.handle_list(None)
        after_add_total = int(after_add.get("total", -1)) if isinstance(after_add, dict) else -1

        remove_args = SimpleNamespace(rule_set="default", index=before_total)
        removed = plugin.handle_remove_rule(remove_args)

        after_remove = plugin.handle_list(None)
        after_remove_total = int(after_remove.get("total", -1)) if isinstance(after_remove, dict) else -1

        ok = (
            isinstance(added, dict)
            and added.get("status") == "ok"
            and after_add_total == before_total + 1
            and isinstance(removed, dict)
            and removed.get("status") == "ok"
            and after_remove_total == before_total
            and rules_path.exists()
        )

        report = {
            "ok": bool(ok),
            "before_total": before_total,
            "after_add_total": after_add_total,
            "after_remove_total": after_remove_total,
            "add_result": added,
            "remove_result": removed,
            "rules_file": str(rules_path),
            "rules_file_exists": rules_path.exists(),
        }

        print(json.dumps(report, ensure_ascii=False))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
