"""
QUANTA — orchestrator.py
Point d'entrée unique du pipeline d'analyse. Relie compute.py (calcul pur)
et test_selector.py (choix du test) en un seul appel cohérent, gère la
délégation des tests "généraux" (OLS, corrélation) vers compute.py, fusionne
les audit_log en une timeline unique, et calcule le score de confiance
(Annexe A du document de specs QUANTA).

Ce module NE FAIT AUCUN CALCUL STATISTIQUE LUI-MÊME -- il appelle
exclusivement compute.py et test_selector.py et orchestre leurs résultats
(y compris l'enrichissement post-test : puissance via
compute.compute_statistical_power). C'est la seule fonction que main.py
(FastAPI) doit connaître pour exposer l'endpoint /analyze.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from app.compute import compute
from app.compute import test_selector as ts


# ═══════════════════════════════════════════════════════════════════════════════
# SCORE DE CONFIANCE (Annexe A) — pondérations
# ═══════════════════════════════════════════════════════════════════════════════

CONFIDENCE_WEIGHTS = {
    "qualite_donnees":        0.20,
    "respect_conditions":     0.25,
    "coherence_inter_methodes": 0.20,
    "taille_echantillon":     0.15,
    "stabilite":              0.20,
}


def _json_safe(obj: Any) -> Any:
    """
    Filet de sécurité final : convertit récursivement tout type non-natif
    (numpy, etc.) en type JSON-natif. compute.py et test_selector.py
    garantissent déjà leurs propres sorties, mais l'orchestrateur applique
    cette conversion une dernière fois sur l'objet assemblé final, pour
    couvrir tout champ qu'il ajoute lui-même (ex: scores calculés ici).
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


# ═══════════════════════════════════════════════════════════════════════════════
# GESTION DE LA DÉLÉGATION (test_selector -> compute)
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_delegation(
    selector_result: dict[str, Any],
    df: pd.DataFrame,
    numeric_cols: list[str],
    normality_results: dict,
    base_regression: dict[str, Any],
    base_correlation: dict[str, Any],
    audit_log: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    test_selector.py peut retourner un statut "delegate_to_ols" ou
    "delegate_to_correlation" plutôt que de calculer lui-même (ces calculs
    appartiennent légitimement à compute.py). Cette fonction résout cette
    délégation :

      - "delegate_to_ols" : si la cible demandée correspond exactement à
        celle déjà calculée dans base_regression (le run générique de
        run_base_compute_pipeline), on réutilise ce résultat sans recalculer
        -- évite un appel statsmodels redondant. Sinon, on relance
        ols_regression() avec le bon target_col.

      - "delegate_to_correlation" : on extrait la paire pertinente depuis
        base_correlation (déjà calculée pour TOUTES les paires numériques),
        sans recalcul.

    Retourne le résultat final à placer dans la réponse (remplace le
    statut "delegate_to_*" par le résultat réel).
    """
    result = selector_result.get("result", {})
    status = result.get("status")

    if status == "delegate_to_ols":
        target = result.get("target_col")
        predictors = result.get("predictor_cols", [])

        already_computed = (
            base_regression.get("status") == "ok"
            and base_regression.get("y_variable") == target
        )
        if already_computed:
            audit_log.append({
                "etape": "delegation_ols", "colonne": target,
                "decision": "reutilisation_resultat_existant",
                "valeur": None,
                "justification": (
                    f"Régression OLS demandée sur '{target}' -- résultat déjà "
                    f"disponible depuis le calcul de base, pas de recalcul."
                ),
            })
            return base_regression

        new_reg = compute.ols_regression(df, numeric_cols, target_col=target)
        audit_log.append({
            "etape": "delegation_ols", "colonne": target,
            "decision": "recalcul_avec_cible_specifique",
            "valeur": predictors,
            "justification": (
                f"Régression OLS demandée sur '{target}' avec prédicteurs "
                f"{predictors} -- différent du calcul de base, recalculée."
            ),
        })
        return new_reg

    if status == "delegate_to_correlation":
        col1, col2 = result.get("col1"), result.get("col2")
        pairs = base_correlation.get("pairs", {})
        key_fwd = f"{col1} x {col2}"
        key_rev = f"{col2} x {col1}"
        pair_result = pairs.get(key_fwd) or pairs.get(key_rev)

        if pair_result is None:
            audit_log.append({
                "etape": "delegation_correlation", "colonne": f"{col1} x {col2}",
                "decision": "paire_introuvable",
                "valeur": None,
                "justification": (
                    f"Corrélation demandée entre '{col1}' et '{col2}' mais cette "
                    f"paire n'a pas été trouvée dans les résultats déjà calculés."
                ),
            })
            return {"status": "error", "reason": f"Paire '{col1}' x '{col2}' introuvable."}

        audit_log.append({
            "etape": "delegation_correlation", "colonne": f"{col1} x {col2}",
            "decision": "reutilisation_resultat_existant",
            "valeur": pair_result.get("r"),
            "justification": (
                f"Corrélation entre '{col1}' et '{col2}' -- résultat déjà "
                f"disponible depuis la matrice de corrélation de base "
                f"(méthode : {base_correlation.get('method')})."
            ),
        })
        return {"status": "ok", "method": base_correlation.get("method"),
                "col1": col1, "col2": col2, **pair_result}

    # Pas de délégation -- résultat direct de test_selector
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SCORE DE CONFIANCE
# ═══════════════════════════════════════════════════════════════════════════════

def _score_qualite_donnees(diagnosis: dict, cleaning: dict) -> tuple[float, list[str]]:
    """
    20% -- pénalise les valeurs manquantes importantes, les doublons,
    les colonnes supprimées pour trop de données manquantes.
    """
    notes = []
    score = 100.0

    missing_pct = diagnosis.get("missing_pct", {})
    if missing_pct:
        max_missing = max(missing_pct.values())
        if max_missing > 20:
            score -= 30
            notes.append(f"Valeurs manquantes importantes détectées (jusqu'à {max_missing:.1f}%).")
        elif max_missing > 5:
            score -= 10
            notes.append(f"Valeurs manquantes modérées (jusqu'à {max_missing:.1f}%).")

    n_dupes = diagnosis.get("n_duplicates", 0)
    n_rows = diagnosis.get("n_rows", 1)
    if n_dupes > 0:
        dup_ratio = n_dupes / max(n_rows, 1)
        if dup_ratio > 0.05:
            score -= 15
            notes.append(f"{n_dupes} doublons détectés ({dup_ratio*100:.1f}% du dataset).")
        else:
            score -= 5

    audit_log = cleaning.get("audit_log", [])
    n_cols_dropped = sum(1 for e in audit_log if e.get("decision") == "suppression_colonne")
    if n_cols_dropped > 0:
        score -= 10 * n_cols_dropped
        notes.append(f"{n_cols_dropped} colonne(s) supprimée(s) pour données manquantes excessives.")

    return max(0.0, score), notes


def _score_respect_conditions(normality: dict, selector_audit: list[dict]) -> tuple[float, list[str]]:
    """
    25% -- pénalise les switches automatiques fréquents (signe que les
    conditions paramétriques classiques ne sont pas respectées) et les
    cas "AMBIGUE" de normalité.
    """
    notes = []
    score = 100.0

    n_ambiguous = sum(1 for v in normality.values() if v.get("conclusion") == "AMBIGUE")
    if n_ambiguous > 0:
        score -= 15 * n_ambiguous
        notes.append(f"{n_ambiguous} variable(s) avec conclusion de normalité ambiguë.")

    n_switches = sum(1 for e in selector_audit if "non-param" in str(e.get("decision", "")).lower()
                      or "non-normale" in str(e.get("valeur", "")).lower())
    if n_switches > 0:
        notes.append(f"{n_switches} test(s) basculé(s) vers une méthode non-paramétrique (switch automatique documenté).")
        score -= 5 * n_switches  # pénalité légère : le switch est correct, pas une erreur

    return max(0.0, score), notes


def _score_coherence_inter_methodes(correlation: dict, regression_result: dict) -> tuple[float, list[str]]:
    """
    20% -- vérifie qu'il n'y a pas de contradiction flagrante (ex: une
    régression avec un R2 très faible alors que les corrélations sous-jacentes
    sont fortes, ou une forte multicolinéarité non signalée).
    """
    notes = []
    score = 100.0

    vif = regression_result.get("VIF", {}) if regression_result else {}
    high_vif = {k: v for k, v in vif.items() if v is not None and v > 10}
    if high_vif:
        score -= 20
        notes.append(f"Multicolinéarité élevée détectée (VIF > 10) sur : {', '.join(high_vif.keys())}.")

    if regression_result and regression_result.get("status") == "ok":
        r2 = regression_result.get("R2", 0)
        strong_pairs = [k for k, v in correlation.get("pairs", {}).items()
                        if v.get("strength") in ("Forte", "Très forte")]
        if strong_pairs and r2 < 0.1:
            score -= 10
            notes.append(
                "Des corrélations fortes existent entre variables mais le R² de la "
                "régression reste faible -- possible non-linéarité ou interaction non capturée."
            )

    return max(0.0, score), notes


def _score_taille_echantillon(diagnosis: dict, selector_result: dict) -> tuple[float, list[str]]:
    """
    15% -- pénalise les petits échantillons, en particulier pour les tests
    de groupes (où chaque sous-groupe doit avoir une taille suffisante).
    """
    notes = []
    score = 100.0
    n_rows = diagnosis.get("n_rows", 0)

    if n_rows < 30:
        score -= 40
        notes.append(f"Échantillon très petit (n={n_rows}) -- résultats à interpréter avec grande prudence.")
    elif n_rows < 100:
        score -= 15
        notes.append(f"Échantillon modeste (n={n_rows}).")

    group_sizes = selector_result.get("group_sizes") or selector_result.get("n_group1")
    if isinstance(group_sizes, list) and group_sizes:
        min_group = min(group_sizes)
        if min_group < 10:
            score -= 25
            notes.append(f"Au moins un groupe a un effectif très faible (n={min_group}).")
    elif isinstance(selector_result.get("n_group1"), int):
        min_group = min(selector_result["n_group1"], selector_result.get("n_group2", float("inf")))
        if min_group < 10:
            score -= 25
            notes.append(f"Au moins un groupe a un effectif très faible (n={min_group}).")

    return max(0.0, score), notes


def _score_stabilite(diagnosis: dict, cleaning: dict) -> tuple[float, list[str]]:
    """
    20% -- pénalise les datasets ayant nécessité beaucoup d'interventions
    de nettoyage (signe de données brutes peu fiables) ou un fort taux
    d'outliers.
    """
    notes = []
    score = 100.0

    outlier_counts = diagnosis.get("outlier_counts", {})
    n_rows = diagnosis.get("n_rows", 1)
    if outlier_counts:
        max_outlier_ratio = max(outlier_counts.values()) / max(n_rows, 1)
        if max_outlier_ratio > 0.10:
            score -= 25
            notes.append(f"Proportion élevée de valeurs extrêmes détectées (jusqu'à {max_outlier_ratio*100:.1f}% d'une colonne).")
        elif max_outlier_ratio > 0.03:
            score -= 10

    n_interventions = len(cleaning.get("audit_log", []))
    if n_interventions > 10:
        score -= 10
        notes.append(f"{n_interventions} interventions de nettoyage automatique appliquées.")

    return max(0.0, score), notes


def compute_confidence_score(
    diagnosis: dict, cleaning: dict, normality: dict, correlation: dict,
    regression_result: dict, selector_result: dict, selector_audit: list[dict],
) -> dict[str, Any]:
    """
    Calcule le score de confiance global (0-100) selon les 5 critères
    pondérés de l'Annexe A. Retourne le score ET les points de vigilance
    associés -- jamais un nombre nu sans contexte (cf. recommandation
    ChatGPT sur l'interprétation du score).
    """
    s_qualite, n_qualite = _score_qualite_donnees(diagnosis, cleaning)
    s_conditions, n_conditions = _score_respect_conditions(normality, selector_audit)
    s_coherence, n_coherence = _score_coherence_inter_methodes(correlation, regression_result)
    s_taille, n_taille = _score_taille_echantillon(diagnosis, selector_result)
    s_stabilite, n_stabilite = _score_stabilite(diagnosis, cleaning)

    global_score = (
        s_qualite * CONFIDENCE_WEIGHTS["qualite_donnees"]
        + s_conditions * CONFIDENCE_WEIGHTS["respect_conditions"]
        + s_coherence * CONFIDENCE_WEIGHTS["coherence_inter_methodes"]
        + s_taille * CONFIDENCE_WEIGHTS["taille_echantillon"]
        + s_stabilite * CONFIDENCE_WEIGHTS["stabilite"]
    )

    score_calcule = global_score
    global_score = min(global_score, 95.0)

    all_notes = n_qualite + n_conditions + n_coherence + n_taille + n_stabilite
    score_cap_note = (
        "Score plafonné à 95/100 — QUANTA évalue les propriétés statistiques "
        "des données mais ne peut pas mesurer la qualité du design d'étude, "
        "les biais de collecte, ni la validité externe."
    )
    if score_calcule > 95.0 and score_cap_note not in all_notes:
        all_notes.append(score_cap_note)

    # Plafonnement du niveau affiché selon la taille d'échantillon.
    # Le score numérique reste inchangé pour préserver la transparence.
    n_rows = diagnosis.get("n_rows", 0)
    niveau_cap = None
    cap_reason = None

    if n_rows < 30:
        niveau_cap = "Faible"
        cap_reason = (
            f"Échantillon de taille n={n_rows} (< 30) -- le niveau de confiance "
            f"est plafonné à 'Faible' quelle que soit la qualité du nettoyage, "
            f"car la puissance statistique reste structurellement limitée."
        )
    elif n_rows < 100:
        niveau_cap = "Modéré"
        cap_reason = (
            f"Échantillon de taille n={n_rows} (< 100) -- le niveau de confiance "
            f"est plafonné à 'Modéré' par prudence sur la généralisation des résultats."
        )

    if global_score >= 85:
        niveau_brut = "Élevé"
    elif global_score >= 65:
        niveau_brut = "Modéré"
    elif global_score >= 40:
        niveau_brut = "Faible"
    else:
        niveau_brut = "Très faible"

    niveau_order = {"Très faible": 0, "Faible": 1, "Modéré": 2, "Élevé": 3}
    if niveau_cap is not None and niveau_order[niveau_brut] > niveau_order[niveau_cap]:
        niveau = niveau_cap
        all_notes = all_notes + [cap_reason]
    else:
        niveau = niveau_brut

    return {
        "score_global": round(global_score, 1),
        "niveau": niveau,
        "niveau_brut_avant_plafond": niveau_brut if niveau != niveau_brut else None,
        "details": {
            "qualite_donnees":          round(s_qualite, 1),
            "respect_conditions":       round(s_conditions, 1),
            "coherence_inter_methodes": round(s_coherence, 1),
            "taille_echantillon":       round(s_taille, 1),
            "stabilite":                round(s_stabilite, 1),
        },
        "ponderations": CONFIDENCE_WEIGHTS,
        "points_de_vigilance": all_notes if all_notes else [
            "Aucun point de vigilance particulier identifié."
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MODE AUTONOME — SÉLECTION AUTOMATIQUE D'INTENTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def auto_intent(diagnosis: dict[str, Any]) -> list[ts.AnalysisIntent]:
    """
    Examine le diagnostic du dataset et propose une liste d'intentions
    d'analyse à exécuter lorsque l'utilisateur n'a fourni aucune requête.
    """
    numeric_cols = list(diagnosis.get("numeric_cols", []) or [])
    cat_cols = list(diagnosis.get("cat_cols", []) or [])
    intents: list[ts.AnalysisIntent] = []

    # Règle 1: une catégorielle + une ou plusieurs numériques
    # → comparaison de groupes pour chaque numérique
    if len(cat_cols) >= 1 and len(numeric_cols) >= 1:
        group_col = cat_cols[0]
        for target in numeric_cols[:3]:
            intents.append(
                ts.AnalysisIntent(
                    action="compare_groups",
                    target_col=target,
                    group_col=group_col,
                    raw_query="[auto]",
                )
            )

    # Règle 2: 2+ numériques → corrélation entre toutes
    if len(numeric_cols) >= 2:
        intents.append(
            ts.AnalysisIntent(
                action="correlation",
                target_col=numeric_cols[0],
                group_col=numeric_cols[1],
                raw_query="[auto]",
            )
        )

    # Règle 3: 2 catégorielles → association Chi-deux
    if len(cat_cols) >= 2:
        intents.append(
            ts.AnalysisIntent(
                action="association",
                target_col=cat_cols[0],
                group_col=cat_cols[1],
                raw_query="[auto]",
            )
        )

    # Règle 4: 3+ catégorielles → ACM (Analyse des Correspondances Multiples)
    if len(cat_cols) >= 3:
        intents.append(
            ts.AnalysisIntent(
                action="association",
                target_col=cat_cols[0],
                group_col=cat_cols[1],
                raw_query="[auto]",
            )
        )

    # Toujours ajouter un descriptif global en dernier
    intents.append(ts.AnalysisIntent(action="descriptive_only", raw_query="[auto]"))

    return intents if intents else [ts.AnalysisIntent(action="descriptive_only", raw_query="[auto]")]


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR PRINCIPAL — POINT D'ENTRÉE UNIQUE
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_analysis(
    file_bytes: bytes,
    filename: str,
    intent: ts.AnalysisIntent,
    theme: str = "both",
) -> dict[str, Any]:
    """
    Point d'entrée unique du pipeline QUANTA. À appeler depuis main.py
    (endpoint /analyze).

    Étapes :
      1. compute.run_base_compute_pipeline() -- diagnostic, nettoyage,
         descriptives, normalité, corrélations de base, régression OLS
         générique (si intent.target_col est fourni et numérique -- sert
         de pré-calcul, peut être réutilisé par la délégation).
      2. test_selector.select_and_run_test() -- choix et exécution du test
         d'inférence approprié à l'intention.
      3. Résolution de la délégation (OLS/corrélation spécifique demandée
         par l'intention, potentiellement différente du calcul générique
         de l'étape 1).
      4. Fusion des audit_log (cleaning + sélection de test) en une
         timeline unique triée par ordre d'exécution logique.
      5. Calcul du score de confiance.
      6. Assemblage de la réponse finale, garantie JSON-native.

    theme : "both" (défaut, génère les graphiques pour les deux thèmes),
            "dark" ou "light" (génère uniquement pour ce thème).

    Retourne TOUJOURS un dict -- en cas d'erreur de chargement du fichier,
    retourne {"error": ...} sans lever d'exception.
    """
    # Étape 1 : calcul de base
    base_target = intent.target_col if intent.action == "regression" else None
    pipeline = compute.run_base_compute_pipeline(file_bytes, filename, target_col=base_target, theme=theme)

    if "error" in pipeline:
        return {"error": pipeline["error"], "status": "failed"}

    df = pipeline["dataframe_clean"]
    numeric_cols = pipeline["numeric_cols"]
    cat_cols = pipeline["cat_cols"]
    id_cols = pipeline["diagnosis"].get("id_cols", [])
    normality = pipeline["normality"]

    # Étape 2 : sélection et exécution du test d'inférence
    selector_output = ts.select_and_run_test(
        intent, df, numeric_cols, cat_cols, id_cols, normality
    )

    # Étape 3 : résolution de la délégation
    fused_audit_log: list[dict[str, Any]] = []
    final_inference_result = _resolve_delegation(
        selector_output, df, numeric_cols, normality,
        pipeline["regression"], pipeline["correlation"],
        fused_audit_log,
    )

    # Étape 3b : puissance statistique (compute déterministe, post-test)
    if isinstance(final_inference_result, dict):
        final_inference_result = compute.compute_statistical_power(
            final_inference_result
        )

    # Étape 4 : fusion des audit_log (ordre chronologique logique : nettoyage
    # d'abord, puis validation de l'intention, puis sélection du test, puis
    # délégation éventuelle)
    fused_audit_log = (
        list(pipeline["cleaning"].get("audit_log", []))
        + list(selector_output.get("audit_log", []))
        + fused_audit_log
    )

    # Étape 5 : score de confiance
    confidence = compute_confidence_score(
        diagnosis=pipeline["diagnosis"],
        cleaning=pipeline["cleaning"],
        normality=normality,
        correlation=pipeline["correlation"],
        regression_result=pipeline["regression"],
        selector_result=final_inference_result if isinstance(final_inference_result, dict) else {},
        selector_audit=selector_output.get("audit_log", []),
    )

    # Étape 6 : assemblage final
    response = {
        "status": "ok",
        "filename": filename,
        "diagnosis": pipeline["diagnosis"],
        "descriptive": pipeline["descriptive"],
        "normality": normality,
        "correlation_base": pipeline["correlation"],
        "regression_base": pipeline["regression"],
        "inference": {
            "intent_received": {
                "action": intent.action,
                "target_col": intent.target_col,
                "group_col": intent.group_col,
                "predictor_cols": intent.predictor_cols,
                "paired": intent.paired,
                "raw_query": intent.raw_query,
            },
            "action_executed": selector_output.get("action_executed"),
            "validation_issues": selector_output.get("validation_issues", []),
            "result": final_inference_result,
        },
        "audit_log": fused_audit_log,
        "confidence_score": confidence,
        "charts": pipeline["charts"],
        "charts_light": pipeline.get("charts_light"),
        "r_script": pipeline["r_script"],
        "stata_script": pipeline["stata_script"],
        "n_charts": pipeline["n_charts"],
    }

    return _json_safe(response)
