"""Test brain : text_to_intent avec clé Groq (live) sur demande compare_groups."""
from __future__ import annotations

import sys

from tests._print_brain import (
    REGION_LIKERT_SAMPLE,
    assert_json_serializable,
    llm_is_configured,
    load_sample_columns,
    print_intent,
    text_to_intent,
)

if __name__ == "__main__":
    if not llm_is_configured():
        print("SKIP : aucune clé API LLM configurée (.env) — test live ignoré")
        sys.exit(0)

    query = "comparer le revenu entre régions"
    numeric, categorical = load_sample_columns(REGION_LIKERT_SAMPLE)

    print("=" * 72)
    print(f"QUERY : {query!r}")
    print(f"Colonnes numériques : {numeric}")
    print(f"Colonnes catégorielles : {categorical}")
    print("=" * 72)

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

    if intent.action != "compare_groups":
        print(f"\nÉCHEC : action attendue compare_groups, obtenu={intent.action!r}")
        sys.exit(1)
    if intent.target_col not in numeric:
        print(f"\nÉCHEC : target_col inattendu={intent.target_col!r}")
        sys.exit(1)
    if intent.group_col != "code_region":
        print(f"\nÉCHEC : group_col attendu code_region, obtenu={intent.group_col!r}")
        sys.exit(1)

    print("\nOK : intention compare_groups cohérente (revenu ~ income, régions ~ code_region)")
