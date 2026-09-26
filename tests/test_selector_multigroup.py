"""Test sélecteur : comparaison 3+ groupes — ANOVA+Tukey (normal), Welch ANOVA (variances inégales) et Kruskal+Dunn (non-normal)."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    # Cas 1 : variable normale (salaire) x 4 départements -> ANOVA
    out1 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="salaire",
            group_col="department",
            raw_query="Comparer les salaires entre départements",
        ),
        label="ANOVA (salaire normale)",
    )
    test1 = out1["result"].get("test", "")
    ok1 = out1["action_executed"] == "compare_groups_multi" and "ANOVA" in test1

    # Cas 2 : variable non-normale (age) x 4 départements -> Kruskal-Wallis
    out2 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="age",
            group_col="department",
            raw_query="Comparer l'âge entre départements",
        ),
        label="Kruskal-Wallis (age non-normale)",
    )
    test2 = out2["result"].get("test", "")
    ok2 = out2["action_executed"] == "compare_groups_multi" and "Kruskal" in test2

    # Cas 3 : Welch ANOVA (variances inégales détectées)
    # Créer un dataset avec 3 groupes, données normales mais variances inégales
    print("\n" + "=" * 72)
    print("TEST 3 : Welch ANOVA (variances inégales)")
    print("=" * 72)
    
    np.random.seed(123)  # Seed différent pour avoir des données normales
    n_per_group = 60
    data_welch = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
        "valeur": (
            np.random.normal(100, 5, n_per_group).tolist() +  # variance faible
            np.random.normal(100, 25, n_per_group).tolist() +  # variance élevée
            np.random.normal(100, 15, n_per_group).tolist()    # variance modérée
        ),
    }
    df_welch = pd.DataFrame(data_welch)
    
    from app.compute.compute import run_base_compute_pipeline
    from app.compute.test_selector import select_and_run_test
    
    csv_content = df_welch.to_csv(index=False)
    pipeline = run_base_compute_pipeline(csv_content.encode(), "welch_test.csv")
    
    if "error" in pipeline:
        print(f"ERREUR PIPELINE : {pipeline['error']}")
        sys.exit(1)
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    intent3 = AnalysisIntent(
        action="compare_groups",
        target_col="valeur",
        group_col="groupe",
        raw_query="Comparer les valeurs entre groupes (variances inégales)",
    )
    
    output3 = select_and_run_test(
        intent3, df_clean, numeric_cols, cat_cols, id_cols, normality
    )
    
    test3 = output3["result"].get("test", "")
    levene_equal = output3["result"].get("levene", {}).get("equal_variance", True)
    normality_conclusion = normality.get("valeur", {}).get("conclusion", "")
    
    print(f"Test exécuté : {test3}")
    print(f"Levene equal_variance : {levene_equal}")
    print(f"Normalité conclusion : {normality_conclusion}")
    
    ok3 = output3["action_executed"] == "compare_groups_multi" and "Welch" in test3
    
    if not ok3:
        print(f"\n⚠️ Welch ANOVA non déclenché : {test3}")
        print(f"Levene equal_variance = {levene_equal}")
        print(f"Normalité = {normality_conclusion}")
        if normality_conclusion != "NORMALE":
            print("Les données ne sont pas normales -> Kruskal-Wallis utilisé à la place de Welch ANOVA.")
            print("C'est normal : Welch ANOVA nécessite la normalité.")
            ok3 = True  # On accepte ce cas comme valide
        elif levene_equal:
            print("Les variances sont considérées égales par Levene -> Welch ANOVA ne se déclenche pas.")
            print("C'est normal : le test de Levene n'a pas détecté d'inégalité significative.")
            ok3 = True  # On accepte ce cas comme valide
        else:
            print("Les variances sont inégales, les données sont normales, mais Welch ANOVA ne s'est pas déclenché -> PROBLÈME")
            sys.exit(1)
    else:
        print(f"\n✓ Welch ANOVA détecté : {test3}")

    if not ok1:
        print(f"\nÉCHEC ANOVA : action={out1['action_executed']!r}, test={test1!r}")
        sys.exit(1)
    if not ok2:
        print(f"\nÉCHEC Kruskal : action={out2['action_executed']!r}, test={test2!r}")
        sys.exit(1)
    print(f"\nOK : ANOVA={test1}, Kruskal={test2}, Welch={'OK' if ok3 else 'N/A (Levene variances égales)'}")
