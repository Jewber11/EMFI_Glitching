"""Logbook query endpoints + replay."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from control.deps import AppContext, get_ctx

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])

CSV_FIELDS = [
    "id",
    "ts",
    "session",
    "campaign_id",
    "project_id",
    "project_version",
    "build_sha",
    "target_pc",
    "x",
    "y",
    "z",
    "machine_x",
    "machine_y",
    "machine_z",
    "trigger_mode",
    "glitch_delay_us",
    "pulse_width_ns",
    "shouter_voltage",
    "shouter_pulse_width_ns",
    "shouter_pulse_width_ns_actual",
    "outcome",
    "shouter_state",
    "elapsed_ms",
    "verdict",
    "error",
]


@router.get("/runs")
async def list_runs(
    campaign: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(
        None,
        description="Alias for campaign; useful for heatmap drill-down clients",
    ),
    x: Optional[float] = Query(None),
    y: Optional[float] = Query(None),
    z: Optional[float] = Query(None),
    since: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=10000),
    ctx: AppContext = Depends(get_ctx),
) -> List[Dict[str, Any]]:
    """Query the logbook (backed by SQLite mirror for speed)."""
    resolved_campaign = campaign_id or campaign
    return ctx.logbook.read(
        since=since,
        limit=limit,
        campaign_id=resolved_campaign,
        x=x,
        y=y,
        z=z,
        outcome=outcome,
    )


@router.get("/runs/export")
async def export_runs(
    format: str = Query("csv", pattern="^(csv|parquet)$"),
    campaign: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
) -> Response:
    """Export attempt rows for offline analysis.

    CSV is dependency-free and available everywhere. Parquet is intentionally
    reserved until the project standardizes on a local/cloud analytics stack.
    """
    if format == "parquet":
        raise HTTPException(
            status_code=501,
            detail="parquet export is not implemented yet; use format=csv",
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for entry in ctx.logbook.iter_csv_rows(since=since, outcome=outcome):
        if campaign and entry.get("campaign_id") != campaign:
            continue
        row = dict(entry)
        for key in ("verdict",):
            if isinstance(row.get(key), (dict, list)):
                row[key] = json.dumps(row[key], separators=(",", ":"))
        writer.writerow(row)

    suffix = f"-{campaign}" if campaign else ""
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="emfi-runs{suffix}.csv"'
        },
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    entry = ctx.logbook.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return entry


@router.get("/heatmap")
async def heatmap(
    campaign: Optional[str] = Query(None),
    z: Optional[float] = Query(None),
    outcome: Optional[str] = Query(
        None, description="Filter to a single outcome; omit for all outcomes"
    ),
    ctx: AppContext = Depends(get_ctx),
) -> List[Dict[str, Any]]:
    """Fault density grouped by (x, y).

    Returns ``[{x, y, counts: {glitch, hang, crash, nothing}}]``. By default
    all outcomes are included so the heatmap is non-empty before any glitch
    lands; pass ``outcome`` to restrict to one bucket.
    """
    return ctx.logbook.heatmap(campaign_id=campaign, z=z, outcome=outcome)


@router.post("/replay/{run_id}")
async def replay(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Re-execute the exact glitch attempt identified by run_id."""
    ctx.arm_gate.require_armed()
    ctx.rate_limiter.acquire()
    try:
        result = await ctx.orchestrator.replay(run_id)
    except RuntimeError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    return result
