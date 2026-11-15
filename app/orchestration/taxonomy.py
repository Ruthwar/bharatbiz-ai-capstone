"""Routing vocabulary. Closed for handlers, open for understanding (see docs/INTAKE_DESIGN.md)."""

TAXONOMY_VERSION = "0.1"

INTENTS = (
    "baseline",
    "demand_spike",
    "supplier_delay",
    "limited_cash",
    "stock_discrepancy",
    "delivery_complaint",
    "damaged_item",
    "missing_item",
    "product_request",
    "scheme_question",
    "competitor_observation",
    "combined_disruption",
    "other",
)

UNCLASSIFIED = "unclassified"

ACTIONABLE_INTENTS = (
    "baseline",
    "demand_spike",
    "supplier_delay",
    "limited_cash",
    "stock_discrepancy",
    "delivery_complaint",
    "competitor_observation",
    "product_request",
    "combined_disruption",
)
