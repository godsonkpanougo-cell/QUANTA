"""
Génère des PDF de prévisualisation (thèmes dark + light) à partir d'une
analyse ACP réelle — pour inspection visuelle du design system QUANTA.

Usage : ./venv/Scripts/python scripts/gen_preview_reports.py
Sortie : "rapports quanta/preview_report_dark.pdf" / "preview_report_light.pdf"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from app.compute.compute import run_acp  # noqa: E402
from app.report_generator import generate_pdf_report  # noqa: E402

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rapports quanta",
)


def build_analysis_result() -> dict:
    df = pd.read_csv("tests/test_acp_numeric_id.csv")
    numeric_cols = ["SUP_HA", "Rendement", "Production"]
    acp_result = run_acp(df, numeric_cols)
    if acp_result.get("status") != "ok":
        raise RuntimeError(f"ACP en échec : {acp_result.get('error')}")

    return {
        "filename": "exploitation_agricoles_2026.csv",
        "file_hash": (
            "3f7a1c9e2b8d46f0a5c3e7194d2b8f6a"
            "1c9e2b8d46f0a5c3e7194d2b8f6a3f7a"
        ),
        "intent": {"action": "acp", "target": None, "group": None},
        "analysis": {
            "diagnosis": {
                "n_rows": int(len(df)),
                "n_cols": int(len(df.columns)),
                "dataset_type": "Numérique",
                "numeric_cols": numeric_cols,
                "cat_cols": ["Region"],
                "id_cols": ["ID"],
                "missing": {},
                "missing_pct": {},
                "descriptive_stats": {
                    "numeric": {
                        col: {
                            "mean": round(float(df[col].mean()), 3),
                            "median": round(float(df[col].median()), 3),
                            "std": round(float(df[col].std()), 3),
                            "min": round(float(df[col].min()), 3),
                            "max": round(float(df[col].max()), 3),
                            "skewness": round(float(df[col].skew()), 3),
                            "kurtosis": round(float(df[col].kurt()), 3),
                            "missing_pct": 0.0,
                        }
                        for col in numeric_cols
                    },
                    "categorical": {
                        "Region": {
                            "mode": str(df["Region"].mode().iloc[0]),
                            "frequencies": {
                                str(k): int(v)
                                for k, v in df["Region"].value_counts().items()
                            },
                            "percentages": {
                                str(k): round(float(v), 2)
                                for k, v in (
                                    df["Region"].value_counts(normalize=True) * 100
                                ).items()
                            },
                            "missing_pct": 0.0,
                        }
                    },
                },
            },
            "confidence_score": {
                "score_global": 78.4,
                "niveau": "Élevé",
                "points_de_vigilance": [
                    "Effectif modéré : les résultats d'ACP restent sensibles "
                    "aux observations atypiques.",
                    "Variables fortement corrélées : interpréter les axes "
                    "avec prudence.",
                ],
            },
            "inference": {"result": {"acp": acp_result}},
        },
        "interpretation": {
            "interpretation_principale": {
                "niveau_technique": (
                    "L'ACP sur 3 variables numériques extrait 2 composantes "
                    "captant l'essentiel de la variance. Le premier axe oppose "
                    "les exploitations extensives (grande superficie, fort "
                    "rendement) aux structures intensives."
                ),
                "niveau_analytique": (
                    "La structure de corrélation entre superficie, rendement "
                    "et production s'organise autour d'un gradient "
                    "d'intensification. Les individus se répartissent en deux "
                    "régimes distincts sur le plan factoriel."
                ),
                "niveau_decisionnel": (
                    "Pour cibler des politiques de soutien, distinguer les "
                    "deux régimes identifiés : les exploitations extensives "
                    "répondent mieux aux subventions foncières, les "
                    "intensives aux incitations à la productivité."
                ),
            },
            "resume_executif": (
                "L'analyse en composantes principales révèle deux régimes "
                "agricoles nettement séparés. Le premier axe (72 % de la "
                "variance) capture l'opposition entre extensive et intensive ; "
                "le second axe distingue le rendement de la production brute. "
                "Confiance élevée, sous réserve de l'effectif."
            ),
        },
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    analysis_result = build_analysis_result()

    for theme in ("dark", "light"):
        pdf = generate_pdf_report(analysis_result, theme=theme)
        out = os.path.join(OUT_DIR, f"preview_report_{theme}.pdf")
        with open(out, "wb") as fh:
            fh.write(pdf)
        print(f"OK {theme}: {out} ({len(pdf) / 1024:.1f} Ko)")


if __name__ == "__main__":
    main()
