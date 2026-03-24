#!/usr/bin/env python3
"""
Standalone localhost call/send simulator (independent of OpenSynaptic stack).

Usage examples:
  python -u scripts/standalone_localhost_sim.py --mode demo --protocol udp
  python -u scripts/standalone_localhost_sim.py --mode server --protocol tcp --port 19090
  python -u scripts/standalone_localhost_sim.py --mode client --protocol tcp --port 19090 --count 10
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from typing import Any


def _make_payload(seq: int) -> bytes:
    obj: dict[str, Any] = {
        "event": "standalone_local_send",
        "seq": seq,
        "ts": time.time(),
        "sensor": {
            "id": f"V{seq % 8}",
            "status": "OK",
            "value": round(20.0 + seq * 0.1, 4),
            "unit": "Pa",
        },
    }
    return json.dumps(obj, ensure_ascii=True).encode("utf-8")


def run_udp_server(host: str, port: int, stop_event: threading.Event, timeout_s: float = 0.5) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        sock.settimeout(timeout_s)
        print(f"[UDP server] listening on {host}:{port}")
        while not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            text = data.decode("utf-8", errors="replace")
            print(f"[UDP server] recv from {addr}: {text}")
            sock.sendto(b"ACK", addr)


def run_tcp_server(host: str, port: int, stop_event: threading.Event, timeout_s: float = 0.5) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(8)
        server.settimeout(timeout_s)
        print(f"[TCP server] listening on {host}:{port}")
        while not stop_event.is_set():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(timeout_s)
                while not stop_event.is_set():
                    try:
                        data = conn.recv(65535)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    print(f"[TCP server] recv from {addr}: {text}")
                    conn.sendall(b"ACK")


def run_udp_client(host: str, port: int, count: int, interval_s: float, timeout_s: float = 1.0) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        for i in range(count):
            payload = _make_payload(i)
            t0 = time.perf_counter()
            sock.sendto(payload, (host, port))
            try:
                ack, _ = sock.recvfrom(1024)
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[UDP client] seq={i} ack={ack!r} rtt_ms={rtt_ms:.3f}")
            except socket.timeout:
                print(f"[UDP client] seq={i} timeout waiting ack")
            time.sleep(max(0.0, interval_s))


def run_tcp_client(host: str, port: int, count: int, interval_s: float, timeout_s: float = 1.0) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_s)
        sock.connect((host, port))
        for i in range(count):
            payload = _make_payload(i)
            t0 = time.perf_counter()
            sock.sendall(payload)
            try:
                ack = sock.recv(1024)
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[TCP client] seq={i} ack={ack!r} rtt_ms={rtt_ms:.3f}")
            except socket.timeout:
                print(f"[TCP client] seq={i} timeout waiting ack")
            time.sleep(max(0.0, interval_s))


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone localhost call/send simulator")
    parser.add_argument("--mode", choices=["demo", "server", "client"], default="demo")
    parser.add_argument("--protocol", choices=["udp", "tcp"], default="udp")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19090)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.2, help="seconds between sends")
    parser.add_argument("--startup-wait", type=float, default=0.15, help="demo mode server warmup")
    args = parser.parse_args()

    stop_event = threading.Event()

    if args.mode == "server":
        try:
            if args.protocol == "udp":
                run_udp_server(args.host, args.port, stop_event)
            else:
                run_tcp_server(args.host, args.port, stop_event)
        except KeyboardInterrupt:
            pass
        return 0

    if args.mode == "client":
        if args.protocol == "udp":
            run_udp_client(args.host, args.port, args.count, args.interval)
        else:
            run_tcp_client(args.host, args.port, args.count, args.interval)
        return 0

    # demo: start server in background and run client immediately
    if args.protocol == "udp":
        server_fn = run_udp_server
        client_fn = run_udp_client
    else:
        server_fn = run_tcp_server
        client_fn = run_tcp_client

    th = threading.Thread(target=server_fn, args=(args.host, args.port, stop_event), daemon=True)
    th.start()
    time.sleep(max(0.0, args.startup_wait))
    try:
        client_fn(args.host, args.port, args.count, args.interval)
    finally:
        stop_event.set()
        th.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

