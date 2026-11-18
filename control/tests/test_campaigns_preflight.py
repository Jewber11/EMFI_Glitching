from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

import control.routers.campaigns as campaigns_router
from emfi_protocol.campaigns import (
    AutomationBudgetPolicy,
    Campaign,
    GridParams,
    SweepParams,
    SweepRange,
)
from emfi_protocol.projects import FlashedFirmware

from control.routers.campaigns import _preflight, start
from control.state import AppState, DeviceStatus


class _Config:
    def get(self, *path: str, default: Any = None) -> Any:
        if path == ("safety",):
            return {
                "max_voltage_v": 350,
                "max_pulses_per_sec": 10,
                "max_attempts_per_location": 1000,
            }
        return default


@dataclass
class _Context:
    state: AppState
    config: _Config = field(default_factory=_Config)
    campaigns: dict[str, Any] = field(default_factory=dict)
    flashed_firmware: FlashedFirmware | None = None


def _campaign(**overrides) -> Campaign:
    data = {
        "name": "test",
        "project_id": "purpleboardtest",
        "build_sha": "abc123",
        "grid": GridParams(
            origin=(0.0, 0.0),
            top_right=(1.0, 1.0),
            step_size_mm=1.0,
            z_min_mm=0.0,
            z_max_mm=0.0,
            z_step_mm=0.1,
        ),
        "sweep": SweepParams(
            pulse_width_ns=SweepRange(start=1000, stop=3000, step=1000),
            attempts_per_point=2,
        ),
        "trigger_mode": "software",
        "shouter_voltage": 250,
    }
    data.update(overrides)
    return Campaign(**data)


def _state(*connected: str, armed: bool = True) -> AppState:
    names = ("chipshover", "chipshouter", "scaffold", "xds110")
    return AppState(
        armed=armed,
        origin_set=True,
        devices={
            name: DeviceStatus(name=name, connected=name in connected)
            for name in names
        },
    )


def test_preflight_ok_counts_budget():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(_campaign(), ctx)

    assert result.ok is True
    assert result.grid_points == 4
    assert result.sweep_points == 6
    assert result.total_attempts == 24
    assert result.blockers == []
    assert any("no automation_policy" in w for w in result.warnings)


def test_preflight_allows_negative_backside_grid_with_warning():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(
        _campaign(
            grid=GridParams(
                origin=(0.0, 0.0),
                top_right=(-4.1, -4.1),
                step_size_mm=1.0,
                z_min_mm=0.0,
                z_max_mm=0.0,
                z_step_mm=0.1,
            )
        ),
        ctx,
    )

    assert result.ok is True
    assert result.grid_points == 25
    assert any("negative direction" in w for w in result.warnings)


def test_preflight_counts_materialized_target_delay_sweep(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    project = root / "purpleboardtest"
    build = project / "builds" / "abc123"
    build.mkdir(parents=True)
    (project / "targets.json").write_text(json.dumps([
        {
            "pc_address": 0x1000,
            "pc_end": 0x1004,
            "name": "range",
            "expected_delay_cycles": 32,
            "expected_delay_cycles_end": 34,
            "created_at": "2026-06-01T00:00:00+00:00",
        }
    ]))
    (build / "disassembly.json").write_text(json.dumps({
        "project_id": "purpleboardtest",
        "build_sha": "abc123",
        "cpu_mhz": 32.0,
        "instructions": [],
    }))
    monkeypatch.setenv("EMFI_PROJECTS_ROOT", str(root))
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(
        _campaign(target_pc=0x1000, sweep=SweepParams(attempts_per_point=1)),
        ctx,
    )

    assert result.ok is False
    assert result.sweep_points == 3
    assert result.total_attempts == 12
    assert any("Delay sweeps require external trigger" in b for b in result.blockers)
    assert any("delay_us materialized from target" in w for w in result.warnings)


def test_preflight_blocks_missing_required_device():
    ctx = _Context(_state("chipshover", "scaffold"))

    result = _preflight(_campaign(), ctx)

    assert result.ok is False
    assert "required device is not connected: chipshouter" in result.blockers


def test_preflight_blocks_voltage_over_safety_limit():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold"))

    result = _preflight(_campaign(shouter_voltage=500), ctx)

    assert result.ok is False
    assert any("exceeds safety max_voltage_v" in b for b in result.blockers)


def test_preflight_blocks_automation_policy_max_attempts():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(
        _campaign(automation_policy=AutomationBudgetPolicy(max_attempts=10)),
        ctx,
    )

    assert result.ok is False
    assert any("automation_policy.max_attempts" in b for b in result.blockers)


def test_preflight_blocks_automation_policy_max_runtime():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(
        _campaign(automation_policy=AutomationBudgetPolicy(max_runtime_seconds=1)),
        ctx,
    )

    assert result.ok is False
    assert any("automation_policy.max_runtime_seconds" in b for b in result.blockers)


def test_preflight_blocks_automation_policy_max_voltage_from_base_and_sweep():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    base = _preflight(
        _campaign(automation_policy=AutomationBudgetPolicy(max_voltage=200)),
        ctx,
    )
    swept = _preflight(
        _campaign(
            shouter_voltage=150,
            sweep=SweepParams(
                voltage_v=SweepRange(start=100, stop=260, step=80),
                attempts_per_point=1,
            ),
            automation_policy=AutomationBudgetPolicy(max_voltage=200),
        ),
        ctx,
    )

    assert any("automation_policy.max_voltage" in b for b in base.blockers)
    assert any("automation_policy.max_voltage" in b for b in swept.blockers)


def test_preflight_blocks_automation_policy_trigger_mode():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(
        _campaign(
            trigger_mode="software",
            automation_policy=AutomationBudgetPolicy(allowed_trigger_modes=["one-shot"]),
        ),
        ctx,
    )

    assert result.ok is False
    assert any("allowed by automation_policy.allowed_trigger_modes" in b for b in result.blockers)


def test_preflight_warns_when_not_armed_or_pinned():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", armed=False))

    result = _preflight(_campaign(build_sha=None), ctx)

    assert result.ok is True
    assert any("not armed" in w for w in result.warnings)
    assert any("no pinned build_sha" in w for w in result.warnings)


def test_preflight_warns_when_pinned_build_has_no_flash_record():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    result = _preflight(_campaign(build_sha="abc123"), ctx)

    assert result.ok is True
    assert any("no successful DUT flash recorded" in w for w in result.warnings)


def test_preflight_blocks_flashed_build_mismatch():
    ctx = _Context(
        _state("chipshover", "chipshouter", "scaffold", "xds110"),
        flashed_firmware=FlashedFirmware(
            build_sha="flashed456",
            project_id="purpleboardtest",
            flashed_at=datetime.now(timezone.utc),
        ),
    )

    result = _preflight(_campaign(build_sha="abc123"), ctx)

    assert result.ok is False
    assert any("does not match flashed DUT build flashed456" in b for b in result.blockers)


def test_preflight_blocks_flashed_project_mismatch_when_recorded():
    ctx = _Context(
        _state("chipshover", "chipshouter", "scaffold", "xds110"),
        flashed_firmware=FlashedFirmware(
            build_sha="abc123",
            project_id="other-project",
            flashed_at=datetime.now(timezone.utc),
        ),
    )

    result = _preflight(_campaign(project_id="purpleboardtest", build_sha="abc123"), ctx)

    assert result.ok is False
    assert any("does not match flashed DUT project other-project" in b for b in result.blockers)


@pytest.mark.asyncio
async def test_campaign_start_blocks_flashed_build_mismatch():
    ctx = _Context(
        _state("chipshover", "chipshouter", "scaffold", "xds110"),
        flashed_firmware=FlashedFirmware(
            build_sha="flashed456",
            project_id="purpleboardtest",
            flashed_at=datetime.now(timezone.utc),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await start(_campaign(build_sha="abc123"), ctx)

    assert exc.value.status_code == 409
    assert any("does not match flashed DUT build" in b for b in exc.value.detail["blockers"])


@pytest.mark.asyncio
async def test_campaign_start_blocks_failed_preflight_policy():
    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    with pytest.raises(HTTPException) as exc:
        await start(_campaign(automation_policy=AutomationBudgetPolicy(max_attempts=10)), ctx)

    assert exc.value.status_code == 409
    assert any("automation_policy.max_attempts" in b for b in exc.value.detail["blockers"])


@pytest.mark.asyncio
async def test_campaign_start_counts_materialized_target_delay_sweep(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "projects"
    project = root / "purpleboardtest"
    build = project / "builds" / "abc123"
    build.mkdir(parents=True)
    (project / "targets.json").write_text(json.dumps([
        {
            "pc_address": 0x1000,
            "pc_end": 0x1004,
            "name": "range",
            "expected_delay_cycles": 32,
            "expected_delay_cycles_end": 34,
            "created_at": "2026-06-01T00:00:00+00:00",
        }
    ]))
    (build / "disassembly.json").write_text(json.dumps({
        "project_id": "purpleboardtest",
        "build_sha": "abc123",
        "cpu_mhz": 32.0,
        "instructions": [],
    }))
    monkeypatch.setenv("EMFI_PROJECTS_ROOT", str(root))
    monkeypatch.setattr(campaigns_router.asyncio, "create_task", lambda coro: coro.close())

    ctx = _Context(_state("chipshover", "chipshouter", "scaffold", "xds110"))

    with pytest.raises(HTTPException) as exc:
        await start(_campaign(target_pc=0x1000, sweep=SweepParams(attempts_per_point=1)), ctx)
    assert exc.value.status_code == 409
    assert any("Delay sweeps require external trigger" in b for b in exc.value.detail["blockers"])
