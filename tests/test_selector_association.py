"""Test sélecteur : association catégorielle — Chi-deux (grands effectifs) et Fisher exact (2x2)."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    # Cas 1 : genre x department sur mixed_categorical -> Chi-deux
    out1 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="association",
            target_col="genre",
            group_col="department",
            raw_query="Y a-t-il une association entre genre et département ?",
        ),
        label="Chi-deux (effectifs suffisants)",
    )
    test1 = out1["result"].get("test", "")
    ok1 = out1["action_executed"] == "association" and "Chi-deux" in test1

    # Cas 2 : table 2x2 petite -> Fisher exact
    out2 = run_selector_sample(
        "ts_assoc_fisher.csv",
        AnalysisIntent(
            action="association",
            target_col="exposition",
            group_col="maladie",
            raw_query="Association exposition-maladie",
        ),
        label="Fisher exact (2x2, petits effectifs)",
    )
    test2 = out2["result"].get("test", "")
    ok2 = out2["action_executed"] == "association" and "Fisher" in test2

    if not ok1:
        print(f"\nÉCHEC Chi-deux : action={out1['action_executed']!r}, test={test1!r}")
        sys.exit(1)
    if not ok2:
        print(f"\nÉCHEC Fisher : action={out2['action_executed']!r}, test={test2!r}")
        sys.exit(1)
    print(f"\nOK : Chi-deux={test1}, Fisher={test2}")
