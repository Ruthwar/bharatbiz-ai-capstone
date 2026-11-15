from pathlib import Path

from app.orchestration.inbound import process_inbound
from app.orchestration.workflow import process_message
from app.scenarios.registry import get_scenario, list_scenarios, validate_scenario
from app.state import load_business_state
from app.store.ledger import InboundLedger, ledger as default_ledger

DEMO_OUTCOMES = {
    "SCN-001": "Stock-only: 70/70 pieces fulfilled; no late or unmet units.",
    "SCN-002": "SUP-001: 112/112 pieces fulfilled with 47 procured; no late or unmet units.",
    "SCN-003": "SUP-002: 102/102 litre units fulfilled, 28 late and zero unmet; cost ₹4,876.46.",
    "SCN-004": "Stock-only actual view: 68/102 litre units fulfilled and 34 unmet; on-time-receipt counterfactual selects SUP-005.",
    "SCN-005": "SUP-001: preserve book stock 63 beside physical count 48; procure 19 pieces and leave zero unmet.",
    "SCN-006": "Ask for the order reference; two orders match and no allocation plan is created.",
    "SCN-007": "Two reports from two distinct reporters; corroborated but unverified, with no automatic competitive action.",
    "SCN-008": "Stock-only: 56/166 litre units fulfilled and 110 unmet; on-time-receipt counterfactual selects SUP-005.",
    "SCN-009": "Nine reported requests from three retailers; no catalogue match and no assortment change.",
}


def scenario_summaries() -> list[dict]:
    return [
        {
            "scenario_id": fixture.scenario_id,
            "name": fixture.name,
            "description": fixture.description,
            "target_sku_id": fixture.target_sku_id,
            "review_status": fixture.expected.get("review_status"),
            "demo_outcome": DEMO_OUTCOMES[fixture.scenario_id],
            "message": {
                "text": fixture.message.text,
                "language": fixture.message.language,
                "sender_type": fixture.message.sender.party_type,
                "sender_id": fixture.message.sender.party_id,
            },
        }
        for fixture in list_scenarios()
    ]


def run_scenario(
    scenario_id: str,
    data_dir: Path | None = None,
    persist: bool = False,
    ledger: InboundLedger | None = None,
) -> dict:
    fixture = get_scenario(scenario_id)
    if fixture.message is None:
        raise ValueError(f"{scenario_id}: scenario message is required")
    state = load_business_state(data_dir=data_dir, expected_version=fixture.message.state_version)
    validate_scenario(fixture, state)
    if not persist:
        return process_message(fixture.message, data_dir=data_dir, scenario=fixture)

    inbound = process_inbound(
        fixture.message,
        ledger=ledger or default_ledger,
        data_dir=data_dir,
        scenario=fixture,
    )
    result = inbound.get("result")
    if result is None:
        raise ValueError(f"{scenario_id}: scenario did not produce a processing result")
    return {**result, "inbound": {key: value for key, value in inbound.items() if key != "result"}}
