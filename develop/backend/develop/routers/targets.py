"""GlitchTarget endpoints."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from emfi_protocol.projects import GlitchTarget

from develop import targets as tgt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/targets", tags=["targets"])


@router.get("", response_model=List[GlitchTarget])
async def list_targets(project_id: str) -> List[GlitchTarget]:
    log.debug("GET targets project=%s", project_id)
    return tgt.list_targets(project_id)


@router.post("", response_model=GlitchTarget, status_code=status.HTTP_201_CREATED)
async def add_target(project_id: str, target: GlitchTarget) -> GlitchTarget:
    """Append to targets.json and git commit."""
    log.info("POST target project=%s pc=0x%x", project_id, target.pc_address)
    try:
        return tgt.add_target(project_id, target)
    except tgt.TargetExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.delete("/{pc_address}")
async def remove(project_id: str, pc_address: int) -> dict:
    log.warning("DELETE target project=%s pc=0x%x", project_id, pc_address)
    try:
        tgt.remove_target(project_id, pc_address)
        return {"ok": True}
    except tgt.TargetNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
