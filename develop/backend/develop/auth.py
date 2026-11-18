"""Optional scoped bearer-token auth for Develop."""

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
        return "develop:read"
    if method == "POST" and path.endswith("/build"):
        return "develop:build"
    if "/agent" in path or "/prompt" in path:
        return "develop:agent"
    if method in ("POST", "PUT", "DELETE"):
        return "develop:write"
    return "develop:read"


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
