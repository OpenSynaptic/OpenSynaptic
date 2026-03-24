import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
p = HERE
PROJECT_ROOT = None
for _ in range(8):
    if (p / 'src').is_dir() or (p / 'pyproject.toml').exists() or (p / 'Config.json').exists():
        PROJECT_ROOT = p
        break
    if p.parent == p:
        break
    p = p.parent
if PROJECT_ROOT is None:
    PROJECT_ROOT = HERE
PROJECT_ROOT = str(PROJECT_ROOT)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
for _p in (PROJECT_ROOT, SRC_DIR):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from opensynaptic.core import OpenSynaptic
except Exception:
    try:
        from src.opensynaptic.core import OpenSynaptic
    except Exception as e:
        raise ImportError(f"Cannot import OpenSynaptic. Ensure this repository's root (containing 'src/')\nis on PYTHONPATH or run this script from the project root.\nTried PROJECT_ROOT={PROJECT_ROOT!r} and SRC_DIR={SRC_DIR!r}\nsys.path = {sys.path!r}") from e
import socket
import json
import signal
import threading
import time
import queue
import hashlib
from opensynaptic.utils import (
    os_log,
    LogMsg,
)

class ReceiverStats:

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.received_packets = 0
        self.received_bytes = 0
        self.completed_packets = 0
        self.failed_packets = 0
        self.dropped_packets = 0
        self.sent_responses = 0
        self.sent_bytes = 0
        self.total_latency_ms = 0.0
        self.max_latency_ms = 0.0
        self.current_backlog = 0
        self.max_backlog = 0

    def on_receive(self, size):
        with self._lock:
            self.received_packets += 1
            self.received_bytes += max(0, int(size))

    def on_enqueue(self, backlog):
        with self._lock:
            self.current_backlog = backlog
            if backlog > self.max_backlog:
                self.max_backlog = backlog

    def on_drop(self, backlog):
        with self._lock:
            self.dropped_packets += 1
            self.current_backlog = backlog
            if backlog > self.max_backlog:
                self.max_backlog = backlog

    def on_complete(self, latency_ms, sent_bytes=0):
        with self._lock:
            self.completed_packets += 1
            self.total_latency_ms += latency_ms
            if latency_ms > self.max_latency_ms:
                self.max_latency_ms = latency_ms
            if sent_bytes > 0:
                self.sent_responses += 1
                self.sent_bytes += int(sent_bytes)

    def on_failure(self, latency_ms):
        with self._lock:
            self.failed_packets += 1
            self.total_latency_ms += latency_ms
            if latency_ms > self.max_latency_ms:
                self.max_latency_ms = latency_ms

    def snapshot(self):
        with self._lock:
            elapsed = max(time.time() - self.started_at, 1e-06)
            finished = self.completed_packets + self.failed_packets
            avg_latency = self.total_latency_ms / finished if finished else 0.0
            return {'uptime_s': round(elapsed, 2), 'received_packets': self.received_packets, 'completed_packets': self.completed_packets, 'failed_packets': self.failed_packets, 'dropped_packets': self.dropped_packets, 'received_bytes': self.received_bytes, 'sent_responses': self.sent_responses, 'sent_bytes': self.sent_bytes, 'backlog': self.current_backlog, 'max_backlog': self.max_backlog, 'avg_latency_ms': round(avg_latency, 3), 'max_latency_ms': round(self.max_latency_ms, 3), 'ingress_pps': round(self.received_packets / elapsed, 2), 'complete_pps': round(self.completed_packets / elapsed, 2)}

class ShardedPacketDispatcher:

    def __init__(self, worker_fn, stats, shard_count=4, queue_size=64):
        self.worker_fn = worker_fn
        self.stats = stats
        self.shard_count = max(1, int(shard_count))
        self.queue_size = max(1, int(queue_size))
        self.stop_event = threading.Event()
        self.queues = [queue.Queue(maxsize=self.queue_size) for _ in range(self.shard_count)]
        self._threads = []

    def start(self):
        for idx in range(self.shard_count):
            t = threading.Thread(target=self._worker_loop, args=(idx,), daemon=True, name=f'os-rx-shard-{idx}')
            t.start()
            self._threads.append(t)

    def _compute_shard(self, addr):
        key = f'{addr[0]}:{addr[1]}' if addr else 'unknown'
        digest = hashlib.blake2b(key.encode('utf-8'), digest_size=4).digest()
        return int.from_bytes(digest, 'big') % self.shard_count

    def submit(self, data, addr):
        shard = self._compute_shard(addr)
        item = (time.perf_counter(), data, addr)
        q = self.queues[shard]
        try:
            q.put_nowait(item)
            self.stats.on_enqueue(self.backlog())
            return True
        except queue.Full:
            self.stats.on_drop(self.backlog())
            os_log.log_with_const('warning', LogMsg.RX_OVERLOAD_DROP, shard=shard, backlog=self.backlog(), capacity=self.capacity())
            return False

    def backlog(self):
        return sum((q.qsize() for q in self.queues))

    def capacity(self):
        return self.shard_count * self.queue_size

    def _worker_loop(self, shard):
        q = self.queues[shard]
        while not self.stop_event.is_set():
            try:
                item = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                q.task_done()
                break
            started_at, data, addr = item
            try:
                sent_bytes = int(self.worker_fn(data, addr) or 0)
                self.stats.on_complete((time.perf_counter() - started_at) * 1000.0, sent_bytes=sent_bytes)
            except Exception as e:
                self.stats.on_failure((time.perf_counter() - started_at) * 1000.0)
                os_log.log_with_const('error', LogMsg.RX_WORKER_ERROR, shard=shard, error=str(e))
            finally:
                q.task_done()
                self.stats.on_enqueue(self.backlog())

    def stop(self, drain=True):
        if drain:
            for q in self.queues:
                q.join()
        self.stop_event.set()
        for q in self.queues:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        for t in self._threads:
            t.join(timeout=2.0)


class ReceiverRuntime:

    def __init__(self, node, listen_ip='0.0.0.0', listen_port=8080, shard_count=None, queue_size=32, report_interval_s=60.0):
        self.node = node
        self.listen_ip = str(listen_ip or '0.0.0.0')
        self.listen_port = int(listen_port)
        self.shard_count = int(shard_count or max(2, os.cpu_count() or 2))
        self.queue_size = int(queue_size)
        self.report_interval_s = float(report_interval_s)

        self.stop_event = threading.Event()
        self.stats = ReceiverStats()
        self.dispatcher = None
        self._sock = None
        self._thread = None

    def _serve_loop(self):
        self.node.protocol.parser = self.node.fusion
        next_report_at = time.time() + self.report_interval_s

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            self._sock = s
            s.bind((self.listen_ip, self.listen_port))
            s.settimeout(1.0)

            def handle_packet(data, addr):
                cmd_hex = f'0x{data[0]:02X}'
                os_log.log_with_const('info', LogMsg.RX_PACKET_IN, addr=addr, cmd=cmd_hex, size=len(data))
                dispatch_result = self.node.protocol.classify_and_dispatch(data, addr)
                ptype = dispatch_result.get('type')
                result = dispatch_result.get('result')
                response = dispatch_result.get('response')
                sent_bytes = 0
                if ptype == 'DATA':
                    os_log.log_with_const('info', LogMsg.RX_DATA_PACKET, preview=json.dumps(result, ensure_ascii=False)[:240])
                elif ptype == 'CTRL':
                    os_log.log_with_const('info', LogMsg.RX_CTRL_PACKET, preview=str(result)[:240])
                    if response:
                        s.sendto(response, addr)
                        sent_bytes = len(response)
                        os_log.log_with_const('info', LogMsg.RX_RESPONSE_SENT, addr=addr, size=len(response))
                else:
                    os_log.log_with_const('warning', LogMsg.RX_UNKNOWN_PACKET, preview=str(result)[:240])
                    if response:
                        s.sendto(response, addr)
                        sent_bytes = len(response)
                return sent_bytes

            self.dispatcher = ShardedPacketDispatcher(
                worker_fn=handle_packet,
                stats=self.stats,
                shard_count=self.shard_count,
                queue_size=self.queue_size,
            )
            self.dispatcher.start()
            os_log.log_with_const('info', LogMsg.RX_WORKERS_READY, shards=self.shard_count, queue_size=self.queue_size, capacity=self.dispatcher.capacity())
            try:
                while not self.stop_event.is_set():
                    try:
                        try:
                            data, addr = s.recvfrom(4096)
                        except socket.timeout:
                            data = None
                            addr = None
                        if data:
                            self.stats.on_receive(len(data))
                            self.dispatcher.submit(data, addr)
                        now = time.time()
                        if now >= next_report_at:
                            snap = self.stats.snapshot()
                            os_log.log_with_const('info', LogMsg.RX_PERF, received=snap['received_packets'], completed=snap['completed_packets'], failed=snap['failed_packets'], dropped=snap['dropped_packets'], backlog=snap['backlog'], max_backlog=snap['max_backlog'], avg_latency_ms=snap['avg_latency_ms'], max_latency_ms=snap['max_latency_ms'], ingress_pps=snap['ingress_pps'], complete_pps=snap['complete_pps'])
                            next_report_at = now + self.report_interval_s
                    except Exception as e:
                        os_log.log_with_const('error', LogMsg.RX_SOCKET_ERROR, error=str(e))
            finally:
                if self.dispatcher:
                    self.dispatcher.stop(drain=True)
                snap = self.stats.snapshot()
                os_log.log_with_const('info', LogMsg.RX_FINAL_STATS, snapshot=json.dumps(snap, ensure_ascii=False))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        os_log.log_with_const('info', LogMsg.RX_SERVER_START, port=self.listen_port)
        self._thread = threading.Thread(target=self._serve_loop, daemon=True, name='os-receiver-runtime')
        self._thread.start()

    def stop(self):
        self.stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def get_stats(self):
        return self.stats.snapshot()

def main():
    cfg_path = os.path.join(PROJECT_ROOT, 'Config.json')
    node = OpenSynaptic(cfg_path)
    runtime = ReceiverRuntime(node=node, listen_ip='0.0.0.0', listen_port=8080, shard_count=max(2, os.cpu_count() or 2), queue_size=32, report_interval_s=60.0)

    def _signal_handler(sig, frame):
        os_log.log_with_const('warning', LogMsg.RX_SIGNAL_STOP)
        runtime.stop_event.set()
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, 'SIGTERM'):
        try:
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass
    runtime.start()
    try:
        while not runtime.stop_event.is_set():
            time.sleep(0.2)
    finally:
        runtime.stop()
if __name__ == '__main__':
    main()
