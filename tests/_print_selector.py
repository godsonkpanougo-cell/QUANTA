"""Affichage commun pour les scripts de test du sélecteur de tests statistiques."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.compute import run_base_compute_pipeline
from app.compute.test_selector import AnalysisIntent, select_and_run_test


def assert_json_serializable(result: dict[str, Any]) -> None:
    """Lève TypeError si le résultat n'est pas sérialisable en JSON."""
    json.dumps(result, ensure_ascii=False)


def _pp(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def run_selector_sample(
    csv_name: str,
    intent: AnalysisIntent,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    path = ROOT / "data" / "samples" / csv_name
    if not path.exists():
        raise FileNotFoundError(path)

    print("=" * 72)
    print(f"FICHIER : {csv_name}" + (f" — {label}" if label else ""))
    print("=" * 72)
    print(f"INTENTION : action={intent.action!r}, target={intent.target_col!r}, "
          f"group={intent.group_col!r}, predictors={intent.predictor_cols}")

    pipeline = run_base_compute_pipeline(path.read_bytes(), path.name)
    if "error" in pipeline:
        print("ERREUR PIPELINE :", pipeline["error"])
        return {"pipeline_error": pipeline["error"]}

    diag = pipeline["diagnosis"]
    print(f"\n--- DATASET (post-pipeline) ---")
    print(f"id_cols={diag.get('id_cols', [])}")
    print(f"numeric_cols={pipeline['numeric_cols']}")
    print(f"cat_cols={pipeline['cat_cols']}")

    output = select_and_run_test(
        intent,
        pipeline["dataframe_clean"],
        pipeline["numeric_cols"],
        pipeline["cat_cols"],
        diag.get("id_cols", []),
        pipeline.get("normality", {}),
    )

    assert_json_serializable(output)

    print(f"\n--- ACTION EXÉCUTÉE ---")
    print(f"action_executed={output['action_executed']}")

    if output["validation_issues"]:
        print(f"\n--- VALIDATION_ISSUES ({len(output['validation_issues'])}) ---")
        for issue in output["validation_issues"]:
            print(f"  [{issue['champ']}] {issue['probleme']}")

    print(f"\n--- AUDIT_LOG ---")
    for entry in output["audit_log"]:
        print(
            f"  [{entry['etape']}] col={entry['colonne']} "
            f"-> {entry['decision']} | {entry['justification']}"
        )

    result = output["result"]
    print(f"\n--- RÉSULTAT DU TEST ---")
    print(f"status={result.get('status')}")
    if result.get("test"):
        print(f"test={result['test']}")
    if result.get("p_value") is not None:
        print(f"p_value={result['p_value']}")
    if result.get("reason"):
        print(f"reason={result['reason']}")
    if result.get("posthoc") is not None:
        print(f"posthoc présent : {type(result['posthoc']).__name__}")

    print(f"\n--- JSON OK ---")
    print("json.dumps(result) : OK (sérialisation native garantie par test_selector)")

    return output
