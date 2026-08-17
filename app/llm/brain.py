"""
QUANTA — brain.py (v2)
Couche d'intelligence linguistique : traduit le texte libre de l'utilisateur
en intention structurée (AnalysisIntent), et transforme les résultats
statistiques bruts (issus de orchestrator.py) en interprétation à 3 niveaux
(technique / analytique / décisionnel).

Architecture agnostique au provider LLM :
- Un seul point de contact avec l'extérieur : call_llm() (API compatible
  OpenAI chat.completions -- couvre Groq, OpenRouter, Gemini compat, et
  plus tard Anthropic/OpenAI directement avec un léger adaptateur).
- Tout le reste du fichier (construction de prompt, parsing JSON,
  validation anti-hallucination) est indépendant du provider.
- Passer d'un provider gratuit à une clé payante (Claude Haiku, GPT-4o-mini)
  ne nécessite de modifier QUE la configuration LLM / les variables
  d'environnement -- aucune autre ligne de ce fichier ne change.

Règle d'or héritée du programme 90 jours (Jour 18) : si tous les providers
LLM échouent, on ne plante JAMAIS -- on retourne les résultats bruts déjà
calculés par orchestrator.py, sans interprétation textuelle, plutôt que
de lever une exception.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from app.compute.test_selector import AnalysisIntent

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION LLM — agnostique au provider
# ═══════════════════════════════════════════════════════════════════════════════
#
# Tous les providers ci-dessous exposent une API compatible avec le format
# OpenAI chat.completions (POST {base_url}/chat/completions). Migrer vers
# une clé payante plus tard = changer ces variables d'environnement, rien
# d'autre dans le code.
#
# Variables d'environnement attendues (.env, jamais commit) :
#   PRIMARY_API_KEY, PRIMARY_BASE_URL, PRIMARY_MODEL
#   FALLBACK_API_KEY, FALLBACK_BASE_URL, FALLBACK_MODEL   (optionnel)

REQUEST_TIMEOUT_SECONDS = 90
MAX_RETRIES_PER_PROVIDER = 3
RETRY_BACKOFF_SECONDS = 5


def _llm_config() -> dict[str, dict[str, str]]:
    """Lit la configuration LLM à chaque appel (tests sans clé, hot-reload .env)."""
    return {
        "primary": {
            "api_key": os.environ.get("PRIMARY_API_KEY", os.environ.get("GROQ_API_KEY", "")),
            "base_url": os.environ.get("PRIMARY_BASE_URL", "https://api.groq.com/openai/v1"),
            "model": os.environ.get("PRIMARY_MODEL", "llama-3.1-70b-versatile"),
        },
        "fallback": {
            "api_key": os.environ.get("FALLBACK_API_KEY", os.environ.get("OPENROUTER_API_KEY", "")),
            "base_url": os.environ.get("FALLBACK_BASE_URL", "https://openrouter.ai/api/v1"),
            "model": os.environ.get("FALLBACK_MODEL", "moonshotai/kimi-k2-instruct"),
        },
    }


class LLMUnavailableError(Exception):
    """Levée uniquement en interne -- jamais propagée au-delà de ce module."""
    pass


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2500,
    temperature: float = 0.2,
) -> str | None:
    """
    Point de contact UNIQUE avec l'extérieur. Essaie le provider principal,
    puis le provider de secours en cas d'échec (429, timeout, erreur réseau).

    Retourne le texte brut généré, ou None si les deux providers ont échoué
    après leurs retries respectifs (jamais d'exception levée vers l'appelant
    -- c'est à text_to_intent()/generate_interpretation() de décider du
    comportement de repli).
    """
    for provider_name in ("primary", "fallback"):
        cfg = _llm_config()[provider_name]
        if not cfg["api_key"]:
            logger.warning(f"LLM provider {provider_name}: no API key configured")
            continue

        logger.info(f"Attempting LLM call with provider {provider_name}, model {cfg['model']}")

        for attempt in range(MAX_RETRIES_PER_PROVIDER):
            try:
                response = requests.post(
                    f"{cfg['base_url']}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {cfg['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": cfg["model"],
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"LLM call succeeded with provider {provider_name} on attempt {attempt + 1}")
                    return data["choices"][0]["message"]["content"]

                if response.status_code == 429:
                    logger.warning(f"LLM rate limit (429) from {provider_name}, attempt {attempt + 1}, backing off")
                    time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue

                logger.error(f"LLM call failed with status {response.status_code} from {provider_name}: {response.text[:200]}")
                break

            except requests.exceptions.Timeout:
                logger.warning(f"LLM timeout from {provider_name} on attempt {attempt + 1}")
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"LLM request exception from {provider_name} on attempt {attempt + 1}: {str(e)}")
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue

    logger.error("All LLM providers failed after retries")
    return None


def _extract_json(raw_text: str) -> dict | None:
    """Extrait un objet JSON d'une réponse LLM, tolérant markdown et prose."""
    if raw_text is None:
        return None

    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEXTE LIBRE -> INTENTION STRUCTURÉE
# ═══════════════════════════════════════════════════════════════════════════════

INTENT_SYSTEM_PROMPT = """Tu es un module de traduction d'intention pour QUANTA, un outil d'analyse statistique.

Ton unique tâche : convertir la demande en langage naturel d'un utilisateur en un objet JSON structuré décrivant son intention d'analyse statistique.

Tu reçois aussi la liste des colonnes disponibles dans le dataset (avec leur type : numérique ou catégoriel). Tu DOIS choisir target_col/group_col/predictor_cols UNIQUEMENT parmi ces colonnes -- jamais en inventer une qui n'existe pas dans la liste fournie.

Réponds STRICTEMENT avec un objet JSON, sans aucun texte avant ou après, au format suivant :

{
  "action": "compare_groups" | "correlation" | "association" | "regression" | "descriptive_only",
  "target_col": "<nom_colonne_ou_null>",
  "group_col": "<nom_colonne_ou_null>",
  "predictor_cols": ["<colonne1>", "<colonne2>"],
  "paired": false
}

Règles de choix de l'action :
- "compare_groups" : l'utilisateur veut comparer une variable numérique entre des catégories (ex: "comparer le revenu entre régions", "le salaire diffère-t-il selon le diplôme ?")
- "correlation" : l'utilisateur veut savoir si deux variables numériques sont liées (ex: "est-ce que l'âge influence le salaire ?", "lien entre température et ventes")
- "association" : l'utilisateur veut savoir si deux variables catégorielles sont liées (ex: "le genre influence-t-il le choix du produit ?")
- "regression" : l'utilisateur veut prédire/expliquer une variable par plusieurs autres (ex: "qu'est-ce qui explique le revenu ?", "prédire le churn")
- "descriptive_only" : la demande est vague, générale, ou ne correspond à aucun cas ci-dessus (ex: "analyse ce dataset", "donne-moi un résumé")

Si tu n'es pas sûr du nom exact d'une colonne, choisis la colonne de la liste fournie qui correspond le mieux sémantiquement à ce que l'utilisateur a écrit (ex: l'utilisateur écrit "salaire", la colonne s'appelle "income" -> utilise "income").

Si l'intention est ambiguë ou ne correspond à aucune colonne disponible, utilise action="descriptive_only" avec tous les champs colonne à null plutôt que de deviner au hasard.

Ne JAMAIS inclure de texte explicatif, de balises markdown, ou quoi que ce soit d'autre que l'objet JSON brut."""


def text_to_intent(
    user_query: str,
    available_numeric_cols: list[str],
    available_cat_cols: list[str],
) -> AnalysisIntent:
    """
    Traduit le texte libre de l'utilisateur en AnalysisIntent structuré.

    GARANTIT toujours un AnalysisIntent valide en retour, même en cas
    d'échec LLM total (retombe alors sur action="descriptive_only").
    """
    columns_description = (
        f"Colonnes numériques disponibles : {available_numeric_cols}\n"
        f"Colonnes catégorielles disponibles : {available_cat_cols}"
    )
    user_prompt = f"{columns_description}\n\nDemande de l'utilisateur : \"{user_query}\""

    raw_response = call_llm(INTENT_SYSTEM_PROMPT, user_prompt, max_tokens=400, temperature=0.1)
    parsed = _extract_json(raw_response) if raw_response else None

    if parsed is None:
        return AnalysisIntent(action="descriptive_only", raw_query=user_query)

    all_known_cols = set(available_numeric_cols) | set(available_cat_cols)

    def _clean_col(val: Any) -> str | None:
        if val is None or val == "null" or val not in all_known_cols:
            return None
        return str(val)

    predictor_cols = parsed.get("predictor_cols") or []
    if not isinstance(predictor_cols, list):
        predictor_cols = []
    predictor_cols = [c for c in predictor_cols if c in all_known_cols]

    valid_actions = {"compare_groups", "correlation", "association", "regression", "descriptive_only"}
    action = parsed.get("action")
    if action not in valid_actions:
        action = "descriptive_only"

    return AnalysisIntent(
        action=action,
        target_col=_clean_col(parsed.get("target_col")),
        group_col=_clean_col(parsed.get("group_col")),
        predictor_cols=predictor_cols,
        paired=bool(parsed.get("paired", False)),
        raw_query=user_query,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. RÉSULTATS BRUTS -> INTERPRÉTATION 3 NIVEAUX (UN SEUL APPEL LLM)
# ═══════════════════════════════════════════════════════════════════════════════

INTERPRETATION_SYSTEM_PROMPT = """Tu es un statisticien académique senior rédigeant l'interprétation d'un rapport d'analyse pour QUANTA.

RÈGLE ABSOLUE ET NON-NÉGOCIABLE : tu ne calcules JAMAIS aucun chiffre. Tu ne fais que CITER et REFORMULER les valeurs numériques exactes fournies dans le JSON de résultats que tu reçois. Si une statistique, un p-value, ou un coefficient n'est pas explicitement présent dans les données fournies, tu ne dois jamais l'inventer, l'estimer, ou l'arrondir différemment. Toute violation de cette règle invalide ton interprétation.

RÈGLE ABSOLUE SUR LES P-VALUES : Toujours écrire les p-values avec exactement 3 décimales dans le texte (ex: 0.179, 0.412). Jamais 5 décimales (0.17917). Si p < 0.001, écrire 'p < 0.001'.

Pour CHAQUE test statistique présent dans les résultats, tu dois produire 3 niveaux d'interprétation distincts :

1. NIVEAU TECHNIQUE : formulation rigoureuse avec hypothèses H0/H1 explicites, statistique de test, p-value, décision statistique (rejet ou non de H0 au seuil de 5%). Langage de statisticien.

2. NIVEAU ANALYTIQUE : reformulation pour un rapport, sans jargon statistique excessif mais toujours précis sur ce que le résultat signifie concrètement pour les variables étudiées. Doit rester compréhensible par quelqu'un avec une formation générale en sciences sociales ou en gestion.

3. NIVEAU DÉCISIONNEL : conclusion opérationnelle orientée action, formulée pour un décideur qui n'a pas de formation statistique. Que doit-il retenir et, si pertinent, quelle action cela suggère-t-il ?

INTERPRÉTATION SPÉCIFIQUE POUR L'ACM (Analyse des Correspondances Multiples) :
Si les résultats contiennent une section "acm" avec les champs suivants :
- inertia_pct : pourcentage d'inertie expliquée par chaque dimension
- cumulative_inertia : pourcentage cumulé d'inertie
- top_contributions_dim1 : contributions des modalités à l'axe 1
- interpretation_note : note d'interprétation générée par le système

Pour l'ACM, adapte les 3 niveaux comme suit :
1. NIVEAU TECHNIQUE : mentionne le nombre de variables catégorielles analysées, le pourcentage d'inertie expliquée par les axes 1 et 2, et les modalités les plus contributives à l'axe 1. Explique que l'ACM est une technique d'analyse factorielle pour données catégorielles.
2. NIVEAU ANALYTIQUE : interprète les proximités entre modalités sur le plan factoriel (les modalités proches ont des profils similaires). Mentionne les dimensions qui expliquent le plus d'inertie et ce que cela suggère sur la structure des données.
3. NIVEAU DÉCISIONNEL : synthétise les principaux patterns d'association entre variables catégorielles et suggère des actions ou des investigations complémentaires basées sur ces associations.

Tu dois aussi produire :
- Un résumé exécutif global (3-5 phrases, niveau décisionnel) qui synthétise l'ensemble de l'analyse
- Une liste de limites/réserves méthodologiques basées sur les points_de_vigilance fournis

Réponds STRICTEMENT avec un objet JSON au format suivant, sans aucun texte avant ou après :

{
  "resume_executif": "...",
  "interpretation_principale": {
    "niveau_technique": "...",
    "niveau_analytique": "...",
    "niveau_decisionnel": "..."
  },
  "limites_et_reserves": ["...", "..."],
  "conclusion_generale": "..."
}

Ne JAMAIS inclure de balises markdown ou de texte hors de cet objet JSON."""


def _build_results_summary_for_prompt(analysis_result: dict[str, Any]) -> str:
    """Résumé condensé des résultats pour le prompt LLM (sans données brutes volumineuses)."""
    diag = analysis_result.get("diagnosis", {})
    inference = analysis_result.get("inference", {})
    confidence = analysis_result.get("confidence_score", {})
    
    # On n'envoie QUE les statistiques calculées, jamais les données brutes
    result = inference.get("result", {})
    
    # Nettoyer le résultat : supprimer les champs volumineux avant envoi au LLM
    result_clean = {}
    for key, value in result.items():
        # Exclure les champs contenant des données brutes volumineuses
        if key in ["raw_data", "data", "values", 
                   "observations", "sample",
                   "r_script", "stata_script",
                   "python_script", "charts",
                   "distribution_charts", "audit_log"]:
            continue
        # Limiter les listes longues
        if isinstance(value, list) and len(value) > 20:
            result_clean[key] = value[:20]
            result_clean[f"{key}_truncated"] = True
        elif isinstance(value, str) and len(value) > 500:
            result_clean[key] = value[:500] + "..."
        else:
            result_clean[key] = value
    
    summary = {
        "dataset": {
            "n_rows": diag.get("n_rows"),
            "n_cols": diag.get("n_cols"),
            "type": diag.get("dataset_type"),
        },
        "action": inference.get("action_executed"),
        "query": inference.get(
            "intent_received", {}
        ).get("raw_query", "")[:200],
        "result": result_clean,
        "confidence": {
            "score": confidence.get("score_global"),
            "niveau": confidence.get("niveau"),
            "vigilance": confidence.get(
                "points_de_vigilance", []
            )[:5],
        },
    }
    
    # Mode autonome : fournir l'ensemble des tests pour une interprétation globale.
    tests_effectues = analysis_result.get("tests_effectues")
    if isinstance(tests_effectues, list) and tests_effectues:
        # Tronquer chaque test pour éviter l'explosion
        tests_clean = []
        for test in tests_effectues[:10]:  # Max 10 tests
            test_clean = {}
            for key, value in test.items():
                if key in ["raw_data", "data", "values", 
                           "observations", "sample",
                           "r_script", "stata_script",
                           "python_script", "charts",
                           "distribution_charts", "audit_log"]:
                    continue
                if isinstance(value, list) and len(value) > 20:
                    test_clean[key] = value[:20]
                elif isinstance(value, str) and len(value) > 500:
                    test_clean[key] = value[:500] + "..."
                else:
                    test_clean[key] = value
            tests_clean.append(test_clean)
        summary["tests_effectues"] = tests_clean
        summary["mode"] = "analyse_autonome_multi_tests"
        summary["consigne"] = (
            "Interprète l'ENSEMBLE des tests listés dans tests_effectues. "
            "Le résumé exécutif et les trois niveaux doivent couvrir tous "
            "les résultats significatifs, pas seulement le test principal."
        )
    
    json_str = json.dumps(
        summary, ensure_ascii=False, indent=2
    )
    
    # Limite absolue : 3000 tokens max (environ 12 000 caractères)
    MAX_CHARS = 12000
    if len(json_str) > MAX_CHARS:
        # Tronquer proprement
        json_str = json_str[:MAX_CHARS]
        json_str += '\n... [données tronquées] ...'
    
    return json_str


def _extract_p_value(analysis: dict[str, Any]) -> float | None:
    result = analysis.get("inference", {})
    if not isinstance(result, dict):
        return None
    test_result = result.get("result", {})
    if not isinstance(test_result, dict):
        return None
    p = test_result.get("p_value")
    if p is None:
        return None
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def _pick_most_significant_index(analyses: list[dict[str, Any]]) -> int:
    """
    Index du résultat le plus significatif :
    1) p-value la plus basse parmi les tests disposant d'une p-value
    2) sinon score de confiance le plus élevé
    """
    if not analyses:
        return 0

    best_p_idx: int | None = None
    best_p = float("inf")
    for i, analysis in enumerate(analyses):
        p = _extract_p_value(analysis)
        if p is not None and p < best_p:
            best_p = p
            best_p_idx = i
    if best_p_idx is not None:
        return best_p_idx

    best_idx = 0
    best_score = float("-inf")
    for i, analysis in enumerate(analyses):
        conf = analysis.get("confidence_score", {})
        score = conf.get("score_global") if isinstance(conf, dict) else None
        try:
            score_f = float(score) if score is not None else float("-inf")
        except (TypeError, ValueError):
            score_f = float("-inf")
        if score_f > best_score:
            best_score = score_f
            best_idx = i
    return best_idx


def _summarize_analysis_for_multi(intent: AnalysisIntent, analysis: dict[str, Any]) -> dict[str, Any]:
    """Résumé compact d'un run pour le LLM et le rapport multi-tests."""
    inference = analysis.get("inference", {}) if isinstance(analysis.get("inference"), dict) else {}
    test_result = inference.get("result", {}) if isinstance(inference.get("result"), dict) else {}
    confidence = (
        analysis.get("confidence_score", {})
        if isinstance(analysis.get("confidence_score"), dict)
        else {}
    )
    return {
        "intent": asdict(intent),
        "action_executed": inference.get("action_executed"),
        "test": test_result.get("test"),
        "statistic": test_result.get("statistic", test_result.get("odds_ratio")),
        "p_value": test_result.get("p_value"),
        "dof": test_result.get("dof", test_result.get("df")),
        "significant": test_result.get("significant"),
        "status": test_result.get("status"),
        "reason": test_result.get("reason"),
        "score_confiance": confidence.get("score_global"),
        "niveau_confiance": confidence.get("niveau"),
        "result": test_result,
        "filename": analysis.get("filename"),
        "diagnosis": {
            "n_rows": (analysis.get("diagnosis") or {}).get("n_rows"),
            "n_cols": (analysis.get("diagnosis") or {}).get("n_cols"),
            "dataset_type": (analysis.get("diagnosis") or {}).get("dataset_type"),
        },
    }


def _collect_numbers(obj: Any, acc: list[float]) -> None:
    """Collecte récursivement les valeurs numériques brutes (floats natifs)."""
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, acc)


def _numbers_match(val: float, source_numbers: list[float]) -> bool:
    """
    Compare une valeur extraite du texte aux sources avec tolérance d'arrondi :
    différence absolue <= 0.01 OU différence relative <= 1%.
    """
    for source_val in source_numbers:
        if abs(val - source_val) <= 0.01:
            return True
        if source_val != 0 and abs(val - source_val) / abs(source_val) <= 0.01:
            return True
    return False


def _has_suspicious_leading_zero(raw_num: str) -> bool:
    """
    Détecte un format numérique anormal : zéro de tête significatif (ex: "025,02").
    "0,05" (zéro seul avant la virgule) reste normal.
    """
    integer_part = re.split(r"[.,]", raw_num.lstrip("-"))[0]
    return len(integer_part) > 1 and integer_part.startswith("0")


def _validate_no_hallucinated_numbers(
    generated_text: str, source_data: dict[str, Any]
) -> dict[str, list[str]]:
    """
    Vérifie les nombres du texte généré contre les données sources.

    Retourne :
      - nombres_suspects : absents des sources (±1%)
      - formats_anormaux : zéro de tête suspect (fusion probable)
    """
    standard_alpha_thresholds = {0.05, 0.01, 0.001, 0.10, 0.005}

    source_numbers: list[float] = []
    _collect_numbers(source_data, source_numbers)

    number_pattern = r"-?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?"
    found_in_text = re.findall(number_pattern, generated_text)
    suspects: list[str] = []
    anomalous_formats: list[str] = []

    for raw_num in found_in_text:
        if _has_suspicious_leading_zero(raw_num):
            anomalous_formats.append(raw_num)
            continue

        normalized = raw_num.replace(",", ".")
        try:
            val = float(normalized)
        except ValueError:
            continue

        if 0 <= val <= 12 and val == int(val):
            continue
        if 1900 <= val <= 2100:
            continue
        if round(abs(val), 3) in standard_alpha_thresholds:
            continue

        if not _numbers_match(val, source_numbers):
            suspects.append(raw_num)

    return {
        "nombres_suspects": sorted(set(suspects)),
        "formats_anormaux": sorted(set(anomalous_formats)),
    }


def generate_interpretation(analysis_result: dict[str, Any]) -> dict[str, Any]:
    """
    Transforme le résultat de orchestrator.run_full_analysis() en interprétation
    3 niveaux. En cas d'échec LLM total : llm_available=False + raw_analysis.
    """
    if analysis_result.get("status") != "ok":
        return {
            "llm_available": False,
            "reason": "Le pipeline de calcul a échoué -- aucune interprétation possible.",
            "raw_analysis": analysis_result,
        }

    results_summary = _build_results_summary_for_prompt(analysis_result)
    user_prompt = f"Voici les résultats de l'analyse statistique à interpréter :\n\n{results_summary}"

    raw_response = call_llm(
        INTERPRETATION_SYSTEM_PROMPT, user_prompt, max_tokens=2500, temperature=0.2
    )

    if raw_response is None:
        return {
            "llm_available": False,
            "reason": (
                "Les providers LLM (principal et secours) sont indisponibles "
                "actuellement -- les résultats statistiques bruts restent "
                "fiables et consultables ci-dessous, sans interprétation "
                "textuelle pour le moment."
            ),
            "raw_analysis": analysis_result,
        }

    parsed = _extract_json(raw_response)

    if parsed is None:
        return {
            "llm_available": False,
            "reason": "Réponse du LLM reçue mais non interprétable (format JSON invalide).",
            "raw_llm_response": raw_response,
            "raw_analysis": analysis_result,
        }

    source_data_for_validation = {
        "inference": analysis_result.get("inference", {}),
        "confidence_score": analysis_result.get("confidence_score", {}),
        "diagnosis": analysis_result.get("diagnosis", {}),
    }
    full_generated_text = json.dumps(parsed, ensure_ascii=False)
    hallucination_check = _validate_no_hallucinated_numbers(
        full_generated_text, source_data_for_validation
    )
    suspect_numbers = hallucination_check["nombres_suspects"]
    anomalous_formats = hallucination_check["formats_anormaux"]

    warnings: list[str] = []
    if suspect_numbers:
        warnings.append(
            f"{len(suspect_numbers)} valeur(s) numérique(s) dans le texte généré "
            f"n'ont pas pu être rapprochées des données sources -- à vérifier "
            f"manuellement avant publication du rapport."
        )
    if anomalous_formats:
        warnings.append(
            f"{len(anomalous_formats)} nombre(s) au format anormal détecté(s) "
            f"(zéro de tête suspect, ex: {anomalous_formats[0]!r}) -- probable "
            f"fusion accidentelle de deux valeurs lors de la génération, à "
            f"vérifier en priorité avant publication."
        )

    return validate_conclusions(
        {
            "llm_available": True,
            "resume_executif": parsed.get("resume_executif", ""),
            "interpretation_principale": parsed.get("interpretation_principale", {}),
            "limites_et_reserves": parsed.get("limites_et_reserves", []),
            "conclusion_generale": parsed.get("conclusion_generale", ""),
            "anti_hallucination_check": {
                "nombres_suspects_detectes": suspect_numbers,
                "formats_anormaux_detectes": anomalous_formats,
                "avertissement": " ".join(warnings) if warnings else None,
            },
        },
        analysis_result,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SKEPTIC ENGINE — cohérence conclusions LLM ↔ résultats statistiques
# ═══════════════════════════════════════════════════════════════════════════════

_OVERCLAIM_PHRASES: tuple[str, ...] = (
    "significatif",
    "significative",
    "différence notable",
    "corrélation forte",
)

_OVERCLAIM_NUANCE_PHRASES: tuple[str, ...] = (
    "non significatif",
    "non significative",
    "pas significatif",
    "pas significative",
    "n'est pas significatif",
    "n'est pas significative",
    "aucune différence significative",
    "pas de corrélation significative",
    "pas de différence significative",
    "sans signification",
)

_UNDERCLAIM_PHRASES: tuple[str, ...] = (
    "aucune différence",
    "non significatif",
    "non significative",
    "pas de lien",
)


def _flatten_interpretation_text(interpretation: dict[str, Any]) -> str:
    """Concatène les champs textuels de l'interprétation pour contrôle."""
    parts: list[str] = []
    for key in ("resume_executif", "conclusion_generale"):
        value = interpretation.get(key)
        if isinstance(value, str):
            parts.append(value)
    principale = interpretation.get("interpretation_principale")
    if isinstance(principale, dict):
        for key in ("niveau_technique", "niveau_analytique", "niveau_decisionnel"):
            value = principale.get(key)
            if isinstance(value, str):
                parts.append(value)
    elif isinstance(principale, str):
        parts.append(principale)
    for key in ("summary", "level_1", "level_2", "level_3"):
        value = interpretation.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _collect_p_values_from_analysis(analysis_result: dict[str, Any]) -> list[float]:
    """Collecte les p-values réelles (hors descriptive_only) pour le Skeptic Engine."""
    values: list[float] = []

    def _add(raw: Any) -> None:
        if raw is None:
            return
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            return

    inference = analysis_result.get("inference")
    if isinstance(inference, dict):
        action = str(inference.get("action_executed") or "")
        if action != "descriptive_only":
            result = inference.get("result")
            if isinstance(result, dict):
                _add(result.get("p_value"))

    tests = analysis_result.get("tests_effectues")
    if isinstance(tests, list):
        for entry in tests:
            if not isinstance(entry, dict):
                continue
            action = str(entry.get("action_executed") or "")
            if not action:
                intent = entry.get("intent")
                if isinstance(intent, dict):
                    action = str(intent.get("action") or "")
            if action == "descriptive_only":
                continue
            _add(entry.get("p_value"))
            result = entry.get("result")
            if isinstance(result, dict):
                _add(result.get("p_value"))

    # Dédupliquer en conservant l'ordre (tolérance 1e-12).
    unique: list[float] = []
    for p in values:
        if not any(abs(p - u) < 1e-12 for u in unique):
            unique.append(p)
    return unique


def _text_claims_significance_without_nuance(text: str) -> bool:
    """True si le texte affirme une significativité sans les nuances de négation."""
    lower = text.lower()
    cleaned = lower
    for nuance in _OVERCLAIM_NUANCE_PHRASES:
        cleaned = cleaned.replace(nuance, " ")
    return any(phrase in cleaned for phrase in _OVERCLAIM_PHRASES)


def _text_denies_effect(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _UNDERCLAIM_PHRASES)


def validate_conclusions(
    interpretation: dict[str, Any],
    analysis_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Skeptic Engine : vérifie la cohérence entre conclusions LLM et p-values.

    Ne bloque jamais la génération — ajoute uniquement des alertes :
      skeptic_engine_alert / skeptic_engine_message
    """
    if not isinstance(interpretation, dict):
        return interpretation

    # Ne pas alerter si le LLM n'a pas produit d'interprétation textuelle.
    if interpretation.get("llm_available") is False:
        return interpretation

    p_values = _collect_p_values_from_analysis(analysis_result)
    if not p_values:
        return interpretation

    text = _flatten_interpretation_text(interpretation)
    if not text.strip():
        return interpretation

    all_non_significant = all(p > 0.05 for p in p_values)
    all_significant = all(p < 0.05 for p in p_values)
    messages: list[str] = []

    if all_non_significant and _text_claims_significance_without_nuance(text):
        messages.append(
            "Skeptic Engine : p-value(s) > 0,05 mais l'interprétation évoque "
            "une significativité / différence notable / corrélation forte "
            "sans nuance — conclusion potentiellement incohérente."
        )

    if all_significant and _text_denies_effect(text):
        messages.append(
            "Skeptic Engine : p-value(s) < 0,05 mais l'interprétation suggère "
            "l'absence d'effet (aucune différence / non significatif / pas de "
            "lien) — conclusion potentiellement incohérente."
        )

    # Cas mixte : alerter seulement sur un déni global d'effet.
    if not all_non_significant and not all_significant:
        if "aucune différence" in text.lower() or "pas de lien" in text.lower():
            messages.append(
                "Skeptic Engine : résultats mixtes (significatifs et non "
                "significatifs) mais le texte nie globalement tout effet — "
                "vérifier la formulation."
            )

    if not messages:
        return interpretation

    enriched = dict(interpretation)
    enriched["skeptic_engine_alert"] = True
    enriched["skeptic_engine_message"] = " ".join(messages)
    return enriched


def analyze_with_brain(
    user_query: str | None,
    available_numeric_cols: list[str],
    available_cat_cols: list[str],
    run_analysis_fn,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Enchaîne text_to_intent() -> run_analysis_fn(intent) ->
    generate_interpretation(). run_analysis_fn est injecté pour éviter un
    couplage dur avec orchestrator.py.

    Si user_query est vide/None : mode autonome via auto_intent(diagnosis).
    """
    query_text = (user_query or "").strip()

    # ── Mode autonome : aucune requête utilisateur ──────────────────────────
    if not query_text:
        from app.orchestrator import auto_intent

        diagnosis_payload: dict[str, Any] = dict(diagnosis or {})
        diagnosis_payload.setdefault("numeric_cols", available_numeric_cols)
        diagnosis_payload.setdefault("cat_cols", available_cat_cols)

        intents = auto_intent(diagnosis_payload)
        analyses: list[dict[str, Any]] = [run_analysis_fn(intent) for intent in intents]

        primary_idx = _pick_most_significant_index(analyses)
        primary_intent = intents[primary_idx]
        primary_analysis = analyses[primary_idx]

        tests_effectues = [
            _summarize_analysis_for_multi(intent, analysis)
            for intent, analysis in zip(intents, analyses, strict=True)
        ]

        # Enrichir le payload d'interprétation pour couvrir TOUS les tests.
        interpretation_payload = dict(primary_analysis)
        interpretation_payload["tests_effectues"] = tests_effectues
        # Consolider les points de vigilance de tous les runs.
        merged_vigilance: list[str] = []
        for analysis in analyses:
            conf = analysis.get("confidence_score", {})
            if isinstance(conf, dict):
                for note in conf.get("points_de_vigilance", []) or []:
                    if note not in merged_vigilance:
                        merged_vigilance.append(note)
        if merged_vigilance:
            conf_primary = dict(interpretation_payload.get("confidence_score") or {})
            conf_primary["points_de_vigilance"] = merged_vigilance
            interpretation_payload["confidence_score"] = conf_primary

        interpretation = generate_interpretation(interpretation_payload)

        return {
            "mode": "auto",
            "intent": asdict(primary_intent),
            "intents": [asdict(intent) for intent in intents],
            "analysis": primary_analysis,
            "analyses": [
                {"intent": asdict(intent), "analysis": analysis}
                for intent, analysis in zip(intents, analyses, strict=True)
            ],
            "tests_effectues": tests_effectues,
            "interpretation": interpretation,
        }

    # ── Mode requête : comportement historique inchangé ─────────────────────
    intent = text_to_intent(query_text, available_numeric_cols, available_cat_cols)
    analysis_result = run_analysis_fn(intent)
    
    # S'assurer que les charts sont au bon niveau pour le générateur PDF
    # Si analysis_result a déjà "charts" au niveau racine (orchestrator),
    # on ne l'emballe pas dans "analysis" pour éviter l'imbrication
    if "charts" in analysis_result and "analysis" not in analysis_result:
        # Résultat direct de l'orchestrateur
        interpretation = generate_interpretation(analysis_result)
        return {
            "mode": "query",
            "intent": asdict(intent),
            "analysis": analysis_result,  # charts sont déjà dedans
            "interpretation": interpretation,
        }
    else:
        # Comportement historique
        interpretation = generate_interpretation(analysis_result)
        return {
            "mode": "query",
            "intent": asdict(intent),
            "analysis": analysis_result,
            "interpretation": interpretation,
        }
