"""Device discovery + connection lifecycle."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from emfi_protocol.devices import DeviceStatus as DeviceStatusModel

from control.deps import (
    ADAPTER_ATTR,
    DEVICE_NAMES,
    AppContext,
    call_adapter,
    call_subprocess_adapter,
    get_ctx,
)
from control.ports import list_ports, pick_port

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


def _device_status(ctx: AppContext, name: str) -> Dict[str, Any]:
    adapter = ctx.adapter_for(name)
    ds = ctx.state.devices.get(name)
    status: Dict[str, Any] = {
        "name": name,
        "available": getattr(adapter, "available", True),
        "connected": adapter.connected,
        "port": getattr(adapter, "_port", None),
        "label": ds.label if ds else None,
        "last_error": ds.last_error if ds else None,
        "busy": ctx.workers.get(name).busy if name != "xds110" else False,
    }
    if name == "chipshouter":
        last_fault = getattr(adapter, "last_fault", None)
        status["fault_names"] = last_fault["names"] if last_fault else None
    return status


@router.get("")
def list_devices(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """List discovered serial devices with classification guesses."""
    known = ctx.config.get("known_devices", default={})
    ports = list_ports(known)
    device_statuses = [_device_status(ctx, name) for name in DEVICE_NAMES]
    return {"ports": ports, "devices": device_statuses}


@router.get("/chipshouter/faults")
async def chipshouter_faults(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """Return the ChipSHOUTER's last latched fault + live current faults.

    Shape: ``{"last_fault": {"ts", "names", "raw"} | None,
              "current": [names], "connected": bool}``.
    """
    return ctx.shouter.get_faults()


# ----------------------------------------------------------------------
# Scaffold power rails
#
# Scaffold has two independently-switchable 3.3 V supplies on the board:
#   - DUT      → the MSPM0L2228 target socket            (UI label: slot 1)
#   - Platform → daughterboard / aux header              (UI label: slot 2)
# Both run through the FastAPI scaffold DeviceWorker for serial safety.
# ----------------------------------------------------------------------

_RAILS = ("dut", "platform", "all")


class ConnectRequest(BaseModel):
    port: str | None = None


class _PowerSetRequest(BaseModel):
    rail: str = Field(..., description="One of: dut, platform, all")
    on: bool


class _PowerCycleRequest(BaseModel):
    rail: str = Field(..., description="One of: dut, platform, all")
    off_time: float = Field(0.05, ge=0.0, le=5.0, description="Seconds OFF before re-energising")


class _HuskyConfigureRequest(BaseModel):
    delay_us: float = Field(..., ge=0.0)
    width_ns: float = Field(..., gt=0.0)
    output: str = Field("crowbar", min_length=1)


class _AD2ConfigureRequest(BaseModel):
    sample_rate_hz: float | None = Field(None, gt=0)
    samples: int | None = Field(None, ge=64, le=8192)
    analog_range_v: float | None = Field(None, gt=0)


class _AD2StreamRequest(BaseModel):
    period_s: float = Field(0.5, ge=0.1, le=5.0)


class _AD2TriggeredCaptureRequest(BaseModel):
    sample_rate_hz: float = Field(100_000_000.0, gt=0)
    samples: int = Field(8192, ge=64, le=8192)
    analog_range_v: float = Field(50.0, gt=0)
    trigger_level_v: float = 1.0
    trigger_hysteresis_v: float = Field(0.1, ge=0)
    timeout_s: float = Field(2.0, gt=0, le=30.0)


def _broadcast_power(ctx: AppContext, state: Dict[str, bool]) -> None:
    ctx.broadcast("scaffold_power", state)


@router.get("/scaffold/power")
async def scaffold_power_get(ctx: AppContext = Depends(get_ctx)) -> Dict[str, bool]:
    """Read the live state of both Scaffold power rails."""
    worker = ctx.workers.get("scaffold")
    state = await call_adapter(worker, ctx.scaffold.power_state)
    return state


@router.post("/scaffold/power")
async def scaffold_power_set(
    req: _PowerSetRequest, ctx: AppContext = Depends(get_ctx)
) -> Dict[str, bool]:
    """Enable or disable a Scaffold power rail."""
    if req.rail not in _RAILS:
        raise HTTPException(status_code=400, detail=f"rail must be one of {_RAILS}")
    worker = ctx.workers.get("scaffold")
    if req.rail == "dut":
        await call_adapter(worker, ctx.scaffold.dut_power, req.on)
    elif req.rail == "platform":
        await call_adapter(worker, ctx.scaffold.platform_power, req.on)
    else:
        await call_adapter(worker, ctx.scaffold.dut_power, req.on)
        await call_adapter(worker, ctx.scaffold.platform_power, req.on)
    state = await call_adapter(worker, ctx.scaffold.power_state)
    _broadcast_power(ctx, state)
    LOGGER.info("Scaffold power set: rail=%s on=%s -> %s", req.rail, req.on, state)
    return state


@router.post("/scaffold/power_cycle")
async def scaffold_power_cycle(
    req: _PowerCycleRequest, ctx: AppContext = Depends(get_ctx)
) -> Dict[str, bool]:
    """Power-cycle a Scaffold rail (or both)."""
    if req.rail not in _RAILS:
        raise HTTPException(status_code=400, detail=f"rail must be one of {_RAILS}")
    worker = ctx.workers.get("scaffold")
    if req.rail == "dut":
        await call_adapter(worker, ctx.scaffold.dut_power_cycle, req.off_time)
    elif req.rail == "platform":
        await call_adapter(worker, ctx.scaffold.platform_power_cycle, req.off_time)
    else:
        await call_adapter(worker, ctx.scaffold.all_power_cycle, req.off_time)
    state = await call_adapter(worker, ctx.scaffold.power_state)
    _broadcast_power(ctx, state)
    LOGGER.info("Scaffold power cycled: rail=%s off_time=%.3fs -> %s", req.rail, req.off_time, state)
    return state


@router.get("/husky/status")
async def husky_status(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """Return placeholder Husky status without adding it to DEVICE_NAMES yet."""
    return ctx.husky.status()


@router.post("/husky/configure")
async def husky_configure(
    req: _HuskyConfigureRequest, ctx: AppContext = Depends(get_ctx)
) -> Dict[str, Any]:
    """Configure the future Husky crowbar path.

    Until the ChipWhisperer implementation lands, this route safely returns
    501/500 through the shared adapter error mapping.
    """
    return await call_subprocess_adapter(
        ctx.husky.configure_crowbar,
        delay_us=req.delay_us,
        width_ns=req.width_ns,
        output=req.output,
    )


@router.post("/husky/crowbar_pulse")
async def husky_crowbar_pulse(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """Fire one future Husky crowbar pulse when implementation is available."""
    return await call_subprocess_adapter(ctx.husky.crowbar_pulse)


@router.get("/ad2/status")
async def ad2_status(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    return ctx.ad2.status()


@router.post("/ad2/configure")
async def ad2_configure(req: _AD2ConfigureRequest, ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    status = await call_subprocess_adapter(
        ctx.ad2.configure,
        sample_rate_hz=req.sample_rate_hz,
        samples=req.samples,
        analog_range_v=req.analog_range_v,
    )
    ctx.broadcast("device_status", _device_status(ctx, "ad2"))
    return status


@router.get("/ad2/capture")
async def ad2_capture(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    capture = await call_subprocess_adapter(ctx.ad2.capture)
    ctx.broadcast("ad2_capture", capture)
    return capture


@router.post("/ad2/capture_triggered")
async def ad2_capture_triggered(
    req: _AD2TriggeredCaptureRequest, ctx: AppContext = Depends(get_ctx)
) -> Dict[str, Any]:
    if ctx.ad2_stream_task is not None:
        ctx.ad2_stream_task.cancel()
        ctx.ad2_stream_task = None
    capture = await call_subprocess_adapter(
        ctx.ad2.capture_triggered,
        sample_rate_hz=req.sample_rate_hz,
        samples=req.samples,
        analog_range_v=req.analog_range_v,
        trigger_level_v=req.trigger_level_v,
        trigger_hysteresis_v=req.trigger_hysteresis_v,
        timeout_s=req.timeout_s,
    )
    ctx.broadcast("ad2_capture", capture)
    ctx.broadcast("device_status", _device_status(ctx, "ad2"))
    return capture


@router.post("/ad2/start_stream")
async def ad2_start_stream(req: _AD2StreamRequest, ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    if ctx.ad2_stream_task is not None and not ctx.ad2_stream_task.done():
        return {"streaming": True, "period_s": req.period_s}

    async def _stream() -> None:
        while True:
            try:
                capture = await call_subprocess_adapter(ctx.ad2.capture)
                ctx.broadcast("ad2_capture", capture)
                ctx.broadcast("device_status", _device_status(ctx, "ad2"))
            except Exception as exc:
                ds = ctx.state.devices.get("ad2")
                if ds:
                    ds.connected = ctx.ad2.connected
                    ds.last_error = str(exc)
                ctx.broadcast("device_status", _device_status(ctx, "ad2"))
                LOGGER.warning("AD2 stream capture failed: %s", exc)
            await asyncio.sleep(req.period_s)

    ctx.ad2_stream_task = asyncio.create_task(_stream())
    return {"streaming": True, "period_s": req.period_s}


@router.post("/ad2/stop_stream")
async def ad2_stop_stream(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    if ctx.ad2_stream_task is not None:
        ctx.ad2_stream_task.cancel()
        ctx.ad2_stream_task = None
    return {"streaming": False}


@router.post("/{name}/connect")
async def connect(name: str, request: ConnectRequest | None = None, ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """Open the serial port for a device."""
    if name not in DEVICE_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown device: {name}")

    adapter = ctx.adapter_for(name)
    ctx.manual_disconnects.discard(name)
    if name == "ad2":
        await call_subprocess_adapter(adapter.connect)
        ds = ctx.state.devices.get(name)
        if ds:
            ds.connected = True
            ds.port = None
            ds.last_error = None
        status = _device_status(ctx, name)
        ctx.broadcast("device_status", status)
        LOGGER.info("Device %s connected", name)
        return status

    known = ctx.config.get("known_devices", default={})
    overrides = ctx.config.get("ports", default={})
    ports = list_ports(known)
    requested_port = request.port.strip() if request and request.port else None
    if requested_port:
        ctx.config.update({"ports": {f"{name}_override": requested_port}})
    if name == "chipshover" and not (requested_port or overrides.get("chipshover_override")):
        matches = [p for p in ports if p.get("guess") == name]
        if len(matches) > 1:
            raise HTTPException(status_code=400, detail="Multiple printer ports found; select one explicitly")
    port = pick_port(name, ports, requested_port or overrides.get(f"{name}_override"))
    if name == "chipshouter" and not (requested_port or overrides.get("chipshouter_override")):
        port = None  # Vendor discovery chooses the EMFI interface.
    if adapter.connected:
        if requested_port and requested_port != getattr(adapter, "_port", None):
            await ctx.workers.get(name).call(adapter.disconnect)
        else:
            return _device_status(ctx, name)

    if name == "xds110":
        await call_subprocess_adapter(adapter.connect, port)
    else:
        worker = ctx.workers.get(name)
        await call_adapter(worker, adapter.connect, port)

    if name == "chipshover":
        ctx.state.origin_set = False
        ctx.state.top_right_set = False
        ctx.broadcast_state()
    ds = ctx.state.devices.get(name)
    if ds:
        ds.connected = True
        ds.port = getattr(adapter, "_port", None) or port
        ds.last_error = None

    status = _device_status(ctx, name)
    ctx.broadcast("device_status", status)
    LOGGER.info("Device %s connected on %s", name, port)
    return status


@router.post("/{name}/disconnect")
async def disconnect(name: str, ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    if name not in DEVICE_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown device: {name}")

    adapter = ctx.adapter_for(name)
    ctx.manual_disconnects.add(name)

    if name in ("xds110", "ad2"):
        await call_subprocess_adapter(adapter.disconnect)
    else:
        worker = ctx.workers.get(name)
        await call_adapter(worker, adapter.disconnect)

    if name == "chipshover":
        ctx.state.origin_set = False
        ctx.state.top_right_set = False
        ctx.broadcast_state()
    ds = ctx.state.devices.get(name)
    if ds:
        ds.connected = False
        ds.port = None

    status = _device_status(ctx, name)
    ctx.broadcast("device_status", status)
    LOGGER.info("Device %s disconnected", name)
    return status
