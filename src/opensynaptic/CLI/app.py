import json
from pathlib import Path
import argparse
import logging
import time
from opensynaptic.core.core import OpenSynaptic
from opensynaptic.core.Receiver import main as receiver_main
from opensynaptic.services.tui import TUIService
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg, CLI_HELP_TABLE

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
                     help='只渲染指定區段 (identity/config/transport/pipeline/plugins/db)')
    tui.add_argument('--interactive', action='store_true', default=False,
                     help='進入互動模式，週期性刷新畫面')
    tui.add_argument('--interval', type=float, default=2.0,
                     help='互動模式刷新間隔（秒）')
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
                        help='執行到哪個管道階段後停止並輸出 (standardize/compress/fuse/full)')
    inject.add_argument('--device-id', dest='device_id', default=None)
    inject.add_argument('--device-status', dest='device_status', default='ONLINE')
    inject.add_argument('--sensor-id', dest='sensor_id', default='V1')
    inject.add_argument('--sensor-status', dest='sensor_status', default='OK')
    inject.add_argument('--value', type=float, default=1.0)
    inject.add_argument('--unit', default='Pa')
    inject.add_argument('--sensors', default=None,
                        help='JSON 陣列，多感測器模式: [[id,status,value,unit],...]')
    inject.add_argument('--sensors-file', dest='sensors_file', default=None,
                        help='JSON 檔案路徑（Windows PowerShell 友善替代方案），內容為 [[id,status,value,unit],...]')
    # --- decode ---
    decode = sub.add_parser('decode', aliases=['os-decode'])
    decode.add_argument('--config', dest='config_path', default=None)
    decode.add_argument('--format', dest='decode_format', choices=['hex', 'b62'], default='hex',
                        help='輸入格式: hex=二進制封包十六進制, b62=Base62 壓縮字串')
    decode.add_argument('--data', required=True, help='要解碼的數據字串')
    # --- watch ---
    watch = sub.add_parser('watch', aliases=['os-watch'])
    watch.add_argument('--config', dest='config_path', default=None)
    watch.add_argument('--module', choices=['config', 'registry', 'transport', 'pipeline'], default='config',
                       help='要監控的模塊 (config/registry/transport/pipeline)')
    watch.add_argument('--interval', type=float, default=2.0, help='輪詢間隔（秒）')
    watch.add_argument('--duration', type=float, default=0.0, help='持續時間（秒），0 為不限')
    # --- transporter-toggle ---
    transporter_toggle = sub.add_parser('transporter-toggle', aliases=['os-transporter-toggle'])
    transporter_toggle.add_argument('--config', dest='config_path', default=None)
    transporter_toggle.add_argument('--name', required=True, help='傳輸器名稱（小寫），如 udp / tcp / lora')
    tog_group = transporter_toggle.add_mutually_exclusive_group(required=True)
    tog_group.add_argument('--enable', action='store_true', default=False)
    tog_group.add_argument('--disable', action='store_true', default=False)
    # --- config-show ---
    config_show = sub.add_parser('config-show', aliases=['os-config-show'])
    config_show.add_argument('--config', dest='config_path', default=None)
    config_show.add_argument('--section', default=None,
                             help='頂層 section 名稱，留空則顯示全部')
    # --- config-get ---
    config_get = sub.add_parser('config-get', aliases=['os-config-get'])
    config_get.add_argument('--config', dest='config_path', default=None)
    config_get.add_argument('--key', required=True,
                            help='點號分隔路徑，如 engine_settings.precision')
    # --- config-set ---
    config_set = sub.add_parser('config-set', aliases=['os-config-set'])
    config_set.add_argument('--config', dest='config_path', default=None)
    config_set.add_argument('--key', required=True,
                            help='點號分隔路徑，如 engine_settings.precision')
    config_set.add_argument('--value', required=True,
                            help='新值（字串，--type 指定類型轉換）')
    config_set.add_argument('--type', dest='value_type',
                            choices=['str', 'int', 'float', 'bool', 'json'],
                            default='str',
                            help='值的類型 (str/int/float/bool/json)，預設 str')
    # --- plugin-cmd ---
    plugin_cmd = sub.add_parser('plugin-cmd', aliases=['os-plugin-cmd'])
    plugin_cmd.add_argument('--config', dest='config_path', default=None)
    plugin_cmd.add_argument('--plugin', required=True,
                            help='插件名稱，如 tui / test_plugin')
    plugin_cmd.add_argument('--cmd', required=True,
                            help='插件子命令，如 render / interactive / component')
    plugin_cmd.add_argument('args', nargs=argparse.REMAINDER,
                            help='傳遞給子命令的額外參數')
    # --- plugin-test ---
    plugin_test = sub.add_parser('plugin-test', aliases=['os-plugin-test'])
    plugin_test.add_argument('--config', dest='config_path', default=None)
    plugin_test.add_argument('--suite', choices=['component', 'stress', 'all'],
                             default='all', help='測試套件 (component/stress/all)')
    plugin_test.add_argument('--workers', type=int, default=8,
                             help='壓力測試線程數')
    plugin_test.add_argument('--total', type=int, default=200,
                             help='壓力測試總發送次數')
    plugin_test.add_argument('--verbosity', type=int, default=1,
                             help='組件測試詳細程度')
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
    print('OpenSynaptic CLI 帮助')
    print('=' * 48)
    print('命令清单（中文注解）:')
    for key, info in CLI_HELP_TABLE.items():
        aliases = ', '.join(info.get('aliases', []))
        note = info.get('desc', '')
        if aliases:
            print('- {} ({})\n  {}'.format(key, aliases, note))
        else:
            print('- {}\n  {}'.format(key, note))
    print('\n参数说明:')
    print('  --quiet      降低日志输出，仅保留 warning/error')
    print('  --interval   run 模式轮询间隔（秒）')
    print('  --duration   run 模式持续时间（秒），0 为不限时')
    print('  --once       run 模式只执行一次并退出')
    print('\n原始 argparse 帮助:')
    parser.print_help()

def _make_node(config_path):
    cfg = str(Path(config_path).resolve()) if config_path else None
    return OpenSynaptic(cfg)


def _config_dotpath_get(config, keypath):
    """Read a value from nested dict using dot-notation path."""
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
    """Write a value into nested dict using dot-notation path (creates intermediate dicts)."""
    keys = keypath.split('.')
    current = config
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _cast_value(raw, value_type):
    """Cast a raw string to the requested Python type."""
    import json as _json
    if value_type == 'int':
        return int(raw)
    if value_type == 'float':
        return float(raw)
    if value_type == 'bool':
        return raw.lower() not in ('false', '0', 'no', 'off', '')
    if value_type == 'json':
        return _json.loads(raw)
    return raw  # str

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
    node = _make_node(args.config_path)
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
        tui_svc = TUIService(node)
        node.service_manager.mount('tui', tui_svc, config={}, mode='interactive')
        node.service_manager.load('tui')
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
        result = {'plugins': snap.get('mount_index', []), 'runtime': snap.get('runtime_index', {})}
        os_log.log_with_const('info', LogMsg.CLI_RESULT, result=json.dumps(result, ensure_ascii=False))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if cmd in ('plugin-load', 'os-plugin-load'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-load')
        svc = node.service_manager.load(args.name)
        result = {'name': args.name, 'loaded': bool(svc)}
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
        if sensors_file:
            try:
                with open(sensors_file, 'r', encoding='utf-8-sig') as _sf:
                    sensors = json.load(_sf)
            except Exception as exc:
                print(json.dumps({'error': f'--sensors-file 讀取失敗: {exc}'}, ensure_ascii=False))
                return 1
        elif raw_sensors:
            try:
                sensors = json.loads(raw_sensors)
            except Exception as exc:
                print(json.dumps({'error': f'--sensors JSON 解析失敗: {exc}'}, ensure_ascii=False))
                return 1
        else:
            sensors = [[args.sensor_id, args.sensor_status, args.value, args.unit]]
        result = {}
        # Stage 1: Standardize
        try:
            fact = node.standardizer.standardize(device_id, device_status, sensors)
            result['standardize'] = fact
            os_log.log_with_const('info', LogMsg.INJECT_STAGE, stage='standardize', summary=str(list(fact.keys())))
        except Exception as exc:
            print(json.dumps({'error': f'standardize 失敗: {exc}'}, ensure_ascii=False))
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
            print(json.dumps({'error': f'compress 失敗: {exc}'}, ensure_ascii=False))
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
            print(json.dumps({'error': f'fuse 失敗: {exc}'}, ensure_ascii=False))
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
                print(json.dumps({'error': f'hex 解碼失敗: {exc}'}, ensure_ascii=False))
                return 1
        else:
            try:
                decoded = node.engine.decompress(data)
            except Exception as exc:
                print(json.dumps({'error': f'b62 解碼失敗: {exc}'}, ensure_ascii=False))
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
        print(f'[watch:{watch_module}] 監控啟動 (Ctrl+C 停止)  interval={interval}s', flush=True)
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
                    print(f'\n[{ts}] [{watch_module}] ← 狀態變更:', flush=True)
                    print(json.dumps(current, indent=2, ensure_ascii=False, default=str), flush=True)
                    prev_state = current
                else:
                    os_log.log_with_const('info', LogMsg.WATCH_TICK, ts=ts, module=watch_module)
                    print(f'[{ts}] [{watch_module}] 無變化', end='\r', flush=True)
                if duration and time.time() - start_at >= duration:
                    break
                time.sleep(max(0.2, interval))
            except KeyboardInterrupt:
                print('\n[watch] 已中止', flush=True)
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
        state_label = '啟用' if new_state else '禁用'
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
            print(json.dumps({'error': f'型別轉換失敗: {exc}'}, ensure_ascii=False))
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
        plugin_name = args.plugin
        sub_cmd = args.cmd
        extra_args = list(getattr(args, 'args', []) or [])
        # Ensure TUI and test_plugin are mounted so they can be dispatched
        if plugin_name == 'tui' and not node.service_manager.get('tui'):
            tui_svc = TUIService(node)
            node.service_manager.mount('tui', tui_svc, config={}, mode='interactive')
            node.service_manager.load('tui')
        if plugin_name == 'test_plugin' and not node.service_manager.get('test_plugin'):
            try:
                from opensynaptic.services.test_plugin import TestPlugin
                tp = TestPlugin(node)
                node.service_manager.mount('test_plugin', tp, config={}, mode='runtime')
                node.service_manager.load('test_plugin')
            except Exception as exc:
                print(json.dumps({'error': f'test_plugin 載入失敗: {exc}'}, ensure_ascii=False))
                return 1
        os_log.log_with_const('info', LogMsg.PLUGIN_CMD, plugin=plugin_name, sub_cmd=sub_cmd)
        return node.service_manager.dispatch_plugin_cli(plugin_name, [sub_cmd] + extra_args)

    if cmd in ('plugin-test', 'os-plugin-test'):
        os_log.log_with_const('info', LogMsg.CLI_ACTION, action='plugin-test')
        suite = getattr(args, 'suite', 'all')
        workers = int(getattr(args, 'workers', 8))
        total = int(getattr(args, 'total', 200))
        verbosity = int(getattr(args, 'verbosity', 1))
        try:
            from opensynaptic.services.test_plugin import TestPlugin
        except ImportError as exc:
            print(json.dumps({'error': f'test_plugin 模組載入失敗: {exc}'}, ensure_ascii=False))
            return 1
        tp = TestPlugin(node)
        os_log.log_with_const('info', LogMsg.PLUGIN_TEST_START, plugin='test_plugin', suite=suite)
        if suite == 'component':
            ok, fail, _ = tp.run_component(verbosity=verbosity)
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite=suite, ok=ok, fail=fail)
            print(json.dumps({'ok': ok, 'fail': fail}, ensure_ascii=False))
            return 0 if fail == 0 else 1
        elif suite == 'stress':
            summary, fail = tp.run_stress(total=total, workers=workers)
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite=suite, ok=summary.get('ok', 0), fail=fail)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0 if fail == 0 else 1
        else:  # all
            report = tp.run_all(stress_total=total, stress_workers=workers, verbosity=verbosity)
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='all',
                                  ok=report['component']['ok'], fail=report['overall_fail'])
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report['overall_fail'] == 0 else 1

    parser.print_help()
    return 0
