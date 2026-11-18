"""Common adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseAdapter(ABC):
    """All hardware adapters implement this surface: connect, disconnect, status."""

    name: str

    @abstractmethod
    def connect(self, port: Optional[str] = None) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    def status(self) -> Dict[str, Any]:
        """Return adapter status dict (name, connected, port, last_error)."""
        return {
            "name": self.name,
            "connected": self.connected,
            "port": getattr(self, "_port", None),
            "last_error": getattr(self, "_last_error", None),
        }
