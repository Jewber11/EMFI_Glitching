"""Tests for Control service health/readiness endpoints."""

from __future__ import annotations

import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

from fastapi.testclient import TestClient

try:
    import serial.tools.list_ports  # noqa: F401
except ImportError:
    serial = types.ModuleType("serial")
    serial.__spec__ = ModuleSpec("serial", loader=None)
    serial_tools = types.ModuleType("serial.tools")
    serial_tools.__spec__ = ModuleSpec("serial.tools", loader=None)
    serial_list_ports = types.ModuleType("serial.tools.list_ports")
    serial_list_ports.__spec__ = ModuleSpec("serial.tools.list_ports", loader=None)
    serial_list_ports.comports = lambda: []
    serial_tools.list_ports = serial_list_ports
    serial.tools = serial_tools
    sys.modules.setdefault("serial", serial)
    sys.modules.setdefault("serial.tools", serial_tools)
    sys.modules.setdefault("serial.tools.list_ports", serial_list_ports)

from control.main import create_app
from control.state import AppState, DeviceStatus


class FakeConfig:
    path = Path("/tmp/control-config.json")

    def snapshot(self):
        return {
            "ports": {
                "chipshover_override": "/dev/ttyUSB0",
                "chipshouter_override": None,
            },
        }


class FakeLogbook:
    log_dir = Path("/tmp/control-logs")


class FakeStopFlag:
    def is_set(self) -> bool:
        return False


class FakeContext:
    config = FakeConfig()
    logbook = FakeLogbook()
    stop_flag = FakeStopFlag()
    state = AppState(
        devices={
            "chipshover": DeviceStatus(name="chipshover", connected=True),
            "chipshouter": DeviceStatus(name="chipshouter", busy=True),
        },
    )


def test_healthz_is_lightweight():
    app = create_app()
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "control"}


def test_readyz_reports_configured_state_without_hardware():
    app = create_app()
    app.state.ctx = FakeContext()
    client = TestClient(app)

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ready"] is True
    assert body["service"] == "control"
    assert body["config_path"] == "/tmp/control-config.json"
    assert body["log_dir"] == "/tmp/control-logs"
    assert body["stop_requested"] is False
    assert body["devices"]["chipshover"]["connected"] is True
    assert body["devices"]["chipshover"]["port_configured"] is True
    assert body["devices"]["chipshouter"]["busy"] is True
