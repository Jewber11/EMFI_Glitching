"""Tests for ArmGate / RateLimiter / StopFlag."""

from __future__ import annotations

import time

import pytest

from control.safety import ArmGate, Disarmed, RateLimited, RateLimiter, StopFlag


def test_armgate_starts_disarmed():
    gate = ArmGate()
    assert not gate.is_armed()
    with pytest.raises(Disarmed):
        gate.require_armed()


def test_armgate_arm_disarm_cycle():
    gate = ArmGate()
    gate.arm()
    assert gate.is_armed()
    gate.require_armed()  # should not raise
    gate.disarm()
    assert not gate.is_armed()


def test_armgate_auto_disarm_after_idle():
    gate = ArmGate(auto_disarm_seconds=0.05)
    gate.arm()
    time.sleep(0.1)
    assert not gate.is_armed()


def test_armgate_require_armed_refreshes_idle_timer():
    gate = ArmGate(auto_disarm_seconds=0.2)
    gate.arm()
    time.sleep(0.1)
    gate.require_armed()
    time.sleep(0.1)
    # Idle counter was reset by require_armed, so still armed
    assert gate.is_armed()


def test_armgate_notifies_on_change():
    seen: list[bool] = []
    gate = ArmGate(on_change=seen.append)
    gate.arm()
    gate.disarm()
    assert seen == [True, False]


def test_rate_limiter_allows_under_limit():
    rl = RateLimiter("test", max_per_sec=5)
    for _ in range(5):
        rl.acquire()


def test_rate_limiter_blocks_over_limit():
    rl = RateLimiter("test", max_per_sec=3)
    for _ in range(3):
        rl.acquire()
    with pytest.raises(RateLimited):
        rl.acquire()


def test_rate_limiter_window_slides():
    rl = RateLimiter("test", max_per_sec=2)
    rl.acquire()
    rl.acquire()
    with pytest.raises(RateLimited):
        rl.acquire()
    time.sleep(1.05)
    rl.acquire()  # window cleared


def test_rate_limiter_zero_is_unlimited():
    rl = RateLimiter("test", max_per_sec=0)
    for _ in range(1000):
        rl.acquire()


def test_stop_flag_set_clear():
    sf = StopFlag()
    assert not sf.is_set()
    sf.set()
    assert sf.is_set()
    sf.clear()
    assert not sf.is_set()
