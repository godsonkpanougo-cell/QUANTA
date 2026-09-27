#!/usr/bin/env python3
"""
Analyze Worker — exécuté en subprocess séparé.
Reçoit analysis_id, file_id, query en argv, exécute l'analyse complète,
et écrit le résultat en base de données via db.py.
Usage: python app/analyze_worker.py <analysis_id> <file_id> <query>

La logique d'analyse est déléguée à app/analysis_core.py (module partagé
avec le fallback in-memory de main.py) : un seul code pour les deux chemins,
avec vérification d'annulation avant chaque intent et réutilisation du
pipeline de base en mode autonome.
"""
import sys
import logging
from pathlib import Path

# Configuration du logging pour rendre les logs TIMING visibles en production
# Forcer explicitement stderr avec le bon format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
    force=True  # Force la reconfiguration même si déjà configuré
)

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
from app import analysis_core

_mem_checkpoint("après imports lourds (analysis_core -> orchestrator, brain, compute)")

def main():
    if len(sys.argv) < 4:
        print("Usage: python app/analyze_worker.py <analysis_id> <file_id> <query>", file=sys.stderr)
        sys.exit(1)

    analysis_id = sys.argv[1]
    file_id = sys.argv[2]
    query = sys.argv[3]

    _mem_checkpoint("début main")

    try:
        # Récupérer l'analyse pour obtenir le user_id (isolation des données)
        # Utilisation de get_analysis_internal car le worker n'a pas encore le user_id
        analysis = db.get_analysis_internal(analysis_id)
        if analysis is None:
            # update_analysis_internal : sans user_id, l'écriture serait
            # silencieusement ignorée (WHERE user_id = '' ne matche rien).
            db.update_analysis_internal(
                analysis_id, status="error",
                error=f"analysis_id '{analysis_id}' introuvable.",
                updated_at=_now(),
            )
            sys.exit(1)

        user_id = analysis["user_id"]

        _mem_checkpoint("avant exécution analyse")

        # Logique d'analyse complète déléguée au module partagé.
        # La vérification d'annulation lit la base (statut 'cancelled')
        # avant chaque intent, comme dans l'implémentation historique.
        def _check_cancelled() -> bool:
            current = db.get_analysis_internal(analysis_id)
            return bool(current and current.get("status") == "cancelled")

        analysis_core.run_analysis(
            analysis_id, user_id, file_id, query,
            check_cancelled=_check_cancelled,
        )

        _mem_checkpoint("après exécution analyse")

        print(f"ANALYZE Worker - Succès : analysis_id={analysis_id}", flush=True)
        sys.exit(0)

    except SystemExit:
        # run_analysis -> _raise_if_cancelled -> sys.exit(0) historique est
        # remplacé par une exception ; SystemExit remonte si un sous-module
        # en lève une, on le laisse traverser sans le transformer en erreur.
        raise

    except Exception as e:
        # Filet de sécurité : toute erreur non prévue est capturée et stockée en base
        # update_analysis_internal : le user_id n'est pas forcément disponible
        # dans ce contexte (et sans lui l'écriture serait ignorée) -> variante
        # interne réservée aux workers de confiance. Le remboursement du quota
        # est géré côté main.py (_run_analysis_background.finally) au vu du
        # statut final 'error' -- point unique, jamais deux fois.
        import traceback
        error_msg = f"Erreur inattendue dans analyze_worker : {e}\n{traceback.format_exc()}"
        print(f"ANALYZE Worker - Erreur : {error_msg}", file=sys.stderr, flush=True)
        try:
            db.update_analysis_internal(
                analysis_id, status="error",
                error=error_msg,
                updated_at=_now(),
            )
        except Exception as db_error:
            print(f"ANALYZE Worker - Erreur lors de l'écriture en base : {db_error}", file=sys.stderr, flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
