from pathlib import Path

from app.observability import trace_scope
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
    "SCN-010": "RET-016 has ₹57,448.23 past due; a 30 kg order worth ₹4,620.00 takes exposure to ₹62,068.23, above the ₹50,000.00 limit. Holding the order is the only feasible outcome; pausing existing orders adds delay and accepting it is infeasible. Human credit review.",
    "SCN-011": "SCM-002 allows 7.50% from 40 units; the claimed 10% on 30 units mismatches. No discount or credit note is applied.",
    "SCN-012": "DEL-9001: 60 ordered, 52 received, 5 damaged and 3 wrong; 44 usable and 16 short. A supplier claim needs human approval.",
    "SCN-013": "RCL-001 holds BATCH-004 (SKU-005); up to 110 units are free to quarantine and 4 open orders are affected. Quarantine is the only feasible outcome; releasing the batch is infeasible. Human approval only.",
    "SCN-014": "BATCH-002 expires on 2026-12-02, 9 days away and inside the 14-day return window; return or priority dispatch is recommended.",
    "SCN-015": "RTE-001 has 40 units of capacity against 47 units of demand. All 7 feasible load plans are compared; the best loads ORD-0001 and ORD-0018 (26 units) and defers ORD-0006. The load plan needs human approval.",
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
    decision_mode: str = "deterministic",
) -> dict:
    fixture = get_scenario(scenario_id)
    if fixture.message is None:
        raise ValueError(f"{scenario_id}: scenario message is required")
    state = load_business_state(data_dir=data_dir, expected_version=fixture.message.state_version)
    validate_scenario(fixture, state)
    with trace_scope(f"scenario:{scenario_id}", scenario_id=scenario_id, source="scenario"):
        if not persist:
            return process_message(
                fixture.message, data_dir=data_dir, scenario=fixture, decision_mode=decision_mode
            )

        inbound = process_inbound(
            fixture.message,
            ledger=ledger or default_ledger,
            data_dir=data_dir,
            scenario=fixture,
            decision_mode=decision_mode,
        )
    result = inbound.get("result")
    if result is None:
        raise ValueError(f"{scenario_id}: scenario did not produce a processing result")
    return {**result, "inbound": {key: value for key, value in inbound.items() if key != "result"}}
