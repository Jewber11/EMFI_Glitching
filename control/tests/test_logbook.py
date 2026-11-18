"""Tests for the JSONL logbook + SQLite mirror."""

from __future__ import annotations

import json

from control.logbook import Logbook


def test_logbook_append_writes_jsonl(tmp_path):
    lb = Logbook(tmp_path)
    entry = {
        "id": "abc",
        "x": 1.0,
        "y": 2.0,
        "z": 0.0,
        "outcome": "glitch",
        "verdict": {"fault": True, "heartbeat_alive": True, "campaign_complete": False},
    }
    stored = lb.append(entry)
    assert stored["id"] == "abc"
    # File written
    files = list(tmp_path.glob("logbook-*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text().strip()
    assert json.loads(content)["id"] == "abc"


def test_logbook_read_filters_by_outcome(tmp_path):
    lb = Logbook(tmp_path)
    lb.append({"id": "a", "outcome": "glitch", "x": 0, "y": 0})
    lb.append({"id": "b", "outcome": "hang", "x": 0, "y": 0})
    lb.append({"id": "c", "outcome": "glitch", "x": 1, "y": 1})
    glitches = lb.read(outcome="glitch")
    assert {e["id"] for e in glitches} == {"a", "c"}


def test_logbook_read_filters_heatmap_drilldown_fields(tmp_path):
    lb = Logbook(tmp_path)
    lb.append({"id": "a", "campaign_id": "camp-1", "outcome": "glitch", "x": 1, "y": 2, "z": 0})
    lb.append({"id": "b", "campaign_id": "camp-1", "outcome": "hang", "x": 1, "y": 2, "z": 0})
    lb.append({"id": "c", "campaign_id": "camp-1", "outcome": "glitch", "x": 1, "y": 2, "z": 1})
    lb.append({"id": "d", "campaign_id": "camp-2", "outcome": "glitch", "x": 1, "y": 2, "z": 0})
    lb.append({"id": "e", "campaign_id": "camp-1", "outcome": "glitch", "x": 9, "y": 9, "z": 0})

    rows = lb.read(campaign_id="camp-1", x=1, y=2, z=0, outcome="glitch")

    assert [row["id"] for row in rows] == ["a"]


def test_logbook_sqlite_mirror_contains_appended_rows(tmp_path):
    lb = Logbook(tmp_path)
    lb.append({"id": "a", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "b", "outcome": "nothing", "x": 1.0, "y": 2.0, "z": 0.0})
    # Filtered to one outcome: still returns a per-cell counts dict.
    rows = lb.heatmap(outcome="glitch")
    assert rows == [{"x": 1.0, "y": 2.0, "counts": {"glitch": 1, "hang": 0, "crash": 0, "nothing": 0, "unobserved": 0}}]


def test_logbook_heatmap_per_outcome_counts(tmp_path):
    lb = Logbook(tmp_path)
    # Cell (1,2): 2 glitches, 1 hang, 1 nothing. Cell (3,4): 1 crash.
    lb.append({"id": "a", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "b", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "c", "outcome": "hang", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "d", "outcome": "nothing", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "e", "outcome": "crash", "x": 3.0, "y": 4.0, "z": 0.0})

    # Default: no outcome filter → every cell, all buckets.
    rows = lb.heatmap()
    by_cell = {(r["x"], r["y"]): r["counts"] for r in rows}
    assert by_cell[(1.0, 2.0)] == {"glitch": 2, "hang": 1, "crash": 0, "nothing": 1, "unobserved": 0}
    assert by_cell[(3.0, 4.0)] == {"glitch": 0, "hang": 0, "crash": 1, "nothing": 0, "unobserved": 0}


def test_logbook_heatmap_filters_by_z(tmp_path):
    lb = Logbook(tmp_path)
    lb.append({"id": "a", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    lb.append({"id": "b", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.5})
    rows = lb.heatmap(z=0.0)
    assert len(rows) == 1
    assert rows[0]["counts"]["glitch"] == 1


def test_logbook_get_by_id(tmp_path):
    lb = Logbook(tmp_path)
    lb.append({"id": "needle", "outcome": "glitch", "x": 1, "y": 1})
    lb.append({"id": "hay", "outcome": "nothing", "x": 0, "y": 0})
    found = lb.get("needle")
    assert found is not None
    assert found["id"] == "needle"
