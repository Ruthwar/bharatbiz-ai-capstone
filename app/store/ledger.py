"""In-memory ledger for the demo: dedup, open slot-filling intakes, and the human review queue."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


@dataclass
class PendingIntake:
    conversation_id: str
    message_ids: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    rounds: int = 0


class InboundLedger:
    def __init__(self) -> None:
        self._lock = Lock()
        self._results: dict[str, dict] = {}
        self._intakes: dict[str, PendingIntake] = {}
        self._queue: dict[str, dict] = {}

    def get_result(self, message_id: str) -> dict | None:
        with self._lock:
            return self._results.get(message_id)

    def record_result(self, message_id: str, result: dict) -> None:
        with self._lock:
            self._results[message_id] = result

    def get_intake(self, conversation_id: str) -> PendingIntake | None:
        with self._lock:
            return self._intakes.get(conversation_id)

    def open_intake(self, conversation_id: str, message_id: str, text: str, rounds: int) -> PendingIntake:
        with self._lock:
            intake = self._intakes.get(conversation_id)
            if intake is None:
                intake = PendingIntake(conversation_id=conversation_id)
                self._intakes[conversation_id] = intake
            if message_id not in intake.message_ids:
                intake.message_ids.append(message_id)
                intake.texts.append(text)
            intake.rounds = rounds
            return intake

    def close_intake(self, conversation_id: str) -> None:
        with self._lock:
            self._intakes.pop(conversation_id, None)

    def queue_for_review(self, event_id: str, record: dict) -> None:
        with self._lock:
            record.setdefault("received_at", datetime.now(timezone.utc).isoformat())
            record["review_status"] = record.get("review_status", "pending_review")
            self._queue[event_id] = record

    def pending_reviews(self) -> list[dict]:
        with self._lock:
            return [
                record for record in self._queue.values() if record["review_status"] == "pending_review"
            ]

    def decide(self, event_id: str, decision: str, reviewer: str) -> dict | None:
        with self._lock:
            record = self._queue.get(event_id)
            if record is None:
                return None
            record["review_status"] = "approved" if decision == "approve" else "rejected"
            record["reviewer"] = reviewer
            record["decided_at"] = datetime.now(timezone.utc).isoformat()
            return record

    def reset(self) -> None:
        with self._lock:
            self._results.clear()
            self._intakes.clear()
            self._queue.clear()


ledger = InboundLedger()
