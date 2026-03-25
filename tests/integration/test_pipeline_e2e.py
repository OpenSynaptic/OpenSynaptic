from pathlib import Path
from unittest import SkipTest


def _config_path() -> str:
    return str(Path(__file__).resolve().parents[2] / "Config.json")


def test_virtual_sensor_to_receive_roundtrip():
    from opensynaptic.core import OpenSynaptic

    cfg = _config_path()
    try:
        node = OpenSynaptic(config_path=cfg)
    except Exception as exc:  # pragma: no cover - env dependent (native libs)
        raise SkipTest(f"runtime unavailable: {exc}")
    else:
        if getattr(node, "_is_id_missing", lambda: True)():
            raise SkipTest("device id is unassigned in Config.json; run ensure-id before integration test")

        packet, aid, strategy = node.transmit(
            sensors=[["TMP1", "OK", 23.6, "Pa"], ["HUM1", "OK", 45.2, "%"]],
            t=1710000000,
        )
        decoded = node.receive(packet)

        assert isinstance(packet, (bytes, bytearray))
        assert isinstance(aid, int)
        assert strategy in {"FULL_PACKET", "DIFF_PACKET"}
        assert decoded.get("id")
        assert decoded.get("s1_id") in {"TMP1", "HUM1"}

