"""Ledger Donjon Scaffold board adapter.

Wraps the ``donjon-scaffold`` pip package (>= 0.7 for chain module).
Handles DUT power, D0-D3 pin map, A0 trigger modes, and verdict polling.

Pin map (from old-em-setup/HANDOFF.md):
    PA21 USER_TEST       → D0  (input; rising edge = test loop start)
    PB14 USER_HEARTBEAT  → D1  (input; toggled regularly = alive)
    PB10 USER_LED_2      → D2  (input; rising edge = self-detected fault)
    PB9  USER_LED_3      → D3  (input; falling edge = campaign end)
    --                     A0  (output to ChipSHOUTER external trigger)

Trigger modes:
    disabled  — A0 idle, no automatic trigger
    software  — A0 idle; ChipSHOUTER fires via USB (pulse())
    one-shot  — hardware: D0 rising edge → pgen0 (delay, then pulse) → A0
                (ChipSHOUTER external trigger), one pulse per edge.
    free-run  — same wiring as one-shot in this implementation (see note).

Hardware-trigger implementation (donjon-scaffold 0.9.5, introspected):
    - ``sig_connect(a, b)`` feeds destination ``a`` with source ``b`` (a << b).
    - ``pgen0.start`` is a matrix *destination* fed by ``d0`` (the source).
    - ``pgen0.out`` is a matrix *source* that drives ``a0`` (the destination).
    - ``pgen0.delay`` / ``pgen0.width`` are float properties in *seconds*;
      the library converts to 100 MHz clock ticks internally. We therefore
      set them in seconds rather than computing raw tick registers.
    The earlier chain0-based wiring failed because chain ``events`` are
    matrix destinations (not sources) and the connect direction was
    reversed; pgen0 is the correct module for delay-then-pulse generation.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from control.adapters.base import BaseAdapter

LOGGER = logging.getLogger(__name__)

_VALID_TRIGGER_MODES = ("disabled", "software", "one-shot", "free-run")
_HARDWARE_TRIGGER_MODES = ("one-shot", "free-run")


class ScaffoldAdapter(BaseAdapter):
    name = "scaffold"
    trigger_mode: str = "software"
    # System clock in MHz. Overwritten from the board's reported sys_freq on
    # connect; 100 MHz is the Scaffold default. Informational — the actual
    # tick conversion is done by the lib's second-based pgen properties.
    CLOCK_MHZ: float = 100.0

    def __init__(self) -> None:
        self._impl = None
        self._port: Optional[str] = None
        self._last_error: Optional[str] = None
        self._version: Optional[str] = None
        self._sys_freq: float = 100e6
        # Last hardware-trigger wiring failure, surfaced so the orchestrator
        # can abort rather than silently fall back to software.
        self.last_trigger_mode_error: Optional[str] = None

    def connect(self, port: Optional[str] = None) -> None:
        if port is None:
            raise ValueError("scaffold: no serial port specified")
        try:
            from scaffold import Scaffold
            from scaffold import bus as scaffold_bus
        except ImportError as exc:
            self._last_error = f"donjon-scaffold library not installed: {exc}"
            raise RuntimeError(self._last_error) from exc

        LOGGER.info("Scaffold connecting on %s", port)
        serial_cls = scaffold_bus.serial.Serial
        timeout_s = float(os.environ.get("SCAFFOLD_SERIAL_TIMEOUT_S", "2.0"))

        def serial_with_timeout(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", timeout_s)
            kwargs.setdefault("write_timeout", timeout_s)
            return serial_cls(*args, **kwargs)

        scaffold_bus.serial.Serial = serial_with_timeout
        try:
            self._impl = Scaffold(port)
            self._port = port
            self._version = str(self._impl.version)
            # Cache the system clock so delay/width conversions and logs are
            # correct even if a future board reports a non-100 MHz frequency.
            self._sys_freq = float(getattr(self._impl, "sys_freq", 100e6))
            self.CLOCK_MHZ = self._sys_freq / 1e6
            self._last_error = None
            LOGGER.info(
                "Scaffold connected — firmware %s, clock %.0f MHz",
                self._version, self.CLOCK_MHZ,
            )
        except Exception as exc:
            self._impl = None
            self._port = None
            self._version = None
            self._last_error = f"Scaffold connect failed on {port}: {exc}"
            raise RuntimeError(self._last_error) from exc
        finally:
            scaffold_bus.serial.Serial = serial_cls

    def disconnect(self) -> None:
        if self._impl is not None:
            LOGGER.info("Scaffold disconnecting")
            try:
                self._impl.sig_disconnect_all()
            except Exception as exc:
                LOGGER.debug("sig_disconnect_all: %s", exc)
            try:
                self._impl.power.dut = 0
                self._impl.power.platform = 0
            except Exception as exc:
                LOGGER.debug("power off on disconnect: %s", exc)
            self._impl = None
            self._port = None

    @property
    def connected(self) -> bool:
        return self._impl is not None

    def _require_connected(self) -> None:
        if self._impl is None:
            raise RuntimeError("Scaffold is not connected")

    def set_trigger_mode(self, mode: str) -> None:
        """Configure the A0 trigger path for the given mode.

        For hardware modes (one-shot / free-run), wire the pulse generator
        so a rising edge on D0 (target USER_TEST) starts pgen0, which after
        the configured delay drives A0 (ChipSHOUTER external trigger) for the
        configured width — all in hardware, zero USB jitter.

        Raises RuntimeError if hardware wiring fails (does NOT silently fall
        back to software). ``last_trigger_mode_error`` is also set so the
        caller can inspect the failure.
        """
        if mode not in _VALID_TRIGGER_MODES:
            raise ValueError(
                f"Invalid trigger mode: {mode}. Must be one of {_VALID_TRIGGER_MODES}"
            )
        self._require_connected()
        self.last_trigger_mode_error = None

        sc = self._impl
        # Clear any previous routing before (re)wiring.
        sc.sig_disconnect_all()

        if mode in ("disabled", "software"):
            self.trigger_mode = mode
            LOGGER.info("Scaffold trigger mode set to %s (A0 idle)", mode)
            return

        # Hardware modes: wire d0 -> pgen0.start, pgen0.out -> a0.
        try:
            from scaffold import Polarity

            pgen = sc.pgen0
            # One pulse per trigger edge. (free-run uses the same wiring; the
            # chain-based "fire after Nth event" gating that historically
            # distinguished the two modes is not implemented with pgen — both
            # produce one precise pulse per D0 rising edge, which is what the
            # campaign loop needs.)
            pgen.count = 1
            # Active-high trigger pulse (idle low, high during the pulse).
            pgen.polarity = Polarity.HIGH_ON_PULSES
            # D0 rising edge starts the pulse generator (d0 is the source).
            sc.sig_connect(pgen.start, sc.d0)
            # Pulse generator output drives the A0 trigger to the ChipSHOUTER.
            sc.sig_connect(sc.a0, pgen.out)
        except Exception as exc:
            self.last_trigger_mode_error = f"{type(exc).__name__}: {exc}"
            LOGGER.error(
                "Hardware trigger wiring failed for mode '%s': %s", mode, exc
            )
            # Leave the matrix disconnected (A0 idle) and propagate so the
            # orchestrator can abort instead of silently degrading.
            raise RuntimeError(
                f"hardware trigger wiring failed for '{mode}': {exc}"
            ) from exc

        self.trigger_mode = mode
        LOGGER.info(
            "Scaffold trigger mode set to %s "
            "(d0 → pgen0.start, pgen0.out → a0, delay/width per attempt)",
            mode,
        )

    def set_pulse_delay_us(self, delay_us: float) -> None:
        """Set the pgen0 delay (trigger edge → pulse start), in microseconds.

        The lib's ``pgen0.delay`` setter takes seconds and converts to clock
        ticks internally, so we just convert µs → s. Clamped to the hardware
        minimum (one clock tick) since a zero delay is not representable.
        """
        self._require_connected()
        pgen = self._impl.pgen0
        seconds = max(float(delay_us) * 1e-6, pgen.delay_min)
        pgen.delay = seconds
        LOGGER.debug("pgen0 delay set to %.3f us", seconds * 1e6)

    def set_pulse_width_ns(self, width_ns: float) -> None:
        """Set the pgen0 pulse width = the A0 *trigger* high-time, in ns.

        This is only the duration the A0 line is held high to register a
        rising edge at the ChipSHOUTER's external-trigger input — it does NOT
        determine the EMFI HV pulse width (that's the ChipSHOUTER's own
        ``pulse.width``). Set this once at campaign start to a fixed constant
        (see CAMPAIGN_TRIGGER_WIDTH_NS); do not drive it from the sweep's
        pulse_width_ns. Clamped to the hardware minimum (one clock tick).
        """
        self._require_connected()
        pgen = self._impl.pgen0
        seconds = max(float(width_ns) * 1e-9, pgen.width_min)
        pgen.width = seconds
        LOGGER.debug("pgen0 trigger width set to %.1f ns", seconds * 1e9)

    def get_pulse_width_ns(self) -> float:
        """Read pgen0.width back as nanoseconds (the A0 trigger high-time)."""
        self._require_connected()
        return float(self._impl.pgen0.width) * 1e9

    def arm_attempt(self) -> None:
        """Prepare for the next verdict (reset pin-edge latches).

        No pgen re-arm is needed in hardware modes: the pulse generator
        fires automatically on each rising edge of its ``start`` signal
        (D0), so it is ready for the next attempt without intervention.
        """
        self._require_connected()
        for pin_name in ("d1", "d2", "d3"):
            pin = getattr(self._impl, pin_name, None)
            if pin is not None and hasattr(pin, "clear_event"):
                try:
                    pin.clear_event()
                except Exception as exc:
                    LOGGER.debug("%s.clear_event failed: %s", pin_name, exc)

    def wait_verdict(self, timeout_s: float) -> Dict[str, Any]:
        """Poll D1/D2/D3 until verdict or timeout.

        Returns the shape emfi_protocol.runs.Verdict expects:
            { fault: bool, heartbeat_alive: bool, campaign_complete: bool }
        """
        self._require_connected()
        deadline = time.monotonic() + timeout_s
        fault = False
        heartbeat_alive = False
        campaign_complete = False

        while time.monotonic() < deadline:
            if self._impl.d2.event:
                fault = True
            if self._impl.d1.event:
                heartbeat_alive = True
            if self._impl.d3.event:
                campaign_complete = True
            if fault or heartbeat_alive:
                break
            time.sleep(0.005)

        return {
            "fault": fault,
            "heartbeat_alive": heartbeat_alive,
            "campaign_complete": campaign_complete,
        }

    # ------------------------------------------------------------------
    # Power rails. Scaffold exposes two independent 3.3 V supplies:
    #   - DUT      (bit 0) — the MSPM0L2228 target socket
    #   - Platform (bit 1) — auxiliary header for daughterboards, level
    #                        shifters, external analog frontends, etc.
    # The two are wired through separate FETs on the board, so toggling
    # one never disturbs the other. Both are off by default at power-on.
    # ------------------------------------------------------------------

    def dut_power_cycle(self, off_time: float = 0.05) -> None:
        """Power-cycle the DUT via Scaffold's power module."""
        self._require_connected()
        LOGGER.info("DUT power cycle (off_time=%.3fs)", off_time)
        self._impl.power.dut = 0
        time.sleep(off_time)
        self._impl.power.dut = 1
        time.sleep(0.05)

    def dut_power(self, on: bool) -> None:
        self._require_connected()
        self._impl.power.dut = 1 if on else 0
        LOGGER.info("DUT power %s", "ON" if on else "OFF")

    def platform_power_cycle(self, off_time: float = 0.05) -> None:
        """Power-cycle the Platform rail (slot 2)."""
        self._require_connected()
        LOGGER.info("Platform power cycle (off_time=%.3fs)", off_time)
        self._impl.power.platform = 0
        time.sleep(off_time)
        self._impl.power.platform = 1
        time.sleep(0.05)

    def platform_power(self, on: bool) -> None:
        self._require_connected()
        self._impl.power.platform = 1 if on else 0
        LOGGER.info("Platform power %s", "ON" if on else "OFF")

    def _set_all_power(self, value: int) -> None:
        power = self._impl.power
        try:
            power.all = value
            return
        except AttributeError:
            LOGGER.debug("Scaffold power.all is unavailable; writing rails separately")
        power.dut = 1 if (value & 0b01) else 0
        power.platform = 1 if (value & 0b10) else 0

    def all_power_cycle(self, off_time: float = 0.05) -> None:
        """Power-cycle DUT and Platform together."""
        self._require_connected()
        LOGGER.info("All-rails power cycle (off_time=%.3fs)", off_time)
        self._set_all_power(0b00)
        time.sleep(off_time)
        self._set_all_power(0b11)
        time.sleep(0.05)

    def power_state(self) -> Dict[str, bool]:
        """Snapshot both rails. Returns ``{"dut": bool, "platform": bool}``."""
        self._require_connected()
        return {
            "dut": bool(self._impl.power.dut),
            "platform": bool(self._impl.power.platform),
        }

    # ------------------------------------------------------------------
    # Pin I/O surface used by per-project host/run.py scripts.
    #
    # donjon-scaffold 0.9.5 IO model (introspected — docstring lies about
    # the setter):
    #   IO.value         -> READ-ONLY property; getter senses external input
    #   pin << 0 or 1    -> Signal.__lshift__ → sc.sig_connect(pin, value)
    #                        routes a constant signal to drive the pin;
    #                        equivalent to sc.sig_connect(pin, value)
    #   pin.reg_value    -> the underlying Register (bit 0 = value,
    #                        bit 1 = event); writable but bypasses the
    #                        signal-routing matrix
    #
    # Direction is implicit: a pin with no signal driving it is an input
    # (high-Z, .value getter senses external); a pin with sig_connect(pin, N)
    # is an output driven to N. There is no per-pin disconnect; the
    # nuclear option is sc.sig_disconnect_all() which is too broad.
    # ``set_d_input`` is therefore a no-op declaration in this lib version.
    # ------------------------------------------------------------------

    def _get_pin(self, idx: int) -> Any:
        pin = getattr(self._impl, f"d{idx}", None)
        if pin is None:
            raise ValueError(f"Scaffold has no pin d{idx}")
        return pin

    def set_d_output(self, idx: int) -> None:
        """Claim d<idx> as a push-pull output, driving low initially."""
        self._require_connected()
        self._impl.sig_connect(self._get_pin(idx), 0)

    def set_d_input(self, idx: int) -> None:
        """Declare d<idx> as an input.

        No-op on donjon-scaffold 0.9.5: a pin with no peripheral connected
        is already an input. Kept for symmetry with set_d_output and the
        existing host-script template.
        """
        self._require_connected()

    def write_d(self, idx: int, value: int) -> None:
        """Drive d<idx> low (0) or high (1)."""
        self._require_connected()
        self._impl.sig_connect(self._get_pin(idx), 1 if value else 0)

    def read_d(self, idx: int) -> int:
        """Sense the *instantaneous* logic level on d<idx>.

        For transient edges (a pin pulsed high for microseconds), an
        instantaneous read almost always misses them — use the latched
        edge-event API (``clear_d_event`` / ``read_d_event``) instead.
        """
        self._require_connected()
        return int(self._get_pin(idx).value)

    # ---- edge-event latches --------------------------------------------
    # donjon-scaffold 0.9.5 latches input edges in hardware: ``pin.event``
    # reads 1 once an edge was captured, and ``pin.clear_event()`` resets
    # the latch (writing 0 to the event register). This catches transients
    # that an instantaneous ``read_d`` would miss — the target asserts D2
    # high for only a few µs on a self-detected fault.

    def clear_d_event(self, idx: int) -> None:
        """Reset the edge latch on d<idx> before the verdict window opens."""
        self._require_connected()
        pin = self._get_pin(idx)
        if hasattr(pin, "clear_event"):
            pin.clear_event()
        else:  # pragma: no cover - 0.9.5 always has clear_event
            try:
                pin.event = 0
            except Exception as exc:
                LOGGER.debug("clear_d_event(%d) fallback failed: %s", idx, exc)

    def read_d_event(self, idx: int) -> bool:
        """True if an edge was latched on d<idx> since the last clear."""
        self._require_connected()
        return bool(getattr(self._get_pin(idx), "event", False))

    # ---- per-pin aliases matching the existing host-script template ----
    # (Newer templates should prefer set_d_output(idx) etc.)

    def set_d0_output(self) -> None:
        self.set_d_output(0)

    def set_d1_input(self) -> None:
        self.set_d_input(1)

    def set_d2_input(self) -> None:
        self.set_d_input(2)

    def set_d3_input(self) -> None:
        self.set_d_input(3)

    def set_d0(self, value: int) -> None:
        self.write_d(0, value)

    def read_d1(self) -> int:
        return self.read_d(1)

    def read_d2(self) -> int:
        return self.read_d(2)

    def read_d3(self) -> int:
        return self.read_d(3)

    # Edge-event aliases for the standard verdict pins (used by host scripts).
    def clear_d1_event(self) -> None:
        self.clear_d_event(1)

    def clear_d2_event(self) -> None:
        self.clear_d_event(2)

    def clear_d3_event(self) -> None:
        self.clear_d_event(3)

    def read_d1_event(self) -> bool:
        return self.read_d_event(1)

    def read_d2_event(self) -> bool:
        return self.read_d_event(2)

    def read_d3_event(self) -> bool:
        return self.read_d_event(3)

    @property
    def raw(self) -> Any:
        """Underlying ``donjon-scaffold`` Scaffold instance. Use sparingly."""
        self._require_connected()
        return self._impl
