from __future__ import annotations

import pytest
from pydantic import ValidationError

from emfi_protocol.campaigns import (
    Campaign,
    CampaignBudgets,
    CampaignTiming,
    GridParams,
    SlotConfig,
    SweepParams,
    SweepRange,
    TimelineAction,
    TimingReference,
)


def _base_campaign_payload() -> dict:
    return {
        "name": "dual-smoke",
        "project_id": "ectf-dut",
        "build_sha": "dut-sha",
        "grid": GridParams(origin=(0.0, 0.0), top_right=(0.0, 0.0)),
        "sweep": SweepParams(attempts_per_point=1),
    }


def _dual_payload() -> dict:
    payload = _base_campaign_payload()
    payload.update(
        {
            "mode": "dual_target",
            "slots": {
                "dut": SlotConfig(
                    project_id="ectf-dut",
                    build_sha="dut-sha",
                    power_rail="scaffold.dut",
                    programmer="xds110:dut",
                    uart="uart0",
                    glitcher="chipshouter",
                ),
                "platform": SlotConfig(
                    project_id="ectf-platform",
                    build_sha="platform-sha",
                    power_rail="scaffold.platform",
                    programmer="xds110:platform",
                    uart="uart1",
                    glitcher="husky",
                ),
            },
            "timing": CampaignTiming(
                reference=TimingReference(source="dut.gpio.d0"),
                timeline=[
                    TimelineAction(
                        at_us=0.0,
                        target="dut",
                        device="scaffold",
                        action="wait_for_trigger",
                        source="dut.gpio.d0",
                    ),
                    TimelineAction(
                        at_us=1.2,
                        target="dut",
                        device="chipshouter",
                        action="emfi_pulse",
                        delay_sweep="emfi_delay_us",
                        width_sweep="emfi_width_ns",
                        voltage_sweep="emfi_voltage_v",
                    ),
                    TimelineAction(
                        at_us=1.6,
                        target="platform",
                        device="husky",
                        action="crowbar_pulse",
                        delay_sweep="crowbar_delay_us",
                        width_sweep="crowbar_width_ns",
                    ),
                ],
            ),
            "sweeps": {
                "emfi_delay_us": SweepRange(start=0.8, stop=2.0, step=0.1),
                "emfi_width_ns": SweepRange(start=80, stop=80, step=1),
                "emfi_voltage_v": SweepRange(start=250, stop=250, step=1),
                "crowbar_delay_us": SweepRange(start=1.0, stop=2.5, step=0.1),
                "crowbar_width_ns": SweepRange(start=40, stop=120, step=20),
            },
            "budgets": CampaignBudgets(max_attempts=1000, max_runtime_s=1800),
        }
    )
    return payload


def test_single_target_campaign_remains_backwards_compatible():
    campaign = Campaign.model_validate(_base_campaign_payload())

    assert campaign.mode == "single_target"
    assert campaign.slots is None
    assert campaign.timing is None


def test_dual_target_campaign_accepts_slot_timing_sweep_and_budget_fields():
    campaign = Campaign.model_validate(_dual_payload())

    assert campaign.mode == "dual_target"
    assert campaign.slots is not None
    assert campaign.slots["platform"].glitcher == "husky"
    assert campaign.timing is not None
    assert campaign.timing.timeline[-1].action == "crowbar_pulse"
    assert campaign.budgets is not None
    assert campaign.budgets.max_attempts == 1000


def test_dual_target_campaign_requires_all_extension_blocks():
    payload = _base_campaign_payload()
    payload["mode"] = "dual_target"

    with pytest.raises(ValidationError, match="dual_target campaigns require"):
        Campaign.model_validate(payload)


def test_dual_target_campaign_rejects_unknown_timeline_sweep():
    payload = _dual_payload()
    assert isinstance(payload["timing"], CampaignTiming)
    payload["timing"].timeline[1].delay_sweep = "missing_delay"

    with pytest.raises(ValidationError, match="unknown sweep"):
        Campaign.model_validate(payload)


def test_dual_target_timeline_must_be_ordered():
    with pytest.raises(ValidationError, match="ordered by at_us"):
        CampaignTiming(
            reference=TimingReference(source="dut.gpio.d0"),
            timeline=[
                TimelineAction(
                    at_us=2.0,
                    target="platform",
                    device="husky",
                    action="crowbar_pulse",
                ),
                TimelineAction(
                    at_us=1.0,
                    target="dut",
                    device="chipshouter",
                    action="emfi_pulse",
                ),
            ],
        )
