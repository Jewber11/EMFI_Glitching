"""Per-attempt result models. Mirrors the JSONL logbook schema."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Outcome(str, Enum):
    """Verdict bucket for a single glitch attempt.

    Carried forward from old `orchestrator.perform_attempt` classification.
    """

    GLITCH = "glitch"
    HANG = "hang"
    CRASH = "crash"
    NOTHING = "nothing"
    UNOBSERVED = "unobserved"


class Verdict(BaseModel):
    """Raw GPIO-derived target state at end of attempt window."""

    fault: bool = Field(False, description="D2 rising edge — target self-detected fault")
    heartbeat_alive: bool = Field(False, description="D1 toggled within timeout window")
    campaign_complete: bool = Field(False, description="D3 falling edge — target campaign ended")
    outcome: Optional[str] = None
    response: Optional[str] = None


class AttemptResult(BaseModel):
    """One row in the JSONL logbook."""

    id: str = Field(..., description="UUID per attempt")
    ts: str = Field(..., description="ISO-8601 timestamp with millisecond precision")
    session: str = Field(..., description="Session ID (e.g. 20260521T184213)")
    campaign_id: Optional[str] = None

    # Position
    x: float
    y: float
    z: float
    machine_x: Optional[float] = None
    machine_y: Optional[float] = None
    machine_z: Optional[float] = None

    # Pulse parameters
    trigger_mode: str = Field(..., description="software | one-shot | free-run | disabled")
    glitch_delay_us: Optional[float] = None
    pulse_width_ns: Optional[float] = None
    shouter_voltage: Optional[int] = None
    shouter_pulse_width_ns: Optional[int] = None
    shouter_pulse_width_ns_actual: Optional[int] = Field(
        None,
        description="HV pulse width the ChipSHOUTER acknowledged (read-back); "
        "may differ from the commanded shouter_pulse_width_ns due to device "
        "quantization. None when not on a hardware-trigger campaign.",
    )

    # Outcome
    outcome: Outcome
    verdict: Verdict
    shouter_state: Optional[str] = None
    elapsed_ms: int = 0

    # Optional firmware reference
    project_id: Optional[str] = None
    project_version: Optional[str] = None
    build_sha: Optional[str] = None
    target_pc: Optional[int] = Field(None, description="Targeted instruction PC, if any")
