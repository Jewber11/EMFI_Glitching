from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Any, Dict

import pytest
from fastapi import HTTPException

from control.adapters.husky import HuskyAdapter
from control.routers import devices


def _force_missing_chipwhisperer(monkeypatch: pytest.MonkeyPatch) -> None:
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any):
        if name == "chipwhisperer":
            return None
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def test_husky_status_reports_missing_chipwhisperer(monkeypatch):
    _force_missing_chipwhisperer(monkeypatch)

    adapter = HuskyAdapter()

    assert adapter.status() == {
        "name": "husky",
        "available": False,
        "connected": False,
        "port": None,
        "last_error": "chipwhisperer library not installed",
        "configured": False,
        "implementation": "stub",
        "config": None,
    }


def test_husky_stub_methods_report_not_implemented_when_library_absent(monkeypatch):
    _force_missing_chipwhisperer(monkeypatch)
    adapter = HuskyAdapter()

    with pytest.raises(NotImplementedError, match="requires chipwhisperer"):
        adapter.connect()
    with pytest.raises(NotImplementedError, match="requires chipwhisperer"):
        adapter.configure_crowbar(delay_us=1.0, width_ns=50.0)
    with pytest.raises(NotImplementedError, match="requires chipwhisperer"):
        adapter.crowbar_pulse()


@dataclass
class _FakeContext:
    husky: HuskyAdapter


async def test_husky_status_route_reports_stub(monkeypatch):
    _force_missing_chipwhisperer(monkeypatch)
    ctx = _FakeContext(husky=HuskyAdapter())

    status = await devices.husky_status(ctx)

    assert status["name"] == "husky"
    assert status["available"] is False
    assert status["connected"] is False
    assert status["implementation"] == "stub"


async def test_husky_configure_route_maps_missing_library_to_501(monkeypatch):
    _force_missing_chipwhisperer(monkeypatch)
    ctx = _FakeContext(husky=HuskyAdapter())

    with pytest.raises(HTTPException) as excinfo:
        await devices.husky_configure(
            devices._HuskyConfigureRequest(delay_us=1.0, width_ns=50.0),
            ctx,
        )

    assert excinfo.value.status_code == 501
