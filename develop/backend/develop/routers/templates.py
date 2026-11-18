"""Template listing endpoint."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter

from develop.config import templates_root

log = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


@router.get("/templates")
async def list_templates() -> List[dict]:
    """List available project templates (c_ti_hal, rust_b01lers, etc.)."""
    log.debug("GET /templates")
    root = templates_root()
    templates = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        tmpl_file = entry / "project.toml.template"
        info = {"id": entry.name, "language": "c", "hal": "ti"}
        if tmpl_file.exists():
            for line in tmpl_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("language"):
                    info["language"] = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("hal"):
                    info["hal"] = line.split("=", 1)[1].strip().strip('"')
        templates.append(info)
    return templates
