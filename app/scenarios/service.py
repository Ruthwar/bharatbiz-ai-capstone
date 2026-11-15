from pathlib import Path

from app.orchestration.inbound import process_inbound
from app.orchestration.workflow import process_message
from app.scenarios.registry import get_scenario, list_scenarios, validate_scenario
from app.state import load_business_state
from app.store.ledger import InboundLedger, ledger as default_ledger


def scenario_summaries() -> list[dict]:
    return [
        {
            "scenario_id": fixture.scenario_id,
            "name": fixture.name,
            "description": fixture.description,
            "target_sku_id": fixture.target_sku_id,
            "review_status": fixture.expected.get("review_status"),
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
