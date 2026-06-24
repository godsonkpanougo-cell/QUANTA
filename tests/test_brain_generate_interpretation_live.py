"""Test brain : generate_interpretation live sur résultat orchestrator réel."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from app.llm.brain import _validate_no_hallucinated_numbers
from tests._print_brain import (
    assert_json_serializable,
    generate_interpretation,
    llm_is_configured,
    load_orchestrator_result,
    print_interpretation_summary,
)

if __name__ == "__main__":
    if not llm_is_configured():
        print("SKIP : aucune clé API LLM configurée (.env) — test live ignoré")
        sys.exit(0)

    analysis = load_orchestrator_result(
        "ts_2groups_normal.csv",
        AnalysisIntent(
            action="compare_groups",
            target_col="score",
            group_col="traitement",
            raw_query="Comparer le score entre les deux traitements",
        ),
        label="t-test 2 groupes",
    )
    if analysis.get("status") != "ok":
        print(f"\nÉCHEC : orchestrator status={analysis.get('status')!r}")
        sys.exit(1)

    interp = generate_interpretation(analysis)
    assert_json_serializable(interp, "interpretation")
    print_interpretation_summary(interp)

    if not interp.get("llm_available"):
        print(f"\nÉCHEC : llm_available=False — {interp.get('reason')}")
        sys.exit(1)

    levels = interp.get("interpretation_principale", {})
    for key in ("niveau_technique", "niveau_analytique", "niveau_decisionnel"):
        if not levels.get(key, "").strip():
            print(f"\nÉCHEC : niveau manquant ou vide : {key}")
            sys.exit(1)

    source_for_check = {
        "inference": analysis.get("inference", {}),
        "confidence_score": analysis.get("confidence_score", {}),
        "diagnosis": analysis.get("diagnosis", {}),
    }

    # Régressions déterministes (indépendantes de la variabilité du LLM live)
    reg_scientific = _validate_no_hallucinated_numbers(
        '{"niveau_technique": "p-value = 1e-06"}', source_for_check
    )
    if reg_scientific["nombres_suspects"] or reg_scientific["formats_anormaux"]:
        print(f"\nÉCHEC : faux positif notation scientifique : {reg_scientific}")
        sys.exit(1)

    reg_stat_comma = _validate_no_hallucinated_numbers(
        '{"niveau_technique": "statistic = -5,2792"}', source_for_check
    )
    if "-5,2792" in reg_stat_comma["nombres_suspects"]:
        print(f"\nÉCHEC : -5,2792 (stat réelle, virgule FR) flaggée à tort")
        sys.exit(1)

    reg_hallucination = _validate_no_hallucinated_numbers(
        '{"niveau_technique": "statistic = -7,3337"}', source_for_check
    )
    if "-7,3337" not in reg_hallucination["nombres_suspects"]:
        print(f"\nÉCHEC : -7,3337 (absent des sources) doit rester suspect : {reg_hallucination}")
        sys.exit(1)
    if "-7,3337" in reg_hallucination["formats_anormaux"]:
        print("\nÉCHEC : -7,3337 ne doit pas être classé en format anormal")
        sys.exit(1)

    check = interp.get("anti_hallucination_check", {})
    if "formats_anormaux_detectes" not in check:
        print("\nÉCHEC : champ formats_anormaux_detectes manquant")
        sys.exit(1)

    suspects = check.get("nombres_suspects_detectes", [])
    anomalous = check.get("formats_anormaux_detectes", [])
    if set(suspects) & set(anomalous):
        print(f"\nÉCHEC : chevauchement suspects/formats_anormaux")
        sys.exit(1)
    if suspects:
        print(
            f"\nNOTE : suspects live LLM = {suspects} "
            f"(peut refléter une vraie hallucination du modèle, ex. t=-7,3337 vs -5,2792 réel)"
        )

    print("\nOK : interprétation 3 niveaux générée, régressions anti-hallucination OK")
