"""Test sélecteur : comparaison 2 groupes appariés (paired=True)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.compute.test_selector import AnalysisIntent

if __name__ == "__main__":
    # Créer un dataset de test pour données appariées
    # Simule des mesures avant/après sur les mêmes sujets
    np.random.seed(42)
    n = 30
    data = {
        "sujet": [f"S{i:02d}" for i in range(n)],
        "groupe": ["A"] * (n // 2) + ["B"] * (n - n // 2),
        "avant": np.random.normal(100, 10, n),
        "apres": np.random.normal(105, 10, n),  # léger effet
    }
    df = pd.DataFrame(data)
    
    # Cas 1 : données normales -> t-test pairé (stats.ttest_rel)
    print("=" * 72)
    print("TEST 1 : Données normales appariées -> t-test pairé attendu")
    print("=" * 72)
    
    from app.compute.compute import run_base_compute_pipeline
    import io
    
    csv_content = df.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "paired_test.csv")
    
    if "error" in pipeline:
        print(f"ERREUR PIPELINE : {pipeline['error']}")
        sys.exit(1)
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    # Test avec paired=True sur une variable normale
    intent1 = AnalysisIntent(
        action="compare_groups",
        target_col="avant",
        group_col="groupe",
        paired=True,  # Force le chemin apparié
        raw_query="Comparaison appariée avant/après",
    )
    
    from app.compute.test_selector import select_and_run_test
    output1 = select_and_run_test(
        intent1, df_clean, numeric_cols, cat_cols, id_cols, normality
    )
    
    test1 = output1["result"].get("test", "")
    print(f"Test exécuté : {test1}")
    print(f"Action exécutée : {output1['action_executed']}")
    
    # Vérifier que c'est bien un test apparié
    if "pairé" not in test1.lower() and "paired" not in test1.lower():
        print(f"\n⚠️ ATTENTION : Le test n'est PAS apparié : {test1}")
        print("Cela suggère que le chemin paired=True n'est pas atteint depuis l'orchestrateur.")
        print("Le paramètre paired semble jamais transmis par le LLM ou auto_intent().")
        print("CODE MORT POTENTIEL DÉTECTÉ.")
        sys.exit(1)
    
    print(f"\n✓ Test apparié détecté : {test1}")
    
    # Cas 2 : données non-normales -> Wilcoxon signé (stats.wilcoxon)
    print("\n" + "=" * 72)
    print("TEST 2 : Données non-normales appariées -> Wilcoxon attendu")
    print("=" * 72)
    
    # Créer des données non-normales
    data_non_normal = {
        "sujet": [f"S{i:02d}" for i in range(n)],
        "groupe": ["A"] * (n // 2) + ["B"] * (n - n // 2),
        "score": np.random.exponential(10, n),  # distribution non-normale
    }
    df_non_normal = pd.DataFrame(data_non_normal)
    
    csv_content2 = df_non_normal.to_csv(index=False)
    pipeline2 = run_base_compute_pipeline(csv_content2.encode(), "paired_non_normal.csv")
    
    if "error" in pipeline2:
        print(f"ERREUR PIPELINE : {pipeline2['error']}")
        sys.exit(1)
    
    normality2 = pipeline2.get("normality", {})
    
    intent2 = AnalysisIntent(
        action="compare_groups",
        target_col="score",
        group_col="groupe",
        paired=True,
        raw_query="Comparaison appariée non-normale",
    )
    
    output2 = select_and_run_test(
        intent2, pipeline2["dataframe_clean"], pipeline2["numeric_cols"],
        pipeline2["cat_cols"], pipeline2["diagnosis"].get("id_cols", []), normality2
    )
    
    test2 = output2["result"].get("test", "")
    print(f"Test exécuté : {test2}")
    
    if "wilcoxon" not in test2.lower():
        print(f"\n⚠️ ATTENTION : Wilcoxon non détecté : {test2}")
        sys.exit(1)
    
    print(f"\n✓ Wilcoxon détecté : {test2}")
    print("\n" + "=" * 72)
    print("CONCLUSION : Le chemin paired=True fonctionne quand explicitement forcé")
    print("MAIS il n'est probablement jamais atteint depuis le pipeline réel")
    print("(LLM ne retourne jamais paired=True, auto_intent() ne le définit pas).")
    print("=" * 72)
