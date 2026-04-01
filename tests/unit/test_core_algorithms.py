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
