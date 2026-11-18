"""ChipShover (XY positioning table) adapter.

Wraps the ``chipshover`` pip package (install from GitHub, not PyPI —
the PyPI tarball is malformed). The library speaks G-code over serial
to either Smoothieware or Marlin firmware.

Library API surface (confirmed by probe):
    ChipShover(comport)
    .get_position(forcefinish=True) -> (x, y, z)
    .move(x=None, y=None, z=None)  # absolute, blocks via M400
    .home(x=True, y=True, z=True)  # G28, blocks
    .close()

Coordinate systems
------------------
Three frames, transformed at the API↔machine boundary here:

* **User logical** — what the API/WS report and what the +X/+Y/+Z jog
  buttons mean. Origin is (0,0,0); positive points in the user's chosen
  directions.
* **Machine** — raw gantry coordinates passed to the chipshover library.

``set_origin()`` records the current machine position as the logical
origin; logical coordinates are offsets from it (ported from
old-em-setup/glitchweb/backend/app/devices/chipshover_dev.py:92-104).

On top of the origin offset, the ``axes`` config flags correct for a
gantry mounted differently from the conventional rig:

* ``invert_x`` / ``invert_y`` / ``invert_z`` — the user's positive
  direction for that axis is the machine's negative direction. Set this
  when a jog button moves the stage the "wrong" way.
* ``swap_xy`` — the X and Y stages are physically transposed (mount
  rotated 90°): the user's X drives the machine's Y and vice versa.

Transform order (user → machine): invert the user axes first, then map
to machine axes via the optional swap. Reads apply the exact inverse.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from control.adapters.base import BaseAdapter

LOGGER = logging.getLogger(__name__)


class ChipShoverAdapter(BaseAdapter):
    name = "chipshover"

    def __init__(
        self,
        invert_x: bool = False,
        invert_y: bool = False,
        invert_z: bool = False,
        swap_xy: bool = False,
    ) -> None:
        self._impl = None
        self._port: Optional[str] = None
        self._last_error: Optional[str] = None
        self._origin_machine: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._origin_set: bool = False
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.invert_z = invert_z
        self.swap_xy = swap_xy

    def connect(self, port: Optional[str] = None) -> None:
        if port is None:
            raise ValueError("chipshover: no serial port specified")
        try:
            from chipshover import ChipShover
        except ImportError as exc:
            self._last_error = f"chipshover library not installed: {exc}"
            raise RuntimeError(self._last_error) from exc

        LOGGER.info(
            "ChipShover connecting on %s (invert_x=%s invert_y=%s invert_z=%s swap_xy=%s)",
            port, self.invert_x, self.invert_y, self.invert_z, self.swap_xy,
        )
        self._impl = ChipShover(port)
        self._port = port
        self._last_error = None
        pos = self._impl.get_position()
        LOGGER.info("ChipShover connected — position: %s", pos)

    def disconnect(self) -> None:
        if self._impl is not None:
            LOGGER.info("ChipShover disconnecting")
            try:
                self._impl.close()
            except Exception as exc:
                LOGGER.warning("ChipShover close error: %s", exc)
            self._impl = None
            self._port = None

    @property
    def connected(self) -> bool:
        return self._impl is not None

    def _require_connected(self) -> None:
        if self._impl is None:
            raise RuntimeError("ChipShover is not connected")

    def get_position(self) -> Tuple[float, float, float]:
        """Raw machine position from the gantry."""
        self._require_connected()
        x, y, z = self._impl.get_position()
        return (float(x), float(y), float(z))

    def get_position_logical(self) -> Tuple[float, float, float]:
        """Current position in user logical coordinates (origin + axes applied)."""
        return self.machine_to_logical(*self.get_position())

    def move_absolute_logical(self, x: float, y: float, z: float) -> None:
        self._require_connected()
        mx, my, mz = self.logical_to_machine(x, y, z)
        LOGGER.debug("move_absolute_logical(%s, %s, %s) -> machine(%s, %s, %s)",
                      x, y, z, mx, my, mz)
        self._impl.move(x=mx, y=my, z=mz)

    def move_relative(self, axis: str, distance: float) -> None:
        self._require_connected()
        axis_upper = axis.upper()
        if axis_upper == "X":
            user_delta = (distance, 0.0, 0.0)
        elif axis_upper == "Y":
            user_delta = (0.0, distance, 0.0)
        elif axis_upper == "Z":
            user_delta = (0.0, 0.0, distance)
        else:
            raise ValueError(f"Invalid axis: {axis}")
        # A relative move is a pure delta: apply axis inversion/swap but no
        # origin offset, then add to the current machine position.
        dmx, dmy, dmz = self._user_delta_to_machine(*user_delta)
        cx, cy, cz = self.get_position()
        LOGGER.debug("move_relative(%s, %s) -> machine delta(%s, %s, %s)",
                      axis, distance, dmx, dmy, dmz)
        self._impl.move(x=cx + dmx, y=cy + dmy, z=cz + dmz)

    def home(self) -> None:
        self._require_connected()
        LOGGER.info("ChipShover homing")
        self._impl.home()
        self._origin_set = False
        self._origin_machine = (0.0, 0.0, 0.0)
        LOGGER.info("ChipShover homed — origin cleared")

    def set_origin(self) -> None:
        self._require_connected()
        pos = self.get_position()
        self._origin_machine = pos
        self._origin_set = True
        LOGGER.info("ChipShover origin set at machine %s", pos)

    @property
    def origin_machine(self) -> Tuple[float, float, float]:
        return self._origin_machine

    @property
    def origin_set(self) -> bool:
        return self._origin_set

    def set_origin_machine(self, x: float, y: float, z: float) -> None:
        """Restore a known fixture origin in machine coordinates.

        This is used after homing a bolted-down fixture: home establishes a
        repeatable machine frame, then the saved chip corner becomes logical
        (0, 0, 0) without jogging there by hand.
        """
        self._origin_machine = (float(x), float(y), float(z))
        self._origin_set = True
        LOGGER.info("ChipShover origin restored at machine %s", self._origin_machine)

    # ------------------------------------------------------------------
    # Coordinate transforms (pure; no hardware access).
    # ------------------------------------------------------------------

    def _user_delta_to_machine(
        self, ux: float, uy: float, uz: float
    ) -> Tuple[float, float, float]:
        """User-frame delta → machine-frame delta (invert, then swap)."""
        ix = -ux if self.invert_x else ux
        iy = -uy if self.invert_y else uy
        iz = -uz if self.invert_z else uz
        if self.swap_xy:
            return (iy, ix, iz)
        return (ix, iy, iz)

    def _machine_delta_to_user(
        self, mx: float, my: float, mz: float
    ) -> Tuple[float, float, float]:
        """Machine-frame delta → user-frame delta (inverse: un-swap, un-invert)."""
        if self.swap_xy:
            sx, sy, sz = my, mx, mz
        else:
            sx, sy, sz = mx, my, mz
        ux = -sx if self.invert_x else sx
        uy = -sy if self.invert_y else sy
        uz = -sz if self.invert_z else sz
        return (ux, uy, uz)

    def logical_to_machine(
        self, x: float, y: float, z: float
    ) -> Tuple[float, float, float]:
        ox, oy, oz = self._origin_machine
        dmx, dmy, dmz = self._user_delta_to_machine(x, y, z)
        return (ox + dmx, oy + dmy, oz + dmz)

    def machine_to_logical(
        self, mx: float, my: float, mz: float
    ) -> Tuple[float, float, float]:
        ox, oy, oz = self._origin_machine
        return self._machine_delta_to_user(mx - ox, my - oy, mz - oz)
