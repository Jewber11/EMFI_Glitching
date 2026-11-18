"""Serial port discovery + best-guess device classification.

Carry-forward from old-em-setup/glitchweb/backend/app/ports.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import serial.tools.list_ports

LOGGER = logging.getLogger(__name__)


def list_ports(known: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return all serial ports with a best-guess device label.

    `known` is the `known_devices` section of the config.
    """
    out: List[Dict[str, Any]] = []
    for p in serial.tools.list_ports.comports():
        info = {
            "device": p.device,
            "description": p.description or "",
            "interface": p.interface or "",
            "manufacturer": p.manufacturer or "",
            "product": p.product or "",
            "vid": p.vid,
            "pid": p.pid,
            "serial_number": p.serial_number or "",
            "hwid": p.hwid or "",
        }
        guess = _classify(info, known)
        info["guess"] = guess
        info["label"] = _label(info, guess)
        out.append(info)

    out.sort(key=lambda d: d.get("device") or "")
    LOGGER.info("Port scan: %d ports found", len(out))
    for p in out:
        LOGGER.debug("  %s -> %s", p.get("device"), p.get("guess") or "unknown")
    return out


def _classify(
    info: Dict[str, Any], known: Dict[str, List[Dict[str, Any]]]
) -> Optional[str]:
    if info.get("vid") == 0x1209 and info.get("pid") == 0xFA17:
        try:
            from faultycmd.core.usb import cdc_for
            return "chipshouter" if cdc_for("emfi") == info.get("device") else None
        except Exception:
            return None
    for device_class, patterns in known.items():
        for pat in patterns:
            if _matches(info, pat):
                return device_class
    return None


def _matches(info: Dict[str, Any], pat: Dict[str, Any]) -> bool:
    for k, v in pat.items():
        if k == "vid":
            if info.get("vid") != v:
                return False
        elif k == "pid":
            if info.get("pid") != v:
                return False
        elif k == "manufacturer":
            if (info.get("manufacturer") or "").lower() != v.lower():
                return False
        elif k == "manufacturer_contains":
            if v.lower() not in (info.get("manufacturer") or "").lower():
                return False
        elif k == "product_contains":
            if v.lower() not in (info.get("product") or "").lower():
                return False
        elif k == "description_contains":
            if v.lower() not in (info.get("description") or "").lower():
                return False
        elif k == "serial_prefix":
            if not (info.get("serial_number") or "").startswith(v):
                return False
        else:
            return False
    return True


def _label(info: Dict[str, Any], guess: Optional[str]) -> str:
    parts: List[str] = []
    if guess:
        parts.append(guess)
    desc = info.get("description") or info.get("product") or ""
    if desc:
        parts.append(desc)
    manu = info.get("manufacturer") or ""
    if manu and manu not in " ".join(parts):
        parts.append(manu)
    sn = info.get("serial_number") or ""
    if sn:
        parts.append(f"sn={sn}")
    if info.get("vid") is not None and info.get("pid") is not None:
        parts.append(f"{info['vid']:04x}:{info['pid']:04x}")
    parts.append(info.get("device", ""))
    return " — ".join(p for p in parts if p)


def pick_port(
    device_class: str,
    ports: List[Dict[str, Any]],
    override: Optional[str],
) -> Optional[str]:
    if override:
        return override
    for p in ports:
        if p.get("guess") == device_class:
            return p["device"]
    return None
