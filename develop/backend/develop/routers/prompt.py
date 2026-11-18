"""Generate a copy-pastable Claude Code session prompt for a project."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from develop import projects as proj
from develop.config import control_url, projects_root

log = logging.getLogger(__name__)

router = APIRouter(tags=["prompt"])


def _develop_url() -> str:
    import os
    return os.environ.get("DEVELOP_URL", "http://localhost:8002")


def _build_prompt(p: proj.Project) -> str:
    dev = _develop_url()
    ctrl = control_url()
    pid = p.id
    tree_path = f"{projects_root()}/{pid}"
    latest = p.versions[0] if p.versions else "(none)"

    return f"""\
# EMFI Develop — Project Session: {p.name}

You are working on the firmware project **{p.name}** (`{pid}`) in the EMFI
research platform. This project targets the **{p.target}** MCU using the
**{p.hal}** HAL, written in **{p.language}**.

## Project metadata

| Field | Value |
|---|---|
| Project ID | `{pid}` |
| Name | {p.name} |
| Language | {p.language} |
| Target | {p.target} |
| HAL | {p.hal} |
| Latest version | {latest} |
| Description | {p.description or '(none)'} |
| Working tree | `{tree_path}/` |

## Develop service — {dev}

Use these endpoints to read/write files, build, and manage targets:

```
GET    {dev}/projects/{pid}/tree                          file tree
GET    {dev}/projects/{pid}/file?path=<relative>          read file
PUT    {dev}/projects/{pid}/file?path=<relative>          write file (body: {{"contents":"..."}})

POST   {dev}/projects/{pid}/build                         kick build (body: {{"version":null}})
GET    {dev}/projects/{pid}/builds/{{sha}}/disassembly     parsed assembly listing

GET    {dev}/projects/{pid}/targets                       list GlitchTargets
POST   {dev}/projects/{pid}/targets                       add target (body: GlitchTarget)
DELETE {dev}/projects/{pid}/targets/{{pc}}                 remove target

GET    {dev}/projects/{pid}/host_script                   host-side experiment driver
PUT    {dev}/projects/{pid}/host_script                   update host script (body: {{"contents":"..."}})

POST   {dev}/projects/{pid}/agent                         invoke Claude (body: {{"prompt":"..."}})
```

## Control service — {ctrl}

For flashing and running campaigns:

```
POST   {ctrl}/target/flash         flash firmware (body: {{"build_sha":"...", "elf_url":"{dev}/projects/{pid}/builds/{{sha}}/firmware.elf"}})
POST   {ctrl}/campaigns            start a campaign (body: Campaign model)
GET    {ctrl}/runs?campaign=...    query attempt results
```

## GlitchTarget model

To annotate a target instruction for glitching:

```json
{{
  "pc_address": 4096,
  "name": "branch_after_check",
  "expected_delay_cycles": 150,
  "notes": "Single-instruction branch; delay from D0 rising edge",
  "created_at": "2026-01-01T00:00:00Z"
}}
```

POST this to `{dev}/projects/{pid}/targets`. The `pc_address` is the
program counter from the disassembly listing. `expected_delay_cycles` is
optional — cycles from the trigger rising edge to this instruction.

## Host-side experiment script

Every project has a `host/run.py` that Control imports when running a
campaign against this project's firmware. It must implement three hooks:

```python
def setup(ctx) -> None:
    \"\"\"Called once before the campaign starts. Configure DUT
    power, trigger mode, etc.\"\"\"

def attempt(ctx) -> dict:
    \"\"\"Called once per glitch attempt. Returns
        {{"fault": bool, "heartbeat_alive": bool,
         "campaign_complete": bool}}
    Reuses the Verdict shape from emfi_protocol.runs.\"\"\"

def teardown(ctx) -> None:
    \"\"\"Called once after the campaign ends. Power-down DUT,
    restore safe state.\"\"\"
```

`ctx` exposes: `ctx.scaffold` (ScaffoldAdapter), `ctx.shouter`
(ChipShouterAdapter), `ctx.params` (SweepParams), `ctx.logbook`
(Logbook), `ctx.state` (AppState).

Edit the host script at: `{dev}/projects/{pid}/host_script`

## Reference docs

- `develop/setup.md` — lab box setup, toolchains, run instructions
- `agentConversation.md` — cross-app coordination channel
- `develop/SPEC.md` — full API contract

## Working directory

Your working tree is `{tree_path}/`. Source files are under `src/`,
build artifacts under `builds/<sha>/`, and glitch targets in
`targets.json`. The project is a git repo; versions are git tags.
"""


@router.get("/projects/{project_id}/prompt")
async def get_prompt(project_id: str) -> dict:
    """Return a generated Claude Code session prompt for this project."""
    log.info("GET /projects/%s/prompt", project_id)
    try:
        p = proj.get_project(project_id)
    except proj.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id!r} not found")
    return {"prompt": _build_prompt(p)}
