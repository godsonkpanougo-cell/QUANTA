"""
QUANTA — db.py
Persistance légère via SQLite (module standard sqlite3, pas d'ORM lourd).

Remplace le stockage en mémoire (dict Python) de main.py par une base
fichier qui survit aux redémarrages du serveur. Décision du Jour 21 du
programme 90 jours -- volontairement minimaliste : pas de SQLAlchemy, pas
de migrations Alembic, pas de pool de connexions. Une table "uploads",
une table "analyses", des fonctions get/set simples.

Le fichier .db est créé automatiquement au premier import, dans le
répertoire de travail (configurable via QUANTA_DB_PATH).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any

DB_PATH = os.environ.get("QUANTA_DB_PATH", "quanta.db")

# SQLite n'aime pas le multi-thread sans précaution -- FastAPI + BackgroundTasks
# peut exécuter le code de fond dans un thread différent du thread principal.
# Un verrou global simple suffit à cette échelle (pas de besoin de pool de
# connexions pour un MVP solo) ; check_same_thread=False + lock = sûr.
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _get_conn():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    """Crée les tables si elles n'existent pas. Appelée au démarrage de main.py."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                file_id      TEXT PRIMARY KEY,
                path         TEXT NOT NULL,
                filename     TEXT NOT NULL,
                numeric_cols TEXT NOT NULL,
                cat_cols     TEXT NOT NULL,
                id_cols      TEXT NOT NULL,
                n_rows       INTEGER NOT NULL,
                n_cols       INTEGER NOT NULL,
                dataset_type TEXT,
                uploaded_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                analysis_id TEXT PRIMARY KEY,
                file_id     TEXT NOT NULL,
                query       TEXT NOT NULL,
                status      TEXT NOT NULL,
                result      TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES uploads(file_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC)")


def clear_all() -> None:
    """Vide les tables (isolation entre scripts de test API in-process)."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM uploads")


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOADS
# ═══════════════════════════════════════════════════════════════════════════════

def save_upload(file_id: str, data: dict[str, Any]) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO uploads
               (file_id, path, filename, numeric_cols, cat_cols, id_cols,
                n_rows, n_cols, dataset_type, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id, data["path"], data["filename"],
                json.dumps(data["numeric_cols"]), json.dumps(data["cat_cols"]),
                json.dumps(data["id_cols"]), data["n_rows"], data["n_cols"],
                data.get("dataset_type"), data["uploaded_at"],
            ),
        )


def get_upload(file_id: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM uploads WHERE file_id = ?", (file_id,)).fetchone()
    if row is None:
        return None
    return {
        "path": row["path"],
        "filename": row["filename"],
        "numeric_cols": json.loads(row["numeric_cols"]),
        "cat_cols": json.loads(row["cat_cols"]),
        "id_cols": json.loads(row["id_cols"]),
        "n_rows": row["n_rows"],
        "n_cols": row["n_cols"],
        "dataset_type": row["dataset_type"],
        "uploaded_at": row["uploaded_at"],
    }


def upload_exists(file_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM uploads WHERE file_id = ?", (file_id,)).fetchone()
    return row is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSES
# ═══════════════════════════════════════════════════════════════════════════════

def create_analysis(analysis_id: str, file_id: str, query: str, created_at: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO analyses
               (analysis_id, file_id, query, status, result, error, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?)""",
            (analysis_id, file_id, query, created_at, created_at),
        )


def update_analysis(
    analysis_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    updated_at: str = "",
) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE analyses SET status = ?, result = ?, error = ?, updated_at = ? WHERE analysis_id = ?",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                updated_at,
                analysis_id,
            ),
        )


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
    if row is None:
        return None
    return {
        "analysis_id": row["analysis_id"],
        "file_id": row["file_id"],
        "query": row["query"],
        "status": row["status"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_analyses(limit: int = 100) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT analysis_id, status, query, created_at FROM analyses "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"analysis_id": r["analysis_id"], "status": r["status"],
         "query": r["query"], "created_at": r["created_at"]}
        for r in rows
    ]
