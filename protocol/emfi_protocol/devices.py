"""Device-status and motion-related shared models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    x: float = Field(..., description="Logical X coordinate in mm (from origin)")
    y: float = Field(..., description="Logical Y coordinate in mm")
    z: float = Field(..., description="Logical Z coordinate in mm")

    machine_x: Optional[float] = Field(None, description="Raw machine X (origin offset applied)")
    machine_y: Optional[float] = None
    machine_z: Optional[float] = None


class DeviceStatus(BaseModel):
    name: str = Field(..., description="One of: chipshover, chipshouter, scaffold, xds110")
    available: bool = Field(False, description="Adapter library importable")
    connected: bool = Field(False, description="Serial port open / handle valid")
    port: Optional[str] = Field(None, description="Serial device path, if connected")
    label: Optional[str] = Field(None, description="Human-readable identifier")
    last_error: Optional[str] = None
    busy: bool = False
    fault_names: Optional[List[str]] = Field(
        None,
        description="ChipSHOUTER: decoded names of the most recently latched "
        "faults (e.g. fault_high_voltage). None when no device faults captured.",
    )


class ArmState(BaseModel):
    armed: bool
    auto_disarm_seconds: float = Field(
        300.0,
        description="Seconds since last pulse before the gate auto-closes",
    )
    seconds_until_auto_disarm: Optional[float] = Field(
        None,
        description="Countdown to auto-disarm, or null if not armed",
    )
