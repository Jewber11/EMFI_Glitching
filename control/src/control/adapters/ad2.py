"""Digilent Analog Discovery 2 capture adapter.

The AD2 is used as a lightweight dashboard instrument:

* Scope CH1: ChipSHOUTER voltage monitor, rendered as the UI CH3 pulse trace.
* DIO0: ledger trigger/reference marker.
* DIO1: ledger-generated clock.
* DIO2/DIO3: optional target status/UART markers.

The adapter talks directly to Digilent's WaveForms runtime through ``ctypes`` so
Control does not need a Python package beyond the vendor ``libdwf`` runtime.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import threading
import time
from typing import Any, Dict, List, Optional

from control.adapters.base import BaseAdapter


_DWF_STATE_DONE = 2
_ACQMODE_SINGLE = 0
_FILTER_DECIMATE = 0
_TRIGSRC_NONE = 0
_TRIGSRC_DETECTOR_ANALOG_IN = 2
_TRIGSRC_ANALOG_IN = 4
_TRIGTYPE_EDGE = 0
_TRIGSLOPE_RISE = 0


class AD2Adapter(BaseAdapter):
    name = "ad2"

    def __init__(self) -> None:
        self._dwf: Any = None
        self._hdwf = ctypes.c_int(0)
        self._lock = threading.RLock()
        self._last_error: Optional[str] = None
        self._sample_rate_hz = 2_000_000.0
        self._digital_sample_rate_hz = 2_000_000.0
        self._samples = 8192
        self._analog_range_v = 50.0
        self._pulse_probe_ratio = 20.0
        self._available = False
        self._load_runtime()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def connected(self) -> bool:
        return bool(self._hdwf.value)

    def connect(self, port: Optional[str] = None) -> None:
        del port
        with self._lock:
            if not self._available or self._dwf is None:
                raise RuntimeError(self._last_error or "Digilent WaveForms runtime is not available")
            if self.connected:
                return
            hdwf = ctypes.c_int(0)
            ok = self._dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(hdwf))
            if not ok or not hdwf.value:
                self._last_error = self._error_message()
                raise RuntimeError(f"AD2 open failed: {self._last_error}")
            self._hdwf = hdwf
            self._last_error = None
            self._configure_instruments()

    def disconnect(self) -> None:
        with self._lock:
            if self._dwf is not None and self.connected:
                self._dwf.FDwfDeviceClose(self._hdwf)
            self._hdwf = ctypes.c_int(0)

    def configure(
        self,
        *,
        sample_rate_hz: Optional[float] = None,
        samples: Optional[int] = None,
        analog_range_v: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if sample_rate_hz is not None:
                if sample_rate_hz <= 0:
                    raise ValueError("sample_rate_hz must be positive")
                self._sample_rate_hz = float(sample_rate_hz)
            if samples is not None:
                if samples < 64 or samples > 8192:
                    raise ValueError("samples must be between 64 and 8192")
                self._samples = int(samples)
            if analog_range_v is not None:
                if analog_range_v <= 0:
                    raise ValueError("analog_range_v must be positive")
                self._analog_range_v = float(analog_range_v)
            if self.connected:
                self._configure_instruments()
            return self.status()

    def capture(self) -> Dict[str, Any]:
        with self._lock:
            if not self.connected:
                self.connect()

            assert self._dwf is not None
            count = int(self._samples)
            sample_rate = float(self._sample_rate_hz)
            started_at = time.time()

            analog = (ctypes.c_double * count)()
            digital = (ctypes.c_uint16 * count)()

            self._dwf.FDwfDigitalInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(True))
            self._dwf.FDwfAnalogInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(True))

            analog_status = ctypes.c_byte(0)
            digital_status = ctypes.c_byte(0)
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                self._dwf.FDwfAnalogInStatus(self._hdwf, ctypes.c_bool(True), ctypes.byref(analog_status))
                self._dwf.FDwfDigitalInStatus(self._hdwf, ctypes.c_bool(True), ctypes.byref(digital_status))
                if analog_status.value == 2 and digital_status.value == 2:
                    break
                time.sleep(0.002)

            self._dwf.FDwfAnalogInStatusData(self._hdwf, ctypes.c_int(0), analog, ctypes.c_int(count))
            self._dwf.FDwfDigitalInStatusData(
                self._hdwf,
                ctypes.cast(digital, ctypes.c_void_p),
                ctypes.c_int(count * ctypes.sizeof(ctypes.c_uint16)),
            )

            volts = [round(float(analog[i]), 5) for i in range(count)]
            words = [int(digital[i]) for i in range(count)]
            channels = {
                "pulse": {
                    "source": "ad2_scope_ch1",
                    "label": "ChipSHOUTER voltage monitor",
                    "unit": "V",
                    "probe_ratio": self._pulse_probe_ratio,
                    "scaled_unit": "V",
                    "scaled_label": "ChipSHOUTER monitor at probe tip x20",
                    "values": volts,
                },
                "trigger": {
                    "source": "ad2_dio0",
                    "label": "Ledger trigger/ref",
                    "values": self._bit_values(words, 0),
                },
                "clock": {
                    "source": "ad2_dio1",
                    "label": "Ledger clock",
                    "values": self._bit_values(words, 1),
                },
                "status0": {
                    "source": "ad2_dio2",
                    "label": "Optional DIO2 marker",
                    "values": self._bit_values(words, 2),
                },
                "status1": {
                    "source": "ad2_dio3",
                    "label": "Optional DIO3 marker",
                    "values": self._bit_values(words, 3),
                },
            }
            return {
                "name": self.name,
                "available": self.available,
                "connected": self.connected,
                "timestamp": started_at,
                "sample_rate_hz": sample_rate,
                "digital_sample_rate_hz": self._digital_sample_rate_hz,
                "samples": count,
                "duration_s": count / sample_rate,
                "analog_range_v": self._analog_range_v,
                "pulse_probe_ratio": self._pulse_probe_ratio,
                "mapping": {
                    "ui_ch3_pulse": "ad2_scope_ch1",
                    "ui_ch2_trigger": "ad2_dio0",
                    "ui_ch1_clock": "ad2_dio1",
                    "optional_status": ["ad2_dio2", "ad2_dio3"],
                },
                "channels": channels,
            }

    def capture_triggered(
        self,
        *,
        sample_rate_hz: float = 100_000_000.0,
        samples: int = 8192,
        analog_range_v: float = 50.0,
        trigger_level_v: float = 1.0,
        trigger_hysteresis_v: float = 0.1,
        timeout_s: float = 2.0,
    ) -> Dict[str, Any]:
        """Capture a high-speed window around a CH1 analog trigger.

        The trigger level is in raw AD2 volts. With the current 20:1 monitor
        probe, ``1.0`` means roughly 20 V at the ChipSHOUTER monitor point.
        """
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if samples < 64 or samples > 8192:
            raise ValueError("samples must be between 64 and 8192")
        if analog_range_v <= 0:
            raise ValueError("analog_range_v must be positive")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

        with self._lock:
            if not self.connected:
                self.connect()

            assert self._dwf is not None
            count = int(samples)
            started_at = time.time()
            old_config = (self._sample_rate_hz, self._samples, self._analog_range_v)
            analog = (ctypes.c_double * count)()
            digital = (ctypes.c_uint16 * count)()
            analog_status = ctypes.c_byte(0)
            digital_status = ctypes.c_byte(0)
            auto_triggered = ctypes.c_int(0)
            timed_out = False

            try:
                self._sample_rate_hz = float(sample_rate_hz)
                self._samples = count
                self._analog_range_v = float(analog_range_v)
                self._configure_triggered_instruments(
                    trigger_level_v=float(trigger_level_v),
                    trigger_hysteresis_v=float(trigger_hysteresis_v),
                )

                self._dwf.FDwfDigitalInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(False))
                self._dwf.FDwfAnalogInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(False))
                time.sleep(0.03)
                self._dwf.FDwfDigitalInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(True))
                self._dwf.FDwfAnalogInConfigure(self._hdwf, ctypes.c_bool(True), ctypes.c_bool(True))

                deadline = time.monotonic() + timeout_s
                while time.monotonic() < deadline:
                    self._dwf.FDwfAnalogInStatus(self._hdwf, ctypes.c_bool(True), ctypes.byref(analog_status))
                    self._dwf.FDwfDigitalInStatus(self._hdwf, ctypes.c_bool(True), ctypes.byref(digital_status))
                    if analog_status.value == _DWF_STATE_DONE:
                        break
                    time.sleep(0.001)
                else:
                    timed_out = True

                if hasattr(self._dwf, "FDwfAnalogInStatusAutoTriggered"):
                    self._dwf.FDwfAnalogInStatusAutoTriggered(self._hdwf, ctypes.byref(auto_triggered))

                self._dwf.FDwfAnalogInStatusData(self._hdwf, ctypes.c_int(0), analog, ctypes.c_int(count))
                self._dwf.FDwfDigitalInStatusData(
                    self._hdwf,
                    ctypes.cast(digital, ctypes.c_void_p),
                    ctypes.c_int(count * ctypes.sizeof(ctypes.c_uint16)),
                )
            finally:
                if self._dwf is not None and self.connected:
                    self._dwf.FDwfAnalogInTriggerSourceSet(self._hdwf, ctypes.c_int(_TRIGSRC_NONE))
                    self._dwf.FDwfDigitalInTriggerSourceSet(self._hdwf, ctypes.c_int(_TRIGSRC_NONE))
                self._sample_rate_hz, self._samples, self._analog_range_v = old_config
                if self._dwf is not None and self.connected:
                    self._configure_instruments()

            volts = [round(float(analog[i]), 5) for i in range(count)]
            words = [int(digital[i]) for i in range(count)]
            channels = {
                "pulse": {
                    "source": "ad2_scope_ch1",
                    "label": "ChipSHOUTER voltage monitor",
                    "unit": "V",
                    "probe_ratio": self._pulse_probe_ratio,
                    "scaled_unit": "V",
                    "scaled_label": "ChipSHOUTER monitor at probe tip x20",
                    "values": volts,
                },
                "trigger": {
                    "source": "ad2_dio0",
                    "label": "Ledger trigger/ref",
                    "values": self._bit_values(words, 0),
                },
                "clock": {
                    "source": "ad2_dio1",
                    "label": "Ledger clock",
                    "values": self._bit_values(words, 1),
                },
                "status0": {
                    "source": "ad2_dio2",
                    "label": "Optional DIO2 marker",
                    "values": self._bit_values(words, 2),
                },
                "status1": {
                    "source": "ad2_dio3",
                    "label": "Optional DIO3 marker",
                    "values": self._bit_values(words, 3),
                },
            }
            return {
                "name": self.name,
                "available": self.available,
                "connected": self.connected,
                "timestamp": started_at,
                "mode": "triggered",
                "triggered": not timed_out and not bool(auto_triggered.value),
                "timeout": timed_out,
                "auto_triggered": bool(auto_triggered.value),
                "analog_status": int(analog_status.value),
                "digital_status": int(digital_status.value),
                "trigger_source": "ad2_scope_ch1",
                "trigger_level_v": float(trigger_level_v),
                "trigger_hysteresis_v": float(trigger_hysteresis_v),
                "sample_rate_hz": float(sample_rate_hz),
                "digital_sample_rate_hz": self._digital_sample_rate_hz,
                "samples": count,
                "duration_s": count / float(sample_rate_hz),
                "analog_range_v": float(analog_range_v),
                "pulse_probe_ratio": self._pulse_probe_ratio,
                "mapping": {
                    "ui_ch3_pulse": "ad2_scope_ch1",
                    "ui_ch2_trigger": "ad2_dio0",
                    "ui_ch1_clock": "ad2_dio1",
                    "optional_status": ["ad2_dio2", "ad2_dio3"],
                },
                "channels": channels,
            }

    def status(self) -> Dict[str, Any]:
        status = super().status()
        status.update(
            {
                "available": self.available,
                "sample_rate_hz": self._sample_rate_hz,
                "digital_sample_rate_hz": self._digital_sample_rate_hz,
                "samples": self._samples,
                "analog_range_v": self._analog_range_v,
                "pulse_probe_ratio": self._pulse_probe_ratio,
                "mapping": {
                    "scope_ch1": "ChipSHOUTER voltage monitor",
                    "dio0": "ledger trigger/ref",
                    "dio1": "ledger clock",
                    "dio2": "optional marker/UART",
                    "dio3": "optional marker/UART",
                },
            }
        )
        return status

    def _load_runtime(self) -> None:
        path = ctypes.util.find_library("dwf")
        candidates = [path, "libdwf.so", "/usr/lib/libdwf.so", "/usr/lib/x86_64-linux-gnu/libdwf.so"]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                self._dwf = ctypes.cdll.LoadLibrary(candidate)
                self._set_prototypes()
                self._available = True
                self._last_error = None
                return
            except OSError as exc:
                self._last_error = str(exc)
        self._available = False
        if not self._last_error:
            self._last_error = "Digilent WaveForms runtime libdwf.so not found"

    def _set_prototypes(self) -> None:
        assert self._dwf is not None
        self._dwf.FDwfDeviceOpen.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self._dwf.FDwfDeviceOpen.restype = ctypes.c_int
        self._dwf.FDwfDeviceClose.argtypes = [ctypes.c_int]
        self._dwf.FDwfDeviceClose.restype = None
        self._dwf.FDwfGetLastErrorMsg.argtypes = [ctypes.c_char_p]
        self._dwf.FDwfGetLastErrorMsg.restype = None
        self._dwf.FDwfAnalogInChannelEnableSet.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_bool]
        self._dwf.FDwfAnalogInChannelRangeSet.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInChannelOffsetSet.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInChannelFilterSet.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInFrequencySet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInBufferSizeSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInAcquisitionModeSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInTriggerSourceSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInTriggerPositionSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInTriggerAutoTimeoutSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInTriggerHoldOffSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInTriggerTypeSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInTriggerChannelSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInTriggerFilterSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInTriggerLevelSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInTriggerHysteresisSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfAnalogInTriggerConditionSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfAnalogInConfigure.argtypes = [ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
        self._dwf.FDwfAnalogInStatus.argtypes = [ctypes.c_int, ctypes.c_bool, ctypes.POINTER(ctypes.c_byte)]
        self._dwf.FDwfAnalogInStatusAutoTriggered.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self._dwf.FDwfAnalogInStatusData.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
        ]
        self._dwf.FDwfDigitalInInternalClockInfo.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self._dwf.FDwfDigitalInDividerSet.argtypes = [ctypes.c_int, ctypes.c_uint]
        self._dwf.FDwfDigitalInBufferSizeSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfDigitalInSampleFormatSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfDigitalInAcquisitionModeSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfDigitalInTriggerSourceSet.argtypes = [ctypes.c_int, ctypes.c_int]
        self._dwf.FDwfDigitalInTriggerPositionSet.argtypes = [ctypes.c_int, ctypes.c_uint]
        self._dwf.FDwfDigitalInTriggerPrefillSet.argtypes = [ctypes.c_int, ctypes.c_uint]
        self._dwf.FDwfDigitalInTriggerAutoTimeoutSet.argtypes = [ctypes.c_int, ctypes.c_double]
        self._dwf.FDwfDigitalInConfigure.argtypes = [ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
        self._dwf.FDwfDigitalInStatus.argtypes = [ctypes.c_int, ctypes.c_bool, ctypes.POINTER(ctypes.c_byte)]
        self._dwf.FDwfDigitalInStatusData.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]

    def _configure_instruments(self) -> None:
        assert self._dwf is not None
        self._dwf.FDwfAnalogInChannelEnableSet(self._hdwf, ctypes.c_int(0), ctypes.c_bool(True))
        self._dwf.FDwfAnalogInChannelRangeSet(self._hdwf, ctypes.c_int(0), ctypes.c_double(self._analog_range_v))
        self._dwf.FDwfAnalogInFrequencySet(self._hdwf, ctypes.c_double(self._sample_rate_hz))
        self._dwf.FDwfAnalogInBufferSizeSet(self._hdwf, ctypes.c_int(self._samples))
        self._dwf.FDwfAnalogInAcquisitionModeSet(self._hdwf, ctypes.c_int(0))
        digital_clock_hz = ctypes.c_double(100_000_000.0)
        self._dwf.FDwfDigitalInInternalClockInfo(self._hdwf, ctypes.byref(digital_clock_hz))
        divider = max(1, int(round(digital_clock_hz.value / self._sample_rate_hz)))
        self._digital_sample_rate_hz = digital_clock_hz.value / divider
        self._dwf.FDwfDigitalInDividerSet(self._hdwf, ctypes.c_uint(divider))
        self._dwf.FDwfDigitalInBufferSizeSet(self._hdwf, ctypes.c_int(self._samples))
        self._dwf.FDwfDigitalInSampleFormatSet(self._hdwf, ctypes.c_int(16))
        self._dwf.FDwfDigitalInAcquisitionModeSet(self._hdwf, ctypes.c_int(0))

    def _configure_triggered_instruments(self, *, trigger_level_v: float, trigger_hysteresis_v: float) -> None:
        assert self._dwf is not None
        self._configure_instruments()
        self._dwf.FDwfAnalogInChannelOffsetSet(self._hdwf, ctypes.c_int(0), ctypes.c_double(0.0))
        self._dwf.FDwfAnalogInChannelFilterSet(self._hdwf, ctypes.c_int(0), ctypes.c_int(_FILTER_DECIMATE))
        self._dwf.FDwfAnalogInTriggerSourceSet(self._hdwf, ctypes.c_int(_TRIGSRC_DETECTOR_ANALOG_IN))
        self._dwf.FDwfAnalogInTriggerPositionSet(self._hdwf, ctypes.c_double(0.0))
        self._dwf.FDwfAnalogInTriggerAutoTimeoutSet(self._hdwf, ctypes.c_double(0.0))
        self._dwf.FDwfAnalogInTriggerHoldOffSet(self._hdwf, ctypes.c_double(0.0))
        self._dwf.FDwfAnalogInTriggerTypeSet(self._hdwf, ctypes.c_int(_TRIGTYPE_EDGE))
        self._dwf.FDwfAnalogInTriggerChannelSet(self._hdwf, ctypes.c_int(0))
        self._dwf.FDwfAnalogInTriggerFilterSet(self._hdwf, ctypes.c_int(_FILTER_DECIMATE))
        self._dwf.FDwfAnalogInTriggerLevelSet(self._hdwf, ctypes.c_double(trigger_level_v))
        self._dwf.FDwfAnalogInTriggerHysteresisSet(self._hdwf, ctypes.c_double(trigger_hysteresis_v))
        self._dwf.FDwfAnalogInTriggerConditionSet(self._hdwf, ctypes.c_int(_TRIGSLOPE_RISE))
        self._dwf.FDwfDigitalInTriggerSourceSet(self._hdwf, ctypes.c_int(_TRIGSRC_ANALOG_IN))
        self._dwf.FDwfDigitalInTriggerPositionSet(self._hdwf, ctypes.c_uint(self._samples // 2))
        self._dwf.FDwfDigitalInTriggerPrefillSet(self._hdwf, ctypes.c_uint(self._samples // 2))
        self._dwf.FDwfDigitalInTriggerAutoTimeoutSet(self._hdwf, ctypes.c_double(0.0))

    def _error_message(self) -> str:
        if self._dwf is None:
            return self._last_error or "libdwf.so not loaded"
        buf = ctypes.create_string_buffer(512)
        self._dwf.FDwfGetLastErrorMsg(buf)
        return buf.value.decode(errors="replace") or "unknown WaveForms error"

    @staticmethod
    def _bit_values(words: List[int], bit: int) -> List[int]:
        mask = 1 << bit
        return [1 if (word & mask) else 0 for word in words]
