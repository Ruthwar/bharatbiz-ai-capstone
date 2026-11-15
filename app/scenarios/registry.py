import json
from functools import lru_cache
from pathlib import Path

from app.scenarios.contracts import ScenarioFixture
from app.schemas.contracts import BusinessState

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "scenario_fixtures"


@lru_cache(maxsize=1)
def list_scenarios() -> tuple[ScenarioFixture, ...]:
    fixtures = [
        ScenarioFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(FIXTURE_DIR.glob("SCN-*.json"))
    ]
    identifiers = [fixture.scenario_id for fixture in fixtures]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate scenario fixture identifier")
    return tuple(fixtures)


def get_scenario(scenario_id: str) -> ScenarioFixture:
    try:
        return next(fixture for fixture in list_scenarios() if fixture.scenario_id == scenario_id)
    except StopIteration as exc:
        raise ValueError(f"Unknown scenario: {scenario_id}") from exc


def validate_scenario(fixture: ScenarioFixture, state: BusinessState) -> None:
    sku_ids = {row["sku_id"] for row in state.products}
    supplier_ids = {row["supplier_id"] for row in state.suppliers}
    retailer_ids = {row["retailer_id"] for row in state.retailers}
    order_ids = {row["order_id"] for row in state.open_orders}
    if fixture.target_sku_id and fixture.target_sku_id not in sku_ids:
        raise ValueError(f"{fixture.scenario_id}: unknown target SKU")
    if fixture.message and fixture.message.state_version != state.state_version:
        raise ValueError(f"{fixture.scenario_id}: fixture state version differs from business state")
    overlays = fixture.overlays
    if overlays.original_supplier_id and overlays.original_supplier_id not in supplier_ids:
        raise ValueError(f"{fixture.scenario_id}: unknown delayed supplier")
    unknown_orders = set(overlays.demand_order_ids) - order_ids
    if unknown_orders:
        raise ValueError(f"{fixture.scenario_id}: unknown demand orders {sorted(unknown_orders)}")
    receipt_ids = [receipt.receipt_id for receipt in overlays.receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise ValueError(f"{fixture.scenario_id}: duplicate receipt identifier")
    if any(receipt.retailer_id not in retailer_ids for receipt in overlays.receipts):
        raise ValueError(f"{fixture.scenario_id}: unknown receipt retailer")
