"""Test brain : generate_interpretation sans clé — llm_available=false + raw_analysis."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_brain import (
    assert_json_serializable,
    generate_interpretation,
    llm_keys_disabled,
    load_orchestrator_result,
    print_interpretation_summary,
)

if __name__ == "__main__":
    analysis = load_orchestrator_result(
        "ts_2groups_normal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="score",
            group_col="traitement",
            raw_query="Comparer le score entre les deux traitements",
        ),
    )

    with llm_keys_disabled():
        interp = generate_interpretation(analysis)

    assert_json_serializable(interp, "interpretation")
    print_interpretation_summary(interp)

    if interp.get("llm_available") is not False:
        print(f"\nÉCHEC : llm_available attendu False, obtenu={interp.get('llm_available')!r}")
        sys.exit(1)
    raw = interp.get("raw_analysis")
    if not raw or raw.get("status") != "ok":
        print(f"\nÉCHEC : raw_analysis inaccessible ou status != ok")
        sys.exit(1)
    if "confidence_score" not in raw:
        print("\nÉCHEC : raw_analysis sans confidence_score")
        sys.exit(1)

    print("\nOK : repli llm_available=false, raw_analysis accessible")
