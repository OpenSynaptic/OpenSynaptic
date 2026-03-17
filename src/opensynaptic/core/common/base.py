# OpenSynaptic Core Common Interface Layer
# 仅定义协议/接口/常量/异常，不实现具体逻辑
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional, Union

# ---- 基础异常 ----
class NativeLibraryUnavailable(Exception):
    """Raised when a required native library is unavailable."""
    pass

# ---- 配置/上下文协议 ----
class BaseContext(ABC):
    @property
    @abstractmethod
    def config_path(self) -> str:
        pass

    @abstractmethod
    def read_json(self, path: str) -> Any:
        pass

    @abstractmethod
    def write_json(self, path: str, data: Any) -> None:
        pass

    @abstractmethod
    def get_registry_path(self, aid: Union[int, str]) -> str:
        pass

# ---- 日志消息协议 ----
class LogMsg:
    # 仅定义常用枚举，具体内容由实现层补充
    READY = "READY"
    ERROR = "ERROR"
    # ...可扩展...

# ---- Base62 编解码协议 ----
class Base62Codec(ABC):
    @staticmethod
    @abstractmethod
    def encode(data: bytes) -> str:
        pass

    @staticmethod
    @abstractmethod
    def decode(data: str) -> bytes:
        pass

# ---- 校验/加密协议 ----
def crc8(data: bytes) -> int:
    """协议层定义，具体实现由实现层提供"""
    raise NotImplementedError

def crc16_ccitt(data: bytes) -> int:
    raise NotImplementedError

def xor_payload_into(payload: bytes, key: bytes) -> bytes:
    raise NotImplementedError

def derive_session_key(seed: bytes) -> bytes:
    raise NotImplementedError

# ---- 缓冲区协议 ----
def ensure_bytes(data: Any) -> bytes:
    raise NotImplementedError

def payload_len(data: Any) -> int:
    raise NotImplementedError

def zero_copy_enabled() -> bool:
    raise NotImplementedError

def as_readonly_view(data: bytes) -> memoryview:
    raise NotImplementedError

# ---- 基类接口（示例） ----
class BaseOpenSynaptic(ABC):
    @abstractmethod
    def ensure_id(self, server_ip: str, server_port: int, device_meta: dict = None) -> None:
        pass

    @abstractmethod
    def transmit(self, sensors: List[Any]) -> Tuple[bytes, int, str]:
        pass

    @abstractmethod
    def dispatch(self, packet: bytes, medium: str = "UDP") -> bool:
        pass

class BaseOpenSynapticStandardizer(ABC):
    @abstractmethod
    def standardize(self, sensors: List[Any]) -> List[Any]:
        pass

class BaseOpenSynapticEngine(ABC):
    @abstractmethod
    def compress(self, data: Any) -> Any:
        pass

    @abstractmethod
    def decompress(self, data: Any) -> Any:
        pass

class BaseOSVisualFusionEngine(ABC):
    @abstractmethod
    def run_engine(self, *args, **kwargs) -> Any:
        pass

class BaseOSHandshakeManager(ABC):
    @abstractmethod
    def negotiate(self, *args, **kwargs) -> Any:
        pass

class BaseTransporterManager(ABC):
    @abstractmethod
    def send(self, payload: bytes, config: dict) -> bool:
        pass

    @abstractmethod
    def listen(self, config: dict, callback: Any) -> None:
        pass

# ---- END OF FILE ----

