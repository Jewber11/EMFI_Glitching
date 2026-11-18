from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from control.routers import motion


class _Config:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {"fixture": {"default_grid": None}}

    def get(self, *path: str, default: Any = None) -> Any:
        cur: Any = self.data
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur

    def update(self, partial: dict[str, Any]) -> dict[str, Any]:
        for key, value in partial.items():
            if isinstance(value, dict) and isinstance(self.data.get(key), dict):
                self.data[key].update(value)
            else:
                self.data[key] = value
        return self.data


class _Worker:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class _Shover:
    origin_machine = (4.0, 5.0, 6.0)
    origin_set = True

    def __init__(self) -> None:
        self.restored: tuple[float, float, float] | None = None

    def set_origin_machine(self, x: float, y: float, z: float) -> None:
        self.restored = (x, y, z)
        self.origin_machine = self.restored
        self.origin_set = True

    def get_position(self) -> tuple[float, float, float]:
        return (4.5, 6.0, 6.1)

    def machine_to_logical(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        ox, oy, oz = self.origin_machine
        return (x - ox, y - oy, z - oz)


@dataclass
class _State:
    position_machine: tuple[float, float, float] = (14.0, 15.0, 6.2)
    position_logical: tuple[float, float, float] = (10.0, 10.0, 0.2)
    origin_set: bool = True
    top_right_set: bool = True
    top_right: tuple[float, float] = (10.0, 10.0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "origin_set": self.origin_set,
            "top_right_set": self.top_right_set,
            "top_right": list(self.top_right),
        }


@dataclass
class _Ctx:
    config: _Config = field(default_factory=_Config)
    shover: _Shover = field(default_factory=_Shover)
    state: _State = field(default_factory=_State)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    workers: dict[str, _Worker] = field(default_factory=lambda: {"chipshover": _Worker()})

    def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append((topic, payload))

    def broadcast_state(self) -> None:
        self.broadcast("state", self.state.snapshot())


async def test_save_current_fixture_persists_machine_origin() -> None:
    ctx = _Ctx()

    result = await motion.save_current_fixture(
        motion.SaveCurrentFixtureRequest(name="purple-board", step_size_mm=0.5),
        ctx,
    )

    fixture = result["fixture"]
    assert fixture["name"] == "purple-board"
    assert fixture["origin"] == [0.0, 0.0]
    assert fixture["top_right"] == [10.0, 10.0]
    assert fixture["machine_origin"] == [4.0, 5.0, 6.0]
    assert fixture["machine_top_right"] == [14.0, 15.0, 6.2]
    assert ctx.config.get("fixture", "default_grid") == fixture
    assert ctx.events[-1] == ("fixture", fixture)


async def test_save_current_fixture_allows_negative_backside_corner() -> None:
    ctx = _Ctx()
    ctx.state.top_right = (-4.1, -4.1)
    ctx.state.position_machine = (-0.1, 0.9, 6.2)

    result = await motion.save_current_fixture(
        motion.SaveCurrentFixtureRequest(name="backside-die"),
        ctx,
    )

    fixture = result["fixture"]
    assert fixture["top_right"] == [-4.1, -4.1]
    assert fixture["machine_top_right"] == [-0.1, 0.9, 6.2]


async def test_apply_fixture_restores_origin_and_grid() -> None:
    ctx = _Ctx()
    ctx.config.update({
        "fixture": {
            "default_grid": {
                "name": "purple-board",
                "origin": [0.0, 0.0],
                "top_right": [8.0, 9.0],
                "machine_origin": [1.0, 2.0, 3.0],
                "step_size_mm": 0.25,
                "z_min_mm": 0.0,
                "z_max_mm": 0.5,
                "z_step_mm": 0.1,
            }
        }
    })

    result = await motion.apply_fixture(ctx)

    assert result["origin_set"] is True
    assert result["top_right"] == [8.0, 9.0]
    assert ctx.shover.restored == (1.0, 2.0, 3.0)
    assert ctx.state.position_logical == pytest.approx((3.5, 4.0, 3.1))
    assert ("state", ctx.state.snapshot()) in ctx.events


async def test_save_current_fixture_requires_origin() -> None:
    ctx = _Ctx()
    ctx.shover.origin_set = False

    with pytest.raises(Exception) as exc:
        await motion.save_current_fixture(motion.SaveCurrentFixtureRequest(), ctx)

    assert "cannot save fixture before setting origin" in str(exc.value)
