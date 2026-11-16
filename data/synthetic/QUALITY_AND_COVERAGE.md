# Synthetic Dataset Quality & Coverage Note

* **Author:** Varsha (Member 5 — RAG, Data Collection & Dataset Quality)
* **Date:** 2026-11-14
* **Directory Audited:** `data/synthetic/`
* **Reference Schema:** `data/synthetic/DATA_DICTIONARY.md`
* **Dataset Status:** Regenerated (`v2`) — `v1` confirmed excluded/historical-only.
* **Executable Validation:** Run `python data/data_check.py` from any working directory.

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
| `supplier_products.csv` | 47 | `(supplier_id, sku_id)` | `supplier_id`, `sku_id` | `source_type` | Verified (47/60 listed pairs) |
| `inventory.csv` | 12 | `sku_id` | `sku_id` | `source_type` | Verified (1:1 with `products.csv`) |
| `historical_order_lines.csv` | 80 | `order_id` (line-level) | `retailer_id`, `sku_id` | `source_type` | Verified |
| `open_orders.csv` | 30 | `order_id` | `retailer_id`, `sku_id` | `source_type` | Verified |
| `supplier_deliveries.csv` | 50 | `delivery_id` | `supplier_id`, `sku_id` | `source_type` | Verified against listed offers |
| `scheduled_receivables.csv` | 30 | `receivable_id` | `retailer_id` | `currency`, `state_version`, `source_type` | Verified |
| `retailer_complaints.csv` | 25 | `complaint_id` | `retailer_id`, `sku_id` | `state_version`, `source_type` | Verified |
| `market_observations.csv` | 30 | `observation_id` | `source_id`, `retailer_id`, `sku_id` | `corroboration_status`, `confidence`, `state_version`, `source_type` | Verified |
| `cash_ledger.csv` | 30 | `entry_id` | None | `source_type` | Verified |
| `scenarios.csv` / `scenarios.json` | 8 | `scenario_id` | None | Benchmark definitions | Verified (8 definitions) |
| `messages.jsonl` | 1,000 | Message ID | Entity references in `entities` | Synthetic intake messages | Verified |
| `events.jsonl` | 1,000 | Event ID | `source_message_ids` → `messages.jsonl` | Event labels, full-source evidence spans and review metadata | Verified (structure and 1:1 links) |
| `business_state.json` | 1 object | Snapshot | Aggregates ledger/inventory | Point-in-time state | Verified |
| `scenario_fixtures/SCN-001.json` through `SCN-009.json` | 9 fixtures | `SCN-001` through `SCN-009` | `scenario_id` | Deterministic test fixtures | Verified (9/9 evaluations passing) |

`purchase_order_id` in `supplier_deliveries.csv` is a synthetic reference identifier; there is no purchase-order master table in this dataset version. `events.jsonl` does not contain extracted entity facts. The three extended tables are state-versioned and validated by `data/data_check.py`.

---

## 3. Data Quality & Consistency Checks
* **Stable IDs & Display Labels:** `supplier_id`, `retailer_id`, and `sku_id` serve as deterministic internal join keys across the relational tables. `supplier_name`, `retailer_name`, `shop_type`, and `area` are display-only labels. The JSON-string `entities` field in `messages.jsonl` stores trade names and matching internal IDs where applicable.
* **Units & Currency Standardization:**
  * Monetary columns (`unit_cost_rupees`, `amount_rupees`, `minimum_buffer_rupees`) use exact decimal INR rounded to 2 decimal places.
  * Quantity columns (`quantity_units`, `on_hand_units`, `reserved_units`, `incoming_units`, `reorder_point_units`, `min_order_units`, `capacity_units`) use the SKU's explicit `base_unit`; order and inventory rows also carry `unit`.
  * Dates (`entry_date`, `order_date`, `requested_delivery_date`, `as_of_date`, `planned_date`, `actual_date`) follow ISO 8601 (`YYYY-MM-DD`), and message timestamps include `+05:30` (IST).
* **Domain Constraints:**
  * Supplier offers and all 50 supplier-delivery rows are restricted to the 47 listed `(supplier_id, sku_id)` pairs in `supplier_products.csv`.
  * `supplier_deliveries.csv` explicitly tracks schedule variance via `planned_date`, `actual_date`, `delay_days`, and `status`.
  * `scheduled_receivables.csv` uses exact two-decimal INR strings and retailer foreign keys; complaint and market-observation rows use retailer/SKU foreign keys and the current state version.
* **Repeatable Checks:** `data/data_check.py` validates row counts, unique keys, synthetic lineage, retailer/SKU references, supplier-offer pairs, one-to-one message-event links, scenario CSV/JSON equality and timestamp formats. It also checks receivable status against due dates and complaint resolution notes against lifecycle status.

---

## 4. Coverage & Team Handoffs
* **Coverage Summary:** Covers 12 FMCG/retail SKUs across 5 suppliers and 20 retailers (`shop_type`, `area`, `service_priority`), backed by 80 historical order lines, 30 open orders, 50 supplier deliveries, 30 scheduled receivables, 25 retailer complaints, 30 market observations, 30 cash ledger entries, 8 base scenario definitions (`scenarios.csv` / `scenarios.json`), and 1,000 message-event pairs. Nine executable fixtures (`SCN-001` through `SCN-009`) are present and all nine pass `python scripts/evaluate_scenarios.py`; `SCN-009` is an additional smaller-pack request variant.
* **Handoff to Ruthwar & Rajesh (Labels & Evidence):**
  * Use `messages.jsonl` (`intent`, JSON-string `entities`, `evidence_span`, and `uncertainty`) for intake extraction and classification evaluation.
  * Use `events.jsonl` (`source_message_ids`, `event_type`, `evidence_spans`, and review metadata) for event-routing and review evaluation, not as a source of extracted entity facts.
  * Ground operational status labels using `open_orders.csv` (`status`, `priority`), `supplier_deliveries.csv` (`status`, `delay_days`), and `cash_ledger.csv` (`entry_type`, `minimum_buffer_rupees`).
* **Handoff to Workflow / Dashboard:**
  * Filter/badge synthetic records using `source_type` across all transactional/master tables and `verified_business` on `retailers.csv`.
