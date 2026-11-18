"""Artifact download — Control pulls the .elf from these endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from develop.projects import project_dir

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/builds/{sha}", tags=["artifacts"])


def _artifact_path(project_id: str, sha: str, filename: str):
    path = project_dir(project_id) / "builds" / sha / filename
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{filename} not found for build {sha!r}",
        )
    return path


@router.get("/firmware.elf")
async def firmware_elf(project_id: str, sha: str) -> FileResponse:
    log.info("Download firmware.elf project=%s sha=%s", project_id, sha)
    return FileResponse(_artifact_path(project_id, sha, "firmware.elf"),
                        media_type="application/octet-stream")


@router.get("/firmware.bin")
async def firmware_bin(project_id: str, sha: str) -> FileResponse:
    log.info("Download firmware.bin project=%s sha=%s", project_id, sha)
    return FileResponse(_artifact_path(project_id, sha, "firmware.bin"),
                        media_type="application/octet-stream")


@router.get("/firmware.lst")
async def firmware_lst(project_id: str, sha: str) -> FileResponse:
    log.info("Download firmware.lst project=%s sha=%s", project_id, sha)
    return FileResponse(_artifact_path(project_id, sha, "firmware.lst"),
                        media_type="text/plain")
