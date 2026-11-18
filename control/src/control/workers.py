"""Per-device single-threaded executor.

The invariant: every hardware call for a given device is serialized through
one worker thread. This makes pyserial safe without explicit locking and
prevents two browser tabs from racing on the same port.

Carry-forward from old-em-setup/glitchweb/backend/app/workers.py.
TODO(spec): split read-queue from write-queue per device so status polls
don't compete with writes.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)


class DeviceBusy(RuntimeError):
    """Raised when a non-queueable call is rejected because the worker is busy."""


class DeviceWorker:
    """Wraps a single hardware device's calls in a single worker thread."""

    def __init__(self, name: str):
        self.name = name
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"dev-{name}"
        )
        self._inflight = 0

    def submit(self, fn: Callable[..., Any], *args, **kwargs) -> Future:
        self._inflight += 1
        fut = self._executor.submit(fn, *args, **kwargs)
        fut.add_done_callback(lambda _f: self._dec())
        return fut

    async def call(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        fut = self.submit(fn, *args, **kwargs)
        return await asyncio.wrap_future(fut, loop=loop)

    def _dec(self) -> None:
        self._inflight = max(0, self._inflight - 1)

    @property
    def busy(self) -> bool:
        return self._inflight > 0

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


class WorkerRegistry:
    """Holds one DeviceWorker per device name."""

    def __init__(self) -> None:
        self._workers: dict[str, DeviceWorker] = {}

    def get(self, name: str) -> DeviceWorker:
        if name not in self._workers:
            self._workers[name] = DeviceWorker(name)
        return self._workers[name]

    def shutdown_all(self) -> None:
        for w in self._workers.values():
            w.shutdown(wait=False)
        self._workers.clear()
