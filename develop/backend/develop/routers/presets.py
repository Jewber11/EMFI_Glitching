"""Campaign-preset endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from emfi_protocol.projects import CampaignPreset

from develop import presets as ps

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/presets", tags=["presets"])


class CreatePresetRequest(BaseModel):
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]


@router.get("", response_model=List[CampaignPreset])
async def list_all(project_id: str) -> List[CampaignPreset]:
    log.debug("GET presets project=%s", project_id)
    return ps.list_presets(project_id)


@router.get("/{preset_id}", response_model=CampaignPreset)
async def get_one(project_id: str, preset_id: str) -> CampaignPreset:
    log.debug("GET preset project=%s preset=%s", project_id, preset_id)
    try:
        return ps.get_preset(project_id, preset_id)
    except ps.PresetNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.post("", response_model=CampaignPreset, status_code=status.HTTP_201_CREATED)
async def create(project_id: str, req: CreatePresetRequest) -> CampaignPreset:
    log.info("POST preset project=%s name=%s", project_id, req.name)
    try:
        return ps.create_preset(
            project_id, req.name, req.config, req.description or ""
        )
    except ps.PresetValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.delete("/{preset_id}")
async def remove(project_id: str, preset_id: str) -> dict:
    log.warning("DELETE preset project=%s preset=%s", project_id, preset_id)
    try:
        ps.delete_preset(project_id, preset_id)
        return {"ok": True}
    except ps.PresetNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
