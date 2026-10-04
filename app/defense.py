"""
QUANTA — defense.py (Pilier 4 : Mode Soutenance)

Pourquoi : l'indispensabilité se décide sur les moments de vérité — la veille
de la défense. Le Mode Soutenance génère les questions probables du jury
AVEC LES RÉPONSES CHIFFRÉES tirées de l'analyse persistée, plus les défenses
aux points de vigilance que le Skeptic Engine a déjà identifiés. Aucun
concurrent ne peut le faire : ils n'ont pas la rigueur statistique sous-jacente
(et n'ont donc rien de fiable à citer).

Règles d'or (non négociables) :
  - ZÉRO chiffre inventé : chaque réponse reformule des valeurs EXTRAITES du
    résultat persisté (la même source de vérité que le PDF) ;
  - chaque réponse porte son `source` (chemin JSON) : la soutenance reste
    AUDITABLE, cohérente avec le Repro Pack (Pilier 3) ;
  - génération DÉTERMINISTE, sans LLM et sans recalcul : instantanée,
    sans coût, sans risque de timeout — compatible budget Render ;
  - les sections absentes (ex: pas de test d'inférence) sont simplement
    omises : le pack s'adapte à ce que l'analyse contient réellement.

Isolation (règle « sans casser l'existant ») :
  - AUCUNE table nouvelle (lit l'analyse via db.get_analysis existant) ;
  - endpoint GET /defense/{analysis_id} préfixé, auth user stricte ;
  - branchement main.py : 2 lignes (import + include_router).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import db
from app import auth

router = APIRouter(prefix="/defense", tags=["defense"])

_EFFECT_KEYS = ("effect_size", "cramers_v", "eta_squared", "epsilon_squared",
                "cohens_d", "cliffs_delta", "r", "rho")
_CI_SUFFIXES = (("", ""), ("_ci_lower", "_ci_upper"),
                ("_effect_size_ci_lower", "_effect_size_ci_upper"))


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _pipeline_of(result: dict[str, Any]) -> dict[str, Any]:
    """Le résultat persisté est soit la réponse pipeline directe, soit
    emboîtée sous 'analysis' (sortie brain.analyze_with_brain)."""
    inner = result.get("analysis")
    if isinstance(inner, dict) and ("diagnosis" in inner or "confidence_score" in inner):
        return inner
    return result


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else str(v)
    return str(v)


def _find_test_result(pipeline: dict[str, Any]) -> dict[str, Any]:
    inf = pipeline.get("inference")
    if isinstance(inf, dict):
        res = inf.get("result")
        if isinstance(res, dict):
            return res
    return {}


# ── Extracteurs (une seule source : resultats persistés) ─────────────────────

def _identity(pipeline: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    diag = pipeline.get("diagnosis") or {}
    conf = pipeline.get("confidence_score") or {}
    inf = pipeline.get("inference") or {}
    return {
        "filename": pipeline.get("filename"),
        "n_rows": diag.get("n_rows"),
        "n_cols": diag.get("n_cols"),
        "score_global": conf.get("score_global"),
        "niveau_confiance": conf.get("niveau"),
        "test_execute": inf.get("action_executed"),
        "requete": analysis.get("query", ""),
    }


def _normality_summary(pipeline: dict[str, Any]) -> dict[str, Any] | None:
    norm = pipeline.get("normality")
    if not isinstance(norm, dict) or not norm:
        return None
    normales = sum(
        1 for v in norm.values()
        if isinstance(v, dict) and v.get("conclusion") == "NORMALE"
    )
    return {"n_variables": len(norm), "n_normales": normales}


def _correlation_summary(pipeline: dict[str, Any]) -> dict[str, Any] | None:
    corr = pipeline.get("correlation_base") or pipeline.get("correlation")
    if not isinstance(corr, dict) or not corr.get("pairs"):
        return None
    pairs = corr["pairs"]
    top = sorted(
        pairs.items(),
        key=lambda kv: abs(kv[1].get("r", 0) or 0),
        reverse=True,
    )[:3]
    mult = corr.get("multiplicity_correction")
    return {
        "method": corr.get("method"),
        "n_paires": len(pairs),
        "top3": [
            {
                "paire": k,
                "r": v.get("r"),
                "p_value": v.get("p_value"),
                "p_adjusted": v.get("p_adjusted"),
            }
            for k, v in top
        ],
        "multiplicity": mult,
    }


def _inference_summary(pipeline: dict[str, Any]) -> dict[str, Any] | None:
    inf = pipeline.get("inference") or {}
    res = _find_test_result(pipeline)
    if not inf.get("action_executed") and not res:
        return None
    effect = _pick(res, *_EFFECT_KEYS)
    ci_low = ci_high = None
    # IC bootstrap : cherche {<metrique>}_ci_lower/_ci_upper pour toute
    # metrique d'effet connue présente dans le résultat.
    for k in _EFFECT_KEYS:
        lo, hi = res.get(f"{k}_ci_lower"), res.get(f"{k}_ci_upper")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            ci_low, ci_high = lo, hi
            break
    return {
        "action_executed": inf.get("action_executed"),
        "intent": (inf.get("intent_received") or {}).get("action"),
        "test_name": _pick(res, "name", "test_name", "test"),
        "statistic": _pick(res, "statistic", "stat", "W", "U", "H", "F", "t", "chi2"),
        "p_value": _pick(res, "p_value", "p"),
        "decision": _pick(res, "decision", "conclusion"),
        "effect_size": effect,
        "effect_ci": [ci_low, ci_high] if ci_low is not None else None,
        "power": _pick(res, "power", "puissance"),
        "validation_issues": inf.get("validation_issues") or [],
    }


def _confidence_summary(pipeline: dict[str, Any]) -> dict[str, Any] | None:
    conf = pipeline.get("confidence_score")
    if not isinstance(conf, dict) or not conf:
        return None
    return {
        "score_global": conf.get("score_global"),
        "niveau": conf.get("niveau"),
        "details": conf.get("details"),
        "points_de_vigilance": conf.get("points_de_vigilance") or [],
    }


def _audit_summary(pipeline: dict[str, Any]) -> dict[str, Any] | None:
    log = pipeline.get("audit_log")
    if not isinstance(log, list) or not log:
        return None
    return {"n_operations": len(log), "operations": [
        str(e.get("step") or e.get("action") or e.get("operation") or "?") for e in log
        if isinstance(e, dict)
    ]}


# ── Génération des questions (déterministe, valeurs citées) ──────────────────

def _build_questions(pipeline: dict[str, Any], ident: dict[str, Any],
                     norm: dict | None, corr: dict | None,
                     inf: dict | None, conf: dict | None,
                     audit: dict | None) -> list[dict[str, str]]:
    q: list[dict[str, str]] = []

    if inf and inf.get("test_name"):
        q.append({
            "question": (
                f"Pourquoi avoir retenu le test « {inf['test_name']} » et non un autre ?"
            ),
            "reponse": (
                f"L'intention « {inf.get('intent') or inf.get('action_executed')} » a été "
                f"exécutée en {inf['test_name']} ; le choix découle des conditions des "
                f"données (voir l'audit_log du résultat et la répartition de normalité ci-dessous). "
                + (
                    f"Sur {norm['n_variables']} variables numériques, {norm['n_normales']} sont "
                    f"conclues NORMALES par le pipeline."
                    if norm else ""
                )
            ).strip(),
            "source": "inference.action_executed, normality",
        })
    if inf and inf.get("p_value") is not None:
        rep = (
            f"Le test donne {inf['test_name'] or 'le test'} = {inf['statistic'] if inf.get('statistic') is not None else 'n/a'}, "
            f"p = {_fmt(inf['p_value'])}, décision : {inf.get('decision') or 'voir rapport'}."
        )
        if inf.get("effect_size") is not None:
            rep += f" Taille d'effet : {_fmt(inf['effect_size'])}"
            if inf.get("effect_ci"):
                rep += f" (IC 95% : [{_fmt(inf['effect_ci'][0])} ; {_fmt(inf['effect_ci'][1])}])"
            rep += "."
        if inf.get("power") is not None:
            rep += f" Puissance statistique : {_fmt(inf['power'])}."
        q.append({
            "question": "Votre résultat est-il robuste ou peut-il être dû au hasard ?",
            "reponse": rep,
            "source": "inference.result (p_value, decision, effect_size, IC bootstrap, power)",
        })
    if corr:
        q.append({
            "question": (
                f"Vous avez testé {corr['n_paires']} paires de corrélations "
                f"({corr['method']}) : comment contrôlez-vous les faux positifs ?"
            ),
            "reponse": (
                (
                    f"Correction de multiplicité appliquée : "
                    f"{corr['multiplicity'].get('significant_raw')} paires significatives en brut, "
                    f"{corr['multiplicity'].get('significant_adjusted')} après correction "
                    f"({corr['multiplicity'].get('method')}) — le q-value figure à côté du p brut."
                    if corr.get("multiplicity")
                    else "Le p-value brut est rapporté paire par paire (pas de test multiple global)."
                )
                + (
                    " Corrélation la plus forte : "
                    f"{corr['top3'][0]['paire']} (r={_fmt(corr['top3'][0]['r'])}, "
                    f"p={_fmt(corr['top3'][0]['p_value'])})."
                    if corr.get("top3")
                    else ""
                )
            ),
            "source": "correlation_base.pairs, correlation_base.multiplicity_correction",
        })
    if ident.get("n_rows") is not None:
        cap = (
            f" Le score de confiance est plafonné au niveau « {conf['niveau']} »."
            if conf and conf.get("niveau") else ""
        )
        q.append({
            "question": f"Un échantillon de n={ident['n_rows']} suffit-il pour conclure ?",
            "reponse": (
                f"L'analyse porte sur n={ident['n_rows']} lignes et {ident.get('n_cols') or 'n/a'} colonnes."
                + cap
                + (
                    f" Score de confiance global : {conf['score_global']}."
                    if conf and conf.get("score_global") is not None else ""
                )
                + " La puissance statistique du test principal est rapportée dans les résultats."
            ),
            "source": "diagnosis.n_rows, confidence_score",
        })
    if audit:
        q.append({
            "question": "Comment avez-vous préparé les données (manquants, outliers, doublons) ?",
            "reponse": (
                f"Le pipeline a journalisé {audit['n_operations']} opérations de préparation "
                f"(audit_log reproductible, inclus dans resultats.json) : "
                + ", ".join(audit["operations"][:6]) + "."
            ),
            "source": "audit_log",
        })
    if norm:
        q.append({
            "question": "Sur quoi fondez-vous l'hypothèse de normalité (ou non) de vos variables ?",
            "reponse": (
                f"Tests de normalité du pipeline : {norm['n_normales']}/{norm['n_variables']} "
                f"variables conclues NORMALES (Shapiro n<50, D'Agostino n>=20) — "
                f"ce choix conditionne la méthode de corrélation rapportée."
            ),
            "source": "normality",
        })
    return q


def _build_defenses(vigilances: list[str]) -> list[dict[str, str]]:
    """Défense préparée pour chaque point de vigilance du Skeptic Engine —
    stratégie de réponse générique (aucun chiffre inventé)."""
    out = []
    for v in vigilances:
        out.append({
            "vigilance": v,
            "defense_preparee": (
                "Reconnaissez le point, puis citez la donnée qui le borne : "
                "taille d'échantillon et niveau de confiance pour la puissance, "
                "IC bootstrap pour la précision de l'effet, q-value (correction "
                "de multiplicité) pour le risque de faux positif, audit_log pour "
                "le traitement des données. Ces éléments sont dans resultats.json."
            ),
        })
    return out


def _memo(corr: dict | None, inf: dict | None,
          conf: dict | None) -> list[dict[str, str]]:
    """Les 3 chiffres à avoir en tête en entrant dans la salle."""
    memo: list[dict[str, str]] = []
    if inf and inf.get("p_value") is not None:
        memo.append({
            "chiffre": f"p = {_fmt(inf['p_value'])} ({inf.get('test_name') or 'test principal'})",
            "ce_que_ca_prouve": inf.get("decision") or "décision statistique du test principal",
        })
    if conf and conf.get("score_global") is not None:
        memo.append({
            "chiffre": f"score de confiance {conf['score_global']} (niveau {conf.get('niveau')})",
            "ce_que_ca_prouve": "qualité globale et limites de l'analyse",
        })
    if corr and corr.get("top3"):
        t = corr["top3"][0]
        memo.append({
            "chiffre": (
                f"r = {_fmt(t['r'])} pour {t['paire']} "
                + (f"(q = {_fmt(t['p_adjusted'])})" if t.get("p_adjusted") is not None else "")
            ).strip(),
            "ce_que_ca_prouve": "la corrélation la plus forte du dataset",
        })
    return memo[:3]


# ── Assemblage ────────────────────────────────────────────────────────────────

def build_defense_pack(analysis_id: str, user_id: str) -> dict[str, Any]:
    analysis = db.get_analysis(analysis_id, user_id)
    if analysis is None:
        raise ValueError(f"analysis_id '{analysis_id}' introuvable pour cet utilisateur.")
    if analysis["status"] != "done":
        raise ValueError(
            f"L'analyse n'est pas terminée (statut : '{analysis['status']}'). "
            "Attendez 'done' avant de préparer la soutenance."
        )
    result = analysis.get("result")
    if not isinstance(result, dict):
        raise ValueError("Résultat d'analyse invalide ou absent.")

    pipeline = _pipeline_of(result)
    ident = _identity(pipeline, analysis)
    norm = _normality_summary(pipeline)
    corr = _correlation_summary(pipeline)
    inf = _inference_summary(pipeline)
    conf = _confidence_summary(pipeline)
    audit = _audit_summary(pipeline)

    vigilances = (conf or {}).get("points_de_vigilance") or []
    questions = _build_questions(pipeline, ident, norm, corr, inf, conf, audit)

    return {
        "analysis_id": analysis_id,
        "generateur": "deterministe (aucun LLM, aucun recalcul — valeurs citées du résultat persisté)",
        "fiche_identite": ident,
        "questions_probables": questions,
        "defenses_points_de_vigilance": _build_defenses(vigilances),
        "memo_derniere_ligne": _memo(corr, inf, conf),
        "n_questions": len(questions),
    }


@router.get("/{analysis_id}")
def http_get_defense(
    analysis_id: str,
    current_user: dict = Depends(auth.get_current_user),
) -> dict[str, Any]:
    try:
        return build_defense_pack(analysis_id, current_user["user_id"])
    except ValueError as e:
        status = 404 if "introuvable" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
