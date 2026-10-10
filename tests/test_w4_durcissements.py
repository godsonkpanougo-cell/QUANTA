"""SESSION D (W4) — Trois durcissements, tests rouges d'abord.

1. `/health` expose les 7 premiers caractères de `RENDER_GIT_COMMIT` (env
   Render) : permet au smoke test de vérifier QUEL commit est déployé (G15).
2. Sessions : `timespec="microseconds"` — `isoformat()` omet les microsecondes
   quand elles valent 0 (format ISO VARIABLE), ce qui casse l'ordre
   lexicographique des comparaisons de chaînes `expires_at < now`.
3. PDF worker : `capture_output=True` accumulait TOUTE la sortie subprocess en
   mémoire (le worker d'analyse a déjà le correctif V6 avec fichiers
   temporaires bornés — main.py:543-560).

Exécutable aussi en script CLI : python -m tests.test_w4_durcissements
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import db
import main
from tests._api_test import get_client, reset_api_state


# ─── 1. /health + RENDER_GIT_COMMIT ─────────────────────────────────────────

def test_health_sans_env_commit_absent(monkeypatch):
    """Sans RENDER_GIT_COMMIT (dev local), le comportement historique est
    conservé : pas de clé commit, zéro crash."""
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    reset_api_state()
    r = get_client().get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok" and data["service"] == "quanta-api"
    assert "commit" not in data


def test_health_expose_7_premiers_caracteres_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890deadbeef")
    reset_api_state()
    r = get_client().get("/health")
    assert r.status_code == 200
    assert r.json().get("commit") == "abcdef1", (
        f"attendu 'abcdef1' (7 premiers caractères), obtenu {r.json().get('commit')!r}"
    )


def test_health_commit_blanc_traite_comme_absent(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "   ")
    reset_api_state()
    r = get_client().get("/health")
    assert r.status_code == 200
    assert "commit" not in r.json()


# ─── 2. Sessions : timespec microsecondes ───────────────────────────────────

def test_helper_session_timestamp_microsecondes_toujours():
    """Le helper garantit un format ISO fixe : microsecondes TOUJOURS
    présentes, y compris à 0 — condition de l'ordre lexicographique."""
    naive_zero = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc).replace(
        tzinfo=None
    )
    ts = db._session_timestamp(naive_zero)
    assert ts == "2026-01-01T00:00:00.000000Z", (
        f"microsecondes omises ou format variable : {ts!r}"
    )


def test_helper_session_timestamp_microsecondes_renseignees():
    naive = datetime(2026, 6, 15, 12, 30, 45, 123456, tzinfo=timezone.utc).replace(
        tzinfo=None
    )
    assert db._session_timestamp(naive) == "2026-06-15T12:30:45.123456Z"


def test_create_session_format_microsecondes():
    db.clear_all()
    token = db.create_session("user-w4", ttl_hours=1)
    row = db.get_session(token)
    for champ in ("created_at", "expires_at"):
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$", row[champ]), (
            f"{champ} hors format ISO microsecondes fixe : {row[champ]!r}"
        )
    db.clear_all()


def test_ordre_lexicographique_egal_chronologique():
    """Le cœur du bug : à microsecondes omises, 'Z' (0x5A) > '.' (0x4E) casse
    la comparaison de chaînes dans la même seconde."""
    t1 = db._session_timestamp(datetime(2026, 1, 1, 0, 0, 0, 0).replace(tzinfo=None))
    t2 = db._session_timestamp(datetime(2026, 1, 1, 0, 0, 0, 500000).replace(tzinfo=None))
    assert (t1 < t2) is True, (
        "ordre lexicographique != ordre chronologique : format variable"
    )


# ─── 3. PDF worker : sortie bornée (fichiers temporaires, façon V6) ─────────

def _seed_analyse_done(user_id: str, analysis_id: str, file_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.save_upload(file_id, user_id, {
        "path": "data/samples/clean.csv", "filename": "clean.csv",
        "numeric_cols": ["col1"], "cat_cols": [], "id_cols": [],
        "n_rows": 10, "n_cols": 1, "dataset_type": "tabular",
        "uploaded_at": now,
    })
    db.create_analysis(analysis_id, user_id, file_id, "q", now, file_hash="h-w4")
    assert db.update_analysis(
        analysis_id, status="done",
        result={"confidence": {"score_global": 0.8}, "tests": [],
                "interpretations": []},
        updated_at=now, user_id=user_id, file_hash="h-w4",
    ) is True


def test_pdf_worker_sortie_par_fichiers_temporaires():
    """Le subprocess PDF worker ne doit PLUS être appelé avec
    capture_output=True (accumulation mémoire bornée par V6 côté analyse)."""
    db.clear_all()
    user_id = db.create_or_update_user(
        "google-w4-pdf", "w4-pdf@example.com", "W4", "https://example.com/a.jpg",
    )
    _seed_analyse_done(user_id, "w4-pdf-1", "w4-pdf-file-1")

    def fake_run(cmd, **kwargs):
        # Écrire un PDF minimal à la place du worker, comme il le ferait.
        # cmd = [python, app/pdf_worker.py, input_path, pdf_path, theme]
        pdf_path = cmd[3]
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 fake")
        return MagicMock(returncode=0, stdout="", stderr="")

    # Le cache disque PDF (A3) ferait un HIT entre deux exécutions de la
    # suite -> forcer la régénération ET nettoyer le fichier laissé.
    _upload_dir = os.environ.get("QUANTA_UPLOAD_DIR", "/data/uploads")
    _cached_pdf = os.path.join(_upload_dir, "report_w4-pdf-1_dark.pdf")
    with patch("main.subprocess.run", side_effect=fake_run) as mock_run:
        main.app.dependency_overrides[main.auth.get_current_user] = (
            lambda: {"user_id": user_id}
        )
        try:
            r = get_client().get("/report/w4-pdf-1?force=true")
        finally:
            main.app.dependency_overrides.clear()
            db.clear_all()
            try:
                os.unlink(_cached_pdf)
            except OSError:
                pass

    assert r.status_code == 200, r.text
    kwargs = mock_run.call_args.kwargs
    assert "capture_output" not in kwargs, (
        "capture_output=True accumule toute la sortie worker en mémoire"
    )
    assert "stdout" in kwargs and kwargs["stdout"] is not None, (
        "la sortie doit être redirigée vers un fichier temporaire borné (V6)"
    )
    assert "stderr" in kwargs and kwargs["stderr"] is not None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
