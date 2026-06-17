"""Test sélecteur : comparaison 2 groupes, variable non-normale -> Mann-Whitney."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    output = run_selector_sample(
        "ts_2groups_nonnormal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="delai",
            group_col="groupe",
            raw_query="Comparer les délais entre contrôle et traitement",
        ),
    )
    result = output["result"]
    test_name = result.get("test", "")
    if output["action_executed"] != "compare_groups_2" or "Mann-Whitney" not in test_name:
        print(f"\nÉCHEC : attendu compare_groups_2 + Mann-Whitney, obtenu {output['action_executed']!r} / {test_name!r}")
        sys.exit(1)
    print(f"\nOK : {test_name}")
