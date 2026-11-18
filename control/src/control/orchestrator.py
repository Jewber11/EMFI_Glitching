"""Campaign engine: per-attempt sequencing + multi-dimensional sweep.

Ported from old-em-setup/glitchweb/backend/app/orchestrator.py and extended:

- XYZ grid sweep is augmented by delay_us × pulse_width_ns × voltage_v.
- Each campaign loads the per-project ``host/run.py`` script (or a default
  fallback) and calls ``setup(ctx)``, ``attempt(ctx)``, ``teardown(ctx)``.
- StopFlag is checked between every attempt for prompt cancellation.
- WS topics: position, attempt, counter, campaign_progress, error.
- ``replay(run_id)`` re-jogs and re-fires any historical attempt.

Sweep loop nesting (outermost → innermost):
    z → y (serpentine) → x → delay_us → pulse_width_ns → voltage_v
    → attempts_per_point

Host-script lookup: ``~/emfi-projects/{project_id}/host/run.py``
(Control and Develop are co-located on the lab box so a direct
filesystem read is simpler than HTTP).
"""

from __future__ import annotations

import asyncio
import json
import importlib.util
import logging
import math
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from control.logbook import Logbook
from control.safety import ArmGate, Disarmed, RateLimited, RateLimiter, StopFlag
from control.state import AppState
from control.workers import WorkerRegistry

LOGGER = logging.getLogger(__name__)

# Fixed A0 trigger high-time for hardware-trigger campaigns. Just long enough
# for the ChipSHOUTER's external-trigger input to register a rising edge; the
# actual glitch energy is set by the ChipSHOUTER's own pulse.width per attempt.
# Set once at campaign start; sanity-checked per attempt.
TRIGGER_WIDTH_NS = 500.0
TRIGGER_WIDTH_DRIFT_NS = 50.0  # warn if pgen0 width drifts beyond this


# --------------------------------------------------------------------------
# Host script support
# --------------------------------------------------------------------------

class ParamsView:
    """Dict that also supports attribute access for host_script convenience.

    Old host scripts that do ``ctx.params.delay_us`` → still work.
    Old host scripts that do ``ctx.params["delay_us"]`` → also still work.
    Old host scripts that do ``ctx.params.get("delay_us")`` → also still work.

    Missing keys return ``None`` in all three forms (forgiving by design —
    a host script written for one sweep dimension shouldn't crash when run
    on a campaign that doesn't use that dimension).

    Supports ``**params`` unpacking via ``keys()`` and ``__getitem__``.
    """

    __slots__ = ("_store",)

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        object.__setattr__(self, "_store", dict(data) if data else {})

    def __getattr__(self, key: str) -> Any:
        # Only invoked when regular lookup misses (i.e. not _store).
        return self._store.get(key)

    def __getitem__(self, key: str) -> Any:
        return self._store.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __iter__(self):
        return iter(self._store)

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def keys(self):
        return self._store.keys()

    def items(self):
        return self._store.items()

    def values(self):
        return self._store.values()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._store)


class HostScriptContext:
    """Small namespace passed to host script setup/attempt/teardown."""

    def __init__(
        self,
        scaffold: Any,
        shouter: Any,
        params: Any,
        logbook: Logbook,
        state: AppState,
    ) -> None:
        self.scaffold = scaffold
        self.target = scaffold  # legacy naming compat
        self.shouter = shouter
        # Accept either a plain dict (older callers) or a ParamsView. Either
        # way, wrap so host scripts get attribute access.
        self.params = params if isinstance(params, ParamsView) else ParamsView(params or {})
        self.logbook = logbook
        self.state = state


def _scaffold_host_script(scaffold: Any) -> Any:
    """Return a stand-in module with setup/attempt/teardown that does the
    standard D0/D1/D2/D3 verdict read via the Scaffold adapter."""

    class _Default:
        @staticmethod
        def setup(ctx: HostScriptContext) -> None:
            sc = ctx.scaffold
            sc.set_d_input(1)
            sc.set_d_input(2)
            sc.set_d_input(3)

        @staticmethod
        def attempt(ctx: HostScriptContext) -> Dict[str, Any]:
            # Clear the edge latches, open the verdict window, then read the
            # latched events. This catches transient pulses (D2 high for µs on
            # a self-detected fault, D3 falling edge at campaign end) that an
            # instantaneous read_d would miss.
            sc = ctx.scaffold
            sc.clear_d_event(1)
            sc.clear_d_event(2)
            sc.clear_d_event(3)
            timeout_s = float(ctx.params.get("verdict_timeout_s", 0.5))
            time.sleep(timeout_s)
            return {
                "fault": sc.read_d_event(2),
                "heartbeat_alive": sc.read_d_event(1),
                "campaign_complete": sc.read_d_event(3),
            }

        @staticmethod
        def teardown(ctx: HostScriptContext) -> None:
            return None

    return _Default()


def _default_host_script(scaffold: Any, settings: Optional[Dict[str, Any]] = None) -> Any:
    """Observe optional target UART; otherwise record an unobserved pulse."""
    options = settings or {}
    if not options.get("target_serial_port") and getattr(scaffold, "connected", False):
        return _scaffold_host_script(scaffold)

    class _Default:
        port = None

        def setup(self, ctx):
            if options.get("target_serial_port"):
                import serial
                self.port = serial.Serial(options["target_serial_port"], int(options.get("target_serial_baud", 115200)), timeout=0.05)

        def prepare(self, ctx):
            if self.port:
                self.port.reset_input_buffer()

        def attempt(self, ctx):
            if not self.port:
                return {"outcome": "unobserved"}
            deadline = time.monotonic() + float(ctx.params.get("verdict_timeout_s", 0.5))
            data = bytearray()
            while time.monotonic() < deadline:
                data.extend(self.port.read(max(1, self.port.in_waiting)))
            response = data.decode("utf-8", errors="replace")
            glitch = options.get("target_glitch_text") or "ESCAPED"
            normal = options.get("target_normal_text") or "normal"
            if glitch.lower() in response.lower():
                outcome = "glitch"
            elif not response:
                outcome = "hang"
            elif normal.lower() in response.lower():
                outcome = "nothing"
            else:
                outcome = "crash"
            return {"outcome": outcome, "response": response}

        def teardown(self, ctx):
            if self.port:
                self.port.close()
                self.port = None

    return _Default()


def _load_host_script(project_id: str) -> Tuple[Any, Optional[Path]]:
    """Load ~/emfi-projects/<project_id>/host/run.py if present.

    Returns (module-or-default, path). On any error, returns the default
    so the campaign can still run with built-in verdict logic.
    """
    path = _projects_root() / project_id / "host" / "run.py"
    if not path.exists():
        LOGGER.info("No host/run.py at %s; using built-in default", path)
        return None, None
    try:
        spec = importlib.util.spec_from_file_location(f"host_run_{project_id}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not build spec for {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for fn in ("setup", "attempt", "teardown"):
            if not hasattr(mod, fn):
                LOGGER.warning(
                    "Host script %s missing %s(); falling back to default", path, fn
                )
                return None, path
        LOGGER.info("Loaded host script from %s", path)
        return mod, path
    except Exception:
        LOGGER.exception("Failed to load host script at %s; using default", path)
        return None, path


def _projects_root() -> Path:
    return Path(os.environ.get("EMFI_PROJECTS_ROOT") or (Path.home() / "emfi-projects"))


def _project_dir(project_id: str) -> Path:
    return _projects_root() / project_id


def _load_target_record(project_id: str, target_pc: Optional[int]) -> Optional[Dict[str, Any]]:
    if target_pc is None:
        return None
    path = _project_dir(project_id) / "targets.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        LOGGER.exception("Could not read target metadata from %s", path)
        return None

    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        try:
            start = int(record.get("pc_address"))
            end = int(record.get("pc_end") or start)
        except (TypeError, ValueError):
            continue
        if start <= int(target_pc) <= end:
            return record
    return None


def _load_cpu_mhz(project_id: str, build_sha: Optional[str]) -> float:
    if not build_sha:
        return 32.0
    path = _project_dir(project_id) / "builds" / build_sha / "disassembly.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 32.0
    except Exception:
        LOGGER.exception("Could not read disassembly metadata from %s", path)
        return 32.0
    try:
        cpu_mhz = float(data.get("cpu_mhz") or 32.0)
    except (TypeError, ValueError):
        return 32.0
    return cpu_mhz if cpu_mhz > 0 else 32.0


def materialize_target_delay_sweep(
    project_id: str,
    build_sha: Optional[str],
    target_pc: Optional[int],
    sweep: Any,
) -> Tuple[Any, Optional[str]]:
    """Fill sweep.delay_us from GlitchTarget delay metadata when omitted."""
    existing_delay = sweep.get("delay_us") if isinstance(sweep, dict) else getattr(sweep, "delay_us", None)
    if existing_delay is not None:
        return sweep, None

    target = _load_target_record(project_id, target_pc)
    if target is None:
        return sweep, None

    start_cycles = target.get("expected_delay_cycles")
    if start_cycles is None:
        return sweep, None
    end_cycles = target.get("expected_delay_cycles_end")
    if end_cycles is None:
        end_cycles = start_cycles

    try:
        start_cycles_f = float(start_cycles)
        end_cycles_f = float(end_cycles)
    except (TypeError, ValueError):
        return sweep, None

    cpu_mhz = _load_cpu_mhz(project_id, build_sha)
    start_us = start_cycles_f / cpu_mhz
    stop_us = end_cycles_f / cpu_mhz
    delay_range = {
        "start": min(start_us, stop_us),
        "stop": max(start_us, stop_us),
        "step": 1.0 / cpu_mhz,
    }

    if isinstance(sweep, dict):
        materialized = dict(sweep)
        materialized["delay_us"] = delay_range
    else:
        materialized = sweep.model_copy(update={"delay_us": delay_range})

    name = target.get("name") or (f"0x{int(target_pc):x}" if target_pc is not None else "target")
    return materialized, (
        f"delay_us materialized from target {name!r} "
        f"({start_cycles_f:g}-{end_cycles_f:g} cycles at {cpu_mhz:g} MHz)"
    )


# --------------------------------------------------------------------------
# Sweep iteration
# --------------------------------------------------------------------------

def _sweep_range_values(rng: Any) -> List[float]:
    """Yield inclusive [start, stop] stepped by ``step``. None → [None]."""
    if rng is None:
        return [None]  # type: ignore[list-item]
    start = float(rng["start"]) if isinstance(rng, dict) else float(rng.start)
    stop = float(rng["stop"]) if isinstance(rng, dict) else float(rng.stop)
    step = float(rng["step"]) if isinstance(rng, dict) else float(rng.step)
    if step <= 0:
        return [start]
    n = int(math.floor((stop - start) / step + 1e-9)) + 1
    return [start + i * step for i in range(max(1, n))]


def _grid_points(grid: Any) -> Iterator[Tuple[float, float, float, int, int, int]]:
    """Yield (x, y, z, x_idx, y_idx, z_idx) in z → y (serpentine) → x order."""
    if isinstance(grid, dict):
        origin = grid["origin"]
        top_right = grid["top_right"]
        step = float(grid["step_size_mm"])
        z_min = float(grid["z_min_mm"])
        z_max = float(grid["z_max_mm"])
        z_step = float(grid["z_step_mm"])
    else:
        origin = grid.origin
        top_right = grid.top_right
        step = float(grid.step_size_mm)
        z_min = float(grid.z_min_mm)
        z_max = float(grid.z_max_mm)
        z_step = float(grid.z_step_mm)

    ox, oy = float(origin[0]), float(origin[1])
    tx, ty = float(top_right[0]), float(top_right[1])

    x_steps = max(1, int(math.floor(abs(tx - ox) / step + 1e-9)) + 1) if step > 0 else 1
    y_steps = max(1, int(math.floor(abs(ty - oy) / step + 1e-9)) + 1) if step > 0 else 1
    z_steps = max(1, int(math.floor((z_max - z_min) / z_step + 1e-9)) + 1) if z_step > 0 else 1
    x_step = step if tx >= ox else -step
    y_step = step if ty >= oy else -step

    for zi in range(z_steps):
        z = z_min + zi * z_step
        for yi in range(y_steps):
            y = oy + yi * y_step
            x_range = range(x_steps) if yi % 2 == 0 else range(x_steps - 1, -1, -1)
            for xi in x_range:
                x = ox + xi * x_step
                yield (x, y, z, xi, yi, zi)


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

class Orchestrator:
    def __init__(
        self,
        state: AppState,
        arm_gate: ArmGate,
        stop_flag: StopFlag,
        rate_limiter: RateLimiter,
        logbook: Logbook,
        shover: Any,
        shouter: Any,
        scaffold: Any,
        broadcast: Callable[[str, Dict[str, Any]], None],
        workers: Optional[WorkerRegistry] = None,
    ) -> None:
        self.state = state
        self.arm_gate = arm_gate
        self.stop_flag = stop_flag
        self.rate_limiter = rate_limiter
        self.logbook = logbook
        self.shover = shover
        self.shouter = shouter
        self.scaffold = scaffold
        self.broadcast = broadcast
        self.workers = workers
        self._task: Optional[asyncio.Task] = None
        self._task_lock = asyncio.Lock()

    def _worker(self, name: str) -> Any:
        if self.workers is None:
            raise RuntimeError("Orchestrator has no WorkerRegistry; wire it in deps.py")
        return self.workers.get(name)

    async def _safe_disarm(self) -> None:
        """Best-effort ChipSHOUTER disarm; never raises. Used on abort paths."""
        if self.shouter.connected:
            try:
                await self._worker("chipshouter").call(self.shouter.disarm_safe)
            except Exception:
                pass

    # ---- one attempt -----------------------------------------------------

    async def perform_attempt(
        self,
        verdict_timeout_s: float,
        pulse_params: Dict[str, Any],
        host_script: Any,
        host_ctx: HostScriptContext,
        campaign_id: Optional[str] = None,
        project_id: Optional[str] = None,
        project_version: Optional[str] = None,
        build_sha: Optional[str] = None,
        target_pc: Optional[int] = None,
        trigger_mode: str = "software",
        shouter_auto_arm: bool = True,
    ) -> Dict[str, Any]:
        """Single glitch attempt at the current position.

        Carry-forward from old orchestrator.perform_attempt (lines 49-137)
        with host_script integration replacing the inline verdict logic.
        """
        self.arm_gate.require_armed()
        while True:
            if self.stop_flag.is_set():
                raise Disarmed("Campaign stopped")
            try:
                self.rate_limiter.acquire()
                break
            except RateLimited:
                await asyncio.sleep(0.1)
                self.arm_gate.require_armed()

        t0 = time.monotonic()

        shouter_worker = self._worker("chipshouter")
        scaffold_worker = self._worker("scaffold")

        # In auto-arm mode, ensure shouter is armed (idempotent).
        if shouter_auto_arm and self.shouter.connected:
            try:
                await shouter_worker.call(self.shouter.arm, clear_faults=False)
            except Exception as exc:
                LOGGER.warning("shouter arm during attempt failed: %s", exc)

        # Prep scaffold for the next verdict (clear edge latches).
        if self.scaffold.connected:
            try:
                await scaffold_worker.call(self.scaffold.arm_attempt)
            except Exception as exc:
                LOGGER.debug("scaffold arm_attempt: %s", exc)

        # Per-attempt pulse programming.
        #
        # The sweep's pulse_width_ns is the EMFI HV pulse width → it goes to
        # the ChipSHOUTER (set every attempt, even when not sweeping width, to
        # catch any mid-campaign drift). The Scaffold pgen0 only provides the
        # A0 trigger: its delay is the per-attempt glitch delay; its width is a
        # fixed trigger constant set once at campaign start (sanity-checked
        # below, never reprogrammed here).
        shouter_pw_actual: Optional[int] = None
        shouter_pw = pulse_params.get("pulse_width_ns") or pulse_params.get("shouter_pulse_width_ns")
        shouter_pw = 1000 if shouter_pw is None else int(shouter_pw)
        if self.shouter.connected:
            try:
                shouter_pw_actual = await shouter_worker.call(
                    self.shouter.set_pulse_width, shouter_pw)
            except Exception as exc:
                raise RuntimeError(f"FaultyCat pulse width set failed: {exc}") from exc

        if trigger_mode in ("one-shot", "free-run") and self.scaffold.connected:
            delay_us = pulse_params.get("delay_us")
            delay_us = 1.0 if delay_us is None else float(delay_us)
            try:
                await scaffold_worker.call(self.scaffold.set_pulse_delay_us, delay_us)
                # Cheap sanity check: the trigger width should still be the
                # campaign-start constant. Only log if it drifted.
                pgen_w = await scaffold_worker.call(self.scaffold.get_pulse_width_ns)
                if abs(pgen_w - TRIGGER_WIDTH_NS) > TRIGGER_WIDTH_DRIFT_NS:
                    LOGGER.warning("pgen0 trigger width drifted: %.1f ns", pgen_w)
            except Exception as exc:
                LOGGER.warning("pgen delay set / width check failed: %s", exc)

        host_ctx.params = ParamsView({**host_ctx.params.to_dict(), "verdict_timeout_s": verdict_timeout_s, "trigger_mode": trigger_mode, **pulse_params})
        if hasattr(host_script, "prepare"):
            await scaffold_worker.call(host_script.prepare, host_ctx)
        await asyncio.sleep(0.02)

        # Fire the pulse (software trigger) or rely on hardware A0 trigger.
        if trigger_mode == "software":
            if not self.shouter.connected:
                raise RuntimeError(
                    "software trigger mode needs FaultyCat connected"
                )
            await shouter_worker.call(self.shouter.pulse)
        # one-shot / free-run: A0 fires from Scaffold; no USB call here.

        # Host script reads the verdict (default: scaffold.wait_verdict).
        host_ctx.params = ParamsView({
            **host_ctx.params.to_dict(),
            "verdict_timeout_s": verdict_timeout_s,
            "trigger_mode": trigger_mode,
            **pulse_params,
        })
        verdict: Dict[str, Any] = {
            "fault": False, "heartbeat_alive": False, "campaign_complete": False,
        }
        attempt_error: Optional[str] = None
        try:
            mod = host_script
            if hasattr(mod, "attempt"):
                # Run host_script.attempt on the scaffold worker thread to
                # serialize with other Scaffold IO.
                verdict = await scaffold_worker.call(mod.attempt, host_ctx) or verdict
        except Exception as exc:
            attempt_error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            LOGGER.exception("Host script attempt() failed")

        # Read shouter state for crash classification (tolerant of unplugged).
        state_str = ""
        active_faults: List[Any] = []
        if self.shouter.connected:
            try:
                state_str = await shouter_worker.call(self.shouter.get_state)
                active_faults = await shouter_worker.call(self.shouter.get_fault_active)
            except Exception as exc:
                LOGGER.debug("could not read shouter state: %s", exc)

        crashed = (str(state_str).lower() == "fault") or bool(active_faults)
        fault_detected = bool(verdict.get("fault"))
        hung = not bool(verdict.get("heartbeat_alive"))

        if attempt_error is not None:
            outcome = "crash"
        elif verdict.get("outcome") in ("glitch", "hang", "crash", "nothing", "unobserved"):
            outcome = verdict["outcome"]
        elif fault_detected:
            outcome = "glitch"
        elif hung:
            outcome = "hang"
        elif crashed:
            outcome = "crash"
        else:
            outcome = "nothing"

        if verdict.get("campaign_complete"):
            self.state.counters.campaigns += 1

        self.state.counters.record(outcome)

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        entry = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "campaign_id": campaign_id,
            "x": self.state.position_logical[0],
            "y": self.state.position_logical[1],
            "z": self.state.position_logical[2],
            "machine_x": self.state.position_machine[0],
            "machine_y": self.state.position_machine[1],
            "machine_z": self.state.position_machine[2],
            "trigger_mode": trigger_mode,
            "glitch_delay_us": pulse_params.get("delay_us") or pulse_params.get("glitch_delay_us"),
            "pulse_width_ns": pulse_params.get("pulse_width_ns"),
            "shouter_voltage": pulse_params.get("voltage_v") or pulse_params.get("shouter_voltage"),
            "shouter_pulse_width_ns": shouter_pw,
            "shouter_pulse_width_ns_actual": shouter_pw_actual,
            "outcome": outcome,
            "verdict": verdict,
            "shouter_state": str(state_str) if state_str else None,
            "elapsed_ms": elapsed_ms,
            "project_id": project_id,
            "project_version": project_version,
            "build_sha": build_sha,
            "target_pc": target_pc,
        }
        if attempt_error:
            entry["error"] = attempt_error
        stored = self.logbook.append(entry)

        # Broadcast attempt + counter snapshot.
        self.broadcast("attempt", stored)
        self.broadcast("counter", {
            "attempts": self.state.counters.attempts,
            "glitches": self.state.counters.glitches,
            "hangs": self.state.counters.hangs,
            "crashes": self.state.counters.crashes,
            "nothings": self.state.counters.nothings,
            "unobserved": self.state.counters.unobserved,
            "campaigns": self.state.counters.campaigns,
        })

        if outcome == "hang" and self.scaffold.connected:
            try:
                await scaffold_worker.call(self.scaffold.dut_power_cycle)
            except Exception as exc:
                LOGGER.warning("DUT power cycle on hang failed: %s", exc)

        return {"outcome": outcome, "entry": stored}

    # ---- campaign --------------------------------------------------------

    async def run_campaign(
        self,
        campaign: Any,
        status: Any = None,
    ) -> Dict[str, Any]:
        """Run a full campaign.

        ``campaign`` is the Campaign Pydantic model; ``status`` is the
        CampaignStatus to update in-place (optional).
        """
        # Accept either Pydantic model or dict.
        if isinstance(campaign, dict):
            c = campaign
        else:
            c = campaign.model_dump()

        campaign_id = c.get("id") or str(uuid.uuid4())
        project_id = c["project_id"]
        project_version = c.get("project_version")
        build_sha = c.get("build_sha")
        target_pc = c.get("target_pc")
        trigger_mode = c.get("trigger_mode", "software")
        auto_arm = bool(c.get("shouter_auto_arm", True))
        verdict_timeout_s = float(c.get("verdict_timeout_ms", 500)) / 1000.0
        stop_conditions = c.get("stop_conditions") or {}
        max_glitches = c.get("max_glitches")
        if max_glitches is None:
            max_glitches = stop_conditions.get("max_glitches")
        max_glitches = int(max_glitches) if max_glitches is not None else None
        stop_on_first_crash = bool(
            c.get("stop_on_first_crash", False)
            or stop_conditions.get("stop_on_first_crash", False)
        )
        max_runtime_seconds = c.get("max_runtime_seconds")
        if max_runtime_seconds is None:
            max_runtime_seconds = stop_conditions.get("max_runtime_seconds")
        max_runtime_seconds = (
            float(max_runtime_seconds) if max_runtime_seconds is not None else None
        )

        grid = c["grid"]
        sweep, sweep_note = materialize_target_delay_sweep(
            project_id, build_sha, target_pc, c["sweep"]
        )
        if sweep_note:
            LOGGER.info("Campaign %s %s", campaign_id, sweep_note)

        delays = _sweep_range_values(sweep.get("delay_us"))
        widths = _sweep_range_values(sweep.get("pulse_width_ns"))
        voltages = _sweep_range_values(sweep.get("voltage_v"))
        attempts_per_point = int(sweep.get("attempts_per_point", 1))

        grid_pts = list(_grid_points(grid))
        sweep_combinations = len(delays) * len(widths) * len(voltages)
        total = len(grid_pts) * sweep_combinations * attempts_per_point
        LOGGER.info(
            "Campaign %s starting: %d grid pts × %d sweep × %d attempts = %d total",
            campaign_id, len(grid_pts), sweep_combinations, attempts_per_point, total,
        )

        if status is not None:
            status.total_attempts = total

        host_mod, host_path = _load_host_script(project_id)
        if host_mod is None:
            host_mod = _default_host_script(self.scaffold, c)
            LOGGER.info("Using default host script (no per-project run.py)")

        host_ctx = HostScriptContext(
            scaffold=self.scaffold,
            shouter=self.shouter,
            params={},
            logbook=self.logbook,
            state=self.state,
        )

        scaffold_worker = self._worker("scaffold")
        shouter_worker = self._worker("chipshouter")
        shover_worker = self._worker("chipshover")

        self.stop_flag.clear()
        self.state.scan.active = True
        self.state.scan.completed = 0
        self.state.scan.total = total

        # --- Preparation phase (abort-on-failure with manual cleanup) ---

        # 1. Auto-arm + configure ChipSHOUTER (USB; independent of the Scaffold
        #    signal matrix). Non-fatal: a hardware-arm hiccup is logged but the
        #    campaign proceeds (the software ARM gate still guards every pulse).
        if auto_arm and self.shouter.connected:
            try:
                await shouter_worker.call(
                    self.shouter.configure,
                    voltage=int(c.get("shouter_voltage", 250)),
                    pulse_width_ns=int(c.get("shouter_pulse_width_ns", 1000)),
                    pulse_repeat=1,
                    pulse_deadtime_ms=10,
                    arm_timeout_min=1,
                    mute=bool(c.get("shouter_mute", True)),
                )
                if trigger_mode in ("one-shot", "free-run"):
                    await shouter_worker.call(
                        self.shouter.configure_hardware_trigger,
                        active_high=True,
                        termination_50r=True,
                    )
                await shouter_worker.call(self.shouter.arm, clear_faults=True)
            except Exception as exc:
                LOGGER.exception("Auto-arm failed")
                self.broadcast("error", {
                    "campaign_id": campaign_id,
                    "detail": f"Auto-arm failed: {exc}",
                })
                await self._safe_disarm()
                self.state.scan.active = False
                raise RuntimeError(f"FaultyCat setup failed: {exc}") from exc

        # 2. Configure the A0 trigger path. For hardware modes this wires
        #    d0 → pgen0 → a0. The user explicitly chose hardware triggering, so
        #    a wiring failure ABORTS the campaign — no silent software degrade.
        #    Runs after auto-arm and before host setup: set_trigger_mode calls
        #    sig_disconnect_all, which must precede any host-script pin setup.
        if self.scaffold.connected:
            try:
                await scaffold_worker.call(self.scaffold.set_trigger_mode, trigger_mode)
            except Exception as exc:
                LOGGER.error("Hardware trigger wiring failed: %s", exc)
                self.broadcast("error", {
                    "campaign_id": campaign_id,
                    "detail": f"hardware trigger wiring failed: {exc}",
                })
                self.broadcast("campaign_progress", {
                    "campaign_id": campaign_id,
                    "phase": "failed",
                    "completed_attempts": 0,
                    "total_attempts": total,
                    "current_xyz": None,
                    "current_sweep": None,
                })
                await self._safe_disarm()
                self.state.scan.active = False
                return {"ok": False, "reason": f"trigger wiring failed: {exc}"}

            # Hardware modes: fix the A0 trigger high-time once. The sweep's
            # pulse_width_ns drives the ChipSHOUTER HV pulse (per attempt),
            # NOT this trigger width.
            if trigger_mode in ("one-shot", "free-run"):
                try:
                    await scaffold_worker.call(
                        self.scaffold.set_pulse_width_ns, TRIGGER_WIDTH_NS)
                    LOGGER.info("pgen0 trigger width fixed at %.0f ns", TRIGGER_WIDTH_NS)
                except Exception as exc:
                    LOGGER.warning("could not set pgen0 trigger width: %s", exc)

        # 3. Host script setup. Failure here aborts the whole campaign.
        try:
            host_mod.setup(host_ctx)
        except Exception as exc:
            LOGGER.exception("Host script setup() failed")
            self.broadcast("error", {
                "campaign_id": campaign_id,
                "detail": f"Host script setup failed: {exc}",
            })
            self.broadcast("campaign_progress", {
                "campaign_id": campaign_id,
                "phase": "failed",
                "completed_attempts": 0,
                "total_attempts": total,
                "current_xyz": None,
                "current_sweep": None,
            })
            # Defensive: ensure shouter is safely disarmed even if setup
            # ran far enough to leave it armed.
            await self._safe_disarm()
            self.state.scan.active = False
            return {"ok": False, "reason": f"setup failed: {exc}"}

        # --- Run phase (cleanup guaranteed via finally) ---
        self.broadcast("campaign_progress", {
            "campaign_id": campaign_id,
            "phase": "started",
            "completed_attempts": 0,
            "total_attempts": total,
            "current_xyz": None,
            "current_sweep": None,
        })

        completed = 0
        campaign_glitches = 0
        host_script_errors = 0
        stop_reason: Optional[str] = None
        run_started_at = time.monotonic()

        def request_policy_stop(reason: str) -> None:
            nonlocal stop_reason
            if stop_reason is None:
                stop_reason = reason
                LOGGER.info("Campaign %s stop policy reached: %s", campaign_id, reason)
            self.stop_flag.set()

        def runtime_limit_reached() -> bool:
            if max_runtime_seconds is None:
                return False
            if time.monotonic() - run_started_at < max_runtime_seconds:
                return False
            request_policy_stop(
                f"max_runtime_seconds reached ({max_runtime_seconds:g}s)"
            )
            return True

        try:
            for (x, y, z, xi, yi, zi) in grid_pts:
                if self.stop_flag.is_set():
                    LOGGER.info("Campaign %s stop_flag set; breaking grid loop", campaign_id)
                    break

                # Move to grid point.
                try:
                    await shover_worker.call(self.shover.move_absolute_logical, x, y, z)
                    machine = await shover_worker.call(self.shover.get_position)
                    self.state.position_machine = machine
                    self.state.position_logical = self.shover.machine_to_logical(*machine) if hasattr(self.shover, "machine_to_logical") else (x, y, z)
                    self.state.scan.current_xyz = (x, y, z)
                    self.broadcast("position", {
                        "x": x, "y": y, "z": z,
                        "machine_x": self.state.position_machine[0],
                        "machine_y": self.state.position_machine[1],
                        "machine_z": self.state.position_machine[2],
                    })
                except Exception as exc:
                    LOGGER.exception("Move to (%.3f, %.3f, %.3f) failed", x, y, z)
                    self.broadcast("error", {
                        "campaign_id": campaign_id,
                        "detail": f"Move failed at ({x:.3f}, {y:.3f}, {z:.3f}): {exc}",
                    })
                    self.stop_flag.set()
                    break

                for delay_us in delays:
                    if self.stop_flag.is_set():
                        break
                    for width_ns in widths:
                        if self.stop_flag.is_set():
                            break
                        for voltage_v in voltages:
                            if self.stop_flag.is_set():
                                break

                            # Apply voltage to ChipSHOUTER if it varies.
                            if voltage_v is not None and self.shouter.connected:
                                try:
                                    await shouter_worker.call(
                                        self.shouter.configure,
                                        voltage=int(voltage_v),
                                        pulse_width_ns=int(width_ns or c.get("shouter_pulse_width_ns", 1000)),
                                    )
                                except Exception as exc:
                                    LOGGER.warning("Voltage set failed: %s", exc)

                            pulse_params = {
                                "delay_us": delay_us,
                                "pulse_width_ns": width_ns,
                                "voltage_v": voltage_v,
                                "shouter_voltage": voltage_v or c.get("shouter_voltage"),
                                "shouter_pulse_width_ns": c.get("shouter_pulse_width_ns"),
                            }

                            for _ in range(attempts_per_point):
                                if self.stop_flag.is_set():
                                    break
                                if runtime_limit_reached():
                                    break
                                try:
                                    res = await self.perform_attempt(
                                        verdict_timeout_s=verdict_timeout_s,
                                        pulse_params=pulse_params,
                                        host_script=host_mod,
                                        host_ctx=host_ctx,
                                        campaign_id=campaign_id,
                                        project_id=project_id,
                                        project_version=project_version,
                                        build_sha=build_sha,
                                        target_pc=target_pc,
                                        trigger_mode=trigger_mode,
                                        shouter_auto_arm=auto_arm,
                                    )
                                    completed += 1
                                    # Defensive: track host-script errors
                                    # separately from real shouter faults so
                                    # we can refuse to report 100%-error
                                    # campaigns as "completed".
                                    if res.get("entry", {}).get("error"):
                                        host_script_errors += 1
                                    outcome = res.get("outcome")
                                    if outcome == "glitch":
                                        campaign_glitches += 1
                                    self.state.scan.completed = completed
                                    if status is not None:
                                        status.completed_attempts = completed
                                    # Periodic campaign_progress (every attempt
                                    # is cheap — broadcast batches drop oldest).
                                    self.broadcast("campaign_progress", {
                                        "campaign_id": campaign_id,
                                        "phase": "running",
                                        "completed_attempts": completed,
                                        "total_attempts": total,
                                        "current_xyz": [x, y, z],
                                        "current_sweep": {
                                            "delay_us": delay_us,
                                            "pulse_width_ns": width_ns,
                                            "voltage_v": voltage_v,
                                        },
                                    })
                                    if (
                                        max_glitches is not None
                                        and campaign_glitches >= max_glitches
                                    ):
                                        request_policy_stop(
                                            f"max_glitches reached ({campaign_glitches}/{max_glitches})"
                                        )
                                        break
                                    if stop_on_first_crash and outcome == "crash":
                                        request_policy_stop("stop_on_first_crash reached")
                                        break
                                except Disarmed as exc:
                                    LOGGER.warning("Campaign %s disarmed: %s", campaign_id, exc)
                                    self.broadcast("error", {
                                        "campaign_id": campaign_id,
                                        "detail": f"Disarmed mid-campaign: {exc}",
                                    })
                                    self.stop_flag.set()
                                    break
                                except RateLimited as exc:
                                    LOGGER.warning("Rate limited: %s — sleeping 200ms", exc)
                                    await asyncio.sleep(0.2)
                                except Exception as exc:
                                    LOGGER.exception("Attempt failed; stopping campaign")
                                    self.stop_flag.set()
                                    self.broadcast("error", {
                                        "campaign_id": campaign_id,
                                        "detail": f"Attempt error: {exc}",
                                    })
        finally:
            self.state.scan.active = False

            # Host script teardown — log but don't propagate.
            try:
                host_mod.teardown(host_ctx)
            except Exception as exc:
                LOGGER.warning("Host script teardown() failed: %s", exc)

            if auto_arm and self.shouter.connected:
                try:
                    await shouter_worker.call(self.shouter.disarm_safe)
                except Exception:
                    pass

            if self.stop_flag.is_set():
                phase = "stopped"
                reason = stop_reason
            elif completed > 0 and host_script_errors == completed:
                phase = "failed"
                reason = (
                    f"every host_script.attempt() raised "
                    f"({host_script_errors}/{completed}) — check host/run.py"
                )
            else:
                phase = "completed"
                reason = None
            payload: Dict[str, Any] = {
                "campaign_id": campaign_id,
                "phase": phase,
                "completed_attempts": completed,
                "total_attempts": total,
                "current_xyz": None,
                "current_sweep": None,
            }
            if reason:
                payload["reason"] = reason
            self.broadcast("campaign_progress", payload)
            LOGGER.info(
                "Campaign %s %s: %d / %d attempts%s",
                campaign_id, phase, completed, total,
                f" — {reason}" if reason else "",
            )

        return {"ok": True, "completed": completed, "total": total, "campaign_id": campaign_id}

    # ---- replay ----------------------------------------------------------

    async def replay(self, run_id: str) -> Dict[str, Any]:
        """Re-execute the attempt identified by ``run_id``.

        Fetches the AttemptResult from the logbook, jogs the stage to its
        (x, y, z) position, and re-fires the same pulse parameters.
        """
        entry = self.logbook.get(run_id)
        if entry is None:
            raise RuntimeError(f"Run {run_id} not found in logbook")

        x, y, z = entry.get("x", 0.0), entry.get("y", 0.0), entry.get("z", 0.0)
        trigger_mode = entry.get("trigger_mode", "software")
        project_id = entry.get("project_id") or "_replay"

        host_mod, _ = _load_host_script(project_id) if project_id != "_replay" else (None, None)
        if host_mod is None:
            host_mod = _default_host_script(self.scaffold)

        host_ctx = HostScriptContext(
            scaffold=self.scaffold,
            shouter=self.shouter,
            params={},
            logbook=self.logbook,
            state=self.state,
        )

        shover_worker = self._worker("chipshover")

        # Jog to position.
        try:
            await shover_worker.call(self.shover.move_absolute_logical, x, y, z)
            self.state.position_logical = (x, y, z)
            self.broadcast("position", {
                "x": x, "y": y, "z": z,
                "machine_x": self.state.position_machine[0],
                "machine_y": self.state.position_machine[1],
                "machine_z": self.state.position_machine[2],
            })
        except Exception as exc:
            raise RuntimeError(f"Replay jog to ({x}, {y}, {z}) failed: {exc}")

        pulse_params = {
            "delay_us": entry.get("glitch_delay_us"),
            "pulse_width_ns": entry.get("pulse_width_ns"),
            "voltage_v": entry.get("shouter_voltage"),
            "shouter_voltage": entry.get("shouter_voltage"),
            "shouter_pulse_width_ns": entry.get("shouter_pulse_width_ns"),
        }

        result = await self.perform_attempt(
            verdict_timeout_s=0.5,
            pulse_params=pulse_params,
            host_script=host_mod,
            host_ctx=host_ctx,
            campaign_id=None,
            project_id=entry.get("project_id"),
            project_version=entry.get("project_version"),
            build_sha=entry.get("build_sha"),
            target_pc=entry.get("target_pc"),
            trigger_mode=trigger_mode,
            shouter_auto_arm=False,  # replay is single-shot; caller arms
        )
        return result["entry"]
