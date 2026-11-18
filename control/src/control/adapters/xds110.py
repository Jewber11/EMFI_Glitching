"""XDS110 programmer / debugger adapter.

Two backends, both subprocess-based:

1. **TI dslite / UniFlash CLI** — fast, headless flashing. Used by
   ``flash()`` for the build -> flash -> campaign loop. Path configured via
   ``config.programmer.dslite_bin`` or env ``DSLITE_BIN``.

2. **OpenOCD** — interactive debugging. Used by ``attach_debugger()`` to
   spin up an OpenOCD daemon on configurable gdb/telnet ports for
   combined SW + HW attack analysis. Path via ``config.programmer.openocd_bin``
   or env ``OPENOCD_BIN``.

Neither backend uses pyserial — both are subprocess wrappers, so they
do NOT need to live behind a DeviceWorker; instead, isolate per-process
state on the adapter instance and serialize at the router layer.
"""

from __future__ import annotations

import glob
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from control.adapters.base import BaseAdapter

LOGGER = logging.getLogger(__name__)

_CCXML_HINT = (
    "No MSPM0L2228 ccxml found. Generate one via UniFlash GUI and save "
    "to ~/.config/emfi-control/MSPM0L2228.ccxml, OR set "
    "programmer.dslite_ccxml in ~/.config/emfi-control/config.json."
)


class XDS110Adapter(BaseAdapter):
    name = "xds110"

    def __init__(
        self,
        dslite_bin: Optional[str] = None,
        dslite_ccxml: Optional[str] = None,
        openocd_bin: Optional[str] = None,
        openocd_config: Optional[str] = None,
    ) -> None:
        self.dslite_bin = dslite_bin
        self.dslite_ccxml = dslite_ccxml
        self.openocd_bin = openocd_bin
        self.openocd_config = openocd_config
        self._port: Optional[str] = None
        self._debug_proc: Optional[subprocess.Popen] = None

    def connect(self, port: Optional[str] = None) -> None:
        """Record the detected XDS110 path for dashboard/device status."""
        self._port = port

    def disconnect(self) -> None:
        self.detach_debugger()
        self._port = None

    @property
    def connected(self) -> bool:
        return self._port is not None

    def flash(self, elf_path: Path) -> dict:
        """Flash the MSPM0L2228 via dslite.

        UniFlash 9.4.1's ``dslite.sh`` wrapper UNCONDITIONALLY prepends
        ``flash`` to whatever subcommand you pass — so calling::

            dslite.sh load --config=… <elf>

        ends up invoking ``DSLite flash load --config=… <elf>``, where the
        inner ``DSLite flash`` subcommand treats ``load`` as a positional
        flash-filename and dies with::

            Failed: Unable to open file: load

        The correct invocation is to pass NO subcommand at all and let the
        wrapper fall through to its default 'flash' mode plus ``--run`` so
        the target actually executes after loading (otherwise it sits
        halted at the entry point and a subsequent power-cycle is needed
        to start execution)::

            dslite.sh --run --config=<ccxml> <elf>

        That expands to ``DSLite flash --run --config=… <elf>`` which is
        the documented form.
        """
        if not self.dslite_bin:
            raise RuntimeError(
                "dslite binary path not configured. Set DSLITE_BIN env var "
                "or programmer.dslite_bin in ~/.config/emfi-control/config.json."
            )
        dslite = Path(self.dslite_bin)
        if not dslite.exists():
            raise FileNotFoundError(f"dslite binary not found at {dslite}")

        ccxml_path = self._resolve_ccxml()

        elf_path = Path(elf_path)
        if not elf_path.exists():
            raise RuntimeError(f"ELF file does not exist: {elf_path}")
        LOGGER.info("Flashing %s via dslite (ccxml=%s)", elf_path, ccxml_path)

        cmd = [str(dslite), "--run", f"--config={ccxml_path}", str(elf_path)]
        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            success = result.returncode == 0
            log_tail = (result.stdout + result.stderr)[-2000:]
            if success:
                LOGGER.info("Flash succeeded in %dms", elapsed_ms)
            else:
                LOGGER.warning("Flash failed (rc=%d) in %dms: %s",
                               result.returncode, elapsed_ms, log_tail[-200:])
            return {
                "success": success,
                "returncode": result.returncode,
                "elapsed_ms": elapsed_ms,
                "ccxml": str(ccxml_path),
                "stdout_tail": result.stdout[-2000:],
                "stderr_tail": result.stderr[-2000:],
                "log_tail": log_tail,
            }
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            LOGGER.error("Flash timed out after %dms", elapsed_ms)
            return {
                "success": False,
                "returncode": -1,
                "elapsed_ms": elapsed_ms,
                "ccxml": str(ccxml_path),
                "stdout_tail": "",
                "stderr_tail": "",
                "log_tail": "Timeout after 120s — dslite process killed.",
            }

    def _resolve_ccxml(self) -> Path:
        if self.dslite_ccxml:
            p = Path(self.dslite_ccxml)
            if p.exists():
                return p
            raise RuntimeError(f"Configured ccxml does not exist: {p}")

        config_dir = Path.home() / ".config" / "emfi-control"
        canonical = config_dir / "MSPM0L2228.ccxml"
        if canonical.exists():
            return canonical

        for hit in sorted(glob.glob(str(Path.home() / "ti" / "uniflash_*" / "onboard" / "MSPM0L2228*.ccxml"))):
            return Path(hit)

        raise RuntimeError(_CCXML_HINT)

    def reset(self) -> None:
        raise NotImplementedError("XDS110Adapter.reset")

    def attach_debugger(self, gdb_port: int = 3333, telnet_port: int = 4444) -> dict:
        """Spawn `openocd -f <cfg>` in the background."""
        raise NotImplementedError("XDS110Adapter.attach_debugger (openocd subprocess)")

    def detach_debugger(self) -> None:
        if self._debug_proc is not None:
            LOGGER.info("Terminating OpenOCD process (pid=%d)", self._debug_proc.pid)
            try:
                self._debug_proc.terminate()
                self._debug_proc.wait(timeout=5)
            except Exception:
                LOGGER.warning("OpenOCD process did not terminate cleanly")
            self._debug_proc = None
