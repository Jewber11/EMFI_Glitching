"""Target MCU flashing + debugging via XDS110.

Flash sequence: power on DUT via Scaffold board, then flash via XDS110.
"""

from __future__ import annotations

import logging
import hashlib
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from emfi_protocol.projects import FlashedFirmware
from pydantic import BaseModel

from control.deps import AppContext, call_adapter, call_subprocess_adapter, get_ctx
from control.provenance import save_flashed_firmware
from control.adapters.pico_probe import PicoProbeAdapter

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/target", tags=["target"])


@router.get("/firmware")
def list_firmware(folder: str) -> dict:
    """List loadable files below a folder on the Control host."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {root}")
    images = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in (".elf", ".out", ".hex", ".bin", ".prot", ".hsm"):
                if suffix:
                    continue
                try:
                    with path.open("rb") as candidate:
                        if candidate.read(4) != b"\x7fELF":
                            continue
                except OSError:
                    continue
            images.append({"path": str(path), "name": str(path.relative_to(root)),
                           "mode": "ectf" if suffix in (".bin", ".prot", ".hsm") else "swd"})
            if len(images) >= 5000:
                return {"folder": str(root), "images": images, "truncated": True}
    return {"folder": str(root), "images": images, "truncated": False}


class FlashRequest(BaseModel):
    build_sha: str
    elf_url: str
    project_id: Optional[str] = None
    project_version: Optional[str] = None
    mode: Literal["swd", "ectf"] = "swd"
    name: str = "firmware"


def _flash_ectf(binary: str, port: str, path: Path, name: str) -> dict:
    if not path.is_file():
        raise ValueError(f"Firmware file does not exist: {path}")
    try:
        result = subprocess.run([binary, "hw", port, "reflash", "-n", name, str(path)],
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"eCTF flash failed: {exc}") from exc
    return {"success": result.returncode == 0, "returncode": result.returncode,
            "programmer": "ectf", "log_tail": (result.stdout + result.stderr)[-4000:]}


class DebugAttachRequest(BaseModel):
    build_sha: str
    elf_url: Optional[str] = None
    gdb_port: int = 3333
    telnet_port: int = 4444


@router.post("/flash")
async def flash(req: FlashRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Flash the MSPM0L2228 via XDS110.

    Sequence:
    1. Power-cycle the DUT via Scaffold to ensure it's in a known state
    2. Flash the ELF via dslite/UniFlash subprocess
    """
    LOGGER.info("Flash requested: build_sha=%s elf_url=%s", req.build_sha, req.elf_url)

    power_cycle = ctx.config.get("programmer", "power_cycle") if getattr(ctx, "config", None) else True
    if power_cycle is None:
        power_cycle = not isinstance(ctx.xds110, PicoProbeAdapter)
    if power_cycle:
        scaffold_worker = ctx.workers.get("scaffold")
        await call_adapter(scaffold_worker, ctx.scaffold.dut_power_cycle)

    elf_path = await _resolve_elf(req.elf_url)
    build_sha = req.build_sha
    if build_sha.startswith("file:"):
        try:
            with elf_path.open("rb") as image:
                build_sha = hashlib.file_digest(image, "sha256").hexdigest()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Cannot read firmware: {exc}") from exc

    try:
        from control.provenance import default_flashed_firmware_path
        default_flashed_firmware_path().unlink(missing_ok=True)
        ctx.flashed_firmware = None
        if req.mode == "ectf":
            port = ctx.config.get("programmer", "ectf_port") or (ctx.xds110._port if isinstance(ctx.xds110, PicoProbeAdapter) else None)
            if not port:
                raise HTTPException(status_code=400, detail="Set programmer.ectf_port")
            result = await call_subprocess_adapter(_flash_ectf, ctx.config.get("programmer", "ectf_bin", default="ectf"), port, elf_path, req.name)
        else:
            result = await call_subprocess_adapter(ctx.xds110.flash, elf_path)
    finally:
        if req.elf_url.startswith(("http://", "https://")):
            elf_path.unlink(missing_ok=True)
    if isinstance(result, dict) and result.get("success") is False:
        raise HTTPException(status_code=500, detail=result.get("log_tail") or "Flash failed")
    record = FlashedFirmware(
        build_sha=build_sha,
        elf_url=req.elf_url,
        project_id=req.project_id,
        project_version=req.project_version,
        flashed_at=datetime.now(timezone.utc),
        flash_result=result if isinstance(result, dict) else {"result": result},
    )
    ctx.flashed_firmware = record
    try:
        save_flashed_firmware(record)
    except OSError:
        LOGGER.exception("Flash succeeded but failed to persist flashed firmware provenance")

    ctx.broadcast("device_status", {"name": "xds110", "connected": True})
    LOGGER.info("Flash complete: build_sha=%s result=%s", req.build_sha, result)
    return {"ok": True, "build_sha": build_sha, "flash_result": result}


@router.post("/reset")
async def reset(ctx: AppContext = Depends(get_ctx)) -> dict:
    await call_subprocess_adapter(ctx.xds110.reset)
    return {"ok": True}


@router.post("/debug_attach")
async def debug_attach(req: DebugAttachRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Start OpenOCD attached to the target for debugger sessions."""
    result = await call_subprocess_adapter(
        ctx.xds110.attach_debugger,
        gdb_port=req.gdb_port,
        telnet_port=req.telnet_port,
    )
    LOGGER.info("OpenOCD attached: gdb=%d telnet=%d", req.gdb_port, req.telnet_port)
    return {"ok": True, "gdb_port": req.gdb_port, "telnet_port": req.telnet_port, **(result or {})}


@router.post("/debug_detach")
async def debug_detach(ctx: AppContext = Depends(get_ctx)) -> dict:
    ctx.xds110.detach_debugger()
    return {"ok": True}


async def _resolve_elf(elf_url: str) -> Path:
    """Resolve an ELF URL to a local file path.

    Supports ``file:///path`` (local) and ``http(s)://`` (download from Develop).
    """
    if elf_url.startswith("file://"):
        return Path(elf_url[7:])

    if elf_url.startswith(("http://", "https://")):
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(elf_url)
            resp.raise_for_status()
        from urllib.parse import urlparse
        suffix = Path(urlparse(elf_url).path).suffix or ".elf"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(resp.content)
        tmp.close()
        LOGGER.info("Downloaded ELF to %s (%d bytes)", tmp.name, len(resp.content))
        return Path(tmp.name)

    return Path(elf_url)
