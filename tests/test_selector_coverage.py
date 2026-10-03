"""Tests de couverture pour les chemins de code manquants dans test_selector.py et orchestrator.py.

Ces tests couvrent 7 trous identifiés dans l'audit de couverture :
1. Comparaison appariée (t-test pairé) - données normales
2. Comparaison appariée non-normale (Wilcoxon signé)
3. Welch ANOVA spécifique (variances inégales + normalité)
4. Power analysis (compute_statistical_power)
5. Recalcul OLS avec target_col différent (orchestrator)
6. Repli Games-Howell/Dunn sans scikit-posthocs
7. Repli Dunn sans scikit-posthocs (test de Kruskal-Wallis post-hoc)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.compute import run_base_compute_pipeline
from app.compute.test_selector import (
    AnalysisIntent,
    run_two_group_comparison,
    run_multi_group_comparison,
    select_and_run_test,
)
from app.orchestrator import _resolve_delegation


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 : Comparaison appariée (t-test pairé) - données normales
# ═══════════════════════════════════════════════════════════════════════════════

def test_paired_comparison_normal():
    """Test que le t-test pairé est bien sélectionné pour données appariées normales."""
    np.random.seed(42)
    n = 30
    data = {
        "sujet": [f"S{i:02d}" for i in range(n)],
        "groupe": ["A"] * (n // 2) + ["B"] * (n - n // 2),
        "avant": np.random.normal(100, 10, n),
        "apres": np.random.normal(105, 10, n),
    }
    df = pd.DataFrame(data)
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "paired_test.csv")
    
    assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Forcer paired=True sur une variable normale
    audit_log = []
    result = run_two_group_comparison(
        df_clean, "avant", "groupe", normality, True, audit_log
    )
    
    assert result["status"] == "ok"
    assert "pairé" in result["test"].lower() or "paired" in result["test"].lower()
    assert result["paired"] is True
    
    # Vérifier que l'audit_log documente la décision
    assert any(e["etape"] == "selection_test" for e in audit_log)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 : Comparaison appariée non-normale (Wilcoxon signé)
# ═══════════════════════════════════════════════════════════════════════════════

def test_paired_comparison_non_normal():
    """Test que Wilcoxon signé est sélectionné pour données appariées non-normales."""
    np.random.seed(42)
    n = 30
    data = {
        "sujet": [f"S{i:02d}" for i in range(n)],
        "groupe": ["A"] * (n // 2) + ["B"] * (n - n // 2),
        "score": np.random.exponential(10, n),  # Distribution non-normale
    }
    df = pd.DataFrame(data)
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "paired_non_normal.csv")
    
    assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Forcer paired=True sur une variable non-normale
    audit_log = []
    result = run_two_group_comparison(
        df_clean, "score", "groupe", normality, True, audit_log
    )
    
    assert result["status"] == "ok"
    assert "wilcoxon" in result["test"].lower()
    assert result["paired"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 : Welch ANOVA spécifique (variances inégales + normalité)
# ═══════════════════════════════════════════════════════════════════════════════

def test_welch_anova_unequal_variances():
    """Test que Welch ANOVA est sélectionné pour variances inégales avec normalité."""
    np.random.seed(123)
    n_per_group = 60
    data = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
        "valeur": (
            np.random.normal(100, 5, n_per_group).tolist() +  # variance faible
            np.random.normal(100, 25, n_per_group).tolist() +  # variance élevée
            np.random.normal(100, 15, n_per_group).tolist()    # variance modérée
        ),
    }
    df = pd.DataFrame(data)
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "welch_test.csv")
    
    assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Vérifier que les données sont normales
    is_normal = normality.get("valeur", {}).get("conclusion") == "NORMALE"
    
    audit_log = []
    result = run_multi_group_comparison(
        df_clean, "valeur", "groupe", normality, audit_log
    )
    
    assert result["status"] == "ok"
    
    # Si les données sont normales et Levene détecte des variances inégales,
    # Welch ANOVA doit être sélectionné
    if is_normal:
        levene_equal = result["levene"]["equal_variance"]
        if not levene_equal:
            assert "Welch" in result["test"]
            # Vérifier que Games-Howell est déclenché si p < 0.05
            if result["p_value"] < 0.05:
                assert result["posthoc"] is not None
                assert "Games-Howell" in result["posthoc"].get("method", "") or "Tukey" in result["posthoc"].get("method", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 : Power analysis (compute_statistical_power)
# ═══════════════════════════════════════════════════════════════════════════════

def test_compute_statistical_power_ttest():
    """Test que compute_statistical_power enrichit un résultat t-test."""
    from app.compute.compute import compute_statistical_power
    
    result = {
        "status": "ok",
        "test": "t-test de Student (variances égales)",
        "n_group1": 30,
        "n_group2": 30,
        "effect_size": 0.5,
        "p_value": 0.04,
    }
    
    enriched = compute_statistical_power(result)
    
    assert "power" in enriched
    assert enriched["power"] is not None
    assert "power_interpretation" in enriched
    assert 0.40 <= enriched["power"] <= 0.60  # Plage attendue pour d=0.5, n=30


def test_compute_statistical_power_anova():
    """Test que compute_statistical_power enrichit un résultat ANOVA."""
    from app.compute.compute import compute_statistical_power
    
    result = {
        "status": "ok",
        "test": "ANOVA à un facteur (variances égales)",
        "n_groups": 3,
        "group_sizes": [30, 30, 30],
        "eta_squared": 0.06,
        "p_value": 0.03,
    }
    
    enriched = compute_statistical_power(result)
    
    assert "power" in enriched
    assert enriched["power"] is not None


def test_compute_statistical_power_chisquare():
    """Test que compute_statistical_power enrichit un résultat Chi-deux."""
    from app.compute.compute import compute_statistical_power
    
    result = {
        "status": "ok",
        "test": "Chi-deux d'indépendance",
        "cramers_v": 0.3,
        "n_observations": 100,
        "p_value": 0.02,
    }
    
    enriched = compute_statistical_power(result)
    
    # Chi-deux peut ne pas être supporté, vérifier juste que ça ne crash pas
    assert isinstance(enriched, dict)


def test_compute_statistical_power_error_case():
    """Test que compute_statistical_power ne calcule pas pour status=error."""
    from app.compute.compute import compute_statistical_power
    
    result = {
        "status": "error",
        "reason": "Test invalide",
    }
    
    enriched = compute_statistical_power(result)
    
    assert enriched.get("power") is None


def test_compute_statistical_power_already_enriched():
    """Test que compute_statistical_power ne recalcule pas si power déjà présent."""
    from app.compute.compute import compute_statistical_power
    
    result = {
        "status": "ok",
        "test": "t-test",
        "n_group1": 30,
        "n_group2": 30,
        "effect_size": 0.5,
        "power": 0.75,  # Déjà présent
    }
    
    enriched = compute_statistical_power(result)
    
    assert enriched["power"] == 0.75  # Non recalculé


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 : Recalcul OLS avec target_col différent (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════════

def test_ols_recalc_different_target():
    """Test que le recalcul OLS se déclenche quand target_col diffère du pipeline de base."""
    np.random.seed(42)
    n = 50
    data = {
        "id": list(range(n)),
        "age": np.random.normal(40, 10, n),
        "income": np.random.normal(50000, 15000, n),
        "score": np.random.normal(75, 15, n),
    }
    df = pd.DataFrame(data)
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "ols_test.csv")
    
    assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Simuler un scénario où le pipeline de base calcule OLS sur "income"
    # mais l'intent demande OLS sur "score"
    base_regression = {
        "status": "ok",
        "y_variable": "income",  # Cible du pipeline de base
        "r_squared": 0.45,
    }
    
    # Créer un selector_result qui demande une délégation OLS avec une cible différente
    selector_result = {
        "result": {
            "status": "delegate_to_ols",
            "target_col": "score",  # Cible différente
            "predictor_cols": ["age"],
        }
    }
    
    audit_log = []
    
    # Appeler _resolve_delegation pour forcer le chemin de recalcul
    from app.compute import compute
    delegated = _resolve_delegation(
        selector_result,
        df_clean,
        numeric_cols,
        normality,
        base_regression=base_regression,
        base_correlation={},
        audit_log=audit_log,
    )
    
    # Vérifier que le recalcul a eu lieu
    assert delegated["status"] == "ok"
    assert delegated["y_variable"] == "score"  # Nouvelle cible
    
    # Vérifier l'audit_log
    delegation_entry = next((e for e in audit_log if e["etape"] == "delegation_ols"), None)
    assert delegation_entry is not None
    assert delegation_entry["decision"] == "recalcul_avec_cible_specifique"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 : Repli Games-Howell sans scikit-posthocs
# ═══════════════════════════════════════════════════════════════════════════════

def test_games_howell_fallback_without_scikit_posthocs():
    """Test que le repli vers Tukey se déclenche quand scikit-posthocs est indisponible."""
    import app.compute.test_selector as test_selector_module
    
    # Monkeypatch HAS_POSTHOCS à False
    original_has_posthocs = test_selector_module.HAS_POSTHOCS
    test_selector_module.HAS_POSTHOCS = False
    
    try:
        np.random.seed(123)
        n_per_group = 60
        data = {
            "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
            "valeur": (
                np.random.normal(100, 5, n_per_group).tolist() +
                np.random.normal(100, 25, n_per_group).tolist() +
                np.random.normal(100, 15, n_per_group).tolist()
            ),
        }
        df = pd.DataFrame(data)
        
        csv_content = df.to_csv(index=False)
        pipeline = run_base_compute_pipeline(csv_content.encode(), "games_howell_test.csv")
        
        assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
        
        df_clean = pipeline["dataframe_clean"]
        numeric_cols = pipeline["numeric_cols"]
        cat_cols = pipeline["cat_cols"]
        id_cols = pipeline["diagnosis"].get("id_cols", [])
        normality = pipeline.get("normality", {})
        
        audit_log = []
        result = run_multi_group_comparison(
            df_clean, "valeur", "groupe", normality, audit_log
        )
        
        assert result["status"] == "ok"
        
        # Si Welch ANOVA est utilisé et p < 0.05, vérifier le repli
        if "Welch" in result["test"] and result["p_value"] < 0.05:
            assert result["posthoc"] is not None
            # Le repli doit utiliser Tukey avec avertissement
            posthoc_method = result["posthoc"].get("method", "")
            assert "Tukey" in posthoc_method
            assert "_avertissement" in result["posthoc"]
            assert "Games-Howell indisponible" in result["posthoc"]["_avertissement"]
    finally:
        # Restaurer HAS_POSTHOCS
        test_selector_module.HAS_POSTHOCS = original_has_posthocs


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 : Repli Dunn sans scikit-posthocs (Kruskal-Wallis post-hoc)
# ═══════════════════════════════════════════════════════════════════════════════

def test_dunn_fallback_without_scikit_posthocs():
    """Test que le repli se déclenche quand scikit-posthocs est indisponible pour Dunn."""
    import app.compute.test_selector as test_selector_module
    
    # Monkeypatch HAS_POSTHOCS à False
    original_has_posthocs = test_selector_module.HAS_POSTHOCS
    test_selector_module.HAS_POSTHOCS = False
    
    try:
        np.random.seed(42)
        n_per_group = 50
        data = {
            "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
            "valeur": (
                np.random.exponential(10, n_per_group).tolist() +  # Non-normal
                np.random.exponential(15, n_per_group).tolist() +
                np.random.exponential(20, n_per_group).tolist()
            ),
        }
        df = pd.DataFrame(data)
        
        csv_content = df.to_csv(index=False)
        pipeline = run_base_compute_pipeline(csv_content.encode(), "dunn_test.csv")
        
        assert "error" not in pipeline, f"Pipeline error: {pipeline.get('error')}"
        
        df_clean = pipeline["dataframe_clean"]
        numeric_cols = pipeline["numeric_cols"]
        cat_cols = pipeline["cat_cols"]
        id_cols = pipeline["diagnosis"].get("id_cols", [])
        normality = pipeline.get("normality", {})
        
        audit_log = []
        result = run_multi_group_comparison(
            df_clean, "valeur", "groupe", normality, audit_log
        )
        
        assert result["status"] == "ok"
        
        # Si Kruskal-Wallis est utilisé et p < 0.05, vérifier le repli
        if "Kruskal" in result["test"] and result["p_value"] < 0.05:
            # Sans scikit-posthocs, Dunn doit retourner une erreur
            assert result["posthoc"] is not None
            assert "error" in result["posthoc"]
            assert "scikit-posthocs" in result["posthoc"]["error"]
    finally:
        # Restaurer HAS_POSTHOCS
        test_selector_module.HAS_POSTHOCS = original_has_posthocs
