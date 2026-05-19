# 로컬 DB 
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class PersonaRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS persona_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    mime_type TEXT,
                    extension TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS autofill_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    instruction TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                """
            )

    def get_profile(self) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM persona_profile WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def save_profile(self, profile: Dict[str, Any], source: str = "manual") -> Dict[str, Any]:
        payload_json = json.dumps(profile, ensure_ascii=False)
        updated_at = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO persona_profile (id, payload_json, source, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (payload_json, source, updated_at),
            )
        return {
            "profile": profile,
            "source": source,
            "updated_at": updated_at,
        }

    def save_document(
        self,
        original_name: str,
        stored_name: str,
        mime_type: str,
        extension: str,
        extracted_text: str,
    ) -> Dict[str, Any]:
        created_at = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO documents (
                    original_name,
                    stored_name,
                    mime_type,
                    extension,
                    extracted_text,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (original_name, stored_name, mime_type, extension, extracted_text, created_at),
            )
            document_id = cursor.lastrowid
        return self.get_document(document_id)

    def get_document(self, document_id: int) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, original_name, stored_name, mime_type, extension, extracted_text, created_at
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"document_not_found:{document_id}")
        return dict(row)

    def list_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    original_name,
                    extension,
                    created_at,
                    substr(extracted_text, 1, 500) AS preview
                FROM documents
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_autofill_run(
        self, document_id: int, instruction: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        created_at = utc_now_iso()
        result_json = json.dumps(result, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO autofill_runs (document_id, instruction, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (document_id, instruction, result_json, created_at),
            )
            run_id = cursor.lastrowid
        return self.get_autofill_run(run_id)

    def get_autofill_run(self, run_id: int) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    runs.id,
                    runs.document_id,
                    runs.instruction,
                    runs.result_json,
                    runs.created_at,
                    documents.original_name
                FROM autofill_runs AS runs
                JOIN documents ON documents.id = runs.document_id
                WHERE runs.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"autofill_run_not_found:{run_id}")
        payload = dict(row)
        payload["result"] = json.loads(payload.pop("result_json"))
        return payload

    def list_autofill_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    runs.id,
                    runs.document_id,
                    runs.instruction,
                    runs.created_at,
                    documents.original_name,
                    json_extract(runs.result_json, '$.document_type') AS document_type,
                    json_extract(runs.result_json, '$.summary') AS summary
                FROM autofill_runs AS runs
                JOIN documents ON documents.id = runs.document_id
                ORDER BY runs.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

