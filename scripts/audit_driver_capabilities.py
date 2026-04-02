#!/usr/bin/env python3
"""
Audit script: Check send/receive capabilities of all protocol drivers.
"""

import sys
import importlib
import threading
import time
from pathlib import Path


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def _pick_probe_port(base: int = 39000) -> int:
    return base + int(time.time() * 1000) % 1000


def _build_probe_config(module_path: str, port: int) -> dict:
    host = '127.0.0.1'
    if 'core.transport_layer.protocols' in module_path:
        return {
            'transport_options': {
                'listen_host': host,
                'listen_port': port,
            }
        }
    if module_path.endswith('.matter') or module_path.endswith('.zigbee'):
        return {
            'application_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
                'protocol': 'udp',
                'timeout': 0.5,
            }
        }
    if module_path.endswith('.bluetooth'):
        return {
            'physical_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
                'protocol': 'udp',
                'timeout': 0.5,
            }
        }
    return {}


def _needs_driver_receive_check(module_path: str) -> bool:
    return module_path in {
        'opensynaptic.core.physical_layer.protocols.rs485',
        'opensynaptic.core.physical_layer.protocols.can',
        'opensynaptic.core.physical_layer.protocols.lora',
    }


def _driver_receive_contract_ok(module_path: str) -> tuple[bool, str]:
    try:
        if module_path.endswith('.rs485'):
            from opensynaptic.hardware_drivers.RS485 import RS485_Driver
            ok = callable(getattr(RS485_Driver, 'receive', None))
            return ok, 'RS485_Driver.receive() missing' if not ok else ''
        if module_path.endswith('.can'):
            from opensynaptic.hardware_drivers.CAN import CAN_Driver
            ok = callable(getattr(CAN_Driver, 'receive', None))
            return ok, 'CAN_Driver.receive() missing' if not ok else ''
        if module_path.endswith('.lora'):
            from opensynaptic.hardware_drivers.LoRa import LoRaDriver
            ok = callable(getattr(LoRaDriver, 'receive', None))
            return ok, 'LoRaDriver.receive() missing' if not ok else ''
    except Exception as e:
        return False, f'driver import failed: {e}'
    return True, ''


def _runtime_probe_listen(module, module_path: str, name: str) -> tuple[str, str]:
    """Return (status, reason) where status in PASS/SKIP/FAIL/WARN."""
    if not hasattr(module, 'listen') or not callable(getattr(module, 'listen')):
        return 'SKIP', 'listen() unavailable'

    # Known external dependencies or non-blocking stubs are intentionally skipped.
    if name in {'MQTT', 'QUIC', 'IWIP', 'UIP', 'UART', 'RS485', 'CAN', 'LoRa'}:
        return 'SKIP', 'external dependency / hardware / simulator path'

    port = _pick_probe_port()
    cfg = _build_probe_config(module_path, port)
    errors = []

    def _target():
        try:
            module.listen(cfg, lambda _data, _addr: None)
        except Exception as exc:
            errors.append(str(exc))

    t = threading.Thread(target=_target, daemon=True, name=f'audit-listen-{name.lower()}')
    t.start()
    time.sleep(0.25)

    if errors:
        return 'FAIL', errors[0]
    if not t.is_alive():
        return 'WARN', 'listen() returned immediately'
    return 'PASS', 'listener thread alive'


def audit_driver(module_path: str, layer: str, name: str) -> dict:
    """Audit a driver for send/receive capabilities."""
    try:
        module = importlib.import_module(module_path)
        
        has_send = hasattr(module, 'send') and callable(getattr(module, 'send'))
        has_listen = hasattr(module, 'listen') and callable(getattr(module, 'listen'))
        has_receive = hasattr(module, 'receive') and callable(getattr(module, 'receive'))
        contract_ok = True
        contract_reason = ''
        if _needs_driver_receive_check(module_path):
            contract_ok, contract_reason = _driver_receive_contract_ok(module_path)

        runtime_status, runtime_reason = _runtime_probe_listen(module, module_path, name)

        base_ok = bool(has_send and (has_listen or has_receive) and contract_ok)
        if not base_ok:
            status = '⚠ INCOMPLETE'
        elif runtime_status == 'FAIL':
            status = '✗ RUNTIME_FAIL'
        elif runtime_status == 'WARN':
            status = '⚠ RUNTIME_WARN'
        else:
            status = '✓ COMPLETE'

        missing = [x for x in ['send', 'listen/receive'] if not (
            has_send if x == 'send' else (has_listen or has_receive)
        )]
        if not contract_ok and contract_reason:
            missing.append(contract_reason)
        
        return {
            "module": name,
            "layer": layer,
            "path": module_path,
            "send": has_send,
            "listen": has_listen,
            "receive": has_receive,
            "status": status,
            "runtime_probe": runtime_status,
            "runtime_probe_reason": runtime_reason,
            "missing": missing,
        }
    except Exception as e:
        return {
            "module": name,
            "layer": layer,
            "path": module_path,
            "error": str(e),
            "status": "✗ ERROR"
        }


def main() -> int:
    repo_root = _ensure_import_path()
    
    print("=" * 80)
    print("OpenSynaptic Driver Capability Audit")
    print("=" * 80)
    
    drivers = {
        "L4 Transport": [
            ("opensynaptic.core.transport_layer.protocols.udp", "UDP"),
            ("opensynaptic.core.transport_layer.protocols.tcp", "TCP"),
            ("opensynaptic.core.transport_layer.protocols.quic", "QUIC"),
            ("opensynaptic.core.transport_layer.protocols.iwip", "IWIP"),
            ("opensynaptic.core.transport_layer.protocols.uip", "UIP"),
        ],
        "PHY Physical": [
            ("opensynaptic.core.physical_layer.protocols.uart", "UART"),
            ("opensynaptic.core.physical_layer.protocols.rs485", "RS485"),
            ("opensynaptic.core.physical_layer.protocols.can", "CAN"),
            ("opensynaptic.core.physical_layer.protocols.lora", "LoRa"),
            ("opensynaptic.core.physical_layer.protocols.bluetooth", "Bluetooth"),
        ],
        "L7 Application": [
            ("opensynaptic.services.transporters.drivers.mqtt", "MQTT"),
            ("opensynaptic.services.transporters.drivers.matter", "Matter"),
            ("opensynaptic.services.transporters.drivers.zigbee", "Zigbee"),
        ]
    }
    
    all_results = {}
    
    for layer, protocols in drivers.items():
        print(f"\n[{layer}]")
        all_results[layer] = []
        
        for module_path, name in protocols:
            result = audit_driver(module_path, layer, name)
            all_results[layer].append(result)
            
            if "error" in result:
                print(f"  ✗ {name:10} - ERROR: {result['error']}")
            else:
                send_mark = "✓" if result["send"] else "✗"
                recv_mark = "✓" if (result["listen"] or result["receive"]) else "✗"
                status = result["status"]
                probe_mark = result.get('runtime_probe', 'SKIP')
                print(f"  {status:15} {name:10} Send:{send_mark}  Receive:{recv_mark}  Probe:{probe_mark}")
                if result.get("missing"):
                    print(f"                     Missing: {', '.join(result['missing'])}")
                probe_reason = result.get('runtime_probe_reason')
                if probe_reason and probe_mark in {'FAIL', 'WARN', 'SKIP'}:
                    print(f"                     Probe reason: {probe_reason}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_complete = 0
    total_incomplete = 0
    total_error = 0
    
    for layer, results in all_results.items():
        for r in results:
            if "error" in r:
                total_error += 1
            elif r["status"].startswith("✓"):
                total_complete += 1
            else:
                total_incomplete += 1
    
    print(f"\n  Complete (Contract + Probe):  {total_complete}")
    print(f"  Incomplete / Warn / Fail:    {total_incomplete}")
    print(f"  Error:                       {total_error}")
    
    incomplete_drivers = []
    for layer, results in all_results.items():
        for r in results:
            if "error" not in r and r["status"].startswith("⚠"):
                incomplete_drivers.append((r["module"], layer, r.get("missing", [])))
    
    if incomplete_drivers:
        print(f"\n⚠ DRIVERS WITH CONTRACT GAPS:")
        for name, layer, missing in incomplete_drivers:
            print(f"  - {name} ({layer}): {', '.join(missing) if missing else 'check runtime probe details'}")
    
    return 0 if total_incomplete == 0 and total_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

