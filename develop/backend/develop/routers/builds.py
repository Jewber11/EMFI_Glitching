"""Build endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from emfi_protocol.projects import BuildArtifact

from develop import builds as bld
from develop.projects import ProjectNotFoundError

log = logging.getLogger(__name__)

router = APIRouter(tags=["builds"])


class BuildRequest(BaseModel):
    version: Optional[str] = None


@router.post("/projects/{project_id}/build", response_model=BuildArtifact)
async def trigger(
    project_id: str,
    req: BuildRequest = BuildRequest(),
    force: bool = Query(False, description="Skip cache and rebuild"),
) -> BuildArtifact:
    """Kick a build. Streams logs via WS topic `build_log`."""
    log.info("POST /projects/%s/build version=%s force=%s", project_id, req.version, force)
    try:
        return await bld.build(project_id, req.version, force=force)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except bld.ToolchainNotFoundError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


@router.get("/projects/{project_id}/builds", response_model=List[BuildArtifact])
async def list_builds(project_id: str) -> List[BuildArtifact]:
    log.debug("GET /projects/%s/builds", project_id)
    return bld.list_build_artifacts(project_id)


@router.get("/projects/{project_id}/builds/{sha}", response_model=BuildArtifact)
async def get_build(project_id: str, sha: str) -> BuildArtifact:
    log.debug("GET /projects/%s/builds/%s", project_id, sha)
    artifact = bld.get_build_artifact(project_id, sha)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Build {sha!r} not found")
    return artifact
