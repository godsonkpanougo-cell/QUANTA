"""Test orchestrateur : pipeline standard compare_groups de bout en bout.

HISTORIQUE : échouait systématiquement (Mann-Whitney au lieu de
Student/Welch). Cause racine trouvée le 05/10/2026 et corrigée dans
compute.run_base_compute_pipeline : la branche theme="both" (défaut prod)
écrasait la normalité par un dict VIDE (double .get("normality")) -> le
selector recevait une normalité vide -> bascule non-paramétrique
systématique. Ce fichier est désormais un vrai test pytest (collecté par
la suite) et reste exécutable en script CLI.
"""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample


def test_compare_groups_pipeline_end_to_end():
    result = run_orchestrator_sample(
        "ts_2groups_normal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="score",
            group_col="traitement",
            raw_query="Comparer le score entre les deux traitements",
        ),
    )
    assert result.get("status") == "ok"
    assert result["inference"]["action_executed"] == "compare_groups_2"
    test_name = result["inference"]["result"].get("test", "")
    assert "Student" in test_name or "Welch" in test_name, (
        f"Normalité par groupe confirmée (fixture) -> test paramétrique "
        f"attendu, obtenu : {test_name!r}"
    )


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
