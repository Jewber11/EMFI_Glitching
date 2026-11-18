"""Campaign-preset CRUD — saved configurations stored per project.

Each preset lives at ``~/emfi-projects/{id}/presets/{preset_id}.json`` and
is version-tracked in the project's git repo so it travels with the
firmware.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from pydantic import ValidationError

from emfi_protocol.campaigns import Campaign
from emfi_protocol.projects import CampaignPreset

from develop import git_ops
from develop.projects import project_dir

log = logging.getLogger(__name__)


class PresetNotFoundError(Exception):
    pass


class PresetValidationError(Exception):
    pass


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "preset"


def _unique_preset_id(presets_dir_path: Path, base: str) -> str:
    slug = _slugify(base)
    if not (presets_dir_path / f"{slug}.json").exists():
        return slug
    n = 2
    while (presets_dir_path / f"{slug}_{n}.json").exists():
        n += 1
    return f"{slug}_{n}"


def presets_dir(project_id: str) -> Path:
    return project_dir(project_id) / "presets"


def list_presets(project_id: str) -> List[CampaignPreset]:
    log.debug("Listing presets for project=%s", project_id)
    d = presets_dir(project_id)
    if not d.exists():
        return []
    result: List[CampaignPreset] = []
    for f in sorted(d.glob("*.json")):
        try:
            result.append(CampaignPreset(**json.loads(f.read_text())))
        except Exception as e:
            log.warning("Skipping invalid preset %s: %s", f.name, e)
    return result


def get_preset(project_id: str, preset_id: str) -> CampaignPreset:
    log.debug("Loading preset project=%s preset=%s", project_id, preset_id)
    p = presets_dir(project_id) / f"{preset_id}.json"
    if not p.exists():
        raise PresetNotFoundError(f"Preset {preset_id!r} not found")
    return CampaignPreset(**json.loads(p.read_text()))


def create_preset(
    project_id: str, name: str, config: dict, description: str = ""
) -> CampaignPreset:
    """Validate `config` against Campaign, then persist + git commit."""
    log.info("Creating preset project=%s name=%s", project_id, name)
    try:
        Campaign(**config)
    except ValidationError as e:
        raise PresetValidationError(str(e))

    d = presets_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    preset_id = _unique_preset_id(d, name)

    preset = CampaignPreset(
        id=preset_id,
        name=name,
        description=description or None,
        created_at=datetime.now(timezone.utc),
        config=config,
    )
    (d / f"{preset_id}.json").write_text(preset.model_dump_json(indent=2) + "\n")

    git_ops.commit(project_dir(project_id), f"Add campaign preset {name!r}")
    return preset


def delete_preset(project_id: str, preset_id: str) -> None:
    log.warning("Deleting preset project=%s preset=%s", project_id, preset_id)
    p = presets_dir(project_id) / f"{preset_id}.json"
    if not p.exists():
        raise PresetNotFoundError(f"Preset {preset_id!r} not found")
    p.unlink()
    git_ops.commit(project_dir(project_id), f"Delete campaign preset {preset_id!r}")
