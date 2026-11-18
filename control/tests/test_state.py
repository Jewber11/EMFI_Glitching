"""Tests for AppState counters + snapshot."""

from __future__ import annotations

from control.state import AppState, Counters


def test_counter_record_increments_attempts_and_outcome():
    c = Counters()
    c.record("glitch")
    c.record("hang")
    c.record("crash")
    c.record("nothing")
    c.record("unknown-treated-as-nothing")
    assert c.attempts == 5
    assert c.glitches == 1
    assert c.hangs == 1
    assert c.crashes == 1
    assert c.nothings == 2


def test_counter_reset():
    c = Counters(attempts=10, glitches=3)
    c.reset()
    assert c.attempts == 0
    assert c.glitches == 0


def test_appstate_snapshot_structure():
    s = AppState()
    snap = s.snapshot()
    # Spot-check the contract View depends on
    for key in (
        "devices",
        "position_logical",
        "position_machine",
        "origin_set",
        "top_right_set",
        "counters",
        "scan",
        "armed",
    ):
        assert key in snap
    assert "attempts" in snap["counters"]
    assert "active" in snap["scan"]
