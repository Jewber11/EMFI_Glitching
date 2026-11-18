"""Persistent JSON config for Control.

Path: ~/.config/emfi-control/config.json (auto-created on first run).
Mirrors the shape of old-em-setup/glitchweb/backend/app/config.py:
thread-safe Config class with load/save/snapshot/update/get + hot reload.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

LOGGER = logging.getLogger(__name__)


DEFAULTS: Dict[str, Any] = {
    "host": {"bind": "0.0.0.0", "port": 8001},
    "develop_url": "http://localhost:8002",
    "axes": {
        "invert_x": False,
        "invert_y": False,
        "invert_z": False,
        "swap_xy": False,
    },
    "safety": {
        "arm_hold_ms": 1000,
        "auto_disarm_minutes": 5,
        "max_voltage_v": 350,
        "max_pulses_per_sec": 10,
        "max_attempts_per_location": 1000,
    },
    "defaults": {
        "trigger_mode": "software",
        "pulse_delay_us": 1.0,
        "pulse_width_ns": 200.0,
        "pulse_polarity_negative": False,
        "verdict_timeout_ms": 500,
        "shouter_voltage": 250,
        "shouter_pulse_width_ns": 1000,
        "shouter_pulse_repeat": 1,
        "shouter_pulse_deadtime_ms": 10,
        "shouter_arm_timeout_min": 1,
        "shouter_mute": True,
        "shouter_auto_arm": True,
        "step_size_mm": 1.0,
        "z_increment_mm": 0.1,
        "max_z_height_mm": 0.5,
        "attempts_per_location": 1,
    },
    "fixture": {
        "default_grid": None,
    },
    "known_devices": {
        "chipshover": [
            {"manufacturer_contains": "Creality"},
            {"vid": 0x1a86, "pid": 0x7523},
            {"vid": 0x1a86, "pid": 0x55d4},
            {"vid": 0x0483, "pid": 0x5740},
            {"manufacturer_contains": "marlinfw"},
            {"description_contains": "3D Printer"},
        ],
        "chipshouter": [
            {"vid": 0x1209, "pid": 0xFA17},
            {"serial_prefix": "CW521"},
        ],
        "scaffold": [{"manufacturer": "FTDI", "serial_prefix": "scaffold"}],
        "xds110": [{"description_contains": "XDS110"}],
    },
    "ports": {
        "chipshover_override": None,
        "chipshouter_override": None,
        "scaffold_override": None,
        "xds110_override": None,
    },
    "programmer": {
        "backend": "auto",
        "probe_rs_bin": None,
        "probe": None,
        "power_cycle": None,
        "ectf_bin": "ectf",
        "ectf_port": None,
        "dslite_bin": None,
        "dslite_ccxml": None,
        "openocd_bin": None,
        "openocd_config": None,
    },
}


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "emfi-control" / "config.json"


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    """Thread-safe access to the persistent config with hot reload."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        """(Re-)read config from disk, merging over defaults (hot reload)."""
        with self._lock:
            if self.path.exists():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    LOGGER.warning("Failed to parse config at %s, using defaults", self.path)
                    loaded = {}
                self._data = _deep_merge(deepcopy(DEFAULTS), loaded)
                LOGGER.info("Config loaded from %s", self.path)
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._data = deepcopy(DEFAULTS)
                self.save()
                LOGGER.info("Config created at %s with defaults", self.path)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
            tmp.replace(self.path)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def update(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._data = _deep_merge(self._data, partial)
            self.save()
            return deepcopy(self._data)

    def get(self, *path: str, default: Any = None) -> Any:
        with self._lock:
            cur: Any = self._data
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    return default
                cur = cur[k]
            return deepcopy(cur)
