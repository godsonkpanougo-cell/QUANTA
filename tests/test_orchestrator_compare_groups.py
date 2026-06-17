"""Test orchestrateur : pipeline standard compare_groups de bout en bout."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    result = run_orchestrator_sample(
        "ts_2groups_normal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="score",
            group_col="traitement",
            raw_query="Comparer le score entre les deux traitements",
        ),
    )
    if result.get("status") != "ok":
        print(f"\nÉCHEC : status={result.get('status')!r}")
        sys.exit(1)
    if result["inference"]["action_executed"] != "compare_groups_2":
        print(f"\nÉCHEC : action_executed={result['inference']['action_executed']!r}")
        sys.exit(1)
    test_name = result["inference"]["result"].get("test", "")
    if "Student" not in test_name and "Welch" not in test_name:
        print(f"\nÉCHEC : test={test_name!r}")
        sys.exit(1)
    print(f"\nOK : pipeline complet, {test_name}")
