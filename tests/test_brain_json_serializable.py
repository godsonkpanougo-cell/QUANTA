"""Test brain : json.dumps() sur tous les chemins (avec et sans clé LLM)."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_brain import (
    REGION_LIKERT_SAMPLE,
    assert_json_serializable,
    generate_interpretation,
    llm_keys_disabled,
    load_orchestrator_result,
    load_sample_columns,
    text_to_intent,
    analyze_with_brain,
)

if __name__ == "__main__":
    payloads: list[tuple[str, dict]] = []
    numeric, categorical = load_sample_columns(REGION_LIKERT_SAMPLE)

    with llm_keys_disabled():
        intent = text_to_intent(
            "comparer le revenu entre régions",
            numeric,
            categorical,
        )
        payloads.append(("intent_no_key", {
            "action": intent.action,
            "target_col": intent.target_col,
            "group_col": intent.group_col,
            "predictor_cols": intent.predictor_cols,
            "paired": intent.paired,
            "raw_query": intent.raw_query,
        }))

        analysis = load_orchestrator_result(
            "clean.csv",
            AnalysisIntent(action="correlation", target_col="age", group_col="income"),
        )
        interp = generate_interpretation(analysis)
        payloads.append(("interpretation_no_key", interp))

        def stub_run(intent):
            return analysis

        e2e = analyze_with_brain(
            "analyse ce dataset",
            numeric,
            categorical,
            stub_run,
        )
        payloads.append(("analyze_with_brain_no_key", e2e))

    for label, obj in payloads:
        assert_json_serializable(obj, label)

    print(f"\nOK : {len(payloads)} payloads JSON-sérialisables (chemins sans clé LLM)")
