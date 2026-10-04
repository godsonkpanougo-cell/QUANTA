"""
QUANTA — multiplicity.py
Module de correction pour les comparaisons multiples.

Fournit deux méthodes de correction standard pour contrôler le taux d'erreur
de Type I lors de tests multiples :
- Holm-Bonferroni : contrôle du Family-Wise Error Rate (FWER)
- Benjamini-Hochberg (FDR) : contrôle du False Discovery Rate

Ces corrections s'appliquent sur UNE famille de tests à la fois (ex: toutes
les paires de corrélation d'une même analyse = une famille).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any


def holm_bonferroni(p_values: list[float] | np.ndarray) -> np.ndarray:
    """
    Correction Holm-Bonferroni (step-down) pour contrôler le FWER.
    
    Plus puissant que Bonferroni standard tout en maintenant un contrôle
    strict du taux d'erreur familial.
    
    Args:
        p_values: Liste ou array de p-values brutes
        
    Returns:
        Array de p-values ajustées (même ordre que l'entrée)
        
    Reference:
        Holm, S. (1979). A simple sequentially rejective multiple test procedure.
        Scandinavian Journal of Statistics, 6(2), 65-70.
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    
    if n == 0:
        return np.array([])
    
    # Copie pour éviter de modifier l'original
    p_adj = p.copy()
    
    # Trier les p-values avec leurs indices originaux
    sorted_indices = np.argsort(p)
    sorted_p = p[sorted_indices]
    
    # Formule Holm-Bonferroni : p_adj[i] = min(1, p_sorted[i] * (n - i))
    # où i est le rang (0-indexed)
    sorted_p = np.minimum(sorted_p * (n - np.arange(n)), 1.0)

    # Contrainte monotone step-down : p_adj[i] = max_{j<=i} mult[j]
    # (cumul MAXIMISANT depuis le début — validé contre
    # statsmodels.stats.multitest.multipletests(method="holm"), voir
    # tests/test_multiplicity.py). Un cumul minimisant ici SOUS-CORRIGE
    # et laisse passer des faux positifs (bug corrigé le 02/10/2026).
    sorted_p = np.maximum.accumulate(sorted_p)

    # Remettre dans l'ordre original
    p_adj[sorted_indices] = sorted_p
    
    return p_adj


def benjamini_hochberg(p_values: list[float] | np.ndarray) -> np.ndarray:
    """
    Correction Benjamini-Hochberg (FDR) pour contrôler le False Discovery Rate.
    
    Plus puissant que Holm-Bonferroni pour les familles de tests nombreuses,
    au prix d'un contrôle moins strict (contrôle le FDR, pas le FWER).
    
    Args:
        p_values: Liste ou array de p-values brutes
        
    Returns:
        Array de p-values ajustées (q-values, même ordre que l'entrée)
        
    Reference:
        Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery
        rate: a practical and powerful approach to multiple testing.
        Journal of the Royal Statistical Society, Series B, 57(1), 289-300.
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    
    if n == 0:
        return np.array([])
    
    # Copie pour éviter de modifier l'original
    p_adj = p.copy()
    
    # Trier les p-values avec leurs indices originaux
    sorted_indices = np.argsort(p)
    sorted_p = p[sorted_indices]
    
    # Formule Benjamini-Hochberg : q[i] = min(1, p_sorted[i] * n / (i + 1))
    # où i est le rang (0-indexed)
    sorted_p = np.minimum(sorted_p * n / np.arange(1, n + 1), 1.0)

    # Contrainte monotone step-up : q[i] = min_{j>=i} mult[j]
    # (cumul MINIMISANT depuis la fin — validé contre
    # statsmodels.stats.multitest.multipletests(method="fdr_bh"), voir
    # tests/test_multiplicity.py). Un cumul maximisant ici SUR-CORRIGE
    # et élimine des découvertes vraies (bug corrigé le 02/10/2026).
    sorted_p = np.minimum.accumulate(sorted_p[::-1])[::-1]

    # Remettre dans l'ordre original
    p_adj[sorted_indices] = sorted_p
    
    return p_adj


def apply_fdr_correction_to_pairs(
    pairs: dict[str, dict[str, Any]],
    method: str = "bh"
) -> dict[str, dict[str, Any]]:
    """
    Applique la correction FDR (Benjamini-Hochberg) sur une famille de paires
    de tests (ex: toutes les paires de corrélation d'une analyse).
    
    Pour chaque paire, ajoute :
    - p_adjusted : p-value après correction FDR (q-value)
    - significant_adjusted : True si q < 0.05
    
    Les champs existants sont PRESERVÉS :
    - p_value (brut, inchangé)
    - significant (basé sur p < 0.05 brut)
    
    Args:
        pairs: Dictionnaire de paires {key: {p_value: float, ...}}
        method: "bh" pour Benjamini-Hochberg, "holm" pour Holm-Bonferroni
        
    Returns:
        Dictionnaire de paires avec les champs p_adjusted et significant_adjusted
        ajoutés à chaque entrée.
    """
    if not pairs:
        return pairs
    
    # Extraire toutes les p-values brutes dans l'ordre des clés
    keys = list(pairs.keys())
    p_values = []
    
    for key in keys:
        pair_data = pairs[key]
        p_val = pair_data.get("p_value")
        if p_val is not None and not np.isnan(p_val):
            p_values.append(float(p_val))
        else:
            p_values.append(1.0)  # p-value maximale si NaN/None
    
    p_values = np.array(p_values)
    
    # Appliquer la correction
    if method == "holm":
        p_adjusted = holm_bonferroni(p_values)
    else:  # défaut: Benjamini-Hochberg
        p_adjusted = benjamini_hochberg(p_values)
    
    # Mettre à jour chaque paire avec les valeurs ajustées
    for i, key in enumerate(keys):
        pair_data = pairs[key]
        pair_data["p_adjusted"] = round(float(p_adjusted[i]), 5)
        pair_data["significant_adjusted"] = bool(p_adjusted[i] < 0.05)
    
    return pairs


def count_significant_pairs(
    pairs: dict[str, dict[str, Any]],
    threshold: float = 0.05
) -> dict[str, int]:
    """
    Compte les paires significatives avant et après correction.
    
    Args:
        pairs: Dictionnaire de paires avec p_value et p_adjusted
        threshold: Seuil de significativité (défaut: 0.05)
        
    Returns:
        Dict avec counts : {raw: int, adjusted: int}
    """
    count_raw = 0
    count_adjusted = 0
    
    for pair_data in pairs.values():
        p_raw = pair_data.get("p_value")
        p_adj = pair_data.get("p_adjusted")
        
        if p_raw is not None and not np.isnan(p_raw) and p_raw < threshold:
            count_raw += 1
        
        if p_adj is not None and not np.isnan(p_adj) and p_adj < threshold:
            count_adjusted += 1
    
    return {
        "significant_raw": count_raw,
        "significant_adjusted": count_adjusted,
    }
