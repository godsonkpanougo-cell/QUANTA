"""Affichage commun pour les scripts de test du pipeline compute."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.compute import run_base_compute_pipeline


def _pp(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def run_sample(csv_name: str, target_col: str | None = None) -> dict:
    path = ROOT / "data" / "samples" / csv_name
    if not path.exists():
        raise FileNotFoundError(path)

    print("=" * 72)
    print(f"FICHIER : {csv_name}")
    print("=" * 72)

    result = run_base_compute_pipeline(path.read_bytes(), path.name, target_col=target_col)

    if "error" in result:
        print("ERREUR PIPELINE :", result["error"])
        return result

    diag = result["diagnosis"]
    print("\n--- DIAGNOSIS ---")
    print(f"n_rows={diag['n_rows']}, n_cols={diag['n_cols']}, dataset_type={diag['dataset_type']}")
    print(f"id_cols={diag.get('id_cols', [])}")
    print(f"numeric_cols={diag['numeric_cols']}")
    print(f"cat_cols={diag['cat_cols']}")
    print(f"reclassified_as_categorical={_pp(diag.get('reclassified_as_categorical', {}))}")
    if diag.get("missing_pct"):
        print(f"missing_pct={_pp(diag['missing_pct'])}")
    if diag.get("outlier_counts"):
        print(f"outlier_counts={_pp(diag['outlier_counts'])}")
    print(f"n_duplicates={diag.get('n_duplicates')}")

    print("\n--- CLEANING audit_log ---")
    for entry in result["cleaning"].get("audit_log", []):
        print(
            f"  [{entry['etape']}] col={entry['colonne']} "
            f"-> {entry['decision']} | {entry['justification']}"
        )

    print("\n--- NORMALITY (conclusions) ---")
    for col, info in result.get("normality", {}).items():
        print(f"  {col}: n={info.get('n')} -> {info.get('conclusion')} ({info.get('methode_decision')})")

    print("\n--- REGRESSION ---")
    reg = result.get("regression", {})
    print(f"  status={reg.get('status')}")
    if reg.get("reason"):
        print(f"  reason={reg['reason']}")
    if reg.get("status") == "ok":
        print(f"  R2={reg.get('R2')}, n_obs={reg.get('n_obs')}")

    return result
