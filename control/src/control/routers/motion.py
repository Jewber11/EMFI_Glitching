"""XYZ motion control."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from control.deps import AppContext, call_adapter, get_ctx

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/motion", tags=["motion"])


class MoveAbsRequest(BaseModel):
    x: float
    y: float
    z: float


class MoveRelRequest(BaseModel):
    axis: str
    distance: float


class SetTopRightRequest(BaseModel):
    x: float
    y: float


class FixtureGridRequest(BaseModel):
    name: str = Field("default", min_length=1, max_length=80)
    origin: List[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)
    top_right: List[float] = Field(..., min_length=2, max_length=2)
    machine_origin: List[float] = Field(..., min_length=3, max_length=3)
    machine_top_right: Optional[List[float]] = Field(None, min_length=3, max_length=3)
    step_size_mm: float = Field(1.0, gt=0)
    z_min_mm: float = 0.0
    z_max_mm: float = 0.5
    z_step_mm: float = Field(0.1, gt=0)
    notes: str = ""


class SaveCurrentFixtureRequest(BaseModel):
    name: str = Field("default", min_length=1, max_length=80)
    step_size_mm: float = Field(1.0, gt=0)
    z_min_mm: float = 0.0
    z_max_mm: float = 0.5
    z_step_mm: float = Field(0.1, gt=0)
    notes: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _validate_fixture(raw: Dict[str, Any]) -> Dict[str, Any]:
    origin = [float(raw["origin"][0]), float(raw["origin"][1])]
    top_right = [float(raw["top_right"][0]), float(raw["top_right"][1])]
    z_min = float(raw.get("z_min_mm", 0.0))
    z_max = float(raw.get("z_max_mm", 0.5))
    z_step = float(raw.get("z_step_mm", 0.1))
    step_size = float(raw.get("step_size_mm", 1.0))
    if step_size <= 0:
        raise HTTPException(status_code=400, detail="fixture step_size_mm must be positive")
    if z_max < z_min:
        raise HTTPException(status_code=400, detail="fixture z_max_mm must be >= z_min_mm")
    if z_step <= 0:
        raise HTTPException(status_code=400, detail="fixture z_step_mm must be positive")
    return {
        "name": str(raw.get("name") or "default"),
        "origin": origin,
        "top_right": top_right,
        "machine_origin": [float(v) for v in raw["machine_origin"][:3]],
        "machine_top_right": [float(v) for v in raw.get("machine_top_right")[:3]]
        if raw.get("machine_top_right") else None,
        "step_size_mm": step_size,
        "z_min_mm": z_min,
        "z_max_mm": z_max,
        "z_step_mm": z_step,
        "notes": str(raw.get("notes") or ""),
        "updated_at": str(raw.get("updated_at") or _utc_now()),
    }


def _fixture_from_config(ctx: AppContext) -> Dict[str, Any] | None:
    raw = ctx.config.get("fixture", "default_grid", default=None)
    if not isinstance(raw, dict):
        return None
    return _validate_fixture(raw)


def _broadcast_position(ctx: AppContext) -> None:
    lx, ly, lz = ctx.state.position_logical
    mx, my, mz = ctx.state.position_machine
    ctx.broadcast("position", {
        "x": lx, "y": ly, "z": lz,
        "machine_x": mx, "machine_y": my, "machine_z": mz,
    })


async def _refresh_position(ctx: AppContext) -> None:
    """Read actual position from the adapter and update both machine and logical state.

    The logical position is derived from the machine reading via a pure
    transform (origin offset + axis inversion/swap), so the WS ``position``
    topic always reports the user's coordinate system — never the gantry's.
    """
    worker = ctx.workers.get("chipshover")
    machine = await call_adapter(worker, ctx.shover.get_position)
    ctx.state.position_machine = machine
    ctx.state.position_logical = ctx.shover.machine_to_logical(*machine)


@router.post("/move_abs")
async def move_abs(req: MoveAbsRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshover")
    await call_adapter(worker, ctx.shover.move_absolute_logical, req.x, req.y, req.z)
    await _refresh_position(ctx)
    _broadcast_position(ctx)
    lx, ly, lz = ctx.state.position_logical
    return {"ok": True, "position": [lx, ly, lz]}


@router.post("/move_rel")
async def move_rel(req: MoveRelRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    if req.axis.upper() not in ("X", "Y", "Z"):
        raise HTTPException(status_code=400, detail=f"Invalid axis: {req.axis}")
    worker = ctx.workers.get("chipshover")
    await call_adapter(worker, ctx.shover.move_relative, req.axis.upper(), req.distance)
    await _refresh_position(ctx)
    _broadcast_position(ctx)
    lx, ly, lz = ctx.state.position_logical
    return {"ok": True, "position": [lx, ly, lz]}


@router.post("/home")
async def home(ctx: AppContext = Depends(get_ctx)) -> dict:
    worker = ctx.workers.get("chipshover")
    await call_adapter(worker, ctx.shover.home)
    ctx.state.origin_set = False
    ctx.state.top_right_set = False
    ctx.broadcast_state()
    await _refresh_position(ctx)
    _broadcast_position(ctx)
    lx, ly, lz = ctx.state.position_logical
    return {"ok": True, "position": [lx, ly, lz]}


@router.post("/set_origin")
async def set_origin(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Mark current position as logical (0, 0, 0)."""
    worker = ctx.workers.get("chipshover")
    await call_adapter(worker, ctx.shover.set_origin)
    ctx.state.origin_set = True
    await _refresh_position(ctx)
    _broadcast_position(ctx)
    ctx.broadcast_state()
    return {"ok": True, "origin_set": True}


@router.post("/set_top_right")
async def set_top_right(req: SetTopRightRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    ctx.state.top_right = (req.x, req.y)
    ctx.state.top_right_set = True
    ctx.broadcast_state()
    return {"ok": True, "top_right": [req.x, req.y]}


@router.get("/fixture")
async def get_fixture(ctx: AppContext = Depends(get_ctx)) -> dict:
    fixture = _fixture_from_config(ctx)
    return {"ok": True, "fixture": fixture}


@router.post("/fixture")
async def save_fixture(req: FixtureGridRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    fixture = _validate_fixture({**req.model_dump(), "updated_at": _utc_now()})
    ctx.config.update({"fixture": {"default_grid": fixture}})
    ctx.broadcast("fixture", fixture)
    return {"ok": True, "fixture": fixture}


@router.post("/fixture/save_current")
async def save_current_fixture(req: SaveCurrentFixtureRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    if not ctx.shover.origin_set:
        raise HTTPException(status_code=400, detail="cannot save fixture before setting origin")
    if not ctx.state.top_right_set:
        raise HTTPException(status_code=400, detail="cannot save fixture before setting top-right")
    fixture = _validate_fixture({
        "name": req.name,
        "origin": [0.0, 0.0],
        "top_right": list(ctx.state.top_right),
        "machine_origin": list(ctx.shover.origin_machine),
        "machine_top_right": list(ctx.state.position_machine),
        "step_size_mm": req.step_size_mm,
        "z_min_mm": req.z_min_mm,
        "z_max_mm": req.z_max_mm,
        "z_step_mm": req.z_step_mm,
        "notes": req.notes,
        "updated_at": _utc_now(),
    })
    ctx.config.update({"fixture": {"default_grid": fixture}})
    ctx.broadcast("fixture", fixture)
    return {"ok": True, "fixture": fixture}


@router.post("/fixture/apply")
async def apply_fixture(ctx: AppContext = Depends(get_ctx)) -> dict:
    fixture = _fixture_from_config(ctx)
    if fixture is None:
        raise HTTPException(status_code=404, detail="no default fixture saved")
    worker = ctx.workers.get("chipshover")
    machine_origin = fixture["machine_origin"]
    await call_adapter(worker, ctx.shover.set_origin_machine, *machine_origin)
    ctx.state.origin_set = True
    ctx.state.top_right = (float(fixture["top_right"][0]), float(fixture["top_right"][1]))
    ctx.state.top_right_set = True
    await _refresh_position(ctx)
    _broadcast_position(ctx)
    ctx.broadcast_state()
    ctx.broadcast("fixture", fixture)
    return {"ok": True, "fixture": fixture, "origin_set": True, "top_right": list(ctx.state.top_right)}
