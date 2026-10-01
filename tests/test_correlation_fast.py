"""Test de régression P1-bis : app.compute.correlation_fast.

Verrouille le contrat de non-régression du module vectorisé contre la
sémantique prod (dropna par paire, scipy pearsonr/spearmanr) :
  - régimes SANS NaN : le chemin vectorisé doit être IDENTIQUE (±1e-6)
    à un calcul scipy par paire indépendant ;
  - régime AVEC NaN : le fallback boucle doit être EXACTEMENT identique ;
  - choose_method : réplique la règle prod (toutes normales -> pearson).
Test rapide (aucun LLM, aucun réseau), collecté par pytest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr, spearmanr

from app.compute.correlation_fast import choose_method, compute_correlation_pairs


def _reference_pairs(df: pd.DataFrame, numeric_cols: list[str], method: str) -> dict:
    """Calcul de référence indépendant : boucle scipy par paire (sémantique prod)."""
    pairs = {}
    for i, c1 in enumerate(numeric_cols):
        for j, c2 in enumerate(numeric_cols):
            if i < j:
                s1 = df[c1].dropna()
                s2 = df[c2].dropna()
                common = s1.index.intersection(s2.index)
                if len(common) >= 3:
                    if method == "pearson":
                        r, p = pearsonr(s1[common], s2[common])
                    else:
                        r, p = spearmanr(s1[common], s2[common])
                    pairs[f"{c1} x {c2}"] = (float(r), float(p), len(common))
    return pairs


@pytest.fixture(scope="module")
def df_no_nan() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n, k = 120, 8
    X = rng.normal(size=(n, k))
    X[:, 1] = X[:, 0] * 0.8 + rng.normal(scale=0.2, size=n)
    X[:, 2] = -X[:, 0] * 0.6 + rng.normal(scale=0.3, size=n)
    return pd.DataFrame(X, columns=[f"c{i}" for i in range(k)])


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_identity_no_nan(df_no_nan: pd.DataFrame, method: str) -> None:
    cols = list(df_no_nan.columns)
    out = compute_correlation_pairs(df_no_nan, cols, method)
    assert out["path"] == "vectorized"
    ref = _reference_pairs(df_no_nan, cols, method)
    assert set(out["pairs"]) == set(ref)
    for key, (r_ref, p_ref, n_ref) in ref.items():
        got = out["pairs"][key]
        assert got["n"] == n_ref
        assert abs(got["r"] - round(r_ref, 4)) <= 1e-6
        assert abs(got["p_value"] - round(p_ref, 5)) <= 1e-6
        # Cohérence décision/force dérivée des valeurs
        assert got["decision"] == (
            "Corrélation significative (p<0.05)" if p_ref < 0.05
            else "Pas de corrélation significative"
        )


def test_identity_with_nan_exact_fallback(df_no_nan: pd.DataFrame) -> None:
    df = df_no_nan.copy()
    rng = np.random.default_rng(3)
    for c in df.columns:
        df.loc[df.sample(frac=0.08, random_state=abs(hash(c)) % 1000).index, c] = np.nan
    cols = list(df.columns)
    out = compute_correlation_pairs(df, cols, "pearson")
    assert out["path"] == "loop_fallback"
    ref = _reference_pairs(df, cols, "pearson")
    assert set(out["pairs"]) == set(ref)
    for key, (r_ref, p_ref, n_ref) in ref.items():
        got = out["pairs"][key]
        assert got["n"] == n_ref
        assert got["r"] == round(r_ref, 4)          # exact
        assert got["p_value"] == round(p_ref, 5)    # exact


def test_significant_pairs_matches_p_threshold(df_no_nan: pd.DataFrame) -> None:
    cols = list(df_no_nan.columns)
    out = compute_correlation_pairs(df_no_nan, cols, "pearson")
    expected = sorted(
        (key for key, v in out["pairs"].items() if v["p_value"] < 0.05)
    )
    assert sorted(x[0] for x in out["significant_pairs"]) == expected


def test_choose_method_replicates_prod_rule() -> None:
    normality = {"a": {"conclusion": "NORMALE"}, "b": {"conclusion": "NORMALE"}}
    assert choose_method(["a", "b"], normality) == "pearson"
    normality["b"] = {"conclusion": "NON NORMALE"}
    assert choose_method(["a", "b"], normality) == "spearman"


def test_too_few_numeric_cols_returns_error() -> None:
    out = compute_correlation_pairs(pd.DataFrame({"a": [1.0, 2.0, 3.0]}), ["a"], "pearson")
    assert "error" in out
