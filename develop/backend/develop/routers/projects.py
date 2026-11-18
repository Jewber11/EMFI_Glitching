"""Project CRUD endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from emfi_protocol.projects import Project

from develop import projects as proj

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    template: str
    language: str
    hal: str
    description: Optional[str] = None


class ImportProjectRequest(BaseModel):
    name: str
    source_path: str
    language: str
    hal: str
    description: Optional[str] = None
    exclude: Optional[List[str]] = None


class PutFileRequest(BaseModel):
    contents: str


@router.get("", response_model=List[Project])
async def list_all() -> List[Project]:
    log.debug("GET /projects")
    return proj.list_projects()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create(req: CreateProjectRequest) -> Project:
    log.info("POST /projects name=%s template=%s", req.name, req.template)
    try:
        return proj.create_project(
            req.name, req.template, req.language, req.hal, req.description or ""
        )
    except proj.ProjectExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/import", response_model=Project, status_code=status.HTTP_201_CREATED)
async def import_project(req: ImportProjectRequest) -> Project:
    log.info("POST /projects/import name=%s source=%s", req.name, req.source_path)
    try:
        return proj.import_project(
            req.name, req.source_path, req.language, req.hal,
            req.description or "", req.exclude,
        )
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except proj.ProjectExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/{project_id}", response_model=Project)
async def get_one(project_id: str) -> Project:
    log.debug("GET /projects/%s", project_id)
    try:
        return proj.get_project(project_id)
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id!r} not found")


@router.delete("/{project_id}")
async def delete(project_id: str) -> dict:
    log.warning("DELETE /projects/%s", project_id)
    try:
        proj.delete_project(project_id)
        return {"ok": True}
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id!r} not found")


@router.get("/{project_id}/tree")
async def tree(project_id: str) -> dict:
    log.debug("GET /projects/%s/tree", project_id)
    try:
        return proj.file_tree(project_id)
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id!r} not found")


@router.get("/{project_id}/file")
async def get_file(project_id: str, path: str) -> dict:
    log.debug("GET /projects/%s/file path=%s", project_id, path)
    try:
        contents = proj.read_file(project_id, path)
        return {"path": path, "contents": contents}
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"File {path!r} not found")
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Path traversal denied")


@router.put("/{project_id}/file")
async def put_file(project_id: str, path: str, body: PutFileRequest) -> dict:
    log.info("PUT /projects/%s/file path=%s", project_id, path)
    try:
        proj.write_file(project_id, path, body.contents)
        return {"ok": True, "path": path}
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Path traversal denied")
