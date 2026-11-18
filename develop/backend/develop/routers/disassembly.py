"""Disassembly endpoint — returns AssemblyListing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from emfi_protocol.projects import AssemblyListing

from develop.disassemble import DisassemblyError, disassemble_cached
from develop.projects import project_dir

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/builds/{sha}", tags=["disassembly"]
)


@router.get("/disassembly", response_model=AssemblyListing)
async def disassembly(project_id: str, sha: str) -> AssemblyListing:
    """Parsed `arm-none-eabi-objdump -d` output. View renders this in Monaco."""
    log.info("GET disassembly project=%s sha=%s", project_id, sha)
    build_dir = project_dir(project_id) / "builds" / sha
    if not build_dir.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Build {sha!r} not found")
    try:
        return disassemble_cached(build_dir, project_id, sha)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except DisassemblyError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
