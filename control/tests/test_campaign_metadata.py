from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from emfi_protocol.campaigns import CampaignMetadataUpdate

from control.campaign_metadata import CampaignMetadataStore
from control.deps import get_ctx
from control.routers import campaigns


@dataclass
class _Context:
    campaign_metadata: CampaignMetadataStore


def test_campaign_metadata_store_persists_and_normalizes_tags(tmp_path):
    path = tmp_path / "campaign_metadata.json"
    store = CampaignMetadataStore(path)

    updated = store.update(
        "camp-1",
        CampaignMetadataUpdate(
            notes="scope showed UART edge",
            tags=[" uart ", "glitch", "uart", ""],
        ),
    )

    assert updated.notes == "scope showed UART edge"
    assert updated.tags == ["uart", "glitch"]
    loaded = CampaignMetadataStore(path).get("camp-1")
    assert loaded.notes == "scope showed UART edge"
    assert loaded.tags == ["uart", "glitch"]
    assert loaded.updated_at is not None


def test_campaign_metadata_endpoints_get_and_update(tmp_path):
    store = CampaignMetadataStore(tmp_path / "campaign_metadata.json")
    app = FastAPI()
    app.include_router(campaigns.router)
    app.dependency_overrides[get_ctx] = lambda: _Context(store)
    client = TestClient(app)

    empty = client.get("/campaigns/camp-1/metadata")
    assert empty.status_code == 200
    assert empty.json()["notes"] == ""
    assert empty.json()["tags"] == []

    updated = client.put(
        "/campaigns/camp-1/metadata",
        json={"notes": "interesting window", "tags": ["glitch", "stable", "glitch"]},
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "interesting window"
    assert updated.json()["tags"] == ["glitch", "stable"]
