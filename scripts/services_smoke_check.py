import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
BASE = [PY, "-u", str(ROOT / "src" / "main.py")]

commands = [
    ["plugin-list"],
    ["tui", "--section", "identity"],
    ["plugin-cmd", "--plugin", "tui", "--cmd", "render", "--", "--section", "identity"],
    ["web-user", "status"],
    ["web-user", "options-schema", "--", "--only-writable"],
    ["web-user", "list"],
    ["deps", "check"],
    ["deps", "doctor"],
    ["env-guard", "status"],
    ["env-guard", "resource-show"],
    ["env-guard", "resource-init"],
    ["env-guard", "set", "--", "--auto-install", "false"],
    ["env-guard", "start"],
    ["env-guard", "stop"],
    [
        "plugin-cmd", "--plugin", "test_plugin", "--cmd", "stress", "--",
        "--total", "200", "--workers", "2", "--no-progress", "--pipeline-mode", "batch_fused"
    ],
    ["plugin-cmd", "--plugin", "port_forwarder", "--cmd", "status"],
]

failures = []
for idx, args in enumerate(commands, start=1):
    cmd = BASE + args
    print(f"[{idx}/{len(commands)}] RUN: {' '.join(args)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        failures.append((args, -1, str(exc)))
        print(f"  !! EXC: {exc}")
        continue

    if proc.returncode != 0:
        failures.append((args, proc.returncode, (proc.stderr or proc.stdout)[-1000:]))
        print(f"  !! FAIL rc={proc.returncode}")
    else:
        print("  OK")

if failures:
    print("\n--- FAILURES ---")
    for args, rc, tail in failures:
        print(f"CMD: {' '.join(args)}")
        print(f"RC: {rc}")
        print(tail)
        print("---")
    sys.exit(1)

print("\nAll smoke commands passed.")

