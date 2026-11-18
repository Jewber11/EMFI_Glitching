"""GlitchTarget CRUD — annotations stored in `targets.json` per project."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from emfi_protocol.projects import GlitchTarget

from develop import git_ops
from develop.projects import project_dir

log = logging.getLogger(__name__)


class TargetExistsError(Exception):
    pass


class TargetNotFoundError(Exception):
    pass


def targets_file(project_id: str) -> Path:
    return project_dir(project_id) / "targets.json"


def _read_raw(project_id: str) -> list[dict]:
    tf = targets_file(project_id)
    if not tf.exists():
        return []
    return json.loads(tf.read_text())


def _write_raw(project_id: str, data: list[dict]) -> None:
    tf = targets_file(project_id)
    tf.write_text(json.dumps(data, indent=2, default=str) + "\n")


def list_targets(project_id: str) -> List[GlitchTarget]:
    log.debug("Listing targets for project=%s", project_id)
    raw = _read_raw(project_id)
    return [GlitchTarget(**t) for t in raw]


def add_target(project_id: str, target: GlitchTarget) -> GlitchTarget:
    """Append target to targets.json and commit the change."""
    log.info("Adding target pc=0x%x to project=%s", target.pc_address, project_id)
    raw = _read_raw(project_id)

    for existing in raw:
        if existing.get("pc_address") == target.pc_address:
            raise TargetExistsError(
                f"Target at 0x{target.pc_address:x} already exists"
            )

    raw.append(json.loads(target.model_dump_json()))
    _write_raw(project_id, raw)

    repo = project_dir(project_id)
    git_ops.commit(repo, f"Add target {target.name} at 0x{target.pc_address:x}")
    return target


def remove_target(project_id: str, pc_address: int) -> None:
    log.info("Removing target pc=0x%x from project=%s", pc_address, project_id)
    raw = _read_raw(project_id)
    filtered = [t for t in raw if t.get("pc_address") != pc_address]

    if len(filtered) == len(raw):
        raise TargetNotFoundError(f"No target at 0x{pc_address:x}")

    _write_raw(project_id, filtered)

    repo = project_dir(project_id)
    git_ops.commit(repo, f"Remove target at 0x{pc_address:x}")
