#!/usr/bin/env python3
"""
Audit script: Check send/receive capabilities of all protocol drivers.

This module is integrated into the CLI via: os-cli plugin-test --suite audit
"""

import sys
import importlib
from pathlib import Path


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]  # Go up to project root
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def audit_driver(module_path: str, layer: str, name: str) -> dict:
    """Audit a driver for send/receive capabilities."""
    try:
        module = importlib.import_module(module_path)
        
        has_send = hasattr(module, 'send') and callable(getattr(module, 'send'))
        has_listen = hasattr(module, 'listen') and callable(getattr(module, 'listen'))
        has_receive = hasattr(module, 'receive') and callable(getattr(module, 'receive'))
        
        return {
            "module": name,
            "layer": layer,
            "path": module_path,
            "send": has_send,
            "listen": has_listen,
            "receive": has_receive,
            "status": "✓ COMPLETE" if (has_send and (has_listen or has_receive)) else "⚠ INCOMPLETE",
            "missing": [x for x in ["send", "listen/receive"] if not (
                has_send if x == "send" else (has_listen or has_receive)
            )]
        }
    except Exception as e:
        return {
            "module": name,
            "layer": layer,
            "path": module_path,
            "error": str(e),
            "status": "✗ ERROR"
        }


def audit_all_drivers() -> dict:
    """Audit all drivers and return results."""
    repo_root = _ensure_import_path()
    
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
        ],
        "L7 Application": [
            ("opensynaptic.services.transporters.drivers.mqtt", "MQTT"),
        ]
    }
    
    all_results = {}
    
    for layer, protocols in drivers.items():
        all_results[layer] = []
        
        for module_path, name in protocols:
            result = audit_driver(module_path, layer, name)
            all_results[layer].append(result)
    
    return all_results


def main() -> int:
    _ensure_import_path()
    
    print("=" * 80)
    print("OpenSynaptic Driver Capability Audit")
    print("=" * 80)
    
    all_results = audit_all_drivers()
    
    for layer, results in all_results.items():
        print(f"\n[{layer}]")
        
        for r in results:
            if "error" in r:
                print(f"  ✗ {r['module']:10} - ERROR: {r['error']}")
            else:
                send_mark = "✓" if r["send"] else "✗"
                recv_mark = "✓" if (r["listen"] or r["receive"]) else "✗"
                status = r["status"]
                print(f"  {status:15} {r['module']:10} Send:{send_mark}  Receive:{recv_mark}")
                if r.get("missing"):
                    print(f"                     Missing: {', '.join(r['missing'])}")
    
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
    
    print(f"\n  Complete (Send + Receive):   {total_complete}")
    print(f"  Incomplete (Missing Receive): {total_incomplete}")
    print(f"  Error:                       {total_error}")
    
    incomplete_drivers = []
    for layer, results in all_results.items():
        for r in results:
            if "error" not in r and r["status"].startswith("⚠"):
                incomplete_drivers.append((r["module"], layer, r.get("missing", [])))
    
    if incomplete_drivers:
        print(f"\n⚠ DRIVERS MISSING RECEIVE CAPABILITY:")
        for name, layer, missing in incomplete_drivers:
            print(f"  - {name} ({layer}): needs listen() or receive()")
    
    return 0 if total_incomplete == 0 and total_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

