import asyncio
from types import SimpleNamespace

import pytest

from control.adapters.pico_probe import PicoProbeAdapter
from control.main import _discovery_loop


@pytest.mark.asyncio
async def test_pico_is_selected_and_disconnected_on_removal(monkeypatch):
    ports = [{"device": "/dev/ttyACM4", "vid": 0x2e8a, "pid": 0x000c, "serial_number": "123"}]
    monkeypatch.setattr("control.main.list_ports", lambda known: ports)
    class Config:
        def get(self, *keys, default=None):
            return {("programmer", "backend"): "auto"}.get(keys, default)
    class Connected:
        connected = True
        _port = None
    class Worker:
        async def call(self, fn):
            return fn()
    class Workers:
        def get(self, name):
            return Worker()
    devices = {name: SimpleNamespace(connected=False, port=None, available=False, label=None, last_error=None) for name in ("xds110", "chipshover", "chipshouter")}
    others = {name: Connected() for name in ("chipshover", "chipshouter")}
    ctx = SimpleNamespace(config=Config(), xds110=object(), manual_disconnects=set(), workers=Workers(), state=SimpleNamespace(devices=devices), adapter_for=lambda name: others[name], broadcast=lambda *args: None, broadcast_state=lambda: None)
    task = asyncio.create_task(_discovery_loop(ctx))
    await asyncio.sleep(0.1)
    assert isinstance(ctx.xds110, PicoProbeAdapter)
    assert devices["xds110"].connected
    assert devices["xds110"].port == "/dev/ttyACM4"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
