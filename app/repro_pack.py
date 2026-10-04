"""
QUANTA — repro_pack.py (Pilier 3 : Repro Pack, « chaque chiffre est
recomputable »)

Pourquoi : l'argument qui convainc un encadreur n'est pas « notre IA est
forte », c'est « ce rapport est AUDITABLE ». Le Repro Pack est un ZIP
téléchargeable par analyse qui contient tout ce qu'il faut pour vérifier :

  README.txt          — audit : analysis_id, dates, sha256 du fichier source,
                        versions EXACTES des packages, seeds, plateforme ;
  resultats.json      — la sortie persistée EXACTE du pipeline (la source de
                        vérité qui a produit le PDF), jamais réécrite ;
  donnees/<fichier>   — l'UPLOAD ORIGINAL tel quel (son sha256 figure dans
                        le README) : le pack est autonome ;
  rapport_<theme>.pdf — inclus SI déjà généré (sinon note dans le README :
                        GET /report/{id} le produit) ;
  scripts R/Stata     — inclus s'ils sont présents dans le résultat.

Isolation (règle « sans casser l'existant ») :
  - AUCUNE table nouvelle : lit analyses/uploads via db.py existant ;
  - AUCUN recalcul statistique : le pack s'assemble en lecture pure
    (rapide, compatible budget Render) ;
  - endpoint GET /repro_pack/{analysis_id} préfixé, auth user stricte ;
  - branchement main.py : 2 lignes (import + include_router).
"""
from __future__ import annotations

import io
import json
import os
import platform
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import db
from app import auth

router = APIRouter(prefix="/repro_pack", tags=["repro_pack"])

# Packages dont la version entre dans l'audit (tolère l'absence).
_AUDITED_PACKAGES = (
    "numpy", "pandas", "scipy", "statsmodels", "prince",
    "matplotlib", "seaborn", "fastapi", "uvicorn",
)


def _package_versions() -> dict[str, str]:
    from importlib.metadata import version
    out: dict[str, str] = {}
    for name in _AUDITED_PACKAGES:
        try:
            out[name] = version(name)
        except Exception:
            out[name] = "non-installé"
    return out


def _build_readme(analysis: dict[str, Any], result: dict[str, Any],
                  upload: dict[str, Any] | None, pdf_included: bool,
                  data_included: bool) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "REPRO PACK QUANTA — dossier d'audit scientifique",
        "================================================",
        "",
        f"Généré le            : {now}",
        f"analysis_id          : {analysis['analysis_id']}",
        f"Requête (query)      : {analysis.get('query', '')}",
        f"Statut               : {analysis['status']}",
        f"Créée le             : {analysis.get('created_at')}",
        f"Fichier source       : {(upload or {}).get('filename', 'n/a')}",
        f"sha256 (source)      : {analysis.get('file_hash') or 'non-enregistré'}",
        f"Dimensions           : n_rows={((upload or {}).get('n_rows'))} n_cols={((upload or {}).get('n_cols'))}",
        "",
        "CONTENU DE L'ARCHIVE",
        "--------------------",
        "  resultats.json      : sortie persistée EXACTE du pipeline QUANTA",
        "                        (aucune réécriture, aucun recalcul).",
        f"  donnees/            : {'upload original inclus (identité vérifiable par le sha256 ci-dessus)' if data_included else 'ABSENT (fichier source nettoyé du disque serveur)'}",
        f"  rapport PDF         : {'inclus (thème demandé)' if pdf_included else 'non inclus — générez-le via GET /report/' + analysis['analysis_id']}",
        "",
        "ENVIRONNEMENT D'EXÉCUTION",
        "-------------------------",
        f"Python               : {sys.version.split()[0]}",
        f"Plateforme           : {platform.platform()}",
    ]
    lines.append("Versions des packages  :")
    for name, ver in _package_versions().items():
        lines.append(f"  - {name:<12} {ver}")
    lines += [
        "",
        "DÉTERMINISME (seeds)",
        "--------------------",
        "  - Échantillonnage (datasets > 5000 lignes) : random_state=42",
        "    (compute.run_base_compute_pipeline, run_acm, run_acp) ;",
        "  - ACM (prince.MCA) : n_iter/random_state=42 ;",
        "  - ACP (prince.PCA) : random_state=42 ;",
        "  - Bootstraps (IC des tailles d'effet) : générateurs numpy seedés",
        "    par appel (test_selector._bootstrap_matrix), pas d'état global.",
        "",
        "COMMENT VÉRIFIER UN CHIFFRE",
        "---------------------------",
        "  1. resultats.json est la sortie immuable produite à la date indiquée ;",
        "  2. reprenez donnees/<fichier> et vérifiez son sha256 (doit égaler",
        "     celui du README) ;",
        "  3. rejouez l'analyse QUANTA sur ce même fichier : le cache interne",
        "     garantit le résultat IDENTIQUE pour (sha256, requête) ;",
        "  4. les scripts R/Stata (s'ils suivent) reproduisent les calculs",
        "     clés hors de QUANTA, dans vos propres outils.",
        "",
        "Note d'intégrité : ce pack a été assemblé en lecture pure — QUANTA",
        "n'a rien recalculé ni modifié à la génération de cette archive.",
    ]
    return "\n".join(lines)


def build_repro_pack(analysis_id: str, user_id: str,
                     theme: str = "dark") -> tuple[bytes, str]:
    """Assemble le ZIP. Retourne (bytes, filename). Lève ValueError si
    l'analyse est introuvable pour cet utilisateur ou non terminée."""
    analysis = db.get_analysis(analysis_id, user_id)
    if analysis is None:
        raise ValueError(f"analysis_id '{analysis_id}' introuvable pour cet utilisateur.")
    if analysis["status"] != "done":
        raise ValueError(
            f"L'analyse n'est pas terminée (statut : '{analysis['status']}'). "
            "Attendez 'done' avant de demander le Repro Pack."
        )
    result = analysis.get("result")
    if not isinstance(result, dict):
        raise ValueError("Résultat d'analyse invalide ou absent.")

    try:
        upload = db.get_upload(analysis.get("file_id"), user_id)
    except Exception:
        upload = None

    theme_norm = (theme or "dark").strip().lower()
    if theme_norm not in {"dark", "light"}:
        theme_norm = "dark"

    upload_dir = os.environ.get("QUANTA_UPLOAD_DIR", "/data/uploads")
    pdf_path = os.path.join(upload_dir, f"report_{analysis_id}_{theme_norm}.pdf")
    pdf_included = os.path.exists(pdf_path)

    data_bytes: bytes | None = None
    data_name: str | None = None
    if upload and upload.get("path"):
        try:
            with open(upload["path"], "rb") as f:
                data_bytes = f.read()
            data_name = os.path.basename(upload.get("filename") or "donnees")
        except OSError:
            data_bytes = None

    safe_id = "".join(c if c.isalnum() or c == "-" else "_" for c in analysis_id)
    filename = f"repro_pack_{safe_id}_{theme_norm}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            _build_readme(analysis, result, upload, pdf_included,
                          data_included=data_bytes is not None),
        )
        zf.writestr(
            "resultats.json",
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
        if data_bytes is not None and data_name:
            zf.writestr(f"donnees/{data_name}", data_bytes)
        if pdf_included:
            with open(pdf_path, "rb") as f:
                zf.writestr(f"rapport_{theme_norm}.pdf", f.read())
        # Scripts R/Stata s'ils sont présents dans le résultat persisté
        for key, arcname in (("r_script", "script_reproduction.R"),
                             ("stata_script", "script_reproduction.do")):
            if isinstance(result.get(key), str) and result[key].strip():
                zf.writestr(arcname, result[key])

    return buf.getvalue(), filename


@router.get("/{analysis_id}")
def http_get_repro_pack(
    analysis_id: str,
    theme: str = "dark",
    current_user: dict = Depends(auth.get_current_user),
) -> Response:
    from fastapi import Response  # local: n'alourdit pas les imports module-level
    try:
        content, filename = build_repro_pack(
            analysis_id, current_user["user_id"], theme=theme
        )
    except ValueError as e:
        status = 404 if "introuvable" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
