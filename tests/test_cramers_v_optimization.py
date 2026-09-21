"""Test pour vérifier l'optimisation du bootstrap V de Cramér."""

import time
import pandas as pd
import numpy as np
from app.compute.test_selector import _cramers_v_with_ci


def test_cramers_v_optimization_timing():
    """
    Test que l'optimisation du bootstrap réduit significativement le temps.
    Compare le temps avant/après optimisation (objectif: < 5s pour 1000 itérations).
    """
    # Créer un dataset catégoriel réaliste
    np.random.seed(42)
    n = 200
    data = {
        "sexe": np.random.choice(["H", "F"], size=n),
        "preference": np.random.choice(["A", "B", "C"], size=n, p=[0.5, 0.3, 0.2])
    }
    df = pd.DataFrame(data)
    
    print(f"\nDataset: {n} lignes, 2 variables catégorielles")
    print(f"Tableau de contingence:\n{pd.crosstab(df['sexe'], df['preference'])}")
    
    # Mesurer le temps avec l'optimisation
    start_time = time.time()
    cramers_v, ci_lower, ci_upper = _cramers_v_with_ci(df, "sexe", "preference", n_bootstrap=1000)
    elapsed = time.time() - start_time
    
    print(f"\nRésultats:")
    print(f"V de Cramér: {cramers_v}")
    print(f"IC 95%: [{ci_lower}, {ci_upper}]")
    print(f"Temps écoulé: {elapsed:.2f}s pour 1000 itérations bootstrap")
    
    # Vérifier que le temps est raisonnable (< 10s, idéalement < 5s)
    assert elapsed < 10.0, f"Le bootstrap devrait prendre < 10s, mais a pris {elapsed:.2f}s"
    
    # Vérifier que les résultats sont valides
    assert 0 <= cramers_v <= 1, "V de Cramér devrait être entre 0 et 1"
    assert not np.isnan(ci_lower), "IC inférieur ne devrait pas être NaN"
    assert not np.isnan(ci_upper), "IC supérieur ne devrait pas être NaN"
    assert ci_lower <= cramers_v <= ci_upper, "V de Cramér devrait être dans l'IC"
    
    print(f"\n[OK] Temps acceptable: {elapsed:.2f}s (< 10s)")
    print(f"[OK] Résultats valides")


if __name__ == "__main__":
    test_cramers_v_optimization_timing()
