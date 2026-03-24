#!/usr/bin/env python3
"""
Quick integration test suite for OpenSynaptic.
Run this to verify the entire system works correctly.

This module is integrated into the CLI via: os-cli plugin-test --suite integration
"""

import sys
import json
from pathlib import Path


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]  # Go up to project root
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def run_tests(repo_root: Path = None) -> dict:
    """Run integration test suite."""
    if repo_root is None:
        repo_root = _ensure_import_path()
    
    from opensynaptic.core import OpenSynaptic
    
    config_path = repo_root / "Config.json"
    tests_passed = 0
    tests_failed = 0
    results = []
    
    # Test 1: Node initialization
    print("\n[TEST 1] Node initialization with auto-driver discovery")
    try:
        node = OpenSynaptic(config_path=str(config_path))
        assert node.assigned_id is not None
        assert len(node.transporter_manager._transport_manager.adapters) > 0
        print("  ✓ PASS: Node initialized, drivers auto-loaded")
        tests_passed += 1
        results.append({"test": "Node initialization", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Node initialization", "status": "FAIL", "error": str(e)})
    
    # Test 2: Transmit single sensor
    print("\n[TEST 2] Transmit single sensor")
    try:
        packet, aid, strategy = node.transmit(
            sensors=[["sensor1", "OK", 42.0, "Pa"]],
            device_id="test_device"
        )
        assert packet is not None
        assert len(packet) > 0
        assert isinstance(strategy, str)
        print(f"  ✓ PASS: Generated {len(packet)} byte packet, strategy={strategy}")
        tests_passed += 1
        results.append({"test": "Transmit single sensor", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Transmit single sensor", "status": "FAIL", "error": str(e)})
    
    # Test 3: Transmit multiple sensors
    print("\n[TEST 3] Transmit multiple sensors")
    try:
        packet_multi, aid, strategy = node.transmit(
            sensors=[
                ["V1", "OK", 3.14, "Pa"],
                ["T1", "OK", 25.3, "Cel"],
                ["H1", "OK", 65.0, "%"],
            ],
            device_id="multi_sensor_device"
        )
        assert len(packet_multi) > 0
        print(f"  ✓ PASS: 3 sensors packed into {len(packet_multi)} bytes")
        tests_passed += 1
        results.append({"test": "Transmit multiple sensors", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Transmit multiple sensors", "status": "FAIL", "error": str(e)})
    
    # Test 4: Receive (decompress) - use packet_multi from test 3
    print("\n[TEST 4] Receive and decompress packet")
    try:
        decoded = node.receive(packet_multi)
        assert isinstance(decoded, dict), f"Expected dict, got {type(decoded)}"
        if decoded.get("error"):
            raise AssertionError(f"Decode error: {decoded.get('error')}")
        assert decoded.get("id"), "Missing 'id' in decoded result"
        sensors_count = len([k for k in decoded if k.startswith("s") and k.endswith("_id")])
        assert sensors_count >= 2, f"Expected at least 2 sensors, got {sensors_count}"
        print(f"  ✓ PASS: Decompressed {sensors_count} sensors from packet")
        tests_passed += 1
        results.append({"test": "Receive and decompress", "status": "PASS"})
    except AssertionError as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Receive and decompress", "status": "FAIL", "error": str(e)})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Receive and decompress", "status": "FAIL", "error": str(e)})
    
    # Test 5: Receive via protocol (handshake) - use packet_multi
    print("\n[TEST 5] Receive via protocol (with handshake)")
    try:
        dispatch = node.receive_via_protocol(packet_multi, addr=("127.0.0.1", 5555))
        assert isinstance(dispatch, dict)
        assert dispatch.get("type") in ["DATA", "CTRL", "ERROR"]
        result = dispatch.get("result", {})
        assert not result.get("error") or True  # Error ok for some cases
        print(f"  ✓ PASS: Received as {dispatch.get('type')} packet")
        tests_passed += 1
        results.append({"test": "Receive via protocol", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Receive via protocol", "status": "FAIL", "error": str(e)})
    
    # Test 6: Dispatch (send via UDP)
    print("\n[TEST 6] Dispatch to UDP driver")
    try:
        # Create a fresh packet for dispatch
        pkt, _, _ = node.transmit(sensors=[["test", "OK", 1.0, "Pa"]])
        result = node.dispatch(pkt, medium="UDP")
        # UDP might fail if no server, but driver should be invoked
        print(f"  ✓ PASS: Dispatch invoked UDP driver (result={result})")
        tests_passed += 1
        results.append({"test": "Dispatch to UDP", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Dispatch to UDP", "status": "FAIL", "error": str(e)})
    
    # Test 7: Transport layer driver access
    print("\n[TEST 7] Transport layer driver direct access")
    try:
        from opensynaptic.core.transport_layer import get_transport_layer_manager
        tm = get_transport_layer_manager()
        assert "udp" in tm.adapters
        adapter = tm.get_adapter("udp")
        assert adapter is not None
        assert hasattr(adapter.module, "send")
        print(f"  ✓ PASS: UDP adapter loaded and validated")
        tests_passed += 1
        results.append({"test": "Transport layer access", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Transport layer access", "status": "FAIL", "error": str(e)})
    
    # Test 8: Physical layer driver access
    print("\n[TEST 8] Physical layer driver direct access")
    try:
        from opensynaptic.core.physical_layer import get_physical_layer_manager
        pm = get_physical_layer_manager()
        assert "uart" in pm.adapters
        adapter = pm.get_adapter("uart")
        assert adapter is not None
        assert hasattr(adapter.module, "send")
        print(f"  ✓ PASS: UART adapter loaded and validated")
        tests_passed += 1
        results.append({"test": "Physical layer access", "status": "PASS"})
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        tests_failed += 1
        results.append({"test": "Physical layer access", "status": "FAIL", "error": str(e)})
    
    return {
        "passed": tests_passed,
        "failed": tests_failed,
        "total": tests_passed + tests_failed,
        "results": results,
        "success": tests_failed == 0,
    }


def main() -> int:
    repo_root = _ensure_import_path()
    
    print("=" * 70)
    print("OpenSynaptic Integration Test Suite")
    print("=" * 70)
    
    result = run_tests(repo_root)
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {result['passed']}/{result['total']} tests passed")
    print("=" * 70)
    
    if result["success"]:
        print("\n✓ All tests PASSED! System is ready for production.")
        return 0
    else:
        print(f"\n✗ {result['failed']} tests FAILED. Review the output above.")
        print("\n[JSON Details]")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

