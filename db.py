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

DB_PATH = os.environ.get("QUANTA_DB_PATH", "/data/quanta.db")

# Créer le dossier /data si nécessaire (Railway volume persistant)
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# SQLite n'aime pas le multi-thread sans précaution -- FastAPI + BackgroundTasks
# peut exécuter le code de fond dans un thread différent du thread principal.
# Un verrou global simple suffit à cette échelle (pas de besoin de pool de
# connexions pour un MVP solo) ; check_same_thread=False + lock = sûr.
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
            CREATE TABLE IF NOT EXISTS users (
                user_id      TEXT PRIMARY KEY,
                google_sub   TEXT UNIQUE NOT NULL,
                email        TEXT UNIQUE NOT NULL,
                name         TEXT,
                picture_url  TEXT,
                created_at   TEXT NOT NULL,
                last_login_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                expires_at    TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                file_id      TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                path         TEXT NOT NULL,
                filename     TEXT NOT NULL,
                numeric_cols TEXT NOT NULL,
                cat_cols     TEXT NOT NULL,
                id_cols      TEXT NOT NULL,
                n_rows       INTEGER NOT NULL,
                n_cols       INTEGER NOT NULL,
                dataset_type TEXT,
                uploaded_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                analysis_id TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                file_id     TEXT NOT NULL,
                query       TEXT NOT NULL,
                status      TEXT NOT NULL,
                result      TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES uploads(file_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
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

def save_upload(file_id: str, user_id: str, data: dict[str, Any]) -> None:
    """Sauvegarde les métadonnées d'un upload avec user_id."""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO uploads
               (file_id, user_id, path, filename, numeric_cols, cat_cols, id_cols,
                n_rows, n_cols, dataset_type, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id, user_id, data["path"], data["filename"],
                json.dumps(data["numeric_cols"]), json.dumps(data["cat_cols"]),
                json.dumps(data["id_cols"]), data["n_rows"], data["n_cols"],
                data.get("dataset_type"), data["uploaded_at"],
            ),
        )


def get_upload(file_id: str, user_id: str) -> dict[str, Any] | None:
    """Récupère un upload si l'utilisateur est le propriétaire."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM uploads WHERE file_id = ? AND user_id = ?",
            (file_id, user_id)
        ).fetchone()
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


def upload_exists(file_id: str, user_id: str) -> bool:
    """Vérifie si un upload existe et appartient à l'utilisateur."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM uploads WHERE file_id = ? AND user_id = ?",
            (file_id, user_id)
        ).fetchone()
    return row is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSES
# ═══════════════════════════════════════════════════════════════════════════════

def create_analysis(analysis_id: str, user_id: str, file_id: str, query: str, created_at: str) -> None:
    """Crée une analyse avec user_id."""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO analyses
               (analysis_id, user_id, file_id, query, status, result, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)""",
            (analysis_id, user_id, file_id, query, created_at, created_at),
        )


def update_analysis(
    analysis_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    updated_at: str = "",
    user_id: str = "",
) -> bool:
    """Met à jour une analyse si l'utilisateur est le propriétaire."""
    with _get_conn() as conn:
        cursor = conn.execute(
            "UPDATE analyses SET status = ?, result = ?, error = ?, updated_at = ? "
            "WHERE analysis_id = ? AND user_id = ? AND status != 'done'",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                updated_at,
                analysis_id,
                user_id,
            ),
        )
        if cursor.rowcount == 0:
            print(
                f"DB - update_analysis IGNORÉ pour {analysis_id} : "
                f"statut déjà 'done' (définitif) OU utilisateur non propriétaire, "
                f"tentative d'écriture '{status}' bloquée.",
                flush=True,
            )
            return False
        return True


def get_analysis(analysis_id: str, user_id: str) -> dict[str, Any] | None:
    """Récupère une analyse si l'utilisateur est le propriétaire."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE analysis_id = ? AND user_id = ?",
            (analysis_id, user_id)
        ).fetchone()
    if row is None:
        return None
    return {
        "analysis_id": row["analysis_id"],
        "file_id": row["file_id"],
        "user_id": row["user_id"],
        "query": row["query"],
        "status": row["status"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_analyses(user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """
    Liste les analyses d'un utilisateur avec nom de fichier et score de confiance.
    
    Approche choisie : JOIN avec la table uploads pour le filename,
    et parsing JSON en Python pour le score (score_global) quand status="done".
    C'est plus simple que les fonctions JSON de SQLite et cohérent avec le style existant.
    """
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT a.analysis_id, a.status, a.query, a.created_at, a.updated_at, a.result,
                      u.filename
               FROM analyses a
               JOIN uploads u ON a.file_id = u.file_id
               WHERE a.user_id = ? ORDER BY a.created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    
    analyses = []
    for r in rows:
        analysis = {
            "analysis_id": r["analysis_id"],
            "status": r["status"],
            "query": r["query"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "filename": r["filename"],
        }
        
        # Extraire le score de confiance uniquement si status="done"
        if r["status"] == "done" and r["result"]:
            try:
                result = json.loads(r["result"])
                # Le score est dans result.confidence.score_global
                confidence = result.get("confidence", {})
                analysis["confidence_score"] = confidence.get("score_global")
            except (json.JSONDecodeError, KeyError, TypeError):
                # En cas d'erreur de parsing, pas de score
                analysis["confidence_score"] = None
        else:
            analysis["confidence_score"] = None
        
        analyses.append(analysis)
    
    return analyses


def delete_analysis(analysis_id: str, user_id: str) -> None:
    """Supprime une analyse si l'utilisateur est le propriétaire."""
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM analyses WHERE analysis_id = ? AND user_id = ?",
            (analysis_id, user_id)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════════

def create_or_update_user(
    google_sub: str,
    email: str,
    name: str | None,
    picture_url: str | None,
) -> str:
    """
    Crée l'utilisateur s'il n'existe pas (par google_sub), sinon
    met à jour last_login_at, name, picture_url. Retourne user_id.
    """
    import uuid
    from datetime import datetime

    now = datetime.utcnow().isoformat() + "Z"

    with _get_conn() as conn:
        # Chercher par google_sub
        existing = conn.execute(
            "SELECT user_id FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()

        if existing:
            user_id = existing["user_id"]
            # Mettre à jour last_login_at et potentiellement name/picture_url
            conn.execute(
                """UPDATE users
                   SET last_login_at = ?, name = ?, picture_url = ?
                   WHERE user_id = ?""",
                (now, name, picture_url, user_id),
            )
            return user_id
        else:
            # Créer nouvel utilisateur
            user_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO users
                   (user_id, google_sub, email, name, picture_url, created_at, last_login_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, google_sub, email, name, picture_url, now, now),
            )
            return user_id


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Récupère un utilisateur par son user_id."""
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "google_sub": row["google_sub"],
        "email": row["email"],
        "name": row["name"],
        "picture_url": row["picture_url"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════════════════════

def create_session(user_id: str, ttl_hours: int = 24 * 7) -> str:
    """
    Crée une session, retourne le session_token (secrets.token_urlsafe(32)).
    """
    import secrets
    from datetime import datetime, timedelta

    session_token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    created_at = now.isoformat() + "Z"
    expires_at = (now + timedelta(hours=ttl_hours)).isoformat() + "Z"

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO sessions
               (session_token, user_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (session_token, user_id, created_at, expires_at),
        )

    return session_token


def get_session(session_token: str) -> dict[str, Any] | None:
    """
    Récupère une session par son token. Retourne None si le token
    n'existe pas OU si expires_at est dépassé.
    """
    from datetime import datetime

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_token = ?", (session_token,)
        ).fetchone()

    if row is None:
        return None

    # Vérifier expiration
    expires_at = row["expires_at"]
    now = datetime.utcnow().isoformat() + "Z"

    if expires_at < now:
        # Session expirée, la supprimer et retourner None
        delete_session(session_token)
        return None

    return {
        "session_token": row["session_token"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


def delete_session(session_token: str) -> None:
    """Supprime une session (déconnexion)."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))


def cleanup_expired_sessions() -> int:
    """
    Supprime toutes les sessions expirées, retourne le nombre
    supprimé (utile pour un nettoyage périodique).
    """
    from datetime import datetime

    now = datetime.utcnow().isoformat() + "Z"

    with _get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (now,)
        )
        return cursor.rowcount
