"""Routing vocabulary. Closed for handlers, open for understanding (see docs/INTAKE_DESIGN.md)."""

TAXONOMY_VERSION = "0.1"

INTENTS = (
    "supplier_delay",
    "delivery_complaint",
    "damaged_item",
    "missing_item",
    "product_request",
    "scheme_question",
    "competitor_observation",
    "other",
)

UNCLASSIFIED = "unclassified"

ACTIONABLE_INTENTS = ("supplier_delay",)
