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

import os
import re
import sys
import uuid
import base64
import io
import tempfile
import logging
import threading
import hashlib
import subprocess
import json

# Configuration du logging pour rendre les logs TIMING visibles en production
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Any

# Forcer le backend matplotlib Agg AVANT toute importation
os.environ['MPLBACKEND'] = 'Agg'

from dotenv import load_dotenv

# LOG DE DÉMARRAGE POUR CONFIRMER LA VERSION
print("=" * 60)
print("QUANTA STARTUP - VERSION WITH MATPLOTLIB FIX")
print("Matplotlib backend forced: Agg")
print("=" * 60)
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import Response
from fastapi import Cookie, Depends
from pydantic import BaseModel, StringConstraints, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.background import BackgroundScheduler

import db
from app.compute import upload_validation
from app.compute import test_selector as ts
from app.llm import brain
from app.orchestrator import run_full_analysis
from app import analysis_core
from app import auth


# ═══════════════════════════════════════════════════════════════════════════════
# SANITISATION DU NOM DE FICHIER UPLOADÉ (protection path traversal)
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_UPLOAD_EXTENSIONS = {"csv", "xls", "xlsx", "dta", "sav"}


def _sanitize_upload_filename(raw_filename: str | None) -> str:
    """
    Neutralise un nom de fichier fourni par le client avant écriture disque.

    Défenses empilées :
      1. os.path.basename() -- supprime tout composant de répertoire
         ("../../etc/evil.csv" -> "evil.csv", y compris séparateurs Windows
         "\\" via remplacement préalable) ;
      2. retrait des caractères de contrôle et des séparateurs résiduels ;
      3. rejet explicite de "." et ".." (noms réservés du système de fichiers) ;
      4. limitation de longueur (255 = limite commune des FS) ;
      5. extension whitelistée (csv/xls/xlsx/dta/sav) -- un fichier sans
         extension valide est rejeté par /upload de toute façon.

    Retourne toujours un nom plat, sûr à concaténer sous UPLOAD_DIR.
    """
    filename = (raw_filename or "upload.bin").replace("\\", "/")
    filename = os.path.basename(filename)
    filename = filename.replace("\x00", "")
    # Retirer tout caractère non alphanumérique utile (hors . - _ espace)
    filename = re.sub(r"[^A-Za-z0-9._\- ]", "_", filename).strip()
    if filename in {"", ".", ".."}:
        filename = "upload.bin"
    if len(filename) > 255:
        stem, _, ext = filename.rpartition(".")
        filename = (stem[:240] or "upload") + ("." + ext[:14] if ext else "")
    return filename


def _validate_upload_extension(filename: str) -> None:
    """Rejette les extensions hors whitelist avant tout traitement."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format de fichier non supporté '.{ext or '?'}'. "
                    f"Formats acceptés : CSV, XLS, XLSX, DTA (Stata), SAV (SPSS).",
        )

load_dotenv(Path(__file__).resolve().parent / ".env")

# Configuration logging structuré
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

def _run_with_timeout(func, args=(), kwargs={}, timeout=300):
    """
    Exécute une fonction avec un timeout portable (Windows + Linux).
    Utilise threading pour éviter les limitations de signal sur Windows.
    """
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        # Timeout - le thread tourne encore
        # On ne peut pas tuer le thread en Python, mais on peut retourner une erreur
        raise TimeoutError(f"Operation timeout after {timeout}s")
    
    if exception[0] is not None:
        raise exception[0]
    
    return result[0]

app = FastAPI(title="QUANTA API", version="0.1.0")

# Rate limiting pour protéger contre les abus
def _get_rate_limit_key(request: Request) -> str:
    """
    Clé de rate limiting : utilise user_id si authentifié, sinon IP.
    Permet de limiter /analyze par utilisateur plutôt que par IP.
    """
    session_token = request.cookies.get("session_token")
    if session_token:
        session = db.get_session(session_token)
        if session:
            return f"user:{session['user_id']}"
    return get_remote_address(request)

limiter = Limiter(key_func=_get_rate_limit_key)
app.state.limiter = limiter

# Handler personnalisé pour les erreurs de rate limiting (message propre)
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return Response(
        content='{"detail": "Trop de requêtes. Veuillez réessayer dans quelques minutes."}',
        status_code=429,
        media_type="application/json"
    )

# CORS : autoriser le frontend local pendant le développement. À restreindre
# au domaine de production réel avant le déploiement (Jour 61 du programme).
_default_origins = "http://localhost:3000"
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
allowed_origins = [
    o.strip() for o in _allowed_origins_env.split(",") if o.strip()
] or [_default_origins]

print(f"CORS - Origines autorisées : {allowed_origins}", flush=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# SessionMiddleware pour OAuth (stockage du paramètre state CSRF)
session_secret_key = os.environ.get("SESSION_SECRET_KEY", "")
if not session_secret_key:
    print("ATTENTION : SESSION_SECRET_KEY non defini - protection CSRF du flux OAuth affaiblie", flush=True)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret_key,
    max_age=60 * 60 * 24 * 7,  # 7 jours, cohérent avec le cookie de session
)

# Inclure le router d'authentification
app.include_router(auth.router)

db.init_db()


# ═══════════════════════════════════════════════════════════════════════════════
# STOCKAGE DES FICHIERS PHYSIQUES (les métadonnées sont en base via db.py)
# ═══════════════════════════════════════════════════════════════════════════════

UPLOAD_DIR = os.environ.get("QUANTA_UPLOAD_DIR", "/data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 Mo (augmenté pour production)
MAX_ROWS = 100_000  # Augmenté pour production


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP AUTOMATIQUE (fichiers et analyses anciens)
# ═══════════════════════════════════════════════════════════════════════════════

def cleanup_old_files() -> None:
    """
    Nettoie les fichiers uploadés, analyses et sessions de plus de 24 heures.
    Exécuté périodiquement par APScheduler.
    """
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # Nettoyer les fichiers uploadés
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                filepath = os.path.join(UPLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    # Ne jamais supprimer les PDFs de rapport encore utiles ?
                    # Non : ils sont régénérables à la demande depuis le résultat
                    # en base ; la suppression des PDFs > 24h est sûre.
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
                    if file_mtime < cutoff_time:
                        try:
                            os.remove(filepath)
                            logger.info("Deleted old upload file", filename=filename)
                        except Exception as e:
                            logger.warning("Failed to delete file", filename=filename, error=str(e))
        
        # Nettoyer les analyses anciennes de la base (variantes internes sans
        # user_id -- réservées au nettoyage système, voir db.py).
        old_analyses = db.list_analyses_internal(limit=1000)
        deleted_count = 0
        for analysis in old_analyses:
            if analysis.get("updated_at"):
                try:
                    updated_at = datetime.fromisoformat(analysis["updated_at"])
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if updated_at < cutoff_time:
                        db.delete_analysis_internal(analysis["analysis_id"])
                        deleted_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to parse date for analysis",
                        analysis_id=analysis.get("analysis_id"), error=str(e),
                    )
        
        if deleted_count > 0:
            logger.info("Deleted old analyses from database", count=deleted_count)

        # Purger les sessions expirées (sinon suppression uniquement lazy à
        # l'accès -> accumulation illimitée en base).
        try:
            expired_sessions = db.cleanup_expired_sessions()
            if expired_sessions > 0:
                logger.info("Deleted expired sessions", count=expired_sessions)
        except Exception as e:
            logger.warning("Session cleanup failed", error=str(e))
            
    except Exception as e:
        logger.error("Cleanup failed", error=str(e))


# Démarrer le scheduler de cleanup
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_old_files, 'interval', hours=6)
scheduler.start()


# ═══════════════════════════════════════════════════════════════════════════════
# SCHÉMAS DE REQUÊTE
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyzeRequest(BaseModel):
    file_id: str
    # max_length : la query est stockée en base ET injectée dans le prompt LLM
    # -- sans borne, c'est un vecteur de coût (tokens) et de gonflement DB.
    query: Annotated[str, StringConstraints(max_length=2000)] = ""

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
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(auth.get_current_user)
) -> dict[str, Any]:
    """
    Reçoit un fichier (CSV/Excel/Stata/SPSS), le sauvegarde temporairement,
    et retourne un diagnostic léger (colonnes disponibles par type) --
    utile pour que le frontend puisse, par exemple, suggérer des colonnes
    à l'utilisateur ou valider sa requête avant de lancer l'analyse.

    Ne lance PAS l'analyse complète ici -- seulement le chargement et la
    classification des colonnes (rapide), pour donner un retour immédiat.
    """
    # Vérification précoce via Content-Length si disponible
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Fichier trop volumineux ({size / 1e6:.1f} Mo). "
                            f"Limite actuelle : {MAX_FILE_SIZE_BYTES / 1e6:.0f} Mo.",
                )
        except ValueError:
            pass  # Content-Length invalide, on continue avec la lecture chunked

    # Lecture par chunks pour éviter de charger tout en mémoire
    CHUNK_SIZE = 64 * 1024  # 64 KB
    raw_bytes = bytearray()
    total_read = 0

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux ({total_read / 1e6:.1f} Mo). "
                        f"Limite actuelle : {MAX_FILE_SIZE_BYTES / 1e6:.0f} Mo.",
            )
        raw_bytes.extend(chunk)

    # Sanitisation du nom de fichier (protection path traversal) + whitelist
    # d'extension AVANT toute lecture ou écriture disque.
    filename = _sanitize_upload_filename(file.filename)
    _validate_upload_extension(filename)

    diag = upload_validation.load_and_diagnose(bytes(raw_bytes), filename)

    if "error" in diag:
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier : {diag['error']}")

    if diag["n_rows"] > MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Dataset trop volumineux ({diag['n_rows']} lignes). "
                    f"Limite actuelle : {MAX_ROWS} lignes pour cette version.",
        )

    file_id = str(uuid.uuid4())
    # filename est désormais garanti plat (pas de composant de répertoire) :
    # saved_path reste strictement sous UPLOAD_DIR.
    saved_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(saved_path, "wb") as f:
        f.write(bytes(raw_bytes))

    db.save_upload(file_id, current_user["user_id"], {
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


def _run_analysis_core(analysis_id: str, user_id: str, file_id: str, query: str) -> None:
    """
    Logique principale d'analyse (fallback in-memory), déléguée au module
    partagé app/analysis_core.py -- même code que le worker subprocess,
    avec vérification d'annulation avant chaque intent (le /cancel était
    historiquement ignoré sur ce chemin).
    """
    def _check_cancelled() -> bool:
        analysis = db.get_analysis(analysis_id, user_id)
        return bool(analysis and analysis.get("status") == "cancelled")

    analysis_core.run_analysis(
        analysis_id, user_id, file_id, query,
        check_cancelled=_check_cancelled,
    )
    # Logging diagnostic présence des charts (le module partagé ne logge pas,
    # il est aussi utilisé par le worker subprocess qui a ses propres prints).
    try:
        final = db.get_analysis(analysis_id, user_id)
        result = (final or {}).get("result") or {}
        analysis = result.get("analysis") if isinstance(result, dict) else None
        if isinstance(analysis, dict):
            charts = analysis.get("charts")
            if charts:
                logger.info("Analysis charts present", count=len(charts))
            else:
                logger.warning("Analysis has NO charts")
        else:
            logger.warning("Analysis result has NO 'analysis' key")
    except Exception:
        pass


def _run_analysis_dispatch(analysis_id: str, user_id: str, file_id: str, query: str) -> None:
    """
    Tente d'abord l'exécution via le sous-processus analyze_worker.py.
    En cas d'échec (timeout, erreur, ou statut pas "done" en base),
    retombe sur l'exécution en mémoire via _run_analysis_core.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "app/analyze_worker.py", analysis_id, file_id, query],
            capture_output=True, text=True, timeout=260,
        )
        print(f"ANALYZE Worker - Returncode: {proc.returncode}", flush=True)
        if proc.stdout:
            print(f"ANALYZE Worker - Stdout: {proc.stdout[-6000:]}", flush=True)
        if proc.stderr:
            print(f"ANALYZE Worker - Stderr: {proc.stderr[-6000:]}", flush=True)

        # Vérifier le statut en base pour confirmer le succès réel
        analysis = db.get_analysis(analysis_id, user_id)
        if proc.returncode == 0 and analysis and analysis.get("status") == "done":
            print("ANALYZE Worker - Succès via sous-processus", flush=True)
            return
        else:
            print("ANALYZE Worker - Échec (returncode non nul ou statut pas 'done' en base), fallback vers exécution en mémoire", flush=True)
            _run_analysis_core(analysis_id, user_id, file_id, query)
    except subprocess.TimeoutExpired as e:
        print(f"ANALYZE Worker - Timeout après 260s", flush=True)
        if e.stdout:
            print(f"ANALYZE Worker - Stdout partiel avant timeout: {e.stdout[-3000:]}", flush=True)
        if e.stderr:
            print(f"ANALYZE Worker - Stderr partiel avant timeout: {e.stderr[-3000:]}", flush=True)
        print("ANALYZE Worker - Fallback vers exécution en mémoire", flush=True)
        _run_analysis_core(analysis_id, user_id, file_id, query)
    except Exception as e:
        print(f"ANALYZE Worker - Erreur lors de l'exécution du sous-processus : {e}, fallback vers exécution en mémoire", flush=True)
        _run_analysis_core(analysis_id, user_id, file_id, query)


def _run_analysis_background(analysis_id: str, user_id: str, file_id: str, query: str) -> None:
    """
    Exécutée en arrière-plan par BackgroundTasks. Ne lève jamais d'exception
    vers l'extérieur -- toute erreur est capturée et stockée dans l'état de
    l'analyse, consultable via /status.
    """
    try:
        # Exécuter l'analyse avec un timeout de 5 minutes (300 secondes)
        _run_with_timeout(_run_analysis_dispatch, args=(analysis_id, user_id, file_id, query), timeout=300)
    except TimeoutError as e:
        db.update_analysis(
            analysis_id, status="error",
            error=f"Timeout: {str(e)}",
            updated_at=_now(),
            user_id=user_id,
        )
    except Exception as e:
        # Filet de sécurité ultime : même une erreur totalement imprévue ne
        # doit jamais laisser l'analyse bloquée en "running" indéfiniment.
        db.update_analysis(
            analysis_id, status="error",
            error=f"Erreur inattendue pendant l'analyse : {e}",
            updated_at=_now(),
            user_id=user_id,
        )
    finally:
        # Remboursement du quota (point unique, exactement une fois) : toute
        # analyse qui finit en 'error' ne consomme pas le quota mensuel de
        # l'utilisateur -- qu'elle ait échoué par timeout, crash worker,
        # échec in-process ou fallback en erreur.
        try:
            final = db.get_analysis(analysis_id, user_id)
            if final and final.get("status") == "error":
                db.refund_quota(user_id)
        except Exception:
            pass


@app.post("/analyze")
@limiter.limit("5/minute")
def analyze(
    request: Request,
    analyze_request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(auth.get_current_user)
) -> dict[str, Any]:
    """
    Lance une analyse en arrière-plan et retourne immédiatement un
    analysis_id. Le frontend doit ensuite poller GET /status/{analysis_id}
    jusqu'à obtenir le statut "done" ou "error".
    
    Si une analyse identique (même fichier, même requête, même utilisateur)
    existe déjà en cache, renvoie le résultat sans recalcul ni consommation de quota.
    """
    if not db.upload_exists(analyze_request.file_id, current_user["user_id"]):
        raise HTTPException(
            status_code=404,
            detail=f"file_id '{analyze_request.file_id}' introuvable. Uploadez d'abord un fichier via /upload.",
        )

    user_id = current_user["user_id"]
    
    # Calculer le file_hash pour le cache
    upload_info = db.get_upload(analyze_request.file_id, user_id)
    if upload_info is None:
        raise HTTPException(
            status_code=404,
            detail=f"file_id '{analyze_request.file_id}' introuvable."
        )
    
    with open(upload_info["path"], "rb") as f:
        file_bytes = f.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    
    # Chercher dans le cache (strictement par utilisateur)
    cached = db.find_cached_analysis(user_id, file_hash, analyze_request.query)
    if cached:
        # Cache hit : créer une nouvelle entrée avec le résultat déjà calculé
        analysis_id = str(uuid.uuid4())
        db.create_analysis(analysis_id, user_id, analyze_request.file_id, analyze_request.query, _now(), file_hash)
        db.update_analysis(
            analysis_id,
            status="done",
            result=cached["result"],
            updated_at=_now(),
            user_id=user_id,
            file_hash=file_hash,
        )
        return {"analysis_id": analysis_id, "status": "done", "from_cache": True}
    
    # Cache miss : comportement normal avec consommation de quota
    allowed, remaining, renewal_at = db.check_and_increment_quota(user_id)
    
    if not allowed:
        # Formater la date de renouvellement pour l'affichage
        from datetime import datetime
        renewal_date_str = ""
        if renewal_at:
            try:
                renewal_date = datetime.fromisoformat(renewal_at.replace("Z", "+00:00"))
                renewal_date_str = renewal_date.strftime("%d/%m/%Y")
            except ValueError:
                renewal_date_str = "date inconnue"
        
        raise HTTPException(
            status_code=403,
            detail=f"Quota mensuel atteint (15 analyses). Renouvellement le {renewal_date_str}."
        )

    analysis_id = str(uuid.uuid4())
    db.create_analysis(analysis_id, user_id, analyze_request.file_id, analyze_request.query, _now(), file_hash)

    background_tasks.add_task(_run_analysis_background, analysis_id, user_id, analyze_request.file_id, analyze_request.query)

    return {"analysis_id": analysis_id, "status": "pending", "from_cache": False}


@app.get("/status/{analysis_id}")
def get_status(
    analysis_id: str,
    current_user: dict = Depends(auth.get_current_user)
) -> dict[str, Any]:
    """
    Statut d'une analyse en cours ou terminée. Le frontend poll cet
    endpoint toutes les 2-3 secondes (Jour 28 du programme).
    """
    analysis = db.get_analysis(analysis_id, current_user["user_id"])
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
def get_history(current_user: dict = Depends(auth.get_current_user)) -> dict[str, Any]:
    """
    Liste légère des analyses passées (sans le détail complet des résultats)
    -- maintenant persistée via SQLite (db.py), survit aux redémarrages
    du serveur.
    """
    items = db.list_analyses(current_user["user_id"], limit=100)
    return {"count": len(items), "analyses": items}


@app.get("/quota")
def get_quota(current_user: dict = Depends(auth.get_current_user)) -> dict[str, Any]:
    """
    Retourne les informations de quota de l'utilisateur connecté.
    """
    quota_info = db.get_quota_info(current_user["user_id"])
    if quota_info is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable."
        )
    return quota_info


@app.post("/analyses/{analysis_id}/cancel")
def cancel_analysis(
    analysis_id: str,
    current_user: dict = Depends(auth.get_current_user)
) -> dict[str, str]:
    """
    Annule une analyse en cours. Le worker vérifie le statut avant chaque intent
    et s'arrête si le statut est "cancelled".
    """
    analysis = db.get_analysis(analysis_id, current_user["user_id"])
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"analysis_id '{analysis_id}' introuvable."
        )
    
    if analysis["status"] not in {"pending", "running"}:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible d'annuler une analyse avec statut '{analysis['status']}'."
        )
    
    # Mettre à jour le statut en base
    updated = db.update_analysis(
        analysis_id,
        status="cancelled",
        updated_at=_now(),
        user_id=current_user["user_id"]
    )
    
    if not updated:
        raise HTTPException(
            status_code=400,
            detail="Impossible de mettre à jour l'analyse (statut déjà 'done' ou utilisateur non propriétaire)."
        )
    
    return {"analysis_id": analysis_id, "status": "cancelled"}


@app.get("/report/{analysis_id}")
def get_report(
    analysis_id: str,
    theme: str = "dark",
    current_user: dict = Depends(auth.get_current_user)
) -> Response:
    """
    Télécharge le rapport PDF d'une analyse terminée.
    Query param optionnel : theme=dark|light (défaut dark).
    Exemple : /report/{id}?theme=light
    """
    analysis = db.get_analysis(analysis_id, current_user["user_id"])
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

    theme_norm = (theme or "dark").strip().lower()
    if theme_norm not in {"dark", "light"}:
        theme_norm = "dark"

    result = analysis.get("result")
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Résultat d'analyse invalide ou absent — génération du PDF impossible.",
        )

    upload_dir = os.environ.get("QUANTA_UPLOAD_DIR", "/data/uploads")
    os.makedirs(upload_dir, exist_ok=True)

    logger.debug("PDF Report generation", analysis_id=analysis_id, theme=theme_norm)

    # Chercher PDF déjà généré
    pdf_path = os.path.join(upload_dir, f"report_{analysis_id}_{theme_norm}.pdf")

    # Supprimer PDF existant pour forcer régénération avec PDF Worker
    if os.path.exists(pdf_path):
        logger.debug("Deleting existing PDF", pdf_path=pdf_path)
        os.unlink(pdf_path)

    logger.debug("Launching PDF Worker")

    # Toujours lancer le PDF Worker
    # Écrire le JSON d'entrée dans un fichier temp
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json',
            delete=False, encoding='utf-8'
        ) as tmp:
            logger.debug("Creating temp file", temp_file=tmp.name)
            json.dump(result, tmp, ensure_ascii=False)
            input_path = tmp.name
            logger.debug("JSON written to temp file", input_path=input_path)
    except Exception as e:
        logger.error("Error creating temp file", error=str(e))
        raise

    logger.debug("Entering subprocess try block")

    try:
        # Lancer le subprocess PDF Worker
        # Timeout 300s (5 minutes)
        logger.info("PDF Worker - Launching subprocess", analysis_id=analysis_id)
        logger.debug("Before subprocess.run")
        proc = subprocess.run(
            [sys.executable, "app/pdf_worker.py", input_path, pdf_path, theme_norm],
            timeout=300,
            capture_output=True,
            text=True
        )
        logger.debug("After subprocess.run", returncode=proc.returncode)

        logger.info("PDF Worker - Returncode", returncode=proc.returncode)
        if proc.stdout:
            logger.debug("PDF Worker - Stdout", stdout=proc.stdout[-6000:])
        if proc.stderr:
            logger.debug("PDF Worker - Stderr", stderr=proc.stderr[-6000:])

        if proc.returncode != 0:
            logger.error("PDF Worker failed, using fallback lightweight PDF")
            # Fallback PDF léger
            from app.report_generator import generate_lightweight_pdf
            pdf_bytes = generate_lightweight_pdf(result, theme=theme_norm)
            if pdf_bytes:
                filename = f"rapport_quanta_{analysis_id[:8]}.pdf"
                # Pas de headers CORS manuels : le middleware CORSMiddleware
                # (allow_credentials=True) rejette "*" -- les origines
                # autorisées sont déjà gérées par ALLOWED_ORIGINS.
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                    }
                )
            raise HTTPException(status_code=500, detail="Erreur génération PDF")
        
        logger.info("PDF Worker - Success, PDF generated", pdf_path=pdf_path)

    except subprocess.TimeoutExpired:
        # Timeout 5min dépassé = très grand dataset
        # Retourner PDF léger
        from app.report_generator import generate_lightweight_pdf
        pdf_bytes = generate_lightweight_pdf(result, theme=theme_norm)
        if pdf_bytes:
            filename = f"rapport_quanta_{analysis_id[:8]}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                }
            )
        raise HTTPException(status_code=504, detail="Timeout génération PDF")

    except Exception as e:
        logger.exception("Subprocess exception", exception_type=type(e).__name__, error=str(e))
        raise
    
    finally:
        # Nettoyer le fichier JSON temporaire
        try:
            os.unlink(input_path)
        except:
            pass
    
    # Lire et servir le PDF
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="PDF non généré")

    suffix = "academique" if theme_norm == "light" else "dark"
    filename = f"rapport_quanta_{suffix}_{analysis_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


# Note : pas de nettoyage automatique des fichiers à l'arrêt du serveur --
# ce serait contradictoire avec l'objectif de persistance via SQLite. Un
# vrai mécanisme d'expiration/nettoyage périodique (ex: fichiers de plus
# de 30 jours) est prévu pour une itération ultérieure, pas en V1.
