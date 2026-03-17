#!/usr/bin/env python
"""Smoke test for coremanager discovery and native-backed utils."""

import sys
from pathlib import Path


def _bootstrap_paths():
    root = None
    for parent in Path(__file__).resolve().parents:
        if (parent / 'Config.json').exists():
            root = parent
            break
    if root is None:
        return
    src = root / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main():
    _bootstrap_paths()

    from opensynaptic.core import get_core_manager
    from opensynaptic.utils import (
        has_native_library,
        NativeLibraryUnavailable,
        Base62Codec,
        crc8,
        crc16_ccitt,
        derive_session_key,
        xor_payload,
    )

    manager = get_core_manager()
    print('[core] discovered:', manager.discover_cores())
    print('[core] active:', manager.get_active_core_name())
    print('[core] symbols:', manager.list_symbols())
    print('[native] os_base62:', has_native_library('os_base62'))
    print('[native] os_security:', has_native_library('os_security'))

    try:
        codec = Base62Codec(precision=4)
        token = codec.encode(12.3456)
        restored = codec.decode(token)
        print('[b62] token/restored:', token, restored)
        print('[sec] crc8(abc):', crc8(b'abc'))
        print('[sec] crc16(abc):', crc16_ccitt(b'abc'))
        key = derive_session_key(42, 1700000000)
        print('[sec] key length:', len(key))
        encrypted = xor_payload(b'hello', b'key', 3)
        print('[sec] xor roundtrip:', xor_payload(encrypted, b'key', 3) == b'hello')
    except NativeLibraryUnavailable as exc:
        print('[native] unavailable:', exc)


if __name__ == '__main__':
    main()
