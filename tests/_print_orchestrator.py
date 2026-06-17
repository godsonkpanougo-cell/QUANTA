"""Affichage commun pour les scripts de test de l'orchestrateur."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.test_selector import AnalysisIntent
from app.orchestrator import run_full_analysis


def assert_json_serializable(result: dict[str, Any]) -> None:
    """Lève TypeError si le résultat n'est pas sérialisable en JSON."""
    json.dumps(result, ensure_ascii=False)


def _audit_steps(audit_log: list[dict[str, Any]]) -> list[str]:
    return [e.get("etape", "") for e in audit_log]


def run_orchestrator_sample(
    csv_name: str | None,
    intent: AnalysisIntent,
    *,
    label: str | None = None,
    file_bytes: bytes | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    if file_bytes is not None:
        data = file_bytes
        fname = filename or "inline.bin"
        source = fname
    else:
        if csv_name is None:
            raise ValueError("csv_name ou file_bytes requis")
        path = ROOT / "data" / "samples" / csv_name
        if not path.exists():
            raise FileNotFoundError(path)
        data = path.read_bytes()
        fname = path.name
        source = csv_name

    print("=" * 72)
    print(f"SOURCE : {source}" + (f" — {label}" if label else ""))
    print("=" * 72)
    print(f"INTENTION : action={intent.action!r}, target={intent.target_col!r}, "
          f"group={intent.group_col!r}, predictors={intent.predictor_cols}")

    result = run_full_analysis(data, fname, intent)
    assert_json_serializable(result)

    if result.get("status") == "failed" or "error" in result:
        print(f"\n--- ERREUR ---")
        print(f"status={result.get('status')}")
        print(f"error={result.get('error')}")
        print("\n--- JSON OK ---")
        return result

    print(f"\n--- STATUT ---")
    print(f"status={result['status']}")
    print(f"action_executed={result['inference']['action_executed']}")

    inf = result["inference"]["result"]
    if inf.get("test"):
        print(f"test={inf['test']}")
    if inf.get("status"):
        print(f"inference.status={inf['status']}")
    if inf.get("R2") is not None:
        print(f"R2={inf['R2']}")
    if inf.get("r") is not None:
        print(f"r={inf['r']}")

    conf = result.get("confidence_score", {})
    print(f"\n--- CONFIANCE ---")
    print(f"score_global={conf.get('score_global')}, niveau={conf.get('niveau')}")
    for note in conf.get("points_de_vigilance", []):
        print(f"  • {note}")

    steps = _audit_steps(result.get("audit_log", []))
    print(f"\n--- AUDIT_LOG ({len(steps)} entrées) ---")
    print(f"étapes : {steps}")

    print(f"\n--- JSON OK ---")
    print("json.dumps(result) : OK (sérialisation native garantie par orchestrator)")

    return result
