import json
from pathlib import Path
import argparse
import logging
import sys
import time
from types import SimpleNamespace
from opensynaptic.core import OpenSynaptic
from opensynaptic.core.Receiver import main as receiver_main
from opensynaptic.services.env_guard.main import EnvironmentGuardService
from opensynaptic.services.plugin_registry import (
    ensure_and_mount_plugin,
    list_builtin_plugins,
    normalize_plugin_name,
)
from opensynaptic.utils.errors import EnvironmentMissingError
from opensynaptic.utils.c.build_native import build_all as build_native_all
from opensynaptic.utils.c.check_native_toolchain import build_guidance, get_toolchain_report
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg, CLI_HELP_TABLE
from opensynaptic.utils.c.native_loader import NativeLibraryUnavailable


_ENV_GUARD_STANDALONE = None

def _build_parser():
    parser = argparse.ArgumentParser(prog='os-node', description='OpenSynaptic CLI')
    parser.add_argument('--config', dest='config_path', default=None)
    parser.add_argument('--host', required=False, default=None)
    parser.add_argument('--port', required=False, type=int, default=None)
    parser.add_argument('--once', action='store_true', default=False)
    parser.add_argument('--interval', type=float, default=5.0)
    parser.add_argument('--duration', type=float, default=0.0)
    parser.add_argument('--quiet', action='store_true', default=False)
    sub = parser.add_subparsers(dest='command')
    snapshot = sub.add_parser('snapshot', aliases=['os-snapshot'])
    snapshot.add_argument('--config', dest='config_path', default=None)
    receive = sub.add_parser('receive', aliases=['os-receive'])
    receive.add_argument('--config', dest='config_path', default=None)
    tui = sub.add_parser('tui', aliases=['os-tui'])
    tui.add_argument('--config', dest='config_path', default=None)
    tui.add_argument('--section', default=None,
                     help='Render only one section (identity/config/transport/pipeline/plugins/db)')
    tui.add_argument('--interactive', action='store_true', default=False,
                     help='Enter interactive BIOS-like mode')
    tui.add_argument('--interval', type=float, default=2.0,
                     help='Interactive refresh interval in seconds')
    time_sync = sub.add_parser('time-sync', aliases=['os-time-sync'])
    time_sync.add_argument('--config', dest='config_path', default=None)
    ensure_id = sub.add_parser('ensure-id', aliases=['os-ensure-id'])
    ensure_id.add_argument('--config', dest='config_path', default=None)
    ensure_id.add_argument('--host', required=False, default=None)
    ensure_id.add_argument('--port', required=False, type=int, default=None)
    transmit = sub.add_parser('transmit', aliases=['os-transmit'])
    transmit.add_argument('--config', dest='config_path', default=None)
    transmit.add_argument('--device-id', dest='device_id', default=None)
    transmit.add_argument('--status', default='ONLINE')
    transmit.add_argument('--sensor-id', default='V1')
    transmit.add_argument('--sensor-status', default='OK')
    transmit.add_argument('--value', type=float, default=1.0)
    transmit.add_argument('--unit', default='Pa')
    transmit.add_argument('--medium', default='UDP')
    reload_protocol = sub.add_parser('reload-protocol', aliases=['os-reload-protocol'])
    reload_protocol.add_argument('--config', dest='config_path', default=None)
    reload_protocol.add_argument('--medium', required=True)
    run = sub.add_parser('run', aliases=['os-run'])
    run.add_argument('--config', dest='config_path', default=None)
    run.add_argument('--host', required=False, default=None)
    run.add_argument('--port', required=False, type=int, default=None)
    run.add_argument('--once', action='store_true', default=False)
    run.add_argument('--interval', type=float, default=5.0)
    run.add_argument('--duration', type=float, default=0.0)
    run.add_argument('--quiet', action='store_true', default=False)
    plugin_list = sub.add_parser('plugin-list', aliases=['os-plugin-list'])
    plugin_list.add_argument('--config', dest='config_path', default=None)
    plugin_load = sub.add_parser('plugin-load', aliases=['os-plugin-load'])
    plugin_load.add_argument('--config', dest='config_path', default=None)
    plugin_load.add_argument('--name', required=True)
    transport_status = sub.add_parser('transport-status', aliases=['os-transport-status'])
    transport_status.add_argument('--config', dest='config_path', default=None)
    db_status = sub.add_parser('db-status', aliases=['os-db-status'])
    db_status.add_argument('--config', dest='config_path', default=None)
    # --- inject ---
    inject = sub.add_parser('inject', aliases=['os-inject'])
    inject.add_argument('--config', dest='config_path', default=None)
    inject.add_argument('--module', choices=['standardize', 'compress', 'fuse', 'full'], default='full',
                        help='Stop and print after the selected pipeline stage (standardize/compress/fuse/full)')
    inject.add_argument('--device-id', dest='device_id', default=None)
    inject.add_argument('--device-status', dest='device_status', default='ONLINE')
    inject.add_argument('--sensor-id', dest='sensor_id', default='V1')
    inject.add_argument('--sensor-status', dest='sensor_status', default='OK')
    inject.add_argument('--value', type=float, default=1.0)
    inject.add_argument('--unit', default='Pa')
    inject.add_argument('--sensors', default=None,
                        help='JSON array for multi-sensor mode: [[id,status,value,unit],...]')
    inject.add_argument('--sensors-file', dest='sensors_file', default=None,
                        help='JSON file path (PowerShell-friendly option), format: [[id,status,value,unit],...]')
    # --- decode ---
    decode = sub.add_parser('decode', aliases=['os-decode'])
    decode.add_argument('--config', dest='config_path', default=None)
    decode.add_argument('--format', dest='decode_format', choices=['hex', 'b62'], default='hex',
                        help='Input format: hex=binary packet hex string, b62=Base62 compressed string')
    decode.add_argument('--data', required=True, help='Data string to decode')
    # --- watch ---
    watch = sub.add_parser('watch', aliases=['os-watch'])
    watch.add_argument('--config', dest='config_path', default=None)
    watch.add_argument('--module', choices=['config', 'registry', 'transport', 'pipeline'], default='config',
                       help='Module to watch (config/registry/transport/pipeline)')
    watch.add_argument('--interval', type=float, default=2.0, help='Polling interval in seconds')
    watch.add_argument('--duration', type=float, default=0.0, help='Total duration in seconds; 0 means unlimited')
    # --- transporter-toggle ---
    transporter_toggle = sub.add_parser('transporter-toggle', aliases=['os-transporter-toggle'])
    transporter_toggle.add_argument('--config', dest='config_path', default=None)
    transporter_toggle.add_argument('--name', required=True, help='Transporter name (lowercase), e.g. udp / tcp / lora')
    tog_group = transporter_toggle.add_mutually_exclusive_group(required=True)
    tog_group.add_argument('--enable', action='store_true', default=False)
    tog_group.add_argument('--disable', action='store_true', default=False)
    # --- config-show ---
    config_show = sub.add_parser('config-show', aliases=['os-config-show'])
    config_show.add_argument('--config', dest='config_path', default=None)
    config_show.add_argument('--section', default=None,
                             help='Top-level section name; leave empty to print all')
    # --- config-get ---
    config_get = sub.add_parser('config-get', aliases=['os-config-get'])
    config_get.add_argument('--config', dest='config_path', default=None)
    config_get.add_argument('--key', required=True,
                            help='Dot path, for example: engine_settings.precision')
    # --- config-set ---
    config_set = sub.add_parser('config-set', aliases=['os-config-set'])
    config_set.add_argument('--config', dest='config_path', default=None)
    config_set.add_argument('--key', required=True,
                            help='Dot path, for example: engine_settings.precision')
    config_set.add_argument('--value', required=True,
                            help='New value string (use --type for conversion)')
    config_set.add_argument('--type', dest='value_type',
                            choices=['str', 'int', 'float', 'bool', 'json'],
                            default='str',
                            help='Value type (str/int/float/bool/json), default=str')
    # --- plugin-cmd ---
    plugin_cmd = sub.add_parser('plugin-cmd', aliases=['os-plugin-cmd'])
    plugin_cmd.add_argument('--config', dest='config_path', default=None)
    plugin_cmd.add_argument('--plugin', required=True,
                            help='Plugin name, e.g. tui / test_plugin / web_user')
    plugin_cmd.add_argument('--cmd', required=True,
                            help='Plugin sub-command, e.g. render / interactive / component')
    plugin_cmd.add_argument('args', nargs=argparse.REMAINDER,
                            help='Extra arguments passed to the plugin sub-command')
    # --- plugin-test ---
    plugin_test = sub.add_parser('plugin-test', aliases=['os-plugin-test'])
    plugin_test.add_argument('--config', dest='config_path', default=None)
    plugin_test.add_argument('--suite', choices=['component', 'stress', 'all'],
                             default='all', help='Test suite (component/stress/all)')
    plugin_test.add_argument('--workers', type=int, default=8,
                             help='Stress test worker threads')
    plugin_test.add_argument('--total', type=int, default=200,
                             help='Total stress test iterations')
    plugin_test.add_argument('--sources', type=int, default=6,
                             help='Number of rotating sensor source templates for stress test')
    plugin_test.add_argument('--no-progress', action='store_true', default=False,
                             help='Disable live progress bar during stress test')
    plugin_test.add_argument('--verbosity', type=int, default=1,
                             help='Component test verbosity level')
    # --- web-user (standalone plugin command) ---
    web_user = sub.add_parser('web-user', aliases=['os-web-user'])
    web_user.add_argument('--config', dest='config_path', default=None)
    web_user.add_argument('--cmd', choices=['start', 'stop', 'status', 'list', 'add', 'update', 'delete'], default='start')
    web_user.add_argument('args', nargs=argparse.REMAINDER,
                          help='Arguments passed to web_user sub-command')
    # --- deps (standalone plugin command) ---
    deps = sub.add_parser('deps', aliases=['os-deps'])
    deps.add_argument('--config', dest='config_path', default=None)
    deps.add_argument('--cmd', choices=['check', 'doctor', 'sync', 'repair', 'install'], default='check')
    deps.add_argument('args', nargs=argparse.REMAINDER,
                      help='Arguments passed to dependency_manager sub-command')
    env_guard = sub.add_parser('env-guard', aliases=['os-env-guard'])
    env_guard.add_argument('--config', dest='config_path', default=None)
    env_guard.add_argument('--cmd', choices=['status', 'start', 'stop', 'set', 'resource-show', 'resource-init'], default='status')
    env_guard.add_argument('args', nargs=argparse.REMAINDER,
                           help='Arguments passed to env_guard sub-command')
    native_check = sub.add_parser('native-check', aliases=['os-native-check'])
    native_check.add_argument('--json', action='store_true', default=False,
                              help='Output precheck report as JSON')
    native_check.add_argument('--timeout', type=float, default=8.0,
                              help='Timeout in seconds for toolchain precheck')
    native_build = sub.add_parser('native-build', aliases=['os-native-build'])
    native_build.add_argument('--json', action='store_true', default=False,
                              help='Output build result as JSON')
    native_build.add_argument('--no-progress', action='store_true', default=False,
                              help='Disable real-time compile output stream')
    native_build.add_argument('--idle-timeout', type=float, default=20.0,
                              help='Timeout in seconds when compiler produces no output')
    native_build.add_argument('--max-timeout', type=float, default=300.0,
                              help='Maximum compile time per target in seconds')
    sub.add_parser('help', aliases=['os-help'])
    return parser


def _apply_quiet_mode(args):
    if not bool(getattr(args, 'quiet', False)):
        return
    try:
        os_log.logger.setLevel(logging.WARNING)
        for h in os_log.logger.handlers:
            h.setLevel(logging.WARNING)
    except Exception:
        pass


def _render_help_text(parser):
    print('OpenSynaptic CLI Help')
    print('=' * 48)
    print('Command list:')
    for key, info in CLI_HELP_TABLE.items():
        aliases = ', '.join(info.get('aliases', []))
        note = info.get('desc', '')
        if aliases:
            print('- {} ({})\n  {}'.format(key, aliases, note))
        else:
            print('- {}\n  {}'.format(key, note))
    print('\nCommon options:')
    print('  --quiet      reduce logs to warning/error')
    print('  --interval   run-mode polling interval (seconds)')
    print('  --duration   run-mode duration (seconds), 0 = unlimited')
    print('  --once       run mode executes once and exits')
    print('\nRaw argparse help:')
    parser.print_help()

def _make_node(config_path):
    cfg = str(Path(config_path).resolve()) if config_path else None
    return OpenSynaptic(cfg)


def _load_config_for_cli(config_path):
    if config_path:
        cfg_path = Path(config_path).resolve()
    else:
        cfg_path = Path.cwd() / 'Config.json'
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception:
        return {}


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


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    _apply_quiet_mode(args)
    cmd = args.command or 'run'
    os_log.log_with_const('info', LogMsg.CLI_READY, mode=cmd)
    if cmd in ('help', 'os-help'):
        _render_help_text(parser)
        return 0
    if cmd in ('receive', 'os-receive'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='receive')
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
    if cmd in ('env-guard', 'os-env-guard'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='env-guard')
        svc = _standalone_env_guard(getattr(args, 'config_path', None))
        if svc is None:
            print(json.dumps({'ok': False, 'error': 'env_guard is disabled in config'}, ensure_ascii=False))
            return 1
        sub_cmd = getattr(args, 'cmd', 'status')
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        commands = svc.get_cli_commands()
        handler = commands.get(sub_cmd)
        if handler is None:
            print(json.dumps({'error': 'unknown env-guard cmd', 'available': sorted(commands.keys())}, ensure_ascii=False))
            return 1
        return handler(extra_args) or 0
    try:
        node = _make_node(args.config_path)
    except NativeLibraryUnavailable as exc:
        print(json.dumps({'error': str(exc), 'hint': 'Build native libs via: python -u src/opensynaptic/utils/c/build_native.py'}, ensure_ascii=False))
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
        ok = node.ensure_id(host, port)
        print(json.dumps({'ok': ok, 'assigned_id': node.assigned_id}, ensure_ascii=False))
        return 0 if ok else 1
    if cmd in ('transmit', 'os-transmit'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='transmit')
        packet, aid, strategy = node.transmit(sensors=[[args.sensor_id, args.sensor_status, args.value, args.unit]], device_id=args.device_id, device_status=args.status)
        sent = node.dispatch(packet, medium=args.medium)
        result = {'assigned_id': aid, 'strategy': strategy, 'packet_len': len(packet), 'sent': bool(sent)}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if sent else 1
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
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if cmd in ('plugin-load', 'os-plugin-load'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-load')
        key, svc = _ensure_plugin(node, args.name, mode='runtime', load=True)
        result = {'name': key, 'loaded': bool(svc)}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if svc else 1
    if cmd in ('transport-status', 'os-transport-status'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='transport-status')
        result = {
            'active_transporters': sorted(list(node.active_transporters.keys())),
            'transport_status': node.config.get('RESOURCES', {}).get('transport_status', {}),
            'physical_status': node.config.get('RESOURCES', {}).get('physical_status', {}),
            'application_status': node.config.get('RESOURCES', {}).get('application_status', {}),
        }
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if cmd in ('db-status', 'os-db-status'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='db-status')
        result = {'enabled': bool(node.db_manager), 'dialect': getattr(node.db_manager, 'dialect', None)}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if cmd in ('run', 'os-run'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='run')
        host = getattr(args, 'host', None) or node.config.get('Client_Core', {}).get('server_host', '127.0.0.1')
        port = getattr(args, 'port', None) or node.config.get('Client_Core', {}).get('server_port', 8080)
        ensure_ok = node.ensure_id(host, port)
        once = bool(getattr(args, 'once', False))
        interval = float(getattr(args, 'interval', 5.0))
        duration = float(getattr(args, 'duration', 0.0))
        result = {'ok': ensure_ok, 'assigned_id': node.assigned_id, 'mode': 'once' if once else 'persistent'}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        if not ensure_ok:
            return 1
        if once:
            return 0

        start_at = time.time()
        while True:
            try:
                if hasattr(node, 'transporter_manager'):
                    node.transporter_manager.runtime_tick()
                if duration and time.time() - start_at >= duration:
                    break
                time.sleep(max(0.2, interval))
            except KeyboardInterrupt:
                break
            except Exception as exc:
                os_log.err('CLI', 'RUN_LOOP', exc, {})
                time.sleep(max(0.2, interval))
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
            print(json.dumps({'error': f'standardize failed: {exc}'}, ensure_ascii=False))
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
            print(json.dumps({'error': f'compress failed: {exc}'}, ensure_ascii=False))
            return 1
        if module == 'compress':
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        # Stage 3: Fuse (binary packet)
        try:
            aid = node.assigned_id if not node._is_id_missing() else 0
            raw_input_str = f'{aid};{compressed}'
            binary_packet = node.fusion.run_engine(raw_input_str, strategy='FULL')
            result['fuse'] = {'hex': binary_packet.hex(), 'length': len(binary_packet)}
            os_log.log_with_const('info', LogMsg.INJECT_STAGE, stage='fuse', summary=f'len={len(binary_packet)}')
        except Exception as exc:
            print(json.dumps({'error': f'fuse failed: {exc}'}, ensure_ascii=False))
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
                print(json.dumps({'error': f'hex decode failed: {exc}'}, ensure_ascii=False))
                return 1
        else:
            try:
                decoded = node.engine.decompress(data)
            except Exception as exc:
                print(json.dumps({'error': f'b62 decode failed: {exc}'}, ensure_ascii=False))
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
                    current = {
                        'standardizer_cache_entries': len(node.standardizer.registry),
                        'engine_rev_unit_entries': len(getattr(node.engine, 'REV_UNIT', {})),
                        'fusion_ram_cache_aids': list(node.fusion._RAM_CACHE.keys()),
                        'fusion_template_count': sum(
                            len(v.get('data', {}).get('templates', {}))
                            for v in node.fusion._RAM_CACHE.values()
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
        driver = node.transporter_manager.refresh_protocol(args.medium)
        ok = bool(driver)
        result = {'medium': args.medium, 'reloaded': ok}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
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
            print(json.dumps({'error': f'plugin dispatch failed: {exc}'}, ensure_ascii=False))
            return 1

    if cmd in ('web-user', 'os-web-user'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='web-user')
        sub_cmd = getattr(args, 'cmd', 'start')
        extra_args = list(getattr(args, 'args', []) or [])
        if extra_args and extra_args[0] == '--':
            extra_args = extra_args[1:]
        return _dispatch_plugin(node, 'web_user', sub_cmd, args=extra_args, mode='runtime')

    if cmd in ('deps', 'os-deps'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='deps')
        sub_cmd = getattr(args, 'cmd', 'check')
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
        if suite == 'component':
            extra_args = ['--verbosity', verbosity]
        elif suite == 'stress':
            extra_args = ['--total', total, '--workers', workers, '--sources', sources]
            if no_progress:
                extra_args.append('--no-progress')
        else:
            extra_args = ['--total', total, '--workers', workers, '--sources', sources, '--verbosity', verbosity]
            if no_progress:
                extra_args.append('--no-progress')
        return _dispatch_plugin(node, 'test_plugin', suite, args=extra_args, mode='runtime')

    parser.print_help()
    return 0
