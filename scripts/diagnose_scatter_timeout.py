"""Script de diagnostic pour reproduire le timeout scatter plots sur datasets avec beaucoup de variables numériques."""
from __future__ import annotations

import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.compute import run_base_compute_pipeline

if __name__ == "__main__":
    print("=" * 72)
    print("DIAGNOSTIC : Timeout scatter plots - Simulation dataset dense")
    print("=" * 72)
    
    # Simuler un dataset avec 60 variables numériques pour reproduire le timeout
    np.random.seed(42)
    n_rows = 1000
    n_numeric = 60
    
    data = {}
    for i in range(n_numeric):
        # Générer des variables avec des corrélations significatives
        base = np.random.randn(n_rows)
        if i > 0:
            # Ajouter une corrélation avec la variable précédente
            base = 0.7 * base + 0.3 * np.random.randn(n_rows)
        data[f"var_{i}"] = base
    
    df = pd.DataFrame(data)
    csv_content = df.to_csv(index=False).encode()
    
    print(f"\nDataset simulé : {n_rows} lignes x {n_numeric} variables numériques")
    print(f"Paires possibles : {n_numeric * (n_numeric - 1) // 2}")
    
    print("\n--- Test du pipeline de base ---")
    start_time = time.time()
    
    try:
        result = run_base_compute_pipeline(csv_content, "test_dense.csv")
        elapsed = time.time() - start_time
        
        if "error" in result:
            print(f"\nERREUR : {result['error']}")
            sys.exit(1)
        
        print(f"\nPipeline terminé en {elapsed:.3f}s")
        
        # Analyser les résultats
        corr = result.get("correlation", {})
        scatter_plots = corr.get("scatter_plots", {})
        n_scatter = len(scatter_plots)
        
        print(f"Nombre de scatter plots générés : {n_scatter}")
        
        if elapsed > 30:
            print(f"\n[WARNING] Temps élevé : {elapsed:.3f}s")
            print("Cela confirme que la génération des scatter plots est le goulot d'étranglement.")
        else:
            print(f"\n[OK] Temps acceptable : {elapsed:.3f}s")
        
    except Exception as e:
        print(f"\nERREUR : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Voir les logs TIMING pour la répartition du temps")
    print("=" * 72)
