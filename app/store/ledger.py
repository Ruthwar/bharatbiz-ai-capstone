"""Ledger for the demo: dedup, open slot-filling intakes, and the human review queue.

`InboundLedger` keeps everything in memory. `SqliteLedger` has the same interface and survives a
restart; the API uses it by default so a review item is not lost when the server is restarted.
"""

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            record.setdefault("received_at", _now())
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
            record["decided_at"] = _now()
            return record

    def reset(self) -> None:
        with self._lock:
            self._results.clear()
            self._intakes.clear()
            self._queue.clear()


class SqliteLedger(InboundLedger):
    """Same interface as `InboundLedger`, backed by SQLite so state outlives the process."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = Lock()
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS results (
                    message_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS intakes (
                    conversation_id TEXT PRIMARY KEY,
                    message_ids TEXT NOT NULL,
                    texts TEXT NOT NULL,
                    rounds INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_queue (
                    event_id TEXT PRIMARY KEY,
                    review_status TEXT NOT NULL,
                    record TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def get_result(self, message_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM results WHERE message_id = ?", (message_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def record_result(self, message_id: str, result: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO results (message_id, payload) VALUES (?, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET payload = excluded.payload",
                (message_id, json.dumps(result, ensure_ascii=False)),
            )
            self._conn.commit()

    def get_intake(self, conversation_id: str) -> PendingIntake | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT conversation_id, message_ids, texts, rounds FROM intakes WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return PendingIntake(
            conversation_id=row[0],
            message_ids=json.loads(row[1]),
            texts=json.loads(row[2]),
            rounds=row[3],
        )

    def open_intake(self, conversation_id: str, message_id: str, text: str, rounds: int) -> PendingIntake:
        intake = self.get_intake(conversation_id) or PendingIntake(conversation_id=conversation_id)
        if message_id not in intake.message_ids:
            intake.message_ids.append(message_id)
            intake.texts.append(text)
        intake.rounds = rounds
        with self._lock:
            self._conn.execute(
                "INSERT INTO intakes (conversation_id, message_ids, texts, rounds) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET "
                "message_ids = excluded.message_ids, texts = excluded.texts, rounds = excluded.rounds",
                (
                    conversation_id,
                    json.dumps(intake.message_ids, ensure_ascii=False),
                    json.dumps(intake.texts, ensure_ascii=False),
                    intake.rounds,
                ),
            )
            self._conn.commit()
        return intake

    def close_intake(self, conversation_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM intakes WHERE conversation_id = ?", (conversation_id,))
            self._conn.commit()

    def queue_for_review(self, event_id: str, record: dict) -> None:
        with self._lock:
            record.setdefault("received_at", _now())
            record["review_status"] = record.get("review_status", "pending_review")
            self._conn.execute(
                "INSERT INTO review_queue (event_id, review_status, record) VALUES (?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "review_status = excluded.review_status, record = excluded.record",
                (event_id, record["review_status"], json.dumps(record, ensure_ascii=False)),
            )
            self._conn.commit()

    def pending_reviews(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT record FROM review_queue WHERE review_status = 'pending_review' ORDER BY rowid"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def decide(self, event_id: str, decision: str, reviewer: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT record FROM review_queue WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None:
                return None
            record = json.loads(row[0])
            record["review_status"] = "approved" if decision == "approve" else "rejected"
            record["reviewer"] = reviewer
            record["decided_at"] = _now()
            self._conn.execute(
                "UPDATE review_queue SET review_status = ?, record = ? WHERE event_id = ?",
                (record["review_status"], json.dumps(record, ensure_ascii=False), event_id),
            )
            self._conn.commit()
            return record

    def reset(self) -> None:
        with self._lock:
            self._conn.executescript(
                "DELETE FROM results; DELETE FROM intakes; DELETE FROM review_queue;"
            )
            self._conn.commit()


def _default_path() -> str:
    configured = os.getenv("BHARATBIZ_LEDGER_DB")
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2] / "data" / "runtime" / "ledger.sqlite3")


ledger = SqliteLedger(_default_path())
