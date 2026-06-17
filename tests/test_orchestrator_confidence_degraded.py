"""Test orchestrateur : score de confiance sur dataset dégradé (petit n)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    intent_clean = AnalysisIntent(
        action="correlation",
        target_col="age",
        group_col="income",
        raw_query="Corrélation de référence sur dataset propre",
    )
    intent_degraded = AnalysisIntent(
        action="correlation",
        target_col="age",
        group_col="weight",
        raw_query="Corrélation exploratoire sur petit échantillon",
    )

    clean = run_orchestrator_sample("clean.csv", intent_clean, label="référence propre")
    degraded = run_orchestrator_sample("small_sample.csv", intent_degraded, label="dataset dégradé n=25")
    clean_path = Path(__file__).resolve().parents[1] / "data" / "samples" / "clean.csv"
    n95_bytes = (
        pd.read_csv(clean_path)
        .head(95)
        .to_csv(index=False)
        .encode("utf-8")
    )
    n95 = run_orchestrator_sample(
        None,
        intent_clean,
        label="échantillon intermédiaire n=95",
        file_bytes=n95_bytes,
        filename="clean_n95.csv",
    )

    if clean.get("status") != "ok" or degraded.get("status") != "ok" or n95.get("status") != "ok":
        print("\nÉCHEC : un des pipelines a échoué")
        sys.exit(1)

    score_clean = clean["confidence_score"]["score_global"]
    score_degraded = degraded["confidence_score"]["score_global"]
    vigilance = degraded["confidence_score"]["points_de_vigilance"]
    niveau_degraded = degraded["confidence_score"]["niveau"]
    niveau_degraded_brut = degraded["confidence_score"]["niveau_brut_avant_plafond"]
    niveau_clean_brut = clean["confidence_score"]["niveau_brut_avant_plafond"]
    niveau_n95 = n95["confidence_score"]["niveau"]
    niveau_n95_brut = n95["confidence_score"]["niveau_brut_avant_plafond"]

    if score_degraded >= score_clean:
        print(f"\nÉCHEC : score dégradé ({score_degraded}) >= score propre ({score_clean})")
        sys.exit(1)
    if niveau_degraded != "Faible":
        print(f"\nÉCHEC : n=25 doit être plafonné à 'Faible' (obtenu={niveau_degraded})")
        sys.exit(1)
    if niveau_degraded_brut != "Élevé":
        print(
            "\nÉCHEC : n=25 doit conserver la trace du niveau brut "
            f"'Élevé' avant plafond (obtenu={niveau_degraded_brut})"
        )
        sys.exit(1)
    if niveau_clean_brut is not None:
        print(
            "\nÉCHEC : n=100 ne doit pas être plafonné "
            f"(niveau_brut_avant_plafond attendu=None, obtenu={niveau_clean_brut})"
        )
        sys.exit(1)
    if niveau_n95 != "Modéré":
        print(f"\nÉCHEC : n=95 doit être plafonné à 'Modéré' (obtenu={niveau_n95})")
        sys.exit(1)
    if niveau_n95_brut != "Élevé":
        print(
            "\nÉCHEC : n=95 doit conserver la trace du niveau brut "
            f"'Élevé' avant plafond (obtenu={niveau_n95_brut})"
        )
        sys.exit(1)
    if not any("petit" in n.lower() or "n=25" in n.lower() for n in vigilance):
        print(f"\nÉCHEC : points_de_vigilance sans mention du petit échantillon : {vigilance}")
        sys.exit(1)

    print(
        "\nOK : score propre="
        f"{score_clean}, dégradé={score_degraded}, plafonds n=25/n=95 validés, "
        "vigilance pertinente"
    )
