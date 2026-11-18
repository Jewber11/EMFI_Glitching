from __future__ import annotations

import subprocess

from control.adapters.xds110 import XDS110Adapter


def test_xds110_connect_tracks_detected_port():
    adapter = XDS110Adapter()

    assert adapter.connected is False

    adapter.connect("/dev/serial/by-id/xds110")

    assert adapter.connected is True
    assert adapter._port == "/dev/serial/by-id/xds110"


def test_xds110_disconnect_clears_status():
    adapter = XDS110Adapter()
    adapter.connect("/dev/serial/by-id/xds110")

    adapter.disconnect()

    assert adapter.connected is False
    assert adapter._port is None


def test_xds110_flash_uses_uniflash_wrapper_default_flash_mode(tmp_path, monkeypatch):
    dslite = tmp_path / "dslite.sh"
    dslite.write_text("#!/bin/sh\n")
    ccxml = tmp_path / "target.ccxml"
    ccxml.write_text("<ccxml />\n")
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    seen = {}

    def fake_run(cmd, capture_output, text, timeout):
        seen["cmd"] = cmd
        seen["capture_output"] = capture_output
        seen["text"] = text
        seen["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = XDS110Adapter(
        dslite_bin=str(dslite),
        dslite_ccxml=str(ccxml),
    ).flash(elf)

    assert result["success"] is True
    assert seen["cmd"] == [
        str(dslite),
        "--run",
        f"--config={ccxml}",
        str(elf),
    ]
    assert "load" not in seen["cmd"]
