import io
import json
import re
import shlex
import threading
from contextlib import redirect_stderr, redirect_stdout


class CliExecutor:
    def __init__(self, service):
        self.service = service
        self._lock = threading.RLock()
        self._jobs = {}
        self._seq = 0
        self._latest_run_stats = {}
        self._latest_perf_stats = {}

    def ingest_output_line(self, line):
        text = str(line or '').strip()
        if not text:
            return
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and isinstance(payload.get('run_stats'), dict):
                self._latest_run_stats = dict(payload.get('run_stats', {}))
                return
        except Exception:
            pass
        if 'Performance stats' not in text:
            return
        pattern = (
            r"recv=(?P<recv>\d+)\s+ok=(?P<ok>\d+)\s+fail=(?P<fail>\d+)\s+drop=(?P<drop>\d+)"
            r"\s+backlog=(?P<backlog_cur>\d+)/(?:\s*)?(?P<backlog_max>\d+)"
            r"\s+avg=(?P<avg>[0-9.]+)ms\s+max=(?P<max>[0-9.]+)ms"
            r"\s+pps\(in/out\)=(?P<pps_in>[0-9.]+)/(?P<pps_out>[0-9.]+)"
        )
        m = re.search(pattern, text)
        if not m:
            return
        self._latest_perf_stats = {
            'recv': int(m.group('recv')),
            'ok': int(m.group('ok')),
            'fail': int(m.group('fail')),
            'drop': int(m.group('drop')),
            'backlog_current': int(m.group('backlog_cur')),
            'backlog_max': int(m.group('backlog_max')),
            'avg_ms': float(m.group('avg')),
            'max_ms': float(m.group('max')),
            'pps_in': float(m.group('pps_in')),
            'pps_out': float(m.group('pps_out')),
        }

    @staticmethod
    def coerce_tokens(command_line):
        line = str(command_line or '').strip()
        if not line:
            return []
        return shlex.split(line)

    def run_tokens(self, tokens):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        rc = 1
        try:
            from opensynaptic.CLI.app import main as os_cli_main
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                try:
                    maybe = os_cli_main(tokens)
                    rc = int(maybe or 0)
                except SystemExit as exc:
                    rc = int(exc.code) if isinstance(exc.code, int) else 1
        except Exception as exc:
            err_buf.write(str(exc))
            rc = 1
        stdout_text = out_buf.getvalue()
        stderr_text = err_buf.getvalue()
        for ln in stdout_text.splitlines():
            self.ingest_output_line(ln)
        for ln in stderr_text.splitlines():
            self.ingest_output_line(ln)
        return rc, stdout_text, stderr_text

    def execute(self, command_line):
        tokens = self.coerce_tokens(command_line)
        if not tokens:
            return False, {'error': 'empty command'}
        rc, out, err = self.run_tokens(tokens)
        return rc == 0, {'ok': rc == 0, 'command': ' '.join(tokens), 'exit_code': int(rc), 'stdout': out, 'stderr': err}

    def overview_metrics(self):
        run = dict(self._latest_run_stats or {})
        perf = dict(self._latest_perf_stats or {})
        return {
            'run_stats': {
                'status': run.get('status', 'idle'),
                'uptime_s': int(run.get('uptime_s', 0) or 0),
                'packets_processed': int(run.get('packets_processed', 0) or 0),
                'avg_packet_latency_ms': float(run.get('avg_packet_latency_ms', 0.0) or 0.0),
                'tick_errors': int(run.get('tick_errors', 0) or 0),
            },
            'performance_stats': {
                'recv': int(perf.get('recv', 0) or 0),
                'ok': int(perf.get('ok', 0) or 0),
                'fail': int(perf.get('fail', 0) or 0),
                'drop': int(perf.get('drop', 0) or 0),
                'backlog_current': int(perf.get('backlog_current', 0) or 0),
                'backlog_max': int(perf.get('backlog_max', 0) or 0),
                'avg_ms': float(perf.get('avg_ms', 0.0) or 0.0),
                'max_ms': float(perf.get('max_ms', 0.0) or 0.0),
                'pps_in': float(perf.get('pps_in', 0.0) or 0.0),
                'pps_out': float(perf.get('pps_out', 0.0) or 0.0),
            },
        }

