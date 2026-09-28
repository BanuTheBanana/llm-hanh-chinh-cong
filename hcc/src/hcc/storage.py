"""SQLite persistence for conversation state and append-only request audit events."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from .validation import assert_valid


class SQLiteStore:
    """Small local store; each operation uses its own short-lived connection."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        self._is_memory = self.database_path == ":memory:"
        self._database_uri = (
            f"file:hcc-{uuid4().hex}?mode=memory&cache=shared"
            if self._is_memory
            else self.database_path
        )
        if not self._is_memory:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._anchor = self._connect() if self._is_memory else None
        connection = self._anchor or self._connect()
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS conversation_states (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    session_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    payload_json TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_uri, uri=self._is_memory)
        connection.row_factory = sqlite3.Row
        return connection

    def get_conversation_state(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM conversation_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        state = json.loads(row["state_json"])
        assert_valid("conversation_state", state)
        return state

    def save_conversation_state(self, state: dict) -> None:
        assert_valid("conversation_state", state)
        encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO conversation_states(session_id, state_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     state_json = excluded.state_json,
                     updated_at = excluded.updated_at""",
                (state["session_id"], encoded, state["updated_at"]),
            )

    def record(self, event_type: str, session_id: str | None, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(event_type, session_id, payload_json) VALUES (?, ?, ?)",
                (event_type, session_id, encoded),
            )

    def list_audit_events(self, session_id: str | None = None) -> list[dict]:
        query = "SELECT event_id, event_type, session_id, created_at, payload_json FROM audit_events"
        parameters: tuple[str, ...] = ()
        if session_id is not None:
            query += " WHERE session_id = ?"
            parameters = (session_id,)
        query += " ORDER BY event_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]