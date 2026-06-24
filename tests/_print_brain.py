"""Affichage et helpers communs pour les scripts de test brain.py."""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.compute import compute
from app.compute.test_selector import AnalysisIntent
from app.llm.brain import analyze_with_brain, generate_interpretation, text_to_intent
from app.orchestrator import run_full_analysis

REGION_LIKERT_SAMPLE = "region_likert.csv"
MIXED_CATEGORICAL_SAMPLE = "mixed_categorical.csv"


def assert_json_serializable(result: dict[str, Any], label: str = "result") -> None:
    """Lève TypeError si le résultat n'est pas sérialisable en JSON."""
    json.dumps(result, ensure_ascii=False)
    print(f"json.dumps({label}) : OK")


def llm_is_configured() -> bool:
    """True si au moins un provider LLM a une clé API renseignée."""
    keys = (
        os.environ.get("PRIMARY_API_KEY", ""),
        os.environ.get("GROQ_API_KEY", ""),
        os.environ.get("FALLBACK_API_KEY", ""),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )
    return any(k and k.strip() for k in keys)


@contextmanager
def llm_keys_disabled() -> Iterator[None]:
    """Désactive temporairement toutes les clés LLM pour les tests de repli."""
    env_keys = (
        "PRIMARY_API_KEY",
        "GROQ_API_KEY",
        "FALLBACK_API_KEY",
        "OPENROUTER_API_KEY",
    )
    saved = {k: os.environ.get(k) for k in env_keys}
    try:
        for k in env_keys:
            os.environ[k] = ""
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def load_sample_columns(csv_name: str) -> tuple[list[str], list[str]]:
    """Charge numeric_cols et cat_cols via le pipeline compute de base."""
    path = ROOT / "data" / "samples" / csv_name
    if not path.exists():
        raise FileNotFoundError(path)
    pipeline = compute.run_base_compute_pipeline(path.read_bytes(), path.name)
    if "error" in pipeline:
        raise RuntimeError(pipeline["error"])
    return pipeline["numeric_cols"], pipeline["cat_cols"]


def load_orchestrator_result(
    csv_name: str,
    intent: AnalysisIntent,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    """Exécute run_full_analysis sur un échantillon et vérifie la sérialisation JSON."""
    path = ROOT / "data" / "samples" / csv_name
    print("=" * 72)
    print(f"ORCHESTRATOR : {csv_name}" + (f" — {label}" if label else ""))
    print("=" * 72)
    result = run_full_analysis(path.read_bytes(), path.name, intent)
    assert_json_serializable(result, "analysis_result")
    return result


def print_intent(intent: AnalysisIntent) -> None:
    print(
        f"action={intent.action!r}, target={intent.target_col!r}, "
        f"group={intent.group_col!r}, predictors={intent.predictor_cols}"
    )


def print_interpretation_summary(interp: dict[str, Any]) -> None:
    print(f"\n--- INTERPRÉTATION ---")
    print(f"llm_available={interp.get('llm_available')}")
    if not interp.get("llm_available"):
        print(f"reason={interp.get('reason', '')[:120]}...")
        print(f"raw_analysis.status={interp.get('raw_analysis', {}).get('status')}")
        return

    levels = interp.get("interpretation_principale", {})
    for key in ("niveau_technique", "niveau_analytique", "niveau_decisionnel"):
        text = levels.get(key, "")
        preview = (text[:120] + "...") if len(text) > 120 else text
        print(f"  {key}: {preview}")

    check = interp.get("anti_hallucination_check", {})
    suspects = check.get("nombres_suspects_detectes", [])
    anomalous = check.get("formats_anormaux_detectes", [])
    print(f"  nombres_suspects_detectes={suspects}")
    print(f"  formats_anormaux_detectes={anomalous}")
    if check.get("avertissement"):
        print(f"  avertissement={check['avertissement']}")
