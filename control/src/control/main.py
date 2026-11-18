"""FastAPI entrypoint for Control."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from control.audit import install_audit_middleware
from control.auth import install_auth_middleware
from control.deps import ADAPTER_ATTR, DEVICE_NAMES, build_context
from control.routers import (
    campaigns,
    config as config_router,
    devices,
    motion,
    runs,
    safety as safety_router,
    shouter,
    target,
    ws,
)
from control.safety import Disarmed, RateLimited
from control.ports import list_ports, pick_port
from control.adapters.pico_probe import PicoProbeAdapter

LOGGER = logging.getLogger("control")

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _default_log_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "share"))
    return base / "emfi-control" / "logs"


def setup_logging() -> Path:
    """Configure root logger: console + rotating file."""
    log_dir = Path(os.environ.get("CONTROL_LOG_DIR", "")) or _default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "control.log"

    fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for h in list(root.handlers):
        root.removeHandler(h)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10_000_000, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return log_path


async def _discovery_loop(ctx):
    """Discover and reconnect rig devices through their serialized workers."""
    while True:
        ports = await asyncio.to_thread(list_ports, ctx.config.get("known_devices", default={}) or {})
        overrides = ctx.config.get("ports", default={}) or {}
        present = {p["device"] for p in ports}
        pico_ports = [p for p in ports if p.get("vid") == 0x2e8a and p.get("pid") == 0x000c]
        backend = ctx.config.get("programmer", "backend", default="auto")
        if backend == "auto" and len(pico_ports) == 1 and not isinstance(ctx.xds110, PicoProbeAdapter):
            ctx.xds110 = PicoProbeAdapter(binary=ctx.config.get("programmer", "probe_rs_bin"), probe=ctx.config.get("programmer", "probe"))
        if isinstance(ctx.xds110, PicoProbeAdapter):
            adapter = ctx.xds110
            serial = adapter.probe.split(":", 2)[2] if adapter.probe and adapter.probe.count(":") >= 2 else None
            matches = [p for p in pico_ports if not serial or serial == p.get("serial_number")]
            port = matches[0]["device"] if len(matches) == 1 and "xds110" not in ctx.manual_disconnects else None
            if port != adapter._port:
                if port:
                    adapter.connect(port)
                else:
                    adapter.disconnect()
                ds = ctx.state.devices["xds110"]
                ds.connected = adapter.connected
                ds.port = adapter._port
                ds.label = "Pico Debug Probe"
                ctx.broadcast("device_status", {"name": "xds110", "connected": ds.connected, "port": ds.port, "label": ds.label})
        for name in ("chipshover", "chipshouter"):
            adapter = ctx.adapter_for(name)
            if name in ctx.manual_disconnects:
                continue
            worker = ctx.workers.get(name)
            port = overrides.get(f"{name}_override")
            if name == "chipshover" and not port:
                matches = [p for p in ports if p.get("guess") == name]
                port = matches[0]["device"] if len(matches) == 1 else None
            if adapter.connected and adapter._port and adapter._port not in present:
                await worker.call(adapter.disconnect)
            if not adapter.connected and (port or name == "chipshouter"):
                def connect_if_needed():
                    if not adapter.connected:
                        adapter.connect(port)
                try:
                    await worker.call(connect_if_needed)
                except Exception as exc:
                    LOGGER.debug("Auto-connect %s failed: %s", name, exc)
            ds = ctx.state.devices[name]
            changed = ds.connected != adapter.connected or ds.port != adapter._port
            ds.connected = adapter.connected
            ds.available = True
            ds.port = adapter._port
            if changed:
                if name == "chipshover":
                    ctx.state.origin_set = False
                    ctx.state.top_right_set = False
                    ctx.broadcast_state()
                ds.last_error = None
                ctx.broadcast("device_status", {"name": name, "connected": ds.connected, "available": True, "port": ds.port, "last_error": None, "busy": False, "label": None})
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log_path = setup_logging()
    LOGGER.info("Control starting — log file: %s", log_path)

    ctx = build_context()
    app.state.ctx = ctx
    ctx.loop = asyncio.get_running_loop()

    LOGGER.info("API docs: http://%s:%s/docs",
                os.environ.get("CONTROL_HOST", "0.0.0.0"),
                os.environ.get("CONTROL_PORT", "8001"))

    discovery_task = asyncio.create_task(_discovery_loop(ctx))

    try:
        yield
    finally:
        discovery_task.cancel()
        try:
            await discovery_task
        except asyncio.CancelledError:
            pass
        LOGGER.info("Control shutting down")
        ctx.stop_flag.set()
        if ctx.ad2_stream_task is not None:
            ctx.ad2_stream_task.cancel()
        for adapter in (ctx.shover, ctx.shouter, ctx.scaffold, ctx.xds110, ctx.ad2):
            try:
                adapter.disconnect()
            except Exception:
                pass
        ctx.workers.shutdown_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title="EMFI Control",
        version="0.1.0",
        description="Hardware-singleton service for the lab rig.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_auth_middleware(app)
    install_audit_middleware(app)

    @app.exception_handler(Disarmed)
    async def _disarmed(request: Request, exc: Disarmed) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(RateLimited)
    async def _rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(NotImplementedError)
    async def _not_impl(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": f"Not implemented: {exc}"})

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, object]:
        return {"ok": True, "service": "control"}

    @app.get("/readyz", include_in_schema=False, response_model=None)
    async def readyz(request: Request) -> JSONResponse | dict[str, object]:
        ctx = getattr(request.app.state, "ctx", None)
        if ctx is None:
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "ready": False,
                    "service": "control",
                    "reason": "context not initialized",
                },
            )

        config = ctx.config.snapshot()
        ports = config.get("ports", {}) or {}
        state = ctx.state.snapshot()
        devices = state.get("devices", {})

        return {
            "ok": True,
            "ready": True,
            "service": "control",
            "config_path": str(ctx.config.path),
            "log_dir": str(ctx.logbook.log_dir),
            "audit_dir": str(getattr(getattr(ctx, "audit_log", None), "audit_dir", "")),
            "armed": state.get("armed", False),
            "stop_requested": ctx.stop_flag.is_set(),
            "devices": {
                name: {
                    "connected": status.get("connected", False),
                    "busy": status.get("busy", False),
                    "port_configured": bool(ports.get(f"{name}_override")),
                }
                for name, status in devices.items()
            },
        }

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        LOGGER.info("%s %s", request.method, request.url.path)
        response: Response = await call_next(request)
        if response.status_code >= 400:
            LOGGER.warning("%s %s -> %d", request.method, request.url.path, response.status_code)
        return response

    app.include_router(config_router.router)
    app.include_router(devices.router)
    app.include_router(motion.router)
    app.include_router(shouter.router)
    app.include_router(target.router)
    app.include_router(campaigns.router)
    app.include_router(runs.router)
    app.include_router(safety_router.router)
    app.include_router(ws.router)

    return app


app = create_app()
