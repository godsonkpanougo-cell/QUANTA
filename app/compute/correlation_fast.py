"""
QUANTA — correlation_fast.py (P1-bis, branche feature/freebuff-perf-corr)

Implémentation vectorisée EXACTE du calcul des paires de corrélation de
`compute.correlation_analysis` (compute.py ~753-790), dont la boucle Python
coûte 27,7 s en prod sur 1035 paires (L2_tobit : 44,6 s au total pour
l'étape correlation_analysis).

Contrat de non-régression (exigé par le protocole symbose) :
  - mêmes r (±1e-4), mêmes p-values (±1e-4), mêmes paires, mêmes arrondis ;
  - mêmes champs de `pairs` (decision/strength/direction/n) ;
  - même gestion du dropna PAR PAIRE (intersection d'index) ;
  - top-5 scatter inchangé (le tri par |r| est reproduit via
    `significant_pairs`, la génération des plots reste dans compute.py).

Principe :
  - SANS NaN dans df[numeric_cols] : l'intersection d'index vaut tous les
    index pour chaque paire → pearsonr/spearmanr par paire sont
    mathématiquement égaux à une matrice de corrélations + la formule t
    exacte des p-values (identique à ce que scipy implémente en interne).
    Rangs Spearman calculés UNE fois par colonne (rankdata, méthode
    "average", identique à scipy.spearmanr).
  - AVEC NaN : repli boucle fidèle (copie exacte de la logique prod,
    pearsonr/spearmanr sur l'intersection d'index par paire).

Ce module est volontairement ISOLÉ : rien dans l'application ne l'importe
tant que l'A/B de non-régression n'a pas été validé par le directeur.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import rankdata, t as t_dist

from scipy.stats import pearsonr, spearmanr


def choose_method(numeric_cols: list[str], normality_results: dict) -> str:
    """Réplique exacte du choix de méthode de compute.correlation_analysis."""
    all_normal = all(
        normality_results.get(col, {}).get("conclusion") == "NORMALE"
        for col in numeric_cols
    )
    return "pearson" if all_normal else "spearman"


def _strength(r: float) -> str:
    ar = abs(r)
    if ar >= 0.8:
        return "Très forte"
    if ar >= 0.6:
        return "Forte"
    if ar >= 0.4:
        return "Modérée"
    if ar >= 0.2:
        return "Faible"
    return "Négligeable"


def _pair_entry(r: float, p: float, n_common: int) -> dict[str, Any]:
    return {
        "r": round(float(r), 4),
        "p_value": round(float(p), 5),
        "n": int(n_common),
        "decision": "Corrélation significative (p<0.05)" if p < 0.05
                    else "Pas de corrélation significative",
        "strength": _strength(r),
        "direction": "Positive" if r > 0 else "Négative",
    }


def _p_values_from_r(r_values: np.ndarray, n: int) -> np.ndarray:
    """Formule t exacte des p-values de Pearson/Spearman (celle de scipy).

    p = 2 * sf(|r| * sqrt((n-2)/(1-r²)), df=n-2) — équivalent à la
    distribution bêta utilisée par scipy.stats.pearsonr (écart ~1e-12).
    """
    r = np.clip(np.abs(r_values), 0.0, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_stat = r * np.sqrt((n - 2) / (1.0 - r * r))
    p = 2.0 * t_dist.sf(t_stat, n - 2)
    return np.where(np.isnan(r_values), np.nan, p)


def _pairs_from_matrix(
    r_matrix: np.ndarray,
    p_matrix_vals: np.ndarray,
    numeric_cols: list[str],
    n_common: int,
) -> tuple[dict[str, Any], list[tuple[str, str, str, float]]]:
    """Construit pairs + significant_pairs avec les formats prod exacts."""
    k = len(numeric_cols)
    pairs: dict[str, Any] = {}
    significant_pairs: list[tuple[str, str, str, float]] = []
    for i in range(k):
        for j in range(i + 1, k):
            r = float(r_matrix[i, j])
            p = float(p_matrix_vals[i, j])
            pair_key = f"{numeric_cols[i]} x {numeric_cols[j]}"
            pairs[pair_key] = _pair_entry(r, p, n_common)
            if p < 0.05:
                significant_pairs.append((pair_key, numeric_cols[i], numeric_cols[j], abs(r)))
    return pairs, significant_pairs


def _vectorized_no_nan(
    df: pd.DataFrame, numeric_cols: list[str], method: str
) -> tuple[np.ndarray, np.ndarray, int]:
    """Chemins vectorisés exacts (aucune NaN). Retourne (R, P, n)."""
    X = df[numeric_cols].to_numpy(dtype=np.float64)
    n = X.shape[0]

    if method == "pearson":
        with np.errstate(divide="ignore", invalid="ignore"):
            R = np.corrcoef(X, rowvar=False)
    else:  # spearman : rangs average par colonne, puis Pearson sur les rangs
        Ranks = rankdata(X, axis=0, method="average")
        with np.errstate(divide="ignore", invalid="ignore"):
            R = np.corrcoef(Ranks, rowvar=False)

    P = _p_values_from_r(R, n)
    return R, P, n


def _loop_fallback(
    df: pd.DataFrame, numeric_cols: list[str], method: str
) -> tuple[np.ndarray, np.ndarray, dict[int, int]]:
    """Repli boucle FIDÈLE à la prod : dropna PAR PAIRE + scipy par paire.

    Reproduit compute.correlation_analysis (~753-790) sans les plots :
    s1/s2 dropna, intersection d'index, test n>=3, scipy par paire.
    Retourne (R, P) et un dict {i: n_common} par colonne i (paires (i,j)
    avec n<3 laissées à 1.0 comme en prod).
    """
    k = len(numeric_cols)
    R = np.eye(k)
    P = np.ones((k, k))
    n_common_by_pair: dict[int, int] = {}

    for i, c1 in enumerate(numeric_cols):
        for j, c2 in enumerate(numeric_cols):
            if i < j:
                s1 = df[c1].dropna()
                s2 = df[c2].dropna()
                common = s1.index.intersection(s2.index)
                if len(common) >= 3:
                    if method == "pearson":
                        r, p = pearsonr(s1[common], s2[common])
                    else:
                        r, p = spearmanr(s1[common], s2[common])
                    R[i, j] = R[j, i] = r
                    P[i, j] = P[j, i] = p
                    n_common_by_pair[(i, j)] = len(common)
    return R, P, n_common_by_pair


def compute_correlation_pairs(
    df: pd.DataFrame, numeric_cols: list[str], method: str
) -> dict[str, Any]:
    """
    Point d'entrée du module. Calcule pairs + p_matrix + significant_pairs
    avec un contrat d'identité envers la boucle de production.

    method : "pearson" | "spearman" (cf. choose_method).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    if len(numeric_cols) < 2:
        return {"error": "Moins de 2 variables numériques pour la corrélation."}

    has_nan = bool(df[numeric_cols].isna().any().any())

    if not has_nan:
        R, P, n = _vectorized_no_nan(df, numeric_cols, method)
        pairs, significant_pairs = _pairs_from_matrix(R, P, numeric_cols, n)
        path = "vectorized"
    else:
        R, P, n_by_pair = _loop_fallback(df, numeric_cols, method)
        k = len(numeric_cols)
        pairs: dict[str, Any] = {}
        significant_pairs = []
        for i in range(k):
            for j in range(i + 1, k):
                if (i, j) in n_by_pair:
                    r = float(R[i, j])
                    p = float(P[i, j])
                    pair_key = f"{numeric_cols[i]} x {numeric_cols[j]}"
                    pairs[pair_key] = _pair_entry(r, p, n_by_pair[(i, j)])
                    if p < 0.05:
                        significant_pairs.append(
                            (pair_key, numeric_cols[i], numeric_cols[j], abs(r))
                        )
        n = -1
        path = "loop_fallback"

    return {
        "path": path,
        "pairs": pairs,
        "r_matrix": R,
        "p_matrix": pd.DataFrame(P, index=numeric_cols, columns=numeric_cols),
        "significant_pairs": significant_pairs,
    }
