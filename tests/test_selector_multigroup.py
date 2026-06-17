"""Test sélecteur : comparaison 3+ groupes — ANOVA+Tukey (normal) et Kruskal+Dunn (non-normal)."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    # Cas 1 : variable normale (salaire) x 4 départements -> ANOVA
    out1 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="salaire",
            group_col="department",
            raw_query="Comparer les salaires entre départements",
        ),
        label="ANOVA (salaire normale)",
    )
    test1 = out1["result"].get("test", "")
    ok1 = out1["action_executed"] == "compare_groups_multi" and "ANOVA" in test1

    # Cas 2 : variable non-normale (age) x 4 départements -> Kruskal-Wallis
    out2 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="age",
            group_col="department",
            raw_query="Comparer l'âge entre départements",
        ),
        label="Kruskal-Wallis (age non-normale)",
    )
    test2 = out2["result"].get("test", "")
    ok2 = out2["action_executed"] == "compare_groups_multi" and "Kruskal" in test2

    if not ok1:
        print(f"\nÉCHEC ANOVA : action={out1['action_executed']!r}, test={test1!r}")
        sys.exit(1)
    if not ok2:
        print(f"\nÉCHEC Kruskal : action={out2['action_executed']!r}, test={test2!r}")
        sys.exit(1)
    print(f"\nOK : ANOVA={test1}, Kruskal={test2}")
