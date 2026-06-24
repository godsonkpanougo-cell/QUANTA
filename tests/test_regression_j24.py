"""
BILAN J24 — Non-régression massif via l'API HTTP (requests).

Prérequis : serveur lancé séparément :
    cd QUANTA && uvicorn main:app --reload --port 8000

Commande :
    python -m tests.test_regression_j24

Variable d'environnement optionnelle : QUANTA_API_URL (défaut http://127.0.0.1:8000)
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get("QUANTA_API_URL", "http://127.0.0.1:8000").rstrip("/")
POLL_INTERVAL_S = 2
POLL_TIMEOUT_S = 60

# Dataset -> requête naturelle adaptée au contenu
CASES: list[tuple[str, str]] = [
    ("clean.csv", "corrélation entre age et income"),
    ("missing_15pct.csv", "analyser la corrélation entre age et income"),
    ("outliers_extreme.csv", "analyser les relations entre revenue, cost et profit"),
    ("region_likert.csv", "comparer le revenu entre régions"),
    ("small_sample.csv", "corrélation entre weight et height"),
    ("large_sample.csv", "régression de productivity sur age et years_exp"),
    ("with_duplicates.csv", "statistiques descriptives sur age et salary"),
    ("mixed_categorical.csv", "comparer le salaire entre départements"),
    ("ts_2groups_normal.csv", "comparer le score entre les deux traitements"),
    ("ts_2groups_nonnormal.csv", "comparer le délai entre les deux groupes"),
    ("ts_logistic_binary.csv", "prédire le diabète à partir de l'âge et de l'IMC"),
    ("ts_assoc_fisher.csv", "analyser l'association entre exposition et maladie"),
]


def llm_is_configured() -> bool:
    keys = (
        os.environ.get("PRIMARY_API_KEY", ""),
        os.environ.get("GROQ_API_KEY", ""),
        os.environ.get("FALLBACK_API_KEY", ""),
        os.environ.get("OPENROUTER_API_KEY", ""),
    )
    return any(k and k.strip() for k in keys)


def sample_path(name: str) -> Path:
    path = ROOT / "data" / "samples" / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


@dataclass
class CaseResult:
    dataset: str
    passed: bool = False
    status: str = "—"
    action_executed: str = "—"
    confidence_score: str = "—"
    llm_available: str = "—"
    json_ok: str = "—"
    errors: list[str] = field(default_factory=list)


def _check_server() -> None:
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(
            f"\nÉCHEC : serveur inaccessible sur {BASE_URL}\n"
            f"  Lancez : uvicorn main:app --reload --port 8000\n"
            f"  Détail : {exc}"
        )
        sys.exit(1)
    data = resp.json()
    if data.get("status") != "ok":
        print(f"\nÉCHEC : /health inattendu : {data}")
        sys.exit(1)


def _upload(session: requests.Session, csv_name: str) -> dict[str, Any]:
    path = sample_path(csv_name)
    with path.open("rb") as f:
        resp = session.post(
            f"{BASE_URL}/upload",
            files={"file": (path.name, f, "text/csv")},
            timeout=30,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"POST /upload -> {resp.status_code}: {resp.text}")
    return resp.json()


def _analyze(session: requests.Session, file_id: str, query: str) -> str:
    resp = session.post(
        f"{BASE_URL}/analyze",
        json={"file_id": file_id, "query": query},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"POST /analyze -> {resp.status_code}: {resp.text}")
    data = resp.json()
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        raise RuntimeError(f"POST /analyze sans analysis_id : {data}")
    return analysis_id


def _poll_status(session: requests.Session, analysis_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        resp = session.get(f"{BASE_URL}/status/{analysis_id}", timeout=10)
        if resp.status_code != 200:
            raise RuntimeError(f"GET /status -> {resp.status_code}: {resp.text}")
        data = resp.json()
        status = data.get("status")
        if status in ("done", "error"):
            return data
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(
        f"Timeout {POLL_TIMEOUT_S}s — analysis_id={analysis_id} toujours en cours"
    )


def _validate_result(status_payload: dict[str, Any]) -> list[str]:
    """Retourne la liste des erreurs de validation (vide = OK)."""
    errors: list[str] = []

    if status_payload.get("status") != "done":
        errors.append(
            f"status API={status_payload.get('status')!r} "
            f"(error={status_payload.get('error')!r})"
        )
        return errors

    result = status_payload.get("result")
    if not isinstance(result, dict):
        errors.append("result absent ou non-dict")
        return errors

    try:
        json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        errors.append(f"json.dumps(result) échoue : {exc}")
        return errors

    analysis = result.get("analysis", {})
    if analysis.get("status") != "ok":
        errors.append(f"analysis.status={analysis.get('status')!r}")

    inference = analysis.get("inference", {})
    action = inference.get("action_executed")
    if action is None:
        errors.append("inference.action_executed est None")

    confidence = analysis.get("confidence_score", {})
    score = confidence.get("score_global")
    if not isinstance(score, (int, float)) or score <= 0:
        errors.append(f"confidence_score.score_global invalide : {score!r}")

    interpretation = result.get("interpretation", {})
    llm_avail = interpretation.get("llm_available")
    if not isinstance(llm_avail, bool):
        errors.append(f"interpretation.llm_available non booléen : {llm_avail!r}")

    return errors


def _run_case(
    session: requests.Session,
    dataset: str,
    query: str,
) -> CaseResult:
    out = CaseResult(dataset=dataset)
    try:
        upload_data = _upload(session, dataset)
        file_id = upload_data["file_id"]
        analysis_id = _analyze(session, file_id, query)
        status_payload = _poll_status(session, analysis_id)

        out.status = str(status_payload.get("status", "—"))

        result = status_payload.get("result") or {}
        analysis = result.get("analysis", {}) if isinstance(result, dict) else {}
        inference = analysis.get("inference", {})
        confidence = analysis.get("confidence_score", {})
        interpretation = result.get("interpretation", {}) if isinstance(result, dict) else {}

        out.action_executed = str(inference.get("action_executed", "—"))
        score = confidence.get("score_global")
        out.confidence_score = str(score) if score is not None else "—"
        llm_avail = interpretation.get("llm_available")
        out.llm_available = str(llm_avail) if isinstance(llm_avail, bool) else "—"

        try:
            json.dumps(result, ensure_ascii=False)
            out.json_ok = "Oui"
        except (TypeError, ValueError):
            out.json_ok = "Non"

        out.errors = _validate_result(status_payload)
        out.passed = len(out.errors) == 0

    except Exception as exc:
        out.errors.append(str(exc))
        out.passed = False

    return out


def _print_summary_table(results: list[CaseResult]) -> None:
    headers = ("Dataset", "Status", "Action exécutée", "Score confiance", "LLM dispo", "JSON OK")
    rows = [
        (
            r.dataset,
            r.status,
            r.action_executed,
            r.confidence_score,
            r.llm_available,
            r.json_ok,
        )
        for r in results
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    sep = "-+-".join("-" * w for w in widths)
    print()
    print(fmt_row(headers))
    print(sep)
    for row in rows:
        print(fmt_row(row))
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    llm_cfg = llm_is_configured()
    print("=" * 72)
    print("BILAN J24 — Non-régression API HTTP (requests)")
    print(f"Base URL      : {BASE_URL}")
    print(f"LLM configuré : {llm_cfg}")
    print(f"Datasets      : {len(CASES)}")
    print("=" * 72)

    _check_server()

    session = requests.Session()
    results: list[CaseResult] = []

    for i, (dataset, query) in enumerate(CASES, start=1):
        print(f"\n[{i}/{len(CASES)}] {dataset}")
        print(f"  query : {query!r}")
        case = _run_case(session, dataset, query)
        results.append(case)
        if case.passed:
            print(
                f"  OK — action={case.action_executed}, "
                f"score={case.confidence_score}, llm={case.llm_available}"
            )
        else:
            for err in case.errors:
                print(f"  ÉCHEC : {err}")

    _print_summary_table(results)

    failed = [r for r in results if not r.passed]
    if not failed:
        print("✅ BILAN J24 : MOIS 1 VALIDÉ — Passage au Mois 2 autorisé.")
        return 0

    print("❌ BILAN J24 : ÉCHECS DÉTECTÉS — Mois 1 non validé.")
    print("\nCas en échec :")
    for r in failed:
        print(f"  • {r.dataset}")
        for err in r.errors:
            print(f"      - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
