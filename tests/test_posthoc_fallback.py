"""Test fallback post-hoc : Games-Howell et Dunn sans scikit-posthocs."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest.mock as mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from app.compute.compute import run_base_compute_pipeline
from app.compute.test_selector import AnalysisIntent, select_and_run_test

if __name__ == "__main__":
    print("=" * 72)
    print("TEST 1 : Games-Howell fallback sans scikit-posthocs")
    print("=" * 72)
    
    # Créer un dataset avec 3 groupes, données normales mais variances inégales
    # Utiliser un seed différent pour garantir la normalité
    np.random.seed(999)
    n_per_group = 60
    data = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
        "valeur": (
            np.random.normal(100, 3, n_per_group).tolist() +
            np.random.normal(100, 20, n_per_group).tolist() +
            np.random.normal(100, 10, n_per_group).tolist()
        ),
    }
    df = pd.DataFrame(data)
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "games_howell_test.csv")
    
    if "error" in pipeline:
        print(f"ERREUR PIPELINE : {pipeline['error']}")
        sys.exit(1)
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Mock HAS_POSTHOCS à False pour simuler l'absence de scikit-posthocs
    import app.compute.test_selector as ts_module
    with mock.patch.object(ts_module, 'HAS_POSTHOCS', False):
        intent = AnalysisIntent(
            action="compare_groups",
            target_col="valeur",
            group_col="groupe",
            raw_query="Comparer les valeurs entre groupes",
        )
        
        output = select_and_run_test(
            intent, df_clean, numeric_cols, cat_cols, id_cols, normality
        )
        
        result = output["result"]
        print(f"Test exécuté : {result.get('test', 'N/A')}")
        normality_conclusion = normality.get("valeur", {}).get("conclusion", "")
        print(f"Normalité : {normality_conclusion}")
        
        posthoc = result.get("posthoc")
        if posthoc:
            method = posthoc.get("method", "")
            print(f"Post-hoc method : {method}")
            
            if "Tukey" in method and "repli" in method:
                print("[OK] Fallback Tukey détecté (Games-Howell indisponible)")
                if "_avertissement" in posthoc:
                    print(f"[OK] Avertissement présent : {posthoc['_avertissement'][:50]}...")
            elif "Games-Howell" in method:
                print("[WARNING] Games-Howell détecté (mais scikit-posthocs devrait être désactivé)")
                print("Le mock n'a peut-être pas fonctionné comme attendu.")
            else:
                print(f"[WARNING] Méthode inattendue : {method}")
        else:
            if "Welch" in result.get("test", ""):
                print("[WARNING] Welch ANOVA détecté mais pas de post-hoc")
                print("Cela peut être normal si le test n'est pas significatif (p >= 0.05)")
            else:
                print("[WARNING] Aucun post-hoc détecté")
                print(f"Test utilisé : {result.get('test', 'N/A')}")
                print("Le fallback Games-Howell n'a pas pu être testé car Welch ANOVA ne s'est pas déclenché.")
    
    print("\n" + "=" * 72)
    print("TEST 2 : Dunn error sans scikit-posthocs")
    print("=" * 72)
    
    # Créer un dataset avec 3 groupes, données non-normales
    np.random.seed(123)
    data_non_normal = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
        "valeur": (
            np.random.exponential(10, n_per_group).tolist() +
            np.random.exponential(15, n_per_group).tolist() +
            np.random.exponential(20, n_per_group).tolist()
        ),
    }
    df_non_normal = pd.DataFrame(data_non_normal)
    
    csv_content2 = df_non_normal.to_csv(index=False)
    pipeline2 = run_base_compute_pipeline(csv_content2.encode(), "dunn_test.csv")
    
    if "error" in pipeline2:
        print(f"ERREUR PIPELINE : {pipeline2['error']}")
        sys.exit(1)
    
    normality2 = pipeline2.get("normality", {})
    
    with mock.patch.object(ts_module, 'HAS_POSTHOCS', False):
        intent2 = AnalysisIntent(
            action="compare_groups",
            target_col="valeur",
            group_col="groupe",
            raw_query="Comparer les valeurs entre groupes (non-normal)",
        )
        
        output2 = select_and_run_test(
            intent2, pipeline2["dataframe_clean"], pipeline2["numeric_cols"],
            pipeline2["cat_cols"], pipeline2["diagnosis"].get("id_cols", []), normality2
        )
        
        result2 = output2["result"]
        print(f"Test exécuté : {result2.get('test', 'N/A')}")
        
        posthoc2 = result2.get("posthoc")
        if posthoc2:
            if "error" in posthoc2:
                print(f"[OK] Erreur détectée comme attendu : {posthoc2['error']}")
            else:
                method2 = posthoc2.get("method", "")
                print(f"[WARNING] Méthode inattendue : {method2}")
                print(f"Post-hoc complet : {posthoc2}")
        else:
            print("⚠️ Aucun post-hoc détecté (peut être normal si test non significatif)")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Tests de fallback post-hoc terminés")
    print("=" * 72)
