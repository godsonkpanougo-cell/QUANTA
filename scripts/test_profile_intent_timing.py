"""Profile le temps d'exécution du premier intent pour identifier l'anomalie."""
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
    print("PROFILE : Premier intent timing anomaly")
    print("=" * 72)
    
    # Créer un dataset identique
    np.random.seed(42)
    n = 100
    data = {
        "groupe": ["A"] * (n // 2) + ["B"] * (n // 2),
        "valeur1": np.random.normal(100, 10, n).tolist(),
        "valeur2": np.random.normal(50, 5, n).tolist(),
    }
    df = pd.DataFrame(data)
    csv_content = df.to_csv(index=False)
    
    # Obtenir le diagnostic
    diagnosis = load_and_diagnose(csv_content.encode(), "test_profile.csv")
    intents = auto_intent(diagnosis)
    
    # Premier intent (compare_groups valeur1)
    intent1 = intents[0]
    print(f"\nIntent 1: action={intent1.action}, target={intent1.target_col}, group={intent1.group_col}")
    
    # Exécuter 3 fois pour voir si c'est reproductible
    for run in range(3):
        print(f"\n--- Run {run + 1} ---")
        
        # Étape 1: load_and_diagnose
        t0 = time.time()
        diagnosis = load_and_diagnose(csv_content.encode(), "test_profile.csv")
        t1 = time.time()
        print(f"load_and_diagnose: {t1 - t0:.3f}s")
        
        # Étape 2: auto_intent
        t2 = time.time()
        intents = auto_intent(diagnosis)
        t3 = time.time()
        print(f"auto_intent: {t3 - t2:.3f}s")
        
        # Étape 3: run_full_analysis (inclut compute pipeline + test_selector)
        t4 = time.time()
        result = run_full_analysis(csv_content.encode(), "test_profile.csv", intent=intent1, theme="dark")
        t5 = time.time()
        print(f"run_full_analysis: {t5 - t4:.3f}s")
        print(f"Total: {t5 - t0:.3f}s")
    
    print("\n" + "=" * 72)
    print("NOTE : Si le premier run est significativement plus lent,")
    print("c'est probablement un cache matplotlib ou import de bibliothèques.")
    print("=" * 72)
