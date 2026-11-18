from __future__ import annotations

import json
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
from control.state import AppState


class _Config:
    path = Path("/tmp/config.json")

    def snapshot(self):
        return {"ports": {}}


class _Logbook:
    log_dir = Path("/tmp/logs")


class _StopFlag:
    def is_set(self):
        return False


class _Context:
    config = _Config()
    logbook = _Logbook()
    stop_flag = _StopFlag()
    state = AppState()
    campaigns = {}


def test_auth_disabled_by_default_allows_readyz(monkeypatch):
    monkeypatch.delenv("EMFI_AUTH_TOKENS", raising=False)
    app = create_app()
    app.state.ctx = _Context()

    response = TestClient(app).get("/readyz")

    assert response.status_code == 200


def test_auth_requires_bearer_when_tokens_configured(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "agent", "scopes": ["control:read"]}}),
    )
    app = create_app()
    app.state.ctx = _Context()

    response = TestClient(app).get("/readyz")

    assert response.status_code == 401


def test_auth_accepts_matching_scope(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "agent", "scopes": ["control:read"]}}),
    )
    app = create_app()
    app.state.ctx = _Context()

    response = TestClient(app).get("/readyz", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200


def test_auth_allows_cors_preflight_without_bearer(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "agent", "scopes": ["campaign:start"]}}),
    )
    app = create_app()

    response = TestClient(app).options(
        "/campaigns",
        headers={
            "Origin": "https://emfi.ics.red",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200


def test_auth_rejects_missing_scope(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "agent", "scopes": ["control:read"]}}),
    )
    app = create_app()

    response = TestClient(app).post("/campaigns", headers={"Authorization": "Bearer secret"}, json={})

    assert response.status_code == 403


def test_auth_metadata_update_uses_write_fallback_scope(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "agent", "scopes": ["control:read"]}}),
    )
    app = create_app()

    response = TestClient(app).put(
        "/campaigns/camp-1/metadata",
        headers={"Authorization": "Bearer secret"},
        json={"notes": "x", "tags": []},
    )

    assert response.status_code == 403
    assert "control:write" in response.json()["detail"]
