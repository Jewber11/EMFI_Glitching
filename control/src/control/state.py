"""In-memory app state + broadcast hub.

Carry-forward from old-em-setup/glitchweb/backend/app/state.py. The state is
the single source of truth pushed to every connected WS client. Mutations
funnel through update_*() methods that emit events.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceStatus:
    name: str
    available: bool = False        # adapter import succeeded
    connected: bool = False        # serial port open
    port: Optional[str] = None
    label: Optional[str] = None
    last_error: Optional[str] = None
    busy: bool = False


@dataclass
class Counters:
    attempts: int = 0
    glitches: int = 0
    hangs: int = 0
    crashes: int = 0
    nothings: int = 0
    unobserved: int = 0
    campaigns: int = 0

    def reset(self) -> None:
        self.attempts = self.glitches = self.hangs = self.crashes = 0
        self.nothings = self.unobserved = self.campaigns = 0

    def record(self, outcome: str) -> None:
        self.attempts += 1
        if outcome == "glitch":
            self.glitches += 1
        elif outcome == "hang":
            self.hangs += 1
        elif outcome == "crash":
            self.crashes += 1
        elif outcome == "unobserved":
            self.unobserved += 1
        else:
            self.nothings += 1


@dataclass
class ScanProgress:
    active: bool = False
    completed: int = 0
    total: int = 0
    current_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class AppState:
    devices: Dict[str, DeviceStatus] = field(default_factory=dict)
    position_logical: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    position_machine: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    origin_set: bool = False
    top_right_set: bool = False
    top_right: Tuple[float, float] = (0.0, 0.0)
    counters: Counters = field(default_factory=Counters)
    scan: ScanProgress = field(default_factory=ScanProgress)
    armed: bool = False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "devices": {
                k: {
                    "name": v.name,
                    "available": v.available,
                    "connected": v.connected,
                    "port": v.port,
                    "label": v.label,
                    "last_error": v.last_error,
                    "busy": v.busy,
                }
                for k, v in self.devices.items()
            },
            "position_logical": list(self.position_logical),
            "position_machine": list(self.position_machine),
            "origin_set": self.origin_set,
            "top_right_set": self.top_right_set,
            "top_right": list(self.top_right),
            "counters": {
                "attempts": self.counters.attempts,
                "glitches": self.counters.glitches,
                "hangs": self.counters.hangs,
                "crashes": self.counters.crashes,
                "nothings": self.counters.nothings,
                "unobserved": self.counters.unobserved,
                "campaigns": self.counters.campaigns,
            },
            "scan": {
                "active": self.scan.active,
                "completed": self.scan.completed,
                "total": self.scan.total,
                "current_xyz": list(self.scan.current_xyz),
            },
            "armed": self.armed,
        }


class Broadcaster:
    """Distributes events to all connected WebSocket clients."""

    def __init__(self) -> None:
        self._queues: List[asyncio.Queue] = []
        self._lock = threading.Lock()

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._queues.append(q)
        LOGGER.debug("WS client registered (%d total)", len(self._queues))
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        with self._lock:
            if q in self._queues:
                self._queues.remove(q)
        LOGGER.debug("WS client unregistered (%d remaining)", len(self._queues))

    def broadcast(self, message: Dict[str, Any]) -> None:
        # Drop oldest on backpressure rather than block the producer.
        with self._lock:
            queues = list(self._queues)
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except Exception:
                    pass

    def broadcast_threadsafe(
        self, loop: asyncio.AbstractEventLoop, message: Dict[str, Any]
    ) -> None:
        loop.call_soon_threadsafe(self.broadcast, message)
