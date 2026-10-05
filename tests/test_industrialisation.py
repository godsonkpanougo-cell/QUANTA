"""Tests durcissement (A4) : contrat Pydantic + HC3 + bug theme="both".

Verrouille :
  - le contrat AnalysisPayload contre un VRAI résultat de pipeline
    (thème both — celui qui cachait le bug de normalité vide) ;
  - le bug theme="both" : la normalité doit être peuplée dans les DEUX
    branches de run_base_compute_pipeline (causait la bascule systématique
    en non-paramétrique en prod, corrigé le 05/10/2026) ;
  - l'OLS robuste : détection d'hétéroscédasticité -> HC3 avec coefficients
    IDENTIQUES et écarts-types ajustés ; homoscédasticité -> nonrobust ;
  - l'orchestrateur de bout en bout : données normales par groupe ->
    Student/Welch (et plus Mann-Whitney systématique).
Aucun réseau, aucun LLM. < 60 s.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, ".")

from app.compute import compute
from app.compute.test_selector import AnalysisIntent
from app.schemas import AnalysisPayload
from tests._print_orchestrator import run_orchestrator_sample


def _hetero_df(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(10, 3, n)
    y = 2 * x + rng.normal(0, 0.5 + 0.8 * x, n)
    return pd.DataFrame({"y": y, "x": x})


def _homo_df(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(10, 3, n)
    y = 2 * x + rng.normal(0, 1.0, n)  # variance constante
    return pd.DataFrame({"y": y, "x": x})


def test_pipeline_theme_both_has_populated_normality():
    raw = open("data/samples/ts_2groups_normal.csv", "rb").read()
    p = compute.run_base_compute_pipeline(raw, "ts_2groups_normal.csv", theme="both")
    assert "score" in p["normality"], (
        "BUG theme=both : la normalité était vidée par le double .get, "
        "le selector basculait systématiquement en non-paramétrique"
    )
    assert p["normality"]["score"]["conclusion"] == "NORMALE"


def test_orchestrator_chooses_parametric_on_normal_groups():
    result = run_orchestrator_sample(
        "ts_2groups_normal.csv",
        AnalysisIntent(action="compare_groups", target_col="score",
                       group_col="traitement", raw_query="q"),
    )
    assert result["status"] == "ok"
    test_name = result["inference"]["result"].get("test", "")
    assert "Student" in test_name or "Welch" in test_name


def test_analysis_payload_contract_on_real_pipeline():
    # Le contrat AnalysisPayload décrit la réponse de l'ORCHESTRATEUR
    # (status/inference/confidence_score) — pas le pipeline de base.
    result = run_orchestrator_sample(
        "ts_2groups_normal.csv",
        AnalysisIntent(action="compare_groups", target_col="score",
                       group_col="traitement", raw_query="q"),
    )
    payload = AnalysisPayload.model_validate(result)
    assert payload.status == "ok"
    assert payload.diagnosis["n_rows"] == 120
    assert payload.normality["score"]["conclusion"] == "NORMALE"
    assert payload.confidence_score.score_global > 0


def test_hc3_selected_when_heteroscedastic():
    df = _hetero_df()
    r = compute.ols_regression(df, ["x", "y"], target_col="y")
    assert r["status"] == "ok"
    assert r["heteroscedasticity_detected"] is True
    assert r["cov_type_used"] == "HC3"
    cb, cr = r["coefficients"]["x"], r["coefficients_robust"]["x"]
    # estimations ponctuelles IDENTIQUES, seuls les SE changent
    assert cb["coefficient"] == cr["coefficient"]
    assert cb["std_err"] != cr["std_err_robust"]
    assert cb["p_value"] == cb["p_value"]  # sanity: classique présent
    assert cr["p_value_robust"] >= 0.0


def test_hc3_not_selected_when_homoscedastic():
    df = _homo_df()
    r = compute.ols_regression(df, ["x", "y"], target_col="y")
    assert r["status"] == "ok"
    assert r["heteroscedasticity_detected"] is False
    assert r["cov_type_used"] == "nonrobust"
    assert r["coefficients_robust"] == {}
