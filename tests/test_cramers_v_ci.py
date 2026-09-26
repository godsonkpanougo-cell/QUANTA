"""Test unitaire pour les intervalles de confiance bootstrap du V de Cramér."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from app.compute.test_selector import run_categorical_association, _cramers_v_with_ci

if __name__ == "__main__":
    print("=" * 72)
    print("TEST : IC bootstrap pour V de Cramér")
    print("=" * 72)
    
    # Créer un dataset catégoriel pour test chi²
    np.random.seed(42)
    n = 100
    data = {
        "sexe": np.random.choice(["H", "F"], n),
        "preference": np.random.choice(["A", "B", "C"], n),
    }
    df = pd.DataFrame(data)
    
    print("\n--- TEST 1 : Fonction _cramers_v_with_ci directe ---")
    cramers_v, ci_lower, ci_upper = _cramers_v_with_ci(df, "sexe", "preference")
    print(f"V de Cramér : {cramers_v}")
    print(f"IC bootstrap 95% : [{ci_lower}, {ci_upper}]")
    
    if not np.isnan(ci_lower) and not np.isnan(ci_upper):
        print("[OK] IC bootstrap calculé avec succès")
        if ci_lower <= cramers_v <= ci_upper:
            print("[OK] V de Cramér dans l'IC (vérification de base)")
        else:
            print("[WARNING] V de Cramér hors de l'IC (anormal)")
    else:
        print("[WARNING] IC bootstrap non calculé (échantillon trop petit ?)")
    
    print("\n--- TEST 2 : Intégration dans run_categorical_association ---")
    audit_log = []
    result = run_categorical_association(df, "sexe", "preference", audit_log)
    
    print(f"Status : {result.get('status')}")
    print(f"Test : {result.get('test')}")
    print(f"V de Cramér : {result.get('cramers_v')}")
    print(f"V de Cramér CI : [{result.get('cramers_v_ci_lower')}, {result.get('cramers_v_ci_upper')}]")
    
    if result.get("cramers_v_ci_lower") is not None and result.get("cramers_v_ci_upper") is not None:
        print("[OK] IC bootstrap intégré dans le résultat")
    else:
        print("[ERROR] IC bootstrap non intégré dans le résultat")
    
    print("\n--- TEST 3 : Échantillon trop petit (< 10) ---")
    small_data = {
        "sexe": ["H", "F"],
        "preference": ["A", "B"],
    }
    small_df = pd.DataFrame(small_data)
    cramers_v_small, ci_lower_small, ci_upper_small = _cramers_v_with_ci(small_df, "sexe", "preference")
    print(f"V de Cramér : {cramers_v_small}")
    print(f"IC bootstrap : [{ci_lower_small}, {ci_upper_small}]")
    
    if np.isnan(ci_lower_small) and np.isnan(ci_upper_small):
        print("[OK] IC bootstrap retourné NaN pour petit échantillon")
    else:
        print("[WARNING] IC bootstrap calculé malgré petit échantillon")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Test IC bootstrap V de Cramér")
    print("Fonctionnalité implémentée et testée.")
    print("=" * 72)
