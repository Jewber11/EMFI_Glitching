"""Read-only configuration endpoint.

Exposes the persisted config sections View needs to display the current
rig setup (axis orientation, port pins, safety limits). Editing is done
by hand in ~/.config/emfi-control/config.json for now — there is no POST.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from control.deps import AppContext, get_ctx

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config(ctx: AppContext = Depends(get_ctx)) -> Dict[str, Any]:
    """Return the axes / ports / safety config sections (read-only)."""
    return {
        "axes": ctx.config.get("axes", default={}),
        "ports": ctx.config.get("ports", default={}),
        "safety": ctx.config.get("safety", default={}),
        "fixture": ctx.config.get("fixture", default={}),
    }
