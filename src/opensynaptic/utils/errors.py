from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorType(str, Enum):
    CONFIG = 'config_error'
    NETWORK = 'network_error'
    AUTH = 'auth_error'
    DATA = 'data_error'
    CRC = 'crc_error'
    PLUGIN = 'plugin_error'
    RUST_CORE = 'rust_core_error'
    TRANSPORT = 'transport_error'
    VALIDATION = 'validation_error'
    ENVIRONMENT = 'environment_error'
    INTERNAL = 'internal_error'


class OpenSynapticError(Exception):
    """Base exception for project-level typed errors."""

    code = 'OS_GENERIC'
    error_type = ErrorType.INTERNAL


@dataclass
class TypedOpenSynapticError(OpenSynapticError):
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> Dict[str, Any]:
        return {
            'type': type(self).__name__,
            'code': self.code,
            'error_type': str(self.error_type.value),
            'message': self.message,
            'details': dict(self.details or {}),
        }


class ConfigurationError(TypedOpenSynapticError):
    code = 'OS_CONFIG'
    error_type = ErrorType.CONFIG


class NetworkError(TypedOpenSynapticError):
    code = 'OS_NETWORK'
    error_type = ErrorType.NETWORK


class AuthenticationError(TypedOpenSynapticError):
    code = 'OS_AUTH'
    error_type = ErrorType.AUTH


class DataError(TypedOpenSynapticError):
    code = 'OS_DATA'
    error_type = ErrorType.DATA


class CRCError(DataError):
    code = 'OS_CRC'
    error_type = ErrorType.CRC


class PluginLoadError(TypedOpenSynapticError):
    code = 'OS_PLUGIN_LOAD'
    error_type = ErrorType.PLUGIN


class RustCoreLoadError(TypedOpenSynapticError):
    code = 'OS_RUST_CORE'
    error_type = ErrorType.RUST_CORE


@dataclass
class EnvironmentMissingError(OpenSynapticError):
    """Raised when required runtime/build environment resources are missing."""

    message: str
    missing_kind: str = 'environment'
    resource: str = ''
    install_urls: List[str] = field(default_factory=list)
    install_commands: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    code = 'OS_ENV_MISSING'
    error_type = ErrorType.ENVIRONMENT

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> Dict[str, Any]:
        return {
            'type': type(self).__name__,
            'code': self.code,
            'message': self.message,
            'missing_kind': self.missing_kind,
            'resource': self.resource,
            'install_urls': list(self.install_urls or []),
            'install_commands': list(self.install_commands or []),
            'details': dict(self.details or {}),
        }


@dataclass
class ValidationError(OpenSynapticError):
    message: str
    code = 'OS_VALIDATION'
    error_type = ErrorType.VALIDATION

    def __str__(self) -> str:
        return self.message


@dataclass
class TransportError(OpenSynapticError):
    message: str
    code = 'OS_TRANSPORT'
    error_type = ErrorType.TRANSPORT

    def __str__(self) -> str:
        return self.message


def classify_exception(exc: Exception) -> Dict[str, Optional[str]]:
    text = str(exc or '')
    low = text.lower()

    if isinstance(exc, RustCoreLoadError):
        return {'category': ErrorType.RUST_CORE.value, 'code': exc.code}
    if isinstance(exc, PluginLoadError):
        return {'category': ErrorType.PLUGIN.value, 'code': exc.code}
    if isinstance(exc, CRCError):
        return {'category': ErrorType.CRC.value, 'code': exc.code}
    if isinstance(exc, DataError):
        return {'category': ErrorType.DATA.value, 'code': exc.code}
    if isinstance(exc, NetworkError):
        return {'category': ErrorType.NETWORK.value, 'code': exc.code}
    if isinstance(exc, AuthenticationError):
        return {'category': ErrorType.AUTH.value, 'code': exc.code}
    if isinstance(exc, ConfigurationError):
        return {'category': ErrorType.CONFIG.value, 'code': exc.code}
    if isinstance(exc, EnvironmentMissingError):
        return {'category': ErrorType.ENVIRONMENT.value, 'code': exc.code}
    if isinstance(exc, ValidationError):
        return {'category': ErrorType.VALIDATION.value, 'code': exc.code}
    if isinstance(exc, TransportError):
        return {'category': ErrorType.TRANSPORT.value, 'code': exc.code}

    if any(x in low for x in ('crc16', 'crc check', 'checksum')):
        return {'category': ErrorType.CRC.value, 'code': CRCError.code}
    if any(x in low for x in ('plugin', 'mount plugin', 'plugin dispatch')):
        return {'category': ErrorType.PLUGIN.value, 'code': PluginLoadError.code}
    if any(x in low for x in ('rscore', 'rust', 'os_rscore', 'dll load failed')):
        return {'category': ErrorType.RUST_CORE.value, 'code': RustCoreLoadError.code}
    if any(x in low for x in ('timeout', 'connection refused', 'network', 'no route', 'unreachable', 'socket')):
        return {'category': ErrorType.NETWORK.value, 'code': NetworkError.code}
    if any(x in low for x in ('config', 'json decode', 'invalid config')):
        return {'category': ErrorType.CONFIG.value, 'code': ConfigurationError.code}

    if isinstance(exc, OpenSynapticError):
        cat = getattr(exc, 'error_type', ErrorType.INTERNAL)
        return {'category': getattr(cat, 'value', ErrorType.INTERNAL.value), 'code': getattr(exc, 'code', 'OS_GENERIC')}
    return {'category': 'unclassified', 'code': None}

