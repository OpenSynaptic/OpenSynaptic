import os
import sys
import json
from pathlib import Path
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

def read_json(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        os_log.err('PTH', 'IO', e, {'path': path})
        return {}

def write_json(path, obj, indent=4):
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        os_log.err('PTH', 'IO', e, {'path': path})
        return False

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

def get_config_path():
    return os.path.join(ctx.root, 'Config.json')

def get_registry_path(aid):
    s_val = str(aid).zfill(10)
    rel_dir = os.path.join('data', 'device_registry', s_val[0:2], s_val[2:4])
    return os.path.join(ctx.root, rel_dir, f'{aid}.json')

def get_lib_path(*args):
    res_root = ctx.config.get('RESOURCES', {}).get('root', 'libraries')
    return os.path.join(ctx.root, res_root, *args)
