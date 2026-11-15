from threading import Lock

from app.orchestration.drafts import check_draft
from app.store.ledger import ReviewDecisionError

_review_lock = Lock()


class DraftSafetyError(ValueError):
    pass


def decide_review(
    ledger,
    store,
    event_id: str,
    decision: str,
    reviewer: str,
    draft_id: str | None = None,
    note: str | None = None,
    final_text: str | None = None,
) -> dict | None:
    with _review_lock:
        record = ledger.get_review(event_id)
        if record is None:
            return None
        if record["review_status"] != "pending_review":
            raise ReviewDecisionError(f"review {event_id} is already {record['review_status']}")
        linked_draft = record.get("draft_id")
        if linked_draft and linked_draft != draft_id:
            raise ReviewDecisionError("draft reviews must use the retail draft review endpoint")
        if linked_draft:
            draft = store.get_draft(linked_draft)
            if draft is None:
                raise LookupError(f"draft {linked_draft} not found")
            warnings = check_draft(final_text, draft["allowed_tokens"]) if final_text is not None else []
            if warnings:
                raise DraftSafetyError("edited draft failed safety checks: " + ", ".join(warnings))
            store.record_draft_review(linked_draft, decision, reviewer, note, final_text, warnings)
        elif draft_id:
            raise ReviewDecisionError("this review item has no linked response draft")
        return ledger.decide(event_id, decision, reviewer)
