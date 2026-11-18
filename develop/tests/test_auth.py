from __future__ import annotations

import json

from fastapi.testclient import TestClient

from develop.main import create_app


def test_auth_disabled_by_default_allows_readyz(monkeypatch):
    monkeypatch.delenv("EMFI_AUTH_TOKENS", raising=False)
    response = TestClient(create_app()).get("/readyz")

    assert response.status_code == 200


def test_auth_requires_bearer_when_tokens_configured(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "builder", "scopes": ["develop:read"]}}),
    )

    response = TestClient(create_app()).get("/readyz")

    assert response.status_code == 401


def test_auth_accepts_matching_scope(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "builder", "scopes": ["develop:read"]}}),
    )

    response = TestClient(create_app()).get(
        "/readyz", headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 200


def test_auth_allows_cors_preflight_without_bearer(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "builder", "scopes": ["develop:build"]}}),
    )

    response = TestClient(create_app()).options(
        "/projects/demo/build",
        headers={
            "Origin": "https://emfi.ics.red",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200


def test_auth_rejects_missing_scope(monkeypatch):
    monkeypatch.setenv(
        "EMFI_AUTH_TOKENS",
        json.dumps({"secret": {"name": "reader", "scopes": ["develop:read"]}}),
    )

    response = TestClient(create_app()).post(
        "/projects/demo/build", headers={"Authorization": "Bearer secret"}, json={}
    )

    assert response.status_code == 403
