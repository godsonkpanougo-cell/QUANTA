"""Test orchestrateur : cas piège bout-en-bout (colonne id / inexistante)."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    out1 = run_orchestrator_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="revenu_annuel",
            group_col="department",
            raw_query="Comparer revenu annuel par département",
        ),
        label="colonne inexistante",
    )
    out2 = run_orchestrator_sample(
        "mixed_categorical.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="id",
            group_col="department",
            raw_query="Comparer id par département",
        ),
        label="colonne identifiant",
    )

    for label, out in [("inexistante", out1), ("id", out2)]:
        if out.get("status") != "ok":
            print(f"\nÉCHEC {label} : status={out.get('status')!r}")
            sys.exit(1)
        if out["inference"]["action_executed"] != "descriptive_only":
            print(f"\nÉCHEC {label} : action_executed={out['inference']['action_executed']!r}")
            sys.exit(1)
        if not out["inference"]["validation_issues"]:
            print(f"\nÉCHEC {label} : validation_issues vide")
            sys.exit(1)
        if out["inference"]["result"].get("status") != "skipped":
            print(f"\nÉCHEC {label} : inference.status={out['inference']['result'].get('status')!r}")
            sys.exit(1)

    print("\nOK : repli descriptive_only bout-en-bout sans crash")
