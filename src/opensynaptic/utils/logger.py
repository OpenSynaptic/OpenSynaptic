import sys, traceback
from pathlib import Path
import logging
from opensynaptic.utils import (
    LogMsg,
    MESSAGES,
    EnvironmentMissingError,
    classify_exception,
)

class LevelFilter(logging.Filter):

    def __init__(self, max_level):
        super().__init__()
        self.max_level = max_level

    def filter(self, record):
        return record.levelno <= self.max_level

class OSLogger:

    def __init__(self, name='OS'):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        if not self.logger.handlers:
            fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S')
            h_out = logging.StreamHandler(sys.stdout)
            h_out.setFormatter(fmt)
            h_out.setLevel(logging.DEBUG)
            h_out.addFilter(LevelFilter(logging.INFO))
            self.logger.addHandler(h_out)
            h_err = logging.StreamHandler(sys.stderr)
            h_err.setFormatter(fmt)
            h_err.setLevel(logging.WARNING)
            self.logger.addHandler(h_err)
            self.logger.setLevel(logging.DEBUG)
        self._error_listeners = []

    def _caller_lineno(self, depth=2):
        try:
            return sys._getframe(depth).f_lineno
        except Exception:
            return None

    def _format(self, mid, eid, exc, ctx=None):
        lineno = self._caller_lineno(3)
        msg = {'mid': mid, 'eid': eid, 'msg': str(exc), 'ctx': ctx, 'loc': f'{Path.cwd()}:{lineno}' if lineno is not None else None}
        return msg

    def info(self, mid, eid, msg, ctx=None):
        out = self._format(mid, eid, msg, ctx)
        self.logger.info(out)
        return out

    def err(self, mid, eid, exc, ctx=None):
        out = self._format(mid, eid, exc, ctx)
        out['error_type'] = type(exc).__name__
        out.update(classify_exception(exc))
        if isinstance(exc, EnvironmentMissingError):
            out['environment'] = exc.as_dict()
        try:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:
            pass
        self.logger.error(out)
        event = {'mid': mid, 'eid': eid, 'error': exc, 'payload': out}
        for listener in list(self._error_listeners):
            try:
                listener(event)
            except Exception:
                continue
        return {'error': out}

    def add_error_listener(self, listener):
        if callable(listener) and listener not in self._error_listeners:
            self._error_listeners.append(listener)

    def remove_error_listener(self, listener):
        if listener in self._error_listeners:
            self._error_listeners.remove(listener)

    def log_with_const(self, level, msg_key, **kwargs):
        template = MESSAGES.get(msg_key, None)
        text = template.format(**kwargs) if template else msg_key.value if isinstance(msg_key, LogMsg) else str(msg_key)
        if level.lower() in ('info', 'debug'):
            self.logger.info(text)
        elif level.lower() == 'warning':
            self.logger.warning(text)
        else:
            self.logger.error(text)
        return {'msg': text}
os_log = OSLogger()
