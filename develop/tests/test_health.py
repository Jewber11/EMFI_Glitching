"""Tests for Develop service health/readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from develop.main import create_app


def test_healthz_is_lightweight():
    app = create_app()
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "develop"}


def test_readyz_reports_configured_paths_and_tools():
    app = create_app()
    client = TestClient(app)

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ready"] is True
    assert body["service"] == "develop"
    assert body["paths"]["templates_root_exists"] is True
    assert "projects_root" in body["paths"]
    assert "static_build" in body["paths"]
    assert body["control_url"].startswith("http")
    assert "arm_gcc" in body["tools"]
