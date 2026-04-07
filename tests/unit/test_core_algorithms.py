import ctypes
from pathlib import Path

import pytest


def _config_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "Config.json")


def _require_native(*libs: str) -> None:
    from opensynaptic.utils.c.native_loader import has_native_library

    missing = [name for name in libs if not has_native_library(name)]
    if missing:
        pytest.skip(f"native runtime unavailable: missing {', '.join(missing)}")


def test_crc16_reference_vector():
    _require_native("os_security")
    from opensynaptic.utils import crc16_ccitt

    assert crc16_ccitt(b"123456789") == 0x29B1


def test_base62_compress_decompress_roundtrip():
    _require_native("os_base62")
    from opensynaptic.core.pycore.solidity import OpenSynapticEngine

    cfg = _config_path()
    engine = None
    try:
        engine = OpenSynapticEngine(config_path=cfg)
    except Exception as exc:  # pragma: no cover - env dependent (native libs)
        pytest.skip(f"native runtime unavailable: {exc}")

    fact = {
        "id": "N1",
        "s": "ONLINE",
        "t": 1710000000,
        "s1_id": "TEMP",
        "s1_s": "OK",
        "s1_u": "Pa",
        "s1_v": 101.3,
    }

    encoded = engine.compress(fact)
    decoded = engine.decompress(encoded)

    assert decoded["id"] == "N1"
    assert decoded["s1_id"] == "TEMP"
    assert decoded["s1_u"]
    assert pytest.approx(float(decoded["s1_v"]), rel=1e-3) == 101.3


def test_packet_encode_decode_roundtrip():
    _require_native("os_base62", "os_security")
    from opensynaptic.core.pycore.solidity import OpenSynapticEngine
    from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine

    cfg = _config_path()
    engine = None
    fusion = None
    try:
        engine = OpenSynapticEngine(config_path=cfg)
        fusion = OSVisualFusionEngine(config_path=cfg)
    except Exception as exc:  # pragma: no cover - env dependent (native libs)
        pytest.skip(f"native runtime unavailable: {exc}")

    fact = {
        "id": "N2",
        "s": "ONLINE",
        "t": 1710000000,
        "s1_id": "H1",
        "s1_s": "OK",
        "s1_u": "%",
        "s1_v": 56.1,
    }
    compressed = engine.compress(fact)
    packet = fusion.run_engine(f"12345;{compressed}", strategy="FULL")
    decoded = fusion.decompress(packet)

    assert isinstance(packet, (bytes, bytearray))
    assert str(decoded["id"]).split(";")[-1] == "N2"
    assert decoded["s1_id"] == "H1"


def test_python_abi_shim_fallback_when_rs_extension_symbols_are_unavailable(monkeypatch, tmp_path):
    import importlib
    import importlib.metadata as importlib_metadata
    import site
    import sys
    import sysconfig

    src_root = Path(__file__).resolve().parents[2] / 'src'
    monkeypatch.syspath_prepend(str(src_root))
    sys.modules.pop('opensynaptic.utils.c.native_loader', None)
    from opensynaptic.utils.c import native_loader
    native_loader = importlib.reload(native_loader)

    candidate_dir = tmp_path / "opensynaptic_rscore"
    candidate_dir.mkdir()
    candidate_path = candidate_dir / "opensynaptic_rscore.cpython-313-x86_64-linux-gnu.so"
    candidate_path.write_bytes(b"shim-probe")

    class _FakeRsPkg:
        __file__ = str(candidate_dir / "__init__.py")
        __path__ = [str(candidate_dir)]

        @staticmethod
        def abi_info_py():
            return "opensynaptic_rscore c-api+pyo3"

    def _fail_loader(*_args, **_kwargs):
        raise OSError("symbol hidden from dynsym")

    def _fake_import_module(name, package=None):
        if name == 'opensynaptic_rscore':
            return _FakeRsPkg()
        raise ImportError(name)

    native_loader._LIB_CACHE.clear()
    monkeypatch.setattr(native_loader, '_native_dirs', lambda: [])
    monkeypatch.setattr(native_loader, '_try_build_once', lambda: None)
    monkeypatch.setattr(native_loader.ctypes, 'PyDLL', _fail_loader)
    monkeypatch.setattr(native_loader.ctypes, 'CDLL', _fail_loader)
    monkeypatch.setattr(native_loader.importlib, 'import_module', _fake_import_module)
    monkeypatch.setattr(importlib_metadata, 'distribution', lambda _name: (_ for _ in ()).throw(importlib_metadata.PackageNotFoundError()))
    monkeypatch.setattr(sysconfig, 'get_paths', lambda: {'platlib': str(tmp_path), 'purelib': str(tmp_path)})
    monkeypatch.setattr(site, 'getsitepackages', lambda: [])

    assert native_loader.has_native_library('os_base62')
    b62 = native_loader.load_native_library('os_base62')
    out = ctypes.create_string_buffer(16)
    assert b62.os_b62_encode_i64(61, out, ctypes.sizeof(out)) == 1
    assert out.value == b'Z'
    ok = ctypes.c_int(0)
    assert b62.os_b62_decode_i64(out.value, ctypes.byref(ok)) == 61
    assert ok.value == 1

    assert native_loader.has_native_library('os_security')
    sec = native_loader.load_native_library('os_security')
    payload = (ctypes.c_ubyte * 3)(1, 2, 3)
    key = (ctypes.c_ubyte * 4)(10, 11, 12, 13)
    out_buf = (ctypes.c_ubyte * 3)()
    assert sec.os_crc8(payload, 3, 0x07, 0) == 72
    sec.os_xor_payload(payload, 3, key, 4, 1, out_buf)
    assert bytes(out_buf) == bytes.fromhex('0b0f0f')
