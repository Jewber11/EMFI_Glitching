"""ARM gate endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from emfi_protocol.devices import ArmState

from control.deps import AppContext, get_ctx

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["safety"])


@router.post("/arm", response_model=ArmState)
async def arm(ctx: AppContext = Depends(get_ctx)) -> ArmState:
    """Engage the ARM gate. UI should require a hold gesture to call this."""
    ctx.arm_gate.arm()
    return ArmState(
        armed=True,
        auto_disarm_seconds=ctx.arm_gate.auto_disarm_seconds,
        seconds_until_auto_disarm=ctx.arm_gate.auto_disarm_seconds,
    )


@router.post("/disarm", response_model=ArmState)
async def disarm(ctx: AppContext = Depends(get_ctx)) -> ArmState:
    ctx.arm_gate.disarm()
    ctx.stop_flag.set()
    await ctx.workers.get("chipshouter").call(ctx.shouter.disarm_safe)
    return ArmState(
        armed=False,
        auto_disarm_seconds=ctx.arm_gate.auto_disarm_seconds,
        seconds_until_auto_disarm=None,
    )


@router.get("/arm_state", response_model=ArmState)
async def arm_state(ctx: AppContext = Depends(get_ctx)) -> ArmState:
    armed = ctx.arm_gate.is_armed()
    remaining = None
    if armed:
        elapsed = time.monotonic() - ctx.arm_gate._last_pulse_ts
        remaining = max(0.0, ctx.arm_gate.auto_disarm_seconds - elapsed)
    return ArmState(
        armed=armed,
        auto_disarm_seconds=ctx.arm_gate.auto_disarm_seconds,
        seconds_until_auto_disarm=remaining,
    )
