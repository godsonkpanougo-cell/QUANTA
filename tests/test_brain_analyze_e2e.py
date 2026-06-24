"""Test brain : analyze_with_brain bout-en-bout avec orchestrator.run_full_analysis."""
from __future__ import annotations

import sys
from pathlib import Path

from tests._print_brain import (
    ROOT,
    assert_json_serializable,
    llm_is_configured,
    load_sample_columns,
    print_interpretation_summary,
    analyze_with_brain,
)
from app.llm.brain import _has_suspicious_leading_zero, _validate_no_hallucinated_numbers

if __name__ == "__main__":
    csv_name = "region_likert.csv"
    query = "comparer le revenu entre régions"
    path = ROOT / "data" / "samples" / csv_name
    file_bytes = path.read_bytes()

    numeric_cols, cat_cols = load_sample_columns(csv_name)

    def run_analysis(intent):
        from app.orchestrator import run_full_analysis
        return run_full_analysis(file_bytes, path.name, intent)

    print("=" * 72)
    print(f"E2E : {csv_name} — {query!r}")
    print(f"LLM configuré : {llm_is_configured()}")
    print("=" * 72)

    result = analyze_with_brain(query, numeric_cols, cat_cols, run_analysis)
    assert_json_serializable(result, "analyze_with_brain")

    intent = result["intent"]
    analysis = result["analysis"]
    interp = result["interpretation"]

    print(f"\n--- INTENT ---")
    print(
        f"action={intent['action']!r}, target={intent['target_col']!r}, "
        f"group={intent['group_col']!r}"
    )
    print(f"\n--- ANALYSIS ---")
    print(f"status={analysis.get('status')}")
    print(f"action_executed={analysis.get('inference', {}).get('action_executed')}")
    print_interpretation_summary(interp)

    if analysis.get("status") != "ok":
        print(f"\nÉCHEC : analysis.status={analysis.get('status')!r}")
        sys.exit(1)

    if llm_is_configured():
        if intent.get("action") != "compare_groups":
            print(f"\nÉCHEC (live) : action attendue compare_groups, obtenu={intent.get('action')!r}")
            sys.exit(1)
        if not interp.get("llm_available"):
            print(f"\nÉCHEC (live) : interprétation indisponible — {interp.get('reason')}")
            sys.exit(1)

        check = interp.get("anti_hallucination_check", {})
        suspects = check.get("nombres_suspects_detectes", [])
        anomalous = check.get("formats_anormaux_detectes", [])
        warning = check.get("avertissement") or ""

        if "formats_anormaux_detectes" not in check:
            print("\nÉCHEC : champ formats_anormaux_detectes manquant")
            sys.exit(1)

        overlap = set(suspects) & set(anomalous)
        if overlap:
            print(f"\nÉCHEC : chevauchement suspects/formats_anormaux : {overlap}")
            sys.exit(1)

        for token in anomalous:
            if not _has_suspicious_leading_zero(token):
                print(f"\nÉCHEC : {token!r} dans formats_anormaux sans zéro de tête suspect")
                sys.exit(1)
            if token in suspects:
                print(f"\nÉCHEC : {token!r} ne doit pas être dans nombres_suspects")
                sys.exit(1)

        if anomalous and "format anormal" not in warning.lower():
            print(f"\nÉCHEC : avertissement doit mentionner le format anormal : {warning!r}")
            sys.exit(1)

        # Régression ANOVA : 025,02 classé en format anormal, pas en suspect classique
        regression = _validate_no_hallucinated_numbers(
            '{"niveau_analytique": "eta_squared de 025,02 sur les revenus"}',
            {
                "inference": analysis.get("inference", {}),
                "confidence_score": analysis.get("confidence_score", {}),
                "diagnosis": analysis.get("diagnosis", {}),
            },
        )
        if "025,02" not in regression["formats_anormaux"]:
            print(f"\nÉCHEC : 025,02 attendu dans formats_anormaux, obtenu={regression}")
            sys.exit(1)
        if "025,02" in regression["nombres_suspects"]:
            print("\nÉCHEC : 025,02 ne doit pas figurer dans nombres_suspects")
            sys.exit(1)

        live_leading_zero = [t for t in anomalous if _has_suspicious_leading_zero(t)]
        if live_leading_zero:
            print(f"\nNOTE : formats anormaux live détectés : {live_leading_zero}")
        else:
            print("\nNOTE : pas de zéro de tête dans la sortie live (LLM variable) — régression unitaire OK")
    else:
        if intent.get("action") != "descriptive_only":
            print(f"\nÉCHEC (no-key) : action attendue descriptive_only")
            sys.exit(1)
        if interp.get("llm_available") is not False:
            print("\nÉCHEC (no-key) : llm_available devrait être False")
            sys.exit(1)

    print("\nOK : pipeline analyze_with_brain bout-en-bout")
