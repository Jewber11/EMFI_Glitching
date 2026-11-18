from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from control.audit import AuditLog, dangerous_action, install_audit_middleware


def test_dangerous_action_classifies_mutating_hardware_routes() -> None:
    assert dangerous_action("POST", "/arm") == "safety:arm"
    assert dangerous_action("POST", "/shouter/pulse") == "shouter:pulse"
    assert dangerous_action("POST", "/motion/move_abs") == "motion:move_abs"
    assert dangerous_action("POST", "/devices/scaffold/power") == "scaffold:power"
    assert dangerous_action("POST", "/devices/xds110/connect") == "device:connect"
    assert dangerous_action("POST", "/target/flash") == "target:flash"
    assert dangerous_action("POST", "/campaigns") == "campaign:start"
    assert dangerous_action("POST", "/campaigns/run-1/stop") == "campaign:stop"
    assert dangerous_action("POST", "/replay/run-1") == "campaign:replay"


def test_dangerous_action_ignores_safe_reads() -> None:
    assert dangerous_action("GET", "/devices") is None
    assert dangerous_action("GET", "/campaigns") is None
    assert dangerous_action("OPTIONS", "/campaigns") is None


def test_audit_log_appends_jsonl(tmp_path: Path) -> None:
    audit_log = AuditLog(tmp_path)

    entry = audit_log.append({"action": "safety:arm", "principal": "tester"})

    files = list(tmp_path.glob("audit-*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    assert json.loads(line) == entry
    assert entry["action"] == "safety:arm"
    assert entry["principal"] == "tester"
    assert "ts" in entry


def test_audit_middleware_records_dangerous_routes(tmp_path: Path) -> None:
    class Context:
        audit_log = AuditLog(tmp_path)

    app = FastAPI()
    app.state.ctx = Context()
    install_audit_middleware(app)

    @app.post("/arm")
    async def arm(request: Request):
        request.state.principal = {"name": "agent"}
        return {"ok": True}

    response = TestClient(app).post("/arm?reason=test")

    assert response.status_code == 200
    audit_file = next(tmp_path.glob("audit-*.jsonl"))
    entry = json.loads(audit_file.read_text(encoding="utf-8"))
    assert entry["action"] == "safety:arm"
    assert entry["method"] == "POST"
    assert entry["path"] == "/arm"
    assert entry["query"] == "reason=test"
    assert entry["principal"] == "agent"
    assert entry["status_code"] == 200


def test_audit_middleware_ignores_safe_routes(tmp_path: Path) -> None:
    class Context:
        audit_log = AuditLog(tmp_path)

    app = FastAPI()
    app.state.ctx = Context()
    install_audit_middleware(app)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert list(tmp_path.glob("audit-*.jsonl")) == []
