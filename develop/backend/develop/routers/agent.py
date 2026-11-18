"""Claude Code CLI agent endpoint."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from develop import agent as agt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/agent", tags=["agent"])


class AgentRequest(BaseModel):
    prompt: str
    model: str = "opus"


@router.post("")
async def run_agent(project_id: str, req: AgentRequest) -> dict:
    """Spawn `claude` in the project directory.

    Returns immediately with a job ID; stream output via WS topic `agent_output`.
    """
    log.info("POST agent project=%s model=%s prompt=%s", project_id, req.model, req.prompt[:120])
    job_id = uuid.uuid4().hex[:8]

    async def _run() -> None:
        try:
            async for _line in agt.run_agent(project_id, req.prompt):
                pass
        except agt.AgentError:
            pass
        except Exception:
            log.exception("Agent task failed for project=%s", project_id)

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "started"}
