"""Durable notes and tags for campaigns."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emfi_protocol.campaigns import CampaignMetadata, CampaignMetadataUpdate


def default_campaign_metadata_path() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "share"))
    return state / "emfi-control" / "campaign_metadata.json"


def _normalize_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


class CampaignMetadataStore:
    """Thread-safe JSON store keyed by campaign id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_campaign_metadata_path()
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._data = {}
                return
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                loaded = {}
            if not isinstance(loaded, dict):
                loaded = {}
            self._data = {
                str(campaign_id): dict(value)
                for campaign_id, value in loaded.items()
                if isinstance(value, dict)
            }

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, campaign_id: str) -> CampaignMetadata:
        with self._lock:
            raw = self._data.get(campaign_id, {})
            return CampaignMetadata(
                campaign_id=campaign_id,
                notes=str(raw.get("notes") or ""),
                tags=_normalize_tags(list(raw.get("tags") or [])),
                updated_at=raw.get("updated_at"),
            )

    def update(self, campaign_id: str, patch: CampaignMetadataUpdate) -> CampaignMetadata:
        with self._lock:
            raw = dict(self._data.get(campaign_id, {}))
            if patch.notes is not None:
                raw["notes"] = patch.notes
            if patch.tags is not None:
                raw["tags"] = _normalize_tags(patch.tags)
            raw["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self._data[campaign_id] = raw
            self._save_locked()
            return self.get(campaign_id)
