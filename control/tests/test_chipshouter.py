"""ChipShouterAdapter tests — verifies Reset_Exception retry behavior.

The ChipSHOUTER occasionally resets during property writes; the lib raises
``chipshouter.com_tools.Reset_Exception``. The adapter retries once after
a 5s sleep before giving up.
"""

from __future__ import annotations

import logging
from typing import Any, List
from unittest.mock import patch

import pytest

from control.adapters.chipshouter import (
    ChipShouterAdapter,
    Reset_Exception,
    _fault_names,
    _fault_raw,
)


class _FakePulse:
    def __init__(self) -> None:
        self.repeat = 1
        self.width = 0
        self.deadtime = 0


class _FakeImpl:
    """Configurable chipshouter stand-in.

    ``reset_on`` is a list of property-name strings; assigning to those
    properties raises Reset_Exception the first time, then succeeds.
    ``state_sequence`` is a list of state strings returned by .state in order.
    """

    def __init__(
        self,
        reset_on_voltage_writes: int = 0,
        state_sequence: List[str] = ("ready", "armed"),
    ) -> None:
        # Bypass __setattr__ for initialization so the voltage default
        # doesn't trip the injected Reset_Exception.
        for k, v in {
            "_reset_remaining": reset_on_voltage_writes,
            "_state_sequence": list(state_sequence),
            "_state_idx": 0,
            "voltage": 0,
            "pulse": _FakePulse(),
            "arm_timeout": 0,
            "mute": False,
            "armed": False,
            "faults_current": 0,
            "faults_latched": None,
        }.items():
            object.__setattr__(self, k, v)

    def __setattr__(self, name: str, value: Any) -> None:
        # Inject Reset_Exception during voltage writes if requested.
        if name == "voltage" and self._reset_remaining > 0:
            object.__setattr__(self, "_reset_remaining", self._reset_remaining - 1)
            raise Reset_Exception("simulated reset")
        object.__setattr__(self, name, value)

    @property
    def state(self) -> str:
        if self._state_idx < len(self._state_sequence):
            s = self._state_sequence[self._state_idx]
            self._state_idx += 1
            return s
        return self._state_sequence[-1]


def test_configure_retries_after_reset_exception():
    """First write raises Reset_Exception; retry succeeds."""
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(reset_on_voltage_writes=1)
    with patch("control.adapters.chipshouter.time.sleep") as sleep_mock:
        sa.configure(voltage=500, pulse_width_ns=80)
    # voltage write attempted twice (first raised, second succeeded)
    assert sa._impl.voltage == 500
    # 5-second recovery sleep occurred at least once
    sleep_calls = [c.args[0] for c in sleep_mock.call_args_list]
    assert 5.0 in sleep_calls


def test_configure_gives_up_after_two_resets():
    """Both writes raise Reset_Exception → RuntimeError with hint."""
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(reset_on_voltage_writes=999)
    with patch("control.adapters.chipshouter.time.sleep"):
        with pytest.raises(RuntimeError, match="reset.*times.*configure"):
            sa.configure(voltage=500, pulse_width_ns=80)


def test_configure_succeeds_clean_path():
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(reset_on_voltage_writes=0)
    sa.configure(voltage=300, pulse_width_ns=100, mute=True)
    assert sa._impl.voltage == 300
    assert sa._impl.pulse.width == 100
    assert sa._impl.mute is True


def test_arm_idempotent_when_already_armed():
    """If state reads as 'armed' already, no cmd_arm is sent."""
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(state_sequence=["armed"])
    sa.arm(timeout_s=1.0)
    # We never set armed=True because we shortcut.
    assert sa._impl.armed is False


def test_arm_does_not_treat_disarmed_as_armed():
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(state_sequence=["disarmed", "armed"])

    sa.arm()

    assert sa._impl.armed is True


def test_arm_succeeds_when_state_transitions():
    sa = ChipShouterAdapter()
    sa._impl = _FakeImpl(state_sequence=["ready", "armed"])
    sa.arm(timeout_s=1.0)
    assert sa._impl.armed is True


# --- fault decode helpers -------------------------------------------------

def test_fault_names_handles_string_list():
    assert _fault_names(["fault_high_voltage", "fault_trigger_error"]) == [
        "fault_high_voltage", "fault_trigger_error"
    ]


def test_fault_names_handles_dict_list():
    raw = [{"fault": 1, "name": "fault_high_voltage"}, {"fault": 0, "name": "fault_probe"}]
    # Only entries with a truthy fault/value are included.
    assert _fault_names(raw) == ["fault_high_voltage"]


def test_fault_names_empty():
    assert _fault_names([]) == []
    assert _fault_names(None) == []


def test_fault_raw_reconstructs_bitmask():
    # fault_high_voltage = bit 3 (0x8), fault_trigger_error = bit 8 (0x100).
    assert _fault_raw(["fault_high_voltage"]) == 0x8
    assert _fault_raw(["fault_high_voltage", "fault_trigger_error"]) == 0x108
    # Unknown names are ignored.
    assert _fault_raw(["bogus_fault"]) == 0


# --- Bug 1: capture latched faults before clearing ------------------------

def test_arm_captures_latched_faults_before_clearing():
    """When the device is in fault state, arm() reads faults_latched into
    self.last_fault BEFORE writing faults_current = 0."""
    sa = ChipShouterAdapter()
    impl = _FakeImpl(state_sequence=["fault", "armed"])
    impl.faults_latched = ["fault_high_voltage", "fault_trigger_error"]
    sa._impl = impl
    with patch("control.adapters.chipshouter.time.sleep"):
        sa.arm(timeout_s=1.0)

    # Faults were cleared...
    assert impl.faults_current == 0
    # ...but the specific cause was captured first.
    assert sa.last_fault is not None
    assert sa.last_fault["names"] == ["fault_high_voltage", "fault_trigger_error"]
    assert sa.last_fault["raw"] == 0x108
    assert "ts" in sa.last_fault


def test_capture_faults_returns_none_when_clean():
    sa = ChipShouterAdapter()
    impl = _FakeImpl()
    impl.faults_latched = []
    sa._impl = impl
    assert sa._capture_faults() is None
    assert sa.last_fault is None


def test_get_faults_shape_connected():
    sa = ChipShouterAdapter()
    impl = _FakeImpl()
    impl.faults_latched = []
    impl.faults_current = ["fault_overtemp"]
    sa._impl = impl
    info = sa.get_faults()
    assert info["connected"] is True
    assert info["current"] == ["fault_overtemp"]
    assert info["last_fault"] is None


def test_get_faults_when_disconnected():
    sa = ChipShouterAdapter()
    info = sa.get_faults()
    assert info == {"last_fault": None, "current": [], "connected": False}


# --- Bug 2: HV pulse width set + read-back --------------------------------

def test_set_pulse_width_returns_acknowledged_value():
    sa = ChipShouterAdapter()
    impl = _FakeImpl()
    sa._impl = impl
    actual = sa.set_pulse_width(80)
    assert actual == 80
    assert impl.pulse.width == 80


def test_set_pulse_width_warns_on_quantization(caplog):
    """If the device reports a different width than commanded, warn + return it."""
    sa = ChipShouterAdapter()
    impl = _FakeImpl()

    class _QPulse:
        def __init__(self) -> None:
            self._w = 0
            self.repeat = 1
            self.deadtime = 0

        @property
        def width(self) -> int:
            return self._w + 5  # device quantizes up by 5

        @width.setter
        def width(self, v: int) -> None:
            self._w = int(v)

    impl.pulse = _QPulse()
    sa._impl = impl
    with caplog.at_level(logging.WARNING, logger="control.adapters.chipshouter"):
        actual = sa.set_pulse_width(80)
    assert actual == 85
    assert any("pulse width" in r.message for r in caplog.records)
