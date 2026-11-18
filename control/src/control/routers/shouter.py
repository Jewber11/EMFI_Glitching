"""ChipSHOUTER control endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from control.deps import AppContext, call_adapter, get_ctx

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/shouter", tags=["shouter"])


class PulseRequest(BaseModel):
    voltage: Optional[int] = None
    pulse_width_ns: Optional[int] = None
    repeat: int = Field(1, ge=1, le=100)


class ConfigRequest(BaseModel):
    voltage: int
    pulse_width_ns: int
    pulse_repeat: int = 1
    pulse_deadtime_ms: int = 10
    arm_timeout_min: int = 1
    mute: bool = True


@router.post("/arm")
async def arm(ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshouter")
    await call_adapter(worker, ctx.shouter.arm)
    ctx.broadcast("device_status", {
        "name": "chipshouter", "connected": ctx.shouter.connected,
    })
    return {"ok": True, "state": "armed"}


@router.get("/status")
async def status(ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshouter")
    return await call_adapter(worker, ctx.shouter.status)


@router.post("/disarm")
async def disarm(ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshouter")
    await call_adapter(worker, ctx.shouter.disarm)
    ctx.broadcast("device_status", {
        "name": "chipshouter", "connected": ctx.shouter.connected,
    })
    return {"ok": True, "state": "disarmed"}


@router.post("/pulse")
async def pulse(req: PulseRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Fire one or more pulses. Requires ArmGate to be armed."""
    ctx.arm_gate.require_armed()
    worker = ctx.workers.get("chipshouter")
    if req.pulse_width_ns is not None:
        await call_adapter(worker, ctx.shouter.set_pulse_width, req.pulse_width_ns)
    for _ in range(req.repeat):
        ctx.arm_gate.require_armed()
        ctx.rate_limiter.acquire()
        await call_adapter(worker, ctx.shouter.pulse)
        ctx.state.counters.record("unobserved")

    ctx.broadcast("counter", {
        "attempts": ctx.state.counters.attempts,
        "glitches": ctx.state.counters.glitches,
        "hangs": ctx.state.counters.hangs,
        "crashes": ctx.state.counters.crashes,
        "nothings": ctx.state.counters.nothings,
        "unobserved": ctx.state.counters.unobserved,
        "campaigns": ctx.state.counters.campaigns,
    })
    return {"ok": True, "pulses_fired": req.repeat}


@router.post("/config")
async def configure(req: ConfigRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshouter")
    await call_adapter(
        worker, ctx.shouter.configure,
        voltage=req.voltage,
        pulse_width_ns=req.pulse_width_ns,
        pulse_repeat=req.pulse_repeat,
        pulse_deadtime_ms=req.pulse_deadtime_ms,
        arm_timeout_min=req.arm_timeout_min,
        mute=req.mute,
    )
    return {"ok": True, "config": req.model_dump()}
