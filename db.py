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
import uuid
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
    # Utiliser une connexion directe pour la migration (pas de context manager pour éviter le double commit)
    conn = _connect()
    try:
        # Vérifier si la table users existe déjà
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone() is not None
        
        if table_exists:
            # Migration explicite : supprimer la contrainte NOT NULL sur quota_renewal_at
            # SQLite ne supporte pas DROP CONSTRAINT, donc on recrée la table
            try:
                # Vérifier si la colonne a encore la contrainte NOT NULL
                columns = conn.execute("PRAGMA table_info(users)").fetchall()
                quota_col = [c for c in columns if c[1] == "quota_renewal_at"]
                if quota_col and quota_col[0][3] == 1:  # notnull=1 signifie NOT NULL
                    print("Migration détectée : suppression contrainte NOT NULL sur quota_renewal_at", flush=True)
                    # Transaction explicite pour garantir l'atomicité (évite perte de données si crash entre DROP et RENAME)
                    conn.execute("BEGIN TRANSACTION")
                    try:
                        # Recréer la table sans la contrainte NOT NULL
                        conn.execute("""
                            CREATE TABLE users_new (
                                user_id      TEXT PRIMARY KEY,
                                google_sub   TEXT UNIQUE NOT NULL,
                                email        TEXT UNIQUE NOT NULL,
                                name         TEXT,
                                picture_url  TEXT,
                                created_at   TEXT NOT NULL,
                                last_login_at TEXT,
                                analyses_count INTEGER DEFAULT 0,
                                quota_renewal_at TEXT
                            )
                        """)
                        # Copier les données
                        conn.execute("""
                            INSERT INTO users_new 
                            SELECT user_id, google_sub, email, name, picture_url, created_at, last_login_at, analyses_count, quota_renewal_at
                            FROM users
                        """)
                        # Supprimer l'ancienne table et renommer
                        conn.execute("DROP TABLE users")
                        conn.execute("ALTER TABLE users_new RENAME TO users")
                        conn.commit()
                        print("Migration terminée : contrainte NOT NULL supprimée", flush=True)
                    except Exception:
                        conn.rollback()
                        raise
            except Exception as e:
                # Erreur ignorée : la migration a peut-être déjà été appliquée
                pass
        else:
            # Table n'existe pas : créer avec le nouveau schéma
            conn.execute("""
                CREATE TABLE users (
                    user_id      TEXT PRIMARY KEY,
                    google_sub   TEXT UNIQUE NOT NULL,
                    email        TEXT UNIQUE NOT NULL,
                    name         TEXT,
                    picture_url  TEXT,
                    created_at   TEXT NOT NULL,
                    last_login_at TEXT,
                    analyses_count INTEGER DEFAULT 0,
                    quota_renewal_at TEXT
                )
            """)
            conn.commit()
        
        # Migration pour les utilisateurs existants : ajouter les colonnes si elles n'existent pas
        try:
            conn.execute("ALTER TABLE users ADD COLUMN analyses_count INTEGER DEFAULT 0")
            conn.commit()
        except:
            pass  # La colonne existe déjà
        try:
            conn.execute("ALTER TABLE users ADD COLUMN quota_renewal_at TEXT")
            conn.commit()
        except:
            pass  # La colonne existe déjà
            
        # Créer les autres tables
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
        conn.commit()
    finally:
        conn.close()


def clear_all() -> None:
    """Vide les tables (isolation entre scripts de test API in-process)."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM uploads")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")


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


def get_analysis_internal(analysis_id: str) -> dict[str, Any] | None:
    """
    Récupère une analyse sans vérification de propriétaire.
    
    Réservée aux workers de confiance (ex: analyze_worker.py) qui ont besoin
    d'accéder aux métadonnées d'une analyse pour effectuer des opérations
    système (timeout, génération de rapport, etc.).
    
    NE PAS utiliser dans les endpoints publics HTTP.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE analysis_id = ?",
            (analysis_id,)
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
    name: str,
    picture_url: str,
) -> str:
    """
    Crée ou met à jour un utilisateur via Google OAuth.
    Retourne le user_id.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    renewal_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")

    with _get_conn() as conn:
        # Chercher par google_sub
        existing = conn.execute(
            "SELECT user_id FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()

        if existing:
            user_id = existing["user_id"]
            # Mettre à jour last_login_at et potentiellement name/picture_url
            # Initialiser les colonnes de quota si elles sont NULL
            conn.execute(
                """UPDATE users
                   SET last_login_at = ?, name = ?, picture_url = ?,
                       analyses_count = COALESCE(analyses_count, 0),
                       quota_renewal_at = CASE 
                           WHEN quota_renewal_at IS NULL OR quota_renewal_at = '' 
                           THEN ? 
                           ELSE quota_renewal_at 
                       END
                   WHERE user_id = ?""",
                (now, name, picture_url, renewal_date, user_id),
            )
            return user_id
        else:
            # Créer nouvel utilisateur avec quota initialisé
            user_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO users
                   (user_id, google_sub, email, name, picture_url, created_at, last_login_at, analyses_count, quota_renewal_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (user_id, google_sub, email, name, picture_url, now, now, renewal_date),
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
        "analyses_count": row["analyses_count"] if "analyses_count" in row.keys() else 0,
        "quota_renewal_at": row["quota_renewal_at"] if "quota_renewal_at" in row.keys() else "",
    }


def check_and_increment_quota(user_id: str, monthly_limit: int = 15) -> tuple[bool, int, str]:
    """
    Vérifie et incrémente le quota d'analyses de manière atomique.
    
    Retourne (allowed, remaining, renewal_date):
    - allowed: True si l'analyse est autorisée, False si quota dépassé
    - remaining: nombre d'analyses restantes après incrémentation (si allowed=True)
                 ou 0 (si allowed=False)
    - renewal_date: date de renouvellement du quota (ISO 8601)
    
    Transaction atomique pour éviter les race conditions.
    """
    from datetime import datetime, timezone, timedelta

    with _get_conn() as conn:
        # Récupérer le quota actuel
        row = conn.execute(
            "SELECT analyses_count, quota_renewal_at FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if row is None:
            return False, 0, ""
        
        current_count = row["analyses_count"] or 0
        renewal_at_str = row["quota_renewal_at"] or ""
        
        # Vérifier si le quota doit être renouvelé (plus d'un mois calendrier)
        now = datetime.now(timezone.utc)
        if renewal_at_str:
            try:
                # Nettoyer la date: remplacer Z par +00:00 et éviter les doublons
                date_to_parse = renewal_at_str.replace("Z", "+00:00")
                if date_to_parse.endswith("+00:00+00:00"):
                    date_to_parse = date_to_parse.replace("+00:00+00:00", "+00:00")
                renewal_at = datetime.fromisoformat(date_to_parse)
                # S'assurer que renewal_at est timezone-aware
                if renewal_at.tzinfo is None:
                    renewal_at = renewal_at.replace(tzinfo=timezone.utc)
                # Comparer les dates
                if now >= renewal_at:
                    # Renouvellement : remettre à 0 et nouvelle date
                    new_renewal = (now + timedelta(days=30)).isoformat().replace("+00:00", "Z")
                    conn.execute(
                        """UPDATE users
                           SET analyses_count = 0, quota_renewal_at = ?
                           WHERE user_id = ?""",
                        (new_renewal, user_id)
                    )
                    current_count = 0
                    renewal_at_str = new_renewal
            except ValueError as e:
                # Date invalide, ignorer et utiliser la valeur actuelle
                import sys
                print(f"Erreur parsing date renouvellement: {e}", file=sys.stderr)
                pass
        
        # Vérifier le quota
        if current_count >= monthly_limit:
            return False, 0, renewal_at_str
        
        # Incrémenter le compteur
        new_count = current_count + 1
        conn.execute(
            "UPDATE users SET analyses_count = ? WHERE user_id = ?",
            (new_count, user_id)
        )
        
        remaining = monthly_limit - new_count
        return True, remaining, renewal_at_str


def get_quota_info(user_id: str, monthly_limit: int = 15) -> dict[str, Any] | None:
    """
    Récupère les informations de quota d'un utilisateur.
    Retourne None si l'utilisateur n'existe pas.
    Initialise les colonnes quota si elles sont NULL (utilisateurs pré-migration).
    """
    from datetime import datetime, timezone

    with _get_conn() as conn:
        # Essayer de récupérer les colonnes quota
        try:
            row = conn.execute(
                "SELECT analyses_count, quota_renewal_at FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
        except Exception as e:
            # Si les colonnes n'existent pas (erreur SQLite), les créer
            print(f"Colonnes quota manquantes pour user_id={user_id}, tentative d'initialisation: {e}", file=sys.stderr)
            try:
                conn.execute("ALTER TABLE users ADD COLUMN analyses_count INTEGER DEFAULT 0")
                conn.execute("ALTER TABLE users ADD COLUMN quota_renewal_at TEXT")
                conn.commit()
                # Réessayer après création des colonnes
                row = conn.execute(
                    "SELECT analyses_count, quota_renewal_at FROM users WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
            except Exception as e2:
                print(f"Échec création colonnes quota: {e2}", file=sys.stderr)
                return None
    
    if row is None:
        return None
    
    current_count = row["analyses_count"] or 0
    renewal_at_str = row["quota_renewal_at"] or ""
    
    # Si renewal_at est vide (utilisateur pré-migration), l'initialiser
    if not renewal_at_str:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        new_renewal = (now + timedelta(days=30)).isoformat().replace("+00:00", "Z")
        with _get_conn() as conn:
            conn.execute(
                "UPDATE users SET analyses_count = 0, quota_renewal_at = ? WHERE user_id = ?",
                (new_renewal, user_id)
            )
            conn.commit()
        renewal_at_str = new_renewal
        current_count = 0
    
    # Vérifier si le quota doit être renouvelé (lecture seule)
    now = datetime.now(timezone.utc)
    if renewal_at_str:
        try:
            # Nettoyer la date: remplacer Z par +00:00 et éviter les doublons
            date_to_parse = renewal_at_str.replace("Z", "+00:00")
            if date_to_parse.endswith("+00:00+00:00"):
                date_to_parse = date_to_parse.replace("+00:00+00:00", "+00:00")
            renewal_at = datetime.fromisoformat(date_to_parse)
            # S'assurer que renewal_at est timezone-aware
            if renewal_at.tzinfo is None:
                renewal_at = renewal_at.replace(tzinfo=timezone.utc)
            if now >= renewal_at:
                # Le quota est expiré mais non renouvelé (lecture seule)
                current_count = 0
        except ValueError:
            pass
    
    remaining = max(0, monthly_limit - current_count)
    
    return {
        "limit": monthly_limit,
        "used": current_count,
        "remaining": remaining,
        "renewal_at": renewal_at_str,
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
