"""ChipShoverAdapter coordinate-transform tests (no hardware).

Covers the axes config (invert_x/y/z, swap_xy) wired through the
user↔machine boundary. The fake mirrors the real library surface:
``move(x, y, z)`` (absolute) and ``get_position()`` — the lib has no
relative-move API, so move_relative computes an absolute target.
"""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from control.adapters.chipshover import ChipShoverAdapter


class FakeShover:
    def __init__(self, pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        self.pos = pos
        self.last_abs: Optional[Tuple[float, float, float]] = None

    def get_position(self, *args, **kwargs) -> Tuple[float, float, float]:
        return self.pos

    def move(self, x=None, y=None, z=None) -> None:
        self.last_abs = (x, y, z)
        self.pos = (x, y, z)

    def close(self) -> None:
        pass


def _adapter(**flags) -> ChipShoverAdapter:
    a = ChipShoverAdapter(**flags)
    a._impl = FakeShover()
    return a


# --- inversion ------------------------------------------------------------

def test_invert_x_flips_jog_direction():
    """User +X jog moves the gantry in machine -X."""
    a = _adapter(invert_x=True)
    a.move_relative("X", 1.0)
    assert a._impl.last_abs == (-1.0, 0.0, 0.0)


def test_invert_y_flips_jog_direction():
    a = _adapter(invert_y=True)
    a.move_relative("Y", 1.0)
    assert a._impl.last_abs == (0.0, -1.0, 0.0)


def test_invert_z_flips_jog_direction():
    a = _adapter(invert_z=True)
    a.move_relative("Z", 0.5)
    assert a._impl.last_abs == (0.0, 0.0, -0.5)


def test_no_flags_is_identity():
    a = _adapter()
    a.move_absolute_logical(3.0, 4.0, 5.0)
    assert a._impl.last_abs == (3.0, 4.0, 5.0)


def test_invert_x_absolute_move():
    a = _adapter(invert_x=True)
    a.move_absolute_logical(10.0, 2.0, 0.0)
    assert a._impl.last_abs == (-10.0, 2.0, 0.0)


# --- swap -----------------------------------------------------------------

def test_swap_xy_swaps_axes():
    """User (1, 2) maps to machine (2, 1)."""
    a = _adapter(swap_xy=True)
    a.move_absolute_logical(1.0, 2.0, 0.0)
    assert a._impl.last_abs == (2.0, 1.0, 0.0)


def test_swap_xy_relative_x_drives_machine_y():
    a = _adapter(swap_xy=True)
    a.move_relative("X", 1.0)
    assert a._impl.last_abs == (0.0, 1.0, 0.0)


# --- combined -------------------------------------------------------------

def test_invert_x_plus_swap_xy_combined():
    """invert applies to user axes first, then swap maps to machine axes.

    User +X with invert_x → -X intent; swap maps X-intent to machine Y →
    machine -Y.
    """
    a = _adapter(invert_x=True, swap_xy=True)
    a.move_relative("X", 1.0)
    assert a._impl.last_abs == (0.0, -1.0, 0.0)


def test_invert_both_plus_swap_absolute():
    a = _adapter(invert_x=True, invert_y=True, swap_xy=True)
    # invert → (-1, -2, 0); swap → (-2, -1, 0)
    a.move_absolute_logical(1.0, 2.0, 0.0)
    assert a._impl.last_abs == (-2.0, -1.0, 0.0)


# --- read-back (machine → user) -------------------------------------------

def test_get_position_logical_applies_inverse():
    """The reported logical position matches the user's button convention.

    Gantry parked at machine (-10, -10): the user sees logical (+10, +10),
    so the calibration wizard's top_right ends up positive (the bug fix).
    """
    a = _adapter(invert_x=True, invert_y=True)
    a._impl.pos = (-10.0, -10.0, 0.0)
    assert a.get_position_logical() == (10.0, 10.0, 0.0)


def test_machine_to_logical_honors_origin_offset():
    a = _adapter()
    a._origin_machine = (5.0, 3.0, 1.0)
    assert a.machine_to_logical(7.0, 4.0, 1.0) == (2.0, 1.0, 0.0)


@pytest.mark.parametrize("flags", [
    {},
    {"invert_x": True},
    {"invert_y": True},
    {"invert_z": True},
    {"swap_xy": True},
    {"invert_x": True, "swap_xy": True},
    {"invert_x": True, "invert_y": True, "invert_z": True, "swap_xy": True},
])
def test_logical_machine_roundtrip_is_identity(flags):
    a = _adapter(**flags)
    a._origin_machine = (5.0, -3.0, 1.0)
    for u in [(1.0, 2.0, 0.5), (-4.0, 7.0, -2.0), (0.0, 0.0, 0.0)]:
        m = a.logical_to_machine(*u)
        back = a.machine_to_logical(*m)
        assert all(abs(b - c) < 1e-9 for b, c in zip(back, u)), (flags, u, m, back)
