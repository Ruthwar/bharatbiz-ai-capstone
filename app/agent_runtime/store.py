"""Persistent agent sessions: one row per turn, SQLite, local only.

The store keeps the review state that should survive across turns (the resolved intent,
the identifiers already known, the last run summary). It never stores an approval or a
business action; approving a review remains in the ledger.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

CONTEXT_FIELDS = (
    "intent",
    "sku_id",
    "supplier_id",
    "retailer_id",
    "delay_days",
    "required_units",
    "outflow_rupees",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentSessionStore:
    """Append-only turns plus the latest context per conversation."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = Lock()
        self._path = str(path)
        self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        try:
            if self._path != ":memory:":
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._path, check_same_thread=False)
        except (sqlite3.Error, OSError):
            logger.warning("agent session database unavailable at %s; staying in memory", self._path, exc_info=True)
            self._path = ":memory:"
            conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_turn (
                run_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                question TEXT NOT NULL,
                intent TEXT NOT NULL,
                status TEXT NOT NULL,
                context TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS agent_turn_conversation
                ON agent_turn (conversation_id, turn);
            """
        )
        conn.commit()
        return conn

    @property
    def database(self) -> str:
        return self._path

    def next_turn(self, conversation_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(turn), 0) FROM agent_turn WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return int(row[0]) + 1

    def context(self, conversation_id: str) -> dict:
        """Latest resolved context, so a follow-up question need not repeat IDs."""
        with self._lock:
            row = self._conn.execute(
                "SELECT context FROM agent_turn WHERE conversation_id = ? ORDER BY turn DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return {}
        return {key: payload[key] for key in CONTEXT_FIELDS if key in payload}

    def save_turn(
        self,
        *,
        run_id: str,
        conversation_id: str,
        turn: int,
        question: str,
        intent: str,
        status: str,
        context: dict,
        summary: dict,
    ) -> None:
        clean = {key: context.get(key) for key in CONTEXT_FIELDS if context.get(key) is not None}
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agent_turn "
                "(run_id, conversation_id, turn, question, intent, status, context, summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    conversation_id,
                    turn,
                    question,
                    intent,
                    status,
                    json.dumps(clean, ensure_ascii=False, default=str),
                    json.dumps(summary, ensure_ascii=False, default=str),
                    _now(),
                ),
            )
            self._conn.commit()

    def turns(self, conversation_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, conversation_id, turn, question, intent, status, context, summary, created_at "
                "FROM agent_turn WHERE conversation_id = ? ORDER BY turn",
                (conversation_id,),
            ).fetchall()
        keys = (
            "run_id", "conversation_id", "turn", "question", "intent", "status",
            "context", "summary", "created_at",
        )
        turns = []
        for row in rows:
            record = dict(zip(keys, row))
            for field in ("context", "summary"):
                try:
                    record[field] = json.loads(record[field])
                except (TypeError, json.JSONDecodeError):
                    record[field] = {}
            turns.append(record)
        return turns

    def reset(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM agent_turn")
            self._conn.commit()


def _default_path() -> str:
    configured = os.getenv("BHARATBIZ_AGENT_DB")
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2] / "data" / "runtime" / "agent_sessions.sqlite3")


agent_store = AgentSessionStore(_default_path())
