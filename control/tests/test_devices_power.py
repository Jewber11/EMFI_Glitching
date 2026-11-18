from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import sys
import types
from typing import Any, Dict, List, Tuple

import pytest
from fastapi import HTTPException

if importlib.util.find_spec("serial") is None:
    serial = types.ModuleType("serial")
    tools = types.ModuleType("serial.tools")
    list_ports = types.ModuleType("serial.tools.list_ports")
    list_ports.comports = lambda: []
    tools.list_ports = list_ports
    serial.tools = tools
    sys.modules["serial"] = serial
    sys.modules["serial.tools"] = tools
    sys.modules["serial.tools.list_ports"] = list_ports

from control.routers import devices
from control.workers import WorkerRegistry


class _FakeScaffold:
    def __init__(self) -> None:
        self.dut = False
        self.platform = False
        self.cycles: List[Tuple[str, float]] = []

    def power_state(self) -> Dict[str, bool]:
        return {"dut": self.dut, "platform": self.platform}

    def dut_power(self, on: bool) -> None:
        self.dut = on

    def platform_power(self, on: bool) -> None:
        self.platform = on

    def dut_power_cycle(self, off_time: float = 0.05) -> None:
        self.cycles.append(("dut", off_time))
        self.dut = True

    def platform_power_cycle(self, off_time: float = 0.05) -> None:
        self.cycles.append(("platform", off_time))
        self.platform = True

    def all_power_cycle(self, off_time: float = 0.05) -> None:
        self.cycles.append(("all", off_time))
        self.dut = True
        self.platform = True


@dataclass
class _FakeContext:
    scaffold: _FakeScaffold
    workers: WorkerRegistry
    broadcasts: List[Tuple[str, Dict[str, Any]]]

    def broadcast(self, topic: str, payload: Dict[str, Any]) -> None:
        self.broadcasts.append((topic, payload))


@pytest.fixture
def ctx():
    context = _FakeContext(_FakeScaffold(), WorkerRegistry(), [])
    try:
        yield context
    finally:
        context.workers.shutdown_all()


async def test_scaffold_power_get_reads_both_rails(ctx):
    ctx.scaffold.dut = True
    assert await devices.scaffold_power_get(ctx) == {"dut": True, "platform": False}


async def test_scaffold_power_set_updates_and_broadcasts(ctx):
    req = devices._PowerSetRequest(rail="platform", on=True)

    state = await devices.scaffold_power_set(req, ctx)

    assert state == {"dut": False, "platform": True}
    assert ctx.broadcasts == [("scaffold_power", state)]


async def test_scaffold_power_set_all_updates_both_rails(ctx):
    req = devices._PowerSetRequest(rail="all", on=True)

    state = await devices.scaffold_power_set(req, ctx)

    assert state == {"dut": True, "platform": True}


async def test_scaffold_power_cycle_uses_selected_rail_and_broadcasts(ctx):
    req = devices._PowerCycleRequest(rail="dut", off_time=0.2)

    state = await devices.scaffold_power_cycle(req, ctx)

    assert ctx.scaffold.cycles == [("dut", 0.2)]
    assert state == {"dut": True, "platform": False}
    assert ctx.broadcasts == [("scaffold_power", state)]


async def test_scaffold_power_rejects_unknown_rail(ctx):
    req = devices._PowerSetRequest(rail="bogus", on=True)

    with pytest.raises(HTTPException) as excinfo:
        await devices.scaffold_power_set(req, ctx)

    assert excinfo.value.status_code == 400
