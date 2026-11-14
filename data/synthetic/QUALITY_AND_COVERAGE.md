# Synthetic Dataset Quality & Coverage Note

* **Author:** Varsha (Member 5 — RAG, Data Collection & Dataset Quality)
* **Date:** 2026-11-14
* **Directory Audited:** `data/synthetic/`
* **Reference Schema:** `data/synthetic/DATA_DICTIONARY.md`
* **Dataset Status:** Regenerated (`v2`) — `v1` confirmed excluded/historical-only.

---

## 1. Version, Lineage & Reproducibility
* **Generator Script:** `scripts/generate_synthetic_data.py` (fixed seed; deterministic output).
* **Synthetic Isolation:** Every transactional and master CSV table explicitly carries a `source_type` column, and `retailers.csv` carries a `verified_business` flag. `messages.jsonl` and `events.jsonl` are strictly separated from any permissioned pilot data.
* **Unknown Fact Handling:** Missing or unverified source facts remain explicitly `unknown` rather than being imputed.

---

## 2. Table Inventory & Schema Audit

| File Name | Row Count | Primary Key (`ID`) | Foreign Keys | Lineage / Guardrail Columns | Status |
| :--- | :---: | :--- | :--- | :--- | :--- |
| `products.csv` | 12 | `sku_id` | None | `source_type` | Verified |
| `suppliers.csv` | 5 | `supplier_id` | None | `source_type` | Verified |
| `retailers.csv` | 20 | `retailer_id` | None | `source_type`, `verified_business` | Verified |
| `supplier_products.csv` | 47 | `(supplier_id, sku_id)` | `supplier_id`, `sku_id` | `source_type` | Verified (47/60 valid pairs) |
| `inventory.csv` | 12 | `sku_id` | `sku_id` | `source_type` | Verified (1:1 with `products.csv`) |
| `historical_order_lines.csv` | 80 | `order_id` (line-level) | `retailer_id`, `sku_id` | `source_type` | Verified |
| `open_orders.csv` | 30 | `order_id` | `retailer_id`, `sku_id` | `source_type` | Verified |
| `supplier_deliveries.csv` | 50 | `delivery_id` | `purchase_order_id`, `supplier_id`, `sku_id` | `source_type` | Verified |
| `cash_ledger.csv` | 30 | `entry_id` | None | `source_type` | Verified |
| `scenarios.csv` / `scenarios.json` | 8 | `scenario_id` | None | Benchmark definitions | Verified (8 cases) |
| `messages.jsonl` | 1,000 | Message ID | Entity references | Synthetic intake messages | Verified |
| `events.jsonl` | 1,000 | Event ID | `supplier_id`, `retailer_id`, `sku_id` | Evidence-linked annotations | Verified |
| `business_state.json` | 1 object | Snapshot | Aggregates ledger/inventory | Point-in-time state | Verified |
| `scenario_fixtures/SCN-003.json` | 1 fixture | `SCN-003` | `scenario_id` | Deterministic test fixture | Verified |

---

## 3. Data Quality & Consistency Checks
* **Stable IDs & Display Labels:** `supplier_id`, `retailer_id`, and `sku_id` serve as deterministic internal join keys across all relational tables. `supplier_name`, `retailer_name`, `shop_type`, and `area` are display-only labels; `events.jsonl` stores both quoted trade names and matching internal IDs.
* **Units & Currency Standardization:**
  * Monetary columns (`unit_cost_rupees`, `amount_rupees`, `minimum_buffer_rupees`) use exact decimal INR rounded to 2 decimal places.
  * Quantity columns (`quantity_units`, `on_hand_units`, `reserved_units`, `incoming_units`, `reorder_point_units`, `min_order_units`, `capacity_units`) pair with explicit `unit` / `base_unit` / `units_per_case` fields.
  * Dates (`entry_date`, `order_date`, `requested_delivery_date`, `as_of_date`, `planned_date`, `actual_date`) follow ISO 8601 (`YYYY-MM-DD`), and timestamps include `+05:30` (IST).
* **Domain Constraints:**
  * Supplier quotes/orders are restricted strictly to the 47 valid `(supplier_id, sku_id)` rows in `supplier_products.csv`.
  * `supplier_deliveries.csv` explicitly tracks schedule variance via `planned_date`, `actual_date`, `delay_days`, and `status`.

---

## 4. Coverage & Team Handoffs
* **Coverage Summary:** Covers 12 FMCG/retail SKUs across 5 suppliers and 20 retailers (`shop_type`, `area`, `service_priority`), backed by 80 historical order lines, 30 open orders, 50 supplier deliveries, 30 cash ledger entries, 8 end-to-end scenarios (`scenarios.csv` / `scenarios.json`), and 1,000 message-event pairs.
* **Handoff to Ruthwar & Rajesh (Labels & Evidence):**
  * Use `events.jsonl` (`entities` + event labels) paired with `messages.jsonl` for intake extraction and classification evaluation.
  * Ground operational status labels using `open_orders.csv` (`status`, `priority`), `supplier_deliveries.csv` (`status`, `delay_days`), and `cash_ledger.csv` (`entry_type`, `minimum_buffer_rupees`).
* **Handoff to Workflow / Dashboard:**
  * Filter/badge synthetic records using `source_type` across all tables and `verified_business` on `retailers.csv`.