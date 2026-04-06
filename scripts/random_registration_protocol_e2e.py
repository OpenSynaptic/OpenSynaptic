#!/usr/bin/env python3
"""
Randomized end-to-end validation:
1) New device registration via real ensure_id UDP handshake.
2) Random protocol send to random protocol listener.
3) Receiver-side protocol parsing verification.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import queue
import random
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Optional


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


NETWORK_PROTOCOLS = ("udp", "tcp", "matter", "zigbee", "bluetooth")

PROTOCOL_MODULES: Dict[str, str] = {
    "udp": "opensynaptic.core.transport_layer.protocols.udp",
    "tcp": "opensynaptic.core.transport_layer.protocols.tcp",
    "matter": "opensynaptic.services.transporters.drivers.matter",
    "zigbee": "opensynaptic.services.transporters.drivers.zigbee",
    "bluetooth": "opensynaptic.core.physical_layer.protocols.bluetooth",
}

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
        self._thread = threading.Thread(target=self._runner, daemon=True, name=f"rand-listen-{self.protocol}")
        self._thread.start()
        self._ready.wait(timeout=1.0)

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
                    "received_at_perf": t_recv,
                    "addr": str(addr),
                    "payload": data,
                }
        return None


class LocalHandshakeResponder:
    def __init__(self, host: str, port: int, state_dir: Path):
        self.host = host
        self.port = port
        self.state_dir = state_dir
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._error: Optional[str] = None

    @property
    def error(self) -> Optional[str]:
        return self._error

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="local-handshake-responder")
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        self._stop_event.set()
        # Wake recvfrom
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as wake_sock:
            wake_sock.settimeout(0.2)
            try:
                wake_sock.sendto(b"\x00", (self.host, self.port))
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            from opensynaptic.core.pycore.handshake import OSHandshakeManager
            from opensynaptic.utils.id_allocator import IDAllocator

            self.state_dir.mkdir(parents=True, exist_ok=True)
            handshake = OSHandshakeManager(
                target_sync_count=3,
                registry_dir=str(self.state_dir / "registry"),
                secure_store_path=str(self.state_dir / "secure_sessions.json"),
            )
            allocator = IDAllocator(
                base_dir=str(self.state_dir),
                start_id=1,
                end_id=4294967294,
                persist_file="id_allocation.json",
            )
            handshake.id_allocator = allocator

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.host, self.port))
                sock.settimeout(0.2)
                self._ready_event.set()
                while not self._stop_event.is_set():
                    try:
                        data, addr = sock.recvfrom(4096)
                    except socket.timeout:
                        continue
                    except Exception:
                        continue
                    if not data:
                        continue
                    try:
                        out = handshake.classify_and_dispatch(data, addr)
                    except Exception:
                        continue
                    response = out.get("response") if isinstance(out, dict) else None
                    if response:
                        try:
                            sock.sendto(response, addr)
                        except Exception:
                            pass
        except Exception as exc:
            self._error = str(exc)
            self._ready_event.set()


def generate_sensors(rng: random.Random, idx: int):
    count = rng.randint(1, 4)
    sensors = []
    for i in range(count):
        sid = f"S{idx}_{i}"
        val = round(rng.uniform(0.1, 99.9), 4)
        unit = rng.choice(["Pa", "Cel", "%", "A", "V"])
        sensors.append([sid, "OK", val, unit])
    return sensors


def prepare_node_config(base_cfg: Dict[str, Any], device_id: str, host: str, port: int, backend: str) -> Dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg["device_id"] = device_id
    cfg["assigned_id"] = 4294967295

    client_core = cfg.setdefault("Client_Core", {})
    client_core["server_host"] = host
    client_core["server_port"] = int(port)

    engine = cfg.setdefault("engine_settings", {})
    engine["core_backend"] = backend

    resources = cfg.setdefault("RESOURCES", {})
    app_status = resources.setdefault("application_status", {})
    app_status["mqtt"] = False
    app_status["matter"] = True
    app_status["zigbee"] = True

    transport_status = resources.setdefault("transport_status", {})
    transport_status["udp"] = True
    transport_status["tcp"] = True
    transport_status["quic"] = False
    transport_status["iwip"] = False
    transport_status["uip"] = False

    physical_status = resources.setdefault("physical_status", {})
    physical_status["uart"] = False
    physical_status["rs485"] = False
    physical_status["can"] = False
    physical_status["lora"] = False
    physical_status["bluetooth"] = True

    app_cfg = resources.setdefault("application_config", {})
    app_cfg.setdefault("matter", {})
    app_cfg.setdefault("zigbee", {})
    app_cfg["matter"]["enabled"] = True
    app_cfg["zigbee"]["enabled"] = True

    phy_cfg = resources.setdefault("physical_config", {})
    phy_cfg.setdefault("bluetooth", {})
    phy_cfg["bluetooth"]["enabled"] = True

    # Keep runtime deterministic during stress script execution.
    service_plugins = resources.setdefault("service_plugins", {})
    for key, val in list(service_plugins.items()):
        if isinstance(val, dict):
            val["enabled"] = False
            if "auto_start" in val:
                val["auto_start"] = False

    resources["transporters_status"] = {
        **{k: bool(v) for k, v in app_status.items()},
        **{k: bool(v) for k, v in transport_status.items()},
        **{k: bool(v) for k, v in physical_status.items()},
    }
    return cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Random registration + protocol e2e validator")
    parser.add_argument("--rounds", type=int, default=30, help="Total randomized rounds")
    parser.add_argument("--seed", type=int, default=202611, help="Random seed")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local listeners and handshake server")
    parser.add_argument("--listen-base-port", type=int, default=20080, help="Base port for protocol listeners")
    parser.add_argument("--handshake-port", type=int, default=20888, help="UDP port for local ensure_id responder")
    parser.add_argument("--timeout", type=float, default=1.5, help="Receive timeout in seconds")
    parser.add_argument("--backend", default="pycore", choices=["pycore", "rscore"], help="Core backend for OpenSynaptic node")
    parser.add_argument(
        "--output",
        default="data/benchmarks/random_registration_protocol_e2e_latest.json",
        help="Report output path (relative to repo root)",
    )
    return parser.parse_args()


def main() -> int:
    repo_root = _ensure_import_path()
    args = parse_args()

    # Ensure core selection applies before importing facade symbols.
    os.environ["OPENSYNAPTIC_CORE"] = args.backend
    from opensynaptic.core import OpenSynaptic

    rng = random.Random(args.seed)

    module_map: Dict[str, Any] = {}
    module_errors: Dict[str, str] = {}
    for name, path in PROTOCOL_MODULES.items():
        mod, err = import_module_safe(path)
        if err:
            module_errors[name] = err
        else:
            module_map[name] = mod

    listener_ports = {name: args.listen_base_port + idx for idx, name in enumerate(NETWORK_PROTOCOLS)}
    listeners: Dict[str, ListenerHarness] = {}
    for recv in NETWORK_PROTOCOLS:
        harness = ListenerHarness(
            protocol=recv,
            host=args.host,
            port=listener_ports[recv],
            transport=RECEIVER_TRANSPORT[recv],
        )
        harness.start()
        if harness.error is None:
            listeners[recv] = harness
        else:
            module_errors[f"listener:{recv}"] = harness.error

    base_cfg_path = repo_root / "Config.json"
    base_cfg = json.loads(base_cfg_path.read_text(encoding="utf-8"))

    report: Dict[str, Any] = {
        "started_at": utc_now_iso(),
        "backend": args.backend,
        "seed": args.seed,
        "rounds": args.rounds,
        "module_errors": module_errors,
        "listener_ports": listener_ports,
        "rows": [],
    }

    with TemporaryDirectory(prefix="os-rand-e2e-") as tmp_dir:
        temp_root = Path(tmp_dir)
        responder = LocalHandshakeResponder(args.host, args.handshake_port, temp_root / "responder")
        responder.start()
        if responder.error:
            report["fatal"] = f"local handshake responder failed: {responder.error}"
            out_path = (repo_root / args.output).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Fatal: {report['fatal']}")
            return 1

        try:
            for idx in range(args.rounds):
                device_id = f"RAND_NODE_{idx:04d}"
                node_cfg = prepare_node_config(
                    base_cfg=base_cfg,
                    device_id=device_id,
                    host=args.host,
                    port=args.handshake_port,
                    backend=args.backend,
                )
                cfg_path = temp_root / "nodes" / f"node_{idx:04d}.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(json.dumps(node_cfg, indent=2, ensure_ascii=False), encoding="utf-8")

                row: Dict[str, Any] = {
                    "round": idx,
                    "device_id": device_id,
                    "registered": False,
                    "assigned_id": None,
                    "sender": None,
                    "receiver": None,
                    "expected_compatible": None,
                    "send_ok": False,
                    "received": False,
                    "decode_ok": False,
                    "status": "",
                    "reason": "",
                    "latency_ms": None,
                }

                try:
                    node = OpenSynaptic(config_path=str(cfg_path))
                except Exception as exc:
                    row["status"] = "NODE_INIT_FAIL"
                    row["reason"] = str(exc)
                    report["rows"].append(row)
                    continue

                try:
                    ensure_out = node.ensure_id(args.host, args.handshake_port, device_meta={"kind": "random-e2e", "round": idx})
                    row["registered"] = bool(ensure_out)
                    row["assigned_id"] = int(getattr(node, "assigned_id", 0) or 0)
                    if not row["registered"] or row["assigned_id"] <= 0 or row["assigned_id"] >= 4294967295:
                        row["status"] = "REGISTER_FAIL"
                        row["reason"] = f"ensure_id result={ensure_out} assigned_id={row['assigned_id']}"
                        report["rows"].append(row)
                        continue

                    sensors = generate_sensors(rng, idx)
                    packet, _, _ = node.transmit(
                        sensors=sensors,
                        device_id=device_id,
                        t=int(time.time()),
                    )

                    sender = rng.choice(NETWORK_PROTOCOLS)
                    receiver = rng.choice(NETWORK_PROTOCOLS)
                    row["sender"] = sender
                    row["receiver"] = receiver

                    recv_transport = RECEIVER_TRANSPORT[receiver]
                    expected_compatible = recv_transport in SENDER_TRANSPORTS[sender]
                    row["expected_compatible"] = bool(expected_compatible)

                    send_mod = module_map.get(sender)
                    recv_harness = listeners.get(receiver)
                    if send_mod is None:
                        row["status"] = "SENDER_IMPORT_FAIL"
                        row["reason"] = module_errors.get(sender, "unknown sender import issue")
                        report["rows"].append(row)
                        continue
                    if recv_harness is None:
                        row["status"] = "RECEIVER_LISTEN_FAIL"
                        row["reason"] = module_errors.get(receiver, "receiver listen unavailable")
                        report["rows"].append(row)
                        continue

                    recv_harness.clear()
                    send_cfg = build_sender_config(sender, args.host, listener_ports[receiver], recv_transport)

                    t0 = time.perf_counter()
                    send_ok = bool(send_mod.send(packet, send_cfg))
                    row["send_ok"] = send_ok

                    match = None
                    if send_ok:
                        match = recv_harness.wait_for_payload(packet, timeout_s=args.timeout)
                    row["received"] = bool(match)
                    if match:
                        row["latency_ms"] = round((match["received_at_perf"] - t0) * 1000.0, 3)

                    decode_ok = False
                    decode_reason = ""
                    if match:
                        try:
                            dispatch = node.receive_via_protocol(match["payload"], addr=(args.host, listener_ports[receiver]))
                            if isinstance(dispatch, dict):
                                dispatch_type = str(dispatch.get("type", ""))
                                result = dispatch.get("result", {}) if isinstance(dispatch.get("result", {}), dict) else {}
                                decode_ok = dispatch_type in {"DATA", "CTRL"} and not bool(result.get("error"))
                                if not decode_ok:
                                    decode_reason = f"dispatch_type={dispatch_type} result_error={result.get('error')}"
                            else:
                                decode_reason = f"dispatch returned {type(dispatch)}"
                        except Exception as exc:
                            decode_reason = str(exc)
                    row["decode_ok"] = decode_ok

                    if expected_compatible:
                        if send_ok and row["received"] and decode_ok:
                            row["status"] = "PASS"
                            row["reason"] = "registered and compatible route validated"
                        elif not send_ok:
                            row["status"] = "FAIL_SEND"
                            row["reason"] = "expected compatible but send() returned False"
                        elif not row["received"]:
                            row["status"] = "FAIL_NO_RECEIVE"
                            row["reason"] = "expected compatible but no payload observed"
                        else:
                            row["status"] = "FAIL_DECODE"
                            row["reason"] = decode_reason or "payload arrived but receive_via_protocol failed"
                    else:
                        if row["received"]:
                            row["status"] = "UNEXPECTED_ROUTE"
                            row["reason"] = "transport mismatch should not route but payload was observed"
                        else:
                            row["status"] = "EXPECTED_INCOMPATIBLE"
                            row["reason"] = "transport mismatch path intentionally unroutable"

                except Exception as exc:
                    row["status"] = "ROUND_EXCEPTION"
                    row["reason"] = str(exc)

                report["rows"].append(row)

        finally:
            responder.stop()

    rows = report["rows"]
    summary: Dict[str, Any] = {
        "total_rounds": len(rows),
        "registered_ok": sum(1 for r in rows if r.get("registered")),
        "pass_count": sum(1 for r in rows if r.get("status") == "PASS"),
        "expected_incompatible_count": sum(1 for r in rows if r.get("status") == "EXPECTED_INCOMPATIBLE"),
        "hard_failures": sum(
            1
            for r in rows
            if r.get("status")
            in {
                "NODE_INIT_FAIL",
                "REGISTER_FAIL",
                "SENDER_IMPORT_FAIL",
                "RECEIVER_LISTEN_FAIL",
                "FAIL_SEND",
                "FAIL_NO_RECEIVE",
                "FAIL_DECODE",
                "ROUND_EXCEPTION",
                "UNEXPECTED_ROUTE",
            }
        ),
        "unique_assigned_ids": len({r.get("assigned_id") for r in rows if isinstance(r.get("assigned_id"), int) and r.get("assigned_id") > 0}),
    }

    report["summary"] = summary
    report["finished_at"] = utc_now_iso()

    out_path = (repo_root / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print("Random Registration + Protocol E2E")
    print("=" * 80)
    print(f"Rounds:            {summary['total_rounds']}")
    print(f"Registered OK:     {summary['registered_ok']}")
    print(f"PASS:              {summary['pass_count']}")
    print(f"Expected mismatch: {summary['expected_incompatible_count']}")
    print(f"Hard failures:     {summary['hard_failures']}")
    print(f"Report written:    {out_path}")

    return 1 if int(summary["hard_failures"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
