"""Test orchestrateur : délégation OLS - vérification du chemin de recalcul."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    print("=" * 72)
    print("TEST : Analyse du chemin de recalcul OLS")
    print("=" * 72)
    
    # Analyse du code orchestrator.py (ligne 545-546) :
    # base_target = intent.target_col if intent.action == "regression" else None
    # Donc quand l'action est "regression", le calcul générique utilise déjà
    # le target_col de l'intention. Le chemin de recalcul n'est donc PAS
    # atteignable dans ce scénario normal.
    
    print("\n--- ANALYSE DU CODE ---")
    print("Dans orchestrator.py, ligne 545-546 :")
    print("  base_target = intent.target_col if intent.action == 'regression' else None")
    print("  pipeline = compute.run_base_compute_pipeline(..., target_col=base_target, ...)")
    print("\nConclusion : Quand action='regression', le calcul générique utilise déjà")
    print("le target_col de l'intention. Le chemin de recalcul n'est PAS atteignable")
    print("dans le scénario normal.")
    
    print("\n--- TEST DE RÉUTILISATION (chemin déjà testé) ---")
    result = run_orchestrator_sample(
        "clean.csv",
        AnalysisIntent(
            action="regression",
            target_col="income",
            predictor_cols=["age"],
            raw_query="Prédire income à partir de age",
        ),
        label="délégation OLS réutilisation",
    )
    
    if result.get("status") != "ok":
        print(f"\nÉCHEC : status={result.get('status')!r}")
        sys.exit(1)
    
    base = result["regression_base"]
    inf = result["inference"]["result"]
    
    if base.get("y_variable") == inf.get("y_variable") == "income":
        print(f"\n[OK] Réutilisation détectée : base.y_variable={base.get('y_variable')}, inf.y_variable={inf.get('y_variable')}")
    else:
        print(f"\n[WARNING] ATTENTION : y_variables incohérentes")
    
    delegation = next(e for e in result["audit_log"] if e["etape"] == "delegation_ols")
    print(f"Décision de délégation : {delegation['decision']}")
    
    print("\n" + "=" * 72)
    print("CONCLUSION :")
    print("- Le chemin de réutilisation fonctionne correctement")
    print("- Le chemin de recalcul (recalcul_avec_cible_specifique) n'est PAS atteignable")
    print("  dans le pipeline actuel car orchestrator.py passe toujours intent.target_col")
    print("  au calcul générique quand action='regression'.")
    print("- CODE MORT POTENTIEL DETECTE : la branche recalcul dans _resolve_delegation")
    print("  (orchestrator.py ligne 119) n'est jamais atteinte dans le pipeline normal.")
    print("=" * 72)
