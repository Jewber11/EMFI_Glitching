"""CMSIS-DAP Pico Debug Probe programming via probe-rs."""

from pathlib import Path
import subprocess

from control.adapters.xds110 import XDS110Adapter


class PicoProbeAdapter(XDS110Adapter):
    def __init__(self, binary: str | None = None, probe: str | None = None):
        super().__init__()
        bundled = Path(__file__).resolve().parents[4] / ".tools/probe-rs-tools-x86_64-unknown-linux-gnu/probe-rs"
        self.binary = binary or (str(bundled) if bundled.is_file() else "probe-rs")
        self.probe = probe

    def flash(self, elf_path: Path) -> dict:
        path = Path(elf_path)
        if not path.is_file():
            raise RuntimeError(f"Firmware file does not exist: {path}")
        is_elf = False
        if not path.suffix:
            with path.open("rb") as image:
                is_elf = image.read(4) == b"\x7fELF"
        if path.suffix.lower() not in (".elf", ".out", ".hex") and not is_elf:
            raise ValueError("SWD requires an addressed ELF, OUT, or HEX image; use eCTF mode for application binaries")
        cmd = [self.binary, "download", str(path), "--protocol", "swd", "--chip", "MSPM0L2228", "--non-interactive", "--verify", "--reset", "--binary-format", "hex" if path.suffix.lower() == ".hex" else "elf"]
        cmd += ["--probe", self.probe or "2e8a:000c"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"probe-rs failed: {exc}") from exc
        return {"success": result.returncode == 0, "returncode": result.returncode,
                "programmer": "pico", "log_tail": (result.stdout + result.stderr)[-4000:]}
