import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.schemas.retail import CaseProposal, MarketObservation, ResponseDraft

OPEN_STATES = ("open", "in_progress", "waiting_for_information")
CASE_TRANSITIONS = {
    "open": {"in_progress", "waiting_for_information", "resolved"},
    "in_progress": {"waiting_for_information", "resolved"},
    "waiting_for_information": {"in_progress", "resolved"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}
PRIORITY_RANK = {"normal": 0, "high": 1}


class RetailLifecycleError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class RetailStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = Lock()
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    event_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    retailer_id TEXT,
                    intent TEXT NOT NULL,
                    reporter_id TEXT,
                    observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_interactions_retailer
                    ON interactions (retailer_id, observed_at);
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    retailer_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sku_id TEXT,
                    owner TEXT,
                    summary TEXT NOT NULL,
                    follow_up TEXT NOT NULL,
                    event_ids TEXT NOT NULL,
                    message_ids TEXT NOT NULL,
                    order_ids TEXT NOT NULL,
                    resolution_note TEXT,
                    opened_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    resolved_at TEXT,
                    closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS case_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    draft_id TEXT PRIMARY KEY,
                    event_id TEXT UNIQUE NOT NULL,
                    case_id TEXT,
                    retailer_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    final_text TEXT,
                    allowed_tokens TEXT NOT NULL DEFAULT '[]',
                    reviewer TEXT,
                    review_note TEXT,
                    edit_warnings TEXT NOT NULL DEFAULT '[]',
                    review_status TEXT NOT NULL DEFAULT 'pending_review',
                    sent_manually_at TEXT,
                    sent_manually_by TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_observations (
                    observation_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    sku_id TEXT,
                    competitor_name TEXT NOT NULL,
                    product_label TEXT NOT NULL,
                    offer TEXT NOT NULL,
                    area TEXT NOT NULL,
                    retailer_id TEXT,
                    reporter_id TEXT,
                    observed_at TEXT NOT NULL,
                    observation_text TEXT NOT NULL,
                    evidence_span TEXT NOT NULL,
                    source_message_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_market_observations_group
                    ON market_observations (signal_type, subject, competitor_name, product_label, offer, area);
                """
            )
            self._conn.commit()

    def _row(self, sql: str, args: tuple) -> dict | None:
        row = self._conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(row) for row in self._conn.execute(sql, args).fetchall()]

    @staticmethod
    def _case_view(row: dict | None) -> dict | None:
        if row is None:
            return None
        for key in ("event_ids", "message_ids", "order_ids"):
            row[key] = json.loads(row[key])
        return row

    @staticmethod
    def _draft_view(row: dict | None) -> dict | None:
        if row is None:
            return None
        row["edit_warnings"] = json.loads(row["edit_warnings"])
        row["allowed_tokens"] = json.loads(row["allowed_tokens"])
        return row

    def _activity(self, case_id: str, actor: str, kind: str, detail: dict) -> None:
        self._conn.execute(
            "INSERT INTO case_activity (case_id, at, actor, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (case_id, _now(), actor, kind, json.dumps(detail, ensure_ascii=False)),
        )

    def _record_interaction(self, interaction: dict) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO interactions VALUES (?, ?, ?, ?, ?, ?)",
            (
                interaction["event_id"],
                interaction["message_id"],
                interaction.get("retailer_id"),
                interaction["intent"],
                interaction.get("reporter_id"),
                _utc_iso(interaction["observed_at"]),
            ),
        )

    def interactions_for(self, retailer_id: str, since: str) -> list[dict]:
        with self._lock:
            return self._rows(
                "SELECT * FROM interactions WHERE retailer_id = ? AND observed_at >= ? ORDER BY observed_at",
                (retailer_id, _utc_iso(since)),
            )

    def _open_case(self, retailer_id: str, category: str, sku_id: str | None) -> dict | None:
        placeholders = ",".join("?" for _ in OPEN_STATES)
        return self._case_view(
            self._row(
                f"SELECT * FROM cases WHERE retailer_id = ? AND category = ? AND sku_id IS ? "
                f"AND status IN ({placeholders}) ORDER BY opened_at LIMIT 1",
                (retailer_id, category, sku_id, *OPEN_STATES),
            )
        )

    def open_case_for(self, retailer_id: str, category: str, sku_id: str | None = None) -> dict | None:
        with self._lock:
            return self._open_case(retailer_id, category, sku_id)

    def get_case(self, case_id: str) -> dict | None:
        with self._lock:
            return self._case_view(self._row("SELECT * FROM cases WHERE case_id = ?", (case_id,)))

    def list_cases(self, status: str | None = None, retailer_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM cases WHERE 1=1", []
        if status:
            sql, args = sql + " AND status = ?", args + [status]
        if retailer_id:
            sql, args = sql + " AND retailer_id = ?", args + [retailer_id]
        with self._lock:
            return [self._case_view(row) for row in self._rows(sql + " ORDER BY updated_at DESC", tuple(args))]

    def case_activity(self, case_id: str) -> list[dict]:
        with self._lock:
            rows = self._rows(
                "SELECT at, actor, kind, detail FROM case_activity WHERE case_id = ? ORDER BY id",
                (case_id,),
            )
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        return rows

    def _apply_case(self, proposal: CaseProposal, event_id: str, message_id: str) -> str:
        now = _now()
        existing = self._open_case(proposal.retailer_id, proposal.category, proposal.sku_id)
        if existing is not None:
            if event_id in existing["event_ids"]:
                return existing["case_id"]
            events = existing["event_ids"] + [event_id]
            messages = list(dict.fromkeys(existing["message_ids"] + [message_id]))
            orders = list(dict.fromkeys(existing["order_ids"] + proposal.order_ids))
            priority = existing["priority"]
            if PRIORITY_RANK[proposal.priority] > PRIORITY_RANK[priority]:
                self._activity(
                    existing["case_id"],
                    "system",
                    "priority_raised",
                    {"from": priority, "to": proposal.priority, "reasons": proposal.priority_reasons},
                )
                priority = proposal.priority
            self._conn.execute(
                "UPDATE cases SET event_ids = ?, message_ids = ?, order_ids = ?, priority = ?, updated_at = ? "
                "WHERE case_id = ?",
                (json.dumps(events), json.dumps(messages), json.dumps(orders), priority, now, existing["case_id"]),
            )
            self._activity(
                existing["case_id"], "system", "linked", {"event_id": event_id, "message_id": message_id}
            )
            return existing["case_id"]
        if self._row("SELECT case_id FROM cases WHERE case_id = ?", (proposal.case_id,)):
            return proposal.case_id
        self._conn.execute(
            "INSERT INTO cases (case_id, retailer_id, category, priority, status, sku_id, owner, summary, "
            "follow_up, event_ids, message_ids, order_ids, opened_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.case_id,
                proposal.retailer_id,
                proposal.category,
                proposal.priority,
                proposal.sku_id,
                proposal.summary,
                proposal.follow_up,
                json.dumps([event_id]),
                json.dumps([message_id]),
                json.dumps(proposal.order_ids),
                now,
                now,
            ),
        )
        self._activity(
            proposal.case_id,
            "system",
            "opened",
            {"event_id": event_id, "message_id": message_id, "priority_reasons": proposal.priority_reasons},
        )
        return proposal.case_id

    def update_case(
        self,
        case_id: str,
        actor: str,
        status: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        note: str | None = None,
        resolution_note: str | None = None,
    ) -> dict:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                case = self._case_view(self._row("SELECT * FROM cases WHERE case_id = ?", (case_id,)))
                if case is None:
                    raise LookupError(f"case {case_id} not found")
                now = _now()
                if status and status != case["status"]:
                    if status not in CASE_TRANSITIONS.get(case["status"], set()):
                        raise RetailLifecycleError(f"case status {case['status']} -> {status} is not allowed")
                    if status == "resolved" and not (resolution_note and resolution_note.strip()):
                        raise RetailLifecycleError("resolving a case needs a staff resolution note")
                    fields = {"status": status}
                    if status == "resolved":
                        fields.update(resolution_note=resolution_note.strip(), resolved_at=now)
                    if status == "closed":
                        fields["closed_at"] = now
                    if status == "in_progress" and case["status"] == "resolved":
                        fields["resolved_at"] = None
                        self._activity(case_id, actor, "reopened", {"previous_note": case["resolution_note"]})
                    self._conn.execute(
                        f"UPDATE cases SET {', '.join(f'{key} = ?' for key in fields)} WHERE case_id = ? AND status = ?",
                        (*fields.values(), case_id, case["status"]),
                    )
                    self._activity(case_id, actor, "status_changed", {"from": case["status"], "to": status})
                if owner and owner != case["owner"]:
                    self._conn.execute("UPDATE cases SET owner = ? WHERE case_id = ?", (owner, case_id))
                    self._activity(case_id, actor, "assigned", {"from": case["owner"], "to": owner})
                if priority and priority != case["priority"]:
                    if priority not in PRIORITY_RANK:
                        raise RetailLifecycleError("priority must be high or normal")
                    self._conn.execute("UPDATE cases SET priority = ? WHERE case_id = ?", (priority, case_id))
                    self._activity(case_id, actor, "priority_changed", {"from": case["priority"], "to": priority})
                if note and note.strip():
                    self._activity(case_id, actor, "note", {"text": note.strip()})
                self._conn.execute("UPDATE cases SET updated_at = ? WHERE case_id = ?", (now, case_id))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return self.get_case(case_id)

    def _save_draft(self, draft: ResponseDraft, case_id: str | None) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO drafts (draft_id, event_id, case_id, retailer_id, language, kind, text, "
            "allowed_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                draft.draft_id,
                draft.event_id,
                case_id,
                draft.retailer_id,
                draft.language,
                draft.kind,
                draft.text,
                json.dumps(draft.allowed_tokens, ensure_ascii=False),
                _now(),
            ),
        )

    def get_draft(self, draft_id: str) -> dict | None:
        with self._lock:
            return self._draft_view(self._row("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)))

    def list_drafts(self) -> list[dict]:
        with self._lock:
            rows = self._rows("SELECT * FROM drafts ORDER BY created_at DESC")
        return [self._draft_view(row) for row in rows]

    def record_draft_review(
        self,
        draft_id: str,
        decision: str,
        reviewer: str,
        note: str | None,
        final_text: str | None,
        edit_warnings: list[str],
    ) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                draft = self._row("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
                if draft is None:
                    raise LookupError(f"draft {draft_id} not found")
                if draft["review_status"] != "pending_review":
                    raise RetailLifecycleError(f"draft is already {draft['review_status']}")
                status = "approved" if decision == "approve" else "rejected"
                cursor = self._conn.execute(
                    "UPDATE drafts SET reviewer = ?, review_note = ?, final_text = ?, edit_warnings = ?, "
                    "review_status = ? WHERE draft_id = ? AND review_status = 'pending_review'",
                    (
                        reviewer,
                        note,
                        final_text,
                        json.dumps(edit_warnings, ensure_ascii=False),
                        status,
                        draft_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RetailLifecycleError("draft review has already been decided")
                if draft["case_id"]:
                    self._activity(
                        draft["case_id"],
                        reviewer,
                        "reply_reviewed",
                        {"draft_id": draft_id, "decision": decision, "edited": final_text is not None},
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def mark_sent(self, draft_id: str, sent_by: str) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                draft = self._row("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
                if draft is None:
                    raise LookupError(f"draft {draft_id} not found")
                if draft["review_status"] != "approved":
                    raise RetailLifecycleError("only an approved draft can be marked as manually sent")
                if draft["sent_manually_at"]:
                    raise RetailLifecycleError("draft is already marked as sent")
                now = _now()
                cursor = self._conn.execute(
                    "UPDATE drafts SET sent_manually_at = ?, sent_manually_by = ? "
                    "WHERE draft_id = ? AND sent_manually_at IS NULL",
                    (now, sent_by, draft_id),
                )
                if cursor.rowcount != 1:
                    raise RetailLifecycleError("draft is already marked as sent")
                if draft["case_id"]:
                    self._activity(draft["case_id"], sent_by, "reply_sent_manually", {"draft_id": draft_id})
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _record_observation(self, observation: MarketObservation) -> None:
        data = observation.model_dump()
        data["observed_at"] = _utc_iso(data["observed_at"])
        self._conn.execute(
            "INSERT OR IGNORE INTO market_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(data.values()),
        )

    def observations(self, since: str | None = None) -> list[dict]:
        with self._lock:
            if since:
                return self._rows(
                    "SELECT * FROM market_observations WHERE observed_at >= ? ORDER BY observed_at, observation_id",
                    (_utc_iso(since),),
                )
            return self._rows("SELECT * FROM market_observations ORDER BY observed_at, observation_id")

    def persist(
        self,
        interaction: dict | None,
        case: CaseProposal | None = None,
        draft: ResponseDraft | None = None,
        observations: list[MarketObservation] | None = None,
    ) -> str | None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                if interaction:
                    self._record_interaction(interaction)
                case_id = (
                    self._apply_case(case, interaction["event_id"], interaction["message_id"])
                    if case and interaction
                    else None
                )
                if draft:
                    self._save_draft(draft, case_id)
                for observation in observations or []:
                    self._record_observation(observation)
                self._conn.commit()
                return case_id
            except Exception:
                self._conn.rollback()
                raise

    def reset(self) -> None:
        with self._lock:
            self._conn.executescript(
                "DELETE FROM interactions; DELETE FROM cases; DELETE FROM case_activity; "
                "DELETE FROM drafts; DELETE FROM market_observations;"
            )
            self._conn.commit()


def _default_path() -> str:
    configured = os.getenv("BHARATBIZ_RETAIL_DB")
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2] / "data" / "runtime" / "retail.sqlite3")


retail_store = RetailStore(_default_path())
