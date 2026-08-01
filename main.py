"""
QUANTA — main.py
API FastAPI exposant le pipeline complet (compute -> test_selector ->
orchestrator -> brain) au monde extérieur.

Asynchrone léger : BackgroundTasks de FastAPI, pas de Celery/Redis à ce
stade (décision du Jour 19 du programme -- inutile à la charge actuelle,
complexité non justifiée pour un MVP solo).

État des uploads et analyses persisté via db.py (SQLite, Jour 21 du
programme) -- survit aux redémarrages du serveur, contrairement au
stockage en mémoire pure utilisé dans une version antérieure de ce
fichier. Les fichiers uploadés eux-mêmes restent sur disque (pas en
base) ; seul leur chemin et leurs métadonnées sont en base.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

import db
from app.compute import compute
from app.compute import test_selector as ts
from app.llm import brain
from app.orchestrator import run_full_analysis
from app.report_generator import generate_pdf_report

load_dotenv(Path(__file__).resolve().parent / ".env")

app = FastAPI(title="QUANTA API", version="0.1.0")

# CORS : autoriser le frontend local pendant le développement. À restreindre
# au domaine de production réel avant le déploiement (Jour 61 du programme).
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


# ═══════════════════════════════════════════════════════════════════════════════
# STOCKAGE DES FICHIERS PHYSIQUES (les métadonnées sont en base via db.py)
# ═══════════════════════════════════════════════════════════════════════════════

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "quanta_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 Mo (limite Jour 61 du programme)
MAX_ROWS = 50_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# SCHÉMAS DE REQUÊTE
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyzeRequest(BaseModel):
    file_id: str
    query: str = ""

    @field_validator("query")
    @classmethod
    def query_optional(cls, value: str | None) -> str:
        """Requête libre optionnelle : vide => mode autonome (auto_intent)."""
        if value is None:
            return ""
        return value


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "quanta-api", "version": app.version}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Reçoit un fichier (CSV/Excel/Stata/SPSS), le sauvegarde temporairement,
    et retourne un diagnostic léger (colonnes disponibles par type) --
    utile pour que le frontend puisse, par exemple, suggérer des colonnes
    à l'utilisateur ou valider sa requête avant de lancer l'analyse.

    Ne lance PAS l'analyse complète ici -- seulement le chargement et la
    classification des colonnes (rapide), pour donner un retour immédiat.
    """
    raw_bytes = await file.read()

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux ({len(raw_bytes) / 1e6:.1f} Mo). "
                    f"Limite actuelle : {MAX_FILE_SIZE_BYTES / 1e6:.0f} Mo.",
        )

    filename = file.filename or "upload.bin"
    diag = compute.load_and_diagnose(raw_bytes, filename)

    if "error" in diag:
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier : {diag['error']}")

    if diag["n_rows"] > MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Dataset trop volumineux ({diag['n_rows']} lignes). "
                    f"Limite actuelle : {MAX_ROWS} lignes pour cette version.",
        )

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(saved_path, "wb") as f:
        f.write(raw_bytes)

    db.save_upload(file_id, {
        "path": saved_path,
        "filename": filename,
        "numeric_cols": diag["numeric_cols"],
        "cat_cols": diag["cat_cols"],
        "id_cols": diag.get("id_cols", []),
        "n_rows": diag["n_rows"],
        "n_cols": diag["n_cols"],
        "dataset_type": diag["dataset_type"],
        "uploaded_at": _now(),
    })

    return {
        "file_id": file_id,
        "filename": filename,
        "n_rows": diag["n_rows"],
        "n_cols": diag["n_cols"],
        "dataset_type": diag["dataset_type"],
        "numeric_cols": diag["numeric_cols"],
        "cat_cols": diag["cat_cols"],
    }


def _run_analysis_background(analysis_id: str, file_id: str, query: str) -> None:
    """
    Exécutée en arrière-plan par BackgroundTasks. Ne lève jamais d'exception
    vers l'extérieur -- toute erreur est capturée et stockée dans l'état de
    l'analyse, consultable via /status.
    """
    try:
        db.update_analysis(analysis_id, status="running", updated_at=_now())
        audit_trail: list[dict[str, str]] = []

        upload_info = db.get_upload(file_id)
        if upload_info is None:
            db.update_analysis(
                analysis_id, status="error",
                error=f"file_id '{file_id}' introuvable -- le fichier a peut-être expiré ou n'a jamais été uploadé.",
                updated_at=_now(),
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
            encoding = compute._detect_csv_encoding(file_bytes)
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

        def run_analysis_fn(intent: ts.AnalysisIntent) -> dict[str, Any]:
            analysis = run_full_analysis(file_bytes, filename, intent)
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

        db.update_analysis(analysis_id, status="done", result=result, updated_at=_now())

    except Exception as e:
        # Filet de sécurité ultime : même une erreur totalement imprévue ne
        # doit jamais laisser l'analyse bloquée en "running" indéfiniment.
        db.update_analysis(
            analysis_id, status="error",
            error=f"Erreur inattendue pendant l'analyse : {e}",
            updated_at=_now(),
        )


@app.post("/analyze")
def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    """
    Lance une analyse en arrière-plan et retourne immédiatement un
    analysis_id. Le frontend doit ensuite poller GET /status/{analysis_id}
    jusqu'à obtenir le statut "done" ou "error".
    """
    if not db.upload_exists(request.file_id):
        raise HTTPException(
            status_code=404,
            detail=f"file_id '{request.file_id}' introuvable. Uploadez d'abord un fichier via /upload.",
        )

    analysis_id = str(uuid.uuid4())
    db.create_analysis(analysis_id, request.file_id, request.query, _now())

    background_tasks.add_task(_run_analysis_background, analysis_id, request.file_id, request.query)

    return {"analysis_id": analysis_id, "status": "pending"}


@app.get("/status/{analysis_id}")
def get_status(analysis_id: str) -> dict[str, Any]:
    """
    Statut d'une analyse en cours ou terminée. Le frontend poll cet
    endpoint toutes les 2-3 secondes (Jour 28 du programme).
    """
    analysis = db.get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"analysis_id '{analysis_id}' introuvable.")

    response: dict[str, Any] = {
        "analysis_id": analysis_id,
        "status": analysis["status"],
        "created_at": analysis.get("created_at"),
    }

    if analysis["status"] == "done":
        response["result"] = analysis["result"]
    elif analysis["status"] == "error":
        response["error"] = analysis["error"]

    return response


@app.get("/history")
def get_history() -> dict[str, Any]:
    """
    Liste légère des analyses passées (sans le détail complet des résultats)
    -- maintenant persistée via SQLite (db.py), survit aux redémarrages
    du serveur.
    """
    items = db.list_analyses(limit=100)
    return {"count": len(items), "analyses": items}


@app.get("/report/{analysis_id}")
def get_report(
    analysis_id: str,
    theme: str = "dark",
) -> Response:
    """
    Télécharge le rapport PDF d'une analyse terminée.
    Query param optionnel : theme=dark|light (défaut dark).
    Exemple : /report/{id}?theme=light
    """
    analysis = db.get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"analysis_id '{analysis_id}' introuvable.",
        )

    if analysis["status"] != "done":
        raise HTTPException(
            status_code=400,
            detail=(
                f"L'analyse n'est pas terminée (statut actuel : "
                f"'{analysis['status']}'). Attendez le statut 'done' "
                f"avant de demander le rapport PDF."
            ),
        )

    result = analysis.get("result")
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Résultat d'analyse invalide ou absent — génération du PDF impossible.",
        )

    theme_norm = (theme or "dark").strip().lower()
    if theme_norm not in {"dark", "light"}:
        theme_norm = "dark"

    pdf_bytes = generate_pdf_report(result, theme=theme_norm)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=500,
            detail="Échec de la génération du rapport PDF.",
        )

    suffix = "academique" if theme_norm == "light" else "dark"
    filename = f"rapport_quanta_{suffix}_{analysis_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# Note : pas de nettoyage automatique des fichiers à l'arrêt du serveur --
# ce serait contradictoire avec l'objectif de persistance via SQLite. Un
# vrai mécanisme d'expiration/nettoyage périodique (ex: fichiers de plus
# de 30 jours) est prévu pour une itération ultérieure, pas en V1.
