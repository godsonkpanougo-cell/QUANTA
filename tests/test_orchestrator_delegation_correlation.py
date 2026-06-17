"""Test orchestrateur : délégation corrélation vers matrice compute existante."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    result = run_orchestrator_sample(
        "clean.csv",
        AnalysisIntent(
            action="correlation",
            target_col="age",
            group_col="income",
            raw_query="Corrélation entre age et income",
        ),
        label="délégation corrélation",
    )
    if result.get("status") != "ok":
        print(f"\nÉCHEC : status={result.get('status')!r}")
        sys.exit(1)
    if result["inference"]["action_executed"] != "correlation":
        print(f"\nÉCHEC : action_executed={result['inference']['action_executed']!r}")
        sys.exit(1)
    inf = result["inference"]["result"]
    if inf.get("status") != "ok" or inf.get("r") is None:
        print(f"\nÉCHEC : inference result : {inf}")
        sys.exit(1)
    pair_key = "age x income"
    base_pair = result["correlation_base"]["pairs"].get(pair_key)
    if base_pair is None or base_pair.get("r") != inf.get("r"):
        print(f"\nÉCHEC : corrélation non réutilisée depuis correlation_base")
        sys.exit(1)
    steps = [e["etape"] for e in result["audit_log"]]
    if "delegation_correlation" not in steps:
        print(f"\nÉCHEC : pas d'entrée delegation_correlation dans audit_log")
        sys.exit(1)
    print(f"\nOK : corrélation déléguée, r={inf['r']}, audit delegation_correlation présent")
