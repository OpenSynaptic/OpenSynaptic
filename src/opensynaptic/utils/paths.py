import os
import sys
import json
import time
import tempfile
import threading
from pathlib import Path
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

_WRITE_LOCKS = {}
_WRITE_LOCKS_GUARD = threading.Lock()


def _get_write_lock(lock_path):
    key = os.path.normcase(os.path.abspath(lock_path))
    with _WRITE_LOCKS_GUARD:
        lock = _WRITE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _WRITE_LOCKS[key] = lock
        return lock

def read_json(path):
    if not path or not os.path.exists(path):
        return {}
    last_exc = None
    for attempt in range(3):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except PermissionError as e:
            last_exc = e
            if attempt < 2:
                time.sleep(0.01 * (attempt + 1))
                continue
            break
        except json.JSONDecodeError as e:
            last_exc = e
            break  # 文件格式已损坏，重试无法修复
        except Exception as e:
            os_log.err('PTH', 'IO', e, {'path': path})
            return {}
    if last_exc is not None:
        os_log.err('PTH', 'IO', last_exc, {'path': path})
    return {}

def write_json(path, obj, indent=4):
    if not path:
        return False
    temp_path = None
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = os.path.normcase(os.path.abspath(str(target) + '.lock'))
        with _get_write_lock(lock_path):
            with open(lock_path, 'a+b') as lock_fp:
                file_locked = False
                if os.name == 'nt':
                    import msvcrt
                    lock_fp.seek(0, os.SEEK_END)
                    if lock_fp.tell() == 0:
                        lock_fp.write(b'0')
                        lock_fp.flush()
                    lock_fp.seek(0)
                    for attempt in range(200):
                        try:
                            msvcrt.locking(lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
                            file_locked = True
                            break
                        except OSError as e:
                            win_err = getattr(e, 'winerror', None)
                            errno = getattr(e, 'errno', None)
                            if (win_err in (33, 36) or errno in (13, 36)) and attempt < 199:
                                time.sleep(0.005 * (attempt + 1))
                                continue
                            raise
                    if not file_locked:
                        raise OSError('failed to acquire lock for {}'.format(lock_path))
                else:
                    import fcntl
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
                    file_locked = True
                try:
                    fd, temp_path = tempfile.mkstemp(prefix=f'.{target.name}.', suffix='.tmp', dir=str(target.parent))
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(obj, f, indent=indent, ensure_ascii=False)
                        f.flush()
                        try:
                            os.fsync(f.fileno())
                        except OSError:
                            pass
                    for attempt in range(20):
                        try:
                            os.replace(temp_path, str(target))
                            temp_path = None
                            break
                        except PermissionError:
                            if attempt >= 19:
                                raise
                            time.sleep(0.005 * (attempt + 1))
                        except OSError as e:
                            if getattr(e, 'winerror', None) in (5, 32) and attempt < 19:
                                time.sleep(0.005 * (attempt + 1))
                                continue
                            raise
                finally:
                    if os.name == 'nt' and file_locked:
                        lock_fp.seek(0)
                        msvcrt.locking(lock_fp.fileno(), msvcrt.LK_UNLCK, 1)
                    elif os.name != 'nt' and file_locked:
                        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        return True
    except Exception as e:
        os_log.err('PTH', 'IO', e, {'path': path})
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

class OSContext:

    def __init__(self):
        try:
            self.root = self._detect_root()
            src_path = os.path.join(self.root, 'src')
            if os.path.isdir(src_path) and src_path not in sys.path:
                sys.path.insert(0, src_path)
            self.config = read_json(os.path.join(self.root, 'Config.json'))
            res_conf = (self.config or {}).get('RESOURCES', {})
            registry_conf = res_conf.get('registry')
            if registry_conf:
                if os.path.isabs(registry_conf):
                    self.registry_dir = registry_conf
                else:
                    self.registry_dir = os.path.join(self.root, registry_conf)
            else:
                self.registry_dir = os.path.join(self.root, 'data', 'device_registry')
            os_log.log_with_const('info', LogMsg.READY, root=self.root)
        except Exception as e:
            os_log.err('PTH', 'BOOT', e, {})

    def _detect_root(self):
        p = Path(__file__).resolve().parent
        for parent in [p] + list(p.parents):
            if (parent / 'Config.json').exists():
                return str(parent)
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ctx = OSContext()


def get_user_config_path():
    return str((Path.home() / '.config' / 'opensynaptic' / 'Config.json').resolve())


def get_project_config_path():
    return os.path.join(ctx.root, 'Config.json')


def get_config_path(prefer_user=True):
    if prefer_user:
        return get_user_config_path()
    return get_project_config_path()

def get_registry_path(aid):
    s_val = str(aid).zfill(10)
    rel_dir = os.path.join('data', 'device_registry', s_val[0:2], s_val[2:4])
    return os.path.join(ctx.root, rel_dir, f'{aid}.json')

def get_lib_path(*args):
    res_root = ctx.config.get('RESOURCES', {}).get('root', 'libraries')
    candidate = os.path.join(ctx.root, res_root, *args)
    if not os.path.exists(candidate):
        # Fall back to package-internal libraries when running pip-installed
        _pkg_lib = Path(__file__).resolve().parent.parent / 'libraries'
        pkg_candidate = str(_pkg_lib.joinpath(*args)) if args else str(_pkg_lib)
        if os.path.exists(pkg_candidate):
            return pkg_candidate
    return candidate
