"""Campaign / sweep / grid configuration models."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class GridParams(BaseModel):
    """3D rectangular scan grid in logical (origin-relative) coordinates."""

    origin: Tuple[float, float] = Field(..., description="First XY corner in mm")
    top_right: Tuple[float, float] = Field(..., description="Opposite XY corner in mm")
    step_size_mm: float = Field(1.0, gt=0)
    z_min_mm: float = 0.0
    z_max_mm: float = 0.5
    z_step_mm: float = Field(0.1, gt=0)


class SweepRange(BaseModel):
    """Inclusive numerical sweep with explicit step.

    Set start == stop to pin a single value. Use null to skip this dimension.
    """

    start: float
    stop: float
    step: float = Field(..., gt=0)


class SweepParams(BaseModel):
    """Parameters varied across attempts at each grid point."""

    delay_us: Optional[SweepRange] = None
    pulse_width_ns: Optional[SweepRange] = None
    voltage_v: Optional[SweepRange] = None
    attempts_per_point: int = Field(1, ge=1)


class StopConditions(BaseModel):
    """Optional policies that stop an otherwise valid campaign early."""

    max_glitches: Optional[int] = Field(
        None,
        ge=1,
        description="Stop the campaign after this many glitch outcomes",
    )
    stop_on_first_crash: bool = Field(
        False,
        description="Stop the campaign after the first crash outcome",
    )
    max_runtime_seconds: Optional[float] = Field(
        None,
        gt=0,
        description="Stop the campaign once wall-clock runtime reaches this many seconds",
    )


class AutomationBudgetPolicy(BaseModel):
    """Optional hard caps checked before automated campaign launch."""

    max_attempts: Optional[int] = Field(
        None,
        ge=1,
        description="Block campaign preflight when total attempts exceed this cap",
    )
    max_runtime_seconds: Optional[float] = Field(
        None,
        gt=0,
        description="Block campaign preflight when estimated minimum runtime exceeds this cap",
    )
    max_voltage: Optional[int] = Field(
        None,
        ge=0,
        description="Block campaign preflight when configured or swept voltage exceeds this cap",
    )
    allowed_trigger_modes: Optional[List[str]] = Field(
        None,
        description="Allowed trigger modes for this automation request",
    )


class CampaignMetadata(BaseModel):
    """Operator annotations attached to a campaign id."""

    campaign_id: str
    notes: str = ""
    tags: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class CampaignMetadataUpdate(BaseModel):
    """Partial update for campaign annotations."""

    notes: Optional[str] = None
    tags: Optional[List[str]] = None


CampaignMode = Literal["single_target", "dual_target"]
SlotName = Literal["dut", "platform"]
TimingEdge = Literal["rising", "falling", "both"]
TimelineActionKind = Literal[
    "wait_for_trigger",
    "emfi_pulse",
    "crowbar_pulse",
    "power_cycle",
    "reset",
]


class SlotConfig(BaseModel):
    """Firmware and hardware mapping for one ledger-board target slot."""

    project_id: str = Field(..., min_length=1)
    build_sha: str = Field(..., min_length=1)
    power_rail: str = Field(..., description="Example: scaffold.dut")
    programmer: str = Field(..., description="Example: xds110:dut")
    uart: Optional[str] = Field(None, description="Example: uart0")
    glitcher: Optional[str] = Field(None, description="Example: chipshouter or husky")


class TimingReference(BaseModel):
    """Signal used as the timing origin for coordinated actions."""

    source: str = Field(..., min_length=1)
    edge: TimingEdge = "rising"
    description: Optional[str] = None


class TimelineAction(BaseModel):
    """One ordered action within a dual-target campaign attempt."""

    at_us: float = Field(..., ge=0)
    target: SlotName
    device: str = Field(..., min_length=1)
    action: TimelineActionKind
    source: Optional[str] = None
    delay_sweep: Optional[str] = None
    width_sweep: Optional[str] = None
    voltage_sweep: Optional[str] = None


class CampaignTiming(BaseModel):
    """Reference signal and flat action timeline for each attempt."""

    reference: TimingReference
    timeline: List[TimelineAction] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def timeline_must_be_ordered(self) -> "CampaignTiming":
        times = [action.at_us for action in self.timeline]
        if times != sorted(times):
            raise ValueError("timing.timeline actions must be ordered by at_us")
        return self


class CampaignBudgets(BaseModel):
    """Safety and execution limits for unattended dual-target campaigns."""

    max_attempts: int = Field(..., ge=1)
    max_runtime_s: float = Field(..., gt=0)
    stop_on_first_crash: bool = False
    max_emfi_voltage_v: Optional[float] = Field(None, gt=0)
    max_crowbar_width_ns: Optional[float] = Field(None, gt=0)


class Campaign(BaseModel):
    """A user-defined glitch campaign."""

    id: Optional[str] = None
    name: str
    created_at: Optional[datetime] = None
    mode: CampaignMode = "single_target"

    # Firmware reference (resolved by Control via Develop)
    project_id: str
    project_version: Optional[str] = Field(None, description="Git tag or None for current HEAD")
    build_sha: Optional[str] = Field(None, description="Pinned build hash; None = build at start")
    target_pc: Optional[int] = Field(None, description="Annotated target instruction (optional)")

    grid: GridParams
    sweep: SweepParams

    # Shouter config
    trigger_mode: str = Field("software", description="software | one-shot | free-run | disabled")
    shouter_voltage: int = 250
    shouter_pulse_width_ns: int = 1000
    shouter_mute: bool = True
    shouter_auto_arm: bool = True

    verdict_timeout_ms: int = Field(500, ge=1, le=60000)
    target_serial_port: Optional[str] = None
    target_serial_baud: int = Field(115200, ge=300, le=4000000)
    target_normal_text: str = "normal"
    target_glitch_text: str = "ESCAPED"

    # Dual-target campaign extensions. These remain optional for existing
    # single-target callers and become mandatory only when mode=dual_target.
    slots: Optional[Dict[SlotName, SlotConfig]] = None
    timing: Optional[CampaignTiming] = None
    sweeps: Optional[Dict[str, SweepRange]] = None
    budgets: Optional[CampaignBudgets] = None

    # Optional unattended-run stop policies. Defaults preserve historical
    # behavior: run the full grid/sweep unless a manual stop is requested.
    stop_conditions: Optional[StopConditions] = Field(
        None,
        description="Grouped stop policy fields used by View and automation clients",
    )
    automation_policy: Optional[AutomationBudgetPolicy] = Field(
        None,
        description="Grouped hard budget caps checked by Control preflight",
    )
    max_glitches: Optional[int] = Field(
        None,
        ge=1,
        description="Legacy top-level alias for stop_conditions.max_glitches",
    )
    stop_on_first_crash: bool = Field(
        False,
        description="Legacy top-level alias for stop_conditions.stop_on_first_crash",
    )
    max_runtime_seconds: Optional[float] = Field(
        None,
        gt=0,
        description="Legacy top-level alias for stop_conditions.max_runtime_seconds",
    )

    @model_validator(mode="after")
    def validate_dual_target_fields(self) -> "Campaign":
        if self.mode != "dual_target":
            return self

        missing = []
        if self.slots is None:
            missing.append("slots")
        if self.timing is None:
            missing.append("timing")
        if self.sweeps is None:
            missing.append("sweeps")
        if self.budgets is None:
            missing.append("budgets")
        if missing:
            raise ValueError(
                "dual_target campaigns require " + ", ".join(missing)
            )

        assert self.slots is not None
        expected_slots = {"dut", "platform"}
        present_slots = {str(slot) for slot in self.slots.keys()}
        if present_slots != expected_slots:
            raise ValueError("dual_target slots must contain exactly dut and platform")

        assert self.timing is not None
        assert self.sweeps is not None
        for action in self.timing.timeline:
            for field_name in ("delay_sweep", "width_sweep", "voltage_sweep"):
                sweep_name = getattr(action, field_name)
                if sweep_name is not None and sweep_name not in self.sweeps:
                    raise ValueError(
                        f"timing.timeline references unknown sweep {sweep_name!r}"
                    )
        return self


class CampaignStatus(BaseModel):
    """Run-time progress."""

    campaign_id: str
    active: bool
    completed_attempts: int
    total_attempts: int
    current_position: Optional[Tuple[float, float, float]] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_outcome: Optional[str] = None
