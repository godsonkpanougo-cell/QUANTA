"""
QUANTA — projects.py (Pilier 1 : Projet de recherche persistant)

Pourquoi : un mémoire = 6 mois sur les MÊMES données. Aujourd'hui QUANTA
traiter un upload comme un événement ponctuel (upload -> analyse -> PDF).
Le Projet transforme QUANTA en l'endroit où vit le travail de recherche :
  - un dataset versionné (hash sha256, source conservée) ;
  - des analyses REJOUABLES à l'identique (mêmes file_hash + query =
    cache-hit garanti par db.find_cached_analysis) ;
  - un historique complet par projet ;
  - une comparaison de versions (delta de confiance + tests finis).

Isolation (règle « sans casser l'existant ») :
  -ses propres tables SQLite (`project_*`, IF NOT EXISTS : zéro migration,
   zéro touch du schéma de db.py) ;
  - se connecte à la MÊME base via db.DB_PATH / db._get_conn ;
  - tous les accès sont filtrés par user_id (isolation stricte comme db.py) ;
  - aucun module existant ne l'importe : le branchement se réduit à
    `import app.projects as projects` + `app.include_router(projects.router)`
    dans main.py (2 lignes).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import db
from app import auth

router = APIRouter(prefix="/projects", tags=["projects"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schéma (tables dédiées, IF NOT EXISTS — aucune migration destructive)
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_projects (
               project_id   TEXT PRIMARY KEY,
               user_id      TEXT NOT NULL,
               name         TEXT NOT NULL,
               description  TEXT DEFAULT '',
               dataset_hash TEXT,
               created_at   TEXT NOT NULL,
               updated_at   TEXT NOT NULL
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_dataset_versions (
               version_id  TEXT PRIMARY KEY,
               project_id  TEXT NOT NULL,
               user_id     TEXT NOT NULL,
               version_no  INTEGER NOT NULL,
               file_hash   TEXT NOT NULL,
               file_id     TEXT,
               filename    TEXT NOT NULL,
               n_rows      INTEGER,
               n_cols      INTEGER,
               created_at  TEXT NOT NULL,
               UNIQUE(project_id, version_no)
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_runs (
               run_id      TEXT PRIMARY KEY,
               project_id  TEXT NOT NULL,
               user_id     TEXT NOT NULL,
               version_id  TEXT NOT NULL,
               query       TEXT NOT NULL DEFAULT '',
               analysis_id TEXT,
               status      TEXT NOT NULL DEFAULT 'pending',
               summary     TEXT,
               created_at  TEXT NOT NULL
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pproj_user ON project_projects(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pver_proj ON project_dataset_versions(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prun_proj ON project_runs(project_id)"
    )


@contextmanager
def _conn():
    """Connexion dédiée : tables garanties, commit/rollback, fermeture propre
    (le context-manager natif de sqlite3 ne FERME PAS la connexion)."""
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
# Couche métier (hors HTTP, testable directement)
# ═══════════════════════════════════════════════════════════════════════════════

def create_project(user_id: str, name: str, description: str = "",
                   dataset_hash: str | None = None) -> dict[str, Any]:
    if not (name or "").strip():
        raise ValueError("Le nom du projet ne peut pas être vide.")
    pid = str(uuid.uuid4())
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO project_projects
                   (project_id, user_id, name, description, dataset_hash,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, user_id, name.strip(), description or "", dataset_hash, now, now),
        )
    return {"project_id": pid, "name": name.strip(), "created_at": now}


def list_projects(user_id: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT p.*, 
                      (SELECT COUNT(*) FROM project_runs r 
                        WHERE r.project_id = p.project_id) AS n_runs,
                      (SELECT COUNT(*) FROM project_dataset_versions v 
                        WHERE v.project_id = p.project_id) AS n_versions
               FROM project_projects p
               WHERE p.user_id = ?
               ORDER BY p.updated_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_project_owned(conn: sqlite3.Connection, project_id: str,
                       user_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM project_projects WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if row is None:
        raise ValueError("Projet introuvable pour cet utilisateur.")
    return row


def get_project(project_id: str, user_id: str) -> dict[str, Any]:
    with _conn() as conn:
        proj = dict(_get_project_owned(conn, project_id, user_id))
        versions = [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM project_dataset_versions
                   WHERE project_id = ? ORDER BY version_no ASC""",
                (project_id,),
            ).fetchall()
        ]
        runs = [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM project_runs
                   WHERE project_id = ? ORDER BY created_at ASC""",
                (project_id,),
            ).fetchall()
        ]
    proj["versions"] = versions
    proj["runs"] = runs
    return proj


def delete_project(project_id: str, user_id: str) -> dict[str, Any]:
    with _conn() as conn:
        _get_project_owned(conn, project_id, user_id)
        conn.execute(
            "DELETE FROM project_runs WHERE project_id = ?", (project_id,)
        )
        conn.execute(
            "DELETE FROM project_dataset_versions WHERE project_id = ?",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM project_projects WHERE project_id = ?", (project_id,)
        )
    return {"project_id": project_id, "deleted": True}


def add_dataset_version(project_id: str, user_id: str, file_hash: str,
                        filename: str, file_id: str | None = None,
                        n_rows: int | None = None,
                        n_cols: int | None = None) -> dict[str, Any]:
    """Ajoute une version de dataset ; si le hash existe déjà pour ce projet,
    retourne la version existante (idempotent — même fichier = même version)."""
    with _conn() as conn:
        _get_project_owned(conn, project_id, user_id)
        existing = conn.execute(
            """SELECT * FROM project_dataset_versions
               WHERE project_id = ? AND file_hash = ?""",
            (project_id, file_hash),
        ).fetchone()
        if existing is not None:
            return dict(existing)
        next_no = conn.execute(
            """SELECT COALESCE(MAX(version_no), 0) + 1 AS n
               FROM project_dataset_versions WHERE project_id = ?""",
            (project_id,),
        ).fetchone()["n"]
        vid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO project_dataset_versions
                   (version_id, project_id, user_id, version_no, file_hash,
                    file_id, filename, n_rows, n_cols, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vid, project_id, user_id, next_no, file_hash, file_id,
             filename, n_rows, n_cols, _now()),
        )
        conn.execute(
            "UPDATE project_projects SET updated_at = ? WHERE project_id = ?",
            (_now(), project_id),
        )
        row = conn.execute(
            "SELECT * FROM project_dataset_versions WHERE version_id = ?",
            (vid,),
        ).fetchone()
    return dict(row)


def add_run(project_id: str, user_id: str, version_id: str,
            query: str) -> dict[str, Any]:
    """Enregistre une exécution (analyse) sur une version du projet."""
    with _conn() as conn:
        _get_project_owned(conn, project_id, user_id)
        ver = conn.execute(
            """SELECT * FROM project_dataset_versions
               WHERE version_id = ? AND project_id = ?""",
            (version_id, project_id),
        ).fetchone()
        if ver is None:
            raise ValueError("Version de dataset introuvable pour ce projet.")
        rid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO project_runs
                   (run_id, project_id, user_id, version_id, query,
                    analysis_id, status, summary, created_at)
               VALUES (?, ?, ?, ?, ?, NULL, 'pending', NULL, ?)""",
            (rid, project_id, user_id, version_id, query or "", _now()),
        )
        conn.execute(
            "UPDATE project_projects SET updated_at = ? WHERE project_id = ?",
            (_now(), project_id),
        )
        row = conn.execute(
            "SELECT * FROM project_runs WHERE run_id = ?", (rid,)
        ).fetchone()
    return dict(row)


def attach_analysis(run_id: str, user_id: str, analysis_id: str,
                    status: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lie une analyse terminée à son run (appelé après le polling)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM project_runs WHERE run_id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Run introuvable pour cet utilisateur.")
        conn.execute(
            """UPDATE project_runs
               SET analysis_id = ?, status = ?, summary = ?
               WHERE run_id = ?""",
            (analysis_id, status,
             json.dumps(summary, ensure_ascii=False) if summary else None,
             run_id),
        )
        row = conn.execute(
            "SELECT * FROM project_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    out = dict(row)
    if out.get("summary"):
        out["summary"] = json.loads(out["summary"])
    return out


def _extract_confidence(analysis_result: dict[str, Any] | None) -> float | None:
    if not isinstance(analysis_result, dict):
        return None
    conf = analysis_result.get("confidence_score") or analysis_result.get("confidence")
    if isinstance(conf, dict):
        try:
            return float(conf.get("score_global"))
        except (TypeError, ValueError):
            return None
    return None


def _extract_tests(analysis_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(analysis_result, dict):
        return []
    tests = analysis_result.get("tests_effectues")
    if not isinstance(tests, list):
        return []
    out = []
    for t in tests:
        if isinstance(t, dict):
            out.append({
                "name": t.get("name") or t.get("test") or "?",
                "p_value": t.get("p_value"),
                "statistic": t.get("statistic") or t.get("stat"),
                "decision": t.get("decision") or t.get("conclusion"),
            })
    return out


def replay_run(run_id: str, user_id: str) -> dict[str, Any]:
    """Rejoue une exécution À L'IDENTIQUE : mêmes données (file_hash) +
    même requête => le cache d'analyses de db.py garantit le même résultat.
    Retourne {replayed, from_cache, analysis}."""
    with _conn() as conn:
        run = conn.execute(
            "SELECT * FROM project_runs WHERE run_id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
        if run is None:
            raise ValueError("Run introuvable pour cet utilisateur.")
        ver = conn.execute(
            "SELECT * FROM project_dataset_versions WHERE version_id = ?",
            (run["version_id"],),
        ).fetchone()
    if ver is None:
        raise ValueError("Version de dataset introuvable.")
    cached = db.find_cached_analysis(user_id, ver["file_hash"], run["query"])
    if cached is None:
        return {
            "replayed": False,
            "from_cache": False,
            "reason": (
                "Aucune analyse terminée en cache pour (file_hash, query). "
                "Relancez d'abord l'analyse via /analyze avec ce fichier."
            ),
            "file_hash": ver["file_hash"],
            "query": run["query"],
        }
    return {
        "replayed": True,
        "from_cache": True,
        "analysis_id": cached["analysis_id"],
        "result": cached["result"],
    }


def compare_versions(project_id: str, user_id: str,
                     version_a: str, version_b: str) -> dict[str, Any]:
    """Compare les DERNIERS runs terminés de deux versions du projet :
    delta de confiance + paires de tests présentes dans les deux."""
    with _conn() as conn:
        _get_project_owned(conn, project_id, user_id)
        for vid in (version_a, version_b):
            v = conn.execute(
                """SELECT * FROM project_dataset_versions
                   WHERE version_id = ? AND project_id = ?""",
                (vid, project_id),
            ).fetchone()
            if v is None:
                raise ValueError(f"Version {vid} introuvable pour ce projet.")
        latest = {}
        for vid in (version_a, version_b):
            row = conn.execute(
                """SELECT * FROM project_runs
                   WHERE version_id = ? AND status = 'done'
                   ORDER BY created_at DESC LIMIT 1""",
                (vid,),
            ).fetchone()
            latest[vid] = dict(row) if row else None
    if latest[version_a] is None or latest[version_b] is None:
        return {
            "comparable": False,
            "reason": "Chaque version doit avoir au moins un run terminé (status='done').",
        }

    results = {}
    for vid, run in latest.items():
        res = db.get_analysis_internal(run["analysis_id"])
        results[vid] = {
            "analysis": (res or {}).get("result"),
            "query": run["query"],
        }

    conf_a = _extract_confidence(results[version_a]["analysis"])
    conf_b = _extract_confidence(results[version_b]["analysis"])
    tests_a = {(t["name"], t["decision"]): t for t in _extract_tests(results[version_a]["analysis"])}
    tests_b = {(t["name"], t["decision"]): t for t in _extract_tests(results[version_b]["analysis"])}

    tests_delta = []
    for key in sorted(set(tests_a) | set(tests_b)):
        ta, tb = tests_a.get(key), tests_b.get(key)
        p_a, p_b = (ta or {}).get("p_value"), (tb or {}).get("p_value")
        delta_p = (
            round(float(p_b) - float(p_a), 6)
            if isinstance(p_a, (int, float)) and isinstance(p_b, (int, float))
            else None
        )
        tests_delta.append({
            "test": key[0],
            "decision_a": key[1] if ta else None,
            "decision_b": key[1] if tb else None,
            "p_value_a": p_a,
            "p_value_b": p_b,
            "delta_p_value": delta_p,
            "only_in": ("a" if ta and not tb else "b" if tb and not ta else None),
        })

    return {
        "comparable": True,
        "version_a": version_a,
        "version_b": version_b,
        "confidence": {
            "a": conf_a,
            "b": conf_b,
            "delta": (
                round(conf_b - conf_a, 1)
                if isinstance(conf_a, float) and isinstance(conf_b, float)
                else None
            ),
        },
        "tests_delta": tests_delta,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints HTTP (isolation user stricte via auth.get_current_user)
# ═══════════════════════════════════════════════════════════════════════════════

def _user_id(current_user: dict) -> str:
    uid = current_user.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="Utilisateur non identifié.")
    return uid


@router.post("")
def http_create_project(
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return create_project(
            _user_id(current_user),
            name=body.get("name", ""),
            description=body.get("description", ""),
            dataset_hash=body.get("dataset_hash"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("")
def http_list_projects(
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    items = list_projects(_user_id(current_user))
    return {"count": len(items), "projects": items}


@router.get("/{project_id}")
def http_get_project(
    project_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return get_project(project_id, _user_id(current_user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{project_id}")
def http_delete_project(
    project_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return delete_project(project_id, _user_id(current_user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{project_id}/versions")
def http_add_version(
    project_id: str,
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return add_dataset_version(
            project_id,
            _user_id(current_user),
            file_hash=body.get("file_hash", ""),
            filename=body.get("filename", ""),
            file_id=body.get("file_id"),
            n_rows=body.get("n_rows"),
            n_cols=body.get("n_cols"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{project_id}/runs")
def http_add_run(
    project_id: str,
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return add_run(
            project_id,
            _user_id(current_user),
            version_id=body.get("version_id", ""),
            query=body.get("query", ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/runs/{run_id}/attach")
def http_attach_analysis(
    run_id: str,
    body: dict[str, Any],
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return attach_analysis(
            run_id,
            _user_id(current_user),
            analysis_id=body.get("analysis_id", ""),
            status=body.get("status", "done"),
            summary=body.get("summary"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/runs/{run_id}/replay")
def http_replay_run(
    run_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return replay_run(run_id, _user_id(current_user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{project_id}/compare")
def http_compare_versions(
    project_id: str,
    version_a: str,
    version_b: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return compare_versions(project_id, _user_id(current_user),
                                version_a, version_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
