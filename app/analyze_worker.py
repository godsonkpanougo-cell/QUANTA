#!/usr/bin/env python3
"""
Analyze Worker — exécuté en subprocess séparé.
Reçoit analysis_id, file_id, query en argv, exécute l'analyse complète,
et écrit le résultat en base de données via db.py.
Usage: python app/analyze_worker.py <analysis_id> <file_id> <query>
"""
import sys
import hashlib
from pathlib import Path
from typing import Any

# Ajouter le répertoire racine au PYTHONPATH pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration pour sortie non tamponnée
sys.stdout.reconfigure(line_buffering=True)

# Memory checkpoint (cross-platform)
def _mem_checkpoint(label: str) -> None:
    try:
        import resource
        mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(f"MEM CHECKPOINT [{label}] : {mb:.1f} Mo", flush=True)
    except (ImportError, AttributeError):
        # resource n'est pas disponible sur Windows
        print(f"MEM CHECKPOINT [{label}] : (non disponible sur cette plateforme)", flush=True)

def _now():
    """Timestamp ISO 8601."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

_mem_checkpoint("tout début fichier, avant imports")

# Imports locaux à ce worker (jamais partagés avec main.py)
import db
from app.compute import upload_validation
from app.compute import test_selector as ts
from app.llm import brain
from app.orchestrator import run_full_analysis

_mem_checkpoint("après imports lourds (orchestrator, brain, compute)")

def main():
    if len(sys.argv) < 4:
        print("Usage: python app/analyze_worker.py <analysis_id> <file_id> <query>", file=sys.stderr)
        sys.exit(1)

    analysis_id = sys.argv[1]
    file_id = sys.argv[2]
    query = sys.argv[3]

    _mem_checkpoint("début main")

    try:
        # Marquer le statut "running" en base
        db.update_analysis(analysis_id, status="running", updated_at=_now())
        audit_trail: list[dict[str, str]] = []

        upload_info = db.get_upload(file_id)
        if upload_info is None:
            db.update_analysis(
                analysis_id, status="error",
                error=f"file_id '{file_id}' introuvable -- le fichier a peut-être expiré ou n'a jamais été uploadé.",
                updated_at=_now(),
            )
            sys.exit(1)

        # Lire le fichier depuis le disque
        with open(upload_info["path"], "rb") as f:
            file_bytes = f.read()

        _mem_checkpoint("après chargement du fichier")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        filename = upload_info["filename"]
        n_rows = upload_info["n_rows"]
        n_cols = upload_info["n_cols"]
        numeric_cols = upload_info["numeric_cols"]
        cat_cols = upload_info["cat_cols"]

        # Détecter l'encodage CSV
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

        # Closure run_analysis_fn qui appelle run_full_analysis
        def run_analysis_fn(intent: ts.AnalysisIntent) -> dict[str, Any]:
            analysis = run_full_analysis(file_bytes, filename, intent, theme="dark")
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

        diagnosis = {
            "numeric_cols": numeric_cols,
            "cat_cols": cat_cols,
            "n_rows": n_rows,
            "n_cols": n_cols,
            "dataset_type": upload_info.get("dataset_type"),
            "id_cols": upload_info.get("id_cols", []),
        }

        # Appeler brain.analyze_with_brain
        result = brain.analyze_with_brain(
            user_query=query,
            available_numeric_cols=numeric_cols,
            available_cat_cols=cat_cols,
            run_analysis_fn=run_analysis_fn,
            diagnosis=diagnosis,
        )

        _mem_checkpoint("après brain.analyze_with_brain")

        result["file_hash"] = file_hash

        audit_trail.append({
            "timestamp": _now(),
            "etape": "Génération du rapport",
            "detail": "PDF généré avec succès",
        })
        result["audit_trail"] = audit_trail

        # Marquer le statut "done" en base
        db.update_analysis(analysis_id, status="done", result=result, updated_at=_now())

        print(f"ANALYZE Worker - Succès : analysis_id={analysis_id}", flush=True)
        sys.exit(0)

    except Exception as e:
        # Filet de sécurité : toute erreur non prévue est capturée et stockée en base
        import traceback
        error_msg = f"Erreur inattendue dans analyze_worker : {e}\n{traceback.format_exc()}"
        print(f"ANALYZE Worker - Erreur : {error_msg}", file=sys.stderr, flush=True)
        try:
            db.update_analysis(
                analysis_id, status="error",
                error=error_msg,
                updated_at=_now(),
            )
        except Exception as db_error:
            print(f"ANALYZE Worker - Erreur lors de l'écriture en base : {db_error}", file=sys.stderr, flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
