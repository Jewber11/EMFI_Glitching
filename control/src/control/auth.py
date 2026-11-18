"""Optional scoped bearer-token auth for Control."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from emfi_protocol.auth import AuthConfigError, authenticate_bearer, load_token_config, missing_scope


PUBLIC_PATHS = (
    "/healthz",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _required_scope(method: str, path: str) -> str:
    if path == "/readyz" or method == "GET":
        return "control:read"
    if path == "/campaigns/preflight":
        return "campaign:preflight"
    if path == "/campaigns" and method == "POST":
        return "campaign:start"
    if path.startswith("/campaigns/") and path.endswith("/stop"):
        return "campaign:stop"
    if path in ("/arm", "/disarm"):
        return "safety:arm"
    if path.startswith("/target/"):
        return "target:flash"
    if path.startswith("/motion/"):
        return "motion:write"
    if path.startswith("/shouter/"):
        return "shouter:write"
    if path.startswith("/devices/"):
        return "devices:write"
    if path.startswith("/replay/"):
        return "campaign:start"
    return "control:write"


def install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Callable):
        path = request.url.path
        if request.method == "OPTIONS":
            return await call_next(request)
        if any(path == p or path.startswith(f"{p}/") for p in PUBLIC_PATHS):
            return await call_next(request)

        try:
            token_config = load_token_config()
        except AuthConfigError as exc:
            return JSONResponse(status_code=500, content={"detail": str(exc)})

        if not token_config:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse(status_code=401, content={"detail": "missing bearer token"})

        principal = authenticate_bearer(token, token_config)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "invalid bearer token"})

        required = _required_scope(request.method, path)
        missing = missing_scope(principal, required)
        if missing is not None:
            return JSONResponse(
                status_code=403,
                content={"detail": f"token missing required scope: {missing}"},
            )

        request.state.principal = {"name": principal.name, "scopes": sorted(principal.scopes)}
        return await call_next(request)
