"""ARM gate, rate limiter, stop event — the safety primitives.

Carry-forward from old-em-setup/glitchweb/backend/app/safety.py.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional

LOGGER = logging.getLogger(__name__)


class Disarmed(RuntimeError):
    """Raised when a pulse-emitting call is attempted while disarmed."""


class RateLimited(RuntimeError):
    """Raised when the pulse rate limiter rejects a call."""


@dataclass
class ArmGate:
    """Global software arming gate.

    Any code path that produces a pulse must call require_armed(). The UI
    sets armed via arm()/disarm(). An auto-disarm timer re-closes the gate
    after a configurable idle window.
    """

    auto_disarm_seconds: float = 300.0  # 5 minutes default
    _armed: bool = False
    _last_pulse_ts: float = 0.0
    _lock: threading.RLock = field(default_factory=threading.RLock)
    on_change: Optional[Callable[[bool], None]] = None

    def arm(self) -> None:
        with self._lock:
            self._armed = True
            self._last_pulse_ts = time.monotonic()
        LOGGER.info("ARM gate ENGAGED")
        self._notify()

    def disarm(self) -> None:
        with self._lock:
            self._armed = False
        LOGGER.info("ARM gate DISARMED")
        self._notify()

    def is_armed(self) -> bool:
        with self._lock:
            if self._armed and self.auto_disarm_seconds > 0:
                if time.monotonic() - self._last_pulse_ts > self.auto_disarm_seconds:
                    self._armed = False
                    LOGGER.info("ARM gate auto-disarmed after %.0fs idle", self.auto_disarm_seconds)
            return self._armed

    def require_armed(self) -> None:
        if not self.is_armed():
            LOGGER.warning("Pulse blocked: ARM gate is closed")
            raise Disarmed("Glitch-emitting actions blocked: ARM gate is closed")
        with self._lock:
            self._last_pulse_ts = time.monotonic()

    def _notify(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change(self._armed)
            except Exception:
                pass


@dataclass
class RateLimiter:
    """Sliding-window rate limiter (token bucket without the bucket)."""

    name: str
    max_per_sec: float
    _window: Deque[float] = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> None:
        if self.max_per_sec <= 0:
            return
        now = time.monotonic()
        cutoff = now - 1.0
        with self._lock:
            while self._window and self._window[0] < cutoff:
                self._window.popleft()
            if len(self._window) >= self.max_per_sec:
                LOGGER.warning("Rate limit hit: %s (%.1f/s)", self.name, self.max_per_sec)
                raise RateLimited(
                    f"Rate limit on '{self.name}': "
                    f"{self.max_per_sec:.1f} per second exceeded"
                )
            self._window.append(now)


class StopFlag:
    """Cooperative stop signal for the scan orchestrator."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)
