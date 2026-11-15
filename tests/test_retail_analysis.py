from app.agents.market import group_themes
from app.agents.orders import allocate_by_priority, analyze_fulfilment
from app.orchestration.drafts import LANGUAGES, build_draft, check_draft


def test_priority_fulfilment_is_additive_and_conserves_scn003_stock(state):
    result = analyze_fulfilment(state, "SKU-003")

    assert result.by_sku[0].available_units == 56
    assert result.by_sku[0].requested_units == 102
    assert result.by_sku[0].allocated_units == 56
    assert result.by_sku[0].unmet_units == 46
    assert result.verification_violations == []
    assert result.changed_vs_fifo
    assert sum(row.allocated_units for row in result.allocations) == 56


def test_incompatible_order_units_are_not_converted(state):
    changed = state.model_copy(deep=True)
    changed.open_orders[0]["unit"] = "cases"

    rows = allocate_by_priority(changed, changed.open_orders[0]["sku_id"])
    row = next(row for row in rows if row.order_id == changed.open_orders[0]["order_id"])
    result = analyze_fulfilment(changed, changed.open_orders[0]["sku_id"])

    assert row.allocated_units == 0
    assert row.unmet_units == row.requested_units
    assert f"incompatible_unit:{row.order_id}" in result.verification_violations


def test_generated_reply_drafts_are_safe_in_all_supported_languages():
    for language in LANGUAGES:
        complaint = build_draft(
            "evt-language",
            "RET-001",
            "complaint_ack",
            language,
            category="damaged_item",
            product_label="Cooking oil 5 L tin",
            order_id="ORD-0016",
        )
        request = build_draft(
            "evt-request",
            "RET-001",
            "request_ack",
            language,
            product_label="Toothpaste case",
        )
        assert complaint is not None
        assert request is not None
        assert complaint.safety_violations == []
        assert complaint.requires_approval is True
        assert complaint.sent_automatically is False


def test_draft_safety_rejects_operational_claims_and_empty_edits():
    assert check_draft("   ") == ["empty_text"]
    assert "mentions_money" in check_draft("We will refund ₹500")
    assert "mentions_date_or_time" in check_draft("We will call tomorrow")
    assert "makes_commitment" in check_draft("We will replace it")
    assert "states_cause" in check_draft("It happened because of the courier")
    assert "suggests_substitute" in check_draft("We can offer a substitute")
    assert "asks_question" in check_draft("Can we call you?")
    assert "contains_number" in check_draft("Your 2 items are noted")
    assert check_draft("Report for ORD-0016 is noted", ["ORD-0016"]) == []


def test_market_themes_do_not_cross_corroborate_offers_or_missing_reporters():
    base = {
        "signal_type": "competitor_observation",
        "subject": "ValueMart",
        "competitor_name": "ValueMart",
        "product_label": "Rice 5 kg bag",
        "area": "Kukatpally",
        "observed_at": "2026-11-01T06:30:00+00:00",
        "observation_text": "20 percent off",
        "evidence_span": "20 percent off",
        "source_message_id": "m-1",
    }
    rows = [
        {**base, "observation_id": "o1", "event_id": "e1", "offer": "20 percent off", "reporter_id": "REP-1"},
        {**base, "observation_id": "o2", "event_id": "e2", "offer": "20 percent off", "reporter_id": "REP-2"},
        {**base, "observation_id": "o3", "event_id": "e3", "offer": "10 percent off", "reporter_id": "REP-3"},
        {**base, "observation_id": "o4", "event_id": "e4", "offer": "20 percent off", "reporter_id": None},
    ]

    themes = group_themes(rows)
    corroborated = next(theme for theme in themes if theme.offer == "20 percent off")
    separate = next(theme for theme in themes if theme.offer == "10 percent off")

    assert corroborated.distinct_reporters == 2
    assert corroborated.label == "corroborated_unverified"
    assert separate.distinct_reporters == 1
    assert separate.label == "single_reporter_unverified"
