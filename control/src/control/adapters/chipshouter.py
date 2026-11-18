"""ChipSHOUTER (EMFI pulse source) adapter.

Wraps the ``chipshouter`` pip package. The library exposes most controls
as properties with getters/setters on a ``ChipSHOUTER(comport)`` instance.

Critical invariants (from old-em-setup/HANDOFF.md):
- ``arm()`` MUST be idempotent. The upstream ``armed = True`` calls
  ``cmd_arm()`` which raises ``Firmware_State_Exception`` if already armed.
- ``arm()`` MUST have a timeout. ``wait_for_arm()`` blocks indefinitely
  if HV doesn't come up.
- ``disarm_safe()`` must never raise.

Library API surface (confirmed by probe):
    ChipSHOUTER(comport)
    .state (property, read-only) -> str
    .voltage (property, settable) -> int
    .pulse (property, settable) -> triggers pulse when set to True
    .armed (property, settable) -> calls cmd_arm/cmd_disarm
    .mute (property, settable) -> bool
    .arm_timeout (property, settable) -> int (minutes)
    .faults_current (property, settable)
    .faults_latched (property, read-only)
    .hwtrig_mode (property, settable)
    .hwtrig_term (property, settable)
    .wait_for_arm(timeout=3) -> blocks until armed
    .disconnect()
    .clr_armed (property) -> clears faults then arms
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from control.adapters.base import BaseAdapter

try:
    from chipshouter.com_tools import Reset_Exception  # type: ignore[import-not-found]
except ImportError:  # library not installed in this env
    class Reset_Exception(Exception):  # type: ignore[no-redef]
        """Stand-in for chipshouter.com_tools.Reset_Exception when the lib
        is not installed (e.g. in test environments)."""

# Bit position → fault name, mirroring chipshouter.com_tools.t_16_Bit_Options
# (BIT_FAULT_*). The lib's faults_latched/faults_current already return decoded
# name strings; this map lets us reconstruct a raw bitmask for logging when we
# only have the name list. Kept inline (rather than imported) so the adapter
# degrades gracefully if the lib isn't installed in a test env.
_FAULT_BITS: Dict[str, int] = {
    "fault_probe": 0,
    "fault_overtemp": 1,
    "fault_panel_open": 2,
    "fault_high_voltage": 3,
    "fault_ram_crc": 4,
    "fault_eeprom_crc": 5,
    "fault_gpio_error": 6,
    "fault_ltfault_error": 7,
    "fault_trigger_error": 8,
    "fault_hardware_exc": 9,
    "fault_trigger_glitch": 10,
    "fault_overvoltage": 11,
    "fault_temp_sensor": 12,
}

LOGGER = logging.getLogger(__name__)

# Time to wait after a Reset_Exception before retrying. Per the lib's own
# documented behavior: "wait 5 seconds then reinitialize."
_RESET_RECOVERY_SLEEP = 5.0
_RESET_RETRY_LIMIT = 2  # one initial try + one retry


def _is_armed_state(state: str) -> bool:
    """Return True only for actual armed states, not ``disarmed``."""
    normalized = state.strip().lower()
    return normalized == "armed" or normalized.startswith("armed ")


def _fault_names(raw: Any) -> List[str]:
    """Normalize a faults_latched/faults_current value to a list of names.

    The chipshouter lib returns a list of name strings (e.g.
    ``['fault_high_voltage']``); older/edge cases may return dicts
    (``[{'fault': 1, 'name': 'trigger'}]``) — handle both.
    """
    names: List[str] = []
    if not raw:
        return names
    for item in raw:
        if isinstance(item, dict):
            if item.get("value") or item.get("fault"):
                name = item.get("name")
                if name:
                    names.append(str(name))
        else:
            names.append(str(item))
    return names


def _fault_raw(names: List[str]) -> int:
    """Reconstruct a raw bitmask from decoded fault names (for logging)."""
    raw = 0
    for n in names:
        bit = _FAULT_BITS.get(n)
        if bit is not None:
            raw |= 1 << bit
    return raw


class ChipShouterAdapter(BaseAdapter):
    name = "chipshouter"

    def __init__(self) -> None:
        self._impl = None
        self._port: Optional[str] = None
        self._last_error: Optional[str] = None
        # Most recent latched-fault capture: {"ts", "names", "raw"} or None.
        self.last_fault: Optional[Dict[str, Any]] = None

    def connect(self, port: Optional[str] = None) -> None:
        if port is None:
            raise ValueError("chipshouter: no serial port specified")
        try:
            from chipshouter import ChipSHOUTER
        except ImportError as exc:
            self._last_error = f"chipshouter library not installed: {exc}"
            raise RuntimeError(self._last_error) from exc

        LOGGER.info("ChipSHOUTER connecting on %s", port)
        self._impl = ChipSHOUTER(port)
        self._port = port
        self._last_error = None
        state = str(self._impl.state)
        LOGGER.info("ChipSHOUTER connected — state: %s, voltage: %s",
                     state, self._impl.voltage)

    def disconnect(self) -> None:
        if self._impl is not None:
            LOGGER.info("ChipSHOUTER disconnecting")
            try:
                self._impl.disconnect()
            except Exception as exc:
                LOGGER.warning("ChipSHOUTER disconnect error: %s", exc)
            self._impl = None
            self._port = None

    @property
    def connected(self) -> bool:
        return self._impl is not None

    def _require_connected(self) -> None:
        if self._impl is None:
            raise RuntimeError("ChipSHOUTER is not connected")

    def _with_reset_retry(self, label: str, fn: Callable[[], Any]) -> Any:
        """Run ``fn`` with one retry on ``Reset_Exception``.

        The ChipSHOUTER occasionally resets during property writes and
        verification reads (well-known recurring condition; the lib's own
        docstring recommends sleeping 5s then retrying). If a Reset_Exception
        still fires on the retry, raise RuntimeError with the recovery
        steps the user should take.
        """
        for attempt in range(_RESET_RETRY_LIMIT):
            try:
                return fn()
            except Reset_Exception:
                LOGGER.warning(
                    "ChipSHOUTER reset during %s (attempt %d); waiting %.0fs for reinit",
                    label, attempt + 1, _RESET_RECOVERY_SLEEP,
                )
                time.sleep(_RESET_RECOVERY_SLEEP)
        raise RuntimeError(
            f"ChipSHOUTER reset {_RESET_RETRY_LIMIT} times during {label}; "
            "check HV/USB and retry. If this persists, the chipshouter "
            "Python instance may need to be re-created (disconnect/reconnect)."
        )

    def _capture_faults(self) -> Optional[Dict[str, Any]]:
        """Read latched faults into ``self.last_fault`` (does not clear).

        Returns the capture dict (or None if nothing latched). Always call
        this BEFORE clearing ``faults_current`` so the specific cause is
        preserved for logging and View.
        """
        try:
            latched = self._impl.faults_latched
        except Exception as exc:
            LOGGER.debug("could not read faults_latched: %s", exc)
            return None
        names = _fault_names(latched)
        if not names:
            return None
        capture = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "names": names,
            "raw": _fault_raw(names),
        }
        self.last_fault = capture
        return capture

    def _capture_and_clear_faults(self) -> None:
        """Capture the latched fault cause, log it, then clear faults_current."""
        capture = self._capture_faults()
        if capture is not None:
            LOGGER.warning(
                "ChipSHOUTER fault tripped: %s (raw=0x%x); clearing",
                ", ".join(capture["names"]), capture["raw"],
            )
        else:
            LOGGER.warning("ChipSHOUTER in fault state (no latched detail); clearing")
        self._impl.faults_current = 0

    def get_faults(self) -> Dict[str, Any]:
        """Return the last latched-fault capture, or the live current faults.

        Shape: ``{"last_fault": {...}|None, "current": [names], "connected": bool}``.
        Used by ``GET /devices/chipshouter/faults``.
        """
        if self._impl is None:
            return {"last_fault": self.last_fault, "current": [], "connected": False}
        try:
            current = _fault_names(self._impl.faults_current)
        except Exception as exc:
            LOGGER.debug("could not read faults_current: %s", exc)
            current = []
        return {"last_fault": self.last_fault, "current": current, "connected": True}

    def configure(
        self,
        voltage: int,
        pulse_width_ns: int,
        pulse_repeat: int = 1,
        pulse_deadtime_ms: int = 10,
        arm_timeout_min: int = 1,
        mute: bool = True,
    ) -> None:
        self._require_connected()

        def _do_configure() -> None:
            self._impl.voltage = voltage
            self._impl.pulse.repeat = pulse_repeat
            self._impl.pulse.width = pulse_width_ns
            self._impl.pulse.deadtime = pulse_deadtime_ms * 1000
            self._impl.arm_timeout = arm_timeout_min
            self._impl.mute = mute

        self._with_reset_retry("configure", _do_configure)
        LOGGER.info("ChipSHOUTER configured: V=%d width=%dns repeat=%d mute=%s",
                     voltage, pulse_width_ns, pulse_repeat, mute)

    def configure_hardware_trigger(
        self,
        active_high: bool = True,
        termination_50r: bool = True,
    ) -> None:
        """Configure the external SMB trigger input.

        Scaffold pgen drives the ChipSHOUTER trigger input as a rising pulse, so
        hardware-trigger campaigns need active-high mode enabled before arming.
        """
        self._require_connected()

        def _do_configure() -> None:
            self._impl.hwtrig_mode = bool(active_high)
            self._impl.hwtrig_term = bool(termination_50r)

        self._with_reset_retry("configure_hardware_trigger", _do_configure)
        LOGGER.info(
            "ChipSHOUTER hardware trigger configured: active_high=%s termination_50r=%s",
            active_high,
            termination_50r,
        )

    def set_pulse_width(self, pulse_width_ns: int) -> int:
        """Set the HV pulse width (ns); return the value the device acknowledges.

        This is the parameter that actually determines glitch energy — NOT the
        Scaffold pgen0 trigger width. The device may quantize the request, so
        we read it back and warn on mismatch.
        """
        self._require_connected()
        target = int(pulse_width_ns)

        def _do_set() -> int:
            self._impl.pulse.width = target
            return int(self._impl.pulse.width)

        actual = self._with_reset_retry("set_pulse_width", _do_set)
        if actual != target:
            LOGGER.warning(
                "ChipSHOUTER pulse width set %d ns, device reports %d ns",
                target, actual,
            )
        return actual

    def arm(self, clear_faults: bool = False, timeout_s: float = 5.0) -> None:
        """Idempotent arm with timeout. No-op if already armed.

        Reset_Exception can surface in the lib at any of the property reads
        and writes below; wrap the whole body in the retry helper.
        """
        self._require_connected()

        def _do_arm() -> bool:
            """Return True if armed (either already or after our request)."""
            state = str(self._impl.state).lower()
            if "fault" in state:
                # Capture the specific latched cause BEFORE clearing, so the
                # log/View show WHY (not just "fault").
                self._capture_and_clear_faults()
                time.sleep(0.1)
                state = str(self._impl.state).lower()
            if _is_armed_state(state):
                LOGGER.debug("ChipSHOUTER already armed, skipping")
                return True
            LOGGER.info("ChipSHOUTER arming (timeout=%.1fs)", timeout_s)
            self._impl.armed = True
            return False

        already_armed = self._with_reset_retry("arm", _do_arm)
        if already_armed:
            return

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                s = str(self._impl.state).lower()
            except Reset_Exception:
                LOGGER.warning(
                    "ChipSHOUTER reset during arm wait; waiting %.0fs for reinit",
                    _RESET_RECOVERY_SLEEP,
                )
                time.sleep(_RESET_RECOVERY_SLEEP)
                continue
            if _is_armed_state(s):
                LOGGER.info("ChipSHOUTER armed")
                return
            time.sleep(0.1)

        raise RuntimeError(
            f"ChipSHOUTER failed to arm within {timeout_s}s "
            f"(state: {self._impl.state})"
        )

    def disarm(self) -> None:
        self._require_connected()
        LOGGER.info("ChipSHOUTER disarming")
        self._impl.armed = False

    def disarm_safe(self) -> None:
        """Best-effort disarm — never raises."""
        if self._impl is None:
            return
        try:
            state = str(self._impl.state).lower()
            if not _is_armed_state(state):
                return
            self._impl.armed = False
            LOGGER.info("ChipSHOUTER disarmed (safe)")
        except Exception as exc:
            LOGGER.warning("disarm_safe swallowed: %s", exc)

    def pulse(self) -> None:
        self._require_connected()
        self._impl.pulse = True

    def get_state(self) -> str:
        self._require_connected()
        return str(self._impl.state)

    def get_fault_active(self) -> List[Any]:
        self._require_connected()
        return _fault_names(self._impl.faults_current)

    def status(self) -> Dict[str, Any]:
        status = super().status()
        state: Optional[str] = None
        current_faults: List[str] = []
        if self._impl is not None:
            try:
                state = str(self._impl.state)
            except Exception as exc:
                self._last_error = str(exc)
            try:
                current_faults = _fault_names(self._impl.faults_current)
            except Exception:
                current_faults = []
        status.update(
            {
                "state": state,
                "armed": _is_armed_state(state or ""),
                "faults": current_faults,
                "last_fault": self.last_fault,
            }
        )
        return status
