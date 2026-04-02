import json
import os
import math
import random
import copy
import tempfile
import socket
from pathlib import Path
import logging
import sys
import time
from types import SimpleNamespace
from opensynaptic.core import get_core_manager
from opensynaptic.services.env_guard.main import EnvironmentGuardService
from opensynaptic.services.plugin_registry import (
    ensure_and_mount_plugin,
    list_builtin_plugins,
    normalize_plugin_name,
)
from opensynaptic.utils import (
    build_native_all,
    build_guidance,
    get_toolchain_report,
    EnvironmentMissingError,
    os_log,
    LogMsg,
    NativeLibraryUnavailable,
    has_native_library,
    ctx,
    get_user_config_path,
    classify_exception,
)
from opensynaptic.utils.errors import ErrorType
from opensynaptic.CLI.build_parser import build_parser


_ENV_GUARD_STANDALONE = None
_AUTO_NATIVE_REPAIR_ATTEMPTED = False



def _apply_quiet_mode(args):
    if not bool(getattr(args, 'quiet', False)):
        return
    try:
        os_log.logger.setLevel(logging.WARNING)
        for h in os_log.logger.handlers:
            h.setLevel(logging.WARNING)
    except Exception:
        pass


def _log_cli_result_payload(payload):
    if isinstance(payload, dict):
        summary = {'keys': sorted(list(payload.keys()))}
        if 'status' in payload:
            summary['status'] = payload.get('status')
        if 'reloaded' in payload:
            summary['reloaded'] = payload.get('reloaded')
        if 'ok' in payload:
            summary['ok'] = payload.get('ok')
        text = json.dumps(summary, ensure_ascii=False, default=str)
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=text)
        return
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        text = str(payload)
    os_log.log_with_const('info', LogMsg.CLI_RESULT, result=text[:240] + (' ...' if len(text) > 240 else ''))


def _print_cli_payload(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _render_help_text(parser, full: bool = False) -> None:
    if full:
        parser.print_help()
        return
    print("""
\u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
\u2502                    OpenSynaptic CLI Help                      \u2502
\u2502              2-N-2 IoT Protocol Stack Control Plane           \u2502
\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518

  QUICK START
    status              View system status (ID, transporters, services)
    id-info             Show device identity and ID assignment status
    demo                Local onboarding demo (virtual sensor + web UI)
    transmit            Send a sensor reading  (--sensors for multi-sensor)
    inject              Test pipeline stages   (--module standardize/compress/fuse)

  CORE FEATURES
    run                 Daemon loop  (add --once for a single run)
    snapshot            Full node / service / transporter JSON snapshot
    receive             Start UDP receiver server
    tui                 Dashboard  (add --interactive for live refresh)

  CONFIGURATION
    config-show         Display Config.json  (--section for a specific block)
    config-get          Read a dotted key path  (--key engine_settings.precision)
    config-set          Write a value  (--type int/float/bool/str/json)
    wizard/init         Interactive Config.json generator
    repair-config       Repair/bootstrap user config for local loopback demo
    doctor/diagnose     Run diagnostic checks and repair suggestions
    core                Switch active core backend  (pycore / rscore)

  TESTING & PROFILING
    plugin-test         Run tests  (--profile quick/deep/record for one-flag presets)
      --suite component     Unit component tests
      --suite stress        Concurrent stress tests
      --suite all           Component + stress tests
      --suite compare       pycore vs rscore comparison
      --suite full_load     Full-CPU-saturation stress
      --suite integration   System integration tests
      --suite audit         Driver capability audit
      --profile quick       Fast smoke test          ( 5 000 iters, 1 proc,  b=32)
      --profile deep        Deep stress + auto-profile (50 000 iters, 4 procs, b=64)
      --profile record      pycore vs rscore compare  (10 000 iters, 2 procs, 3 runs)
      --auto-profile        Scan concurrency candidates and pick best config
    pipeline-info       Pipeline config: precision, zero-copy, cache state
    watch               Live-poll a module for state changes

  DEVELOPER TOOLS
    native-check        Check compiler / toolchain availability
    native-build        Build C native bindings
    rscore-build        Compile Rust RSCore crate
    rscore-check        Report Rust DLL availability

  PLUGINS & SERVICES
    plugin-list         List mounted plugins
    plugin-load         Load a plugin by name
    plugin-cmd          Route a sub-command to a plugin CLI handler
    web-user            web_user plugin CLI
    deps                Dependency manager plugin CLI
    env-guard           Environment guard plugin CLI

  UTILITIES
    log-level           Set logger verbosity  (--set debug/info/warning/error)
    transporter-toggle  Enable or disable a transporter  (--enable / --disable)
    reload-protocol     Reload a protocol adapter  (--medium udp/tcp/...)
    transport-status    Show all transporter layer states
    db-status           Show DB engine state
    decode              Decode a hex or Base62 packet to JSON
    time-sync           Request a server timestamp
    ensure-id           Request and persist a device ID from the server

  OTHER
    help                Show this summary
    help --full         Show full argparse reference  (expert mode)

--------------------------------------------------------------
  Common options:
    --config PATH       Path to Config.json  (auto-detected when omitted)
    --quiet             Suppress info logs  (warnings / errors only)
    --yes               First-run wizard: auto-start demo mode
    --no-wizard         Skip first-run wizard prompt
    --once              Run mode: execute once and exit
    --interval N        Polling interval in seconds  (run / watch)
    --duration N        Total run duration in seconds  (0 = unlimited)
    --stats-interval N  Run-mode stats heartbeat in seconds

  Examples:
    os-node status
    os-node transmit --value 100 --unit Pa
    os-node transmit --sensors '[["V1","OK",3.14,"Pa"],["T1","OK",25.3,"Cel"]]'
    os-node inject --module compress --value 22.5 --unit degC
    os-node plugin-test --profile deep
    os-node demo --open-browser
    os-node config-set --key engine_settings.precision --value 6 --type int
    os-node watch --module pipeline --interval 1
""")


def _make_node(config_path):
    manager = get_core_manager()
    if config_path:
        cfg = str(Path(config_path).expanduser().resolve())
    else:
        cfg = str(Path(get_user_config_path()))
    try:
        _self_heal_config(cfg, auto_backup_on_corrupt=True)
    except Exception as exc:
        os_log.err('CLI', 'CONFIG_SELF_HEAL', exc, {'config_path': cfg})
    return manager.create_node(config_path=cfg)


def _load_config_for_cli(config_path):
    if config_path:
        cfg_path = Path(config_path).expanduser().resolve()
    else:
        cfg_path = _demo_config_default_path()
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _backup_broken_config(path: Path) -> str:
    stamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
    backup = path.with_name(f'{path.stem}.bak.{stamp}{path.suffix}')
    backup.write_text(path.read_text(encoding='utf-8', errors='ignore'), encoding='utf-8')
    return str(backup)


def _required_config_defaults() -> dict:
    return {
        'device_id': 'UNKNOWN_NODE',
        'assigned_id': 4294967295,
        'engine_settings': {
            'precision': 4,
            'core_backend': 'pycore',
            'active_standardization': True,
            'active_compression': True,
            'active_collapse': True,
            'zero_copy_transport': True,
            'network_retry': {
                'enabled': True,
                'max_retries': 2,
                'interval_seconds': 1.0,
            },
        },
        'security_settings': {
            'id_lease': {},
        },
        'RESOURCES': {
            'application_status': {},
            'transport_status': {},
            'physical_status': {},
            'application_config': {},
            'transport_config': {},
            'physical_config': {},
            'transporters_status': {},
            'service_plugins': {},
        },
    }


def _self_heal_config(config_path: str, auto_backup_on_corrupt: bool = True) -> dict:
    cfg_path = Path(config_path).expanduser().resolve()
    report = {
        'path': str(cfg_path),
        'exists': cfg_path.exists(),
        'backed_up': None,
        'created': False,
        'changed': False,
        'issues': [],
    }

    payload = {}
    if cfg_path.exists():
        try:
            payload = json.loads(cfg_path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                report['issues'].append('config_root_not_object')
                payload = {}
        except Exception as exc:
            report['issues'].append(f'config_parse_error:{exc.__class__.__name__}')
            if auto_backup_on_corrupt:
                try:
                    report['backed_up'] = _backup_broken_config(cfg_path)
                except Exception:
                    report['issues'].append('config_backup_failed')
            payload = {}
    else:
        report['created'] = True

    changed = _deep_merge_missing(payload, _required_config_defaults())
    if report['created'] or changed:
        _write_json_file(cfg_path, payload)
        report['changed'] = True
    return report


def _standalone_env_guard(config_path=None):
    global _ENV_GUARD_STANDALONE
    if _ENV_GUARD_STANDALONE is not None:
        return _ENV_GUARD_STANDALONE
    cfg = _load_config_for_cli(config_path)
    plugin_cfg = (((cfg.get('RESOURCES', {}) or {}).get('service_plugins', {}) or {}).get('env_guard', {}) or {})
    if plugin_cfg.get('enabled', True) is False:
        return None
    svc = EnvironmentGuardService(node=None)
    svc.config.update(plugin_cfg)
    svc.auto_load()
    _ENV_GUARD_STANDALONE = svc
    return svc


def _notify_env_guard_compiler_missing(config_path, report, guidance_text):
    svc = _standalone_env_guard(config_path)
    if svc is None:
        return
    exc = EnvironmentMissingError(
        message=str(guidance_text or 'No compiler detected.'),
        missing_kind='compiler',
        resource='toolchain',
        install_urls=[
            'https://visualstudio.microsoft.com/visual-cpp-build-tools/',
            'https://www.mingw-w64.org/',
            'https://clang.llvm.org/',
        ],
        details={
            'selected': report.get('selected'),
            'available': report.get('available', []),
            'entries': report.get('entries', {}),
        },
    )
    os_log.err('NATIVE', 'PRECHECK_ENV_MISSING', exc, {'cmd': 'native-check'})


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, '') or '').strip().lower()
    if not raw:
        return bool(default)
    if raw in ('1', 'true', 'yes', 'on'):
        return True
    if raw in ('0', 'false', 'no', 'off'):
        return False
    return bool(default)


def _native_runtime_ready() -> bool:
    try:
        return bool(has_native_library('os_base62')) and bool(has_native_library('os_security'))
    except Exception:
        return False


def _print_native_auto_status(payload: dict) -> None:
    try:
        summary = {
            'reason': payload.get('reason'),
            'attempted': bool(payload.get('attempted')),
            'ok': bool(payload.get('ok')),
            'selected': payload.get('selected'),
            'elapsed_s': payload.get('elapsed_s'),
            'skipped': payload.get('skipped'),
        }
        print('[native-auto] {}'.format(json.dumps(summary, ensure_ascii=False)), file=sys.stderr, flush=True)
    except Exception:
        pass


def _auto_repair_native_runtime(config_path=None, reason='startup', force=False, quiet=False) -> dict:
    global _AUTO_NATIVE_REPAIR_ATTEMPTED

    if not _env_bool('OPENSYNAPTIC_AUTO_NATIVE_REPAIR', default=True):
        return {'attempted': False, 'ok': _native_runtime_ready(), 'reason': reason, 'skipped': 'disabled-by-env'}

    if _native_runtime_ready():
        return {'attempted': False, 'ok': True, 'reason': reason, 'skipped': 'already-ready'}

    if _AUTO_NATIVE_REPAIR_ATTEMPTED and (not force):
        return {'attempted': False, 'ok': _native_runtime_ready(), 'reason': reason, 'skipped': 'already-attempted'}

    _AUTO_NATIVE_REPAIR_ATTEMPTED = True
    os.environ.setdefault('OPENSYNAPTIC_AUTO_BUILD_NATIVE', '1')
    started = time.monotonic()

    try:
        result = build_native_all(
            show_progress=not bool(quiet),
            idle_timeout=15.0,
            max_timeout=180.0,
        )
    except Exception as exc:
        result = {
            'ok': False,
            'error': str(exc),
            'guidance': 'Run `os-node native-check` and `os-node native-build` manually.',
            'precheck': {},
            'selected': None,
            'targets': {},
        }

    if not isinstance(result, dict):
        result = {
            'ok': False,
            'error': 'unexpected build result',
            'guidance': 'Run `os-node native-check` and `os-node native-build` manually.',
            'precheck': {},
            'selected': None,
            'targets': {},
        }

    ok = bool(result.get('ok')) and _native_runtime_ready()
    precheck = result.get('precheck', {}) if isinstance(result.get('precheck', {}), dict) else {}
    if not ok:
        _notify_env_guard_compiler_missing(config_path, precheck, result.get('guidance'))

    return {
        'attempted': True,
        'ok': ok,
        'reason': reason,
        'selected': result.get('selected'),
        'guidance': result.get('guidance'),
        'targets': result.get('targets', {}),
        'error': result.get('error'),
        'elapsed_s': round(time.monotonic() - started, 3),
    }


def _ensure_plugin(node, plugin_name, mode='runtime', load=True):
    key = normalize_plugin_name(plugin_name)
    svc = ensure_and_mount_plugin(node, key, load=load, mode=mode)
    return key, svc


def _dispatch_plugin(node, plugin_name, sub_cmd, args=None, mode='runtime'):
    key, _ = _ensure_plugin(node, plugin_name, mode=mode, load=True)
    argv = [sub_cmd] + list(args or [])
    return node.service_manager.dispatch_plugin_cli(key, argv)


def _config_dotpath_get(config, keypath):
    keys = keypath.split('.')
    current = config
    for key in keys:
        if not isinstance(current, dict):
            raise KeyError(f'Cannot navigate into non-dict at "{key}"')
        if key not in current:
            raise KeyError(f'Key not found: "{key}"')
        current = current[key]
    return current


def _config_dotpath_set(config, keypath, value):
    keys = keypath.split('.')
    current = config
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _cast_value(raw, value_type):
    import json as _json
    if value_type == 'int':
        return int(raw)
    if value_type == 'float':
        return float(raw)
    if value_type == 'bool':
        return raw.lower() not in ('false', '0', 'no', 'off', '')
    if value_type == 'json':
        return _json.loads(raw)
    return raw


def _demo_config_default_path() -> Path:
    return Path(get_user_config_path())


def _demo_temp_config_path() -> Path:
    return Path(tempfile.gettempdir()) / 'opensynaptic_demo' / 'Config.json'


def _read_json_file(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def _deep_merge_missing(target: dict, source: dict) -> bool:
    changed = False
    for key, val in (source or {}).items():
        if key not in target:
            target[key] = copy.deepcopy(val)
            changed = True
            continue
        if isinstance(target.get(key), dict) and isinstance(val, dict):
            if _deep_merge_missing(target[key], val):
                changed = True
    return changed


def _apply_loopback_defaults(cfg: dict) -> dict:
    out = cfg if isinstance(cfg, dict) else {}
    out.setdefault('device_id', 'DEMO_NODE')
    aid = out.get('assigned_id', None)
    if aid in (None, '', 0, '0', 4294967295, '4294967295'):
        out['assigned_id'] = 1

    settings = out.setdefault('OpenSynaptic_Setting', {})
    settings['default_medium'] = 'UDP'

    client = out.setdefault('Client_Core', {})
    client['server_host'] = '127.0.0.1'
    client['server_port'] = 8080

    server = out.setdefault('Server_Core', {})
    server.setdefault('Start_ID', 1)
    server.setdefault('End_ID', 4294967294)
    server['host'] = '127.0.0.1'
    server['port'] = 8080

    resources = out.setdefault('RESOURCES', {})
    resources.setdefault('registry', 'data/device_registry/')

    app_status = resources.setdefault('application_status', {})
    app_status.setdefault('mqtt', False)
    app_status.setdefault('matter', False)
    app_status.setdefault('zigbee', False)

    transport_status = resources.setdefault('transport_status', {})
    transport_status['udp'] = True
    transport_status.setdefault('tcp', False)
    transport_status.setdefault('quic', False)
    transport_status.setdefault('iwip', False)
    transport_status.setdefault('uip', False)

    physical_status = resources.setdefault('physical_status', {})
    physical_status.setdefault('uart', False)
    physical_status.setdefault('rs485', False)
    physical_status.setdefault('can', False)
    physical_status.setdefault('lora', False)
    physical_status.setdefault('bluetooth', False)

    resources['transporters_status'] = {
        **{k: bool(v) for k, v in app_status.items()},
        **{k: bool(v) for k, v in transport_status.items()},
        **{k: bool(v) for k, v in physical_status.items()},
    }

    app_cfg = resources.setdefault('application_config', {})
    app_cfg.setdefault('mqtt', {'enabled': False})
    app_cfg.setdefault('matter', {'enabled': False, 'protocol': 'tcp', 'host': '127.0.0.1', 'port': 5540, 'timeout': 2.0})
    app_cfg.setdefault('zigbee', {'enabled': False, 'protocol': 'udp', 'host': '127.0.0.1', 'port': 6638, 'timeout': 2.0})

    transport_cfg = resources.setdefault('transport_config', {})
    udp_cfg = transport_cfg.setdefault('udp', {})
    udp_cfg['host'] = '127.0.0.1'
    udp_cfg['port'] = 8080
    udp_cfg.setdefault('listen_host', '127.0.0.1')
    udp_cfg.setdefault('listen_port', 8080)

    physical_cfg = resources.setdefault('physical_config', {})
    physical_cfg.setdefault('uart', {})
    physical_cfg.setdefault('rs485', {})
    physical_cfg.setdefault('can', {})
    physical_cfg.setdefault('lora', {})
    physical_cfg.setdefault('bluetooth', {'enabled': False, 'protocol': 'udp', 'host': '127.0.0.1', 'port': 5454, 'timeout': 2.0})

    service_plugins = resources.setdefault('service_plugins', {})
    web_cfg = service_plugins.setdefault('web_user', {})
    web_cfg.setdefault('enabled', True)
    web_cfg.setdefault('mode', 'manual')
    web_cfg['host'] = '127.0.0.1'
    web_cfg['port'] = 8765
    web_cfg.setdefault('auto_start', False)
    web_cfg.setdefault('auth_enabled', False)
    return out


def _build_demo_default_config() -> dict:
    template_path = Path(getattr(ctx, 'root', '') or '') / 'Config.json'
    template = _read_json_file(template_path)
    if not isinstance(template, dict) or not template:
        template = {
            'device_id': 'DEMO_NODE',
            'assigned_id': 1,
            'OpenSynaptic_Setting': {'default_medium': 'UDP'},
            'Client_Core': {'server_host': '127.0.0.1', 'server_port': 8080},
            'Server_Core': {'host': '127.0.0.1', 'port': 8080, 'Start_ID': 1, 'End_ID': 4294967294},
            'engine_settings': {
                'precision': 4,
                'active_standardization': True,
                'active_compression': True,
                'active_collapse': True,
                'zero_copy_transport': True,
            },
            'RESOURCES': {},
            'security_settings': {},
        }
    out = _apply_loopback_defaults(copy.deepcopy(template))
    out.setdefault('config_version', 1)
    out.setdefault('first_run', True)
    return out


def _ensure_demo_config(path: Path) -> dict:
    if path.exists():
        return {'created': False, 'changed': False, 'path': str(path)}
    payload = _build_demo_default_config()
    _write_json_file(path, payload)
    return {'created': True, 'changed': True, 'path': str(path)}


def _repair_demo_config(path: Path) -> dict:
    existed = path.exists()
    current = _read_json_file(path) if existed else {}
    if not isinstance(current, dict):
        current = {}
    before_sig = json.dumps(current, sort_keys=True, ensure_ascii=False)
    baseline = _build_demo_default_config()
    changed = _deep_merge_missing(current, baseline)
    patched = _apply_loopback_defaults(current)
    after_sig = json.dumps(patched, sort_keys=True, ensure_ascii=False)
    if before_sig != after_sig:
        changed = True
    if (not existed) or changed:
        _write_json_file(path, patched)
    return {
        'ok': True,
        'path': str(path),
        'created': not existed,
        'changed': bool((not existed) or changed),
        'mode': 'loopback',
    }


def _friendly_cli_error(exc: Exception) -> dict:
    text = str(exc or '').strip() or exc.__class__.__name__
    low = text.lower()
    cls = classify_exception(exc)
    category = cls.get('category')
    code = cls.get('code')

    templates = {
        ErrorType.CONFIG.value: '配置可能有问题。请检查配置文件路径：{config_path}；建议运行 `os-node wizard` 重新生成配置。',
        ErrorType.NETWORK.value: '网络连接失败。请检查防火墙设置，并确认目标地址与端口正确。',
        ErrorType.CRC.value: 'CRC 校验失败，数据可能在传输中损坏。请检查传输介质和链路稳定性。',
        ErrorType.PLUGIN.value: '插件加载或调用失败。可先运行 `os-node plugin-list` 查看可用插件。',
        ErrorType.RUST_CORE.value: 'Rust 核心加载失败。可安装扩展：`pip install opensynaptic[rscore]`，或切换 `pycore`。',
        ErrorType.AUTH.value: '认证失败。请检查密钥、会话状态和认证配置。',
        ErrorType.DATA.value: '输入数据格式或内容异常。请确认传感器字段和单位是否正确。',
    }

    if 'no assigned physical id' in low or 'ensure_id() first' in low:
        category = ErrorType.CONFIG.value
        text = text or 'device_id is not assigned'

    hint = templates.get(category)
    if hint:
        hint = hint.format(config_path=str(get_user_config_path()))
    payload = {'error': text}
    if code:
        payload['code'] = code
    if category:
        payload['category'] = category
    if hint:
        payload['hint'] = hint
    return payload


def _net_probe(host: str, port: int, timeout: float = 1.0) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(float(timeout))
    try:
        rc = sock.connect_ex((host, int(port)))
        ok = rc == 0
        return {'ok': ok, 'detail': 'reachable' if ok else f'connect_ex={rc}'}
    except Exception as exc:
        return {'ok': False, 'detail': str(exc)}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _diagnose(config_path: str, self_heal: bool = False) -> dict:
    cfg_path = str(Path(config_path).expanduser().resolve())
    report = {
        'ok': True,
        'config_path': cfg_path,
        'checks': {},
        'suggestions': [],
    }

    py_ok = sys.version_info >= (3, 9)
    report['checks']['python'] = {
        'ok': py_ok,
        'version': '{}.{}.{}'.format(*sys.version_info[:3]),
        'required': '>=3.9 (recommended)',
    }
    if not py_ok:
        report['ok'] = False
        report['suggestions'].append('Upgrade Python to 3.9 or newer for better compatibility.')

    cfg_check = _self_heal_config(cfg_path, auto_backup_on_corrupt=True) if self_heal else {
        'path': cfg_path,
        'exists': Path(cfg_path).exists(),
        'created': False,
        'changed': False,
        'backed_up': None,
        'issues': [],
    }
    if not self_heal and Path(cfg_path).exists():
        try:
            parsed = json.loads(Path(cfg_path).read_text(encoding='utf-8'))
            if not isinstance(parsed, dict):
                cfg_check['issues'].append('config_root_not_object')
        except Exception as exc:
            cfg_check['issues'].append(f'config_parse_error:{exc.__class__.__name__}')
    if not cfg_check.get('exists'):
        report['ok'] = False
        report['suggestions'].append('Config.json not found. Run `os-node wizard` to initialize configuration.')
    if cfg_check.get('issues'):
        report['ok'] = False
        if not self_heal:
            report['suggestions'].append('Run `os-node diagnose --self-heal` to auto-backup and repair missing config keys.')
    report['checks']['config'] = cfg_check

    rust_ok = False
    rust_err = None
    try:
        from opensynaptic.core.rscore.codec import has_rs_native
        rust_ok = bool(has_rs_native())
    except Exception as exc:
        rust_ok = False
        rust_err = str(exc)
    report['checks']['rust_core'] = {'ok': rust_ok, 'error': rust_err}
    if not rust_ok:
        report['suggestions'].append('Rust core unavailable. Install with `pip install opensynaptic[rscore]` or run on `pycore`.')

    cfg = _load_config_for_cli(cfg_path)
    resources = (cfg.get('RESOURCES', {}) or {}) if isinstance(cfg, dict) else {}
    transport_status = resources.get('transport_status', {}) if isinstance(resources.get('transport_status', {}), dict) else {}
    transport_cfg = resources.get('transport_config', {}) if isinstance(resources.get('transport_config', {}), dict) else {}
    checks = []
    for name, enabled in sorted(transport_status.items()):
        if not bool(enabled):
            continue
        item = {'name': name, 'enabled': True, 'ok': True, 'detail': 'enabled'}
        cfg_item = transport_cfg.get(name, {}) if isinstance(transport_cfg.get(name, {}), dict) else {}
        host = cfg_item.get('host')
        port = cfg_item.get('port')
        if host and port and name in ('tcp', 'quic', 'iwip', 'uip'):
            probe = _net_probe(str(host), int(port), timeout=0.8)
            item['ok'] = bool(probe.get('ok'))
            item['detail'] = probe.get('detail')
            if not item['ok']:
                report['suggestions'].append(f'Check network route/firewall for {name} -> {host}:{port}.')
        checks.append(item)
    report['checks']['transporters'] = checks
    if any(not x.get('ok', False) for x in checks):
        report['ok'] = False

    return report


def _is_first_run_config(path: Path) -> bool:
    if (not path.exists()):
        return True
    payload = _read_json_file(path)
    return bool(payload.get('first_run', False))


def _mark_first_run_done(path: Path) -> None:
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return
    if payload.get('first_run', False):
        payload['first_run'] = False
        _write_json_file(path, payload)


def _build_demo_sensors(ts: float):
    temp_c = round(23.0 + 2.6 * math.sin(ts / 11.0), 3)
    humid_pct = round(48.0 + 8.0 * math.sin(ts / 17.0), 3)
    pressure_pa = round(101325.0 + 120.0 * math.sin(ts / 7.0), 3)
    return [
        ['T1', 'OK', temp_c, 'Cel'],
        ['H1', 'OK', humid_pct, '%'],
        ['P1', 'OK', pressure_pa, 'Pa'],
    ]


def _wizard_transporter_choices():
    # Keep consistent with current built-in candidates.
    return ['udp', 'tcp', 'quic', 'iwip', 'uip', 'uart', 'rs485', 'can', 'lora', 'mqtt']


def _wizard_prompt(prompt: str, default: str = '') -> str:
    if not sys.stdin or (not sys.stdin.isatty()):
        return str(default or '')
    shown = f"{prompt} [{default}]" if default != '' else prompt
    print(f"{shown}: ", end='', flush=True)
    val = input().strip()
    return val if val else str(default or '')


def _wizard_yes_no(prompt: str, default_yes: bool = True) -> bool:
    default_mark = 'Y/n' if default_yes else 'y/N'
    answer = _wizard_prompt(f"{prompt} ({default_mark})", 'y' if default_yes else 'n').lower()
    return answer in ('y', 'yes', '1', 'true', 'on')


def _apply_wizard_choices(cfg: dict, transporter: str, host: str, port: int, enable_compress: bool, enable_std: bool):
    out = _apply_loopback_defaults(copy.deepcopy(cfg))
    out['first_run'] = False
    out['config_version'] = int(out.get('config_version', 1) or 1)

    resources = out.setdefault('RESOURCES', {})
    app_status = resources.setdefault('application_status', {})
    transport_status = resources.setdefault('transport_status', {})
    physical_status = resources.setdefault('physical_status', {})

    for k in list(app_status.keys()):
        app_status[k] = False
    for k in list(transport_status.keys()):
        transport_status[k] = False
    for k in list(physical_status.keys()):
        physical_status[k] = False

    tr = str(transporter or 'udp').strip().lower()
    if tr in app_status:
        app_status[tr] = True
    elif tr in transport_status:
        transport_status[tr] = True
    elif tr in physical_status:
        physical_status[tr] = True
    else:
        transport_status['udp'] = True
        tr = 'udp'

    resources['transporters_status'] = {
        **{k: bool(v) for k, v in app_status.items()},
        **{k: bool(v) for k, v in transport_status.items()},
        **{k: bool(v) for k, v in physical_status.items()},
    }

    transport_cfg = resources.setdefault('transport_config', {})
    selected_cfg = transport_cfg.setdefault(tr, {})
    selected_cfg['host'] = str(host or '127.0.0.1')
    selected_cfg['port'] = int(port)

    client_cfg = out.setdefault('Client_Core', {})
    client_cfg['server_host'] = str(host or '127.0.0.1')
    client_cfg['server_port'] = int(port)

    engine = out.setdefault('engine_settings', {})
    engine['active_compression'] = bool(enable_compress)
    engine['active_standardization'] = bool(enable_std)
    return out


def _node_id_is_missing(node) -> bool:
    """Return True when *node* has no valid assigned ID.

    Works for both pycore (has ``_is_id_missing()``) and rscore (method may
    be absent) by falling back to a direct sentinel check.
    """
    fn = getattr(node, '_is_id_missing', None)
    if callable(fn):
        return bool(fn())
    # Fallback: compare against MAX_UINT32 sentinel and null-equivalents
    _MAX = 4294967295
    aid = getattr(node, 'assigned_id', None)
    return aid is None or aid == 0 or aid == '' or aid == 'UNKNOWN' or aid == _MAX


def _apply_test_profile(args) -> None:
    """Apply ``--profile`` preset to *args* in-place.

    Called once, right after ``parse_args()``.  When the user passes
    ``--profile quick|deep|record`` the corresponding preset dict is merged
    into *args* so that all downstream ``getattr(args, ...)`` calls see the
    preset values without knowing about ``--profile``.
    """
    from opensynaptic.CLI.parsers.test import PROFILE_PRESETS
    profile = getattr(args, 'profile', None)
    if not profile:
        return
    preset = PROFILE_PRESETS.get(profile, {})
    for key, val in preset.items():
        setattr(args, key, val)


def _handle_transmit_cmd(node, args):
    os_log.log_with_const('info', LogMsg.CLI_ACTION, action='transmit')
    raw_sensors = getattr(args, 'sensors', None)
    sensors_file = getattr(args, 'sensors_file', None)
    tx_sensors = [[args.sensor_id, args.sensor_status, args.value, args.unit]]
    if sensors_file:
        try:
            with open(sensors_file, 'r', encoding='utf-8-sig') as _sf:
                tx_sensors = json.load(_sf)
        except Exception as exc:
            print(json.dumps({'error': f'--sensors-file read failed: {exc}'}, ensure_ascii=False))
            return 1
    elif raw_sensors:
        try:
            tx_sensors = json.loads(raw_sensors)
        except Exception as exc:
            print(json.dumps({'error': f'--sensors JSON parse failed: {exc}'}, ensure_ascii=False))
            return 1

    packet, aid, strategy = node.transmit(
        sensors=tx_sensors,
        device_id=args.device_id,
        device_status=args.status,
    )
    sent = node.dispatch(packet, medium=args.medium)
    packet_cmd = int(packet[0]) if packet else None
    dispatch_path = None
    get_dispatch_path = getattr(node, 'get_last_dispatch_path', None)
    if callable(get_dispatch_path):
        try:
            dispatch_path = get_dispatch_path()
        except Exception:
            dispatch_path = None
    result = {
        'assigned_id': aid,
        'strategy': strategy,
        'packet_len': len(packet),
        'packet_cmd': packet_cmd,
        'dispatch_path': dispatch_path,
        'sensors_count': len(tx_sensors),
        'sent': bool(sent),
    }
    os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if sent else 1



# noinspection PyUnboundLocalVariable
def _main_impl(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_quiet_mode(args)
    # Apply --profile preset before any command reads individual args
    _apply_test_profile(args)
    explicit_cmd = args.command
    cmd = args.command or 'run'
    sensors = None  # branch-local placeholder for static analyzers
    os_log.log_with_const('info', LogMsg.CLI_READY, mode=cmd)

    if cmd in ('help', 'os-help'):
        _render_help_text(parser, full=bool(getattr(args, 'full', False)))
        return 0
    if cmd in ('receive', 'os-receive'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='receive')
        # Import lazily so core.Receiver does not force early core symbol resolution
        # before Config.json-driven backend selection has been applied.
        from opensynaptic.core.Receiver import main as receiver_main
        receiver_main()
        return 0
    if cmd in ('native-check', 'os-native-check'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='native-check')
        timeout_s = max(1.0, float(getattr(args, 'timeout', 8.0)))
        print('[native-check] start timeout={}s'.format(timeout_s), file=sys.stderr, flush=True)
        state = SimpleNamespace(report=None, error=None, last_step='init')

        def _progress(evt):
            step = str(evt.get('step', evt.get('type', 'unknown')))
            state.last_step = step
            ev_elapsed = float(evt.get('elapsed_s', 0.0) or 0.0)
            compiler = evt.get('compiler')
            if compiler:
                print('[native-check][{:.3f}s] {} compiler={}'.format(ev_elapsed, step, compiler), file=sys.stderr, flush=True)
            else:
                print('[native-check][{:.3f}s] {}'.format(ev_elapsed, step), file=sys.stderr, flush=True)

        t0 = time.monotonic()
        try:
            state.report = get_toolchain_report(
                progress_cb=_progress,
                detect_timeout=min(2.0, max(0.2, timeout_s / 4.0)),
                version_timeout=min(2.0, max(0.2, timeout_s / 4.0)),
                overall_timeout=timeout_s,
            )
        except Exception as exc:
            state.error = str(exc)

        if state.report and bool(state.report.get('timeout')):
            payload = {
                'ok': False,
                'error': 'native-check-timeout',
                'elapsed_s': state.report.get('elapsed_s', round(time.monotonic() - t0, 3)),
                'last_step': state.report.get('last_step', state.last_step),
                'hint': build_guidance(state.report),
            }
            if bool(getattr(args, 'json', False)):
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print('native precheck: timeout')
                print('last_step:', payload['last_step'])
                print(payload['hint'])
            return 2

        if state.error:
            payload = {'ok': False, 'error': state.error, 'elapsed_s': round(time.monotonic() - t0, 3)}
            if bool(getattr(args, 'json', False)):
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print('native precheck: error')
                print(state.error)
            return 2

        report = state.report or {}
        payload = {
            'ok': bool(report.get('ok')),
            'selected': report.get('selected'),
            'available': report.get('available', []),
            'entries': report.get('entries', {}),
            'guidance': build_guidance(report),
            'elapsed_s': round(time.monotonic() - t0, 3),
        }
        if not payload['ok']:
            _notify_env_guard_compiler_missing(getattr(args, 'config_path', None), report, payload.get('guidance'))
        if bool(getattr(args, 'json', False)):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print('native precheck: {}'.format('ok' if payload['ok'] else 'not-ready'))
            print('selected:', payload['selected'] or 'none')
            print('available:', ', '.join(payload['available']) if payload['available'] else 'none')
            if payload.get('elapsed_s') is not None:
                print('elapsed_s:', payload['elapsed_s'])
            print(payload['guidance'])
        return 0 if payload['ok'] else 1
    if cmd in ('native-build', 'os-native-build'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='native-build')
        show_progress = not bool(getattr(args, 'no_progress', False))
        idle_timeout = float(getattr(args, 'idle_timeout', 20.0))
        max_timeout = float(getattr(args, 'max_timeout', 300.0))

        def _progress(evt):
            et = str(evt.get('type', ''))
            elapsed = evt.get('elapsed_s', 0.0)
            if et == 'build-start':
                print('[native][0.000s] build-start', file=sys.stderr, flush=True)
            elif et == 'target-start':
                print('[native][{:.3f}s][{}] start compiler={}'.format(elapsed, evt.get('target'), evt.get('compiler')), file=sys.stderr, flush=True)
            elif et == 'heartbeat':
                print('[native][{:.3f}s][{}] running idle={:.3f}s'.format(elapsed, evt.get('target'), float(evt.get('idle_s', 0.0))), file=sys.stderr, flush=True)
            elif et == 'timeout':
                print('[native][{:.3f}s][{}] {}'.format(elapsed, evt.get('target'), evt.get('message')), file=sys.stderr, flush=True)
            elif et == 'target-exit':
                print('[native][{:.3f}s][{}] exit_code={}'.format(elapsed, evt.get('target'), evt.get('exit_code')), file=sys.stderr, flush=True)
            elif et == 'build-end':
                print('[native][{:.3f}s] build-end ok={}'.format(elapsed, evt.get('ok')), file=sys.stderr, flush=True)

        result = build_native_all(
            show_progress=show_progress,
            idle_timeout=idle_timeout,
            max_timeout=max_timeout,
            progress_cb=_progress,
        )
        # Optionally build the Rust crate in the same invocation.
        if bool(getattr(args, 'include_rscore', False)):
            from opensynaptic.core.rscore.build_rscore import build_rscore
            rs_result = build_rscore(release=True, show_progress=show_progress, progress_cb=_progress)
            result.setdefault('targets', {})['os_rscore'] = rs_result
            if not rs_result.get('ok'):
                result['ok'] = False
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result.get('guidance', ''))
            print('selected:', result.get('selected') or 'none')
            for name, info in result.get('targets', {}).items():
                print('{}: {}'.format(name, 'ok' if info.get('ok') else 'build-failed'))
                if info.get('output'):
                    print('  output:', info['output'])
        return 0 if bool(result.get('ok')) else 1
    if cmd in ('rscore-build', 'os-rscore-build'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='rscore-build')
        from opensynaptic.core.rscore.build_rscore import build_rscore
        show_progress = not bool(getattr(args, 'no_progress', False))
        release = not bool(getattr(args, 'debug', False))

        def _rs_progress(evt):
            et = str(evt.get('type', ''))
            elapsed = evt.get('elapsed_s', 0.0)
            if et == 'build-start':
                print('[rscore][0.000s] build-start', file=sys.stderr, flush=True)
            elif et == 'target-start':
                print('[rscore][{:.3f}s] start compiler=cargo'.format(elapsed), file=sys.stderr, flush=True)
            elif et == 'target-exit':
                print('[rscore][{:.3f}s] exit_code={}'.format(elapsed, evt.get('exit_code')), file=sys.stderr, flush=True)
            elif et == 'build-end':
                print('[rscore][{:.3f}s] build-end ok={}'.format(elapsed, evt.get('ok')), file=sys.stderr, flush=True)

        result = build_rscore(release=release, show_progress=show_progress, progress_cb=_rs_progress)
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print('rscore build:', 'ok' if result.get('ok') else 'failed')
            status = result.get('status', '')
            if status == 'cargo-missing':
                print('hint: install Rust from https://rustup.rs/ then re-run rscore-build')
            if result.get('output'):
                print('  output:', result['output'])
        return 0 if bool(result.get('ok')) else 1
    if cmd in ('rscore-check', 'os-rscore-check'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='rscore-check')
        from opensynaptic.core.rscore.codec import has_rs_native, rs_version
        from opensynaptic.core.rscore.build_rscore import _find_cargo, _NATIVE_BIN, _LIB_NAME, _shared_ext
        rs_ok = has_rs_native()
        ver = rs_version() if rs_ok else None
        dll_path = str(_NATIVE_BIN / (_LIB_NAME + _shared_ext()))
        import os as _os
        dll_exists = _os.path.exists(dll_path)
        cargo = _find_cargo()
        manager = get_core_manager()
        active_core = manager.get_active_core_name()
        payload = {
            'rs_native_loaded': rs_ok,
            'version': ver,
            'dll_path': dll_path,
            'dll_exists': dll_exists,
            'cargo_available': cargo is not None,
            'cargo_path': cargo,
            'active_core': active_core,
            'available_cores': manager.available_cores(),
        }
        if bool(getattr(args, 'json', False)):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print('rs_native_loaded :', payload['rs_native_loaded'])
            print('version          :', payload['version'] or 'n/a')
            print('dll_path         :', payload['dll_path'])
            print('dll_exists       :', payload['dll_exists'])
            print('cargo_available  :', payload['cargo_available'])
            print('active_core      :', payload['active_core'])
            print('available_cores  :', ', '.join(payload['available_cores']))
            if not rs_ok and not dll_exists:
                print('hint: run "os-node rscore-build" to compile and install the Rust DLL')
        return 0 if rs_ok else 1
    if cmd in ('env-guard', 'os-env-guard'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='env-guard')
        svc = _standalone_env_guard(getattr(args, 'config_path', None))
        if svc is None:
            print(json.dumps({'ok': False, 'error': 'env_guard is disabled in config'}, ensure_ascii=False))
            return 1
        # Support both positional subcommand and --cmd flag
        # Priority: positional subcommand > --cmd flag > default 'status'
        sub_cmd = (getattr(args, 'subcommand', None) or 
                  getattr(args, 'cmd_flag', None) or 
                  'status')
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        commands = svc.get_cli_commands()
        handler = commands.get(sub_cmd)
        if handler is None:
            print(json.dumps({'error': 'unknown env-guard cmd', 'available': sorted(commands.keys())}, ensure_ascii=False))
            return 1
        return handler(extra_args) or 0

    target_cfg = Path(getattr(args, 'config_path', None)).expanduser().resolve() if getattr(args, 'config_path', None) else _demo_config_default_path()
    if cmd not in ('repair-config', 'os-repair-config'):
        _ensure_demo_config(target_cfg)
        args.config_path = str(target_cfg)

    first_run_state = _is_first_run_config(target_cfg)

    if cmd in ('wizard', 'init', 'os-wizard', 'os-init'):
        base_cfg = _read_json_file(target_cfg)
        if not isinstance(base_cfg, dict):
            base_cfg = _build_demo_default_config()

        if bool(getattr(args, 'default', False)):
            final_cfg = _apply_wizard_choices(
                base_cfg,
                transporter='udp',
                host='127.0.0.1',
                port=8080,
                enable_compress=True,
                enable_std=True,
            )
        else:
            print('[wizard] OpenSynaptic interactive config wizard')
            choices = _wizard_transporter_choices()
            print(f"[wizard] Available transporters: {', '.join(choices)}")
            t_choice = _wizard_prompt('Select transporter', 'udp').strip().lower()
            if t_choice not in choices:
                t_choice = 'udp'
            host = _wizard_prompt('Target host', '127.0.0.1')
            port_raw = _wizard_prompt('Target port', '8080')
            try:
                port = int(port_raw)
            except Exception:
                port = 8080
            enable_std = _wizard_yes_no('Enable standardization', True)
            enable_compress = _wizard_yes_no('Enable compression', True)
            final_cfg = _apply_wizard_choices(
                base_cfg,
                transporter=t_choice,
                host=host,
                port=port,
                enable_compress=enable_compress,
                enable_std=enable_std,
            )

        _write_json_file(target_cfg, final_cfg)
        summary = {
            'ok': True,
            'path': str(target_cfg),
            'default_medium': final_cfg.get('OpenSynaptic_Setting', {}).get('default_medium', 'UDP'),
            'transporters_status': final_cfg.get('RESOURCES', {}).get('transporters_status', {}),
            'active_standardization': final_cfg.get('engine_settings', {}).get('active_standardization', True),
            'active_compression': final_cfg.get('engine_settings', {}).get('active_compression', True),
            'next': 'os-node demo --open-browser',
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if cmd not in ('help', 'os-help', 'demo', 'os-demo', 'repair-config', 'os-repair-config', 'wizard', 'init', 'os-wizard', 'os-init') and first_run_state:
        if bool(getattr(args, 'yes', False)):
            cmd = 'demo'
            args.command = 'demo'
        elif bool(getattr(args, 'no_wizard', False)):
            _mark_first_run_done(target_cfg)
        elif sys.stdin.isatty():
            print('[wizard] Welcome to OpenSynaptic!')
            print('[wizard] Start demo mode now? [Y/n]: ', end='', flush=True)
            choice = (input().strip().lower() if sys.stdin else '')
            if choice in ('', 'y', 'yes'):
                cmd = 'demo'
                args.command = 'demo'
            else:
                _repair_demo_config(target_cfg)
                _mark_first_run_done(target_cfg)
                print('Initialized minimal config for localhost loopback.')
                print('Next: run `os-node demo` or `os-node --help`.')
                if explicit_cmd is None or cmd in ('run', 'os-run'):
                    return 0
        else:
            _mark_first_run_done(target_cfg)

    demo_bootstrap = None
    if cmd in ('repair-config', 'os-repair-config'):
        result = _repair_demo_config(target_cfg)
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"config_path : {result['path']}")
            print(f"created     : {result['created']}")
            print(f"changed     : {result['changed']}")
            print('mode        : loopback (127.0.0.1)')
        return 0 if result.get('ok') else 1

    if cmd in ('doctor', 'os-doctor', 'diagnose', 'os-diagnose'):
        self_heal = bool(getattr(args, 'self_heal', False))
        result = _diagnose(str(target_cfg), self_heal=self_heal)
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            print('diagnose:', 'ok' if result.get('ok') else 'issues-found')
            print('config_path:', result.get('config_path'))
            py = result.get('checks', {}).get('python', {})
            print('python:', py.get('version'), '| required:', py.get('required'))
            rust = result.get('checks', {}).get('rust_core', {})
            print('rust_core:', 'ok' if rust.get('ok') else 'unavailable')
            cfg = result.get('checks', {}).get('config', {})
            print('config_exists:', cfg.get('exists'), '| changed:', cfg.get('changed'), '| backup:', cfg.get('backed_up'))
            tps = result.get('checks', {}).get('transporters', []) or []
            if tps:
                print('transporters:')
                for item in tps:
                    print('  - {}: {} ({})'.format(item.get('name'), 'ok' if item.get('ok') else 'fail', item.get('detail')))
            if result.get('suggestions'):
                print('suggestions:')
                for s in result.get('suggestions', []):
                    print('  -', s)
        return 0 if result.get('ok') else 1

    if cmd in ('demo', 'os-demo'):
        if bool(getattr(args, 'temp_config', False)):
            target_cfg = _demo_temp_config_path()
            args.config_path = str(target_cfg)
        demo_bootstrap = _ensure_demo_config(target_cfg)
        args.config_path = str(target_cfg)

    if first_run_state:
        preflight = _auto_repair_native_runtime(
            config_path=args.config_path,
            reason='first-run-preflight',
            quiet=bool(getattr(args, 'quiet', False)),
        )
        if preflight.get('attempted'):
            _print_native_auto_status(preflight)

    node = None
    try:
        node = _make_node(args.config_path)
    except NativeLibraryUnavailable as exc:
        recovery = _auto_repair_native_runtime(
            config_path=args.config_path,
            reason='node-init-failed',
            force=True,
            quiet=bool(getattr(args, 'quiet', False)),
        )
        if recovery.get('attempted'):
            _print_native_auto_status(recovery)
        if recovery.get('ok'):
            try:
                node = _make_node(args.config_path)
            except NativeLibraryUnavailable as retry_exc:
                exc = retry_exc
        if node is None:
            print(json.dumps({
                'error': str(exc),
                'hint': 'Run `os-node native-check` then `os-node native-build`.',
                'auto_native_repair': {
                    'attempted': recovery.get('attempted'),
                    'ok': recovery.get('ok'),
                    'selected': recovery.get('selected'),
                    'guidance': recovery.get('guidance'),
                },
            }, ensure_ascii=False))
            return 2
    if cmd in ('snapshot', 'os-snapshot'):
        result = {'device_id': node.device_id, 'assigned_id': node.assigned_id, 'services': node.service_manager.snapshot() if hasattr(node, 'service_manager') else {}, 'transporters': sorted(list(node.active_transporters.keys()))}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if cmd in ('time-sync', 'os-time-sync'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='time-sync')
        server_time = node.ensure_time()
        print(json.dumps({'server_time': server_time}, ensure_ascii=False))
        return 0 if server_time else 1
    if cmd in ('ensure-id', 'os-ensure-id'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='ensure-id')
        host = getattr(args, 'host', None) or node.config.get('Client_Core', {}).get('server_host', '127.0.0.1')
        port = getattr(args, 'port', None) or node.config.get('Client_Core', {}).get('server_port', 8080)
        ensure_raw = node.ensure_id(host, port)
        if isinstance(ensure_raw, dict):
            ok = bool(ensure_raw.get('ok', False))
        else:
            ok = bool(ensure_raw)
        print(json.dumps({'ok': ensure_raw, 'assigned_id': node.assigned_id}, ensure_ascii=False))
        return 0 if ok else 1
    if cmd in ('transmit', 'os-transmit'):
        return _handle_transmit_cmd(node, args)
    if cmd in ('tui', 'os-tui'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='tui')
        _, tui_svc = _ensure_plugin(node, 'tui', mode='interactive', load=True)
        section_arg = getattr(args, 'section', None)
        interactive_arg = bool(getattr(args, 'interactive', False))
        interval_arg = float(getattr(args, 'interval', 2.0))
        sections = [section_arg] if section_arg else None
        if interactive_arg:
            tui_svc.run_interactive(interval=interval_arg, sections=sections)
        else:
            print(tui_svc.run_once(sections=sections))
        return 0
    if cmd in ('plugin-list', 'os-plugin-list'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-list')
        snap = node.service_manager.snapshot()
        result = {
            'mounted_plugins': snap.get('mount_index', []),
            'runtime': snap.get('runtime_index', {}),
            'builtin_plugins': list_builtin_plugins(),
        }
        _log_cli_result_payload(result)
        _print_cli_payload(result)
        return 0
    if cmd in ('plugin-load', 'os-plugin-load'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-load')
        key, svc = _ensure_plugin(node, args.name, mode='runtime', load=True)
        result = {'name': key, 'loaded': bool(svc)}
        _log_cli_result_payload(result)
        _print_cli_payload(result)
        return 0 if svc else 1
    if cmd in ('transport-status', 'os-transport-status'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='transport-status')
        result = {
            'active_transporters': sorted(list(node.active_transporters.keys())),
            'transport_status': node.config.get('RESOURCES', {}).get('transport_status', {}),
            'physical_status': node.config.get('RESOURCES', {}).get('physical_status', {}),
            'application_status': node.config.get('RESOURCES', {}).get('application_status', {}),
        }
        _log_cli_result_payload(result)
        _print_cli_payload(result)
        return 0
    if cmd in ('db-status', 'os-db-status'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='db-status')
        result = {'enabled': bool(node.db_manager), 'dialect': getattr(node.db_manager, 'dialect', None)}
        _log_cli_result_payload(result)
        _print_cli_payload(result)
        return 0

    if cmd in ('demo', 'os-demo'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='demo')
        medium = str(getattr(args, 'medium', 'UDP') or 'UDP')
        interval_arg = float(getattr(args, 'interval', 0.0) or 0.0)
        duration = max(0.0, float(getattr(args, 'duration', 0.0) or 0.0))
        once = bool(getattr(args, 'once', False))
        web_host = str(getattr(args, 'web_host', '127.0.0.1') or '127.0.0.1')
        web_port = int(getattr(args, 'web_port', 8765) or 8765)
        open_browser = bool(getattr(args, 'open_browser', False))

        web_started_here = False
        first_success = False
        sent_ok = 0
        sent_fail = 0
        started_at = time.time()
        web_svc = None

        if isinstance(demo_bootstrap, dict) and demo_bootstrap.get('created'):
            print(f"[demo] 首次运行已初始化配置: {demo_bootstrap.get('path')}")
        print('[demo] Virtual sensors: temperature(Cel), humidity(%), pressure(Pa)')

        try:
            _, web_svc = _ensure_plugin(node, 'web_user', mode='runtime', load=True)
            prev_running = bool(getattr(web_svc, 'status', lambda: {})().get('running', False))
            if not prev_running:
                web_started_here = bool(web_svc.start(host=web_host, port=web_port))
                if not web_started_here:
                    raise RuntimeError(f'Web UI start failed at http://{web_host}:{web_port}')

            web_url = f'http://{web_host}:{web_port}'
            print(f'[demo] Web UI: {web_url}')
            print('[demo] Press Ctrl+C to stop demo gracefully.')
            if open_browser:
                try:
                    import webbrowser
                    webbrowser.open(web_url)
                except Exception:
                    pass
            while True:
                ts = time.time()
                sensors = _build_demo_sensors(ts)
                packet, aid, strategy = node.transmit(sensors=sensors, device_status='ONLINE', t=ts)
                sent = bool(node.dispatch(packet, medium=medium))
                if sent:
                    sent_ok += 1
                    if not first_success:
                        first_success = True
                        print('你已经成功发送了第一条数据！')
                else:
                    sent_fail += 1

                if once:
                    break
                if duration and (time.time() - started_at >= duration):
                    break
                sleep_s = max(0.2, interval_arg) if interval_arg > 0 else random.uniform(2.0, 5.0)
                time.sleep(sleep_s)
        except KeyboardInterrupt:
            print('\n[demo] stopped by user', flush=True)
        except Exception as exc:
            print(json.dumps(_friendly_cli_error(exc), ensure_ascii=False))
            return 1
        finally:
            if web_started_here and web_svc is not None:
                try:
                    web_svc.stop()
                except Exception:
                    pass

        try:
            _mark_first_run_done(Path(args.config_path))
        except Exception:
            pass

        result = {
            'ok': bool(first_success),
            'mode': 'loopback',
            'config_path': str(args.config_path),
            'web_url': f'http://{web_host}:{web_port}',
            'medium': medium,
            'sent_ok': sent_ok,
            'sent_fail': sent_fail,
        }
        _log_cli_result_payload(result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if first_success else 1

    # ------------------------------------------------------------------
    # New utility commands
    # ------------------------------------------------------------------

    if cmd in ('status', 'os-status'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='status')
        _id_missing = _node_id_is_missing(node)
        result = {
            'device_id': node.device_id,
            'assigned_id': node.assigned_id,
            'id_assigned': not _id_missing,
            'active_transporters': sorted(list(node.active_transporters.keys())),
            'services': list(node.service_manager.snapshot().get('mount_index', []))
                if hasattr(node, 'service_manager') else [],
            'core_backend': get_core_manager().get_active_core_name(),
            'engine_settings': node.config.get('engine_settings', {}),
        }
        os_log.log_with_const('info', LogMsg.STATUS_SHOW, device_id=str(result['device_id']))
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            assigned_label = 'assigned' if result['id_assigned'] else 'UNASSIGNED (run ensure-id)'
            print(f"device_id      : {result['device_id']}")
            print(f"assigned_id    : {result['assigned_id']}  [{assigned_label}]")
            print(f"core_backend   : {result['core_backend']}")
            print(f"transporters   : {', '.join(result['active_transporters']) or 'none'}")
            print(f"services       : {', '.join(result['services']) or 'none'}")
            settings = result.get('engine_settings', {})
            print(f"precision      : {settings.get('precision', 4)}")
            print(f"zero_copy      : {settings.get('zero_copy_transport', True)}")
        return 0

    if cmd in ('id-info', 'os-id-info'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='id-info')
        result = {
            'device_id': node.device_id,
            'assigned_id': node.assigned_id,
            'assigned': not _node_id_is_missing(node),
            'max_uint32': 4294967295,
            'server_host': node.config.get('Client_Core', {}).get('server_host', None),
            'server_port': node.config.get('Client_Core', {}).get('server_port', None),
        }
        os_log.log_with_const('info', LogMsg.ID_INFO, assigned_id=str(result['assigned_id']))
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"device_id    : {result['device_id']}")
            print(f"assigned_id  : {result['assigned_id']}")
            print(f"assigned     : {result['assigned']}")
            print(f"server       : {result['server_host']}:{result['server_port']}")
            if not result['assigned']:
                print("hint: run 'os-node ensure-id --host <server> --port <port>' to request an ID")
        return 0

    if cmd in ('log-level', 'os-log-level'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='log-level')
        level_str = str(getattr(args, 'level', 'info')).upper()
        level_val = getattr(logging, level_str, logging.INFO)
        try:
            os_log.logger.setLevel(level_val)
            for h in os_log.logger.handlers:
                h.setLevel(level_val)
        except Exception as exc:
            print(json.dumps({'error': str(exc)}, ensure_ascii=False))
            return 1
        os_log.log_with_const('info', LogMsg.LOG_LEVEL_SET, new_level=level_str)
        print(json.dumps({'level': level_str, 'numeric': level_val}, ensure_ascii=False))
        return 0

    if cmd in ('pipeline-info', 'os-pipeline-info'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='pipeline-info')
        settings = node.config.get('engine_settings', {})
        _std = getattr(node, 'standardizer', None)
        _eng = getattr(node, 'engine', None)
        _fus = getattr(node, 'fusion', None)
        result = {
            'core_backend': get_core_manager().get_active_core_name(),
            'active_standardization': settings.get('active_standardization', True),
            'active_compression': settings.get('active_compression', True),
            'active_collapse': settings.get('active_collapse', True),
            'precision': settings.get('precision', 4),
            'zero_copy_transport': settings.get('zero_copy_transport', True),
            'standardizer_registry_size': len(getattr(_std, 'registry', {}) or {}),
            'engine_rev_unit_size': len(getattr(_eng, 'REV_UNIT', {}) or {}),
            'fusion_cached_aids': list((getattr(_fus, '_RAM_CACHE', {}) or {}).keys()),
        }
        os_log.log_with_const('info', LogMsg.PIPELINE_INFO, backend=result['core_backend'])
        if bool(getattr(args, 'json', False)):
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"Core backend          : {result['core_backend']}")
            print(f"Standardization       : {'on' if result['active_standardization'] else 'off'}")
            print(f"Compression           : {'on' if result['active_compression'] else 'off'}")
            print(f"Collapse              : {'on' if result['active_collapse'] else 'off'}")
            print(f"Precision             : {result['precision']} decimal places")
            print(f"Zero-copy transport   : {'on' if result['zero_copy_transport'] else 'off'}")
            print(f"Standardizer registry : {result['standardizer_registry_size']} entries")
            print(f"Rev-unit table        : {result['engine_rev_unit_size']} entries")
            print(f"Fusion cached AIDs    : {result['fusion_cached_aids']}")
        return 0

    if cmd in ('run', 'os-run'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='run')
        host = getattr(args, 'host', None) or node.config.get('Client_Core', {}).get('server_host', '127.0.0.1')
        port = getattr(args, 'port', None) or node.config.get('Client_Core', {}).get('server_port', 8080)
        ensure_raw = node.ensure_id(host, port)
        if isinstance(ensure_raw, dict):
            ensure_ok = bool(ensure_raw.get('ok', False))
        else:
            ensure_ok = bool(ensure_raw)
        once = bool(getattr(args, 'once', False))
        interval = float(getattr(args, 'interval', 5.0))
        duration = float(getattr(args, 'duration', 0.0))
        result = {
            'ok': ensure_ok,
            'ensure_id': ensure_raw,
            'assigned_id': node.assigned_id,
            'mode': 'once' if once else 'persistent',
        }
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        if not ensure_ok:
            return 1
        if once:
            return 0

        receiver_runtime = None
        try:
            cfg = node.config if isinstance(node.config, dict) else {}
            role_cfg = cfg.get('OpenSynaptic_Setting', {}) if isinstance(cfg.get('OpenSynaptic_Setting', {}), dict) else {}
            server_role_enabled = bool(role_cfg.get('Server_Core', False))
            run_cfg = ((cfg.get('engine_settings', {}) or {}).get('run_loop', {}) or {}) if isinstance(cfg.get('engine_settings', {}), dict) else {}
            auto_receive_enabled = bool(run_cfg.get('auto_receive', True)) if isinstance(run_cfg, dict) else True

            if server_role_enabled and auto_receive_enabled:
                from opensynaptic.core.Receiver import ReceiverRuntime
                server_cfg = cfg.get('Server_Core', {}) if isinstance(cfg.get('Server_Core', {}), dict) else {}
                listen_ip = str(server_cfg.get('host', '0.0.0.0') or '0.0.0.0')
                listen_port = int(server_cfg.get('port', 8080) or 8080)
                receiver_runtime = ReceiverRuntime(node=node, listen_ip=listen_ip, listen_port=listen_port)
                receiver_runtime.start()
                node.receiver = receiver_runtime
                os_log.log_with_const(
                    'info',
                    LogMsg.CLI_RESULT,
                    result=json.dumps(
                        {
                            'receiver_auto_started': True,
                            'role_gate': 'OpenSynaptic_Setting.Server_Core',
                            'listen_ip': listen_ip,
                            'listen_port': listen_port,
                        },
                        ensure_ascii=False,
                    ),
                )
            else:
                reason = 'OpenSynaptic_Setting.Server_Core=false' if (not server_role_enabled) else 'engine_settings.run_loop.auto_receive=false'
                os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps({'receiver_auto_started': False, 'reason': reason}, ensure_ascii=False))
        except Exception as _rx_e:
            os_log.err('CLI', 'RUN_RX_BOOT', _rx_e, {})

        start_at = time.time()
        stats_interval_s = 60.0
        try:
            run_cfg = (((node.config or {}).get('engine_settings', {}) or {}).get('run_loop', {}) or {})
            if isinstance(run_cfg, dict):
                stats_interval_s = max(5.0, float(run_cfg.get('stats_interval_seconds', 60.0) or 60.0))
        except Exception:
            stats_interval_s = 60.0
        cli_stats_interval = getattr(args, 'stats_interval', None)
        if cli_stats_interval is not None:
            try:
                stats_interval_s = max(1.0, float(cli_stats_interval))
            except Exception:
                pass
        last_stats_at = time.time() - stats_interval_s
        tick_count = 0
        tick_errors = 0
        local_packets_processed = 0
        local_latency_sum_ms = 0.0
        local_latency_count = 0
        last_batch_sig = None

        def _collect_runtime_packet_stats():
            # Preferred source: receiver absolute counters (if running receive mode).
            recv = getattr(node, 'receiver', None)
            get_stats = getattr(recv, 'get_stats', None)
            if callable(get_stats):
                try:
                    snap = get_stats()
                    if isinstance(snap, dict):
                        p = int(snap.get('completed_packets', snap.get('received_packets', 0)) or 0)
                        lat = float(snap.get('avg_latency_ms', 0.0) or 0.0)
                        return p, lat
                except Exception:
                    pass

            # Fallback source: last rscore batch metrics (incremental heuristic).
            getter = getattr(node, 'get_last_batch_metrics', None)
            if callable(getter):
                try:
                    m = getter()
                    if isinstance(m, dict):
                        st = m.get('stage_timing_ms', {}) if isinstance(m.get('stage_timing_ms', {}), dict) else {}
                        sig = (
                            int(m.get('count', 0) or 0),
                            float(st.get('standardize_ms', 0.0) or 0.0),
                            float(st.get('compress_ms', 0.0) or 0.0),
                            float(st.get('fuse_ms', 0.0) or 0.0),
                            str(m.get('source', '')),
                        )
                        return sig
                except Exception:
                    pass
            return None

        while True:
            try:
                if hasattr(node, 'transporter_manager'):
                    node.transporter_manager.runtime_tick()
                tick_count += 1

                packet_probe = _collect_runtime_packet_stats()
                if isinstance(packet_probe, tuple) and len(packet_probe) == 2:
                    # Absolute counters from receiver path.
                    packets_processed = int(packet_probe[0])
                    avg_packet_latency_ms = float(packet_probe[1])
                else:
                    # Incremental fallback from batch metrics signature.
                    if packet_probe is not None and packet_probe != last_batch_sig:
                        cnt, std_ms, cmp_ms, fus_ms, _src = packet_probe
                        if cnt > 0:
                            est_per_packet_ms = (std_ms + cmp_ms + fus_ms) / float(cnt)
                            local_packets_processed += int(cnt)
                            local_latency_sum_ms += float(est_per_packet_ms) * float(cnt)
                            local_latency_count += int(cnt)
                        last_batch_sig = packet_probe
                    packets_processed = int(local_packets_processed)
                    avg_packet_latency_ms = (local_latency_sum_ms / local_latency_count) if local_latency_count > 0 else 0.0

                now = time.time()
                if now - last_stats_at >= stats_interval_s:
                    uptime_s = int(now - start_at)
                    if tick_errors > 0:
                        status = 'degraded'
                    elif packets_processed > 0:
                        status = 'healthy'
                    else:
                        status = 'idle'
                    stats = {
                        'status': status,
                        'uptime_s': uptime_s,
                        'packets_processed': packets_processed,
                        'avg_packet_latency_ms': round(float(avg_packet_latency_ms), 4),
                        'tick_errors': int(tick_errors),
                    }
                    os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(stats, ensure_ascii=False))
                    print(json.dumps({'run_stats': stats}, ensure_ascii=False))
                    last_stats_at = now
                if duration and time.time() - start_at >= duration:
                    break
                time.sleep(max(0.2, interval))
            except KeyboardInterrupt:
                break
            except Exception as exc:
                tick_errors += 1
                os_log.err('CLI', 'RUN_LOOP', exc, {})
                time.sleep(max(0.2, interval))
        if receiver_runtime is not None:
            try:
                receiver_runtime.stop()
            except Exception:
                pass
        return 0

    if cmd in ('inject', 'os-inject'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='inject')
        module = getattr(args, 'module', 'full')
        device_id = getattr(args, 'device_id', None) or node.device_id
        device_status = getattr(args, 'device_status', 'ONLINE')
        raw_sensors = getattr(args, 'sensors', None)
        sensors_file = getattr(args, 'sensors_file', None)
        fallback_sensor = [[
            getattr(args, 'sensor_id', 'V1'),
            getattr(args, 'sensor_status', 'OK'),
            getattr(args, 'value', 1.0),
            getattr(args, 'unit', 'Pa'),
        ]]
        sensors = fallback_sensor
        if sensors_file:
            try:
                with open(sensors_file, 'r', encoding='utf-8-sig') as _sf:
                    sensors = json.load(_sf)
            except Exception as exc:
                print(json.dumps({'error': f'--sensors-file read failed: {exc}'}, ensure_ascii=False))
                return 1
        elif raw_sensors:
            try:
                sensors = json.loads(raw_sensors)
            except Exception as exc:
                print(json.dumps({'error': f'--sensors JSON parse failed: {exc}'}, ensure_ascii=False))
                return 1
        result = {}
        # Stage 1: Standardize
        try:
            fact = node.standardizer.standardize(device_id, device_status, sensors)
            result['standardize'] = fact
            os_log.log_with_const('info', LogMsg.INJECT_STAGE, stage='standardize', summary=str(list(fact.keys())))
        except Exception as exc:
            payload = _friendly_cli_error(exc)
            payload['error'] = f"standardize failed: {payload.get('error', str(exc))}"
            print(json.dumps(payload, ensure_ascii=False))
            return 1
        if module == 'standardize':
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        # Stage 2: Compress
        try:
            compressed = node.engine.compress(fact)
            result['compress'] = compressed
            os_log.log_with_const('info', LogMsg.INJECT_STAGE, stage='compress', summary=f'len={len(compressed)}')
        except Exception as exc:
            payload = _friendly_cli_error(exc)
            payload['error'] = f"compress failed: {payload.get('error', str(exc))}"
            print(json.dumps(payload, ensure_ascii=False))
            return 1
        if module == 'compress':
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        # Stage 3: Fuse (binary packet)
        try:
            aid = node.assigned_id if not _node_id_is_missing(node) else 0
            raw_input_str = f'{aid};{compressed}'
            binary_packet = node.fusion.run_engine(raw_input_str, strategy='FULL')
            result['fuse'] = {'hex': binary_packet.hex(), 'length': len(binary_packet)}
            os_log.log_with_const('info', LogMsg.INJECT_STAGE, stage='fuse', summary=f'len={len(binary_packet)}')
        except Exception as exc:
            payload = _friendly_cli_error(exc)
            payload['error'] = f"fuse failed: {payload.get('error', str(exc))}"
            print(json.dumps(payload, ensure_ascii=False))
            return 1
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps({'stages': list(result.keys())}, ensure_ascii=False))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd in ('decode', 'os-decode'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='decode')
        fmt = getattr(args, 'decode_format', 'hex')
        data = args.data
        decoded = None
        if fmt == 'hex':
            try:
                raw_bytes = bytes.fromhex(data.replace(' ', '').replace(':', ''))
                decoded = node.fusion.decompress(raw_bytes)
            except Exception as exc:
                payload = _friendly_cli_error(exc)
                payload['error'] = f"hex decode failed: {payload.get('error', str(exc))}"
                print(json.dumps(payload, ensure_ascii=False))
                return 1
        else:
            try:
                decoded = node.engine.decompress(data)
            except Exception as exc:
                payload = _friendly_cli_error(exc)
                payload['error'] = f"b62 decode failed: {payload.get('error', str(exc))}"
                print(json.dumps(payload, ensure_ascii=False))
                return 1
        os_log.log_with_const('info', LogMsg.DECODE_RESULT, result=json.dumps(decoded or {}, ensure_ascii=False))
        print(json.dumps(decoded, indent=2, ensure_ascii=False, default=str))
        return 0 if decoded and 'error' not in (decoded or {}) else 1

    if cmd in ('watch', 'os-watch'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='watch')
        watch_module = getattr(args, 'module', 'config')
        interval = float(getattr(args, 'interval', 2.0))
        duration = float(getattr(args, 'duration', 0.0))
        start_at = time.time()
        prev_state = None
        print(f'[watch:{watch_module}] started (Ctrl+C to stop)  interval={interval}s', flush=True)
        while True:
            try:
                ts = time.strftime('%H:%M:%S')
                if watch_module == 'config':
                    current = {k: v for k, v in node.config.items() if not isinstance(v, (dict, list)) or k in ('RESOURCES', 'engine_settings', 'OpenSynaptic_Setting')}
                elif watch_module == 'registry':
                    from pathlib import Path as _Path
                    reg_dir = _Path(node.base_dir) / 'data' / 'device_registry'
                    current = {str(f.relative_to(reg_dir)): f.stat().st_mtime for f in reg_dir.rglob('*.json')} if reg_dir.exists() else {}
                elif watch_module == 'transport':
                    current = {
                        'active': sorted(list(node.active_transporters.keys())),
                        'transporters_status': node.config.get('RESOURCES', {}).get('transporters_status', {}),
                    }
                elif watch_module == 'pipeline':
                    std_obj = getattr(node, 'standardizer', None)
                    std_registry = getattr(std_obj, 'registry', None)
                    if isinstance(std_registry, dict):
                        std_cache_entries = len(std_registry)
                    else:
                        std_cache_entries = 0
                    fusion_obj = getattr(node, 'fusion', None)
                    ram_cache = getattr(fusion_obj, '_RAM_CACHE', {})
                    if not isinstance(ram_cache, dict):
                        ram_cache = {}
                    current = {
                        'standardizer_cache_entries': std_cache_entries,
                        'engine_rev_unit_entries': len(getattr(node.engine, 'REV_UNIT', {})),
                        'fusion_ram_cache_aids': list(ram_cache.keys()),
                        'fusion_template_count': sum(
                            len(v.get('data', {}).get('templates', {}))
                            for v in ram_cache.values()
                        ),
                    }
                else:
                    current = {}
                changed = json.dumps(current, sort_keys=True, default=str) != json.dumps(prev_state, sort_keys=True, default=str)
                if changed:
                    os_log.log_with_const('info', LogMsg.WATCH_CHANGED, ts=ts, module=watch_module)
                    print(f'\n[{ts}] [{watch_module}] <- state changed:', flush=True)
                    print(json.dumps(current, indent=2, ensure_ascii=False, default=str), flush=True)
                    prev_state = current
                else:
                    os_log.log_with_const('info', LogMsg.WATCH_TICK, ts=ts, module=watch_module)
                    print(f'[{ts}] [{watch_module}] no change', end='\r', flush=True)
                if duration and time.time() - start_at >= duration:
                    break
                time.sleep(max(0.2, interval))
            except KeyboardInterrupt:
                print('\n[watch] stopped', flush=True)
                break
            except Exception as exc:
                os_log.err('CLI', 'WATCH', exc, {'module': watch_module})
                time.sleep(max(0.2, interval))
        return 0

    if cmd in ('transporter-toggle', 'os-transporter-toggle'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='transporter-toggle')
        name = str(args.name).lower()
        new_state = bool(args.enable)
        res_conf = node.config.setdefault('RESOURCES', {})
        ts_map = res_conf.setdefault('transporters_status', {})
        ts_map[name] = new_state
        node._save_config()
        state_label = 'enabled' if new_state else 'disabled'
        os_log.log_with_const('info', LogMsg.TRANSPORTER_TOGGLED, name=name, state=state_label)
        result = {'name': name, 'enabled': new_state}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if cmd in ('reload-protocol', 'os-reload-protocol'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='reload-protocol')
        refresh_fn = getattr(getattr(node, 'transporter_manager', None), 'refresh_protocol', None)
        if not callable(refresh_fn):
            result = {'medium': args.medium, 'reloaded': False, 'reason': 'refresh_protocol_unsupported'}
            _log_cli_result_payload(result)
            _print_cli_payload(result)
            return 1
        driver = refresh_fn(args.medium)
        ok = bool(driver)
        result = {'medium': args.medium, 'reloaded': ok}
        _log_cli_result_payload(result)
        _print_cli_payload(result)
        return 0 if ok else 1

    if cmd in ('config-show', 'os-config-show'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='config-show')
        section = getattr(args, 'section', None)
        if section:
            try:
                data = node.config[section]
            except KeyError:
                print(json.dumps({'error': f'Section "{section}" not found. Available: {sorted(node.config.keys())}'}))
                return 1
        else:
            data = node.config
        os_log.log_with_const('info', LogMsg.CONFIG_SHOW, section=section or 'ALL')
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return 0

    if cmd in ('config-get', 'os-config-get'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='config-get')
        key = args.key
        try:
            value = _config_dotpath_get(node.config, key)
        except KeyError as exc:
            print(json.dumps({'error': str(exc)}, ensure_ascii=False))
            return 1
        os_log.log_with_const('info', LogMsg.CONFIG_GET, key=key, value=str(value))
        print(json.dumps({'key': key, 'value': value}, indent=2, ensure_ascii=False, default=str))
        return 0

    if cmd in ('config-set', 'os-config-set'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='config-set')
        key = args.key
        raw_value = args.value
        value_type = getattr(args, 'value_type', 'str')
        try:
            typed_value = _cast_value(raw_value, value_type)
        except Exception as exc:
            print(json.dumps({'error': f'type conversion failed: {exc}'}, ensure_ascii=False))
            return 1
        try:
            old_value = _config_dotpath_get(node.config, key)
        except KeyError:
            old_value = None
        _config_dotpath_set(node.config, key, typed_value)
        node._save_config()
        os_log.log_with_const('info', LogMsg.CONFIG_SET, key=key, value=str(typed_value))
        result = {'key': key, 'old': old_value, 'new': typed_value}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False, default=str))
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    if cmd in ('core', 'os-core'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='core')
        manager = get_core_manager()
        requested = getattr(args, 'set_core', None)
        persisted = False

        if requested:
            try:
                manager.set_active_core(requested)
            except Exception as exc:
                print(json.dumps({'error': str(exc)}, ensure_ascii=False))
                return 1
            if bool(getattr(args, 'persist', False)):
                _config_dotpath_set(node.config, 'engine_settings.core_backend', requested)
                node._save_config()
                persisted = True

        settings = node.config.get('engine_settings', {}) if isinstance(node.config, dict) else {}
        cfg_core = str(settings.get('core_backend', '')).strip().lower() or manager.default_core
        env_core = str(os.getenv('OPENSYNAPTIC_CORE', '')).strip().lower() or None
        payload = {
            'requested': requested,
            'persisted': persisted,
            'available_cores': manager.available_cores(),
            'configured_core': cfg_core,
            'env_override': env_core,
            'active_core': manager.get_active_core_name(),
        }
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(payload, ensure_ascii=False))
        if bool(getattr(args, 'json', False)):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print('active_core   :', payload['active_core'])
            print('configured    :', payload['configured_core'])
            print('env_override  :', payload['env_override'] or '-')
            print('available     :', ', '.join(payload['available_cores']))
            if requested:
                print('switched_to   :', requested)
                print('persisted     :', persisted)
        return 0

    if cmd in ('plugin-cmd', 'os-plugin-cmd'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-cmd')
        plugin_name = normalize_plugin_name(args.plugin)
        sub_cmd = args.cmd
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        os_log.log_with_const('info', LogMsg.PLUGIN_CMD, plugin=plugin_name, sub_cmd=sub_cmd)
        mode = 'interactive' if plugin_name == 'tui' else 'runtime'
        try:
            return _dispatch_plugin(node, plugin_name, sub_cmd, args=extra_args, mode=mode)
        except Exception as exc:
            payload = _friendly_cli_error(exc)
            payload['error'] = f"plugin dispatch failed: {payload.get('error', str(exc))}"
            print(json.dumps(payload, ensure_ascii=False))
            return 1

    if cmd in ('web-user', 'os-web-user', 'os-web'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='web-user')
        # Support both positional subcommand and --cmd flag
        # Priority: positional subcommand > --cmd flag > default 'start'
        sub_cmd = (getattr(args, 'subcommand', None) or 
                  getattr(args, 'cmd_flag', None) or 
                  'start')
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        return _dispatch_plugin(node, 'web_user', sub_cmd, args=extra_args, mode='runtime')

    if cmd in ('deps', 'os-deps'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='deps')
        # Support both positional subcommand and --cmd flag
        # Priority: positional subcommand > --cmd flag > default 'check'
        sub_cmd = (getattr(args, 'subcommand', None) or 
                  getattr(args, 'cmd_flag', None) or 
                  'check')
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        return _dispatch_plugin(node, 'dependency_manager', sub_cmd, args=extra_args, mode='runtime')


    if cmd in ('plugin-test', 'os-plugin-test'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-test')
        suite = getattr(args, 'suite', 'all')
        total = str(int(getattr(args, 'total', 200)))
        workers = str(int(getattr(args, 'workers', 8)))
        sources = str(int(getattr(args, 'sources', 6)))
        verbosity = str(int(getattr(args, 'verbosity', 1)))
        no_progress = bool(getattr(args, 'no_progress', False))
        core_backend = getattr(args, 'core_backend', None) or None
        runs = str(int(getattr(args, 'runs', 1)))
        warmup = str(int(getattr(args, 'warmup', 0)))
        json_out = getattr(args, 'json_out', None) or None
        require_rust = bool(getattr(args, 'require_rust', False))
        header_probe_rate = str(float(getattr(args, 'header_probe_rate', 0.0) or 0.0))
        batch_size = str(int(getattr(args, 'batch_size', 1) or 1))
        processes = str(int(getattr(args, 'processes', 1) or 1))
        auto_profile = bool(getattr(args, 'auto_profile', False))
        profile_total = str(int(getattr(args, 'profile_total', 100000) or 100000))
        profile_runs = str(int(getattr(args, 'profile_runs', 1) or 1))
        final_runs = str(int(getattr(args, 'final_runs', 1) or 1))
        profile_processes = str(getattr(args, 'profile_processes', '1,2,4,8') or '1,2,4,8')
        profile_threads = getattr(args, 'profile_threads', None)
        profile_batches = str(getattr(args, 'profile_batches', '32,64,128') or '32,64,128')
        chain_mode = str(getattr(args, 'chain_mode', 'core') or 'core')
        threads_per_process_val = getattr(args, 'threads_per_process', None)
        threads_per_process = str(int(threads_per_process_val)) if threads_per_process_val is not None else None
        parallel_component = bool(getattr(args, 'parallel_component', False))
        max_class_workers_val = getattr(args, 'max_class_workers', None)
        component_processes = int(getattr(args, 'component_processes', 0) or 0)
        workers_hint_val = getattr(args, 'workers_hint', None)
        threads_hint_val = getattr(args, 'threads_hint', None)
        batch_hint_val = getattr(args, 'batch_hint', None)
        with_component = bool(getattr(args, 'with_component', False))
        pipeline_mode = str(getattr(args, 'pipeline_mode', 'legacy') or 'legacy')
        use_real_udp = bool(getattr(args, 'use_real_udp', False))
        use_transport = getattr(args, 'use_transport', None) or None
        if suite == 'component':
            extra_args = ['--verbosity', verbosity]
            if parallel_component or component_processes > 0:
                extra_args.append('--parallel')
            if component_processes > 0:
                extra_args += ['--processes', str(component_processes)]
            if max_class_workers_val is not None:
                extra_args += ['--max-class-workers', str(int(max_class_workers_val))]
        elif suite == 'stress':
            extra_args = [
                '--total', total,
                '--workers', workers,
                '--sources', sources,
                '--header-probe-rate', header_probe_rate,
                '--batch-size', batch_size,
                '--processes', processes,
                '--chain-mode', chain_mode,
                '--pipeline-mode', pipeline_mode,
            ]
            if use_real_udp:
                extra_args.append('--use-real-udp')
            if use_transport:
                extra_args += ['--use-transport', use_transport]
            if threads_per_process is not None:
                extra_args += ['--threads-per-process', threads_per_process]
            if no_progress:
                extra_args.append('--no-progress')
            if core_backend:
                extra_args += ['--core-backend', core_backend]
            if require_rust:
                extra_args.append('--require-rust')
            if auto_profile:
                extra_args.append('--auto-profile')
                extra_args += ['--profile-total', profile_total]
                extra_args += ['--profile-runs', profile_runs]
                extra_args += ['--final-runs', final_runs]
                extra_args += ['--profile-processes', profile_processes]
                if profile_threads:
                    extra_args += ['--profile-threads', str(profile_threads)]
                extra_args += ['--profile-batches', profile_batches]
            if json_out:
                extra_args += ['--json-out', json_out]
        elif suite == 'compare':
            extra_args = [
                '--total', total,
                '--workers', workers,
                '--sources', sources,
                '--runs', runs,
                '--warmup', warmup,
                '--header-probe-rate', header_probe_rate,
                '--batch-size', batch_size,
                '--processes', processes,
                '--chain-mode', chain_mode,
                '--pipeline-mode', pipeline_mode,
            ]
            if use_real_udp:
                extra_args.append('--use-real-udp')
            if threads_per_process is not None:
                extra_args += ['--threads-per-process', threads_per_process]
            if no_progress:
                extra_args.append('--no-progress')
            if json_out:
                extra_args += ['--json-out', json_out]
            if require_rust:
                extra_args.append('--require-rust')
        elif suite == 'full_load':
            extra_args = [
                '--total', total,
                '--sources', sources,
                '--verbosity', verbosity,
                '--chain-mode', chain_mode,
                '--pipeline-mode', pipeline_mode,
            ]
            if no_progress:
                extra_args.append('--no-progress')
            if core_backend:
                extra_args += ['--core-backend', core_backend]
            if require_rust:
                extra_args.append('--require-rust')
            if header_probe_rate and float(header_probe_rate) > 0:
                extra_args += ['--header-probe-rate', header_probe_rate]
            if workers_hint_val is not None:
                extra_args += ['--workers-hint', str(int(workers_hint_val))]
            if threads_hint_val is not None:
                extra_args += ['--threads-hint', str(int(threads_hint_val))]
            if batch_hint_val is not None:
                extra_args += ['--batch-hint', str(int(batch_hint_val))]
            if with_component:
                extra_args.append('--with-component')
            if json_out:
                extra_args += ['--json-out', json_out]
        elif suite in ('integration', 'audit'):
            extra_args = []
        else:
            extra_args = [
                '--total', total,
                '--workers', workers,
                '--sources', sources,
                '--verbosity', verbosity,
                '--header-probe-rate', header_probe_rate,
                '--batch-size', batch_size,
                '--processes', processes,
                '--chain-mode', chain_mode,
                '--pipeline-mode', pipeline_mode,
            ]
            if threads_per_process is not None:
                extra_args += ['--threads-per-process', threads_per_process]
            if no_progress:
                extra_args.append('--no-progress')
            if core_backend:
                extra_args += ['--core-backend', core_backend]
            if require_rust:
                extra_args.append('--require-rust')
        return _dispatch_plugin(node, 'test_plugin', suite, args=extra_args, mode='runtime')

    parser.print_help()
    return 0


def main(argv=None):
    try:
        return _main_impl(argv)
    except SystemExit:
        raise
    except Exception as exc:
        payload = _friendly_cli_error(exc)
        print(json.dumps(payload, ensure_ascii=False))
        os_log.err('CLI', 'GLOBAL_EXCEPTION', exc, payload)
        return 1


