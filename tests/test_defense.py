"""Tests Pilier 4 — Mode Soutenance (app/defense.py).

Vérifie : pack déterministe (deux appels == mêmes octets de valeurs),
questions du jury générées depuis les sections réelles du résultat,
réponses CHIFFRÉES tirées de la persistance (aucun chiffre inventé),
défenses aux points de vigilance, mémo de dernière ligne, emboîtement
brain (result.analysis), 404/400, auth et cross-user.
Aucun LLM, aucun recalcul, aucun réseau. < 5 s.
"""
from __future__ import annotations

import hashlib
import tempfile

import pytest
from fastapi.testclient import TestClient

import db
import main
from app import auth, defense

client = TestClient(main.app)


def _user(n: str) -> str:
    # identité unique par run : users.google_sub et users.email sont UNIQUE
    # et la DB de test persiste entre les runs pytest.
    import uuid as _uuid
    tag = _uuid.uuid4().hex[:8]
    return db.create_or_update_user(
        google_sub=f"df-{n}-{tag}", email=f"df-{n}-{tag}@test.com",
        name=f"DF Test {n}", picture_url="http://example.com/a.png",
    )


def _auth_as(uid: str, google_sub: str, email: str):
    main.app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": uid, "google_sub": google_sub, "email": email,
    }


RESULT_FULL = {
    "status": "ok",
    "filename": "L2_tobit.dta",
    "diagnosis": {"n_rows": 301, "n_cols": 121, "id_cols": ["NUMID"]},
    "normality": {
        "AGE": {"conclusion": "NORMALE"},
        "CA": {"conclusion": "NON NORMALE"},
    },
    "correlation_base": {
        "method": "spearman",
        "pairs": {
            "CA x CATOT": {"r": 0.62, "p_value": 0.0, "p_adjusted": 0.0012},
            "A x B": {"r": 0.11, "p_value": 0.3},
        },
        "multiplicity_correction": {
            "method": "benjamini_hochberg",
            "significant_raw": 1025,
            "significant_adjusted": 1010,
        },
    },
    "inference": {
        "action_executed": "compare_groups",
        "intent_received": {"action": "compare_groups"},
        "validation_issues": [],
        "result": {
            "name": "Mann-Whitney",
            "statistic": 1234.5,
            "p_value": 0.0089,
            "decision": "Différence significative (p<0.05)",
            "effect_size": 0.41,
            "effect_size_ci_lower": 0.18,
            "effect_size_ci_upper": 0.62,
            "power": 0.87,
        },
    },
    "audit_log": [
        {"step": "drop_high_missing"},
        {"step": "winsorize_outliers"},
        {"step": "deduplicate_rows"},
    ],
    "confidence_score": {
        "score_global": 82.4,
        "niveau": "Modéré",
        "points_de_vigilance": [
            "Échantillon de taille moyenne (n=301) — puissance limitée pour les petits effets."
        ],
    },
}


def _make_done(uid: str, result: dict, analysis_id: str) -> str:
    # id unique : la DB de test persiste entre les runs pytest, un id
    # déterministe entrerait en collision UNIQUE d'un run à l'autre.
    import uuid as _uuid
    analysis_id = f"{analysis_id}-{_uuid.uuid4().hex[:8]}"
    content = b"a,b\n1,2\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    file_id = f"df-{_uuid.uuid4().hex[:8]}"
    db.save_upload(file_id=file_id, user_id=uid,
                   data={"path": path, "filename": "etude.dta", "numeric_cols": [],
                         "cat_cols": [], "id_cols": [], "n_rows": 301, "n_cols": 2,
                         "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"})
    db.create_analysis(analysis_id, uid, file_id, "compare CA selon zone",
                       "2024-01-01T00:00:00Z", hashlib.sha256(content).hexdigest())
    db.update_analysis(analysis_id=analysis_id, status="done", result=result,
                       updated_at="2024-01-01T00:00:00Z", user_id=uid,
                       file_hash=hashlib.sha256(content).hexdigest())
    return analysis_id


def test_questions_cite_persisted_numbers_deterministic():
    uid = _user("d1")
    aid = _make_done(uid, RESULT_FULL, "df-a-1")
    pack = defense.build_defense_pack(aid, uid)
    assert pack["n_questions"] >= 5
    assert pack["generateur"].startswith("deterministe")
    qs = {q["question"]: q for q in pack["questions_probables"]}

    # chaque réponse CHIFFRÉE provient de la persistance (aucune invention)
    robuste = next(v for k, v in qs.items() if "robuste" in k)
    assert "0.0089" in robuste["reponse"] and "Mann-Whitney" in robuste["reponse"]
    assert "0.41" in robuste["reponse"] and "[0.18 ; 0.62]" in robuste["reponse"]
    assert "0.87" in robuste["reponse"]
    assert robuste["source"] == "inference.result (p_value, decision, effect_size, IC bootstrap, power)"

    faux_positifs = next(v for k, v in qs.items() if "faux positifs" in k)
    assert "1025" in faux_positifs["reponse"] and "1010" in faux_positifs["reponse"]
    assert "benjamini_hochberg" in faux_positifs["reponse"]

    echantillon = next(v for k, v in qs.items() if "n=301" in k)
    assert "n=301" in echantillon["reponse"] and "82.4" in echantillon["reponse"]

    prep = next(v for k, v in qs.items() if "préparé" in k)
    assert "winsorize_outliers" in prep["reponse"]

    # déterminisme : mêmes valeurs au 2e appel
    pack2 = defense.build_defense_pack(aid, uid)
    assert pack == pack2

    # mémo de dernière ligne
    memo_txt = " | ".join(m["chiffre"] for m in pack["memo_derniere_ligne"])
    assert "p = 0.0089" in memo_txt and "82.4" in memo_txt and "r = 0.62" in memo_txt

    # défenses : une par point de vigilance du Skeptic Engine
    assert len(pack["defenses_points_de_vigilance"]) == 1
    assert "puissance" in pack["defenses_points_de_vigilance"][0]["defense_preparee"]


def test_nested_brain_result_is_unwrapped():
    uid = _user("d2")
    aid = _make_done(uid, {"analysis": RESULT_FULL, "llm_available": True}, "df-a-2")
    pack = defense.build_defense_pack(aid, uid)
    assert pack["fiche_identite"]["n_rows"] == 301
    assert any("robuste" in q["question"] for q in pack["questions_probables"])


def test_minimal_result_still_produces_pack():
    uid = _user("d3")
    aid = _make_done(uid, {"status": "ok", "diagnosis": {"n_rows": 50, "n_cols": 3}}, "df-a-3")
    pack = defense.build_defense_pack(aid, uid)
    assert pack["n_questions"] >= 1  # au moins la question échantillon
    assert all("None" not in q["reponse"] or "n/a" in q["reponse"]
               for q in pack["questions_probables"])


def test_errors_and_auth():
    uid, other = _user("d4"), _user("d4b")
    with pytest.raises(ValueError, match="introuvable"):
        defense.build_defense_pack("aucun-id", uid)
    # analyse créée mais PAS marquée done (pas de update_analysis) -> 400
    import uuid as _uuid
    pending_id = f"df-a-4-{_uuid.uuid4().hex[:8]}"
    pending_file = f"df-{_uuid.uuid4().hex[:8]}"
    content = b"a\n1\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        path = f.name
    db.save_upload(file_id=pending_file, user_id=uid,
                   data={"path": path, "filename": "p.csv", "numeric_cols": [],
                         "cat_cols": [], "id_cols": [], "n_rows": 1, "n_cols": 1,
                         "dataset_type": "x", "uploaded_at": "2024-01-01T00:00:00Z"})
    db.create_analysis(pending_id, uid, pending_file, "q",
                       "2024-01-01T00:00:00Z", hashlib.sha256(content).hexdigest())
    with pytest.raises(ValueError, match="pas terminée"):
        defense.build_defense_pack(pending_id, uid)

    # HTTP : done -> 200, cross-user -> 404, sans auth -> 401/403
    aid = _make_done(uid, RESULT_FULL, "df-a-5")
    _auth_as(uid, "df-d4", "df-d4@test.com")
    try:
        r = client.get(f"/defense/{aid}")
        assert r.status_code == 200 and r.json()["n_questions"] >= 5
    finally:
        main.app.dependency_overrides.clear()
    _auth_as(other, "df-d4b", "df-d4b@test.com")
    try:
        assert client.get(f"/defense/{aid}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()
    assert client.get(f"/defense/{aid}").status_code in (401, 403)
