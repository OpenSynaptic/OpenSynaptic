from abc import ABC, abstractmethod

class PhysicalProtocol(ABC):
    """Physical-layer protocol interface (L1/L2-ish)."""
    name = 'unknown'

    @abstractmethod
    def send(self, payload, config):
        raise NotImplementedError
