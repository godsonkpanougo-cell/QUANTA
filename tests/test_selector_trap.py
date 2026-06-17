"""Test sélecteur : cas piège — colonne inexistante ou identifiant -> descriptive_only sans crash."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_selector import run_selector_sample

if __name__ == "__main__":
    # Cas 1 : colonne hallucinée par le LLM
    out1 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="revenu_annuel",
            group_col="department",
            raw_query="Comparer le revenu annuel par département",
        ),
        label="colonne inexistante",
    )

    # Cas 2 : colonne ID proposée par erreur
    out2 = run_selector_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="id",
            group_col="department",
            raw_query="Comparer id par département",
        ),
        label="colonne identifiant",
    )

    def _check_trap(output: dict, label: str) -> bool:
        if output["action_executed"] != "descriptive_only":
            print(f"\nÉCHEC {label} : action_executed={output['action_executed']!r}")
            return False
        issues = output["validation_issues"]
        if not issues:
            print(f"\nÉCHEC {label} : validation_issues vide")
            return False
        if not all(isinstance(i, dict) and "champ" in i and "probleme" in i for i in issues):
            print(f"\nÉCHEC {label} : validation_issues mal structurées (attendu dict JSON)")
            return False
        if output["result"].get("status") != "skipped":
            print(f"\nÉCHEC {label} : result.status={output['result'].get('status')!r}")
            return False
        return True

    ok1 = _check_trap(out1, "inexistante")
    ok2 = _check_trap(out2, "id_cols")

    if not ok1 or not ok2:
        sys.exit(1)
    print(f"\nOK : repli descriptive_only avec validation_issues documentées (sans crash)")
