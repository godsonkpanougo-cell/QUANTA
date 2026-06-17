"""Test sélecteur : comparaison 2 groupes, variable normale -> Student ou Welch."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    output = run_selector_sample(
        "ts_2groups_normal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="score",
            group_col="traitement",
            raw_query="Comparer le score entre les deux traitements",
        ),
    )
    result = output["result"]
    test_name = result.get("test", "")
    expected = ("Student" in test_name) or ("Welch" in test_name)
    if output["action_executed"] != "compare_groups_2" or not expected:
        print(f"\nÉCHEC : attendu compare_groups_2 + Student/Welch, obtenu {output['action_executed']!r} / {test_name!r}")
        sys.exit(1)
    print(f"\nOK : {test_name}")
