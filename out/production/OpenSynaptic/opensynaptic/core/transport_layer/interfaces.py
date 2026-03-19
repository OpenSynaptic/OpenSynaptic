from abc import ABC, abstractmethod

class TransportProtocol(ABC):
    """Transport-layer protocol interface (L4-ish)."""
    name = 'unknown'

    @abstractmethod
    def send(self, payload, config):
        raise NotImplementedError

    def is_available(self):
        return True
