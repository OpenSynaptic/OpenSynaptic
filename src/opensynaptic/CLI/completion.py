"""Argcomplete-backed dynamic completers for OpenSynaptic CLI.

All completers gracefully degrade to empty/static lists when optional
runtime dependencies or config files are unavailable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from opensynaptic.services.plugin_registry import PLUGIN_SPECS, list_builtin_plugins, get_plugin_cli_completion_meta
from opensynaptic.utils import get_user_config_path

try:
    import argcomplete  # type: ignore
except Exception:  # pragma: no cover
    argcomplete = None


_TRANSPORTER_DESC = {
    'udp': 'UDP (User Datagram Protocol)',
    'tcp': 'TCP (Transmission Control Protocol)',
    'quic': 'QUIC (Quick UDP Internet Connections)',
    'iwip': 'iWIP (lightweight stack adapter)',
    'uip': 'uIP (micro IP stack adapter)',
    'uart': 'UART (Serial)',
    'rs485': 'RS485 (Industrial serial bus)',
    'can': 'CAN (Controller Area Network)',
    'lora': 'LoRa (Long Range radio)',
    'bluetooth': 'Bluetooth (Physical-layer gateway transport)',
    'mqtt': 'MQTT (Message Queue Telemetry Transport)',
    'matter': 'Matter (Application-layer gateway transport)',
    'zigbee': 'Zigbee (Application-layer gateway transport)',
}

_CONFIG_KEY_CACHE: Dict[str, Tuple[float, float, List[str]]] = {}
_CONFIG_KEY_CACHE_TTL_S = 5.0

_PLUGIN_CLI_META_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_PLUGIN_CLI_META_TTL_S = 10.0


# -------- Generic helpers --------

def _resolve_config_path(parsed_args: Any) -> Path:
    raw = getattr(parsed_args, 'config_path', None)
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return Path(get_user_config_path())


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _filter_prefix(values: Iterable[str], prefix: str) -> List[str]:
    p = str(prefix or '')
    out = []
    for item in values:
        if item.startswith(p):
            out.append(item)
    return sorted(set(out))


def _with_desc(values: Iterable[str], desc_map: Dict[str, str], prefix: str) -> Any:
    filtered = _filter_prefix(values, prefix)
    if argcomplete is None:
        return filtered
    # Argcomplete supports dict-style completion->description maps.
    out: Dict[str, str] = {}
    for key in filtered:
        out[key] = desc_map.get(key, '')
    return out


# -------- Config key-path completion --------

def _walk_config_paths(node: Any, prefix: str, out: List[str]) -> None:
    if isinstance(node, dict):
        for key, val in node.items():
            if not isinstance(key, str):
                continue
            path = f'{prefix}.{key}' if prefix else key
            out.append(path)
            _walk_config_paths(val, path, out)
        return
    if isinstance(node, list):
        for idx, val in enumerate(node):
            idx_path = f'{prefix}[{idx}]' if prefix else f'[{idx}]'
            out.append(idx_path)
            _walk_config_paths(val, idx_path, out)


def _collect_config_paths(config_path: Path) -> List[str]:
    now = time.time()
    key = str(config_path)
    mtime = float(config_path.stat().st_mtime) if config_path.exists() else -1.0
    cached = _CONFIG_KEY_CACHE.get(key)
    if cached is not None:
        cached_mtime, cached_at, cached_paths = cached
        if cached_mtime == mtime and (now - cached_at) <= _CONFIG_KEY_CACHE_TTL_S:
            return cached_paths

    cfg = _read_json(config_path)
    paths: List[str] = []
    _walk_config_paths(cfg, '', paths)
    deduped = sorted(set(paths))
    _CONFIG_KEY_CACHE[key] = (mtime, now, deduped)
    return deduped


def complete_config_path(prefix: str, parsed_args: Any, **_: Any) -> Any:
    cfg_path = _resolve_config_path(parsed_args)
    paths = _collect_config_paths(cfg_path)
    return _filter_prefix(paths, prefix)


# -------- Transporter completion --------

def _discover_transporters(parsed_args: Any) -> List[str]:
    out = {'udp', 'tcp', 'quic', 'iwip', 'uip', 'uart', 'rs485', 'can', 'lora', 'mqtt', 'matter', 'zigbee'}

    cfg = _read_json(_resolve_config_path(parsed_args))
    resources = cfg.get('RESOURCES', {}) if isinstance(cfg.get('RESOURCES', {}), dict) else {}
    for key_name in ('transporters_status', 'application_status', 'transport_status', 'physical_status'):
        mp = resources.get(key_name, {}) if isinstance(resources.get(key_name, {}), dict) else {}
        for k in mp.keys():
            out.add(str(k).strip().lower())

    # Reflect current code-level candidates if available.
    try:
        from opensynaptic.services.transporters.main import TransporterService
        out.update({str(k).strip().lower() for k in getattr(TransporterService, 'APP_LAYER_DRIVERS', set())})
    except Exception:
        pass
    try:
        from opensynaptic.core.transport_layer.manager import TransportLayerManager
        out.update({str(k).strip().lower() for k in getattr(TransportLayerManager, '_CANDIDATES', tuple())})
    except Exception:
        pass
    try:
        from opensynaptic.core.physical_layer.manager import PhysicalLayerManager
        out.update({str(k).strip().lower() for k in getattr(PhysicalLayerManager, '_CANDIDATES', tuple())})
    except Exception:
        pass

    return sorted(v for v in out if v)


def complete_transporter(prefix: str, parsed_args: Any, **_: Any) -> Any:
    items = _discover_transporters(parsed_args)
    return _with_desc(items, _TRANSPORTER_DESC, prefix)


# -------- Plugin completion --------

def _get_plugin_subcommands(plugin_name: str) -> Dict[str, str]:
    key = str(plugin_name or '').strip().lower().replace('-', '_')
    if not key:
        return {}

    now = time.time()
    cached = _PLUGIN_CLI_META_CACHE.get(key)
    if cached is not None and (now - cached[0]) <= _PLUGIN_CLI_META_TTL_S:
        return cached[1]

    cmds: Dict[str, str] = {}

    try:
        meta = get_plugin_cli_completion_meta(key)
        if isinstance(meta, dict):
            cmds.update({str(k): str(v or '') for k, v in meta.items()})
    except Exception:
        pass

    # Fallback if plugin-specific metadata is unavailable.
    if (not cmds) and (key in PLUGIN_SPECS):
        if key == 'web_user':
            cmds.update({
                'start': 'Start web service',
                'stop': 'Stop web service',
                'status': 'Show web status',
                'dashboard': 'Show dashboard payload',
            })
        elif key == 'dependency_manager':
            cmds.update({'check': '', 'doctor': '', 'sync': '', 'repair': '', 'install': ''})
        elif key == 'env_guard':
            cmds.update({'status': '', 'start': '', 'stop': '', 'set': '', 'resource-show': '', 'resource-init': ''})

    deduped = {k: v for k, v in sorted(cmds.items(), key=lambda x: x[0]) if k}
    _PLUGIN_CLI_META_CACHE[key] = (now, deduped)
    return deduped


def complete_plugin_name(prefix: str, parsed_args: Any, **_: Any) -> List[str]:
    del parsed_args
    return _filter_prefix(list_builtin_plugins(), prefix)


def complete_plugin_subcommand(prefix: str, parsed_args: Any, **_: Any) -> List[str]:
    plugin = getattr(parsed_args, 'plugin', '')
    meta = _get_plugin_subcommands(plugin)
    return _with_desc(meta.keys(), meta, prefix)


# -------- Argcomplete activation --------

def enable_argcomplete(parser: Any) -> None:
    if argcomplete is None:
        return
    try:
        argcomplete.autocomplete(parser)
    except Exception:
        return

