"""Host-side experiment script endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from develop import git_ops
from develop.projects import (
    ProjectNotFoundError, default_host_script, get_project,
    project_dir, read_file, write_file,
)

log = logging.getLogger(__name__)

HOST_SCRIPT_REL = "host/run.py"

router = APIRouter(tags=["host_script"])


class HostScriptBody(BaseModel):
    contents: str


@router.get("/projects/{project_id}/host_script")
async def get_host_script(project_id: str) -> dict:
    log.debug("GET /projects/%s/host_script", project_id)
    try:
        contents = read_file(project_id, HOST_SCRIPT_REL)
        return {"path": HOST_SCRIPT_REL, "contents": contents}
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "host/run.py not found in project")


@router.put("/projects/{project_id}/host_script")
async def put_host_script(project_id: str, body: HostScriptBody) -> dict:
    log.info("PUT /projects/%s/host_script", project_id)
    p = project_dir(project_id)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    write_file(project_id, HOST_SCRIPT_REL, body.contents)
    git_ops.commit(p, "Update host/run.py")
    return {"ok": True, "path": HOST_SCRIPT_REL}


@router.post("/projects/{project_id}/host_script/reset")
async def reset_host_script(project_id: str) -> dict:
    """Overwrite host/run.py with the current canonical template.

    Useful after the template ships breaking changes (e.g. new
    ScaffoldAdapter API) and existing projects need to recover.
    """
    log.warning("RESET host_script project=%s", project_id)
    p = project_dir(project_id)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    try:
        proj = get_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    write_file(project_id, HOST_SCRIPT_REL, default_host_script(proj.language.value))
    git_ops.commit(p, "Reset host/run.py to canonical template")
    return {"ok": True, "path": HOST_SCRIPT_REL}


@router.get("/projects/{project_id}/builds/{sha}/host_script")
async def get_build_host_script(project_id: str, sha: str) -> FileResponse:
    log.info("GET /projects/%s/builds/%s/host_script", project_id, sha)
    path = project_dir(project_id) / "builds" / sha / "host_script.py"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "host_script.py not in this build")
    return FileResponse(path, media_type="text/x-python")
