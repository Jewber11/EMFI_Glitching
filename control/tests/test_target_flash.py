from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from control.routers import target


class _XDS110:
    def flash(self, elf_path: Path) -> dict[str, Any]:
        return {"programmer": "fake", "elf": str(elf_path)}


class _Scaffold:
    def dut_power_cycle(self) -> None:
        return None


@dataclass
class _Ctx:
    xds110: _XDS110 = field(default_factory=_XDS110)
    scaffold: _Scaffold = field(default_factory=_Scaffold)
    workers: dict[str, Any] = field(default_factory=lambda: {"scaffold": object()})
    flashed_firmware: Any = None
    broadcasts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        self.broadcasts.append((topic, payload))


@pytest.mark.asyncio
async def test_flash_remembers_successful_build_metadata(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/emfi-test-target-flash")
    async def fake_call_adapter(worker, fn, *args, **kwargs):
        return None

    async def fake_call_subprocess_adapter(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(target, "call_adapter", fake_call_adapter)
    monkeypatch.setattr(target, "call_subprocess_adapter", fake_call_subprocess_adapter)

    saved = {}

    def fake_save(record):
        saved["record"] = record
        return Path("/tmp/flashed_firmware.json")

    monkeypatch.setattr(target, "save_flashed_firmware", fake_save)

    async def fake_resolve_elf(url: str) -> Path:
        return Path("/tmp/test.elf")

    monkeypatch.setattr(target, "_resolve_elf", fake_resolve_elf)

    ctx = _Ctx()
    req = target.FlashRequest(
        build_sha="abc123",
        elf_url="file:///tmp/test.elf",
        project_id="purpleboardtest",
        project_version="main",
    )

    response = await target.flash(req, ctx)

    assert response["ok"] is True
    assert ctx.flashed_firmware.build_sha == "abc123"
    assert ctx.flashed_firmware.project_id == "purpleboardtest"
    assert ctx.flashed_firmware.project_version == "main"
    assert ctx.flashed_firmware.elf_url == "file:///tmp/test.elf"
    assert ctx.flashed_firmware.flash_result["programmer"] == "fake"
    assert saved["record"].build_sha == "abc123"
    assert ("device_status", {"name": "xds110", "connected": True}) in ctx.broadcasts


@pytest.mark.asyncio
async def test_failed_flash_clears_provenance(tmp_path, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    async def adapter(worker, fn, *args, **kwargs):
        return None
    async def subprocess_adapter(fn, *args, **kwargs):
        return {"success": False, "log_tail": "flash failed"}
    monkeypatch.setattr(target, "call_adapter", adapter)
    monkeypatch.setattr(target, "call_subprocess_adapter", subprocess_adapter)
    ctx = _Ctx(flashed_firmware="previous")
    with pytest.raises(HTTPException, match="flash failed"):
        await target.flash(target.FlashRequest(build_sha="new", elf_url="/tmp/image.elf"), ctx)
    assert ctx.flashed_firmware is None
