#!/usr/bin/env python3
"""
Audit script: Check send/receive capabilities of all protocol drivers.

This module is integrated into the CLI via: os-cli plugin-test --suite audit
"""

from __future__ import annotations

import importlib
import socket
import sys
import threading
import time
from pathlib import Path


_RUNTIME_SKIP_NAMES = {
    'MQTT',
    'QUIC',
    'IWIP',
    'UIP',
    'UART',
    'RS485',
    'CAN',
    'LoRa',
}


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]  # Go up to project root
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def _pick_probe_port(protocol: str = 'tcp') -> int:
    sock_kind = socket.SOCK_DGRAM if str(protocol).strip().lower() == 'udp' else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, sock_kind) as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def _build_probe_config(module_path: str) -> tuple[dict, str | None]:
    host = '127.0.0.1'
    if module_path.endswith('.udp'):
        port = _pick_probe_port('udp')
        return {
            'transport_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
            }
        }, 'udp'
    if module_path.endswith('.tcp'):
        port = _pick_probe_port('tcp')
        return {
            'transport_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
            }
        }, 'tcp'
    if module_path.endswith('.matter') or module_path.endswith('.zigbee'):
        port = _pick_probe_port('udp')
        return {
            'application_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
                'protocol': 'udp',
                'timeout': 0.25,
                'listen_timeout': 0.1,
            }
        }, 'udp'
    if module_path.endswith('.bluetooth'):
        port = _pick_probe_port('udp')
        return {
            'physical_options': {
                'host': host,
                'port': port,
                'listen_host': host,
                'listen_port': port,
                'protocol': 'udp',
                'timeout': 0.25,
                'listen_timeout': 0.1,
            }
        }, 'udp'
    return {}, None


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
    except Exception as exc:
        return False, f'driver import failed: {exc}'
    return True, ''


def _runtime_probe_listen(module, module_path: str, name: str) -> tuple[str, str]:
    if not hasattr(module, 'listen') or not callable(getattr(module, 'listen')):
        return 'SKIP', 'listen() unavailable'
    if not hasattr(module, 'send') or not callable(getattr(module, 'send')):
        return 'SKIP', 'send() unavailable'
    if name in _RUNTIME_SKIP_NAMES:
        return 'SKIP', 'external dependency / hardware / simulator path'

    cfg, protocol = _build_probe_config(module_path)
    if not cfg or not protocol:
        return 'SKIP', 'no stable probe config'

    received = threading.Event()
    listener_errors: list[str] = []
    callback_hits = {'count': 0}

    def _callback(_data, _addr):
        callback_hits['count'] += 1
        received.set()

    def _listener_target():
        try:
            module.listen(cfg, _callback)
        except Exception as exc:
            listener_errors.append(str(exc))

    listener_thread = threading.Thread(
        target=_listener_target,
        daemon=True,
        name=f'audit-probe-{name.lower()}',
    )
    listener_thread.start()

    payload = b'os-audit-probe'
    attempts = 0
    send_successes = 0
    last_send_error = ''
    deadline = time.monotonic() + 3.0

    while time.monotonic() < deadline:
        if received.is_set():
            return 'PASS', f'loopback callback received attempts={attempts} hits={callback_hits["count"]}'
        if listener_errors:
            return 'FAIL', listener_errors[-1]
        if not listener_thread.is_alive() and attempts == 0:
            return 'WARN', 'listen() returned immediately'

        attempts += 1
        try:
            if bool(module.send(payload, cfg)):
                send_successes += 1
        except Exception as exc:
            last_send_error = str(exc)

        if received.wait(timeout=0.15):
            return 'PASS', f'loopback callback received attempts={attempts} hits={callback_hits["count"]}'
        if listener_errors:
            return 'FAIL', listener_errors[-1]
        if not listener_thread.is_alive() and not received.is_set():
            return 'WARN', 'listen() returned before receiving probe payload'

    if received.is_set():
        return 'PASS', f'loopback callback received attempts={attempts} hits={callback_hits["count"]}'
    if listener_errors:
        return 'FAIL', listener_errors[-1]
    if not listener_thread.is_alive():
        return 'WARN', 'listen() returned before receiving probe payload'
    if send_successes > 0:
        return 'FAIL', f'probe send succeeded {send_successes} times but callback was never observed'
    if last_send_error:
        return 'FAIL', f'probe send failed: {last_send_error}'
    return 'FAIL', 'probe timed out without observable send/listen activity'


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
    except Exception as exc:
        return {
            "module": name,
            "layer": layer,
            "path": module_path,
            "error": str(exc),
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
                probe_mark = r.get('runtime_probe', 'SKIP')
                print(f"  {status:15} {r['module']:10} Send:{send_mark}  Receive:{recv_mark}  Probe:{probe_mark}")
                if r.get("missing"):
                    print(f"                     Missing: {', '.join(r['missing'])}")
                probe_reason = r.get('runtime_probe_reason')
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
            if "error" not in r and not r["status"].startswith("✓"):
                incomplete_drivers.append((r["module"], layer, r.get("missing", [])))

    if incomplete_drivers:
        print(f"\n⚠ DRIVERS WITH CONTRACT / RUNTIME GAPS:")
        for name, layer, missing in incomplete_drivers:
            print(f"  - {name} ({layer}): {', '.join(missing) if missing else 'check runtime probe details'}")

    return 0 if total_incomplete == 0 and total_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

