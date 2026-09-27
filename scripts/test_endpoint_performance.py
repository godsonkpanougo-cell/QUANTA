"""Test performance du pipeline d'analyse (équivalent endpoint /analyze)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from app.orchestrator import run_full_analysis, auto_intent
from app.compute.compute import load_and_diagnose
from app.compute.test_selector import AnalysisIntent

if __name__ == "__main__":
    print("=" * 72)
    print("TEST : Performance pipeline analyse (2 num + 1 cat)")
    print("=" * 72)
    
    # Créer un dataset avec 2 colonnes numériques et 1 catégorielle
    np.random.seed(42)
    n = 100
    data = {
        "groupe": ["A"] * (n // 2) + ["B"] * (n // 2),
        "valeur1": np.random.normal(100, 10, n).tolist(),
        "valeur2": np.random.normal(50, 5, n).tolist(),
    }
    df = pd.DataFrame(data)
    csv_content = df.to_csv(index=False)
    
    # Obtenir le diagnostic pour auto_intent
    diagnosis = load_and_diagnose(csv_content.encode(), "test_performance.csv")
    if "error" in diagnosis:
        print(f"ERREUR DIAGNOSTIC : {diagnosis['error']}")
        sys.exit(1)
    
    # Générer les intents automatiquement
    intents = auto_intent(diagnosis)
    print(f"\nNombre d'intents auto-générés : {len(intents)}")
    
    # Mesurer le temps pour chaque intent (comme le ferait l'endpoint /analyze)
    total_elapsed = 0
    all_ci_present = True
    
    for i, intent in enumerate(intents):
        print(f"\n--- Intent {i+1}: action={intent.action}, target={intent.target_col}, group={intent.group_col} ---")
        start_time = time.time()
        result = run_full_analysis(csv_content.encode(), "test_performance.csv", intent=intent, theme="dark")
        elapsed = time.time() - start_time
        total_elapsed += elapsed
        
        print(f"Temps de réponse : {elapsed:.3f}s")
        
        if result.get("status") == "ok":
            inference_result = result.get("inference", {}).get("result", {})
            has_ci = (
                inference_result.get("effect_size_ci_lower") is not None or
                inference_result.get("eta_squared_ci_lower") is not None or
                inference_result.get("epsilon_squared_ci_lower") is not None
            )
            print(f"CI bootstrap présent : {'OUI' if has_ci else 'NON'}")
            if not has_ci:
                all_ci_present = False
        else:
            print(f"ERREUR : {result.get('error', 'Erreur inconnue')}")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Performance pipeline analyse (APRES bootstrap CI)")
    print(f"Temps total ({len(intents)} intents) : {total_elapsed:.3f}s")
    print(f"Temps moyen par intent : {total_elapsed / len(intents):.3f}s")
    print(f"IC bootstrap présents sur tous les tests : {'OUI' if all_ci_present else 'NON'}")
    
    if total_elapsed > 10.0:
        print(f"[WARNING] Temps total élevé : {total_elapsed:.3f}s")
    else:
        print(f"[OK] Temps total acceptable : {total_elapsed:.3f}s")
    print("=" * 72)
    
    print("\nNOTE : Mesure 'APRES' implémentation bootstrap CI.")
    print("Pour une mesure 'AVANT', il faudrait revenir avant les modifications.")
