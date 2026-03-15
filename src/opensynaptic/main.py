import os
import queue
import re
import shlex
import sys
import threading

from opensynaptic.CLI import main as cli_main


def _idle_timeout_seconds():
    raw = os.environ.get("OS_CLI_IDLE_TIMEOUT", "20")
    try:
        return max(0.0, float(raw))
    except Exception:
        return 20.0


def _read_cmdline_with_timeout(timeout_s):
    q = queue.Queue(maxsize=1)

    def _reader():
        try:
            line = input("[OpenSynaptic] Enter a command (example: os-help). Idle timeout will auto-run `run`: ")
            q.put(line)
        except Exception:
            try:
                q.put("")
            except Exception:
                pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    try:
        return q.get(timeout=timeout_s)
    except queue.Empty:
        return None


def _parse_cmdline(line):
    text = (line or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except Exception:
        return text.split()


def _split_chained_commands(line):
    text = (line or '').strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r'\s*(?:&&|;)\s*', text) if p and p.strip()]
    return parts


def _is_run_like(tokens):
    if not tokens:
        return False
    head = str(tokens[0]).strip().lower()
    return head in ('run', 'os-run')


def _run_cli_line(line):
    tokens = _parse_cmdline(line)
    if not tokens:
        return 0
    try:
        return cli_main(tokens)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        return code


def _cli_loop(initial_line=None):
    pending = []
    if initial_line:
        pending.extend(_split_chained_commands(initial_line))

    while True:
        if pending:
            line = pending.pop(0)
        else:
            try:
                line = input('[OpenSynaptic CLI] > ')
            except EOFError:
                return 0
            except KeyboardInterrupt:
                return 0

        text = (line or '').strip()
        if not text:
            continue
        if text.lower() in ('exit', 'quit', 'q'):
            return 0

        chunks = _split_chained_commands(text)
        if len(chunks) > 1 and not pending:
            pending.extend(chunks[1:])
            text = chunks[0]

        tokens = _parse_cmdline(text)
        if not tokens:
            continue
        code = _run_cli_line(text)
        if code not in (0, None):
            continue

        if _is_run_like(tokens):
            continue


def _fallback_args():
    raw = (os.environ.get("OS_CLI_FALLBACK_ARGS", "") or "").strip()
    if not raw:
        return ["run"]
    parsed = _parse_cmdline(raw)
    return parsed if parsed else ["run"]


def main(argv=None):
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if args:
        return cli_main(args)

    timeout_s = _idle_timeout_seconds()
    cmdline = _read_cmdline_with_timeout(timeout_s)
    parsed = _parse_cmdline(cmdline)
    if parsed:
        if _is_run_like(parsed):
            return cli_main(parsed)
        return _cli_loop(cmdline)
    return cli_main(_fallback_args())


def tui_main():
    return cli_main(["tui"])


def cli_entry():
    return cli_main()


if __name__ == '__main__':
    raise SystemExit(main())
