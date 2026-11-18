"""ChipWhisperer Husky crowbar adapter scaffold.

This intentionally stops short of touching real hardware. The first dual-target
work needs Control to expose a stable Husky surface and report clearly when the
ChipWhisperer stack is not installed or the hardware implementation is still
pending.
"""

from __future__ import annotations

import importlib.util
from typing import Any, Dict, Optional

from control.adapters.base import BaseAdapter


class HuskyAdapter(BaseAdapter):
    """Placeholder for Platform-rail crowbar timing via ChipWhisperer Husky."""

    name = "husky"

    def __init__(self) -> None:
        self._port: Optional[str] = None
        self._scope: Any = None
        self._last_error: Optional[str] = None
        self._config: Optional[Dict[str, Any]] = None
        self._available = importlib.util.find_spec("chipwhisperer") is not None
        if not self._available:
            self._last_error = "chipwhisperer library not installed"

    @property
    def available(self) -> bool:
        return self._available

    def connect(self, port: Optional[str] = None) -> None:
        if not self._available:
            raise NotImplementedError("ChipWhisperer Husky support requires chipwhisperer")
        self._last_error = "Husky hardware connection is not implemented yet"
        raise NotImplementedError("HuskyAdapter.connect")

    def disconnect(self) -> None:
        self._scope = None
        self._port = None

    @property
    def connected(self) -> bool:
        return self._scope is not None

    def configure_crowbar(
        self,
        *,
        delay_us: float,
        width_ns: float,
        output: str = "crowbar",
    ) -> Dict[str, Any]:
        if not self._available:
            raise NotImplementedError("ChipWhisperer Husky support requires chipwhisperer")
        if not self.connected:
            raise RuntimeError("Husky is not connected")
        self._config = {
            "delay_us": delay_us,
            "width_ns": width_ns,
            "output": output,
        }
        return dict(self._config)

    def crowbar_pulse(self) -> Dict[str, Any]:
        if not self._available:
            raise NotImplementedError("ChipWhisperer Husky support requires chipwhisperer")
        if not self.connected:
            raise RuntimeError("Husky is not connected")
        if self._config is None:
            raise RuntimeError("Husky crowbar is not configured")
        raise NotImplementedError("HuskyAdapter.crowbar_pulse")

    def status(self) -> Dict[str, Any]:
        status = super().status()
        status.update(
            {
                "available": self.available,
                "configured": self._config is not None,
                "implementation": "stub",
                "config": dict(self._config) if self._config is not None else None,
            }
        )
        return status
