"""
QUANTA — conversation.py (Pilier 2 : Parler à ses données, sans re-upload)

Pourquoi : ChatGPT a gagné parce qu'on PARLE. QUANTA savait déjà traduire
une question en intention (brain.text_to_intent) et exécuter l'analyse
complète, mais uniquement en mode ponctuel (upload -> analyse -> PDF).
La session conversationnelle fait de QUANTA l'endroit quotidien :
  - une session = un dataset chargé (file_hash mémorisé UNE fois) ;
  - chaque question (turn) réutilise TOUT le flux existant :
    cache d'analyses (identité garantie) -> quota -> worker d'arrière-plan
    -> polling /status — ZÉRO duplication de résultat, zéro re-upload ;
  - une session peut être rattachée à un Projet (Pilier 1) : l'historique
    des questions rejoint l'endroit où vit le travail de recherche.

Isolation (règle « sans casser l'existant ») :
  - 2 tables SQLite dédiées conversation_* (IF NOT EXISTS, zéro migration) ;
  - le worker d'arrière-plan est INJECTÉ (set_background_dispatcher) par
    main.py au démarrage : aucun import circulaire, aucun code existant
    modifié (le dispatch réel reste main._run_analysis_background) ;
  - pas de rate-limit slowapi ici (l'instance vit dans main) : la protection
    réelle reste le QUOTA mensuel, contrôlé exactement comme /analyze.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

import db
from app import auth

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Worker injecté par main.py (DI) — évite tout import circulaire.
_background_dispatcher: Callable[..., None] | None = None


def set_background_dispatcher(fn: Callable[..., None]) -> None:
    """Enregistre le worker d'analyse (main._run_analysis_background en prod)."""
    global _background_dispatcher
    _background_dispatcher = fn


# ═══════════════════════════════════════════════════════════════════════════════
# Schéma (tables dédiées — aucune migration)
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_sessions (
               session_id  TEXT PRIMARY KEY,
               user_id     TEXT NOT NULL,
               project_id  TEXT,
               file_id     TEXT NOT NULL,
               file_hash   TEXT NOT NULL,
               created_at  TEXT NOT NULL,
               updated_at  TEXT NOT NULL
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_turns (
               turn_id     TEXT PRIMARY KEY,
               session_id  TEXT NOT NULL,
               user_id     TEXT NOT NULL,
               turn_no     INTEGER NOT NULL,
               query       TEXT NOT NULL,
               analysis_id TEXT,
               status      TEXT NOT NULL DEFAULT 'pending',
               created_at  TEXT NOT NULL
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_csession_user ON conversation_sessions(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cturn_session ON conversation_turns(session_id)"
    )


@contextmanager
def _conn():
    c = sqlite3.connect(db.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        _ensure_tables(c)
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Couche métier
# ═══════════════════════════════════════════════════════════════════════════════

def create_session(user_id: str, file_id: str,
                   project_id: str | None = None) -> dict[str, Any]:
    """Crée une session de conversation sur un upload existant du user.
    Le hash du fichier est calculé UNE fois ici (comme /analyze)."""
    upload = db.get_upload(file_id, user_id)
    if upload is None:
        raise ValueError(
            f"file_id '{file_id}' introuvable pour cet utilisateur. "
            "Uploadez d'abord un fichier via /upload."
        )
    if project_id is not None:
        # Intégration Pilier 1 : le projet doit appartenir au même user.
        from app import projects
        projects.get_project(project_id, user_id)  # ValueError si pas à lui
    try:
        with open(upload["path"], "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        raise ValueError(f"Fichier source introuvable sur le serveur : {e}")
    sid = str(uuid.uuid4())
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO conversation_sessions
                   (session_id, user_id, project_id, file_id, file_hash,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sid, user_id, project_id, file_id, file_hash, now, now),
        )
        row = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ?", (sid,)
        ).fetchone()
    return dict(row)


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM conversation_turns t
                        WHERE t.session_id = s.session_id) AS n_turns
               FROM conversation_sessions s
               WHERE s.user_id = ?
               ORDER BY s.updated_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session_detail(session_id: str, user_id: str) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Session introuvable pour cet utilisateur.")
        turns = [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM conversation_turns
                   WHERE session_id = ? ORDER BY turn_no ASC""",
                (session_id,),
            ).fetchall()
        ]
    session = dict(row)
    session["turns"] = turns
    return session


def delete_session(session_id: str, user_id: str) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Session introuvable pour cet utilisateur.")
        conn.execute(
            "DELETE FROM conversation_turns WHERE session_id = ?", (session_id,)
        )
        conn.execute(
            "DELETE FROM conversation_sessions WHERE session_id = ?", (session_id,)
        )
    return {"session_id": session_id, "deleted": True}


def link_project(session_id: str, user_id: str, project_id: str) -> dict[str, Any]:
    """Rattache une session à un Projet (Pilier 1) de l'utilisateur."""
    from app import projects
    projects.get_project(project_id, user_id)  # ValueError si introuvable
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Session introuvable pour cet utilisateur.")
        conn.execute(
            """UPDATE conversation_sessions
               SET project_id = ?, updated_at = ? WHERE session_id = ?""",
            (project_id, _now(), session_id),
        )
        row = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row)


def ask(session_id: str, user_id: str, query: str) -> dict[str, Any]:
    """Pose une question dans la session — réutilise TOUT le flux /analyze :
    cache d'abord (identité du résultat garantie, zéro quota), puis quota,
    création d'analyse et worker d'arrière-plan injecté. Le frontend poll
    ensuite GET /status/{analysis_id} comme pour une analyse normale.
    Ne lève HTTPException que pour les cas /analyze-équivalents."""
    query = (query or "").strip()
    if not query:
        raise ValueError("La question ne peut pas être vide.")

    with _conn() as conn:
        session = conn.execute(
            "SELECT * FROM conversation_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if session is None:
            raise ValueError("Session introuvable pour cet utilisateur.")
        next_no = conn.execute(
            """SELECT COALESCE(MAX(turn_no), 0) + 1 AS n
               FROM conversation_turns WHERE session_id = ?""",
            (session_id,),
        ).fetchone()["n"]

    file_hash = session["file_hash"]

    # 1) Cache : même fichier + même question -> résultat IDENTIQUE, zéro quota
    cached = db.find_cached_analysis(user_id, file_hash, query)
    if cached:
        analysis_id = str(uuid.uuid4())
        db.create_analysis(analysis_id, user_id, session["file_id"], query,
                           _now(), file_hash)
        db.update_analysis(analysis_id, status="done", result=cached["result"],
                           updated_at=_now(), user_id=user_id, file_hash=file_hash)
        turn_id = str(uuid.uuid4())
        with _conn() as conn:
            conn.execute(
                """INSERT INTO conversation_turns
                       (turn_id, session_id, user_id, turn_no, query,
                        analysis_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'done', ?)""",
                (turn_id, session_id, user_id, next_no, query, analysis_id, _now()),
            )
            conn.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?",
                (_now(), session_id),
            )
        return {"turn_id": turn_id, "turn_no": next_no,
                "analysis_id": analysis_id, "status": "done", "from_cache": True}

    # 2) Quota (exactement comme /analyze)
    allowed, remaining, renewal_at = db.check_and_increment_quota(user_id)
    if not allowed:
        from datetime import datetime
        renewal_date_str = ""
        if renewal_at:
            try:
                renewal_date = datetime.fromisoformat(renewal_at.replace("Z", "+00:00"))
                renewal_date_str = renewal_date.strftime("%d/%m/%Y")
            except ValueError:
                renewal_date_str = "date inconnue"
        raise HTTPException(
            status_code=403,
            detail=f"Quota mensuel atteint (15 analyses). Renouvellement le {renewal_date_str}."
        )

    # 3) Analyse en arrière-plan via le worker injecté (main.py en prod)
    if _background_dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="Worker d'analyse non configuré pour les conversations."
        )
    analysis_id = str(uuid.uuid4())
    db.create_analysis(analysis_id, user_id, session["file_id"], query,
                       _now(), file_hash)
    _background_dispatcher(analysis_id, user_id, session["file_id"], query)

    turn_id = str(uuid.uuid4())
    with _conn() as conn:
        conn.execute(
            """INSERT INTO conversation_turns
                   (turn_id, session_id, user_id, turn_no, query,
                    analysis_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (turn_id, session_id, user_id, next_no, query, analysis_id, _now()),
        )
        conn.execute(
            "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?",
            (_now(), session_id),
        )
    return {"turn_id": turn_id, "turn_no": next_no,
            "analysis_id": analysis_id, "status": "pending", "from_cache": False}


def set_turn_status(analysis_id: str, user_id: str, status: str) -> dict[str, Any]:
    """Synchronise le statut du turn quand l'analyse se termine (polling).
    Idempotent : ne fait rien si aucun turn ne porte cette analyse."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT * FROM conversation_turns
               WHERE analysis_id = ? AND user_id = ?""",
            (analysis_id, user_id),
        ).fetchone()
        if row is None:
            return {"synced": False}
        if row["status"] != status:
            conn.execute(
                "UPDATE conversation_turns SET status = ? WHERE turn_id = ?",
                (status, row["turn_id"]),
            )
            conn.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?",
                (_now(), row["session_id"]),
            )
        return {"synced": True, "turn_id": row["turn_id"], "status": status}


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints HTTP
# ═══════════════════════════════════════════════════════════════════════════════

def _user_id(current_user: dict) -> str:
    uid = current_user.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="Utilisateur non identifié.")
    return uid


def _vc(e: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(e))


@router.post("")
def http_create_session(
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return create_session(
            _user_id(current_user),
            file_id=body.get("file_id", ""),
            project_id=body.get("project_id"),
        )
    except ValueError as e:
        raise _vc(e)


@router.get("")
def http_list_sessions(
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    items = list_sessions(_user_id(current_user))
    return {"count": len(items), "sessions": items}


@router.get("/{session_id}")
def http_get_session(
    session_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return get_session_detail(session_id, _user_id(current_user))
    except ValueError as e:
        raise _vc(e)


@router.delete("/{session_id}")
def http_delete_session(
    session_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return delete_session(session_id, _user_id(current_user))
    except ValueError as e:
        raise _vc(e)


@router.post("/{session_id}/ask")
def http_ask(
    session_id: str,
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return ask(session_id, _user_id(current_user), body.get("query", ""))
    except ValueError as e:
        raise _vc(e)
    # HTTPException (quota 403, worker 503) propage telle quelle


@router.post("/{session_id}/project")
def http_link_project(
    session_id: str,
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return link_project(session_id, _user_id(current_user),
                            body.get("project_id", ""))
    except ValueError as e:
        raise _vc(e)
