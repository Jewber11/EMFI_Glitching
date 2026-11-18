from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from control.logbook import Logbook
from control.deps import get_ctx
from control.routers import runs
from control.routers.runs import export_runs


@dataclass
class _Context:
    logbook: Logbook


def _rows(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.body.decode("utf-8"))))


@pytest.mark.asyncio
async def test_runs_export_csv_filters_campaign_and_json_encodes_verdict(tmp_path):
    logbook = Logbook(tmp_path)
    logbook.append(
        {
            "id": "a",
            "campaign_id": "camp-1",
            "outcome": "glitch",
            "x": 1.0,
            "y": 2.0,
            "z": 0.0,
            "verdict": {"fault": True, "heartbeat_alive": True, "campaign_complete": False},
            "build_sha": "abc123",
        }
    )
    logbook.append(
        {
            "id": "b",
            "campaign_id": "camp-2",
            "outcome": "nothing",
            "x": 3.0,
            "y": 4.0,
            "z": 0.0,
        }
    )

    response = await export_runs(
        format="csv",
        campaign="camp-1",
        since=None,
        outcome=None,
        ctx=_Context(logbook),
    )

    assert response.media_type == "text/csv; charset=utf-8"
    assert "emfi-runs-camp-1.csv" in response.headers["content-disposition"]
    rows = _rows(response)
    assert [row["id"] for row in rows] == ["a"]
    assert rows[0]["build_sha"] == "abc123"
    assert rows[0]["verdict"] == '{"fault":true,"heartbeat_alive":true,"campaign_complete":false}'


@pytest.mark.asyncio
async def test_runs_export_csv_filters_outcome(tmp_path):
    logbook = Logbook(tmp_path)
    logbook.append({"id": "a", "outcome": "glitch", "x": 0, "y": 0})
    logbook.append({"id": "b", "outcome": "hang", "x": 0, "y": 0})

    response = await export_runs(
        format="csv",
        campaign=None,
        since=None,
        outcome="hang",
        ctx=_Context(logbook),
    )

    assert [row["id"] for row in _rows(response)] == ["b"]


@pytest.mark.asyncio
async def test_runs_export_parquet_is_explicitly_unimplemented(tmp_path):
    with pytest.raises(HTTPException) as excinfo:
        await export_runs(
            format="parquet",
            campaign=None,
            since=None,
            outcome=None,
            ctx=_Context(Logbook(tmp_path)),
        )

    assert excinfo.value.status_code == 501


def test_runs_export_route_precedes_run_id_route(tmp_path):
    logbook = Logbook(tmp_path)
    logbook.append({"id": "a", "outcome": "glitch", "x": 0, "y": 0})
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[get_ctx] = lambda: _Context(logbook)

    response = TestClient(app).get("/runs/export")

    assert response.status_code == 200
    assert response.text.splitlines()[0].startswith("id,ts,session")


def test_runs_list_filters_heatmap_drilldown_query(tmp_path):
    logbook = Logbook(tmp_path)
    logbook.append({"id": "a", "campaign_id": "camp-1", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    logbook.append({"id": "b", "campaign_id": "camp-1", "outcome": "hang", "x": 1.0, "y": 2.0, "z": 0.0})
    logbook.append({"id": "c", "campaign_id": "camp-1", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 1.0})
    logbook.append({"id": "d", "campaign_id": "camp-2", "outcome": "glitch", "x": 1.0, "y": 2.0, "z": 0.0})
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[get_ctx] = lambda: _Context(logbook)

    response = TestClient(app).get(
        "/runs",
        params={
            "campaign_id": "camp-1",
            "x": 1.0,
            "y": 2.0,
            "z": 0.0,
            "outcome": "glitch",
        },
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["a"]
