"""Git operation endpoints — commit, tag, log."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from develop import git_ops
from develop.projects import project_dir, ProjectNotFoundError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/git", tags=["git"])


class CommitRequest(BaseModel):
    message: str


class TagRequest(BaseModel):
    name: str


def _resolve(project_id: str):
    p = project_dir(project_id)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id!r} not found")
    return p


@router.post("/commit")
async def commit(project_id: str, req: CommitRequest) -> dict:
    """Stage all changes and create a git commit."""
    log.info("git commit project=%s msg=%s", project_id, req.message[:80])
    repo = _resolve(project_id)
    try:
        sha = git_ops.commit(repo, req.message)
        return {"sha": sha}
    except git_ops.GitError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.post("/tag")
async def tag(project_id: str, req: TagRequest) -> dict:
    """Create a git tag (lightweight)."""
    log.info("git tag project=%s name=%s", project_id, req.name)
    repo = _resolve(project_id)
    try:
        git_ops.tag(repo, req.name)
        return {"ok": True, "name": req.name}
    except git_ops.GitError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/log")
async def log_entries(project_id: str, limit: int = 50) -> List[dict]:
    """Return recent git log entries."""
    log.debug("git log project=%s limit=%d", project_id, limit)
    repo = _resolve(project_id)
    try:
        return git_ops.log_entries(repo, limit)
    except git_ops.GitError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
