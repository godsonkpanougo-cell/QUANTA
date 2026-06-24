"""Test brain : text_to_intent sans clé API — repli descriptive_only sans crash."""
from __future__ import annotations

import sys

from tests._print_brain import (
    REGION_LIKERT_SAMPLE,
    assert_json_serializable,
    llm_keys_disabled,
    load_sample_columns,
    print_intent,
    text_to_intent,
)

if __name__ == "__main__":
    query = "comparer le revenu entre régions"
    numeric, categorical = load_sample_columns(REGION_LIKERT_SAMPLE)

    with llm_keys_disabled():
        intent = text_to_intent(query, numeric, categorical)

    assert_json_serializable(
        {
            "action": intent.action,
            "target_col": intent.target_col,
            "group_col": intent.group_col,
            "predictor_cols": intent.predictor_cols,
            "paired": intent.paired,
            "raw_query": intent.raw_query,
        },
        "intent",
    )
    print_intent(intent)

    if intent.action != "descriptive_only":
        print(f"\nÉCHEC : action attendue descriptive_only, obtenu={intent.action!r}")
        sys.exit(1)

    print("\nOK : repli descriptive_only sans crash (LLM indisponible)")
