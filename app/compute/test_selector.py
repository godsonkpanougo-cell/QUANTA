"""
QUANTA — test_selector.py
Le cerveau académique : choisit le test statistique approprié selon
l'intention de l'utilisateur (traduite par brain.py) ET la structure réelle
du dataset (issue de compute.py).

Principe fondamental : ce module NE FAIT JAMAIS CONFIANCE à l'intention
fournie sans la valider contre la réalité du dataset. Le LLM peut halluciner
un nom de colonne, proposer une variable reclassée en catégorielle, ou une
action incohérente avec les types disponibles. Toute divergence entre
l'intention demandée et la décision réellement prise est documentée dans
l'audit_log -- jamais un choix silencieux, jamais un crash.

Couvre l'arbre de décision complet (Annexe B du document de specs QUANTA) :
  - Comparaison de groupes (2 groupes indépendants / appariés, 3+ groupes)
  - Corrélations (Pearson / Spearman selon normalité)
  - Association entre variables catégorielles (Chi-deux / Fisher exact)
  - Régression (OLS continue / logistique binaire)
  - Statistiques descriptives par défaut (si aucune action claire)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

try:
    import scikit_posthocs as sp
    HAS_POSTHOCS = True
except ImportError:
    HAS_POSTHOCS = False


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURE D'INTENTION (ce que brain.py doit produire)
# ═══════════════════════════════════════════════════════════════════════════════

ActionType = Literal[
    "compare_groups", "correlation", "association", "regression", "descriptive_only"
]


@dataclass
class AnalysisIntent:
    """
    Intention d'analyse structurée, produite par brain.py à partir du texte
    libre de l'utilisateur. Traitée comme une PROPOSITION par test_selector.py,
    jamais comme un ordre direct -- toujours validée contre le dataset réel.
    """
    action: ActionType | None = None
    target_col: str | None = None
    group_col: str | None = None
    predictor_cols: list[str] = field(default_factory=list)
    paired: bool = False
    raw_query: str = ""


@dataclass
class ValidationIssue:
    """Une divergence entre ce qui a été demandé et ce qui a été constaté."""
    champ: str
    valeur_demandee: Any
    probleme: str
    resolution: str


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION DE L'INTENTION CONTRE LE DATASET RÉEL
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_column(
    col_name: str | None,
    numeric_cols: list[str],
    cat_cols: list[str],
    id_cols: list[str],
    role: str,
) -> tuple[str | None, str | None, list[ValidationIssue]]:
    """
    Vérifie qu'une colonne proposée existe réellement et indique son vrai type.

    Retourne (nom_validé_ou_None, type_reel ('numeric'|'categorical'|None), issues)
    """
    issues = []
    if col_name is None:
        return None, None, issues

    if col_name in id_cols:
        issues.append(ValidationIssue(
            champ=role, valeur_demandee=col_name,
            probleme=f"'{col_name}' est un identifiant (id_cols), pas une variable analysable.",
            resolution=f"'{col_name}' ignoré pour le rôle '{role}'.",
        ))
        return None, None, issues

    if col_name in numeric_cols:
        return col_name, "numeric", issues

    if col_name in cat_cols:
        return col_name, "categorical", issues

    issues.append(ValidationIssue(
        champ=role, valeur_demandee=col_name,
        probleme=f"'{col_name}' n'existe pas dans le dataset (ni numeric_cols, ni cat_cols).",
        resolution=f"'{col_name}' ignoré pour le rôle '{role}' -- possible erreur de "
                   f"compréhension de la requête utilisateur par la couche LLM.",
    ))
    return None, None, issues


def _check_n_groups(df: pd.DataFrame, group_col: str) -> int:
    return int(df[group_col].nunique(dropna=True))


# ═══════════════════════════════════════════════════════════════════════════════
# BRIQUES DE TEST — COMPARAISON DE GROUPES (variable continue)
# ═══════════════════════════════════════════════════════════════════════════════

def _normality_ok(normality_results: dict, col: str) -> bool:
    """Lit la conclusion de normalité déjà calculée par compute.py."""
    return normality_results.get(col, {}).get("conclusion") == "NORMALE"


def _levene_equal_variance(groups: list[np.ndarray]) -> tuple[bool, float, float]:
    """Test de Levene pour l'égalité des variances entre groupes."""
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        return True, float("nan"), float("nan")  # pas testable -> hypothèse par défaut
    stat, p = stats.levene(*groups)
    return bool(p > 0.05), float(stat), float(p)


def run_two_group_comparison(
    df: pd.DataFrame, target_col: str, group_col: str,
    normality_results: dict, paired: bool, audit_log: list[dict],
) -> dict[str, Any]:
    """
    Comparaison de 2 groupes pour une variable continue.
    Indépendants : Student (variances égales) / Welch (variances inégales) /
                   Mann-Whitney (non-normal).
    Appariés : t-test pairé (normal) / Wilcoxon signé (non-normal).
    """
    sub = df[[target_col, group_col]].dropna()
    levels = sub[group_col].unique()
    if len(levels) != 2:
        return {"status": "error", "reason": f"Attendu 2 groupes, trouvé {len(levels)}."}

    g1 = sub[sub[group_col] == levels[0]][target_col].values
    g2 = sub[sub[group_col] == levels[1]][target_col].values

    is_normal = _normality_ok(normality_results, target_col)

    if paired:
        if len(g1) != len(g2):
            return {"status": "error", "reason": "Comparaison appariée demandée mais effectifs des groupes différents."}
        if is_normal:
            stat, p = stats.ttest_rel(g1, g2)
            test_name = "t-test pairé (Student)"
        else:
            stat, p = stats.wilcoxon(g1, g2)
            test_name = "Wilcoxon (signé, rangs appariés)"
        audit_log.append({
            "etape": "selection_test", "colonne": target_col,
            "decision": test_name,
            "valeur": f"normalite={'OUI' if is_normal else 'NON'}",
            "justification": (
                f"Comparaison appariée de '{target_col}' entre 2 niveaux de "
                f"'{group_col}' -- normalité {'confirmée' if is_normal else 'rejetée'} "
                f"-> {test_name}."
            ),
        })
        effect_size = _cohens_d(g1, g2) if is_normal else _rank_biserial(g1, g2)
        return _format_two_group_result(test_name, stat, p, g1, g2, levels, effect_size, paired=True)

    equal_var, levene_stat, levene_p = _levene_equal_variance([g1, g2])

    if is_normal:
        if equal_var:
            stat, p = stats.ttest_ind(g1, g2, equal_var=True)
            test_name = "t-test de Student (variances égales)"
        else:
            stat, p = stats.ttest_ind(g1, g2, equal_var=False)
            test_name = "t-test de Welch (variances inégales)"
        effect_size = _cohens_d(g1, g2)
    else:
        stat, p = stats.mannwhitneyu(g1, g2, alternative="two-sided")
        test_name = "Mann-Whitney U (non-paramétrique)"
        effect_size = _rank_biserial(g1, g2)

    audit_log.append({
        "etape": "selection_test", "colonne": target_col,
        "decision": test_name,
        "valeur": f"normalite={'OUI' if is_normal else 'NON'}, levene_p={levene_p:.4f}" if not np.isnan(levene_p) else f"normalite={'OUI' if is_normal else 'NON'}",
        "justification": (
            f"Comparaison de '{target_col}' entre 2 groupes de '{group_col}' -- "
            f"normalité {'confirmée' if is_normal else 'rejetée'}"
            + (f", test de Levene p={levene_p:.4f} ({'variances égales' if equal_var else 'variances inégales'})" if not np.isnan(levene_p) else "")
            + f" -> {test_name}."
        ),
    })

    return _format_two_group_result(test_name, stat, p, g1, g2, levels, effect_size, paired=False,
                                      levene={"statistic": round(levene_stat, 4) if not np.isnan(levene_stat) else None,
                                              "p_value": round(levene_p, 5) if not np.isnan(levene_p) else None,
                                              "equal_variance": equal_var})


def run_multi_group_comparison(
    df: pd.DataFrame, target_col: str, group_col: str,
    normality_results: dict, audit_log: list[dict],
) -> dict[str, Any]:
    """
    Comparaison de 3+ groupes pour une variable continue.
    ANOVA + Tukey HSD (normal, variances égales) /
    Welch ANOVA + Games-Howell (normal, variances inégales) /
    Kruskal-Wallis + Dunn (non-normal).
    """
    sub = df[[target_col, group_col]].dropna()
    levels = sorted(sub[group_col].unique(), key=str)
    groups = [sub[sub[group_col] == lvl][target_col].values for lvl in levels]
    groups = [g for g in groups if len(g) > 0]

    if len(groups) < 3:
        return {"status": "error", "reason": f"Attendu 3+ groupes, trouvé {len(groups)} groupes non-vides."}

    is_normal = _normality_ok(normality_results, target_col)
    equal_var, levene_stat, levene_p = _levene_equal_variance(groups)

    result: dict[str, Any] = {
        "status": "ok",
        "target": target_col,
        "group": group_col,
        "n_groups": len(groups),
        "group_levels": [str(l) for l in levels],
        "group_sizes": [len(g) for g in groups],
        "group_means": [round(float(np.mean(g)), 4) for g in groups],
        "group_medians": [round(float(np.median(g)), 4) for g in groups],
        "levene": {
            "statistic": round(levene_stat, 4) if not np.isnan(levene_stat) else None,
            "p_value": round(levene_p, 5) if not np.isnan(levene_p) else None,
            "equal_variance": equal_var,
        },
    }

    if is_normal and equal_var:
        f_stat, p = stats.f_oneway(*groups)
        test_name = "ANOVA à un facteur (variances égales)"
        result.update({
            "test": test_name, "statistic": round(float(f_stat), 4), "p_value": round(float(p), 6),
            "eta_squared": _eta_squared(groups, f_stat),
        })
        if p < 0.05:
            result["posthoc"] = _tukey_hsd(sub, target_col, group_col)
            posthoc_name = "Tukey HSD"
        else:
            result["posthoc"] = None
            posthoc_name = "non applicable (ANOVA non significative)"

    elif is_normal and not equal_var:
        f_stat, p = stats.f_oneway(*groups)  # approximation; Welch ANOVA via statsmodels si besoin
        test_name = "Welch ANOVA (variances inégales, approximation)"
        result.update({
            "test": test_name, "statistic": round(float(f_stat), 4), "p_value": round(float(p), 6),
            "eta_squared": _eta_squared(groups, f_stat),
            "note": "Variances jugées inégales (Levene) -- interpréter le F avec prudence ; "
                    "Games-Howell recommandé en post-hoc plutôt que Tukey.",
        })
        if p < 0.05 and HAS_POSTHOCS:
            result["posthoc"] = _games_howell_or_fallback(sub, target_col, group_col)
            posthoc_name = "Games-Howell (ou repli Tukey si indisponible)"
        else:
            result["posthoc"] = None
            posthoc_name = "non applicable"

    else:
        h_stat, p = stats.kruskal(*groups)
        test_name = "Kruskal-Wallis (non-paramétrique)"
        result.update({
            "test": test_name, "statistic": round(float(h_stat), 4), "p_value": round(float(p), 6),
            "epsilon_squared": _epsilon_squared(h_stat, sum(len(g) for g in groups)),
        })
        if p < 0.05:
            result["posthoc"] = _dunn_test(sub, target_col, group_col)
            posthoc_name = "Test de Dunn"
        else:
            result["posthoc"] = None
            posthoc_name = "non applicable (Kruskal-Wallis non significatif)"

    audit_log.append({
        "etape": "selection_test", "colonne": target_col,
        "decision": test_name,
        "valeur": f"normalite={'OUI' if is_normal else 'NON'}, levene_p={levene_p:.4f}" if not np.isnan(levene_p) else f"normalite={'OUI' if is_normal else 'NON'}",
        "justification": (
            f"Comparaison de '{target_col}' entre {len(groups)} groupes de '{group_col}' -- "
            f"normalité {'confirmée' if is_normal else 'rejetée'}"
            + (f", Levene p={levene_p:.4f}" if not np.isnan(levene_p) else "")
            + f" -> {test_name}. Post-hoc : {posthoc_name}."
        ),
    })

    return result


def _cohens_d(g1: np.ndarray, g2: np.ndarray) -> float:
    n1, n2 = len(g1), len(g2)
    pooled_std = np.sqrt(((n1 - 1) * np.var(g1, ddof=1) + (n2 - 1) * np.var(g2, ddof=1)) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return round(float((np.mean(g1) - np.mean(g2)) / pooled_std), 4)


def _rank_biserial(g1: np.ndarray, g2: np.ndarray) -> float:
    """Taille d'effet pour Mann-Whitney/Wilcoxon (corrélation rang-bisériale)."""
    n1, n2 = len(g1), len(g2)
    try:
        u_stat, _ = stats.mannwhitneyu(g1, g2, alternative="two-sided")
        return round(float(1 - (2 * u_stat) / (n1 * n2)), 4)
    except Exception:
        return float("nan")


def _eta_squared(groups: list[np.ndarray], f_stat: float) -> float:
    k = len(groups)
    n = sum(len(g) for g in groups)
    df_between = k - 1
    df_within = n - k
    if (f_stat * df_between + df_within) == 0:
        return 0.0
    return round(float((f_stat * df_between) / (f_stat * df_between + df_within)), 4)


def _epsilon_squared(h_stat: float, n: int) -> float:
    if n <= 1:
        return 0.0
    return round(float(h_stat / (n - 1)), 4)


def _tukey_hsd(sub: pd.DataFrame, target_col: str, group_col: str) -> dict:
    try:
        from statsmodels.stats.multicomp import pairwise_tukeyhsd
        res = pairwise_tukeyhsd(sub[target_col], sub[group_col])
        out = {}
        for row in res.summary().data[1:]:
            g1, g2, meandiff, p_adj, lower, upper, reject = row
            out[f"{g1} vs {g2}"] = {
                "meandiff": round(float(meandiff), 4),
                "p_adj": round(float(p_adj), 5),
                "ci": [round(float(lower), 4), round(float(upper), 4)],
                "significatif": bool(reject),
            }
        return out
    except Exception as e:
        return {"error": str(e)}


def _games_howell_or_fallback(sub: pd.DataFrame, target_col: str, group_col: str) -> dict:
    """Games-Howell si scikit-posthocs dispo, sinon repli sur Tukey avec avertissement."""
    if HAS_POSTHOCS:
        try:
            res = sp.posthoc_games_howell(sub, val_col=target_col, group_col=group_col)
            return {"matrix_p_values": res.round(5).to_dict(), "methode": "Games-Howell"}
        except Exception:
            pass
    tukey = _tukey_hsd(sub, target_col, group_col)
    tukey["_avertissement"] = (
        "Games-Howell indisponible (scikit-posthocs manquant ou erreur) -- "
        "repli sur Tukey HSD, à interpréter avec prudence car les variances sont inégales."
    )
    return tukey


def _dunn_test(sub: pd.DataFrame, target_col: str, group_col: str) -> dict:
    if not HAS_POSTHOCS:
        return {"error": "scikit-posthocs non installé -- test de Dunn indisponible."}
    try:
        res = sp.posthoc_dunn(sub, val_col=target_col, group_col=group_col, p_adjust="bonferroni")
        return {"matrix_p_values": res.round(5).to_dict(), "methode": "Dunn (correction Bonferroni)"}
    except Exception as e:
        return {"error": str(e)}


def _format_two_group_result(test_name, stat, p, g1, g2, levels, effect_size, paired, levene=None) -> dict:
    return {
        "status": "ok",
        "test": test_name,
        "statistic": round(float(stat), 4),
        "p_value": round(float(p), 6),
        "n_group1": len(g1), "n_group2": len(g2),
        "group1_label": str(levels[0]), "group2_label": str(levels[1]),
        "mean1": round(float(np.mean(g1)), 4), "mean2": round(float(np.mean(g2)), 4),
        "median1": round(float(np.median(g1)), 4), "median2": round(float(np.median(g2)), 4),
        "effect_size": effect_size,
        "paired": paired,
        "levene": levene,
        "significant": bool(p < 0.05),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BRIQUE — ASSOCIATION ENTRE VARIABLES CATÉGORIELLES
# ═══════════════════════════════════════════════════════════════════════════════

def run_categorical_association(
    df: pd.DataFrame, col1: str, col2: str, audit_log: list[dict],
) -> dict[str, Any]:
    """
    Chi-deux si toutes les cellules attendues >= 5, sinon Fisher exact
    (uniquement valide nativement pour des tables 2x2 -- sinon Chi-deux
    avec avertissement explicite sur la fiabilité).
    """
    sub = df[[col1, col2]].dropna()
    table = pd.crosstab(sub[col1], sub[col2])

    if table.shape[0] < 2 or table.shape[1] < 2:
        return {"status": "error", "reason": "Au moins une des deux variables n'a qu'une seule catégorie."}

    chi2, p_chi2, dof, expected = stats.chi2_contingency(table)
    min_expected = float(expected.min())
    all_cells_ok = min_expected >= 5

    n = table.values.sum()
    cramers_v = _cramers_v(chi2, n, table.shape)

    result: dict[str, Any] = {
        "status": "ok",
        "contingency_table": table.to_dict(),
        "min_expected_count": round(min_expected, 2),
        "n_observations": int(n),
    }

    if all_cells_ok:
        test_name = "Chi-deux d'indépendance"
        result.update({
            "test": test_name, "statistic": round(float(chi2), 4),
            "p_value": round(float(p_chi2), 6), "dof": int(dof),
            "cramers_v": cramers_v,
            "significant": bool(p_chi2 < 0.05),
        })
    elif table.shape == (2, 2):
        odds_ratio, p_fisher = stats.fisher_exact(table.values)
        test_name = "Fisher exact (table 2x2, effectifs attendus < 5)"
        result.update({
            "test": test_name, "odds_ratio": round(float(odds_ratio), 4),
            "p_value": round(float(p_fisher), 6),
            "cramers_v": cramers_v,
            "significant": bool(p_fisher < 0.05),
            "chi2_indicatif": {"statistic": round(float(chi2), 4), "p_value": round(float(p_chi2), 6)},
        })
    else:
        test_name = "Chi-deux d'indépendance (avec réserve)"
        result.update({
            "test": test_name, "statistic": round(float(chi2), 4),
            "p_value": round(float(p_chi2), 6), "dof": int(dof),
            "cramers_v": cramers_v,
            "significant": bool(p_chi2 < 0.05),
            "avertissement": (
                f"Effectif attendu minimal = {min_expected:.2f} (< 5) dans une table "
                f"{table.shape[0]}x{table.shape[1]} -- Fisher exact non disponible nativement "
                f"au-delà de 2x2. Résultat du Chi-deux à interpréter avec prudence."
            ),
        })

    audit_log.append({
        "etape": "selection_test", "colonne": f"{col1} x {col2}",
        "decision": test_name,
        "valeur": f"effectif_min_attendu={min_expected:.2f}",
        "justification": (
            f"Association entre '{col1}' et '{col2}' -- effectif minimal attendu "
            f"{min_expected:.2f} -> {test_name}."
        ),
    })

    return result


def _cramers_v(chi2: float, n: int, shape: tuple[int, int]) -> float:
    if n == 0:
        return 0.0
    r, k = shape
    denom = n * (min(r - 1, k - 1))
    if denom == 0:
        return 0.0
    return round(float(np.sqrt(chi2 / denom)), 4)


# ═══════════════════════════════════════════════════════════════════════════════
# BRIQUE — RÉGRESSION LOGISTIQUE (variable cible binaire)
# ═══════════════════════════════════════════════════════════════════════════════

def run_logistic_regression(
    df: pd.DataFrame, target_col: str, predictor_cols: list[str], audit_log: list[dict],
) -> dict[str, Any]:
    """
    Régression logistique binaire (statsmodels Logit) avec odds ratios.
    target_col doit être binaire (2 valeurs distinctes).
    """
    levels = df[target_col].dropna().unique()
    if len(levels) != 2:
        return {"status": "error", "reason": f"'{target_col}' doit avoir exactement 2 catégories, trouvé {len(levels)}."}

    sub = df[[target_col] + predictor_cols].dropna()
    if len(sub) < len(predictor_cols) + 10:
        return {"status": "error", "reason": "Pas assez d'observations complètes pour la régression logistique."}

    y_map = {levels[0]: 0, levels[1]: 1}
    y = sub[target_col].map(y_map)
    X = sm.add_constant(sub[predictor_cols])

    try:
        model = sm.Logit(y, X).fit(disp=0)
    except Exception as e:
        return {"status": "error", "reason": f"Échec de convergence : {e}"}

    coef_summary = {}
    for var in model.params.index:
        coef = model.params[var]
        coef_summary[var] = {
            "coefficient": round(float(coef), 6),
            "odds_ratio": round(float(np.exp(coef)), 4),
            "p_value": round(float(model.pvalues[var]), 5),
            "ci_lower_or": round(float(np.exp(model.conf_int().loc[var, 0])), 4),
            "ci_upper_or": round(float(np.exp(model.conf_int().loc[var, 1])), 4),
            "significant": bool(model.pvalues[var] < 0.05),
        }

    audit_log.append({
        "etape": "selection_test", "colonne": target_col,
        "decision": "Régression logistique binaire",
        "valeur": f"n={int(model.nobs)}",
        "justification": (
            f"'{target_col}' est binaire (catégories : {levels[0]}={0}, {levels[1]}={1}) "
            f"-> régression logistique avec {len(predictor_cols)} prédicteur(s)."
        ),
    })

    return {
        "status": "ok",
        "target": target_col,
        "target_mapping": {str(levels[0]): 0, str(levels[1]): 1},
        "predictors": predictor_cols,
        "n_obs": int(model.nobs),
        "pseudo_R2": round(float(model.prsquared), 4),
        "log_likelihood": round(float(model.llf), 4),
        "coefficients": coef_summary,
        "LLR_p_value": round(float(model.llr_pvalue), 6),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR DE SÉLECTION — IMPLÉMENTATION INTERNE
# ═══════════════════════════════════════════════════════════════════════════════

def _select_and_run_test_impl(
    intent: AnalysisIntent,
    df: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
    id_cols: list[str],
    normality_results: dict,
) -> dict[str, Any]:
    """
    Implémentation interne de select_and_run_test (voir le wrapper public
    plus bas pour la garantie de sérialisation JSON). Logique inchangée :
    reçoit l'intention (proposée par brain.py), la valide contre le dataset
    réel, choisit et exécute le test approprié.

    Retourne TOUJOURS un dict avec :
      - "result"     : le résultat du test (ou status "skipped"/"error")
      - "audit_log"  : liste d'entrées documentant chaque décision, y compris
                        les divergences entre l'intention demandée et la
                        réalité du dataset
      - "validation_issues" : liste des ValidationIssue rencontrées
      - "action_executed"   : l'action réellement exécutée (peut différer de
                        intent.action si une correction a été nécessaire)
    """
    audit_log: list[dict[str, Any]] = []
    all_issues: list[ValidationIssue] = []

    target_col, target_type, issues_t = _validate_column(
        intent.target_col, numeric_cols, cat_cols, id_cols, "target_col")
    all_issues += issues_t

    group_col, group_type, issues_g = _validate_column(
        intent.group_col, numeric_cols, cat_cols, id_cols, "group_col")
    all_issues += issues_g

    valid_predictors = []
    for p in intent.predictor_cols:
        p_name, p_type, issues_p = _validate_column(p, numeric_cols, cat_cols, id_cols, "predictor_cols")
        all_issues += issues_p
        if p_name and p_type == "numeric":
            valid_predictors.append(p_name)

    for issue in all_issues:
        audit_log.append({
            "etape": "validation_intention",
            "colonne": issue.champ,
            "decision": "correction",
            "valeur": issue.valeur_demandee,
            "justification": f"{issue.probleme} {issue.resolution}",
        })

    action = intent.action

    # ── Cas 1 : comparer des groupes ─────────────────────────────────────
    if action == "compare_groups":
        if target_type != "numeric" or group_type != "categorical":
            audit_log.append({
                "etape": "fallback_action", "colonne": None,
                "decision": "descriptive_only",
                "valeur": None,
                "justification": (
                    f"Action 'compare_groups' demandée mais target_col "
                    f"({target_col!r}, type={target_type}) et/ou group_col "
                    f"({group_col!r}, type={group_type}) ne correspondent pas "
                    f"au schéma attendu (target numérique, group catégoriel) "
                    f"-> repli sur statistiques descriptives."
                ),
            })
            return {"result": {"status": "skipped", "reason": "Schéma invalide pour compare_groups."},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "descriptive_only"}

        n_groups = _check_n_groups(df, group_col)
        if n_groups < 2:
            audit_log.append({
                "etape": "fallback_action", "colonne": group_col,
                "decision": "descriptive_only", "valeur": n_groups,
                "justification": f"'{group_col}' n'a qu'un seul niveau -- comparaison impossible.",
            })
            return {"result": {"status": "skipped", "reason": f"'{group_col}' a moins de 2 niveaux."},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "descriptive_only"}
        elif n_groups == 2:
            result = run_two_group_comparison(df, target_col, group_col, normality_results, intent.paired, audit_log)
            return {"result": result, "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "compare_groups_2"}
        else:
            result = run_multi_group_comparison(df, target_col, group_col, normality_results, audit_log)
            return {"result": result, "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "compare_groups_multi"}

    # ── Cas 2 : association entre catégorielles ──────────────────────────
    if action == "association":
        if target_type != "categorical" or group_type != "categorical":
            audit_log.append({
                "etape": "fallback_action", "colonne": None,
                "decision": "descriptive_only", "valeur": None,
                "justification": (
                    f"Action 'association' demandée mais target_col/group_col ne sont "
                    f"pas toutes deux catégorielles (target={target_type}, group={group_type}) "
                    f"-> repli sur statistiques descriptives."
                ),
            })
            return {"result": {"status": "skipped", "reason": "Schéma invalide pour association."},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "descriptive_only"}
        result = run_categorical_association(df, target_col, group_col, audit_log)
        return {"result": result, "audit_log": audit_log, "validation_issues": all_issues,
                "action_executed": "association"}

    # ── Cas 3 : régression ───────────────────────────────────────────────
    if action == "regression":
        if target_type == "numeric" and valid_predictors:
            audit_log.append({
                "etape": "selection_test", "colonne": target_col,
                "decision": "Régression OLS (déléguée à compute.py)",
                "valeur": f"predictors={valid_predictors}",
                "justification": (
                    f"'{target_col}' est continue -> régression OLS avec "
                    f"{len(valid_predictors)} prédicteur(s) numérique(s)."
                ),
            })
            return {"result": {"status": "delegate_to_ols", "target_col": target_col,
                                "predictor_cols": valid_predictors},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "regression_ols"}
        elif target_type == "categorical":
            n_target_levels = df[target_col].nunique(dropna=True)
            if n_target_levels == 2 and valid_predictors:
                result = run_logistic_regression(df, target_col, valid_predictors, audit_log)
                return {"result": result, "audit_log": audit_log, "validation_issues": all_issues,
                        "action_executed": "regression_logistic"}
            else:
                audit_log.append({
                    "etape": "fallback_action", "colonne": target_col,
                    "decision": "descriptive_only", "valeur": n_target_levels,
                    "justification": (
                        f"'{target_col}' est catégorielle avec {n_target_levels} niveaux "
                        f"(régression logistique nécessite exactement 2) ou aucun prédicteur "
                        f"valide -> repli sur statistiques descriptives."
                    ),
                })
                return {"result": {"status": "skipped", "reason": "Cible catégorielle non-binaire ou sans prédicteur."},
                        "audit_log": audit_log, "validation_issues": all_issues,
                        "action_executed": "descriptive_only"}
        else:
            audit_log.append({
                "etape": "fallback_action", "colonne": None,
                "decision": "descriptive_only", "valeur": None,
                "justification": "Action 'regression' demandée mais target_col invalide ou absent -> repli descriptif.",
            })
            return {"result": {"status": "skipped", "reason": "target_col invalide pour la régression."},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "descriptive_only"}

    # ── Cas 4 : corrélation ──────────────────────────────────────────────
    if action == "correlation":
        if target_type == "numeric" and group_type == "numeric":
            audit_log.append({
                "etape": "selection_test", "colonne": f"{target_col} x {group_col}",
                "decision": "Corrélation (déléguée à compute.py)",
                "valeur": None,
                "justification": (
                    f"'{target_col}' et '{group_col}' sont toutes deux continues "
                    f"-> corrélation Pearson/Spearman (méthode choisie par compute.py "
                    f"selon la normalité conjointe)."
                ),
            })
            return {"result": {"status": "delegate_to_correlation", "col1": target_col, "col2": group_col},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "correlation"}
        else:
            audit_log.append({
                "etape": "fallback_action", "colonne": None,
                "decision": "descriptive_only", "valeur": None,
                "justification": (
                    f"Action 'correlation' demandée mais target_col/group_col ne sont pas "
                    f"toutes deux numériques (target={target_type}, group={group_type}) "
                    f"-> repli sur statistiques descriptives."
                ),
            })
            return {"result": {"status": "skipped", "reason": "Schéma invalide pour correlation."},
                    "audit_log": audit_log, "validation_issues": all_issues,
                    "action_executed": "descriptive_only"}

    # ── Cas 5 : descriptif explicite ou action absente/non reconnue ──────
    audit_log.append({
        "etape": "selection_action", "colonne": None,
        "decision": "descriptive_only",
        "valeur": action,
        "justification": (
            f"Action demandée = {action!r} -- statistiques descriptives par défaut "
            f"(aucune comparaison/corrélation/régression/association n'a pu être "
            f"validée à partir de l'intention fournie)."
        ),
    })
    return {"result": {"status": "ok", "note": "Voir descriptive_stats() dans compute.py"},
            "audit_log": audit_log, "validation_issues": all_issues,
            "action_executed": "descriptive_only"}


# ═══════════════════════════════════════════════════════════════════════════════
# GARANTIE DE SÉRIALISATION JSON — wrapper public
# ═══════════════════════════════════════════════════════════════════════════════

def _json_safe(obj: Any) -> Any:
    """
    Convertit récursivement un objet en structure JSON-native :
      - ValidationIssue (dataclass) -> dict
      - numpy bool_/integer/floating -> bool/int/float Python
      - numpy ndarray -> liste
      - dict / list -> conversion récursive de leurs valeurs
      - autres types -> inchangés (str, int, float, bool, None déjà natifs)

    Filet de sécurité : même si une future modification de test_selector.py
    réintroduit un type non-JSON-natif dans le résultat, ce wrapper l'attrape
    avant que ça n'atteigne l'orchestrateur ou l'API FastAPI.
    """
    if isinstance(obj, ValidationIssue):
        return {
            "champ": obj.champ,
            "valeur_demandee": _json_safe(obj.valeur_demandee),
            "probleme": obj.probleme,
            "resolution": obj.resolution,
        }
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    return obj


def select_and_run_test(
    intent: AnalysisIntent,
    df: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
    id_cols: list[str],
    normality_results: dict,
) -> dict[str, Any]:
    """
    Point d'entrée public. Délègue toute la logique à
    _select_and_run_test_impl(), puis garantit que la sortie est
    intégralement sérialisable en JSON (json.dumps ne lève jamais
    d'exception sur le résultat de cette fonction) -- c'est le contrat
    que l'orchestrateur et l'API FastAPI peuvent utiliser sans précaution
    supplémentaire ni helper de conversion local.
    """
    raw = _select_and_run_test_impl(
        intent, df, numeric_cols, cat_cols, id_cols, normality_results
    )
    return _json_safe(raw)
