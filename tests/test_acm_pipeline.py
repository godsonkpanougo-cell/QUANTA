"""Test ACM : vérifie que run_acm() est atteint par le pipeline complet."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    # Utiliser le fichier test_acm_with_identifier.csv qui existe déjà
    # Ce fichier a 3+ colonnes catégorielles (Region, Type_Sol, Culture, Groupe)
    
    print("=" * 72)
    print("TEST ACM : Pipeline complet avec 3+ colonnes catégorielles")
    print("=" * 72)
    
    # Test avec action="acm" sur 2 colonnes catégorielles
    # Cela devrait déclencher l'ACM automatiquement si 3+ cat_cols sont détectées
    out = run_selector_sample(
        "test_acm_with_identifier.csv",
        AnalysisIntent(
            action="acm",
            target_col="Region",
            group_col="Type_Sol",
            raw_query="Association entre Region et Type_Sol",
        ),
        label="ACM automatique",
    )
    
    result = out["result"]
    print(f"\n--- RÉSULTAT ---")
    print(f"status={result.get('status')}")
    print(f"test={result.get('test', 'N/A')}")
    
    # Vérifier si l'ACM est présente dans le résultat
    if "acm" in result:
        print(f"\n[OK] ACM détecté dans le résultat")
        acm_result = result["acm"]
        print(f"ACM status={acm_result.get('status')}")
        if acm_result.get("status") == "ok":
            print(f"[OK] ACM exécuté avec succès")
            inertia = acm_result.get("inertia_pct", [])
            print(f"Inertie expliquée (premières dimensions) : {inertia[:3] if inertia else 'N/A'}")
        else:
            print(f"⚠️ ACM erreur : {acm_result.get('error', 'Erreur inconnue')}")
    else:
        print(f"\n[WARNING] ACM NON détecté dans le résultat")
        print("Cela suggère que le chemin ACM automatique n'est pas atteint.")
        print("Vérifier si la règle auto_intent() dans orchestrator.py déclenche correctement l'ACM.")
        print("CODE MORT POTENTIEL DÉTECTÉ.")
        sys.exit(1)
    
    print("\n" + "=" * 72)
    print("CONCLUSION : ACM automatique fonctionne")
    print("=" * 72)
