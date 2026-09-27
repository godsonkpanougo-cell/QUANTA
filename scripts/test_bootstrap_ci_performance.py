"""Test performance des intervalles de confiance bootstrap."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from app.compute.compute import run_base_compute_pipeline
from app.compute.test_selector import AnalysisIntent, select_and_run_test

if __name__ == "__main__":
    print("=" * 72)
    print("TEST : Performance des IC bootstrap (1000 réplications)")
    print("=" * 72)
    
    # Créer un dataset synthétique pour t-test 2 groupes
    np.random.seed(42)
    n_per_group = 50
    data = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group,
        "valeur": (
            np.random.normal(100, 10, n_per_group).tolist() +
            np.random.normal(105, 10, n_per_group).tolist()
        ),
    }
    df = pd.DataFrame(data)
    csv_content = df.to_csv(index=False)
    
    print("\n--- TEST 1 : Cohen's d (t-test 2 groupes) ---")
    pipeline = run_base_compute_pipeline(csv_content.encode(), "bootstrap_test.csv")
    
    if "error" in pipeline:
        print(f"ERREUR PIPELINE : {pipeline['error']}")
        sys.exit(1)
    
    df_clean = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline.get("normality", {})
    
    intent = AnalysisIntent(
        action="compare_groups",
        target_col="valeur",
        group_col="groupe",
        raw_query="Test bootstrap CI",
    )
    
    start_time = time.time()
    output = select_and_run_test(intent, df_clean, numeric_cols, cat_cols, id_cols, normality)
    elapsed = time.time() - start_time
    
    result = output["result"]
    print(f"Test exécuté : {result.get('test', 'N/A')}")
    print(f"Effect size : {result.get('effect_size')}")
    print(f"Effect size CI : [{result.get('effect_size_ci_lower')}, {result.get('effect_size_ci_upper')}]")
    print(f"Temps d'exécution : {elapsed:.3f}s")
    
    if elapsed > 5.0:
        print(f"[WARNING] Temps d'exécution élevé : {elapsed:.3f}s")
        print("Considérer de réduire n_bootstrap si cela impacte l'API.")
    else:
        print(f"[OK] Temps d'exécution acceptable : {elapsed:.3f}s")
    
    # Créer un dataset pour ANOVA (3 groupes)
    print("\n--- TEST 2 : η² (ANOVA 3 groupes) ---")
    data_anova = {
        "groupe": ["A"] * n_per_group + ["B"] * n_per_group + ["C"] * n_per_group,
        "valeur": (
            np.random.normal(100, 10, n_per_group).tolist() +
            np.random.normal(105, 10, n_per_group).tolist() +
            np.random.normal(110, 10, n_per_group).tolist()
        ),
    }
    df_anova = pd.DataFrame(data_anova)
    csv_content2 = df_anova.to_csv(index=False)
    
    pipeline2 = run_base_compute_pipeline(csv_content2.encode(), "bootstrap_test_anova.csv")
    
    if "error" in pipeline2:
        print(f"ERREUR PIPELINE : {pipeline2['error']}")
        sys.exit(1)
    
    normality2 = pipeline2.get("normality", {})
    
    start_time2 = time.time()
    output2 = select_and_run_test(
        intent, pipeline2["dataframe_clean"], pipeline2["numeric_cols"],
        pipeline2["cat_cols"], pipeline2["diagnosis"].get("id_cols", []), normality2
    )
    elapsed2 = time.time() - start_time2
    
    result2 = output2["result"]
    print(f"Test exécuté : {result2.get('test', 'N/A')}")
    print(f"η² : {result2.get('eta_squared')}")
    print(f"η² CI : [{result2.get('eta_squared_ci_lower')}, {result2.get('eta_squared_ci_upper')}]")
    print(f"Temps d'exécution : {elapsed2:.3f}s")
    
    if elapsed2 > 5.0:
        print(f"[WARNING] Temps d'exécution élevé : {elapsed2:.3f}s")
    else:
        print(f"[OK] Temps d'exécution acceptable : {elapsed2:.3f}s")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Performance bootstrap CI")
    print(f"Temps total (2 tests) : {elapsed + elapsed2:.3f}s")
    print("=" * 72)
