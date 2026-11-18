"""ScaffoldAdapter tests.

The non-hardware test uses a fake ``_impl`` to verify the adapter dispatches
through ``sig_connect`` for writes (donjon-scaffold 0.9.5 has no
``IO.value`` setter, so the previous ``pin.value = N`` form was silently
broken at runtime).

The ``@pytest.mark.hw`` test exercises the real Scaffold board.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any, List, Tuple

import pytest

if importlib.util.find_spec("scaffold") is None:
    scaffold = types.ModuleType("scaffold")
    scaffold.Polarity = types.SimpleNamespace(HIGH_ON_PULSES="high_on_pulses")
    sys.modules["scaffold"] = scaffold

from control.adapters.scaffold import ScaffoldAdapter


class _FakePin:
    """Minimal IO stand-in. Records what gets written.

    Models the donjon-scaffold edge latch: ``event`` reads 1 once an edge
    was captured; ``clear_event()`` resets it. ``pulse_edge()`` simulates a
    transient the way real hardware latches it — set ``_latched`` so a later
    ``event`` read returns True even though the instantaneous ``value`` is 0.
    """

    def __init__(self, name: str = "pin") -> None:
        self.value = 0  # getter-only on real IO; on the fake we use plain attr
        self.name = name
        self._latched = False
        self._fire_on_clear = False

    @property
    def event(self) -> int:
        return 1 if self._latched else 0

    def clear_event(self) -> None:
        self._latched = False
        # Model an edge that arrives just after the clear (i.e. during the
        # verdict window) — the hardware latch catches it for the later read.
        if self._fire_on_clear:
            self._latched = True
            self._fire_on_clear = False

    def pulse_edge(self) -> None:
        """Latch a transient edge now (already captured by hardware)."""
        self._latched = True

    def arm_window_edge(self) -> None:
        """Arm an edge to arrive during the next verdict window (after clear)."""
        self._fire_on_clear = True


class _FakePgen:
    """Pulse-generator stand-in.

    Mirrors the real lib's second-based ``delay``/``width`` properties: the
    adapter assigns seconds, so the fake just stores them. ``start``/``out``
    are sentinel signal objects used to assert the sig_connect wiring.
    """

    def __init__(self) -> None:
        self.start = "pgen0.start"
        self.out = "pgen0.out"
        self.delay = 0.0
        self.width = 0.0
        self.count = 0
        self.polarity = None
        self.delay_min = 1e-8  # one 100 MHz tick = 10 ns
        self.width_min = 1e-8


class _FakePower:
    def __init__(self) -> None:
        self.dut = 0
        self.platform = 0
        self.all_writes: List[int] = []

    @property
    def all(self) -> int:
        return (1 if self.dut else 0) | (0b10 if self.platform else 0)

    @all.setter
    def all(self, value: int) -> None:
        self.all_writes.append(value)
        self.dut = 1 if value & 0b01 else 0
        self.platform = 1 if value & 0b10 else 0


class _FakeImpl:
    """Just enough donjon-scaffold surface for the adapter's methods."""

    def __init__(self, raise_on_sig_connect: bool = False) -> None:
        self.d0 = _FakePin("d0")
        self.d1 = _FakePin("d1")
        self.d2 = _FakePin("d2")
        self.d3 = _FakePin("d3")
        self.a0 = _FakePin("a0")
        self.pgen0 = _FakePgen()
        self.power = _FakePower()
        self.sys_freq = 100e6
        self.version = "0.9"
        self.sig_connect_calls: List[Tuple[Any, Any]] = []
        self.disconnect_all_count = 0
        self._raise_on_sig_connect = raise_on_sig_connect

    def sig_connect(self, a: Any, b: Any) -> None:
        if self._raise_on_sig_connect:
            raise RuntimeError("Failed to connect (simulated)")
        self.sig_connect_calls.append((a, b))

    def sig_disconnect_all(self) -> None:
        self.disconnect_all_count += 1


def test_set_d_output_routes_constant_zero_via_sig_connect():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa.set_d_output(0)
    assert sa._impl.sig_connect_calls == [(sa._impl.d0, 0)]


def test_write_d_routes_constant_via_sig_connect():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa.write_d(0, 1)
    sa.write_d(0, 0)
    assert sa._impl.sig_connect_calls == [
        (sa._impl.d0, 1),
        (sa._impl.d0, 0),
    ]


def test_write_d_does_not_assign_value():
    """Regression: previously did `pin.value = N` which raises on real IO."""
    sa = ScaffoldAdapter()
    impl = _FakeImpl()

    class _ReadOnlyPin:
        @property
        def value(self) -> int:
            return 0
        # no setter — assigning .value would raise AttributeError

    impl.d0 = _ReadOnlyPin()
    sa._impl = impl
    # Must not raise: the write path goes via sig_connect, not .value =.
    sa.write_d(0, 1)
    assert impl.sig_connect_calls == [(impl.d0, 1)]


def test_read_d_uses_value_getter():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    impl.d1.value = 1
    sa._impl = impl
    assert sa.read_d(1) == 1


def test_set_d_input_is_no_op_in_lib_0_9_5():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa.set_d_input(1)
    # No signal-routing call: input is the default state.
    assert sa._impl.sig_connect_calls == []


def test_aliases_dispatch_to_generic_methods():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa.set_d0_output()
    sa.set_d0(1)
    sa.set_d1_input()
    sa._impl.d1.value = 1
    sa._impl.d2.value = 0
    sa._impl.d3.value = 1
    assert sa.read_d1() == 1
    assert sa.read_d2() == 0
    assert sa.read_d3() == 1
    # set_d0_output drives 0, set_d0(1) drives 1
    assert sa._impl.sig_connect_calls == [
        (sa._impl.d0, 0),
        (sa._impl.d0, 1),
    ]


def test_unknown_pin_raises():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    with pytest.raises(ValueError, match="d99"):
        sa.set_d_output(99)


def test_power_state_reads_dut_and_platform():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    impl.power.dut = 1
    impl.power.platform = 0
    sa._impl = impl
    assert sa.power_state() == {"dut": True, "platform": False}


def test_power_switches_are_independent():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    impl.power.platform = 1
    sa._impl = impl

    sa.dut_power(True)
    assert impl.power.dut == 1
    assert impl.power.platform == 1

    sa.platform_power(False)
    assert impl.power.dut == 1
    assert impl.power.platform == 0


def test_all_power_cycle_uses_combined_power_write(monkeypatch):
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    monkeypatch.setattr("control.adapters.scaffold.time.sleep", lambda _seconds: None)

    sa.all_power_cycle()

    assert impl.power.all_writes == [0b00, 0b11]
    assert sa.power_state() == {"dut": True, "platform": True}


def test_disconnect_powers_off_both_rails():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    impl.power.all = 0b11
    sa._impl = impl

    sa.disconnect()

    assert impl.power.dut == 0
    assert impl.power.platform == 0


# --------------------------------------------------------------------------
# Hardware trigger wiring (pgen0)
# --------------------------------------------------------------------------

def test_one_shot_wires_d0_to_pgen_to_a0():
    from scaffold import Polarity

    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_trigger_mode("one-shot")

    # Matrix cleared before rewiring.
    assert impl.disconnect_all_count == 1
    # One pulse per trigger edge, active-high.
    assert impl.pgen0.count == 1
    assert impl.pgen0.polarity == Polarity.HIGH_ON_PULSES
    # d0 (source) feeds pgen0.start (dest); pgen0.out (source) feeds a0 (dest).
    assert impl.sig_connect_calls == [
        (impl.pgen0.start, impl.d0),
        (impl.a0, impl.pgen0.out),
    ]
    assert sa.trigger_mode == "one-shot"
    assert sa.last_trigger_mode_error is None


def test_free_run_wires_same_path_as_one_shot():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_trigger_mode("free-run")
    assert impl.sig_connect_calls == [
        (impl.pgen0.start, impl.d0),
        (impl.a0, impl.pgen0.out),
    ]
    assert sa.trigger_mode == "free-run"


def test_software_mode_leaves_a0_idle():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_trigger_mode("software")
    # Matrix cleared, but no pgen wiring.
    assert impl.disconnect_all_count == 1
    assert impl.sig_connect_calls == []
    assert sa.trigger_mode == "software"


def test_one_shot_wiring_failure_raises_and_records_error():
    sa = ScaffoldAdapter()
    impl = _FakeImpl(raise_on_sig_connect=True)
    sa._impl = impl
    with pytest.raises(RuntimeError, match="hardware trigger wiring failed"):
        sa.set_trigger_mode("one-shot")
    # Surfaced for the orchestrator to inspect; no silent software fallback.
    assert sa.last_trigger_mode_error is not None
    assert "Failed to connect" in sa.last_trigger_mode_error
    assert sa.trigger_mode != "one-shot"


def test_set_pulse_delay_us_converts_to_seconds():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_pulse_delay_us(1.0)
    assert impl.pgen0.delay == pytest.approx(1e-6)
    sa.set_pulse_delay_us(2.5)
    assert impl.pgen0.delay == pytest.approx(2.5e-6)


def test_set_pulse_width_ns_converts_to_seconds():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_pulse_width_ns(80.0)
    assert impl.pgen0.width == pytest.approx(80e-9)


def test_get_pulse_width_ns_reads_back_nanoseconds():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    sa.set_pulse_width_ns(200.0)          # trigger constant
    assert sa.get_pulse_width_ns() == pytest.approx(200.0)
    # Direct register value (seconds) round-trips through the ns getter.
    impl.pgen0.width = 150e-9
    assert sa.get_pulse_width_ns() == pytest.approx(150.0)


def test_pulse_timing_clamps_to_hardware_minimum():
    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    # A zero delay isn't representable; clamp to one clock tick (delay_min).
    sa.set_pulse_delay_us(0.0)
    assert impl.pgen0.delay == pytest.approx(impl.pgen0.delay_min)
    sa.set_pulse_width_ns(0.0)
    assert impl.pgen0.width == pytest.approx(impl.pgen0.width_min)


def test_invalid_trigger_mode_raises():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    with pytest.raises(ValueError, match="Invalid trigger mode"):
        sa.set_trigger_mode("turbo")


@pytest.mark.hw
def test_scaffold_one_shot_hardware_pulse():
    """Hardware: configure one-shot, set 1 us delay + 100 ns width.

    Verification (manual, with a scope on A0):
      - Toggle D0 high via the raw API (or let the target assert USER_TEST).
      - A0 should fire ONE pulse ~1 us after the D0 rising edge, ~100 ns wide.
    Run with ``pytest -m hw`` on the lab box; expects /dev/ttyUSB0.
    """
    sa = ScaffoldAdapter()
    sa.connect("/dev/ttyUSB0")
    try:
        sa.set_trigger_mode("one-shot")
        sa.set_pulse_delay_us(1.0)
        sa.set_pulse_width_ns(100.0)
        # Drive D0 high manually to trigger one pulse (scope A0 to confirm).
        sa.raw.pgen0.fire()  # also fireable directly for a bench check
    finally:
        sa.set_trigger_mode("software")
        sa.disconnect()


@pytest.mark.hw
def test_scaffold_pin_io_roundtrip():
    """Hardware: open the real board, drive D0, read D1.

    Marked hw so it's skipped in normal runs. Run with ``pytest -m hw``
    on the lab box; expects /dev/ttyUSB0 to be the Scaffold.
    """
    sa = ScaffoldAdapter()
    sa.connect("/dev/ttyUSB0")
    try:
        sa.set_d_output(0)
        sa.write_d(0, 1)
        sa.write_d(0, 0)
        # If D0 is looped to D1 in hardware, this should read what we wrote.
        # Otherwise the call still must not raise.
        _ = sa.read_d(1)
    finally:
        sa.disconnect()


# --------------------------------------------------------------------------
# Edge-event latches (Bug 1: transient fault edges missed by read_d)
# --------------------------------------------------------------------------

def test_read_d_event_reflects_latch():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    assert sa.read_d_event(2) is False
    sa._impl.d2.pulse_edge()           # transient: latched, value still 0
    assert sa._impl.d2.value == 0
    assert sa.read_d_event(2) is True   # but the event latch caught it


def test_clear_d_event_resets_latch():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa._impl.d2.pulse_edge()
    sa.clear_d_event(2)
    assert sa.read_d_event(2) is False


def test_event_aliases_match_indices():
    sa = ScaffoldAdapter()
    sa._impl = _FakeImpl()
    sa._impl.d1.pulse_edge()
    sa._impl.d3.pulse_edge()
    assert sa.read_d1_event() is True
    assert sa.read_d2_event() is False
    assert sa.read_d3_event() is True
    sa.clear_d1_event()
    sa.clear_d3_event()
    assert sa.read_d1_event() is False
    assert sa.read_d3_event() is False


def test_default_host_script_catches_transient_fault_edge():
    """A fault edge during the verdict window → outcome fault=True even though
    the instantaneous pin value is low (the Bug 1 scenario)."""
    from control.orchestrator import HostScriptContext, _default_host_script

    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl

    host = _default_host_script(sa)
    ctx = HostScriptContext(
        scaffold=sa, shouter=None, params={"verdict_timeout_s": 0.0},
        logbook=None, state=None,
    )
    host.setup(ctx)  # declares d1/d2/d3 as inputs (no-op on 0.9.5)

    # Target pulses D2 (self-detected fault) and D1 (heartbeat alive)
    # transiently *during* the verdict window — after attempt() clears the
    # latches. The hardware latch catches them even though .value reads 0.
    impl.d2.arm_window_edge()
    impl.d1.arm_window_edge()
    verdict = host.attempt(ctx)
    assert verdict == {
        "fault": True, "heartbeat_alive": True, "campaign_complete": False,
    }


def test_default_host_script_clears_before_window():
    """Stale latches from a prior attempt must not leak into the next verdict."""
    from control.orchestrator import HostScriptContext, _default_host_script

    sa = ScaffoldAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    host = _default_host_script(sa)
    ctx = HostScriptContext(
        scaffold=sa, shouter=None, params={"verdict_timeout_s": 0.0},
        logbook=None, state=None,
    )
    # Pre-existing stale fault latch.
    impl.d2.pulse_edge()
    # attempt() clears at the start of the window; nothing pulses during it.
    verdict = host.attempt(ctx)
    assert verdict["fault"] is False
