from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class OpenSynapticError(Exception):
    """Base exception for project-level typed errors."""

    code = 'OS_GENERIC'


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

    def __str__(self) -> str:
        return self.message


@dataclass
class TransportError(OpenSynapticError):
    message: str
    code = 'OS_TRANSPORT'

    def __str__(self) -> str:
        return self.message


def classify_exception(exc: Exception) -> Dict[str, Optional[str]]:
    if isinstance(exc, EnvironmentMissingError):
        return {'category': 'environment_missing', 'code': exc.code}
    if isinstance(exc, ValidationError):
        return {'category': 'validation', 'code': exc.code}
    if isinstance(exc, TransportError):
        return {'category': 'transport', 'code': exc.code}
    if isinstance(exc, OpenSynapticError):
        return {'category': 'opensynaptic', 'code': getattr(exc, 'code', 'OS_GENERIC')}
    return {'category': 'unclassified', 'code': None}

