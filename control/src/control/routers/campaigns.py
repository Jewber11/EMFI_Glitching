"""Campaign lifecycle endpoints."""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from emfi_protocol.campaigns import (
    AutomationBudgetPolicy,
    Campaign,
    CampaignMetadata,
    CampaignMetadataUpdate,
    CampaignStatus,
)

from control.deps import AppContext, get_ctx
from control.orchestrator import materialize_target_delay_sweep

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignPreflight(BaseModel):
    ok: bool
    total_attempts: int
    grid_points: int
    sweep_points: int
    required_devices: List[str]
    blockers: List[str]
    warnings: List[str]
    estimates: Dict[str, Any]


def _count_sweep_points(sweep) -> int:
    count = 1
    if isinstance(sweep, dict):
        dimensions = (sweep.get("delay_us"), sweep.get("pulse_width_ns"), sweep.get("voltage_v"))
        attempts_per_point = sweep.get("attempts_per_point", 1)
    else:
        dimensions = (sweep.delay_us, sweep.pulse_width_ns, sweep.voltage_v)
        attempts_per_point = sweep.attempts_per_point
    for dim in dimensions:
        if dim is None:
            continue
        start = float(dim["start"]) if isinstance(dim, dict) else float(dim.start)
        stop = float(dim["stop"]) if isinstance(dim, dict) else float(dim.stop)
        step = float(dim["step"]) if isinstance(dim, dict) else float(dim.step)
        if step > 0:
            steps = int((stop - start) / step) + 1
            count *= max(1, steps)
    count *= max(1, attempts_per_point)
    return count


def _count_grid_points(grid) -> int:
    x_steps = int(math.floor(abs(grid.top_right[0] - grid.origin[0]) / grid.step_size_mm + 1e-9)) + 1
    y_steps = int(math.floor(abs(grid.top_right[1] - grid.origin[1]) / grid.step_size_mm + 1e-9)) + 1
    z_step = grid.z_step_mm if grid.z_step_mm > 0 else 1
    z_range = grid.z_max_mm - grid.z_min_mm
    z_steps = int(math.floor(z_range / z_step + 1e-9)) + 1 if z_range > 0 else 1
    return max(1, x_steps) * max(1, y_steps) * max(1, z_steps)


def _connected_devices(ctx: AppContext) -> Dict[str, bool]:
    devices = ctx.state.snapshot().get("devices", {})
    return {
        name: bool(status.get("connected", False))
        for name, status in devices.items()
        if isinstance(status, dict)
    }


def _provenance_blockers(campaign: Campaign, ctx: AppContext) -> List[str]:
    if not campaign.build_sha:
        return []

    flashed = getattr(ctx, "flashed_firmware", None)
    if flashed is None:
        return []

    blockers: List[str] = []
    if flashed.build_sha != campaign.build_sha:
        blockers.append(
            "campaign build_sha "
            f"{campaign.build_sha} does not match flashed DUT build {flashed.build_sha}"
        )
    if flashed.project_id and flashed.project_id != campaign.project_id:
        blockers.append(
            "campaign project_id "
            f"{campaign.project_id} does not match flashed DUT project {flashed.project_id}"
        )
    return blockers


_VALID_TRIGGER_MODES = ("software", "one-shot", "free-run", "disabled")


def _sweep_range_max(dim: Any) -> float | None:
    if dim is None:
        return None
    start = float(dim["start"]) if isinstance(dim, dict) else float(dim.start)
    stop = float(dim["stop"]) if isinstance(dim, dict) else float(dim.stop)
    return max(start, stop)


def _automation_policy_findings(
    policy: AutomationBudgetPolicy | None,
    campaign: Campaign,
    materialized_sweep: Any,
    total_attempts: int,
    min_runtime_seconds: float | None,
) -> tuple[List[str], List[str]]:
    blockers: List[str] = []
    warnings: List[str] = []
    if policy is None:
        warnings.append(
            "campaign has no automation_policy; preflight cannot enforce automation budget caps"
        )
        return blockers, warnings

    if policy.max_attempts is not None and total_attempts > policy.max_attempts:
        blockers.append(
            f"total attempts {total_attempts} exceeds automation_policy.max_attempts {policy.max_attempts}"
        )

    if policy.max_runtime_seconds is not None:
        if min_runtime_seconds is None:
            warnings.append(
                "automation_policy.max_runtime_seconds set but no max_pulses_per_sec "
                "rate limit is configured, so runtime cannot be estimated"
            )
        elif min_runtime_seconds > policy.max_runtime_seconds:
            blockers.append(
                "estimated minimum runtime "
                f"{min_runtime_seconds:.3f}s exceeds automation_policy.max_runtime_seconds "
                f"{policy.max_runtime_seconds:g}s"
            )

    if policy.max_voltage is not None:
        voltage_candidates = [float(campaign.shouter_voltage)]
        voltage_candidates.extend(
            value
            for value in (
                _sweep_range_max(
                    materialized_sweep.get("voltage_v")
                    if isinstance(materialized_sweep, dict)
                    else materialized_sweep.voltage_v
                ),
            )
            if value is not None
        )
        max_requested_voltage = max(voltage_candidates)
        if max_requested_voltage > policy.max_voltage:
            blockers.append(
                f"requested voltage {max_requested_voltage:g} exceeds automation_policy.max_voltage "
                f"{policy.max_voltage}"
            )

    if policy.allowed_trigger_modes is not None:
        allowed = [mode.strip() for mode in policy.allowed_trigger_modes if mode.strip()]
        invalid = [mode for mode in allowed if mode not in _VALID_TRIGGER_MODES]
        if invalid:
            blockers.append(
                "automation_policy.allowed_trigger_modes contains invalid modes: "
                + ", ".join(invalid)
            )
        if campaign.trigger_mode not in allowed:
            blockers.append(
                f"trigger_mode {campaign.trigger_mode} is not allowed by automation_policy.allowed_trigger_modes"
            )

    return blockers, warnings


def _preflight(campaign: Campaign, ctx: AppContext) -> CampaignPreflight:
    blockers: List[str] = []
    warnings: List[str] = []

    grid_points = _count_grid_points(campaign.grid)
    materialized_sweep, sweep_note = materialize_target_delay_sweep(
        campaign.project_id, campaign.build_sha, campaign.target_pc, campaign.sweep
    )
    sweep_points = _count_sweep_points(materialized_sweep)
    total = grid_points * sweep_points

    x_span = campaign.grid.top_right[0] - campaign.grid.origin[0]
    y_span = campaign.grid.top_right[1] - campaign.grid.origin[1]
    if x_span < 0:
        warnings.append("grid opposite corner is left of origin; scanning X in the negative direction")
    if y_span < 0:
        warnings.append("grid opposite corner is below origin; scanning Y in the negative direction")
    if x_span == 0:
        warnings.append("grid X span is zero; campaign will scan a single X column")
    if y_span == 0:
        warnings.append("grid Y span is zero; campaign will scan a single Y row")
    if campaign.grid.z_max_mm < campaign.grid.z_min_mm:
        blockers.append("grid z_max_mm must be >= z_min_mm")

    trigger_mode = campaign.trigger_mode
    if trigger_mode not in _VALID_TRIGGER_MODES:
        blockers.append("trigger_mode must be one of software, one-shot, free-run, disabled")

    required_devices = ["chipshover", "chipshouter"]
    if trigger_mode in ("one-shot", "free-run"):
        required_devices.append("scaffold")
    if trigger_mode != "software":
        blockers.append("FaultyCat currently supports software trigger only")
    if campaign.shouter_pulse_width_ns < 1000 or campaign.shouter_pulse_width_ns > 50000 or campaign.shouter_pulse_width_ns % 1000:
        blockers.append("FaultyCat pulse width must be 1000–50000 ns in 1000 ns steps")
    if materialized_sweep.delay_us is not None:
        blockers.append("Delay sweeps require external trigger support")
    width_range = materialized_sweep.pulse_width_ns
    if width_range is not None and (width_range.start < 1000 or width_range.stop > 50000 or width_range.stop < width_range.start or any(value % 1000 for value in (width_range.start, width_range.stop, width_range.step))):
        blockers.append("FaultyCat width sweep must use 1000–50000 ns in 1000 ns steps")
    if not campaign.target_serial_port:
        warnings.append("No target serial port selected; outcomes require a host script or will be unobserved")
    if campaign.sweep and campaign.sweep.voltage_v is not None:
        blockers.append("FaultyCat does not support voltage sweeps")

    if not ctx.state.origin_set:
        blockers.append("Set the Ender 3 scan origin before starting")
    connected = _connected_devices(ctx)
    for device in required_devices:
        if not connected.get(device, False):
            blockers.append(f"required device is not connected: {device}")

    if not connected.get("xds110", False):
        warnings.append("xds110 is not connected; flashing/debug will not work until it is connected")
    if not campaign.build_sha:
        warnings.append("campaign has no pinned build_sha; Control may build/use current project state")
    elif getattr(ctx, "flashed_firmware", None) is None:
        warnings.append("no successful DUT flash recorded; cannot verify pinned build_sha")
    blockers.extend(_provenance_blockers(campaign, ctx))
    if ctx.campaigns and any(getattr(c, "active", False) for c in ctx.campaigns.values()):
        blockers.append("another campaign is currently active")
    if not ctx.state.snapshot().get("armed", False):
        warnings.append("system is not armed; campaign start will require arming first")
    if sweep_note:
        warnings.append(sweep_note)

    safety = ctx.config.get("safety", default={}) or {}
    max_voltage = int(safety.get("max_voltage_v", 0) or 0)
    if max_voltage and campaign.shouter_voltage > max_voltage:
        blockers.append(
            f"shouter_voltage {campaign.shouter_voltage} exceeds safety max_voltage_v {max_voltage}"
        )
    max_attempts_per_location = int(safety.get("max_attempts_per_location", 0) or 0)
    if max_attempts_per_location and sweep_points > max_attempts_per_location:
        blockers.append(
            f"sweep attempts per grid point {sweep_points} exceeds max_attempts_per_location {max_attempts_per_location}"
        )
    max_pps = float(safety.get("max_pulses_per_sec", 0) or 0)
    min_seconds = (total / max_pps) if max_pps > 0 else None
    policy_blockers, policy_warnings = _automation_policy_findings(
        campaign.automation_policy,
        campaign,
        materialized_sweep,
        total,
        min_seconds,
    )
    blockers.extend(policy_blockers)
    warnings.extend(policy_warnings)

    if total > 100_000:
        warnings.append("campaign exceeds 100000 attempts; confirm runtime and wear before launch")
    if grid_points < 4:
        warnings.append(f"grid will only produce {grid_points} point{'s' if grid_points != 1 else ''}")

    return CampaignPreflight(
        ok=not blockers,
        total_attempts=total,
        grid_points=grid_points,
        sweep_points=sweep_points,
        required_devices=required_devices,
        blockers=blockers,
        warnings=warnings,
        estimates={
            "min_runtime_seconds_at_rate_limit": min_seconds,
            "max_pulses_per_sec": max_pps or None,
        },
    )


@router.post("", response_model=CampaignStatus)
async def start(campaign: Campaign, ctx: AppContext = Depends(get_ctx)) -> CampaignStatus:
    """Start a campaign. Returns immediately with the assigned ID."""
    preflight = _preflight(campaign, ctx)
    if preflight.blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "blockers": preflight.blockers,
                "warnings": preflight.warnings,
            },
        )

    if campaign.id is None:
        campaign.id = str(uuid.uuid4())
    if campaign.created_at is None:
        campaign.created_at = datetime.now(timezone.utc)

    materialized_sweep, _ = materialize_target_delay_sweep(
        campaign.project_id, campaign.build_sha, campaign.target_pc, campaign.sweep
    )
    total = _count_grid_points(campaign.grid) * _count_sweep_points(materialized_sweep)

    status = CampaignStatus(
        campaign_id=campaign.id,
        active=True,
        completed_attempts=0,
        total_attempts=total,
        started_at=datetime.now(timezone.utc),
    )
    ctx.campaigns[campaign.id] = status

    async def _run() -> None:
        try:
            await ctx.orchestrator.run_campaign(campaign, status)
        except Exception:
            LOGGER.exception("Campaign %s failed", campaign.id)
        finally:
            status.active = False
            status.finished_at = datetime.now(timezone.utc)

    asyncio.create_task(_run())
    LOGGER.info("Campaign %s started (%d total attempts)", campaign.id, total)
    return status


@router.post("/preflight", response_model=CampaignPreflight)
async def preflight(campaign: Campaign, ctx: AppContext = Depends(get_ctx)) -> CampaignPreflight:
    """Validate campaign readiness and estimate budget without touching hardware."""
    return _preflight(campaign, ctx)


@router.get("", response_model=List[CampaignStatus])
async def list_all(ctx: AppContext = Depends(get_ctx)) -> List[CampaignStatus]:
    return list(ctx.campaigns.values())


@router.get("/{campaign_id}/metadata", response_model=CampaignMetadata)
async def get_metadata(
    campaign_id: str,
    ctx: AppContext = Depends(get_ctx),
) -> CampaignMetadata:
    return ctx.campaign_metadata.get(campaign_id)


@router.put("/{campaign_id}/metadata", response_model=CampaignMetadata)
async def update_metadata(
    campaign_id: str,
    patch: CampaignMetadataUpdate,
    ctx: AppContext = Depends(get_ctx),
) -> CampaignMetadata:
    return ctx.campaign_metadata.update(campaign_id, patch)


@router.get("/{campaign_id}", response_model=CampaignStatus)
async def get_one(campaign_id: str, ctx: AppContext = Depends(get_ctx)) -> CampaignStatus:
    if campaign_id not in ctx.campaigns:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
    return ctx.campaigns[campaign_id]


@router.post("/{campaign_id}/stop")
async def stop(campaign_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    if campaign_id not in ctx.campaigns:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
    ctx.stop_flag.set()
    LOGGER.info("Campaign %s stop requested", campaign_id)
    return {"ok": True, "campaign_id": campaign_id}
