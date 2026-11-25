"""Routing vocabulary. Closed for handlers, open for understanding (see docs/INTAKE_DESIGN.md)."""

TAXONOMY_VERSION = "0.2"

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
    "credit_check",
    "scheme_claim",
    "delivery_discrepancy",
    "batch_recall",
    "short_dated_stock",
    "dispatch_planning",
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
    "credit_check",
    "scheme_claim",
    "delivery_discrepancy",
    "batch_recall",
    "short_dated_stock",
    "dispatch_planning",
)
