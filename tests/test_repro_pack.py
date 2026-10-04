"""Tests Pilier 3 — Repro Pack (app/repro_pack.py).

Vérifie : ZIP valide, README d'audit (sha256, versions, seeds, mentions),
resultats.json IDENTIQUE à la sortie persistée (aucune réécriture),
données originales incluses à l'octet près, scripts R/Stata embarqués
s'ils sont présents, PDF inclus s'il existe, 404/400 et auth.
Aucun recalcul statistique, aucun réseau. < 5 s.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile

import pytest
from fastapi.testclient import TestClient

import db
import main
from app import auth, repro_pack

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path):
    """QUANTA_UPLOAD_DIR isolé (PDF cache) — n'affecte pas les autres tests."""
    old = os.environ.get("QUANTA_UPLOAD_DIR")
    os.environ["QUANTA_UPLOAD_DIR"] = str(tmp_path)
    yield tmp_path
    if old is None:
        os.environ.pop("QUANTA_UPLOAD_DIR", None)
    else:
        os.environ["QUANTA_UPLOAD_DIR"] = old


def _user(n: str) -> str:
    return db.create_or_update_user(
        google_sub=f"rp-{n}", email=f"rp-{n}@test.com",
        name=f"RP Test {n}", picture_url="http://example.com/a.png",
    )


def _auth_as(uid: str, google_sub: str, email: str):
    main.app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": uid, "google_sub": google_sub, "email": email,
    }


def _make_done_analysis(uid: str, result: dict | None = None) -> tuple[str, bytes, str]:
    """Upload réel sur disque + analyse done persistée. Retourne (id, bytes, nom)."""
    content = b"x,y\n1,2\n2,4\n3,6\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    file_id = f"rp-{hashlib.sha256(path.encode()).hexdigest()[:8]}"
    db.save_upload(
        file_id=file_id, user_id=uid,
        data={"path": path, "filename": "mon_etude.csv", "numeric_cols": ["x", "y"],
              "cat_cols": [], "id_cols": [], "n_rows": 3, "n_cols": 2,
              "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"},
    )
    file_hash = hashlib.sha256(content).hexdigest()
    analysis_id = f"rp-a-{hashlib.sha256(path.encode()).hexdigest()[:10]}"
    db.create_analysis(analysis_id, uid, file_id, "correlation x y",
                       "2024-01-01T00:00:00Z", file_hash)
    db.update_analysis(
        analysis_id=analysis_id, status="done",
        result=result or {"confidence_score": {"score_global": 80.0},
                          "tests_effectues": [{"name": "Spearman", "p_value": 0.01}],
                          "r_script": "# R code\nsummary(lm(y ~ x))",
                          "stata_script": "* Stata code\nreg y x"},
        updated_at="2024-01-01T00:00:00Z", user_id=uid, file_hash=file_hash,
    )
    return analysis_id, content, path


def test_pack_contains_audit_readme_and_exact_results():
    uid = _user("full")
    analysis_id, content, _ = _make_done_analysis(uid)
    data, fname = repro_pack.build_repro_pack(analysis_id, uid)
    assert fname.startswith("repro_pack_") and fname.endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    assert "README.txt" in names and "resultats.json" in names
    assert "donnees/mon_etude.csv" in names
    assert "script_reproduction.R" in names and "script_reproduction.do" in names

    # README : sha256 du fichier source, versions, seeds, mentions de contenu
    readme = zf.read("README.txt").decode()
    assert hashlib.sha256(content).hexdigest() in readme
    assert "mon_etude.csv" in readme
    assert "numpy" in readme and "scipy" in readme  # versions auditées
    assert "random_state=42" in readme
    assert "upload original inclus" in readme

    # resultats.json : IDENTIQUE à la sortie persistée (aucune réécriture)
    stored = db.get_analysis(analysis_id, uid)["result"]
    packed = json.loads(zf.read("resultats.json").decode())
    assert packed == stored

    # données : à l'octet près
    assert zf.read("donnees/mon_etude.csv") == content


def test_pack_includes_pdf_when_present(isolated_env):
    uid = _user("pdf")
    analysis_id, _, _ = _make_done_analysis(uid)
    pdf_path = os.path.join(str(isolated_env), f"report_{analysis_id}_dark.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 fake")
    data, _ = repro_pack.build_repro_pack(analysis_id, uid, theme="dark")
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert "rapport_dark.pdf" in zf.namelist()
    assert zf.read("rapport_dark.pdf") == b"%PDF-1.4 fake"
    readme = zf.read("README.txt").decode()
    assert "inclus" in readme


def test_pack_without_pdf_mentions_report_endpoint(isolated_env):
    uid = _user("nopdf")
    analysis_id, _, _ = _make_done_analysis(uid)
    data, _ = repro_pack.build_repro_pack(analysis_id, uid)
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert not any(n.endswith(".pdf") for n in zf.namelist())
    assert "GET /report/" in zf.read("README.txt").decode()


def test_pack_errors_missing_and_not_done():
    uid = _user("err")
    with pytest.raises(ValueError, match="introuvable"):
        repro_pack.build_repro_pack("aucun-tel-id", uid)
    # analyse non terminée
    content = b"a\n1\n2\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    file_id = "rp-pending"
    db.save_upload(file_id=file_id, user_id=uid,
                   data={"path": path, "filename": "p.csv", "numeric_cols": [],
                         "cat_cols": [], "id_cols": [], "n_rows": 2, "n_cols": 1,
                         "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"})
    db.create_analysis("rp-a-pending", uid, file_id, "q",
                       "2024-01-01T00:00:00Z", hashlib.sha256(content).hexdigest())
    with pytest.raises(ValueError, match="pas terminée"):
        repro_pack.build_repro_pack("rp-a-pending", uid)


def test_http_download_auth_and_cross_user():
    uid, other = _user("h1"), _user("h2")
    analysis_id, _, _ = _make_done_analysis(uid)
    _auth_as(uid, "rp-h1", "rp-h1@test.com")
    try:
        r = client.get(f"/repro_pack/{analysis_id}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "attachment" in r.headers["content-disposition"]
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "README.txt" in zf.namelist()
    finally:
        main.app.dependency_overrides.clear()

    # cross-user : 404
    _auth_as(other, "rp-h2", "rp-h2@test.com")
    try:
        assert client.get(f"/repro_pack/{analysis_id}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()

    # sans auth : 401/403
    assert client.get(f"/repro_pack/{analysis_id}").status_code in (401, 403)


def test_http_400_when_not_done():
    uid = _user("h3")
    content = b"a\n1\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    db.save_upload(file_id="rp-h3-f", user_id=uid,
                   data={"path": path, "filename": "h3.csv", "numeric_cols": [],
                         "cat_cols": [], "id_cols": [], "n_rows": 1, "n_cols": 1,
                         "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"})
    db.create_analysis("rp-a-h3", uid, "rp-h3-f", "q",
                       "2024-01-01T00:00:00Z", hashlib.sha256(content).hexdigest())
    _auth_as(uid, "rp-h3", "rp-h3@test.com")
    try:
        assert client.get("/repro_pack/rp-a-h3").status_code == 400
    finally:
        main.app.dependency_overrides.clear()
