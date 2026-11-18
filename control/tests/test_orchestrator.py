"""Tests for the campaign engine — uses fake adapters, no hardware."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List, Optional

import pytest

from control.logbook import Logbook
from control.orchestrator import (
    HostScriptContext,
    Orchestrator,
    ParamsView,
    TRIGGER_WIDTH_NS,
    _default_host_script,
    _grid_points,
    _sweep_range_values,
    materialize_target_delay_sweep,
)
from control.safety import ArmGate, RateLimiter, StopFlag
from control.state import AppState, DeviceStatus
from control.workers import WorkerRegistry


# --------------------------------------------------------------------------
# Fake adapters
# --------------------------------------------------------------------------

class FakeShover:
    def __init__(self) -> None:
        self.connected = True
        self.moves: List[tuple] = []

    def move_absolute_logical(self, x: float, y: float, z: float) -> None:
        self.moves.append((x, y, z))

    def get_position(self) -> tuple:
        return (0.0, 0.0, 0.0)


class FakeShouter:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.pulses = 0
        self.state_value = "ready"
        self.faults: List[Any] = []
        self.armed = False
        self.pulse_widths: List[int] = []
        self.hardware_trigger_configs: List[Dict[str, bool]] = []
        # Simulate device quantization: report back this delta vs commanded.
        self.width_readback_delta = 0

    def arm(self, clear_faults: bool = False) -> None:
        self.armed = True

    def disarm_safe(self) -> None:
        self.armed = False

    def configure(self, **kwargs) -> None:
        pass

    def configure_hardware_trigger(
        self,
        active_high: bool = True,
        termination_50r: bool = True,
    ) -> None:
        self.hardware_trigger_configs.append({
            "active_high": bool(active_high),
            "termination_50r": bool(termination_50r),
        })

    def set_pulse_width(self, pulse_width_ns: int) -> int:
        self.pulse_widths.append(int(pulse_width_ns))
        return int(pulse_width_ns) + self.width_readback_delta

    def pulse(self) -> None:
        self.pulses += 1

    def get_state(self) -> str:
        return self.state_value

    def get_fault_active(self) -> List[Any]:
        return list(self.faults)


class FakeScaffold:
    def __init__(self) -> None:
        self.connected = True
        self.trigger_mode = "software"
        self.next_verdict: Dict[str, Any] = {
            "fault": False, "heartbeat_alive": True, "campaign_complete": False,
        }
        self.power_cycles = 0
        self.pin_writes: List[tuple] = []
        self.pin_outputs: List[int] = []
        self.pin_inputs: List[int] = []
        self.pulse_delays_us: List[float] = []
        self.pulse_widths_ns: List[float] = []
        self.trigger_mode_error: Optional[Exception] = None

    def set_trigger_mode(self, mode: str) -> None:
        if self.trigger_mode_error is not None:
            raise self.trigger_mode_error
        self.trigger_mode = mode

    def set_pulse_delay_us(self, delay_us: float) -> None:
        self.pulse_delays_us.append(delay_us)

    def set_pulse_width_ns(self, width_ns: float) -> None:
        # Now only called ONCE at campaign start (the A0 trigger constant).
        self.pulse_widths_ns.append(width_ns)

    def get_pulse_width_ns(self) -> float:
        return self.pulse_widths_ns[-1] if self.pulse_widths_ns else 200.0

    def arm_attempt(self) -> None:
        pass

    def wait_verdict(self, timeout_s: float) -> Dict[str, Any]:
        return dict(self.next_verdict)

    # Edge-event API used by the default host script. Derives the latched
    # events from next_verdict so tests can drive the outcome by setting it.
    # _D<n> maps to the verdict key the orchestrator's default host reads:
    #   d1 → heartbeat_alive, d2 → fault, d3 → campaign_complete.
    _EVENT_KEY = {1: "heartbeat_alive", 2: "fault", 3: "campaign_complete"}

    def clear_d_event(self, idx: int) -> None:
        pass

    def read_d_event(self, idx: int) -> bool:
        return bool(self.next_verdict.get(self._EVENT_KEY.get(idx, ""), False))

    # Pin I/O stubs so host scripts that call the ScaffoldAdapter pin
    # surface from setup()/attempt() don't blow up under test.
    def set_d_output(self, idx: int) -> None:
        self.pin_outputs.append(idx)

    def set_d_input(self, idx: int) -> None:
        self.pin_inputs.append(idx)

    def write_d(self, idx: int, value: int) -> None:
        self.pin_writes.append((idx, value))

    def read_d(self, idx: int) -> int:
        return 0

    def dut_power_cycle(self) -> None:
        self.power_cycles += 1


def make_ctx(tmp_path) -> Dict[str, Any]:
    """Wire up a fake orchestrator + dependencies."""
    state = AppState(
        devices={
            "chipshover": DeviceStatus(name="chipshover", connected=True),
            "chipshouter": DeviceStatus(name="chipshouter", connected=True),
            "scaffold": DeviceStatus(name="scaffold", connected=True),
            "xds110": DeviceStatus(name="xds110"),
        },
    )
    arm_gate = ArmGate(auto_disarm_seconds=600)
    arm_gate.arm()
    stop_flag = StopFlag()
    rate_limiter = RateLimiter("test", max_per_sec=0)  # 0 = unlimited
    logbook = Logbook(tmp_path)
    workers = WorkerRegistry()
    shover = FakeShover()
    shouter = FakeShouter()
    scaffold = FakeScaffold()

    broadcasts: List[tuple] = []

    def broadcast(topic: str, payload: Dict[str, Any]) -> None:
        broadcasts.append((topic, payload))

    orch = Orchestrator(
        state=state,
        arm_gate=arm_gate,
        stop_flag=stop_flag,
        rate_limiter=rate_limiter,
        logbook=logbook,
        shover=shover,
        shouter=shouter,
        scaffold=scaffold,
        broadcast=broadcast,
        workers=workers,
    )
    return {
        "orch": orch, "state": state, "stop_flag": stop_flag,
        "shover": shover, "shouter": shouter, "scaffold": scaffold,
        "broadcasts": broadcasts, "logbook": logbook,
    }


# --------------------------------------------------------------------------
# Pure-logic tests (no event loop needed)
# --------------------------------------------------------------------------

def test_sweep_range_values_none_yields_single_none():
    assert _sweep_range_values(None) == [None]


def test_sweep_range_values_inclusive_stepped():
    rng = {"start": 1.0, "stop": 3.0, "step": 1.0}
    assert _sweep_range_values(rng) == [1.0, 2.0, 3.0]


def test_materialize_target_delay_sweep_from_target_range(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    project = root / "purpleboardtest"
    build = project / "builds" / "abc123"
    build.mkdir(parents=True)
    (project / "targets.json").write_text(json.dumps([
        {
            "pc_address": 0x1000,
            "pc_end": 0x1008,
            "name": "range",
            "expected_delay_cycles": 64,
            "expected_delay_cycles_end": 96,
            "created_at": "2026-06-01T00:00:00+00:00",
        }
    ]))
    (build / "disassembly.json").write_text(json.dumps({
        "project_id": "purpleboardtest",
        "build_sha": "abc123",
        "cpu_mhz": 16.0,
        "instructions": [],
    }))
    monkeypatch.setenv("EMFI_PROJECTS_ROOT", str(root))

    sweep, note = materialize_target_delay_sweep(
        "purpleboardtest", "abc123", 0x1000, {"attempts_per_point": 1}
    )

    assert note is not None
    assert sweep["delay_us"] == {"start": 4.0, "stop": 6.0, "step": 0.0625}


def test_materialize_target_delay_sweep_keeps_explicit_delay(tmp_path, monkeypatch):
    monkeypatch.setenv("EMFI_PROJECTS_ROOT", str(tmp_path))
    explicit = {"delay_us": {"start": 1.0, "stop": 2.0, "step": 0.5}}

    sweep, note = materialize_target_delay_sweep(
        "purpleboardtest", "abc123", 0x1000, explicit
    )

    assert sweep == explicit
    assert note is None


def test_grid_points_serpentine_y():
    """Y axis alternates direction every Z plane."""
    grid = {
        "origin": (0.0, 0.0), "top_right": (2.0, 1.0),
        "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
    }
    pts = list(_grid_points(grid))
    # 3 x_steps * 2 y_steps * 1 z_step = 6 points
    assert len(pts) == 6
    # First y row (yi=0): x forward 0,1,2
    assert [(p[0], p[1]) for p in pts[:3]] == [(0, 0), (1, 0), (2, 0)]
    # Second y row (yi=1): x reverse 2,1,0
    assert [(p[0], p[1]) for p in pts[3:]] == [(2, 1), (1, 1), (0, 1)]


def test_params_view_supports_all_three_access_styles():
    """Host scripts may use any of attr, dict-key, or .get access."""
    pv = ParamsView({"delay_us": 1.5, "pulse_width_ns": 80})
    # attribute access
    assert pv.delay_us == 1.5
    # dict access
    assert pv["delay_us"] == 1.5
    # .get
    assert pv.get("delay_us") == 1.5
    # missing keys → None for forgiving forms
    assert pv.missing is None
    assert pv["missing"] is None
    assert pv.get("missing") is None
    # .get with default
    assert pv.get("missing", "fallback") == "fallback"
    # ** unpacking
    merged = {"x": 0, **pv}
    assert merged == {"x": 0, "delay_us": 1.5, "pulse_width_ns": 80}
    # to_dict roundtrip
    assert pv.to_dict() == {"delay_us": 1.5, "pulse_width_ns": 80}


def test_host_script_context_wraps_dict_params():
    """HostScriptContext wraps a raw dict so host scripts get attribute access."""
    ctx = HostScriptContext(
        scaffold=None, shouter=None,
        params={"delay_us": 2.0},
        logbook=None, state=None,
    )
    assert isinstance(ctx.params, ParamsView)
    assert ctx.params.delay_us == 2.0
    assert ctx.params["delay_us"] == 2.0
    assert ctx.params.get("delay_us") == 2.0


def test_grid_points_origin_offset():
    """Grid honors non-zero origin."""
    grid = {
        "origin": (5.0, 10.0), "top_right": (6.0, 10.0),
        "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
    }
    pts = list(_grid_points(grid))
    assert (5.0, 10.0) in [(p[0], p[1]) for p in pts]
    assert (6.0, 10.0) in [(p[0], p[1]) for p in pts]


def test_grid_points_support_negative_opposite_corner():
    """Backside fixtures can put the opposite corner in negative logical XY."""
    grid = {
        "origin": (0.0, 0.0), "top_right": (-2.0, -1.0),
        "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
    }
    pts = list(_grid_points(grid))
    assert len(pts) == 6
    assert [(p[0], p[1]) for p in pts[:3]] == [(0, 0), (-1, 0), (-2, 0)]
    assert [(p[0], p[1]) for p in pts[3:]] == [(-2, -1), (-1, -1), (0, -1)]


# --------------------------------------------------------------------------
# perform_attempt classification
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_perform_attempt_classifies_glitch(tmp_path):
    """When verdict.fault is True, outcome should be 'glitch'."""
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": True, "heartbeat_alive": True, "campaign_complete": False,
    }
    host_ctx = HostScriptContext(
        scaffold=bits["scaffold"], shouter=bits["shouter"], params={},
        logbook=bits["logbook"], state=bits["state"],
    )
    result = await bits["orch"].perform_attempt(
        verdict_timeout_s=0.1, pulse_params={},
        host_script=_default_host_script(bits["scaffold"]),
        host_ctx=host_ctx,
    )
    assert result["outcome"] == "glitch"
    assert bits["state"].counters.glitches == 1


@pytest.mark.asyncio
async def test_perform_attempt_classifies_hang(tmp_path):
    """When heartbeat_alive is False (and no fault), outcome should be 'hang'."""
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": False, "heartbeat_alive": False, "campaign_complete": False,
    }
    host_ctx = HostScriptContext(
        scaffold=bits["scaffold"], shouter=bits["shouter"], params={},
        logbook=bits["logbook"], state=bits["state"],
    )
    result = await bits["orch"].perform_attempt(
        verdict_timeout_s=0.1, pulse_params={},
        host_script=_default_host_script(bits["scaffold"]),
        host_ctx=host_ctx,
    )
    assert result["outcome"] == "hang"
    # Hang should trigger DUT power cycle.
    assert bits["scaffold"].power_cycles == 1


@pytest.mark.asyncio
async def test_perform_attempt_classifies_nothing(tmp_path):
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": False, "heartbeat_alive": True, "campaign_complete": False,
    }
    host_ctx = HostScriptContext(
        scaffold=bits["scaffold"], shouter=bits["shouter"], params={},
        logbook=bits["logbook"], state=bits["state"],
    )
    result = await bits["orch"].perform_attempt(
        verdict_timeout_s=0.1, pulse_params={},
        host_script=_default_host_script(bits["scaffold"]),
        host_ctx=host_ctx,
    )
    assert result["outcome"] == "nothing"


@pytest.mark.asyncio
async def test_perform_attempt_host_script_can_access_params_three_ways(tmp_path):
    """Host scripts using attr / dict-key / .get access to ctx.params all work."""
    bits = make_ctx(tmp_path)
    seen: Dict[str, Any] = {}

    class TripleAccessScript:
        @staticmethod
        def attempt(ctx):
            seen["attr"] = ctx.params.delay_us
            seen["item"] = ctx.params["pulse_width_ns"]
            seen["get"] = ctx.params.get("voltage_v")
            seen["missing_attr"] = ctx.params.nonexistent
            seen["missing_get"] = ctx.params.get("nonexistent", "fallback")
            return {"fault": False, "heartbeat_alive": True, "campaign_complete": False}

    host_ctx = HostScriptContext(
        scaffold=bits["scaffold"], shouter=bits["shouter"], params={},
        logbook=bits["logbook"], state=bits["state"],
    )
    await bits["orch"].perform_attempt(
        verdict_timeout_s=0.1,
        pulse_params={"delay_us": 1.5, "pulse_width_ns": 80, "voltage_v": 300},
        host_script=TripleAccessScript(),
        host_ctx=host_ctx,
    )
    assert seen["attr"] == 1.5
    assert seen["item"] == 80
    assert seen["get"] == 300
    assert seen["missing_attr"] is None
    assert seen["missing_get"] == "fallback"


@pytest.mark.asyncio
async def test_run_campaign_marks_phase_failed_when_all_attempts_error(tmp_path):
    """100%-error campaigns must broadcast phase=failed, not phase=completed."""
    bits = make_ctx(tmp_path)

    # Monkey-patch _load_host_script to inject a setup-fine, always-raising attempt.
    import control.orchestrator as mod

    class FailingAttempt:
        @staticmethod
        def setup(ctx): pass
        @staticmethod
        def attempt(ctx): raise RuntimeError("attempt always raises")
        @staticmethod
        def teardown(ctx): pass

    original = mod._load_host_script
    mod._load_host_script = lambda pid: (FailingAttempt(), None)
    try:
        campaign = {
            "id": "all-fail", "name": "test", "project_id": "_test",
            "grid": {
                "origin": (0, 0), "top_right": (1, 0),
                "step_size_mm": 1.0, "z_min_mm": 0, "z_max_mm": 0, "z_step_mm": 1,
            },
            "sweep": {"attempts_per_point": 2},
            "trigger_mode": "software", "shouter_auto_arm": False,
            "verdict_timeout_ms": 50,
        }
        result = await bits["orch"].run_campaign(campaign)
        assert result["ok"] is True
        # Every attempt should have errored.
        progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
        phases = [p.get("phase") for p in progress]
        assert "failed" in phases
        # The failure payload includes the reason.
        failed = [p for p in progress if p.get("phase") == "failed"][0]
        assert "host_script" in failed.get("reason", "")
    finally:
        mod._load_host_script = original


@pytest.mark.asyncio
async def test_perform_attempt_classifies_crash_on_shouter_fault(tmp_path):
    """shouter state == 'fault' should classify as crash when no fault/hang."""
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": False, "heartbeat_alive": True, "campaign_complete": False,
    }
    bits["shouter"].state_value = "fault"
    host_ctx = HostScriptContext(
        scaffold=bits["scaffold"], shouter=bits["shouter"], params={},
        logbook=bits["logbook"], state=bits["state"],
    )
    result = await bits["orch"].perform_attempt(
        verdict_timeout_s=0.1, pulse_params={},
        host_script=_default_host_script(bits["scaffold"]),
        host_ctx=host_ctx,
    )
    assert result["outcome"] == "crash"


# --------------------------------------------------------------------------
# Campaign sweep tests
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_campaign_serpentine_y(tmp_path):
    """Each row of Y reverses X direction."""
    bits = make_ctx(tmp_path)
    campaign = {
        "id": "test-1", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (2.0, 1.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 1},
        "trigger_mode": "software",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": False,  # skip configure/arm to keep test simple
        "verdict_timeout_ms": 50,
    }
    await bits["orch"].run_campaign(campaign)
    # 2x3 grid (3 x_steps × 2 y_steps × 1 z_step)
    assert len(bits["shover"].moves) == 6
    # Row 0 (yi=0): x increases
    row0 = bits["shover"].moves[:3]
    assert [m[0] for m in row0] == [0.0, 1.0, 2.0]
    # Row 1 (yi=1): x decreases
    row1 = bits["shover"].moves[3:]
    assert [m[0] for m in row1] == [2.0, 1.0, 0.0]


@pytest.mark.asyncio
async def test_run_campaign_stops_promptly_on_stop_flag(tmp_path):
    """StopFlag set mid-campaign causes the loop to exit within one attempt."""
    bits = make_ctx(tmp_path)

    # Schedule a stop after the first broadcast.
    def _stop_after_first():
        # Trip flag once we've recorded at least one attempt.
        deadline = 2.0
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < deadline:
            if bits["state"].counters.attempts >= 1:
                bits["stop_flag"].set()
                return
            # spin briefly

    campaign = {
        "id": "test-2", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (10.0, 0.0),  # 11 grid points
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 5},  # 55 total attempts
        "trigger_mode": "software",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
    }

    async def stopper():
        # Wait until first attempt completes, then set stop.
        for _ in range(200):
            if bits["state"].counters.attempts >= 1:
                bits["stop_flag"].set()
                return
            await asyncio.sleep(0.005)

    stop_task = asyncio.create_task(stopper())
    result = await bits["orch"].run_campaign(campaign)
    await stop_task

    # Should have stopped well before 55 attempts.
    assert result["completed"] < 55
    # Final campaign_progress should report phase=stopped.
    progress = [b for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    assert any(p[1].get("phase") == "stopped" for p in progress)


@pytest.mark.asyncio
async def test_run_campaign_stops_at_max_glitches(tmp_path):
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": True,
        "heartbeat_alive": True,
        "campaign_complete": False,
    }
    campaign = {
        "id": "stop-glitches", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (10.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 3},
        "trigger_mode": "software",
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
        "max_glitches": 2,
    }

    result = await bits["orch"].run_campaign(campaign)

    assert result["completed"] == 2
    progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    stopped = [p for p in progress if p.get("phase") == "stopped"]
    assert stopped
    assert "max_glitches reached" in stopped[-1]["reason"]


@pytest.mark.asyncio
async def test_run_campaign_accepts_nested_stop_conditions(tmp_path):
    bits = make_ctx(tmp_path)
    bits["scaffold"].next_verdict = {
        "fault": True,
        "heartbeat_alive": True,
        "campaign_complete": False,
    }
    campaign = {
        "id": "stop-glitches-nested", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (10.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 3},
        "trigger_mode": "software",
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
        "stop_conditions": {"max_glitches": 1},
    }

    result = await bits["orch"].run_campaign(campaign)

    assert result["completed"] == 1
    progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    stopped = [p for p in progress if p.get("phase") == "stopped"]
    assert stopped
    assert "max_glitches reached" in stopped[-1]["reason"]


@pytest.mark.asyncio
async def test_run_campaign_stops_on_first_crash(tmp_path):
    bits = make_ctx(tmp_path)
    bits["shouter"].state_value = "fault"
    campaign = {
        "id": "stop-crash", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (10.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 3},
        "trigger_mode": "software",
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
        "stop_on_first_crash": True,
    }

    result = await bits["orch"].run_campaign(campaign)

    assert result["completed"] == 1
    progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    stopped = [p for p in progress if p.get("phase") == "stopped"]
    assert stopped
    assert stopped[-1]["reason"] == "stop_on_first_crash reached"


@pytest.mark.asyncio
async def test_run_campaign_stops_when_runtime_limit_reached(tmp_path, monkeypatch):
    bits = make_ctx(tmp_path)

    import control.orchestrator as mod

    tick = 100.0

    def fake_monotonic() -> float:
        nonlocal tick
        tick += 1.0
        return tick

    monkeypatch.setattr(mod.time, "monotonic", fake_monotonic)

    campaign = {
        "id": "stop-runtime", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (10.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 3},
        "trigger_mode": "software",
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
        "max_runtime_seconds": 0.5,
    }

    result = await bits["orch"].run_campaign(campaign)

    assert result["completed"] == 0
    progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    stopped = [p for p in progress if p.get("phase") == "stopped"]
    assert stopped
    assert "max_runtime_seconds reached" in stopped[-1]["reason"]


@pytest.mark.asyncio
async def test_run_campaign_broadcasts_position_and_attempt(tmp_path):
    bits = make_ctx(tmp_path)
    campaign = {
        "id": "test-3", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (0.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 1},
        "trigger_mode": "software",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
    }
    await bits["orch"].run_campaign(campaign)
    topics = [b[0] for b in bits["broadcasts"]]
    assert "position" in topics
    assert "attempt" in topics
    assert "counter" in topics
    assert "campaign_progress" in topics


# --------------------------------------------------------------------------
# Hardware trigger mode (one-shot)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_shot_campaign_programs_pgen_and_skips_usb_pulse(tmp_path):
    """In one-shot mode the orchestrator: sets the pgen0 A0-trigger width ONCE
    at campaign start, programs the pgen0 delay per attempt, sets the
    ChipSHOUTER HV pulse width per attempt, and does NOT fire over USB."""
    bits = make_ctx(tmp_path)
    campaign = {
        "id": "hw-1", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (0.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {
            "delay_us": {"start": 1.0, "stop": 2.0, "step": 0.5},
            "attempts_per_point": 1,
        },
        "trigger_mode": "one-shot",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
    }
    await bits["orch"].run_campaign(campaign)
    # Trigger mode wired once.
    assert bits["scaffold"].trigger_mode == "one-shot"
    # pgen0 trigger width set ONCE at campaign start, to the fixed constant.
    assert bits["scaffold"].pulse_widths_ns == [TRIGGER_WIDTH_NS]
    # Three delay values swept (1.0, 1.5, 2.0) → three pgen delay programmings.
    assert bits["scaffold"].pulse_delays_us == [1.0, 1.5, 2.0]
    # HV pulse width pushed to the ChipSHOUTER EVERY attempt (not swept here,
    # so each is the campaign default 80 ns).
    assert bits["shouter"].pulse_widths == [80, 80, 80]
    # No USB pulse in hardware mode.
    assert bits["shouter"].pulses == 0


@pytest.mark.asyncio
async def test_one_shot_auto_arm_configures_chipshouter_external_trigger(tmp_path):
    bits = make_ctx(tmp_path)
    campaign = {
        "id": "hw-trig-config", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (0.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 1},
        "trigger_mode": "one-shot",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": True,
        "verdict_timeout_ms": 10,
    }

    await bits["orch"].run_campaign(campaign)

    assert bits["shouter"].hardware_trigger_configs == [
        {"active_high": True, "termination_50r": True}
    ]
    assert bits["shouter"].armed is False


@pytest.mark.asyncio
async def test_one_shot_campaign_logs_actual_pulse_width(tmp_path):
    """shouter_pulse_width_ns_actual (device read-back) is propagated into each
    logged AttemptResult, even when it differs from the commanded value."""
    bits = make_ctx(tmp_path)
    bits["shouter"].width_readback_delta = 3  # device quantizes 80 → 83
    campaign = {
        "id": "hw-actual", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (0.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 2},
        "trigger_mode": "one-shot",
        "shouter_voltage": 250, "shouter_pulse_width_ns": 80, "shouter_mute": True,
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
    }
    await bits["orch"].run_campaign(campaign)
    rows = bits["logbook"].read(limit=100)
    assert len(rows) == 2
    for r in rows:
        assert r["shouter_pulse_width_ns"] == 80
        assert r["shouter_pulse_width_ns_actual"] == 83


@pytest.mark.asyncio
async def test_hardware_trigger_wiring_failure_aborts_campaign(tmp_path):
    """If set_trigger_mode raises, the campaign aborts (no silent degrade)."""
    bits = make_ctx(tmp_path)
    bits["scaffold"].trigger_mode_error = RuntimeError(
        "hardware trigger wiring failed for 'one-shot': boom"
    )
    campaign = {
        "id": "hw-fail", "name": "test", "project_id": "_test",
        "grid": {
            "origin": (0.0, 0.0), "top_right": (1.0, 0.0),
            "step_size_mm": 1.0, "z_min_mm": 0.0, "z_max_mm": 0.0, "z_step_mm": 1.0,
        },
        "sweep": {"attempts_per_point": 1},
        "trigger_mode": "one-shot",
        "shouter_auto_arm": False,
        "verdict_timeout_ms": 10,
    }
    result = await bits["orch"].run_campaign(campaign)
    assert result["ok"] is False
    assert "wiring failed" in result["reason"]
    # No attempts ran; phase=failed broadcast; error broadcast.
    assert bits["shover"].moves == []
    topics = [b[0] for b in bits["broadcasts"]]
    assert "error" in topics
    progress = [b[1] for b in bits["broadcasts"] if b[0] == "campaign_progress"]
    assert any(p.get("phase") == "failed" for p in progress)


# --------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replay_jogs_and_refires(tmp_path):
    bits = make_ctx(tmp_path)
    # Log an attempt directly via the logbook.
    original = bits["logbook"].append({
        "id": "abc", "outcome": "nothing", "x": 2.5, "y": 1.5, "z": 0.0,
        "trigger_mode": "software",
        "glitch_delay_us": 1.0, "pulse_width_ns": 80, "shouter_voltage": 250,
        "verdict": {"fault": False, "heartbeat_alive": True, "campaign_complete": False},
    })

    bits["scaffold"].next_verdict = {
        "fault": True, "heartbeat_alive": True, "campaign_complete": False,
    }
    new_entry = await bits["orch"].replay("abc")
    assert new_entry["outcome"] == "glitch"  # we set fault=True for replay
    # Position was jogged to original (x, y, z).
    assert bits["shover"].moves == [(2.5, 1.5, 0.0)]
    # New entry is a separate row (different id).
    assert new_entry["id"] != "abc"


@pytest.mark.asyncio
async def test_replay_unknown_run_id(tmp_path):
    bits = make_ctx(tmp_path)
    with pytest.raises(RuntimeError, match="not found"):
        await bits["orch"].replay("nonexistent")
