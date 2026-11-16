# Inventory Agent — Contract & Behaviour (Owner: Saurabh)

## Inputs
The agent reads from `BusinessState`:
- `inventory[]` rows for the requested `sku_id`
- `open_orders[]` (read-only, for the demand baseline)
- `state_version` (string), `as_of` (date)
- `open_orders` field is consumed only to compute `open_demand_units`; the agent never writes to it.

Required inventory row fields:
`sku_id, on_hand_units, reserved_units, incoming_units, reorder_point_units, unit`

Optional fields (warned about when absent):
`expiry_date (ISO 8601), warehouse_capacity_units`

## Outputs
`AgentResult` with `proposal`:

| Field | Meaning |
|---|---|
| `available_units` | on_hand − reserved (never negative) |
| `atp_units` | available + confirmed incoming (never negative) |
| `immediately_available_units` | ATP after removing delayed incoming |
| `open_demand_units` | sum of open order quantities for this SKU |
| `shortage_units` | max(0, open_demand − ATP) |
| `immediate_shortage_units` | max(0, open_demand − immediately_available) |
| `reorder_required` | on_hand ≤ reorder_point |
| `expiry_risk` | true if expiry_date within planning horizon |
| `assumptions[]` | unmet-data warnings, delay assumptions |

`evidence_refs` always include `inventory:<sku_id>` and `state_version`.

## Invariants
1. **No negative availability is ever returned.** Impossible inputs raise `ValueError`.
2. `reserved_units > on_hand_units` raises `ValueError` (silent clamping is forbidden).
3. All arithmetic is deterministic; no LLM call.
4. Delayed incoming must satisfy `0 <= delayed_incoming_units <= incoming_units`.

## Shortage vs. immediately-available — the distinction
- `shortage_units` uses **ATP** (available + incoming). It answers: "can total supply cover open demand eventually?"
- `open_demand − immediately_available` answers: "can on-hand supply cover open demand **right now**?"
- A supplier delay changes the second but may not change the first.
- Time-sensitive decisions (allocation, dispatch) must use `immediately_available`.
- Feasibility checks (whether any plan can fulfil demand) use `shortage_units`.

## Handoffs
- **Rajesh (orders):** use `atp_units` and `immediately_available_units` to size allocations; `shortage_units` triggers reallocation.
- **Rohit (supplier):** use `immediate_shortage_units` and `reorder_required` to size time-sensitive purchase proposals when supply is delayed. Use `shortage_units` for long-term ATP gaps. Incoming delay is passed in via `delayed_incoming_units`.
- **Ranjit (optimization/verification):** verify `on_hand − reserved + incoming == atp` and `shortage_units >= 0`.
- **Ruthwar (contracts/orchestration):** every result carries `state_version`; stale versions must be rejected upstream. `ValueError` from this agent should be caught and routed to triage/ABSTAIN.

## Demo
`python scripts/inventory_shortage_demo.py` prints before/after a supplier delay.

## Reproducible scenario (SCN-INV-DEMO)
- SKU-DEMO-1: on_hand=40, reserved=10, incoming=50, reorder_point=20
- Open demand: 70 units
- Baseline ATP: 80 → shortage_units=0
- After 40 of 50 incoming units are delayed: immediately_available=40, immediate shortfall=30