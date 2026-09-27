"""
QUANTA — analysis_core.py
Logique d'analyse partagée entre le worker subprocess (analyze_worker.py)
et le fallback in-memory de main.py (_run_analysis_core).

Historique : ce code existait en deux copies quasi identiques (~150 lignes
chacune) dans main.py et analyze_worker.py. Divergences dangereuses : la
copie worker vérifiait l'annulation avant chaque intent, pas la copie
fallback -> un /cancel pendant une analyse de fallback était ignoré.
Cette version unique garantit :
  - la vérification d'annulation AVANT CHAQUE intent (callback fourni) ;
  - le journal d'audit horodaté identique dans les deux modes ;
  - un seul endroit à corriger pour toute évolution du pipeline.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

import db
from app.compute import upload_validation
from app.compute import test_selector as ts
from app.llm import brain
from app.orchestrator import run_full_analysis


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_analysis(
    analysis_id: str,
    user_id: str,
    file_id: str,
    query: str,
    check_cancelled: Callable[[], bool] | None = None,
) -> None:
    """
    Exécute l'analyse complète pour une analyse déjà créée en base
    (statut 'pending' attendu). Met à jour le statut en base :
    'running' -> 'done' (résultat complet) ou 'error' (message).

    check_cancelled : callback optionnel appelé avant chaque intent.
    S'il retourne True, l'analyse est marquée 'cancelled' et l'exécution
    s'arrête immédiatement (levée de CancelledAnalysis, à intercepter par
    l'appelant pour distinguer annulation propre et erreur).

    Lève toute exception non gérée -- la couche appelante (background task
    ou worker) est responsable du filet de sécurité ultime. En cas
    d'annulation, lève analysis_core.CancelledAnalysis après avoir écrit
    le statut 'cancelled' en base.
    """
    class CancelledAnalysis(Exception):
        """Levée quand l'utilisateur a annulé l'analyse (statut 'cancelled')."""
        pass

    def _raise_if_cancelled() -> None:
        if check_cancelled is not None and check_cancelled():
            db.update_analysis(
                analysis_id,
                status="cancelled",
                error="Analyse annulée par l'utilisateur",
                updated_at=_now(),
                user_id=user_id,
            )
            raise CancelledAnalysis()

    _raise_if_cancelled()
    db.update_analysis(analysis_id, status="running", updated_at=_now(), user_id=user_id)

    audit_trail: list[dict[str, str]] = []

    upload_info = db.get_upload(file_id, user_id)
    if upload_info is None:
        db.update_analysis(
            analysis_id, status="error",
            error=f"file_id '{file_id}' introuvable -- le fichier a peut-être expiré ou n'a jamais été uploadé.",
            updated_at=_now(),
            user_id=user_id,
        )
        return

    with open(upload_info["path"], "rb") as f:
        file_bytes = f.read()

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    filename = upload_info["filename"]
    n_rows = upload_info["n_rows"]
    n_cols = upload_info["n_cols"]
    numeric_cols = upload_info["numeric_cols"]
    cat_cols = upload_info["cat_cols"]

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        encoding = upload_validation._detect_csv_encoding(file_bytes)
    elif ext in {"xls", "xlsx", "dta", "sav"}:
        encoding = f"n/a ({ext})"
    else:
        encoding = "inconnu"

    audit_trail.append({
        "timestamp": _now(),
        "etape": "Chargement du fichier",
        "detail": (
            f"{n_rows} lignes, {n_cols} colonnes, encodage {encoding}"
        ),
    })
    audit_trail.append({
        "timestamp": _now(),
        "etape": "Diagnostic structurel",
        "detail": (
            f"{len(numeric_cols)} variables numériques, "
            f"{len(cat_cols)} catégorielles"
        ),
    })

    def run_analysis_fn(intent: ts.AnalysisIntent, base_pipeline: dict[str, Any] | None = None) -> dict[str, Any]:
        # Vérifier l'annulation AVANT CHAQUE intent -- comportement historique
        # du worker subprocess, désormais partagé avec le fallback in-memory.
        _raise_if_cancelled()

        analysis = run_full_analysis(
            file_bytes, filename, intent, theme="dark",
            base_pipeline=base_pipeline,
        )
        # Journaliser chaque test lancé (appelé 1× en mode query, N× en auto).
        inference = analysis.get("inference") if isinstance(analysis, dict) else None
        if isinstance(inference, dict):
            test_result = inference.get("result")
            test_name = None
            if isinstance(test_result, dict):
                test_name = test_result.get("test") or test_result.get("method")
            action = inference.get("action_executed")
            p_value = (
                test_result.get("p_value")
                if isinstance(test_result, dict)
                else None
            )
            label = test_name or action or intent.action or "test"
            detail_parts = [f"action={action or intent.action}"]
            if intent.target_col:
                detail_parts.append(f"target={intent.target_col}")
            if intent.group_col:
                detail_parts.append(f"group={intent.group_col}")
            if p_value is not None:
                detail_parts.append(f"p={p_value}")
            audit_trail.append({
                "timestamp": _now(),
                "etape": f"Test : {label}",
                "detail": ", ".join(detail_parts),
            })
        return analysis

    # Attributs exposés à brain.analyze_with_brain (mode autonome) : le
    # précalcul du pipeline de base lit run_analysis_fn.file_bytes / .filename
    # pour construire UNE fois le pipeline réutilisé par tous les intents.
    run_analysis_fn.file_bytes = file_bytes      # type: ignore[attr-defined]
    run_analysis_fn.filename = filename          # type: ignore[attr-defined]

    diagnosis = {
        "numeric_cols": numeric_cols,
        "cat_cols": cat_cols,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "dataset_type": upload_info.get("dataset_type"),
        "id_cols": upload_info.get("id_cols", []),
    }

    result = brain.analyze_with_brain(
        user_query=query,
        available_numeric_cols=numeric_cols,
        available_cat_cols=cat_cols,
        run_analysis_fn=run_analysis_fn,
        diagnosis=diagnosis,
    )
    result["file_hash"] = file_hash

    audit_trail.append({
        "timestamp": _now(),
        "etape": "Génération du rapport",
        "detail": "PDF généré avec succès",
    })
    result["audit_trail"] = audit_trail

    db.update_analysis(
        analysis_id, status="done", result=result,
        updated_at=_now(), user_id=user_id, file_hash=file_hash,
    )
