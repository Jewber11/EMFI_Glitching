import subprocess

import pytest
from fastapi import HTTPException

from control.adapters.pico_probe import PicoProbeAdapter
from control.routers import target


def test_pico_download_and_error(tmp_path, monkeypatch):
    image = tmp_path / "bootloader.out"
    image.write_bytes(b"ELF")
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "probe unavailable")
    monkeypatch.setattr(subprocess, "run", run)
    result = PicoProbeAdapter(binary="probe-rs", probe="2e8a:000c:serial").flash(image)
    assert not result["success"]
    assert "probe unavailable" in result["log_tail"]
    assert calls[0] == ["probe-rs", "download", str(image), "--protocol", "swd", "--chip", "MSPM0L2228", "--non-interactive", "--verify", "--reset", "--binary-format", "elf", "--probe", "2e8a:000c:serial"]


def test_pico_rejects_unaddressed_binary(tmp_path):
    image = tmp_path / "firmware.bin"
    image.write_bytes(b"data")
    with pytest.raises(ValueError):
        PicoProbeAdapter().flash(image)


def test_ectf_reflash_command(tmp_path, monkeypatch):
    image = tmp_path / "design.prot"
    image.write_bytes(b"data")
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")
    monkeypatch.setattr(subprocess, "run", run)
    assert target._flash_ectf("ectf", "/dev/ttyACM0", image, "HSM")["success"]
    assert calls[0] == ["ectf", "hw", "/dev/ttyACM0", "reflash", "-n", "HSM", str(image)]
