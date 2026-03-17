"""apply_rscore_dll.py – Swap os_rscore.tmp.dll → os_rscore.dll.

Run this script in a FRESH Python session (before any opensynaptic imports)
to apply the newly compiled rscore DLL.

    python scripts/apply_rscore_dll.py
"""
import os
import shutil
import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / 'src' / 'opensynaptic' / 'utils' / 'c' / 'bin'
TMP_DLL = BIN_DIR / 'os_rscore.tmp.dll'
LIVE_DLL = BIN_DIR / 'os_rscore.dll'
BACKUP_DLL = BIN_DIR / 'os_rscore.bak.dll'

def main():
    if not TMP_DLL.exists():
        print('[apply] Nothing to apply – os_rscore.tmp.dll not found.')
        return 1

    # Backup current DLL if present
    if LIVE_DLL.exists():
        shutil.copy2(str(LIVE_DLL), str(BACKUP_DLL))
        print(f'[apply] Backed up: {BACKUP_DLL.name}')

    try:
        shutil.copy2(str(TMP_DLL), str(LIVE_DLL))
        TMP_DLL.unlink()
        print(f'[apply] DLL applied: {LIVE_DLL}')
        return 0
    except PermissionError as exc:
        print(f'[apply] Permission error – DLL still in use. Close all Python sessions first.')
        print(f'        {exc}')
        return 1
    except Exception as exc:
        print(f'[apply] Error: {exc}')
        return 1

if __name__ == '__main__':
    sys.exit(main())

