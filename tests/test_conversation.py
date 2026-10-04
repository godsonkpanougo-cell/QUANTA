"""Tests Pilier 2 — Session conversationnelle (app/conversation.py).

Vérifie : création de session sur upload réel (hash mémorisé une fois),
ask réutilisant le flux /analyze (cache identité + zéro quota, puis worker
injecté différé), quota 403 équivalent /analyze, intégration Projet (P1),
isolation utilisateur, endpoints HTTP avec auth mockée.
Isolation des tables : seules conversation_* sont vidées.
Aucun LLM réel : le contenu statistique vient du cache/mock ; text_to_intent
n'est PAS appelé ici (il tourne dans le worker de prod, inchangé).
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

import db
import main
from app import auth, conversation, projects

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_conversation_tables():
    """Crée (idempotent) puis vide UNIQUEMENT les tables conversation_*.``"""
    def _reset():
        conn = sqlite3.connect(db.DB_PATH)
        conversation._ensure_tables(conn)
        for t in ("conversation_turns", "conversation_sessions"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def reset_dispatcher():
    yield
    # remet le dispatcher prod (injecté par main.py) après les tests qui le mockent
    conversation.set_background_dispatcher(main._deferred_analysis_background)


def _user(n: str) -> str:
    return db.create_or_update_user(
        google_sub=f"conv-{n}", email=f"conv-{n}@test.com",
        name=f"Conv Test {n}", picture_url="http://example.com/a.png",
    )


def _auth_as(user_id: str, google_sub: str, email: str):
    main.app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": user_id, "google_sub": google_sub, "email": email,
    }


def _upload_real_file(uid: str, content: str = "x,y\n1,2\n2,4\n3,6\n4,8\n") -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    file_id = f"conv-{hashlib.sha256(path.encode()).hexdigest()[:8]}"
    db.save_upload(
        file_id=file_id, user_id=uid,
        data={"path": path, "filename": "data.csv", "numeric_cols": ["x", "y"],
              "cat_cols": [], "id_cols": [], "n_rows": 4, "n_cols": 2,
              "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"},
    )
    return file_id


# ── Sessions ─────────────────────────────────────────────────────────────────

def test_create_session_hashes_file_once():
    uid = _user("s1")
    file_id = _upload_real_file(uid)
    s = conversation.create_session(uid, file_id)
    assert s["file_hash"] == hashlib.sha256(
        open(db.get_upload(file_id, uid)["path"], "rb").read()
    ).hexdigest()
    assert s["project_id"] is None


def test_create_session_rejects_unknown_or_foreign_file():
    uid, other = _user("s2"), _user("s2b")
    file_id = _upload_real_file(uid)
    with pytest.raises(ValueError):
        conversation.create_session(uid, "fichier-inexistant")
    with pytest.raises(ValueError):
        conversation.create_session(other, file_id)  # fichier d'un autre user


def test_session_isolation_between_users():
    uid, other = _user("s3"), _user("s3b")
    file_id = _upload_real_file(uid)
    s = conversation.create_session(uid, file_id)
    with pytest.raises(ValueError):
        conversation.get_session_detail(s["session_id"], other)
    with pytest.raises(ValueError):
        conversation.delete_session(s["session_id"], other)
    assert conversation.list_sessions(other) == []


# ── ask : cache d'abord (identité, zéro quota) ───────────────────────────────

def _seed_cached_analysis(uid: str, file_id: str, query: str) -> None:
    # analysis_id unique (uuid) : la DB de test persiste entre les runs
    # pytest, un id déterministe entrerait en collision UNIQUE.
    import uuid as _uuid
    file_hash = hashlib.sha256(
        open(db.get_upload(file_id, uid)["path"], "rb").read()
    ).hexdigest()
    analysis_id = str(_uuid.uuid4())
    db.create_analysis(analysis_id, uid, file_id, query,
                       "2024-01-01T00:00:00Z", file_hash)
    db.update_analysis(
        analysis_id=analysis_id, status="done",
        result={"confidence_score": {"score_global": 77.0}},
        updated_at="2024-01-01T00:00:00Z", user_id=uid, file_hash=file_hash,
    )


def test_ask_cache_hit_zero_quota_and_identical_result():
    uid = _user("a1")
    file_id = _upload_real_file(uid)
    sid = conversation.create_session(uid, file_id)["session_id"]
    _seed_cached_analysis(uid, file_id, "correlation x et y")
    quota_before = db.get_quota_info(uid)["remaining"]
    out = conversation.ask(sid, uid, "  correlation x et y  ")  # strip
    assert out["from_cache"] is True and out["status"] == "done"
    assert db.get_quota_info(uid)["remaining"] == quota_before  # zéro quota
    detail = conversation.get_session_detail(sid, uid)
    assert detail["turns"][0]["turn_no"] == 1
    assert detail["turns"][0]["status"] == "done"


def test_ask_dispatches_deferred_and_syncs_on_status_poll():
    uid = _user("a2")
    file_id = _upload_real_file(uid)
    sid = conversation.create_session(uid, file_id)["session_id"]
    dispatched: list[tuple] = []

    def fake_worker(analysis_id, user_id, fid, query):
        dispatched.append((analysis_id, user_id, fid, query))
        # simule la fin de l'analyse comme le worker réel
        db.update_analysis(analysis_id, status="done", result={"ok": True},
                           updated_at="2024-01-01T00:00:00Z", user_id=user_id)

    conversation.set_background_dispatcher(fake_worker)
    quota_before = db.get_quota_info(uid)["remaining"]
    out = conversation.ask(sid, uid, "compare x selon y")
    assert out["status"] == "pending" and out["from_cache"] is False
    assert len(dispatched) == 1
    # le quota a bien été consommé exactement comme /analyze
    assert db.get_quota_info(uid)["remaining"] == quota_before - 1

    # le frontend poll /status : le turn se synchronise (idempotent)
    main.app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": uid, "google_sub": "conv-a2", "email": "conv-a2@test.com",
    }
    try:
        st = client.get(f"/status/{out['analysis_id']}").json()
        assert st["status"] == "done"
        turn = conversation.get_session_detail(sid, uid)["turns"][0]
        assert turn["status"] == "done" and turn["analysis_id"] == out["analysis_id"]
    finally:
        main.app.dependency_overrides.clear()


def test_ask_quota_exhausted_403_like_analyze():
    uid = _user("a3")
    file_id = _upload_real_file(uid)
    sid = conversation.create_session(uid, file_id)["session_id"]
    # épuise le quota (15 analyses/mois — colonne analyses_count, sans
    # quota_renewal_at le renouvellement ne remet pas à zéro)
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        "UPDATE users SET analyses_count = 15 WHERE user_id = ?", (uid,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(Exception) as excinfo:
        conversation.ask(sid, uid, "une question")
    assert "Quota mensuel atteint" in str(excinfo.value)


def test_ask_rejects_empty_query():
    uid = _user("a4")
    file_id = _upload_real_file(uid)
    sid = conversation.create_session(uid, file_id)["session_id"]
    with pytest.raises(ValueError):
        conversation.ask(sid, uid, "   ")


# ── Intégration Pilier 1 (Projet) ────────────────────────────────────────────

def test_link_session_to_project_and_cross_user_protection():
    uid, other = _user("p1"), _user("p1b")
    file_id = _upload_real_file(uid)
    pid = projects.create_project(uid, "Mon mémoire")["project_id"]
    sid = conversation.create_session(uid, file_id)["session_id"]
    out = conversation.link_project(sid, uid, pid)
    assert out["project_id"] == pid
    with pytest.raises(ValueError):
        conversation.link_project(sid, uid, "projet-dun-autre")


# ── Endpoints HTTP ───────────────────────────────────────────────────────────

def test_http_lifecycle_auth_required_and_cross_user():
    uid = _user("h1")
    _auth_as(uid, "conv-h1", "conv-h1@test.com")
    file_id = _upload_real_file(uid)
    try:
        r = client.post("/conversations", json={"file_id": file_id})
        assert r.status_code == 200
        sid = r.json()["session_id"]

        r = client.get("/conversations")
        assert r.status_code == 200 and r.json()["count"] == 1

        r = client.post(f"/conversations/{sid}/ask", json={"query": "q"})
        assert r.status_code in (200, 403)  # 200 (cache) ou 403 (quota selon env)

        r = client.delete(f"/conversations/{sid}")
        assert r.status_code == 200 and r.json()["deleted"] is True
        assert client.get(f"/conversations/{sid}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()

    # sans session : 401/403
    main.app.dependency_overrides.clear()
    assert client.get("/conversations").status_code in (401, 403)

    # cross-user : 404
    other = _user("h2")
    file_id2 = _upload_real_file(other)
    sid2 = conversation.create_session(other, file_id2)["session_id"]
    _auth_as(uid, "conv-h1", "conv-h1@test.com")
    try:
        assert client.get(f"/conversations/{sid2}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()
