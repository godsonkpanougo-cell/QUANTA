"""
Verrous d'intégrité d'état — V1/V3 de l'audit de sécurité (§8.2 du
RATTRAPAGE_CLAUDE_2026-10-01.md), Phase 1 du plan d'exécution (§9.2).

V1 — machine à états des analyses :
  - 'done' et 'cancelled' sont TERMINAUX : aucune réécriture possible ;
  - après CONCLUSION de l'orchestrateur (conclude_analysis : timeout ou
    erreur inattendue), toute écriture est bloquée — fin de la double
    écriture error→done par thread zombie (incident 06/10) ;
  - MAIS 'error' NON concluant reste transitionnable vers 'done' : c'est le
    mécanisme de secours du fallback (worker échoue → exécution in-memory
    réussit), qui doit continuer à fonctionner.

V3 — purge des lignes uploads expirées : le fichier physique part à 24 h,
  la ligne ne doit pas survivre (sinon /analyze retombait sur un fichier
  disparu → 500 ; désormais 404 propre + purge automatique).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

TEST_USER = "test_state_integrity_user"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _new_analysis(analysis_id: str) -> str:
    db.create_analysis(analysis_id, TEST_USER, "file-state", "q", _now(), file_hash="h")
    return analysis_id


# ─── V1 : machine à états ────────────────────────────────────────────────────


def test_done_est_terminal():
    """'done' ne peut être écrasé par aucun autre statut (verrou historique)."""
    db.clear_all()
    aid = _new_analysis("state-done-1")
    assert db.update_analysis(aid, status="done", result={"ok": 1},
                             updated_at=_now(), user_id=TEST_USER) is True
    assert db.update_analysis(aid, status="error", error="tentative",
                             updated_at=_now(), user_id=TEST_USER) is False
    assert db.get_analysis(aid, TEST_USER)["status"] == "done"


def test_rescue_error_non_conclu_vers_done_autorisee():
    """Le secours du fallback doit rester possible : error (non conclu) → done."""
    db.clear_all()
    aid = _new_analysis("state-rescue-1")
    assert db.update_analysis(aid, status="error", error="échec worker",
                             updated_at=_now(), user_id=TEST_USER) is True
    assert db.update_analysis(aid, status="done", result={"ok": 2},
                             updated_at=_now(), user_id=TEST_USER) is True
    final = db.get_analysis(aid, TEST_USER)
    assert final["status"] == "done"


def test_cancelled_est_terminal():
    """L'annulation utilisateur est définitive : aucun 'done' de zombie après."""
    db.clear_all()
    aid = _new_analysis("state-cancel-1")
    assert db.update_analysis(aid, status="running", updated_at=_now(),
                             user_id=TEST_USER) is True
    assert db.update_analysis(aid, status="cancelled", updated_at=_now(),
                             user_id=TEST_USER) is True
    assert db.update_analysis(aid, status="done", result={"ok": 3},
                             updated_at=_now(), user_id=TEST_USER) is False
    assert db.get_analysis(aid, TEST_USER)["status"] == "cancelled"


def test_conclusion_orchestrateur_bloque_le_thread_zombie():
    """Scénario exact de l'incident 06/10 : conclusion (timeout) à 480 s,
    puis le thread zombie finit et tente d'écrire 'done' → doit être bloqué,
    et le remboursement (statut 'error' au finally) reste cohérent."""
    db.clear_all()
    aid = _new_analysis("state-zombie-1")
    assert db.update_analysis(aid, status="running", updated_at=_now(),
                             user_id=TEST_USER) is True
    # Conclusion de l'orchestrateur (timeout) :
    assert db.conclude_analysis(aid, error="Timeout: Operation timeout after 480s",
                               updated_at=_now(), user_id=TEST_USER) is True
    # Le zombie tente de terminer normalement :
    assert db.update_analysis(aid, status="done", result={"trop": "tard"},
                             updated_at=_now(), user_id=TEST_USER) is False
    assert db.update_analysis(aid, status="running",
                             updated_at=_now(), user_id=TEST_USER) is False
    final = db.get_analysis(aid, TEST_USER)
    assert final["status"] == "error"
    assert "Timeout" in final["error"]
    # La conclusion est unique : une seconde tentative est ignorée.
    assert db.conclude_analysis(aid, error="double conclusion",
                               updated_at=_now(), user_id=TEST_USER) is False


def test_meme_garde_sur_le_chemin_worker():
    """update_analysis_internal (worker subprocess) applique la même machine
    à états : pas de réécriture après état terminal ni après conclusion."""
    db.clear_all()
    aid = _new_analysis("state-worker-1")
    assert db.update_analysis_internal(aid, status="running",
                                      updated_at=_now()) is True
    assert db.conclude_analysis(aid, error="Timeout", updated_at=_now(),
                               user_id=TEST_USER) is True
    assert db.update_analysis_internal(aid, status="done", result={"ok": 4},
                                      updated_at=_now()) is False
    assert db.get_analysis_internal(aid)["status"] == "error"


# ─── V3 : purge des uploads expirés ──────────────────────────────────────────


def test_purge_lignes_uploads_expirees():
    """Seules les lignes antérieures au cutoff sont purgées."""
    db.clear_all()
    from datetime import datetime, timezone, timedelta
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    recent = _now()
    db.save_upload("file-old", TEST_USER, {
        "path": "/tmp/old.csv", "filename": "old.csv",
        "numeric_cols": [], "cat_cols": [], "id_cols": [],
        "n_rows": 1, "n_cols": 1, "dataset_type": "test", "uploaded_at": old,
    })
    db.save_upload("file-new", TEST_USER, {
        "path": "/tmp/new.csv", "filename": "new.csv",
        "numeric_cols": [], "cat_cols": [], "id_cols": [],
        "n_rows": 1, "n_cols": 1, "dataset_type": "test", "uploaded_at": recent,
    })
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    deleted = db.purge_expired_uploads(cutoff)
    assert deleted == 1, f"1 ligne expirée attendue, {deleted} supprimée(s)"
    assert db.upload_exists("file-old", TEST_USER) is False
    assert db.upload_exists("file-new", TEST_USER) is True
    db.clear_all()


def test_analyze_upload_perime_retourne_404():
    """V3 côté API : /analyze sur un upload dont le fichier a disparu →
    404 explicite « fichier expiré », jamais une 500."""
    db.clear_all()
    from fastapi.testclient import TestClient
    import main
    from app import auth

    db.save_upload("file-perime", TEST_USER, {
        "path": os.path.join(os.path.dirname(__file__), "fichier_inexistant.csv"),
        "filename": "perime.csv",
        "numeric_cols": [], "cat_cols": [], "id_cols": [],
        "n_rows": 1, "n_cols": 1, "dataset_type": "test", "uploaded_at": _now(),
    })

    main.app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": TEST_USER, "email": "t@t", "name": "t", "picture_url": "",
    }
    try:
        client = TestClient(main.app)
        resp = client.post("/analyze", json={"file_id": "file-perime", "query": ""})
    finally:
        main.app.dependency_overrides.pop(auth.get_current_user, None)

    assert resp.status_code == 404, f"404 attendu, obtenu {resp.status_code}"
    assert "expiré" in resp.json()["detail"]
    db.clear_all()


# ─── Tâche 1 (renforts Phase 1) : aucun ajout de logique, tests uniquement ──


def test_migration_concluded_a_chaud_sur_base_preexistante(tmp_path, monkeypatch):
    """Base créée AVANT la migration (table analyses SANS colonne concluded,
    avec des lignes déjà insérées) : _ensure_concluded_column() doit migrer à
    chaud, préserver les lignes existantes, et la ligne legacy doit rester
    écrivable via la machine à états."""
    import sqlite3

    old_db = tmp_path / "pre_migration.db"
    conn = sqlite3.connect(old_db)
    conn.execute(
        """CREATE TABLE analyses (
               analysis_id TEXT PRIMARY KEY,
               user_id     TEXT NOT NULL,
               file_id     TEXT NOT NULL,
               query       TEXT NOT NULL,
               status      TEXT NOT NULL,
               result      TEXT,
               error       TEXT,
               created_at  TEXT NOT NULL,
               updated_at  TEXT NOT NULL,
               file_hash   TEXT
           )"""
    )
    conn.execute(
        "INSERT INTO analyses VALUES ('legacy-1','u1','f1','q','running',"
        "NULL,NULL,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','h')"
    )
    conn.commit()
    conn.close()

    # La table est volontairement dans son schéma d'AVANT migration :
    cols = [r[1] for r in sqlite3.connect(old_db).execute(
        "PRAGMA table_info(analyses)").fetchall()]
    assert "concluded" not in cols, "le test doit partir d'un schéma pré-migration"

    # Le module db pointe sur cette base, et l'indicateur de migration est
    # réarmé comme si le process venait de démarrer sur un vieux schéma.
    monkeypatch.setattr(db, "DB_PATH", str(old_db))
    monkeypatch.setattr(db, "_concluded_column_checked", False)

    # Migration à chaud + écriture sur la ligne préexistante :
    assert db.update_analysis("legacy-1", status="done", result={"ok": 1},
                             updated_at="2026-01-02T00:00:00Z", user_id="u1") is True
    row = db.get_analysis("legacy-1", "u1")
    assert row is not None
    assert row["status"] == "done", "la ligne legacy doit avoir survécu à la migration"

    cols_after = [r[1] for r in sqlite3.connect(old_db).execute(
        "PRAGMA table_info(analyses)").fetchall()]
    assert "concluded" in cols_after, "la colonne concluded doit être ajoutée à chaud"
    concluded_val = sqlite3.connect(old_db).execute(
        "SELECT concluded FROM analyses WHERE analysis_id='legacy-1'").fetchone()[0]
    assert concluded_val == 0, "la ligne legacy doit hériter du DEFAULT 0"


def test_conclude_analysis_appels_concurrents_un_seul_gagnant():
    """Deux appels quasi simultanés à conclude_analysis() sur la même analyse :
    exactement un doit réussir, l'autre doit retourner False proprement."""
    import threading

    db.clear_all()
    aid = _new_analysis("state-concurrent-1")
    assert db.update_analysis(aid, status="running", updated_at=_now(),
                             user_id=TEST_USER) is True

    results = []
    barrier = threading.Barrier(2)

    def _worker():
        barrier.wait()  # départ simultané des deux threads
        results.append(db.conclude_analysis(
            aid, error="conclusion concurrente", updated_at=_now(),
            user_id=TEST_USER))

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, "les deux threads doivent se terminer"
    assert sorted(results) == [False, True], (
        f"exactement un seul gagnant attendu, obtenu {results}"
    )
    assert db.get_analysis(aid, TEST_USER)["status"] == "error"
    db.clear_all()


def test_zombie_chemin_subprocess_bloque_apres_conclusion():
    """Cas zombie exact de l'incident 06/10, mais via le CHEMIN SUBPROCESS
    (update_analysis_internal) : après conclude_analysis (concluded=1), une
    écriture 'done' du worker doit être bloquée même si le worker vient de
    finir correctement."""
    db.clear_all()
    aid = _new_analysis("state-zombie-sub-1")
    # Le worker subprocess marque l'analyse en cours :
    assert db.update_analysis_internal(aid, status="running",
                                      updated_at=_now()) is True
    # L'orchestrateur conclut (timeout du budget global) :
    assert db.conclude_analysis(aid, error="Timeout: Operation timeout after 480s",
                               updated_at=_now(), user_id=TEST_USER) is True
    # Le worker zombie (toujours vivant) tente de terminer normalement :
    assert db.update_analysis_internal(aid, status="done", result={"trop": "tard"},
                                      updated_at=_now()) is False
    final = db.get_analysis_internal(aid)
    assert final["status"] == "error"
    assert final["result"] is None, "aucun résultat zombie ne doit être stocké"
    db.clear_all()
