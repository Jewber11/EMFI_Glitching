from __future__ import annotations

from datetime import datetime, timezone

from emfi_protocol.projects import FlashedFirmware

from control.provenance import load_flashed_firmware, save_flashed_firmware


def test_flashed_firmware_round_trip(tmp_path):
    path = tmp_path / "flashed_firmware.json"
    record = FlashedFirmware(
        build_sha="abc123",
        elf_url="file:///tmp/firmware.elf",
        project_id="purpleboardtest",
        project_version="main",
        flashed_at=datetime.now(timezone.utc),
        flash_result={"ok": True},
    )

    saved_path = save_flashed_firmware(record, path)
    loaded = load_flashed_firmware(path)

    assert saved_path == path
    assert loaded is not None
    assert loaded.build_sha == "abc123"
    assert loaded.project_id == "purpleboardtest"
    assert loaded.flash_result == {"ok": True}


def test_load_flashed_firmware_ignores_missing_file(tmp_path):
    assert load_flashed_firmware(tmp_path / "missing.json") is None
