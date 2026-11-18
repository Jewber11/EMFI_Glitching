"""Claude Code CLI subprocess wrapper.

Spawns `claude` in the project's working directory with the user's prompt.
Streams stdout/stderr line-by-line so the frontend can render the agent's
output live via the WebSocket topic `agent_output`.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import AsyncIterator

from emfi_protocol.ws_events import WsTopic

from develop.broadcaster import broadcaster
from develop.config import claude_bin
from develop.projects import project_dir

log = logging.getLogger(__name__)


class AgentError(Exception):
    pass


async def run_agent(project_id: str, prompt: str) -> AsyncIterator[str]:
    """Yield agent output lines (mixed stdout + stderr) as they arrive."""
    log.info("Launching agent for project=%s prompt=%s", project_id, prompt[:120])

    binary = claude_bin()
    if not shutil.which(binary):
        msg = (
            f"Claude Code CLI ({binary!r}) not found on PATH. "
            "Install: npm i -g @anthropic-ai/claude-code"
        )
        await broadcaster.broadcast(WsTopic.AGENT_OUTPUT, {
            "project_id": project_id, "line": f"ERROR: {msg}", "done": True,
        })
        raise AgentError(msg)

    cwd = str(project_dir(project_id))

    proc = await asyncio.create_subprocess_exec(
        binary, "--print", prompt,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        await broadcaster.broadcast(WsTopic.AGENT_OUTPUT, {
            "project_id": project_id, "line": line,
        })
        yield line

    await proc.wait()
    exit_line = f"[Agent exited with code {proc.returncode}]"
    await broadcaster.broadcast(WsTopic.AGENT_OUTPUT, {
        "project_id": project_id, "line": exit_line, "done": True,
    })
    log.info("Agent finished for project=%s exit=%d", project_id, proc.returncode)
    yield exit_line
