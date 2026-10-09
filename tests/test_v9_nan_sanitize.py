"""
V9 — NaN/inf dans les résultats d'analyse : fuite JSON invalide + fausse
alerte Skeptic Engine.

Reproduction (W1.1) : un CSV à groupes constants (variance intra-nulle) fait
sortir un test de Welch avec statistic=NaN et p_value=NaN (scipy). Ces NaN
étaient stockés tels quels en base par db.update_analysis (json.dumps accepte
NaN par défaut → littéral `NaN` dans la colonne result, JSON non strict), puis
réhydratés à la lecture (db.get_analysis → json.loads).

ÉCART constaté sur la reproduction HTTP : dans l'environnement installé
(fastapi 0.137.0 / starlette 1.3.1), GET /status répond 200 avec null car la
route est annotée `-> dict[str, Any]` et pydantic coerce NaN→None en mode
JSON (preuve : TypeAdapter(dict[str, Any]).dump_python({"x": nan},
mode="json") == {"x": None}). Une route SANS annotation rend en revanche
bien 500 (json.dumps(allow_nan=False) de starlette lève ValueError). Le
correctif de ce workstream supprime les NaN AVANT tout sérialiseur.

Correctif (W1.2) : sanitize_nonfinite() — déplacé en A1 dans
app/safe_json.py (stdlib seule, numpy par duck typing), importé par db.py —
appliqué à deux points :
  (a) sortie de run_full_analysis (orchestrator) ;
  (b) lecture db.get_analysis / db.get_analysis_internal (lignes héritées).

W1.5 : p_value None → le Skeptic Engine n'émet AUCUNE alerte.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import numpy as np
from fastapi.testclient import TestClient

import db
import main
from app import auth
from app.compute import test_selector as ts
from app.llm.brain import validate_conclusions
from app.orchestrator import run_full_analysis

TEST_USER = "test_v9_nan_user"

# CSV à groupes constants : variance intra-groupe nulle → t de Welch NaN.
CSV_CONST = (
    "groupe,valeur\n"
    "A,5\nA,5\nA,5\nA,5\n"
    "B,5\nB,5\nB,5\nB,5\n"
).encode()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_result_column(analysis_id: str):
    """Colonne SQL brute `result` (jamais passée par json.loads)."""
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT result FROM analyses WHERE analysis_id = ?", (analysis_id,)
        ).fetchone()
    return row["result"] if row is not None else None


def _reject_json_constant(name: str):
    """parse_constant=json.loads : lève si NaN/Infinity/-Infinity lus."""
    raise AssertionError(f"constante JSON non-standard lue en base : {name}")


def _run_constant_groups():
    intent = ts.AnalysisIntent(
        action="compare_groups", target_col="valeur", group_col="groupe",
        raw_query="v9",
    )
    return run_full_analysis(CSV_CONST, "constantes.csv", intent=intent, theme="dark")


# ─── W1.4 : sanitize_nonfinite (unit) ────────────────────────────────────────

def test_sanitize_nonfinite_imbrique_numpy_et_infinis():
    from db import sanitize_nonfinite

    obj = {
        "nan": float("nan"),
        "pinf": float("inf"),
        "ninf": float("-inf"),
        "ok": 1.5,
        "entier": 3,
        "texte": "NaN",
        "booleen": True,
        "rien": None,
        "liste": [float("nan"), 2.0, [float("-inf")]],
        "tuple": (float("inf"), 4),
        "np_nan": np.float64("nan"),
        "np_pinf": np.float32("inf"),
        "np_int": np.int64(7),
        "np_bool": np.bool_(True),
        "profond": {"a": {"b": [{"c": float("nan"), "d": 0.0}]}},
    }
    out = sanitize_nonfinite(obj)

    assert out["nan"] is None
    assert out["pinf"] is None
    assert out["ninf"] is None
    assert out["ok"] == 1.5
    assert out["entier"] == 3
    assert out["texte"] == "NaN"
    assert out["booleen"] is True
    assert out["rien"] is None
    assert out["liste"] == [None, 2.0, [None]]
    assert out["tuple"] == [None, 4]
    assert out["np_nan"] is None
    assert out["np_pinf"] is None
    assert out["np_int"] == 7
    assert out["np_bool"] is True
    assert out["profond"] == {"a": {"b": [{"c": None, "d": 0.0}]}}
    # Sortie complète compatible JSON strict.
    json.dumps(out, allow_nan=False)


# ─── W1.1/W1.4 : sortie de run_full_analysis strictement sérialisable ───────

def test_sortie_run_full_analysis_json_strict():
    result = _run_constant_groups()
    # Ne doit PAS lever ValueError (allow_nan=False).
    json.dumps(result, allow_nan=False)
    inference_result = result["inference"]["result"]
    assert inference_result["p_value"] is None
    assert inference_result["statistic"] is None


# ─── W1.1 : GET /status — jamais de 500, sortie strictement sérialisable ────

def test_status_sur_analyse_avec_nan_ne_renvoie_pas_500():
    db.clear_all()
    result = _run_constant_groups()
    aid = "v9-nan-status-1"
    now = _now()
    db.create_analysis(aid, TEST_USER, "file-v9", "q", now, file_hash="h9")
    assert db.update_analysis(aid, status="done", result=result,
                             updated_at=now, user_id=TEST_USER) is True

    client = TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": TEST_USER}
    try:
        response = client.get(f"/status/{aid}")
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    json.dumps(payload, allow_nan=False)
    result_payload = payload["result"]["inference"]["result"]
    assert result_payload.get("p_value") is None
    assert result_payload.get("statistic") is None


# ─── W1.4 : ligne héritée stockée avec NaN → normalisée à la lecture ────────

def test_ligne_heritee_nan_normalisee_a_la_lecture():
    db.clear_all()
    aid = "v9-nan-legacy-1"
    now = _now()
    # Simule une ligne écrite AVANT le correctif : result contient des NaN
    # réels, stockés par json.dumps comme littéral `NaN`.
    legacy_result = {
        "inference": {
            "action_executed": "compare_groups_2",
            "result": {
                "status": "ok",
                "statistic": float("nan"),
                "p_value": float("nan"),
                "effect_size": float("inf"),
            },
        },
    }
    db.create_analysis(aid, TEST_USER, "file-v9", "q", now, file_hash="h9b")
    assert db.update_analysis(aid, status="done", result=legacy_result,
                             updated_at=now, user_id=TEST_USER) is True

    # (b) lecture DB : la ligne héritée est normalisée.
    row = db.get_analysis(aid, TEST_USER)
    legacy_payload = row["result"]["inference"]["result"]
    assert legacy_payload["p_value"] is None
    assert legacy_payload["statistic"] is None
    assert legacy_payload["effect_size"] is None

    # GET /status sur la ligne héritée : 200 + JSON strict.
    client = TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": TEST_USER}
    try:
        response = client.get(f"/status/{aid}")
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    json.dumps(response.json(), allow_nan=False)


# ─── W1.5 : Skeptic Engine — p_value None → aucune alerte ───────────────────

def test_skeptic_engine_p_value_none_aucune_alerte():
    """Avec p_value None (NaN sanitisé), le Skeptic Engine n'émet AUCUNE
    alerte — y compris si le texte nie globalement tout effet (le cas NaN
    déclenchait une fausse alerte « résultats mixtes » avant correctif)."""
    result = _run_constant_groups()
    interpretation = {
        "llm_available": True,
        "resume_executif": "Il y a aucune différence entre les groupes.",
        "interpretation_principale": {},
        "limites_et_reserves": [],
        "conclusion_generale": "Aucune différence notable entre A et B.",
    }
    out = validate_conclusions(interpretation, result)
    assert "skeptic_engine_alert" not in out

    # Preuve directe p_value None → aucune alerte, même texte à risque.
    out_none = validate_conclusions(
        interpretation,
        {"inference": {"action_executed": "compare_groups_2",
                       "result": {"p_value": None}}},
    )
    assert "skeptic_engine_alert" not in out_none

    interpretation_overclaim = {
        "llm_available": True,
        "resume_executif": "On observe une différence notable entre les groupes.",
        "interpretation_principale": {},
        "limites_et_reserves": [],
        "conclusion_generale": "",
    }
    out2 = validate_conclusions(interpretation_overclaim, result)
    assert "skeptic_engine_alert" not in out2


# ─── A2 : écriture DB — jamais de littéral NaN/Infinity en colonne ─────────

def test_ecriture_update_analysis_sans_litteral_nan_sql():
    """A2 : update_analysis sanitisé + allow_nan=False → la colonne SQL
    brute ne contient AUCUN littéral NaN/Infinity/-Infinity."""
    db.clear_all()
    aid = "v9-a2-update-1"
    now = _now()
    result = {
        "inference": {"result": {
            "statistic": float("nan"),
            "p_value": float("inf"),
            "effect_size": float("-inf"),
            "np_nan": np.float64("nan"),
        }},
        "liste": [float("nan"), 1.5],
    }
    db.create_analysis(aid, TEST_USER, "file-a2", "q", now, file_hash="h-a2")
    assert db.update_analysis(aid, status="done", result=result,
                             updated_at=now, user_id=TEST_USER) is True

    raw = _raw_result_column(aid)
    assert raw is not None
    for litteral in ("NaN", "Infinity", "-Infinity"):
        assert litteral not in raw, (
            f"littéral {litteral!r} présent dans la colonne brute : {raw[:500]}"
        )
    # Relecture en JSON strict : aucune constante non-standard tolérée.
    parsed = json.loads(raw, parse_constant=_reject_json_constant)
    assert parsed["inference"]["result"]["statistic"] is None
    assert parsed["inference"]["result"]["p_value"] is None
    assert parsed["inference"]["result"]["effect_size"] is None
    assert parsed["inference"]["result"]["np_nan"] is None
    assert parsed["liste"] == [None, 1.5]


def test_ecriture_update_analysis_internal_sans_litteral_nan_sql():
    """A2 : même garantie sur update_analysis_internal (worker de confiance)."""
    db.clear_all()
    aid = "v9-a2-internal-1"
    now = _now()
    result = {"p": float("nan"), "q": [float("inf"), {"r": float("-inf")}]}
    db.create_analysis(aid, TEST_USER, "file-a2b", "q", now, file_hash="h-a2b")
    assert db.update_analysis_internal(aid, status="done", result=result,
                                      updated_at=now) is True

    raw = _raw_result_column(aid)
    assert raw is not None
    for litteral in ("NaN", "Infinity", "-Infinity"):
        assert litteral not in raw, (
            f"littéral {litteral!r} présent dans la colonne brute : {raw[:500]}"
        )
    parsed = json.loads(raw, parse_constant=_reject_json_constant)
    assert parsed == {"p": None, "q": [None, {"r": None}]}


def test_allow_nan_false_actif_si_sanitizer_contourne(monkeypatch):
    """Ceinture A2 : si le sanitizer était contourné (bug, repli),
    json.dumps(allow_nan=False) doit LEVER ValueError plutôt que d'écrire
    un littéral NaN — et la ligne ne doit pas être modifiée."""
    db.clear_all()
    aid = "v9-a2-belt-1"
    now = _now()
    db.create_analysis(aid, TEST_USER, "file-a2c", "q", now, file_hash="h-a2c")

    monkeypatch.setattr(db, "sanitize_nonfinite", lambda o: o)
    with pytest.raises(ValueError):
        db.update_analysis(aid, status="done", result={"p": float("nan")},
                           updated_at=now, user_id=TEST_USER)
    with pytest.raises(ValueError):
        db.update_analysis_internal(aid, status="done", result={"p": float("nan")},
                                    updated_at=now)

    # Aucune écriture invalide : la colonne reste NULL.
    assert _raw_result_column(aid) is None


# ─── A1 : db.py ne tire plus numpy — preuve par sous-processus ──────────────

def test_import_db_ne_charge_pas_numpy():
    """Un interpréteur neuf qui importe db ne doit PAS charger numpy dans
    sys.modules (app/safe_json.py = stdlib seule, numpy par duck typing)."""
    proc = subprocess.run(
        [sys.executable, "-c", "import sys, db; print('numpy' in sys.modules)"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() == "False", (
        "l'import de db ne doit pas charger numpy ; "
        f"sortie : {proc.stdout.strip()!r} / stderr : {proc.stderr[-500:]!r}"
    )


def test_import_safe_json_ne_charge_pas_numpy():
    """Même preuve pour app.safe_json seul, importé en tout premier."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, app.safe_json; print('numpy' in sys.modules)"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() == "False", proc.stdout.strip()
