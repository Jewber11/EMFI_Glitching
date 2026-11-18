"""Firmware project, build, and assembly-listing models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class Language(str, Enum):
    C = "c"
    RUST = "rust"


class Hal(str, Enum):
    TI = "ti"
    B01LERS = "b01lers"


class Project(BaseModel):
    """A firmware project on disk under ~/emfi-projects/<id>/."""

    id: str = Field(..., description="Filesystem-safe project ID")
    name: str
    language: Language
    target: str = Field("mspm0l2228", description="Target MCU part number")
    hal: Hal
    created_at: datetime
    description: Optional[str] = None
    build_command: Optional[str] = Field(
        None,
        description="Shell command to build (default: 'make all' for C, 'cargo build --release ...' for Rust)",
    )
    artifact_elf: Optional[str] = Field(
        None,
        description="Path (relative to project root) of the .elf/.out produced by build_command. "
        "Defaults: C → 'firmware.elf', Rust → 'target/thumbv8m.main-none-eabi/release/<id>'",
    )
    versions: List[str] = Field(default_factory=list, description="Git tags")


class BuildArtifact(BaseModel):
    """Deterministic build output. Hash covers source tree + toolchain version."""

    project_id: str
    version: Optional[str] = Field(None, description="Git tag or branch")
    sha: str = Field(..., description="Build content hash")
    built_at: datetime
    elf_path: str
    bin_path: str
    listing_path: str
    symbols_path: str
    success: bool
    log_tail: Optional[str] = None
    host_script_path: Optional[str] = Field(
        None, description="Path to host/run.py copied into the build directory"
    )


class FlashedFirmware(BaseModel):
    """Firmware metadata remembered by Control after a successful flash."""

    build_sha: str = Field(..., description="Build hash flashed onto the DUT")
    flashed_at: datetime
    elf_url: Optional[str] = Field(None, description="ELF source used for the flash request")
    project_id: Optional[str] = Field(None, description="Project ID when supplied by the caller")
    project_version: Optional[str] = Field(
        None,
        description="Project version when supplied by the caller",
    )
    flash_result: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw programmer result metadata",
    )


class AssemblyInstruction(BaseModel):
    """One disassembled instruction with source mapping."""

    pc: int = Field(..., description="Program counter (hex address)")
    bytes_hex: str = Field(..., description="Machine code bytes, hex string")
    mnemonic: str
    operands: str = ""
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    function: Optional[str] = None


class AssemblyListing(BaseModel):
    """Result of `arm-none-eabi-objdump -d` parsed into structured form."""

    project_id: str
    build_sha: str
    cpu_mhz: float = Field(32.0, description="Used by View to convert cycles to delay_us")
    instructions: List[AssemblyInstruction]


class GlitchTarget(BaseModel):
    """User-annotated target instruction or range. Stored in `targets.json` per project.

    Set `pc_end` to mark a contiguous instruction range; the campaign engine
    will sweep delay across the range. Leave `pc_end` as None for a
    single-instruction target.
    """

    pc_address: int
    pc_end: Optional[int] = Field(
        None,
        description="If set, target spans [pc_address, pc_end] (inclusive). "
        "None = single instruction.",
    )
    name: str
    expected_delay_cycles: Optional[int] = Field(
        None,
        description="Cycles from a known reference point (e.g. trigger rising edge)",
    )
    expected_delay_cycles_end: Optional[int] = Field(
        None,
        description="Expected delay at pc_end. Only meaningful when pc_end is set.",
    )
    notes: Optional[str] = None
    created_at: datetime

    @model_validator(mode="after")
    def _validate_range(self) -> "GlitchTarget":
        if self.pc_end is not None and self.pc_end <= self.pc_address:
            raise ValueError(
                f"pc_end ({self.pc_end:#x}) must be > pc_address ({self.pc_address:#x})"
            )
        if (
            self.pc_end is not None
            and self.expected_delay_cycles is not None
            and self.expected_delay_cycles_end is None
        ):
            import warnings
            warnings.warn(
                "Range target has expected_delay_cycles but no expected_delay_cycles_end; "
                "delay sweep across the range will fall back to a single value.",
                stacklevel=2,
            )
        return self


class CampaignPreset(BaseModel):
    """A saved campaign configuration template, stored per-project.

    On disk at `~/emfi-projects/{id}/presets/{preset_id}.json`. `config` is
    a Campaign-shaped dict, kept opaque at the protocol level — Control
    re-validates it against `Campaign` when a user submits the preset.
    """

    id: str = Field(..., description="Filesystem-safe preset ID")
    name: str
    description: Optional[str] = None
    created_at: datetime
    config: Dict[str, Any] = Field(
        ..., description="Campaign body (sans id/created_at) as a dict"
    )
