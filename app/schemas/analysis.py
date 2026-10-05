"""Contrats Pydantic des payloads QUANTA (durcissement industrialisation).

Pourquoi : le payload d'analyse n'avait AUCUN contrat — la classe de bug
« clé manquante / structure inattendue » (ex : bug theme="both" qui vidait
la normalité, corrigé le 05/10/2026) ne pouvait être détectée qu'à l'œil.
Ces modèles verrouillent la structure TOPOLOGIQUE du payload (clés
obligatoires + types racines) tout en tolérant l'extensibilité des champs
métier (extra="allow") : la suite de tests valide un VRAI résultat de
pipeline contre ce contrat à chaque run.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceScore(BaseModel):
    """Score de confiance de l'orchestrateur (plafonné par la taille n)."""
    model_config = ConfigDict(extra="allow")

    score_global: float
    niveau: str
    points_de_vigilance: list[str] = Field(default_factory=list)


class InferenceBlock(BaseModel):
    """Bloc d'inférence : intention reçue, test exécuté, résultat."""
    model_config = ConfigDict(extra="allow")

    action_executed: str | None = None
    validation_issues: list[Any] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class AnalysisPayload(BaseModel):
    """Réponse de run_full_analysis (orchestrateur) — contrat racine.
    Les champs métier profonds restent libres (dict) : le contrat verrouille
    ce qui doit TOUJOURS exister pour que PDF/soutenance/Repro Pack marchent.
    """
    model_config = ConfigDict(extra="allow")

    status: str
    filename: str | None = None
    diagnosis: dict[str, Any]
    normality: dict[str, Any]
    correlation_base: dict[str, Any]
    regression_base: dict[str, Any]
    inference: InferenceBlock
    confidence_score: ConfidenceScore
    audit_log: list[dict[str, Any]] = Field(default_factory=list)
    n_charts: int = 0
