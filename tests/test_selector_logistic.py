"""Test sélecteur : régression logistique binaire."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    output = run_selector_sample(
        "ts_logistic_binary.csv",
        AnalysisIntent(
            action="regression",
            target_col="diabete",
            predictor_cols=["age", "imc"],
            raw_query="Prédire le diabète à partir de l'âge et de l'IMC",
        ),
    )
    result = output["result"]
    if output["action_executed"] != "regression_logistic" or result.get("status") != "ok":
        print(f"\nÉCHEC : attendu regression_logistic/ok, obtenu {output['action_executed']!r} / {result.get('status')!r}")
        sys.exit(1)
    print(f"\nOK : régression logistique, n_obs={result.get('n_obs')}, pseudo_R2={result.get('pseudo_R2')}")
