from app.store.ledger import SqliteLedger


def test_sqlite_ledger_survives_a_new_connection(tmp_path):
    path = tmp_path / "ledger.sqlite3"

    first = SqliteLedger(path)
    first.record_result("m-1", {"routed_action": "supplier_delay_planning"})
    first.open_intake("c-1", "m-1", "SUP-005 reports a delay", 1)
    first.queue_for_review("evt-1", {"event_id": "evt-1", "summary": "awaiting review"})

    second = SqliteLedger(path)

    assert second.get_result("m-1") == {"routed_action": "supplier_delay_planning"}
    intake = second.get_intake("c-1")
    assert intake.texts == ["SUP-005 reports a delay"]
    assert intake.rounds == 1
    assert [row["event_id"] for row in second.pending_reviews()] == ["evt-1"]


def test_sqlite_ledger_keeps_a_decision_after_restart(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    SqliteLedger(path).queue_for_review("evt-1", {"event_id": "evt-1", "summary": "awaiting review"})

    reopened = SqliteLedger(path)
    decided = reopened.decide("evt-1", "approve", "owner")

    assert decided["review_status"] == "approved"
    assert SqliteLedger(path).pending_reviews() == []


def test_close_intake_and_reset_clear_stored_state(tmp_path):
    ledger = SqliteLedger(tmp_path / "ledger.sqlite3")
    ledger.open_intake("c-1", "m-1", "hello", 1)
    ledger.queue_for_review("evt-1", {"event_id": "evt-1", "summary": "awaiting review"})

    ledger.close_intake("c-1")
    ledger.reset()

    assert ledger.get_intake("c-1") is None
    assert ledger.pending_reviews() == []
    assert ledger.decide("evt-1", "reject", "owner") is None
