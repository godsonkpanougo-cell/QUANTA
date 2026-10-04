"""Tests Pilier 1 — Projet de recherche persistant (app/projects.py).

Isolation garantie : les tables project_* sont dédiées et vidées après
chaque test ; db.init_db()/clear_all() n'y touchent pas.
Aucun réseau, aucun LLM : TestClient + auth mockée (pattern de test_cache.py).
"""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

import db
import main
from app import auth, projects

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_project_tables():
    """Crée (idempotent) puis vide UNIQUEMENT les tables project_*
    (jamais les tables de db.py)."""
    import sqlite3

    def _reset():
        conn = sqlite3.connect(db.DB_PATH)
        projects._ensure_tables(conn)
        for t in ("project_runs", "project_dataset_versions", "project_projects"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()

    _reset()
    yield
    _reset()


def _user(n: str) -> str:
    # google_sub unique par run (DB de test persistante entre les runs).
    import uuid as _uuid
    tag = _uuid.uuid4().hex[:8]
    return db.create_or_update_user(
        google_sub=f"proj-{n}-{tag}",
        email=f"proj-{n}-{tag}@test.com",
        name=f"Proj Test {n}", picture_url="http://example.com/a.png",
    )


def _auth_as(user_id: str, google_sub: str, email: str):
    app = main.app
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": user_id, "google_sub": google_sub, "email": email,
    }


# ── Couche métier ─────────────────────────────────────────────────────────────

def test_create_list_get_delete_project():
    uid = _user("u1")
    proj = projects.create_project(uid, " Mémoire L2 ", "Tobit sur L2")
    assert proj["name"] == "Mémoire L2"  # strip appliqué
    items = projects.list_projects(uid)
    assert items[0]["n_runs"] == 0 and items[0]["n_versions"] == 0
    got = projects.get_project(proj["project_id"], uid)
    assert got["versions"] == [] and got["runs"] == []
    assert projects.delete_project(proj["project_id"], uid)["deleted"] is True
    with pytest.raises(ValueError):
        projects.get_project(proj["project_id"], uid)


def test_create_project_rejects_blank_name():
    with pytest.raises(ValueError):
        projects.create_project("u", "   ")


def test_project_isolation_between_users():
    u1, u2 = _user("i1"), _user("i2")
    proj = projects.create_project(u1, "Privé")
    with pytest.raises(ValueError):
        projects.get_project(proj["project_id"], u2)
    with pytest.raises(ValueError):
        projects.delete_project(proj["project_id"], u2)
    assert projects.list_projects(u2) == []


def test_versions_idempotent_by_hash_and_increment():
    uid = _user("v1")
    pid = projects.create_project(uid, "Versions")["project_id"]
    h1 = hashlib.sha256(b"dataset-v1").hexdigest()
    h2 = hashlib.sha256(b"dataset-v2").hexdigest()
    v1 = projects.add_dataset_version(pid, uid, h1, "L2_tobit.dta", n_rows=301, n_cols=121)
    v1b = projects.add_dataset_version(pid, uid, h1, "L2_tobit.dta")  # même hash
    assert v1["version_id"] == v1b["version_id"]  # idempotent
    v2 = projects.add_dataset_version(pid, uid, h2, "L2_nettoye.dta")
    assert (v1["version_no"], v2["version_no"]) == (1, 2)


# ── Replay : identité garantie par le cache (file_hash, query) ────────────────

def _make_cached_analysis(uid: str, file_hash: str, query: str) -> str:
    # ids uniques par run : la DB de test persiste entre les runs pytest
    # (uploads/analyses ont des contraintes UNIQUE).
    import uuid as _uuid
    tag = _uuid.uuid4().hex[:8]
    file_id = f"f-{tag}"
    db.save_upload(
        file_id=file_id, user_id=uid,
        data={"path": "x.csv", "filename": "L2.dta", "numeric_cols": [],
              "cat_cols": [], "id_cols": [], "n_rows": 301, "n_cols": 121,
              "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"},
    )
    analysis_id = f"a-{tag}"
    db.create_analysis(
        analysis_id=analysis_id, user_id=uid, file_id=file_id,
        query=query, created_at="2024-01-01T00:00:00Z", file_hash=file_hash,
    )
    db.update_analysis(
        analysis_id=analysis_id, status="done",
        result={"confidence_score": {"score_global": 82.5},
                "tests_effectues": [{"name": "Spearman", "p_value": 0.001,
                                     "decision": "significative"}]},
        updated_at="2024-01-01T00:00:00Z", user_id=uid, file_hash=file_hash,
    )
    return analysis_id


def test_replay_returns_identical_cached_result():
    uid = _user("r1")
    pid = projects.create_project(uid, "Replay")["project_id"]
    fh = hashlib.sha256(b"donnees-reelles").hexdigest()
    vid = projects.add_dataset_version(pid, uid, fh, "L2.dta")["version_id"]
    analysis_id = _make_cached_analysis(uid, fh, "correlations entre variables")
    run = projects.add_run(pid, uid, vid, "correlations entre variables")
    out = projects.replay_run(run["run_id"], uid)
    assert out["replayed"] is True and out["from_cache"] is True
    assert out["analysis_id"] == analysis_id
    assert out["result"]["confidence_score"]["score_global"] == 82.5


def test_replay_without_cache_explains_how():
    uid = _user("r2")
    pid = projects.create_project(uid, "Replay2")["project_id"]
    vid = projects.add_dataset_version(
        pid, uid, hashlib.sha256(b"jamais-analyse").hexdigest(), "x.dta"
    )["version_id"]
    run = projects.add_run(pid, uid, vid, "une question")
    out = projects.replay_run(run["run_id"], uid)
    assert out["replayed"] is False
    assert "file_hash" in out and "query" in out


# ── Comparaison de versions ───────────────────────────────────────────────────

def test_compare_versions_delta_confidence_and_tests():
    uid = _user("c1")
    pid = projects.create_project(uid, "Compare")["project_id"]
    ha = hashlib.sha256(b"avec-outliers").hexdigest()
    hb = hashlib.sha256(b"sans-outliers").hexdigest()
    va = projects.add_dataset_version(pid, uid, ha, "avec.dta")["version_id"]
    vb = projects.add_dataset_version(pid, uid, hb, "sans.dta")["version_id"]

    analysis_a = _make_cached_analysis(uid, ha, "q1")
    run_a = projects.add_run(pid, uid, va, "q1")
    projects.attach_analysis(run_a["run_id"], uid, analysis_a, "done")
    # deuxième version : autre résultat (même query, autre hash)
    import uuid as _uuid
    tag_b = _uuid.uuid4().hex[:8]
    file_b = f"f-b-{tag_b}"
    analysis_b = f"a-b-{tag_b}"
    db.save_upload(
        file_id=file_b, user_id=uid,
        data={"path": "y.csv", "filename": "b.dta", "numeric_cols": [],
              "cat_cols": [], "id_cols": [], "n_rows": 280, "n_cols": 121,
              "dataset_type": "x", "uploaded_at": "2024-01-02T00:00:00Z"},
    )
    db.create_analysis(analysis_id=analysis_b, user_id=uid, file_id=file_b,
                       query="q1", created_at="2024-01-02T00:00:00Z", file_hash=hb)
    db.update_analysis(
        analysis_id=analysis_b, status="done",
        result={"confidence_score": {"score_global": 88.0},
                "tests_effectues": [{"name": "Spearman", "p_value": 0.03,
                                     "decision": "significative"}]},
        updated_at="2024-01-02T00:00:00Z", user_id=uid, file_hash=hb,
    )
    run_b = projects.add_run(pid, uid, vb, "q1")
    projects.attach_analysis(run_b["run_id"], uid, analysis_b, "done")

    cmp = projects.compare_versions(pid, uid, va, vb)
    assert cmp["comparable"] is True
    assert cmp["confidence"] == {"a": 82.5, "b": 88.0, "delta": 5.5}
    assert cmp["tests_delta"][0]["test"] == "Spearman"
    assert cmp["tests_delta"][0]["delta_p_value"] == pytest.approx(0.029)


def test_compare_versions_needs_done_runs():
    uid = _user("c2")
    pid = projects.create_project(uid, "Compare2")["project_id"]
    va = projects.add_dataset_version(pid, uid, "h" * 64, "a.dta")["version_id"]
    vb = projects.add_dataset_version(pid, uid, "g" * 64, "b.dta")["version_id"]
    cmp = projects.compare_versions(pid, uid, va, vb)
    assert cmp["comparable"] is False and "reason" in cmp


# ── Endpoints HTTP (auth mockée, isolation stricte) ──────────────────────────

def test_http_lifecycle_and_auth():
    uid = _user("h1")
    _auth_as(uid, "proj-h1", "proj-h1@test.com")
    try:
        r = client.post("/projects", json={"name": "HTTP", "description": "d"})
        assert r.status_code == 200
        pid = r.json()["project_id"]
        assert r.json()["name"] == "HTTP"

        r = client.get("/projects")
        assert r.status_code == 200 and r.json()["count"] == 1

        r = client.post(f"/projects/{pid}/versions",
                        json={"file_hash": "h" * 64, "filename": "L2.dta"})
        assert r.status_code == 200
        vid = r.json()["version_id"]

        r = client.post(f"/projects/{pid}/runs",
                        json={"version_id": vid, "query": "q"})
        assert r.status_code == 200
        rid = r.json()["run_id"]

        r = client.post(f"/projects/runs/{rid}/attach",
                        json={"analysis_id": "x", "status": "done"})
        assert r.status_code == 200 and r.json()["analysis_id"] == "x"

        r = client.get(f"/projects/{pid}")
        assert r.status_code == 200
        body = r.json()
        assert len(body["versions"]) == 1 and len(body["runs"]) == 1

        r = client.delete(f"/projects/{pid}")
        assert r.status_code == 200 and r.json()["deleted"] is True
        assert client.get(f"/projects/{pid}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()


def test_http_requires_auth():
    main.app.dependency_overrides.clear()
    assert client.get("/projects").status_code in (401, 403)


def test_http_404_cross_user():
    owner, other = _user("o1"), _user("o2")
    pid = projects.create_project(owner, "Secret")["project_id"]
    _auth_as(other, "proj-o2", "proj-o2@test.com")
    try:
        assert client.get(f"/projects/{pid}").status_code == 404
        assert client.delete(f"/projects/{pid}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()
