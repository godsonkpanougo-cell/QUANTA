"""
QUANTA — brain.py v3
Le LLM reçoit les chiffres exacts de compute.py.
Il interprète, contextualise, rédige. Il ne calcule JAMAIS.
"""

import os
import asyncio
import json
import httpx
from typing import Any

# ── Clés API (depuis .env) ────────────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")

GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

GROQ_MODEL       = "llama-3.3-70b-versatile"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

MAX_RETRIES  = 3
RETRY_DELAYS = [8, 16, 24]


# ═══════════════════════════════════════════════════════════════════════════════
# APPEL LLM AVEC FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

async def call_llm(system_prompt: str, user_message: str,
                   max_tokens: int = 2000) -> str:
    """
    Appelle Groq → OpenRouter → Gemini avec retry intelligent.
    """

    # ── Groq ──────────────────────────────────────────────────────────────────
    if GROQ_API_KEY:
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0, connect=10.0, read=120.0)
                ) as client:
                    resp = await client.post(
                        GROQ_URL,
                        headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                                 "Content-Type": "application/json"},
                        json={"model": GROQ_MODEL, "max_tokens": max_tokens,
                              "temperature": 0.15,
                              "messages": [
                                  {"role": "system", "content": system_prompt},
                                  {"role": "user",   "content": user_message},
                              ]},
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        print(f"[BRAIN] ✓ Groq ({len(content)} chars)")
                        return content
                    elif resp.status_code == 429:
                        print(f"[BRAIN] Groq 429 — tentative {attempt+1}/{MAX_RETRIES} — attente {delay}s")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(delay)
                    else:
                        print(f"[BRAIN] Groq {resp.status_code}")
                        break
            except httpx.ReadTimeout:
                print(f"[BRAIN] Groq timeout — tentative {attempt+1}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
            except Exception as e:
                print(f"[BRAIN] Groq erreur : {e}")
                break

    print("[BRAIN] Groq épuisé → OpenRouter")

    # ── OpenRouter ────────────────────────────────────────────────────────────
    if OPENROUTER_API_KEY:
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0, connect=10.0, read=120.0)
                ) as client:
                    resp = await client.post(
                        OPENROUTER_URL,
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                 "Content-Type": "application/json"},
                        json={"model": OPENROUTER_MODEL, "max_tokens": max_tokens,
                              "temperature": 0.15,
                              "messages": [
                                  {"role": "system", "content": system_prompt},
                                  {"role": "user",   "content": user_message},
                              ]},
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        print(f"[BRAIN] ✓ OpenRouter ({len(content)} chars)")
                        return content
                    elif resp.status_code == 429:
                        print(f"[BRAIN] OR 429 — tentative {attempt+1}/{MAX_RETRIES} — attente {delay}s")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(delay)
                    else:
                        break
            except httpx.ReadTimeout:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
            except Exception as e:
                print(f"[BRAIN] OpenRouter erreur : {e}")
                break

    print("[BRAIN] OpenRouter épuisé → Gemini")

    # ── Gemini ────────────────────────────────────────────────────────────────
    if GEMINI_API_KEY:
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0, connect=10.0, read=120.0)
                ) as client:
                    combined = f"{system_prompt}\n\n{user_message}"
                    resp = await client.post(
                        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": combined}]}],
                              "generationConfig": {"maxOutputTokens": max_tokens,
                                                   "temperature": 0.15}},
                    )
                    if resp.status_code == 200:
                        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        print(f"[BRAIN] ✓ Gemini ({len(content)} chars)")
                        return content
                    elif resp.status_code == 429:
                        print(f"[BRAIN] Gemini 429 — tentative {attempt+1}/{MAX_RETRIES}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(delay)
                    else:
                        break
            except httpx.ReadTimeout:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
            except Exception as e:
                print(f"Erreur réelle : {str(e)}")
                break

    raise RuntimeError("Tous les LLM sont épuisés.")


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS SYSTÈME
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es QUANTA, un statisticien expert de niveau Doctorat avec 30 ans d'expérience.
Tu reçois des résultats statistiques DÉJÀ CALCULÉS de manière déterministe par des librairies Python (scipy, statsmodels, pandas).
TON RÔLE UNIQUE : interpréter ces chiffres exacts. Tu ne recalcules JAMAIS. Tu n'inventes JAMAIS de chiffres.
Si tu dois citer un chiffre, cite uniquement ceux qui t'ont été fournis.

Règles de rédaction :
- 3 niveaux systématiques : Technique (statisticien), Analytique (chercheur), Décisionnel (manager)
- Formulation H0/H1 explicite avant chaque conclusion de test
- Signale les résultats surprenants ou contre-intuitifs
- Recommandations opérationnelles concrètes
- Style : professionnel, précis, sans jargon inutile
- Langue de réponse : celle spécifiée dans la requête"""


# ═══════════════════════════════════════════════════════════════════════════════
# PHASES D'INTERPRÉTATION
# ═══════════════════════════════════════════════════════════════════════════════

async def _phase_diagnosis(compute: dict, language: str) -> str:
    user_msg = f"""[PHASE 1 — DIAGNOSTIC STRUCTUREL]
Langue de réponse : {language}

Données reçues du calcul déterministe :
- Fichier : {compute['diagnosis'].get('n_rows')} lignes × {compute['diagnosis'].get('n_cols')} colonnes
- Type de dataset : {compute['diagnosis'].get('dataset_type')}
- Variables numériques : {compute['diagnosis'].get('numeric_cols')}
- Variables catégorielles : {compute['diagnosis'].get('cat_cols')}
- Valeurs manquantes : {json.dumps(compute['diagnosis'].get('missing', {}), ensure_ascii=False)}
- Outliers détectés : {json.dumps(compute['diagnosis'].get('outlier_counts', {}), ensure_ascii=False)}
- Doublons : {compute['diagnosis'].get('n_duplicates')}

Décisions de nettoyage prises :
{chr(10).join(compute['cleaning'].get('cleaning_log', ['Aucune']))}

Rédige le diagnostic structurel complet (3 niveaux). Sois précis sur les implications
de chaque décision de nettoyage."""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1500)


async def _phase_descriptive(compute: dict, language: str) -> str:
    # Synthèse des stats clés pour ne pas dépasser les tokens
    desc_num = compute.get("descriptive", {}).get("descriptive_numeric", {})
    desc_cat = compute.get("descriptive", {}).get("descriptive_categorical", {})

    summary_num = {}
    for col, stats in list(desc_num.items())[:6]:
        summary_num[col] = {
            "n": stats["n"], "mean": stats["mean"], "std": stats["std"],
            "median": stats["median"], "skewness": stats["skewness"],
            "kurtosis": stats["kurtosis"], "cv_pct": stats.get("cv_pct"),
        }

    user_msg = f"""[PHASE 2 — STATISTIQUES DESCRIPTIVES]
Langue : {language}

Résultats calculés (vrais chiffres) :
{json.dumps(summary_num, ensure_ascii=False, indent=2)}

Variables catégorielles :
{json.dumps({col: {"n_unique": v["n_unique"], "mode": v["mode"], "mode_pct": v["mode_pct"]}
             for col, v in list(desc_cat.items())[:4]}, ensure_ascii=False, indent=2)}

Interprète ces statistiques descriptives (3 niveaux). Pour chaque variable numérique :
- Commente la forme de la distribution (asymétrie, aplatissement)
- Identifie les variables à forte variabilité (CV élevé)
- Donne des recommandations pour la suite de l'analyse."""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1800)


async def _phase_normality(compute: dict, language: str) -> str:
    norm = compute.get("normality", {})
    norm_summary = {}
    for col, res in list(norm.items())[:6]:
        sw = res.get("shapiro_wilk", {})
        norm_summary[col] = {
            "n": res.get("n"),
            "shapiro_W": sw.get("statistic"),
            "shapiro_p": sw.get("p_value"),
            "conclusion": res.get("conclusion"),
            "tests_recommandes": res.get("recommended_tests"),
        }

    user_msg = f"""[PHASE 3A — TESTS DE NORMALITÉ]
Langue : {language}

Résultats Shapiro-Wilk (calculés par scipy.stats) :
{json.dumps(norm_summary, ensure_ascii=False, indent=2)}

Pour chaque variable :
- Formule H0 / H1 explicitement
- Donne la décision (rejette / ne rejette pas H0) avec α=0.05
- Explique les implications pour le choix des tests suivants
- Recommande la famille de tests adaptée (paramétriques vs non-paramétriques)"""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1500)


async def _phase_correlation(compute: dict, language: str) -> str:
    corr = compute.get("correlation", {})
    pairs = corr.get("pairs", {})

    # Top 8 corrélations les plus fortes
    sorted_pairs = sorted(pairs.items(), key=lambda x: abs(x[1].get("r", 0)), reverse=True)[:8]

    user_msg = f"""[PHASE 3B — ANALYSE DES CORRÉLATIONS]
Langue : {language}
Méthode utilisée : {corr.get('method', 'spearman').capitalize()} (choix automatique selon normalité)

Corrélations significatives (calculées par scipy) :
{json.dumps(dict(sorted_pairs), ensure_ascii=False, indent=2)}

Interprète ces corrélations :
- Classe par force (très forte, forte, modérée, faible)
- Identifie les corrélations surprenantes ou importantes pour la prise de décision
- Signale tout risque de multicolinéarité pour la régression
- Propose des hypothèses explicatives pour les relations fortes"""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1500)


async def _phase_regression(compute: dict, language: str, objective: str) -> str:
    reg = compute.get("regression", {})
    if "error" in reg:
        return f"Régression non applicable : {reg['error']}"

    coef = reg.get("coefficients", {})
    sig_coef = {k: v for k, v in coef.items() if v.get("significant")}

    user_msg = f"""[PHASE 3C — RÉGRESSION OLS]
Langue : {language}
Objectif d'analyse : {objective}

Résultats OLS (calculés par statsmodels) :
Variable dépendante : {reg.get('y_variable')}
Variables explicatives : {reg.get('x_variables')}
N observations : {reg.get('n_obs')}
R² = {reg.get('R2')} | R² ajusté = {reg.get('R2_adj')}
F-statistic = {reg.get('F_stat')} (p = {reg.get('F_pvalue')})
RMSE = {reg.get('RMSE')}
AIC = {reg.get('AIC')} | BIC = {reg.get('BIC')}

Coefficients significatifs (p < 0.05) :
{json.dumps(sig_coef, ensure_ascii=False, indent=2)}

Diagnostics :
- Durbin-Watson = {reg.get('durbin_watson')} → {reg.get('dw_interpretation')}
- VIF : {json.dumps(reg.get('VIF', {}), ensure_ascii=False)}
- Breusch-Pagan : {json.dumps(reg.get('breusch_pagan', {}), ensure_ascii=False)}

Interprète les résultats OLS (3 niveaux) :
- Qualité globale du modèle (R², F-test avec H0/H1)
- Impact de chaque variable significative (coefficient + intervalle de confiance)
- Diagnostics : autocorrélation, hétéroscédasticité, multicolinéarité
- Recommandations pour améliorer le modèle si nécessaire"""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=2000)


async def _phase_report_forge(
    compute: dict, phases: dict, language: str,
    filename: str, objective: str, software: str
) -> str:
    reg = compute.get("regression", {})
    diag = compute.get("diagnosis", {})

    user_msg = f"""[PHASE FINALE — REPORT FORGE]
Langue : {language}
Fichier : {filename}
Objectif : {objective}
Logiciel de référence : {software}

Synthèse des analyses réalisées :
- {diag.get('n_rows')} observations, {diag.get('n_cols')} variables
- Dataset : {diag.get('dataset_type')}
- R² du modèle : {reg.get('R2', 'N/A')}
- Nombre de graphiques générés : {compute.get('n_charts', 0)}
- Scripts R et Stata fournis : OUI

Génère le RAPPORT FINAL PROFESSIONNEL complet avec ces sections :

## RÉSUMÉ EXÉCUTIF
(1 page, langage non-technique, pour un directeur)

## MÉTHODOLOGIE
(Justification des choix statistiques, références académiques)

## RÉSULTATS PRINCIPAUX
(Avec formulations H0/H1 et décisions formelles)

## CONCLUSIONS ET RECOMMANDATIONS OPÉRATIONNELLES
(Actions concrètes basées sur les résultats)

## LIMITES DE L'ANALYSE
(Biais potentiels, suggestions pour des études complémentaires)

Score de confiance : évalue la fiabilité globale de l'analyse sur 100 en justifiant."""
    return await call_llm(SYSTEM_PROMPT, user_msg, max_tokens=3000)


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE BRAIN PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_with_brain(
    compute_data: dict,
    filename: str,
    objective: str,
    software: str,
    language: str,
) -> dict[str, Any]:
    """
    Orchestre toutes les phases d'interprétation LLM.
    Reçoit les vrais chiffres de compute.py.
    """
    phases = {}
    PAUSE = 5   # secondes entre phases

    print("[BRAIN] Phase 1 — Diagnostic...")
    phases["diagnosis"] = await _phase_diagnosis(compute_data, language)
    await asyncio.sleep(PAUSE)

    print("[BRAIN] Phase 2 — Descriptives...")
    phases["descriptive"] = await _phase_descriptive(compute_data, language)
    await asyncio.sleep(PAUSE)

    print("[BRAIN] Phase 3A — Normalité...")
    phases["normality"] = await _phase_normality(compute_data, language)
    await asyncio.sleep(PAUSE)

    print("[BRAIN] Phase 3B — Corrélations...")
    phases["correlation"] = await _phase_correlation(compute_data, language)
    await asyncio.sleep(PAUSE)

    print("[BRAIN] Phase 3C — Régression OLS...")
    phases["regression"] = await _phase_regression(compute_data, language, objective)
    await asyncio.sleep(10)  # pause plus longue avant le rapport

    print("[BRAIN] Phase Finale — Report Forge...")
    phases["report_forge"] = await _phase_report_forge(
        compute_data, phases, language, filename, objective, software
    )

    # Extraction du score de confiance depuis le rapport final
    report_text = phases.get("report_forge", "")
    score = 75  # défaut
    for word in report_text.split():
        if word.isdigit() and 50 <= int(word) <= 100:
            candidate = int(word)
            # On cherche un nombre suivi de /100 ou "sur 100"
            if f"{candidate}/100" in report_text or f"{candidate} sur 100" in report_text:
                score = candidate
                break

    return {
        "phases":         phases,
        "confidence_score": score,
        "report_final":   phases.get("report_forge", ""),
        "n_phases":       len(phases),
    }
