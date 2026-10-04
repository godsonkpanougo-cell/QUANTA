"""Tests P0 (pilier crédibilité) : corrections de multiplicité.

Verrouille les implémentations de app/compute/multiplicity.py contre
l'ORACLE statsmodels.stats.multitest.multipletests :
  - holm_bonferroni == multipletests(method="holm") ;
  - benjamini_hochberg == multipletests(method="fdr_bh") ;
  - deux cas révélateurs qui échouaient AVANT correction de la contrainte
    de monotonie (Holm sous-corrigé laissait passer des faux positifs,
    BH sur-corrigé éliminait des découvertes vraies) ;
  - 200 familles aléatoires seedées (n de 1 à 120) ;
  - apply_fdr_correction_to_pairs : p_value brute PRÉSERVÉE, ajout de
    p_adjusted / significant_adjusted, NaN traités comme p=1.0.
Aucun réseau, aucun LLM : < 10 s.
"""
from __future__ import annotations

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from app.compute.multiplicity import (
    apply_fdr_correction_to_pairs,
    benjamini_hochberg,
    count_significant_pairs,
    holm_bonferroni,
)


def test_holm_matches_statsmodels_revealing_case():
    # p=[0.04, 0.045] : mult = [0.08, 0.045] décroissant -> le vrai Holm
    # donne [0.08, 0.08] (cumul MAX) ; l'ancien code donnait [0.045, 0.045]
    # et laissait passer p=0.04 à 0.045 < 0.05 (faux positif).
    p = np.array([0.04, 0.045])
    expected = multipletests(p, method="holm")[1]
    out = holm_bonferroni(p)
    assert np.allclose(out, expected)
    assert out[0] == pytest.approx(0.08)


def test_bh_matches_statsmodels_revealing_case():
    # p=[0.01, 0.015] : mult = [0.02, 0.015] décroissant -> le vrai BH donne
    # [0.015, 0.015] (cumul MIN depuis la fin) ; l'ancien code donnait
    # [0.02, 0.02] et éliminait une découverte vraie.
    p = np.array([0.01, 0.015])
    expected = multipletests(p, method="fdr_bh")[1]
    out = benjamini_hochberg(p)
    assert np.allclose(out, expected)
    assert out[0] == pytest.approx(0.015)


def test_holm_and_bh_match_statsmodels_random_families():
    rng = np.random.default_rng(42)
    for _ in range(200):
        n = int(rng.integers(1, 121))
        p = np.round(rng.random(n), 6)
        assert np.allclose(
            holm_bonferroni(p), multipletests(p, method="holm")[1], atol=1e-12
        )
        assert np.allclose(
            benjamini_hochberg(p), multipletests(p, method="fdr_bh")[1], atol=1e-12
        )


def test_edge_cases():
    assert holm_bonferroni([]).size == 0
    assert benjamini_hochberg([]).size == 0
    one = np.array([0.3])
    assert holm_bonferroni(one)[0] == pytest.approx(0.3)
    assert benjamini_hochberg(one)[0] == pytest.approx(0.3)
    p = np.array([0.001, 0.9, 0.2])
    for out in (holm_bonferroni(p), benjamini_hochberg(p)):
        assert np.all(out <= 1.0) and np.all(out >= 0.0)
        assert out.shape == p.shape


def test_apply_fdr_preserves_raw_and_matches_oracle():
    pairs = {
        "a x b": {"r": 0.9, "p_value": 0.001,
                  "decision": "Corrélation significative (p<0.05)"},
        "c x d": {"r": 0.1, "p_value": 0.6,
                  "decision": "Pas de corrélation significative"},
        "e x f": {"r": 0.5, "p_value": 0.02,
                  "decision": "Corrélation significative (p<0.05)"},
        "g x h": {"r": 0.2, "p_value": 0.2,
                  "decision": "Pas de corrélation significative"},
    }
    out = apply_fdr_correction_to_pairs(pairs, method="holm")
    # brut et decision PRÉSERVÉS (non-régression payload)
    assert out["a x b"]["p_value"] == 0.001
    assert out["c x d"]["decision"] == "Pas de corrélation significative"
    # champs ajoutés partout
    for k in out:
        assert "p_adjusted" in out[k] and "significant_adjusted" in out[k]
    # cohérence avec l'oracle statsmodels (ordre des clés conservé)
    p = [0.001, 0.6, 0.02, 0.2]
    expected = multipletests(p, method="holm")[1]
    got = [out[k]["p_adjusted"] for k in ["a x b", "c x d", "e x f", "g x h"]]
    assert np.allclose(got, expected, atol=1e-5)
    counts = count_significant_pairs(out)
    assert counts["significant_raw"] == 2
    assert counts["significant_adjusted"] == int((expected < 0.05).sum())


def test_apply_fdr_nan_treated_as_max_p():
    pairs = {"a x b": {"p_value": 0.01}, "c x d": {"p_value": float("nan")}}
    out = apply_fdr_correction_to_pairs(pairs, method="bh")
    expected = multipletests([0.01, 1.0], method="fdr_bh")[1]
    assert out["a x b"]["p_adjusted"] == pytest.approx(expected[0], abs=1e-5)
    assert out["c x d"]["p_adjusted"] == pytest.approx(expected[1], abs=1e-5)


def test_apply_fdr_empty_family_is_noop():
    assert apply_fdr_correction_to_pairs({}) == {}
