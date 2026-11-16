# Scenario-fixture quality review

Reviewed 2026-11-16 against the merged project. Fixture ownership remains with the scenario owner; this documentation update does not modify any fixture.

## Inventory

- `data/synthetic/scenarios.csv` and `scenarios.json` contain eight stable benchmark definitions (`SCN-001` through `SCN-008`).
- `data/synthetic/scenario_fixtures/` contains nine executable fixtures (`SCN-001` through `SCN-009`), including the additional smaller-pack request variant.
- `python scripts/evaluate_scenarios.py` passes all nine fixtures: **9/9 passed**. Each fixture has a registered handler and scenario-specific expectations.

## SCN-003 checks

| Check | Result |
| --- | --- |
| Stable scenario id matches the definition | Pass |
| Message source is synthetic supplier update | Pass |
| Sender party matches `SUP-005` | Pass |
| SKU is `SKU-003` and is consistent with the message | Pass |
| State version matches `business_state.json` | Pass |
| Planning horizon is present and ISO-formatted | Pass |
| Revised date, stated quantity and purchase-order reference remain explicit unknowns | Pass |
| Fixture changes operational data ownership | No; this review is read-only |

## Data-quality findings

The fixture is suitable for the supplier-delay demonstration. Its unknowns correctly prevent the message from supplying an invented date, quantity or purchase-order reference. The fixture depends on the versioned state and should be re-reviewed whenever that state version changes.

All nine fixtures now have handlers and pass the scenario evaluator. The eight base definitions in `scenarios.csv/json` remain unchanged; `SCN-009` is an additional executable variant. Fixture validation and scenario-specific assertions cover identity, state version, units, operational outcomes and review behavior.
