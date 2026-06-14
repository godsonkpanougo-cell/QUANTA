"""
QUANTA — main.py v2
Backend FastAPI avec couche de calcul déterministe intégrée.
Flux : Upload → compute.py (vrais chiffres) → brain.py (LLM interprète)
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# ── Import des modules QUANTA ─────────────────────────────────────────────────
from compute import run_full_compute_pipeline
from brain import analyze_with_brain

# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="QUANTA API",
    description="L'intelligence statistique suprême — Backend FastAPI",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # en prod : remplacer par l'URL du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE PRINCIPALE — /analyze
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/analyze")
async def analyze(
    file:       UploadFile = File(...),
    objective:  str        = Form("descriptive"),
    software:   str        = Form("R"),
    language:   str        = Form("FR"),
    target_col: Optional[str] = Form(None),
):
    """
    Point d'entrée principal de QUANTA.
    1. compute.py calcule les vrais chiffres
    2. brain.py interprète avec le LLM
    3. Retourne rapport complet + graphiques + scripts
    """
    # Vérification du format
    allowed = {"csv", "xlsx", "xls", "dta", "sav"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : .{ext}. Formats acceptés : {allowed}"
        )

    file_bytes = await file.read()
    filename   = file.filename

    print(f"\n[QUANTA] {'='*50}")
    print(f"[QUANTA] Analyse démarrée → {filename}")
    print(f"[QUANTA] Objectif={objective} | Logiciel={software} | Langue={language}")
    print(f"[QUANTA] {'='*50}")

    # ── ÉTAPE 1 : Calculs déterministes ───────────────────────────────────────
    print("[QUANTA] ÉTAPE 1/2 — Calculs déterministes (compute.py)...")
    try:
        compute_result = run_full_compute_pipeline(
            file_bytes=file_bytes,
            filename=filename,
            target_col=target_col,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur compute : {str(e)}")

    if "error" in compute_result:
        raise HTTPException(status_code=422, detail=compute_result["error"])

    # ── ÉTAPE 2 : Interprétation LLM ──────────────────────────────────────────
    print("[QUANTA] ÉTAPE 2/2 — Interprétation LLM (brain.py)...")
    try:
        brain_result = await analyze_with_brain(
            compute_data=compute_result,
            filename=filename,
            objective=objective,
            software=software,
            language=language,
        )
    except Exception as e:
        # Si le LLM échoue, on retourne quand même les calculs
        print(f"[QUANTA] ⚠ LLM échoué : {e} — retour calculs bruts uniquement")
        brain_result = {
            "error_llm":      str(e),
            "fallback_note":  "Interprétation LLM indisponible — calculs déterministes fournis.",
        }

    # ── ASSEMBLAGE FINAL ───────────────────────────────────────────────────────
    response = {
        "status":       "success",
        "filename":     filename,
        "objective":    objective,
        "software":     software,
        "language":     language,

        # Résultats compute (vrais chiffres)
        "diagnosis":    compute_result.get("diagnosis", {}),
        "cleaning":     compute_result.get("cleaning", {}),
        "descriptive":  compute_result.get("descriptive", {}),
        "normality":    compute_result.get("normality", {}),
        "correlation":  compute_result.get("correlation", {}),
        "regression":   compute_result.get("regression", {}),

        # Graphiques (base64 PNG)
        "charts":       compute_result.get("charts", {}),
        "n_charts":     compute_result.get("n_charts", 0),

        # Scripts reproductibles
        "r_script":     compute_result.get("r_script", ""),
        "stata_script": compute_result.get("stata_script", ""),

        # Interprétation LLM
        "interpretation": brain_result,
    }

    print(f"[QUANTA] ✅ Analyse complète — {compute_result.get('n_charts', 0)} graphiques")
    return JSONResponse(content=response)


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE SANTÉ
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def health():
    return {
        "status": "QUANTA opérationnel",
        "version": "2.0.0",
        "modules": ["compute", "brain"],
        "endpoints": ["/analyze", "/health"],
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
