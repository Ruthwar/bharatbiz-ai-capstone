# Scenario-fixture quality review

Reviewed 2026-11-15. This review is observational; fixture ownership remains with the scenario owner. No fixture was modified.

## Inventory

- `data/synthetic/scenarios.csv` and `scenarios.json` contain eight stable scenario definitions (`SCN-001` through `SCN-008`).
- `data/synthetic/scenario_fixtures/SCN-003.json` is the only executable fixture currently present.
- The remaining seven scenario definitions do not yet have fixture files or handlers. This is an explicit coverage gap, not an inferred failure.

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

The fixture is suitable for the current supplier-delay demonstration. Its unknowns correctly prevent the message from supplying an invented date, quantity or purchase-order reference. The fixture depends on the versioned state and should be re-reviewed whenever that state version changes.

The seven unmaterialised definitions should be treated as future work: create fixtures and handlers only under their existing owners, then add the same state-version, identity, units, cash and evidence checks before execution.
