"""OpenSynaptic utilities unified entry point."""

from opensynaptic.utils.base62.base62 import Base62Codec
from opensynaptic.utils.buffer import as_readonly_view, ensure_bytes, payload_len, to_wire_payload, zero_copy_enabled
from opensynaptic.utils.c.native_loader import (
    NativeLibraryUnavailable,
    has_native_library,
    load_native_library,
    require_native_library,
)
from opensynaptic.utils.c.build_native import build_all as build_native_all
from opensynaptic.utils.c.check_native_toolchain import build_guidance, get_toolchain_report
from opensynaptic.utils.constants import CLI_HELP_TABLE, LogMsg, MESSAGES
from opensynaptic.utils.errors import EnvironmentMissingError, classify_exception
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.paths import (
    ctx,
    get_config_path,
    get_user_config_path,
    get_project_config_path,
    get_lib_path,
    get_registry_path,
    read_json,
    write_json,
)
from opensynaptic.utils.security.security_core import (
    crc8,
    crc16_ccitt,
    derive_session_key,
    xor_payload,
    xor_payload_into,
)

__version__ = '0.1.0'
crc16 = crc16_ccitt

__all__ = [
    'read_json', 'write_json', 'get_config_path', 'get_user_config_path', 'get_project_config_path', 'get_registry_path', 'get_lib_path', 'ctx',
    'os_log',
    'LogMsg', 'MESSAGES', 'CLI_HELP_TABLE',
    'ensure_bytes', 'payload_len', 'zero_copy_enabled', 'as_readonly_view', 'to_wire_payload',
    'Base62Codec',
    'crc8', 'crc16', 'crc16_ccitt', 'xor_payload', 'xor_payload_into', 'derive_session_key',
    'load_native_library', 'require_native_library', 'has_native_library', 'NativeLibraryUnavailable',
    'build_native_all', 'build_guidance', 'get_toolchain_report',
    'EnvironmentMissingError', 'classify_exception',
]

