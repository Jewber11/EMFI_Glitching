"""Append-only audit logging for dangerous Control actions."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request


def default_audit_dir() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "share"))
    return state / "emfi-control" / "audit"


class AuditLog:
    def __init__(self, audit_dir: Path | None = None) -> None:
        self.audit_dir = audit_dir or default_audit_dir()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path_for_today(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.audit_dir / f"audit-{day}.jsonl"

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry = dict(entry)
        entry.setdefault(
            "ts", datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        )
        line = json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n"
        with self._lock:
            with self._path_for_today().open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        return entry


def dangerous_action(method: str, path: str) -> str | None:
    if method not in ("POST", "PUT", "DELETE"):
        return None
    if path in ("/arm", "/disarm"):
        return f"safety:{path.removeprefix('/')}"
    if path.startswith("/shouter/"):
        return f"shouter:{path.rsplit('/', 1)[-1]}"
    if path.startswith("/motion/"):
        return f"motion:{path.rsplit('/', 1)[-1]}"
    if path in ("/devices/scaffold/power", "/devices/scaffold/power_cycle"):
        return f"scaffold:{path.rsplit('/', 1)[-1]}"
    if path.startswith("/devices/") and (
        path.endswith("/connect") or path.endswith("/disconnect")
    ):
        return f"device:{path.rsplit('/', 1)[-1]}"
    if path.startswith("/target/"):
        return f"target:{path.rsplit('/', 1)[-1]}"
    if path == "/campaigns":
        return "campaign:start"
    if path.startswith("/campaigns/") and path.endswith("/stop"):
        return "campaign:stop"
    if path.startswith("/replay/"):
        return "campaign:replay"
    return None


def _principal_name(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, dict):
        return str(principal.get("name") or "authenticated")
    return "anonymous"


def install_audit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        path = request.url.path
        action = dangerous_action(request.method, path)
        response = await call_next(request)
        if action:
            ctx = getattr(request.app.state, "ctx", None)
            audit_log = getattr(ctx, "audit_log", None)
            if audit_log is not None:
                audit_log.append(
                    {
                        "action": action,
                        "method": request.method,
                        "path": path,
                        "query": str(request.url.query),
                        "status_code": response.status_code,
                        "principal": _principal_name(request),
                        "client": request.client.host if request.client else None,
                    }
                )
        return response
