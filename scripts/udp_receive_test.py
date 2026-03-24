#!/usr/bin/env python3
"""UDP receive test harness for OpenSynaptic packet unpacking."""

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ensure_import_path() -> Path:
    """Allow running from repo without requiring editable install."""
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def _json_dump(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return repr(data)


def _extract_meta(decoded: Any) -> Dict[str, Any]:
    if isinstance(decoded, dict):
        meta = decoded.get("__packet_meta__")
        if isinstance(meta, dict):
            return meta
    return {}


def _build_node(config_path: Path):
    from opensynaptic.core import OpenSynaptic

    return OpenSynaptic(config_path=str(config_path))


def _restore_transmit_content(decoded: Any) -> Dict[str, Any]:
    """Rebuild a transmit-like view from decoded payload for quick validation."""
    if not isinstance(decoded, dict):
        return {}
    if decoded.get("error"):
        return {"error": decoded.get("error")}

    restored: Dict[str, Any] = {
        "device_id": decoded.get("id"),
        "device_status": decoded.get("s"),
        "timestamp_raw": decoded.get("t_raw"),
        "sensors": [],
    }
    if "msg" in decoded:
        restored["msg"] = decoded.get("msg")
    if "geohash" in decoded:
        restored["geohash"] = decoded.get("geohash")
    if "url" in decoded:
        restored["url"] = decoded.get("url")

    i = 1
    sensors: List[List[Any]] = []
    while True:
        sid = decoded.get(f"s{i}_id")
        if sid is None:
            break
        sensors.append([
            sid,
            decoded.get(f"s{i}_s"),
            decoded.get(f"s{i}_v"),
            decoded.get(f"s{i}_u"),
        ])
        i += 1
    restored["sensors"] = sensors
    restored["sensors_count"] = len(sensors)
    return restored


def _recv_once(
    sock: socket.socket,
    node,
    buffer_size: int,
    verbose: bool,
    raw_decode_compare: bool,
    auto_reply: bool,
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[str, int]]]:
    packet, addr = sock.recvfrom(buffer_size)
    dispatch = node.receive_via_protocol(packet, addr)

    cmd = packet[0] if packet else -1
    p_type = dispatch.get("type") if isinstance(dispatch, dict) else "UNKNOWN"
    print(f"[recv] from={addr} len={len(packet)} cmd=0x{cmd:02X} type={p_type}")

    result = dispatch.get("result") if isinstance(dispatch, dict) else None
    meta = _extract_meta(result)
    if meta:
        print(f"[meta] {meta}")

    restored = _restore_transmit_content(result)
    if restored:
        print("[restored-transmit]")
        print(_json_dump(restored))

    if verbose:
        print("[dispatch]")
        print(_json_dump(dispatch))

    if raw_decode_compare:
        decoded_direct = node.receive(packet)
        print("[receive() decoded]")
        print(_json_dump(decoded_direct))

    if auto_reply and isinstance(dispatch, dict):
        response = dispatch.get("response")
        if isinstance(response, (bytes, bytearray)) and response:
            sent = sock.sendto(bytes(response), addr)
            print(f"[reply] sent={sent} bytes to {addr}")

    return dispatch if isinstance(dispatch, dict) else None, addr


def _serve_tcp(node, host: str, port: int, verbose: bool, raw_decode_compare: bool, auto_reply: bool):
    """TCP server for receiving OpenSynaptic packets."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(1)
    print(f"[ready] listening tcp://{host}:{port}")
    print("[hint] Ctrl+C to stop")

    try:
        while True:
            try:
                conn, addr = sock.accept()
                print(f"[tcp-connect] {addr}")
                data = conn.recv(65535)
                if data:
                    dispatch = node.receive_via_protocol(data, addr)
                    cmd = data[0] if data else -1
                    p_type = dispatch.get("type") if isinstance(dispatch, dict) else "UNKNOWN"
                    print(f"[recv] from={addr} len={len(data)} cmd=0x{cmd:02X} type={p_type}")
                    
                    result = dispatch.get("result") if isinstance(dispatch, dict) else None
                    meta = _extract_meta(result)
                    if meta:
                        print(f"[meta] {meta}")
                    
                    restored = _restore_transmit_content(result)
                    if restored:
                        print("[restored-transmit]")
                        print(_json_dump(restored))
                    
                    if verbose:
                        print("[dispatch]")
                        print(_json_dump(dispatch))
                    
                    if raw_decode_compare:
                        decoded_direct = node.receive(data)
                        print("[receive() decoded]")
                        print(_json_dump(decoded_direct))
                    
                    if auto_reply and isinstance(dispatch, dict):
                        response = dispatch.get("response")
                        if isinstance(response, (bytes, bytearray)) and response:
                            conn.sendall(bytes(response))
                            print(f"[reply] sent={len(response)} bytes to {addr}")
                
                conn.close()
            except Exception as exc:
                print(f"[error] tcp loop: {exc}")
    except KeyboardInterrupt:
        print("\n[stop] interrupted")
    finally:
        sock.close()


def main() -> int:
    repo_root = _ensure_import_path()

    parser = argparse.ArgumentParser(
        description="OpenSynaptic multi-protocol receive test",
    )
    parser.add_argument(
        "--protocol",
        choices=["udp", "tcp"],
        default="udp",
        help="Protocol to listen on (udp, tcp)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument(
        "--config",
        default=str(repo_root / "Config.json"),
        help="Absolute path to Config.json",
    )
    parser.add_argument("--buffer-size", type=int, default=65535, help="Recv buffer size")
    parser.add_argument("--timeout", type=float, default=None, help="Socket timeout seconds")
    parser.add_argument("--once", action="store_true", help="Receive one packet then exit")
    parser.add_argument("--verbose", action="store_true", help="Print full dispatch JSON")
    parser.add_argument(
        "--raw-decode-compare",
        action="store_true",
        help="Also call node.receive(packet) for direct-decode comparison",
    )
    parser.add_argument(
        "--auto-reply",
        action="store_true",
        help="Automatically send protocol response if dispatch returns response bytes",
    )

    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"[error] Config not found: {config_path}")
        return 2

    node = _build_node(config_path)

    protocol = args.protocol.lower()
    
    if protocol == "tcp":
        _serve_tcp(node, args.host, args.port, args.verbose, args.raw_decode_compare, args.auto_reply)
        return 0

    # UDP (default)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if args.timeout is not None:
        sock.settimeout(max(0.0, float(args.timeout)))
    sock.bind((args.host, args.port))

    print(f"[ready] listening udp://{args.host}:{args.port}")
    print(f"[ready] config={config_path}")
    print("[hint] Ctrl+C to stop")

    try:
        while True:
            try:
                _recv_once(
                    sock=sock,
                    node=node,
                    buffer_size=args.buffer_size,
                    verbose=args.verbose,
                    raw_decode_compare=args.raw_decode_compare,
                    auto_reply=args.auto_reply,
                )
                if args.once:
                    break
            except socket.timeout:
                print("[timeout] no packet received")
                if args.once:
                    break
            except Exception as exc:
                print(f"[error] recv loop: {exc}")
                if args.once:
                    return 1
    except KeyboardInterrupt:
        print("\n[stop] interrupted")
    finally:
        sock.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

