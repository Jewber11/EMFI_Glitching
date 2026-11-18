"""Shared Pydantic models for the EMFI research platform.

These types are the single source of truth for the wire format between
Control, Develop, and View. Both Python apps import from here; the
SvelteKit apps consume the OpenAPI specs generated from FastAPI routes
that reference these models.
"""

from emfi_protocol.campaigns import (
    AutomationBudgetPolicy,
    Campaign,
    CampaignBudgets,
    CampaignMetadata,
    CampaignMetadataUpdate,
    CampaignTiming,
    GridParams,
    SlotConfig,
    StopConditions,
    SweepParams,
    SweepRange,
    TimelineAction,
    TimingReference,
)
from emfi_protocol.devices import ArmState, DeviceStatus, Position
from emfi_protocol.projects import (
    AssemblyInstruction,
    AssemblyListing,
    BuildArtifact,
    FlashedFirmware,
    GlitchTarget,
    Project,
)
from emfi_protocol.runs import AttemptResult, Outcome, Verdict
from emfi_protocol.ws_events import WsEvent, WsTopic

__all__ = [
    "Campaign",
    "AutomationBudgetPolicy",
    "CampaignBudgets",
    "CampaignMetadata",
    "CampaignMetadataUpdate",
    "CampaignTiming",
    "GridParams",
    "SlotConfig",
    "StopConditions",
    "SweepParams",
    "SweepRange",
    "TimelineAction",
    "TimingReference",
    "ArmState",
    "DeviceStatus",
    "Position",
    "AssemblyInstruction",
    "AssemblyListing",
    "BuildArtifact",
    "FlashedFirmware",
    "GlitchTarget",
    "Project",
    "AttemptResult",
    "Outcome",
    "Verdict",
    "WsEvent",
    "WsTopic",
]
