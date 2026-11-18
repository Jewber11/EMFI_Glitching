"""Tests for DeviceWorker — single-threaded serialization."""

from __future__ import annotations

import threading
import time

import pytest

from control.workers import DeviceWorker, WorkerRegistry


def test_worker_returns_value():
    w = DeviceWorker("test")
    fut = w.submit(lambda x: x * 2, 21)
    assert fut.result(timeout=2) == 42
    w.shutdown()


def test_worker_propagates_exception():
    w = DeviceWorker("test")
    fut = w.submit(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        fut.result(timeout=2)
    w.shutdown()


def test_worker_serializes_calls():
    """All calls execute on the same thread, in order."""
    w = DeviceWorker("test")
    threads: list[int] = []

    def record():
        threads.append(threading.get_ident())
        time.sleep(0.01)

    futs = [w.submit(record) for _ in range(5)]
    for f in futs:
        f.result(timeout=2)
    assert len(set(threads)) == 1, "all calls should run on the same thread"
    w.shutdown()


def test_registry_caches_by_name():
    reg = WorkerRegistry()
    a = reg.get("foo")
    b = reg.get("foo")
    c = reg.get("bar")
    assert a is b
    assert a is not c
    reg.shutdown_all()
