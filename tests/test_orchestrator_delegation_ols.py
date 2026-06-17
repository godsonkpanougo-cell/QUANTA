"""Test orchestrateur : délégation régression OLS vers résultat compute existant."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    result = run_orchestrator_sample(
        "clean.csv",
        AnalysisIntent(
            action="regression",
            target_col="income",
            predictor_cols=["age", "score"],
            raw_query="Prédire income à partir de age et score",
        ),
        label="délégation OLS",
    )
    if result.get("status") != "ok":
        print(f"\nÉCHEC : status={result.get('status')!r}")
        sys.exit(1)
    if result["inference"]["action_executed"] != "regression_ols":
        print(f"\nÉCHEC : action_executed={result['inference']['action_executed']!r}")
        sys.exit(1)
    inf = result["inference"]["result"]
    if inf.get("status") != "ok" or inf.get("y_variable") != "income":
        print(f"\nÉCHEC : inference result incohérent : {inf}")
        sys.exit(1)
    base = result["regression_base"]
    if base.get("status") != "ok" or base.get("R2") != inf.get("R2"):
        print(f"\nÉCHEC : réutilisation OLS non cohérente avec regression_base")
        sys.exit(1)
    steps = [e["etape"] for e in result["audit_log"]]
    if "delegation_ols" not in steps:
        print(f"\nÉCHEC : pas d'entrée delegation_ols dans audit_log")
        sys.exit(1)
    delegation = next(e for e in result["audit_log"] if e["etape"] == "delegation_ols")
    if delegation["decision"] != "reutilisation_resultat_existant":
        print(f"\nÉCHEC : decision={delegation['decision']!r}")
        sys.exit(1)
    print(f"\nOK : OLS déléguée, R2={inf['R2']}, audit delegation_ols présent")
