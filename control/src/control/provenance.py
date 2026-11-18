"""Durable Control-side provenance records."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from emfi_protocol.projects import FlashedFirmware

LOGGER = logging.getLogger(__name__)


def default_state_dir() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "share"))
    return state / "emfi-control"


def default_flashed_firmware_path() -> Path:
    return default_state_dir() / "flashed_firmware.json"


def load_flashed_firmware(path: Path | None = None) -> FlashedFirmware | None:
    record_path = path or default_flashed_firmware_path()
    if not record_path.exists():
        return None
    try:
        return FlashedFirmware.model_validate_json(record_path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.exception("Could not load flashed firmware provenance from %s", record_path)
        return None


def save_flashed_firmware(record: FlashedFirmware, path: Path | None = None) -> Path:
    record_path = path or default_flashed_firmware_path()
    record_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = record_path.with_suffix(record_path.suffix + ".tmp")
    tmp_path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(record_path)
    return record_path
