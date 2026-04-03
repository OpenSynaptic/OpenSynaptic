#!/usr/bin/env python3
"""
Exhaustive protocol interoperability validator.

This script runs a real send/receive matrix for local network-capable protocols
and produces a graded report for dependency-gated, simulator, and hardware-gated
protocols.
"""

from __future__ import annotations

import argparse
import importlib
import json
import queue
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


PROTOCOL_MODULES: Dict[str, str] = {
    "udp": "opensynaptic.core.transport_layer.protocols.udp",
    "tcp": "opensynaptic.core.transport_layer.protocols.tcp",
    "quic": "opensynaptic.core.transport_layer.protocols.quic",
    "iwip": "opensynaptic.core.transport_layer.protocols.iwip",
    "uip": "opensynaptic.core.transport_layer.protocols.uip",
    "uart": "opensynaptic.core.physical_layer.protocols.uart",
    "rs485": "opensynaptic.core.physical_layer.protocols.rs485",
    "can": "opensynaptic.core.physical_layer.protocols.can",
    "lora": "opensynaptic.core.physical_layer.protocols.lora",
    "bluetooth": "opensynaptic.core.physical_layer.protocols.bluetooth",
    "mqtt": "opensynaptic.services.transporters.drivers.mqtt",
    "matter": "opensynaptic.services.transporters.drivers.matter",
    "zigbee": "opensynaptic.services.transporters.drivers.zigbee",
}

NETWORK_PROTOCOLS = ("udp", "tcp", "matter", "zigbee", "bluetooth")
NON_NETWORK_PROTOCOLS = ("quic", "iwip", "uip", "uart", "rs485", "can", "lora", "mqtt")

SENDER_TRANSPORTS: Dict[str, set[str]] = {
    "udp": {"udp"},
    "tcp": {"tcp"},
    "matter": {"udp", "tcp"},
    "zigbee": {"udp", "tcp"},
    "bluetooth": {"udp", "tcp"},
}

RECEIVER_TRANSPORT: Dict[str, str] = {
    "udp": "udp",
    "tcp": "tcp",
    "matter": "udp",
    "zigbee": "udp",
    "bluetooth": "udp",
}

LIMITATION_HINTS: Dict[str, str] = {
    "quic": "Depends on aioquic and cert/key wiring for listen mode",
    "iwip": "send/listen are simulator stubs without real callback loop",
    "uip": "send/listen are simulator stubs without real callback loop",
    "uart": "Physical serial path; listen requires pyserial and real port",
    "rs485": "Physical serial path; driver listen depends on hardware receive implementation",
    "can": "Physical CAN path; driver listen depends on hardware receive implementation",
    "lora": "Physical LoRa serial path; requires transceiver and serial port",
    "mqtt": "Requires paho-mqtt and reachable broker",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def import_module_safe(module_path: str):
    try:
        return importlib.import_module(module_path), None
    except Exception as exc:
        return None, str(exc)


def build_listener_config(protocol: str, host: str, port: int) -> Dict[str, Any]:
    if protocol in ("udp", "tcp"):
        return {
            "transport_options": {
                "listen_host": host,
                "listen_port": port,
            }
        }
    if protocol in ("matter", "zigbee"):
        return {
            "application_options": {
                "host": host,
                "port": port,
                "listen_host": host,
                "listen_port": port,
            }
        }
    if protocol == "bluetooth":
        return {
            "physical_options": {
                "host": host,
                "port": port,
                "listen_host": host,
                "listen_port": port,
            }
        }
    return {}


def build_sender_config(protocol: str, host: str, port: int, transport: str) -> Dict[str, Any]:
    if protocol in ("udp", "tcp"):
        return {
            "transport_options": {
                "host": host,
                "port": port,
                "timeout": 1.0,
            }
        }
    if protocol in ("matter", "zigbee"):
        return {
            "application_options": {
                "host": host,
                "port": port,
                "protocol": transport,
                "timeout": 1.0,
            }
        }
    if protocol == "bluetooth":
        return {
            "physical_options": {
                "host": host,
                "port": port,
                "protocol": transport,
                "timeout": 1.0,
            }
        }
    if protocol == "quic":
        return {
            "transport_options": {
                "host": host,
                "port": port,
                "timeout": 0.5,
                "insecure": True,
            }
        }
    if protocol in ("iwip", "uip"):
        return {
            "transport_options": {
                "host": host,
                "port": port,
            }
        }
    if protocol in ("uart", "rs485", "can", "lora"):
        return {
            "physical_options": {
                "port": "COM1",
                "baudrate": 9600,
                "can_id": 291,
                "timeout": 1,
            }
        }
    if protocol == "mqtt":
        return {
            "application_options": {
                "host": host,
                "port": 1883,
                "topic": "os/test/protocol-matrix",
                "client_id": "OSMatrixProbe",
            }
        }
    return {}


class ListenerHarness:
    def __init__(self, protocol: str, host: str, port: int, transport: str):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.transport = transport
        self._queue: "queue.Queue[tuple[float, bytes, Any]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self.started = False
        self.error: Optional[str] = None

    def _runner(self) -> None:
        try:
            if self.transport == "tcp":
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((self.host, self.port))
                    sock.listen(8)
                    sock.settimeout(0.2)
                    self._ready.set()
                    while True:
                        try:
                            conn, addr = sock.accept()
                        except socket.timeout:
                            continue
                        with conn:
                            data = conn.recv(65535)
                            if data:
                                self._queue.put((time.perf_counter(), bytes(data), addr))
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((self.host, self.port))
                    sock.settimeout(0.2)
                    self._ready.set()
                    while True:
                        try:
                            data, addr = sock.recvfrom(65535)
                        except socket.timeout:
                            continue
                        if data:
                            self._queue.put((time.perf_counter(), bytes(data), addr))
        except Exception as exc:
            self.error = str(exc)
            self._ready.set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._runner, daemon=True, name=f"listen-{self.protocol}")
        self._thread.start()
        self._ready.wait(timeout=1.0)
        self.started = self.error is None

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def wait_for_payload(self, expected: bytes, timeout_s: float) -> Optional[Dict[str, Any]]:
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            remain = max(0.01, deadline - time.perf_counter())
            try:
                t_recv, data, addr = self._queue.get(timeout=min(0.05, remain))
            except queue.Empty:
                continue
            if data == expected:
                return {
                    "matched": True,
                    "received_at_perf": t_recv,
                    "addr": str(addr),
                    "size": len(data),
                }
        return None


def run_network_matrix(host: str, base_port: int, timeout_s: float) -> Dict[str, Any]:
    modules: Dict[str, Any] = {}
    load_errors: Dict[str, str] = {}
    listener_errors: Dict[str, str] = {}
    listeners: Dict[str, ListenerHarness] = {}
    receiver_ports = {name: base_port + idx for idx, name in enumerate(NETWORK_PROTOCOLS)}

    for name in NETWORK_PROTOCOLS:
        module, err = import_module_safe(PROTOCOL_MODULES[name])
        if err:
            load_errors[name] = err
            continue
        modules[name] = module

    for recv_name in NETWORK_PROTOCOLS:
        harness = ListenerHarness(
            protocol=recv_name,
            host=host,
            port=receiver_ports[recv_name],
            transport=RECEIVER_TRANSPORT[recv_name],
        )
        harness.start()
        if harness.error:
            listener_errors[recv_name] = harness.error
        else:
            listeners[recv_name] = harness

    rows = []
    expected_compatible = 0
    compatibility_pass = 0
    hard_failures = 0

    for sender in NETWORK_PROTOCOLS:
        send_module = modules.get(sender)
        sender_err = load_errors.get(sender)
        for receiver in NETWORK_PROTOCOLS:
            receiver_harness = listeners.get(receiver)
            receiver_err = listener_errors.get(receiver)
            receiver_transport = RECEIVER_TRANSPORT[receiver]
            is_compatible = receiver_transport in SENDER_TRANSPORTS.get(sender, set())
            payload = (
                f"OS_MATRIX|sender={sender}|receiver={receiver}|ts={time.time_ns()}".encode("utf-8")
            )

            row: Dict[str, Any] = {
                "sender": sender,
                "receiver": receiver,
                "receiver_transport": receiver_transport,
                "expected_compatible": bool(is_compatible),
                "send_ok": False,
                "received": False,
                "latency_ms": None,
                "status": "",
                "reason": "",
            }

            if is_compatible:
                expected_compatible += 1

            if sender_err:
                row["status"] = "IMPORT_ERROR"
                row["reason"] = f"sender import failed: {sender_err}"
                if is_compatible:
                    hard_failures += 1
                rows.append(row)
                continue

            if receiver_err:
                row["status"] = "IMPORT_ERROR"
                row["reason"] = f"receiver import/listen failed: {receiver_err}"
                if is_compatible:
                    hard_failures += 1
                rows.append(row)
                continue

            if not send_module or not hasattr(send_module, "send"):
                row["status"] = "SEND_MISSING"
                row["reason"] = "sender has no send()"
                if is_compatible:
                    hard_failures += 1
                rows.append(row)
                continue

            if not receiver_harness:
                row["status"] = "LISTENER_UNAVAILABLE"
                row["reason"] = "receiver harness unavailable"
                if is_compatible:
                    hard_failures += 1
                rows.append(row)
                continue

            receiver_harness.clear()
            send_cfg = build_sender_config(sender, host, receiver_ports[receiver], receiver_transport)
            t0 = time.perf_counter()
            try:
                send_ok = bool(send_module.send(payload, send_cfg))
            except Exception as exc:
                send_ok = False
                row["reason"] = f"send exception: {exc}"
            row["send_ok"] = send_ok

            match = None
            if send_ok:
                match = receiver_harness.wait_for_payload(payload, timeout_s=timeout_s)
            row["received"] = bool(match)

            if match:
                row["latency_ms"] = round((match["received_at_perf"] - t0) * 1000.0, 3)
                row["received_addr"] = match["addr"]

            if is_compatible:
                if send_ok and match:
                    row["status"] = "PASS"
                    row["reason"] = "expected compatible and packet observed"
                    compatibility_pass += 1
                elif not send_ok:
                    row["status"] = "FAIL_SEND"
                    row["reason"] = row["reason"] or "expected compatible but send() returned False"
                    hard_failures += 1
                else:
                    row["status"] = "FAIL_NO_RECEIVE"
                    row["reason"] = "expected compatible but no packet observed by receiver"
                    hard_failures += 1
            else:
                if match:
                    row["status"] = "UNEXPECTED_ROUTE"
                    row["reason"] = "expected incompatible but receiver got payload"
                    hard_failures += 1
                else:
                    row["status"] = "EXPECTED_INCOMPATIBLE"
                    row["reason"] = "transport mismatch path intentionally not routable"

            rows.append(row)

    summary = {
        "total_pairs": len(rows),
        "expected_compatible_pairs": expected_compatible,
        "compatible_pass_pairs": compatibility_pass,
        "hard_failures": hard_failures,
        "load_errors": load_errors,
        "listener_errors": listener_errors,
        "receiver_ports": receiver_ports,
    }
    return {"rows": rows, "summary": summary}


def probe_non_network_protocols(host: str) -> Dict[str, Any]:
    rows = []
    for name in NON_NETWORK_PROTOCOLS:
        module_path = PROTOCOL_MODULES[name]
        module, err = import_module_safe(module_path)
        entry: Dict[str, Any] = {
            "protocol": name,
            "module": module_path,
            "status": "",
            "reason": "",
            "smoke_send_ok": None,
        }
        if err:
            entry["status"] = "IMPORT_ERROR"
            entry["reason"] = err
            rows.append(entry)
            continue

        has_send = bool(hasattr(module, "send") and callable(getattr(module, "send")))
        has_listen = bool(hasattr(module, "listen") and callable(getattr(module, "listen")))
        has_receive = bool(hasattr(module, "receive") and callable(getattr(module, "receive")))
        supported = True
        if hasattr(module, "is_supported") and callable(getattr(module, "is_supported")):
            try:
                supported = bool(module.is_supported())
            except Exception:
                supported = False

        entry["has_send"] = has_send
        entry["has_listen"] = has_listen
        entry["has_receive"] = has_receive
        entry["supported"] = supported

        smoke_send_ok = None
        if has_send:
            try:
                cfg = build_sender_config(name, host, 1883, "udp")
                smoke_send_ok = bool(module.send(b"OS_NON_NETWORK_SMOKE", cfg))
            except Exception:
                smoke_send_ok = False
        entry["smoke_send_ok"] = smoke_send_ok

        if name == "quic" and not supported:
            entry["status"] = "DEPENDENCY_GATED"
        elif name in ("iwip", "uip"):
            entry["status"] = "SIMULATOR_STUB"
        elif name in ("uart", "rs485", "can", "lora"):
            entry["status"] = "HARDWARE_GATED"
        elif name == "mqtt":
            entry["status"] = "BROKER_GATED"
        else:
            entry["status"] = "INFO"

        entry["reason"] = LIMITATION_HINTS.get(name, "")
        rows.append(entry)

    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"rows": rows, "summary": counts}


def collect_capabilities() -> Dict[str, Any]:
    rows = []
    for name, module_path in PROTOCOL_MODULES.items():
        module, err = import_module_safe(module_path)
        item = {
            "protocol": name,
            "module": module_path,
            "import_ok": err is None,
            "error": err,
            "has_send": False,
            "has_listen": False,
            "has_receive": False,
            "supported": True,
        }
        if module is not None:
            item["has_send"] = bool(hasattr(module, "send") and callable(getattr(module, "send")))
            item["has_listen"] = bool(hasattr(module, "listen") and callable(getattr(module, "listen")))
            item["has_receive"] = bool(hasattr(module, "receive") and callable(getattr(module, "receive")))
            if hasattr(module, "is_supported") and callable(getattr(module, "is_supported")):
                try:
                    item["supported"] = bool(module.is_supported())
                except Exception:
                    item["supported"] = False
        rows.append(item)
    return {"rows": rows}


def write_report(output_path: Path, report: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exhaustive protocol interoperability validator")
    parser.add_argument("--host", default="127.0.0.1", help="Listener bind host for local matrix")
    parser.add_argument("--base-port", type=int, default=19080, help="Base port for receiver listeners")
    parser.add_argument("--timeout", type=float, default=1.5, help="Receive wait timeout for each pair")
    parser.add_argument(
        "--output",
        default="data/benchmarks/protocol_matrix_exhaustive_latest.json",
        help="Report output path (relative to repo root)",
    )
    return parser.parse_args()


def main() -> int:
    repo_root = _ensure_import_path()
    args = parse_args()

    report: Dict[str, Any] = {
        "started_at": utc_now_iso(),
        "host": args.host,
        "base_port": args.base_port,
        "timeout_seconds": args.timeout,
        "capabilities": collect_capabilities(),
    }

    matrix = run_network_matrix(host=args.host, base_port=args.base_port, timeout_s=args.timeout)
    report["network_matrix"] = matrix
    report["non_network_probes"] = probe_non_network_protocols(host=args.host)
    report["finished_at"] = utc_now_iso()
    report["notes"] = [
        "PASS means expected-compatible path observed on receiver callback.",
        "EXPECTED_INCOMPATIBLE means matrix pair is intentionally unroutable due transport mismatch.",
        "Non-network protocols are graded as dependency/simulator/hardware gated with smoke send hints.",
    ]

    out_path = (repo_root / args.output).resolve()
    write_report(out_path, report)

    summary = matrix["summary"]
    print("=" * 80)
    print("Protocol Matrix Exhaustive Validation")
    print("=" * 80)
    print(f"Compatible pairs: {summary['compatible_pass_pairs']}/{summary['expected_compatible_pairs']}")
    print(f"Hard failures:    {summary['hard_failures']}")
    print(f"Report written:   {out_path}")

    return 1 if int(summary["hard_failures"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
