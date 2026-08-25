"""
QUANTA — compute.py (v2)
Couche de calcul déterministe (scipy / statsmodels / pandas).
Calcule les VRAIS chiffres avant de les envoyer au LLM.
Le LLM n'interprète que — il ne calcule jamais.

Changelog v2 (audit Jour 1) :
- Fix bug fillna(inplace=True) sur Series extraite (chaining assignment)
- Ajout garde-fou numérique-mais-catégoriel (codes région, Likert) -> reclassé en cat_cols
- Régression OLS rendue conditionnelle (n'est plus systématique)
- p_matrix de correlation_analysis maintenant retournée et utilisée
- Indices fixes des générateurs R/Stata sécurisés (plus de formules vides)
- Palette harmonisée avec le doc de specs (#0A0A0F)
- normality_tests : seuils clarifiés (Shapiro n<50 prioritaire, D'Agostino n>=20 en complément)
- Sortie restructurée pour préparer le branchement avec test_selector.py / orchestrator.py
"""

import io
import base64
import math
import warnings
import logging
import numpy as np
import pandas as pd
import matplotlib
import os
# Forcer le backend Agg avant toute importation pyplot
os.environ['MPLBACKEND'] = 'Agg'
matplotlib.use("Agg", force=True)  # mode sans affichage
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import shapiro, normaltest, pearsonr, spearmanr
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

logger = logging.getLogger(__name__)
logger.info(f"Matplotlib backend: {matplotlib.get_backend()}")
from statsmodels.stats.diagnostic import het_white, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson
from typing import Any

# Import des fonctions légères de validation d'upload (déplacées vers upload_validation.py)
# pour éviter de charger la stack scientifique lourde dans main.py
from app.compute.upload_validation import (
    ID_COLUMN_NAME_HINTS,
    CATEGORICAL_GUARD_MIN_N,
    CATEGORICAL_CARDINALITY_THRESHOLD,
    _detect_csv_encoding,
    _detect_csv_separator,
    _try_convert_french_decimal,
    _is_likely_id_column,
    _build_diagnosis_descriptive_stats,
    load_and_diagnose,
)

warnings.filterwarnings("ignore")

# ─── Palette QUANTA (harmonisée avec doc de specs Section 13) ────────────────
PALETTE = {
    "bg":     "#0A0A0F",
    "panel":  "#13131A",
    "gold":   "#C9A84C",
    "gold2":  "#E8D5A3",
    "text":   "#E8E8E8",
    "accent": "#00D4FF",
    "danger": "#FF4444",
    "muted":  "#555555",
}

# Taille minimale de l'échantillon pour appliquer la winsorisation des outliers
# (sous ce seuil, le 1er/99e centile ~= min/max -> ce ne sont pas des "outliers"
# mais les extrêmes naturels d'un petit échantillon)
WINSORIZATION_MIN_N = 30

def _apply_mpl_theme(theme: str = "dark") -> None:
    """
    Configure matplotlib / seaborn avant génération des graphiques.

    theme == "light" : style académique clair (default + whitegrid).
    theme == "dark"  : inchangé — _fig_style applique la palette QUANTA.
    """
    if theme != "light":
        return
    plt.style.use("default")
    sns.set_theme(
        style="whitegrid",
        rc={
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "text.color": "#1A1A1A",
            "axes.labelcolor": "#1A1A1A",
            "xtick.color": "#1A1A1A",
            "ytick.color": "#1A1A1A",
            "grid.color": "#666666",
            "axes.edgecolor": "#666666",
        },
    )


def _fig_style(fig, ax_list=None, theme: str = "dark"):
    """
    Applique le style QUANTA sur toutes les figures.
    
    theme : "dark" (défaut) ou "light" (rapport académique clair).
    """
    if theme == "light":
        # Style académique clair
        fig.patch.set_facecolor("white")
        for ax in (ax_list if ax_list is not None else fig.axes):
            ax.set_facecolor("white")
            ax.tick_params(colors="#1A1A1A", labelsize=9)
            ax.xaxis.label.set_color("#1A1A1A")
            ax.yaxis.label.set_color("#1A1A1A")
            ax.title.set_color("#1A1A1A")
            for spine in ax.spines.values():
                spine.set_edgecolor("#666666")
    else:
        # Style dark luxury QUANTA
        fig.patch.set_facecolor(PALETTE["bg"])
        for ax in (ax_list if ax_list is not None else fig.axes):
            ax.set_facecolor(PALETTE["panel"])
            ax.tick_params(colors=PALETTE["text"], labelsize=9)
            ax.xaxis.label.set_color(PALETTE["text"])
            ax.yaxis.label.set_color(PALETTE["text"])
            ax.title.set_color(PALETTE["gold"])
            for spine in ax.spines.values():
                spine.set_edgecolor(PALETTE["muted"])

def _fig_to_b64(fig, dpi: int = 80, theme: str = "dark") -> str:
    """
    Convertit une figure matplotlib en base64 PNG (dpi réduit pour le poids).
    
    theme : "dark" (défaut) ou "light" (rapport académique clair).
    """
    try:
        facecolor = "white" if theme == "light" else PALETTE["bg"]
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                     facecolor=facecolor)
        plt.close(fig)
        buf.seek(0)
        b64_str = base64.b64encode(buf.read()).decode()
        logger.debug(f"Generated chart: {len(b64_str)} chars base64")
        return b64_str
    except Exception as e:
        logger.error(f"Failed to generate chart: {e}")
        plt.close(fig)
        return ""

def generate_boxplot(df: pd.DataFrame, target_col: str, group_col: str, theme: str = "dark") -> str:
    """
    Génère un boxplot montrant la distribution de target_col pour chaque groupe de group_col.
    
    Retourne une chaîne base64 de l'image PNG.
    """
    _apply_mpl_theme(theme)
    
    fig, ax = plt.subplots(figsize=(7, 4))
    
    if theme == "light":
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
    else:
        fig.patch.set_facecolor(PALETTE["bg"])
        ax.set_facecolor(PALETTE["panel"])
    
    groups = df[group_col].unique()
    data = [df[df[group_col]==g][target_col].dropna() for g in groups]
    
    bp = ax.boxplot(data, labels=groups, patch_artist=True)
    
    if theme == "light":
        for patch in bp['boxes']:
            patch.set_facecolor('white')
            patch.set_edgecolor('#1A1A1A')
        for element in ['whiskers','caps']:
            for line in bp[element]:
                line.set_color('#666666')
        for median in bp['medians']:
            median.set_color('#1A1A1A')
        for flier in bp['fliers']:
            flier.set_markerfacecolor('#1A1A1A')
            flier.set_alpha(0.5)
        
        ax.set_title(f'Distribution de {target_col} par {group_col}', color='#1A1A1A', fontsize=13, pad=15)
        ax.set_xlabel(group_col, color='#1A1A1A')
        ax.set_ylabel(target_col, color='#1A1A1A')
        ax.tick_params(colors='#1A1A1A')
        for spine in ax.spines.values():
            spine.set_edgecolor('#666666')
        ax.grid(True, alpha=0.3, color='#CCCCCC')
    else:
        for patch in bp['boxes']:
            patch.set_facecolor(PALETTE["panel"])
            patch.set_edgecolor(PALETTE["gold"])
        for element in ['whiskers','caps']:
            for line in bp[element]:
                line.set_color(PALETTE["muted"])
        for median in bp['medians']:
            median.set_color(PALETTE["accent"])
        for flier in bp['fliers']:
            flier.set_markerfacecolor(PALETTE["gold"])
            flier.set_alpha(0.5)
        
        ax.set_title(f'Distribution de {target_col} par {group_col}', color=PALETTE["text"], fontsize=13, pad=15)
        ax.set_xlabel(group_col, color=PALETTE["muted"])
        ax.set_ylabel(target_col, color=PALETTE["muted"])
        ax.tick_params(colors=PALETTE["muted"])
        for spine in ax.spines.values():
            spine.set_edgecolor('#555563')
        ax.grid(True, alpha=0.1, color='#555563')
    
    plt.tight_layout()
    return _fig_to_b64(fig, theme=theme)


def generate_scatter(df: pd.DataFrame, var1: str, var2: str, theme: str = "dark") -> str:
    """
    Génère un scatter plot entre deux variables avec droite de régression.
    
    Retourne une chaîne base64 de l'image PNG.
    """
    _apply_mpl_theme(theme)
    
    fig, ax = plt.subplots(figsize=(7, 4))
    
    if theme == "light":
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
    else:
        fig.patch.set_facecolor(PALETTE["bg"])
        ax.set_facecolor(PALETTE["panel"])
    
    x = df[var1].dropna()
    y = df[var2].dropna()
    common_idx = x.index.intersection(y.index)
    x, y = x[common_idx], y[common_idx]
    
    if theme == "light":
        ax.scatter(x, y, color='#1A1A1A', alpha=0.5, s=30, edgecolors='none')
        line_color = '#1A1A1A'
        text_color = '#1A1A1A'
        grid_color = '#CCCCCC'
        spine_color = '#666666'
    else:
        ax.scatter(x, y, color=PALETTE["gold"], alpha=0.5, s=30, edgecolors='none')
        line_color = PALETTE["accent"]
        text_color = PALETTE["text"]
        grid_color = '#555563'
        spine_color = '#555563'
    
    # Droite de régression
    z = np.polyfit(x, y, 1)
    p = np.poly1d(z)
    ax.plot(sorted(x), p(sorted(x)), color=line_color, linewidth=1.5, linestyle='--', alpha=0.8)
    
    ax.set_title(f'Corrélation : {var1} vs {var2}', color=text_color, fontsize=13, pad=15)
    ax.set_xlabel(var1, color=text_color)
    ax.set_ylabel(var2, color=text_color)
    ax.tick_params(colors=text_color)
    for spine in ax.spines.values():
        spine.set_edgecolor(spine_color)
    ax.grid(True, alpha=0.1 if theme == "dark" else 0.3, color=grid_color)
    
    plt.tight_layout()
    return _fig_to_b64(fig, theme=theme)



# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# 2. NETTOYAGE CHIRURGICAL
# ═══════════════════════════════════════════════════════════════════════════════

def clean_dataframe(df: pd.DataFrame, diag: dict) -> dict[str, Any]:
    """
    Nettoie le DataFrame selon des règles académiques documentées.
    Retourne le DF propre + log structuré de chaque décision (audit_log).

    Chaque entrée de audit_log est un dict :
      {etape, colonne, decision, valeur, justification}
    -> format directement exploitable par l'orchestrateur et le LLM.
    """
    df = df.copy()
    audit_log: list[dict[str, Any]] = []

    # 1. Doublons — détection et log, sans suppression automatique
    #    (les données utilisateur ne sont pas modifiées sans accord explicite).
    n_dupes_clean = int(df.duplicated().sum())
    if n_dupes_clean:
        audit_log.append({
            "etape": "doublons",
            "colonne": None,
            "decision": "detection_sans_suppression",
            "valeur": n_dupes_clean,
            "justification": (
                f"{n_dupes_clean} ligne(s) dupliquée(s) exactement détectée(s) — "
                f"conservées intactes (aucune suppression automatique)."
            ),
        })
    else:
        audit_log.append({
            "etape": "doublons",
            "colonne": None,
            "decision": "aucun_doublon",
            "valeur": 0,
            "justification": "Aucun doublon exact détecté.",
        })

    numeric_cols = diag.get("numeric_cols", [])
    cat_cols     = diag.get("cat_cols", [])

    # 2. Valeurs manquantes — stratégie adaptative (numériques continues)
    for col in numeric_cols:
        if col not in df.columns:
            continue
        pct = df[col].isnull().mean() * 100
        if pct == 0:
            continue
        elif pct < 5:
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
            audit_log.append({
                "etape": "valeurs_manquantes",
                "colonne": col,
                "decision": "imputation_mediane",
                "valeur": round(float(median_val), 4),
                "justification": f"{pct:.1f}% manquants (< 5%) -> imputation par la médiane.",
            })
        elif pct < 20:
            mean_val = df[col].mean()
            df[col] = df[col].fillna(mean_val)
            audit_log.append({
                "etape": "valeurs_manquantes",
                "colonne": col,
                "decision": "imputation_moyenne",
                "valeur": round(float(mean_val), 4),
                "justification": f"{pct:.1f}% manquants (5-20%) -> imputation par la moyenne.",
            })
        else:
            df = df.drop(columns=[col])
            audit_log.append({
                "etape": "valeurs_manquantes",
                "colonne": col,
                "decision": "suppression_colonne",
                "valeur": round(pct, 1),
                "justification": f"{pct:.1f}% manquants (> 20%) -> variable jugée trop incomplète, supprimée.",
            })

    # 2bis. Valeurs manquantes — catégorielles
    for col in cat_cols:
        if col not in df.columns:
            continue
        pct = df[col].isnull().mean() * 100
        if pct == 0:
            continue
        elif pct < 20:
            mode_series = df[col].mode()
            mode_val = mode_series[0] if not mode_series.empty else "Inconnu"
            df[col] = df[col].fillna(mode_val)
            audit_log.append({
                "etape": "valeurs_manquantes",
                "colonne": col,
                "decision": "imputation_mode",
                "valeur": str(mode_val),
                "justification": f"{pct:.1f}% manquants (< 20%) -> imputation par le mode ('{mode_val}').",
            })
        else:
            df = df.drop(columns=[col])
            audit_log.append({
                "etape": "valeurs_manquantes",
                "colonne": col,
                "decision": "suppression_colonne",
                "valeur": round(pct, 1),
                "justification": f"{pct:.1f}% manquants (> 20%) -> variable jugée trop incomplète, supprimée.",
            })

    # 3. Traitement des outliers (Winsorisation 1%-99%) — uniquement sur les
    #    colonnes numériques continues encore présentes, et uniquement si
    #    l'échantillon est assez grand (Fix #4) : sous WINSORIZATION_MIN_N,
    #    le 1er/99e centile ~= min/max, donc "winsoriser" reviendrait à
    #    tronquer les valeurs extrêmes légitimes d'un petit échantillon,
    #    pas à corriger de vrais outliers.
    remaining_numeric = [c for c in numeric_cols if c in df.columns]
    n_current = len(df)

    if n_current < WINSORIZATION_MIN_N:
        if remaining_numeric:
            audit_log.append({
                "etape": "outliers",
                "colonne": None,
                "decision": "winsorisation_non_appliquee",
                "valeur": n_current,
                "justification": (
                    f"Échantillon de taille n={n_current} (< {WINSORIZATION_MIN_N}) "
                    f"-> winsorisation non appliquée. Sur un petit échantillon, le "
                    f"1er/99e centile coïncide quasiment avec le min/max : tronquer "
                    f"ces valeurs reviendrait à supprimer des observations légitimes, "
                    f"pas de véritables outliers."
                ),
            })
    else:
        for col in remaining_numeric:
            q01 = df[col].quantile(0.01)
            q99 = df[col].quantile(0.99)
            n_out = int(((df[col] < q01) | (df[col] > q99)).sum())
            if n_out > 0:
                df[col] = df[col].clip(lower=q01, upper=q99)
                audit_log.append({
                    "etape": "outliers",
                    "colonne": col,
                    "decision": "winsorisation_1_99",
                    "valeur": n_out,
                    "justification": (
                        f"{n_out} valeur(s) extrême(s) ramenée(s) aux bornes du "
                        f"1er/99e centile [{q01:.3f}, {q99:.3f}]."
                    ),
                })

    # 4. Nettoyage des chaînes pour les colonnes catégorielles restantes
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()

    audit_log.append({
        "etape": "synthese",
        "colonne": None,
        "decision": "dataset_final",
        "valeur": f"{len(df)}x{len(df.columns)}",
        "justification": f"Dataset final : {len(df)} lignes x {len(df.columns)} colonnes après nettoyage.",
    })

    return {
        "dataframe_clean": df,
        "audit_log":       audit_log,
        "n_final":         len(df),
        "n_cols_final":    len(df.columns),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 3. STATISTIQUES DESCRIPTIVES
# ═══════════════════════════════════════════════════════════════════════════════

def descriptive_stats(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str], theme: str = "dark") -> dict[str, Any]:
    """
    Calcule les statistiques descriptives complètes pour les colonnes
    explicitement classifiées comme numériques continues / catégorielles
    (passées par l'appelant, issues du diagnostic -- évite de re-deviner
    les types ici).
    
    theme : "dark" (défaut) ou "light" (rapport académique clair).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    cat_cols     = [c for c in cat_cols if c in df.columns]

    _apply_mpl_theme(theme)

    # Palette selon le thème
    if theme == "light":
        bar_color = "#2C5F8A"  # bleu académique
        mean_color = "#E63946"  # rouge pour moyenne
        median_color = "#457B9D"  # bleu foncé pour médiane
        title_color = "#1A1A1A"
        legend_facecolor = "white"
        legend_textcolor = "#1A1A1A"
    else:
        bar_color = PALETTE["gold"]
        mean_color = PALETTE["accent"]
        median_color = PALETTE["gold2"]
        title_color = PALETTE["gold"]
        legend_facecolor = PALETTE["panel"]
        legend_textcolor = PALETTE["text"]

    desc_num = {}
    for col in numeric_cols:
        s = df[col].dropna()
        if s.empty:
            continue
        q1, q2, q3 = s.quantile([0.25, 0.5, 0.75])
        mean_val = float(s.mean())
        desc_num[col] = {
            "n":        int(s.count()),
            "mean":     round(mean_val, 4),
            "std":      round(float(s.std()), 4),
            "min":      round(float(s.min()), 4),
            "Q1":       round(float(q1), 4),
            "median":   round(float(q2), 4),
            "Q3":       round(float(q3), 4),
            "max":      round(float(s.max()), 4),
            "skewness": round(float(s.skew()), 4),
            "kurtosis": round(float(s.kurt()), 4),
            "cv_pct":   round(float(s.std() / mean_val * 100), 2) if mean_val != 0 else None,
            "IQR":      round(float(q3 - q1), 4),
        }

    desc_cat = {}
    for col in cat_cols:
        vc = df[col].value_counts()
        desc_cat[col] = {
            "n_unique":  int(df[col].nunique()),
            "mode":      str(vc.index[0]) if len(vc) else "N/A",
            "mode_freq": int(vc.iloc[0]) if len(vc) else 0,
            "mode_pct":  round(vc.iloc[0] / len(df) * 100, 2) if len(vc) else 0,
            "top5":      {str(k): int(v) for k, v in vc.head(5).to_dict().items()},
        }

    charts = {}

    # Histogrammes des variables numériques (max 6)
    cols_to_plot = numeric_cols[:6]
    if cols_to_plot:
        n = len(cols_to_plot)
        ncols = min(n, 3)
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(3.5 * ncols, 2.8 * nrows))
        axes = np.array(axes).flatten() if n > 1 else np.array([axes])

        for i, col in enumerate(cols_to_plot):
            ax = axes[i]
            s = df[col].dropna()
            edgecolor = "white" if theme == "light" else PALETTE["bg"]
            ax.hist(s, bins=30, color=bar_color, alpha=0.85, edgecolor=edgecolor)
            ax.axvline(s.mean(), color=mean_color, linewidth=1.5, linestyle="--",
                       label=f"Moy={s.mean():.2f}")
            ax.axvline(s.median(), color=median_color, linewidth=1.2, linestyle=":",
                       label=f"Méd={s.median():.2f}")
            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel(col, fontsize=8)
            ax.set_ylabel("Fréquence", fontsize=8)
            ax.legend(fontsize=7, facecolor=legend_facecolor, labelcolor=legend_textcolor)

        for j in range(len(cols_to_plot), len(axes)):
            axes[j].set_visible(False)

        fig.suptitle("QUANTA — Distributions des variables numériques",
                      color=title_color, fontsize=12, fontweight="bold", y=1.02)
        _fig_style(fig, axes[:n], theme=theme)
        plt.tight_layout()
        charts["distributions"] = _fig_to_b64(fig, theme=theme)

    # Barres pour les variables catégorielles (max 3)
    cat_to_plot = cat_cols[:3]
    if cat_to_plot:
        n = len(cat_to_plot)
        fig, axes = plt.subplots(1, n, figsize=(4.5 * n, 3.0))
        axes = np.array([axes]) if n == 1 else axes.flatten()

        for i, col in enumerate(cat_to_plot):
            ax = axes[i]
            vc = df[col].value_counts().head(10)
            edgecolor = "white" if theme == "light" else PALETTE["bg"]
            text_color = "#1A1A1A" if theme == "light" else PALETTE["text"]
            bars = ax.barh(vc.index.astype(str), vc.values,
                            color=bar_color, edgecolor=edgecolor)
            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel("Effectif", fontsize=8)
            for bar, v in zip(bars, vc.values):
                ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                        f"{v}", va="center", fontsize=7, color=text_color)

        fig.suptitle("QUANTA — Répartition des variables catégorielles",
                      color=title_color, fontsize=12, fontweight="bold")
        _fig_style(fig, axes, theme=theme)
        plt.tight_layout()
        charts["categories"] = _fig_to_b64(fig, theme=theme)

    return {
        "descriptive_numeric":     desc_num,
        "descriptive_categorical": desc_cat,
        "charts":                  charts,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 4. TESTS DE NORMALITÉ (H0/H1 formels)
# ═══════════════════════════════════════════════════════════════════════════════

def normality_tests(df: pd.DataFrame, numeric_cols: list[str], theme: str = "dark") -> dict[str, Any]:
    """
    Pour chaque variable numérique continue :
      - Shapiro-Wilk (le plus puissant pour n < 50, utilisable jusqu'à 5000)
      - D'Agostino-Pearson en complément si n >= 20 (recommandé pour échantillons
        moyens/grands -- moins sensible aux écarts mineurs que Shapiro sur gros n)

    Décision consolidée :
      - Si n < 20 : on se fie uniquement à Shapiro-Wilk (D'Agostino non fiable
        sous n=20, scipy lève une erreur ou un warning).
      - Si n >= 20 : NORMALE seulement si les deux tests disponibles concordent
        (p > 0.05 pour chacun). En cas de désaccord, conclusion = "AMBIGÜE"
        et on recommande la prudence (tests non-paramétriques par défaut).
    
    theme : "dark" (défaut) ou "light" (rapport académique clair).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    results = {}
    charts  = {}

    _apply_mpl_theme(theme)

    # Palette selon le thème
    if theme == "light":
        marker_color = "#2C5F8A"  # bleu académique
        line_color = "#666666"
        title_color = "#1A1A1A"
    else:
        marker_color = PALETTE["gold"]
        line_color = PALETTE["accent"]
        title_color = PALETTE["gold"]

    cols_to_plot = numeric_cols[:4]
    fig = axes = None
    if cols_to_plot:
        n = len(cols_to_plot)
        ncols = min(n, 2)
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(4.5 * ncols, 3.5 * nrows))
        axes = np.array(axes).flatten() if n > 1 else np.array([axes])

    for col in numeric_cols:
        s = df[col].dropna()
        n_obs = len(s)
        col_result: dict[str, Any] = {"n": n_obs}

        if n_obs >= 3:
            try:
                sample = s if n_obs <= 5000 else s.sample(5000, random_state=42)
                stat_sw, p_sw = shapiro(sample)
                col_result["shapiro_wilk"] = {
                    "statistic": round(float(stat_sw), 5),
                    "p_value":   round(float(p_sw), 5),
                    "H0": "Distribution normale",
                    "decision": "Ne rejette pas H0 (normale)" if p_sw > 0.05 else "Rejette H0 (non-normale)",
                    "alpha": 0.05,
                }
            except Exception:
                pass

        if n_obs >= 20:
            try:
                stat_da, p_da = normaltest(s)
                col_result["dagostino_pearson"] = {
                    "statistic": round(float(stat_da), 5),
                    "p_value":   round(float(p_da), 5),
                    "H0": "Distribution normale",
                    "decision": "Ne rejette pas H0 (normale)" if p_da > 0.05 else "Rejette H0 (non-normale)",
                    "alpha": 0.05,
                }
            except Exception:
                pass

        # Décision consolidée
        sw = col_result.get("shapiro_wilk")
        da = col_result.get("dagostino_pearson")

        if n_obs < 20:
            if sw:
                conclusion = "NORMALE" if sw["p_value"] > 0.05 else "NON-NORMALE"
                methode = "Shapiro-Wilk uniquement (n < 20, D'Agostino non fiable)"
            else:
                conclusion = "INDETERMINEE"
                methode = "Échantillon trop petit pour un test de normalité fiable (n < 3)"
        else:
            sw_normal = sw["p_value"] > 0.05 if sw else None
            da_normal = da["p_value"] > 0.05 if da else None
            if sw_normal is not None and da_normal is not None:
                if sw_normal and da_normal:
                    conclusion = "NORMALE"
                    methode = "Shapiro-Wilk et D'Agostino-Pearson concordent (normale)"
                elif not sw_normal and not da_normal:
                    conclusion = "NON-NORMALE"
                    methode = "Shapiro-Wilk et D'Agostino-Pearson concordent (non-normale)"
                else:
                    conclusion = "AMBIGUE"
                    methode = (
                        "Désaccord entre Shapiro-Wilk et D'Agostino-Pearson -> "
                        "tests non-paramétriques recommandés par prudence."
                    )
            elif sw_normal is not None:
                conclusion = "NORMALE" if sw_normal else "NON-NORMALE"
                methode = "Shapiro-Wilk uniquement"
            else:
                conclusion = "INDETERMINEE"
                methode = "Aucun test de normalité n'a pu être calculé."

        col_result["conclusion"] = conclusion
        col_result["methode_decision"] = methode
        col_result["recommended_tests"] = (
            "Tests paramétriques (t-test, ANOVA, Pearson)" if conclusion == "NORMALE"
            else "Tests non-paramétriques (Mann-Whitney, Kruskal-Wallis, Spearman)"
        )

        results[col] = col_result

    # QQ-plots
    if cols_to_plot and fig is not None:
        for i, col in enumerate(cols_to_plot):
            s = df[col].dropna()
            ax = axes[i]
            sm.qqplot(s, line="s", ax=ax, alpha=0.6,
                      markerfacecolor=marker_color, markersize=3,
                      markeredgecolor=marker_color)
            ax.get_lines()[0].set_color(marker_color)
            ax.get_lines()[1].set_color(line_color)
            conclusion = results.get(col, {}).get("conclusion", "")
            ax.set_title(f"QQ-Plot — {col}\n({conclusion})", fontsize=9)

        for j in range(len(cols_to_plot), len(axes)):
            axes[j].set_visible(False)

        fig.suptitle("QUANTA — Tests de normalité (QQ-Plots)",
                      color=title_color, fontsize=12, fontweight="bold")
        _fig_style(fig, axes[:len(cols_to_plot)], theme=theme)
        plt.tight_layout()
        charts["qqplots"] = _fig_to_b64(fig, theme=theme)

    return {"normality": results, "charts": charts}

# ═══════════════════════════════════════════════════════════════════════════════
# 5. CORRÉLATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def correlation_analysis(df: pd.DataFrame, numeric_cols: list[str], normality_results: dict, theme: str = "dark") -> dict[str, Any]:
    """
    Pearson si toutes les variables sont normales, Spearman sinon.
    Retourne la matrice de corrélation, la matrice de p-values associée
    (désormais utilisée), les paires significatives classées, et la heatmap.
    
    theme : "dark" (défaut) ou "light" (rapport académique clair).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    if len(numeric_cols) < 2:
        return {"error": "Moins de 2 variables numériques pour la corrélation."}

    _apply_mpl_theme(theme)

    all_normal = all(
        normality_results.get(col, {}).get("conclusion") == "NORMALE"
        for col in numeric_cols
    )
    method = "pearson" if all_normal else "spearman"

    corr_matrix = df[numeric_cols].corr(method=method).round(4)
    p_matrix = pd.DataFrame(
        np.ones((len(numeric_cols), len(numeric_cols))),
        index=numeric_cols, columns=numeric_cols,
    )

    pairs = {}
    scatter_plots = {}
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

                    p_matrix.loc[c1, c2] = p
                    p_matrix.loc[c2, c1] = p

                    pair_key = f"{c1} x {c2}"
                    pairs[pair_key] = {
                        "r":        round(float(r), 4),
                        "p_value":  round(float(p), 5),
                        "n":        len(common),
                        "decision": "Corrélation significative (p<0.05)" if p < 0.05
                                    else "Pas de corrélation significative",
                        "strength": (
                            "Très forte" if abs(r) >= 0.8 else
                            "Forte"      if abs(r) >= 0.6 else
                            "Modérée"    if abs(r) >= 0.4 else
                            "Faible"     if abs(r) >= 0.2 else "Négligeable"
                        ),
                        "direction": "Positive" if r > 0 else "Négative",
                    }
                    
                    # Générer scatter plot pour les corrélations significatives
                    if p < 0.05:
                        try:
                            scatter_b64 = generate_scatter(df, c1, c2, theme=theme)
                            scatter_plots[pair_key] = scatter_b64
                        except Exception as e:
                            scatter_plots[pair_key] = None

    # Heatmap
    charts = {}
    n = len(numeric_cols)
    size = max(4, n * 0.7)
    fig, ax = plt.subplots(figsize=(size, size * 0.7))

    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    cmap = sns.diverging_palette(220, 40, as_cmap=True)
    
    # Palette selon le thème
    annot_color = "#1A1A1A" if theme == "light" else PALETTE["text"]
    line_color = "#666666" if theme == "light" else PALETTE["muted"]
    
    sns.heatmap(
        corr_matrix, mask=mask, ax=ax, cmap=cmap,
        vmin=-1, vmax=1, center=0, square=True,
        annot=True, fmt=".2f", annot_kws={"size": 8, "color": annot_color},
        linewidths=0.5, linecolor=line_color,
        cbar_kws={"shrink": 0.8},
    )
    ax.set_title(f"Matrice de corrélation ({method.capitalize()})",
                  fontsize=11, fontweight="bold")
    _fig_style(fig, [ax], theme=theme)
    plt.tight_layout()
    charts["correlation_heatmap"] = _fig_to_b64(fig, theme=theme)

    return {
        "method":     method,
        "all_normal": all_normal,
        "matrix":     corr_matrix.to_dict(),
        "p_matrix":   p_matrix.round(5).to_dict(),
        "pairs":      pairs,
        "scatter_plots": scatter_plots,
        "charts":     charts,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 6. RÉGRESSION OLS (désormais CONDITIONNELLE)
# ═══════════════════════════════════════════════════════════════════════════════

def ols_regression(
    df: pd.DataFrame,
    numeric_cols: list[str],
    target_col: str | None = None,
    theme: str = "dark",
) -> dict[str, Any]:
    """
    Régression OLS. NE S'EXÉCUTE QUE SI :
      - target_col est explicitement fourni par l'orchestrateur (basé sur
        l'objectif utilisateur / l'arbre de décision de test_selector.py), ET
      - target_col est dans numeric_cols (donc une variable continue, pas une
        catégorielle reclassée), ET
      - il reste au moins 1 variable explicative numérique continue, ET
      - il y a suffisamment d'observations complètes.

    Si target_col est None : ne calcule rien et retourne un statut explicite
    "skipped" plutôt que de choisir arbitrairement une variable Y. C'est
    à l'orchestrateur / test_selector.py de décider si une régression est
    pertinente pour l'objectif de l'utilisateur.
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    if target_col is None:
        return {
            "status": "skipped",
            "reason": "Aucune variable cible fournie -> la régression OLS n'est exécutée "
                      "que si l'objectif de l'utilisateur ou l'arbre de décision la justifie.",
        }

    if target_col not in numeric_cols:
        return {
            "status": "skipped",
            "reason": (
                f"'{target_col}' n'est pas une variable numérique continue "
                f"(elle a peut-être été reclassée comme catégorielle) -> "
                f"régression OLS non pertinente, voir test_selector.py pour le "
                f"test approprié (ex: régression logistique)."
            ),
        }

    y_col = target_col
    x_cols = [c for c in numeric_cols if c != y_col][:8]  # max 8 régresseurs

    if not x_cols:
        return {"status": "skipped", "reason": "Aucune variable explicative numérique continue disponible."}

    sub = df[[y_col] + x_cols].dropna()
    if len(sub) < len(x_cols) + 5:
        return {"status": "skipped", "reason": "Pas assez d'observations complètes pour la régression."}

    Y = sub[y_col]
    X = sm.add_constant(sub[x_cols])

    try:
        model = sm.OLS(Y, X).fit()
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    vif_data = {}
    try:
        for idx, col in enumerate(X.columns):
            if col == "const":
                continue
            vif_data[col] = round(variance_inflation_factor(X.values, idx), 3)
    except Exception:
        pass

    residuals = model.resid
    dw_stat = round(float(durbin_watson(residuals)), 4)

    het_bp = {}
    try:
        lm, lm_p, _, _ = het_breuschpagan(residuals, X)
        het_bp = {
            "LM_stat": round(float(lm), 4),
            "p_value": round(float(lm_p), 5),
            "decision": "Hétéroscédasticité détectée (p<0.05)" if lm_p < 0.05 else "Homoscédasticité (OK)",
        }
    except Exception:
        pass

    het_w = {}
    try:
        lm_w, lm_p_w, _, _ = het_white(residuals, X)
        het_w = {
            "LM_stat": round(float(lm_w), 4),
            "p_value": round(float(lm_p_w), 5),
            "decision": "Hétéroscédasticité (White)" if lm_p_w < 0.05 else "Homoscédasticité (White OK)",
        }
    except Exception:
        pass

    # Graphique résidus
    _apply_mpl_theme(theme)
    if theme == "light":
        bar_color = "#2C5F8A"
        ref_line_color = "#666666"
        edgecolor = "white"
        title_color = "#1A1A1A"
    else:
        bar_color = PALETTE["gold"]
        ref_line_color = PALETTE["accent"]
        edgecolor = PALETTE["bg"]
        title_color = PALETTE["gold"]

    charts = {}
    fig, axes = plt.subplots(1, 2, figsize=(7, 3.0))

    axes[0].scatter(model.fittedvalues, residuals, color=bar_color, alpha=0.6, s=20)
    axes[0].axhline(0, color=ref_line_color, linewidth=1.5, linestyle="--")
    axes[0].set_xlabel("Valeurs ajustées", fontsize=9)
    axes[0].set_ylabel("Résidus", fontsize=9)
    axes[0].set_title("Résidus vs Valeurs ajustées", fontsize=10)

    axes[1].hist(residuals, bins=25, color=bar_color, alpha=0.85, edgecolor=edgecolor)
    axes[1].set_title("Distribution des résidus", fontsize=10)
    axes[1].set_xlabel("Résidus", fontsize=9)
    axes[1].set_ylabel("Fréquence", fontsize=9)

    fig.suptitle(f"QUANTA — Diagnostic Régression OLS (Y = {y_col})",
                  color=title_color, fontsize=12, fontweight="bold")
    _fig_style(fig, axes, theme=theme)
    plt.tight_layout()
    charts["regression_diagnostics"] = _fig_to_b64(fig, theme=theme)

    coef_summary = {}
    for var in model.params.index:
        coef_summary[var] = {
            "coefficient": round(float(model.params[var]), 6),
            "std_err":     round(float(model.bse[var]), 6),
            "t_stat":      round(float(model.tvalues[var]), 4),
            "p_value":     round(float(model.pvalues[var]), 5),
            "ci_lower":    round(float(model.conf_int().loc[var, 0]), 6),
            "ci_upper":    round(float(model.conf_int().loc[var, 1]), 6),
            "significant": bool(model.pvalues[var] < 0.05),
        }

    return {
        "status":        "ok",
        "y_variable":    y_col,
        "x_variables":   x_cols,
        "n_obs":         int(model.nobs),
        "R2":            round(float(model.rsquared), 4),
        "R2_adj":        round(float(model.rsquared_adj), 4),
        "F_stat":        round(float(model.fvalue), 4),
        "F_pvalue":      round(float(model.f_pvalue), 6),
        "AIC":           round(float(model.aic), 2),
        "BIC":           round(float(model.bic), 2),
        "RMSE":          round(float(np.sqrt(model.mse_resid)), 4),
        "coefficients":  coef_summary,
        "VIF":           vif_data,
        "durbin_watson": dw_stat,
        "dw_interpretation": (
            "Pas d'autocorrélation" if 1.5 < dw_stat < 2.5
            else "Autocorrélation positive possible" if dw_stat < 1.5
            else "Autocorrélation négative possible"
        ),
        "breusch_pagan": het_bp,
        "white_test":    het_w,
        "charts":        charts,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 7. GÉNÉRATEUR DE SCRIPTS R ET STATA (indices sécurisés)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_r_script(df: pd.DataFrame, filename: str,
                       numeric_cols: list[str],
                       regression_result: dict | None = None,
                       n_missing: int = 0) -> str:
    """
    Génère un script R commenté et reproductible.
    Sécurisé : si aucune régression n'a été exécutée (status != "ok"), la
    section régression est omise proprement plutôt que de produire une
    formule R invalide (ex: 'y ~ ' sans variable).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    regression_result = regression_result or {}
    has_regression = regression_result.get("status") == "ok"

    desc_cols = numeric_cols[:6] if numeric_cols else []
    norm_cols = numeric_cols[:4] if numeric_cols else []
    corr_cols = numeric_cols[:6] if len(numeric_cols) >= 2 else []
    impute_cols = numeric_cols[:5] if numeric_cols else []

    lines = []
    lines.append("# ═══════════════════════════════════════════════════════")
    lines.append("# QUANTA — Script R généré automatiquement")
    lines.append(f"# Fichier analysé : {filename}")
    lines.append("# ═══════════════════════════════════════════════════════")
    lines.append("")
    lines.append("# ── 0. Packages requis ─────────────────────────────────")
    lines.append('packages <- c("tidyverse", "psych", "car", "lmtest",')
    lines.append('              "nortest", "ggplot2", "corrplot", "stargazer")')
    lines.append("lapply(packages, function(p) {")
    lines.append('  if (!require(p, character.only = TRUE)) install.packages(p)')
    lines.append("  library(p, character.only = TRUE)")
    lines.append("})")
    lines.append("")
    lines.append("# ── 1. Chargement des données ──────────────────────────")
    lines.append(f'df <- read.csv("{filename}", sep = ",", header = TRUE,')
    lines.append('               stringsAsFactors = FALSE, encoding = "UTF-8")')
    lines.append('cat("Dimensions :", nrow(df), "lignes x", ncol(df), "colonnes\\n")')
    lines.append("")
    lines.append("# ── 2. Aperçu structurel ──────────────────────────────")
    lines.append("str(df)")
    lines.append("summary(df)")
    lines.append("")
    lines.append("# ── 3. Nettoyage ──────────────────────────────────────")
    lines.append("df <- df[!duplicated(df), ]")
    lines.append("")
    if n_missing > 0 and impute_cols:
        lines.append("# Imputation des valeurs manquantes (médiane pour numériques)")
        for col in impute_cols:
            lines.append(f'df${col}[is.na(df${col})] <- median(df${col}, na.rm = TRUE)')
        lines.append("")
    else:
        lines.append("# Aucune valeur manquante détectée — pas d'imputation nécessaire")
        lines.append("")

    if desc_cols:
        cols_str = ", ".join(f'"{c}"' for c in desc_cols)
        lines.append("# ── 4. Statistiques descriptives ─────────────────────")
        lines.append(f"describe(df[, c({cols_str})])")
        lines.append("")

    if norm_cols:
        lines.append("# ── 5. Tests de normalité ─────────────────────────────")
        for col in norm_cols:
            lines.append(f'shapiro.test(df${col})  # H0 : distribution normale')
        lines.append("")
        plot_rows = min(len(norm_cols), 2)
        plot_cols = (len(norm_cols) + 1) // 2
        lines.append(f"par(mfrow = c({plot_rows}, {plot_cols}))")
        for col in norm_cols:
            lines.append(f'qqnorm(df${col}, main = "QQ-Plot {col}"); qqline(df${col}, col = "red")')
        lines.append("par(mfrow = c(1, 1))")
        lines.append("")

    if corr_cols:
        cols_str = ", ".join(f'"{c}"' for c in corr_cols)
        lines.append("# ── 6. Matrice de corrélation ────────────────────────")
        lines.append(f"corr_matrix <- cor(df[, c({cols_str})],")
        lines.append('                   use = "complete.obs", method = "spearman")')
        lines.append("print(round(corr_matrix, 3))")
        lines.append('corrplot(corr_matrix, method = "color", type = "lower",')
        lines.append('         tl.col = "black", addCoef.col = "black")')
        lines.append("")

    if has_regression:
        y_col = regression_result["y_variable"]
        x_cols = regression_result["x_variables"]
        lines.append("# ── 7. Régression OLS ────────────────────────────────")
        lines.append(f"# Variable dépendante : {y_col}")
        lines.append(f"# Variables explicatives : {', '.join(x_cols)}")
        lines.append(f"model <- lm({y_col} ~ {' + '.join(x_cols)}, data = df)")
        lines.append("summary(model)")
        lines.append("")
        lines.append("# Diagnostics de la régression")
        lines.append("par(mfrow = c(2, 2))")
        lines.append("plot(model)")
        lines.append("par(mfrow = c(1, 1))")
        lines.append("")
        lines.append("bptest(model)   # Breusch-Pagan (hétéroscédasticité)")
        lines.append("dwtest(model)   # Durbin-Watson (autocorrélation)")
        lines.append("vif(model)      # Facteurs d'inflation de la variance")
        lines.append("")
    else:
        lines.append("# ── 7. Régression OLS ────────────────────────────────")
        lines.append("# Non générée automatiquement : aucune variable cible pertinente")
        lines.append("# n'a été identifiée pour ce dataset (voir audit QUANTA).")
        lines.append("")

    if numeric_cols:
        first = numeric_cols[0]
        lines.append("# ── 8. Visualisations ggplot2 ─────────────────────────")
        lines.append(f"ggplot(df, aes(x = {first})) +")
        lines.append('  geom_histogram(fill = "#c9a84c", color = "#0a0a0a", bins = 30) +')
        lines.append(f"  geom_vline(aes(xintercept = mean({first})),")
        lines.append('             color = "#00d4ff", linetype = "dashed") +')
        lines.append("  theme_minimal() +")
        lines.append(f'  labs(title = "Distribution — {first}",')
        lines.append(f'       x = "{first}", y = "Fréquence")')
        lines.append("")

    lines.append('cat("\\n✅ Script QUANTA exécuté avec succès.\\n")')
    return "\n".join(lines)

def generate_stata_script(df: pd.DataFrame, filename: str,
                           numeric_cols: list[str],
                           cat_cols: list[str],
                           regression_result: dict | None = None,
                           n_missing: int = 0) -> str:
    """
    Génère un script Stata (.do) commenté et reproductible.
    Sécurisé de la même façon que generate_r_script.
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    cat_cols = [c for c in cat_cols if c in df.columns]
    regression_result = regression_result or {}
    has_regression = regression_result.get("status") == "ok"

    desc_cols = numeric_cols[:8] if numeric_cols else []
    norm_cols = numeric_cols[:5] if numeric_cols else []
    impute_cols = numeric_cols[:4] if numeric_cols else []
    tab_cols = cat_cols[:3]

    lines = []
    lines.append("* ═══════════════════════════════════════════════════════")
    lines.append("* QUANTA — Script Stata généré automatiquement")
    lines.append(f"* Fichier analysé : {filename}")
    lines.append("* ═══════════════════════════════════════════════════════")
    lines.append("")
    lines.append("clear all")
    lines.append("set more off")
    lines.append("capture log close")
    lines.append('log using "QUANTA_analyse.log", replace')
    lines.append("")
    lines.append("* ── 1. Chargement des données ─────────────────────────")
    lines.append(f'import delimited "{filename}", delimiter(",") varnames(1) clear')
    lines.append("describe")
    lines.append("summarize")
    lines.append("")
    lines.append("* ── 2. Nettoyage ──────────────────────────────────────")
    lines.append("duplicates drop")
    lines.append("duplicates report")
    lines.append("")
    lines.append("misstable summarize")
    if n_missing > 0 and impute_cols:
        lines.append("* Imputation des valeurs manquantes (médiane pour numériques)")
        for col in impute_cols:
            lines.append(f"egen {col}_median = median({col})")
            lines.append(f"replace {col} = {col}_median if missing({col})")
            lines.append(f"drop {col}_median")
        lines.append("")
    else:
        lines.append("* Aucune valeur manquante détectée — pas d'imputation nécessaire")
        lines.append("")

    if desc_cols:
        cols_str = " ".join(desc_cols)
        lines.append("* ── 3. Statistiques descriptives ─────────────────────")
        lines.append(f"summarize {cols_str}, detail")
        lines.append(f"tabstat {cols_str}, stats(n mean sd min p25 p50 p75 max skewness kurtosis)")
        lines.append("")

    if tab_cols:
        lines.append("* Variables catégorielles")
        for col in tab_cols:
            lines.append(f"tabulate {col}")
        lines.append("")

    if norm_cols:
        lines.append("* ── 4. Tests de normalité ────────────────────────────")
        for col in norm_cols:
            lines.append(f"swilk {col}  /* Shapiro-Wilk : H0 = distribution normale */")
        for col in norm_cols:
            lines.append(f"sktest {col}  /* Skewness-Kurtosis test */")
        lines.append("")

    if len(numeric_cols) >= 2:
        cols_str = " ".join(numeric_cols[:8])
        lines.append("* ── 5. Corrélations ──────────────────────────────────")
        lines.append(f"pwcorr {cols_str}, sig star(0.05)")
        lines.append(f"spearman {cols_str}")
        lines.append("")

    if has_regression:
        y_col = regression_result["y_variable"]
        x_cols = regression_result["x_variables"]
        lines.append("* ── 6. Régression OLS ────────────────────────────────")
        lines.append(f"* Variable dépendante : {y_col}")
        lines.append(f"* Variables explicatives : {', '.join(x_cols)}")
        lines.append(f"regress {y_col} {' '.join(x_cols)}")
        lines.append("")
        lines.append("* Diagnostics post-estimation")
        lines.append("estat vif              /* Multicolinéarité */")
        lines.append("estat hettest          /* Breusch-Pagan */")
        lines.append("estat ovtest           /* Ramsey RESET */")
        lines.append("predict residuals, residuals")
        lines.append("predict fitted, xb")
        lines.append("")
    else:
        lines.append("* ── 6. Régression OLS ────────────────────────────────")
        lines.append("* Non générée automatiquement : aucune variable cible pertinente")
        lines.append("* n'a été identifiée pour ce dataset (voir audit QUANTA).")
        lines.append("")

    if numeric_cols:
        first = numeric_cols[0]
        lines.append("* ── 7. Visualisations ─────────────────────────────────")
        lines.append(f"histogram {first}, bin(30) ///")
        lines.append(f'  title("Distribution — {first}") ///')
        lines.append(f'  xtitle("{first}") ytitle("Fréquence") ///')
        lines.append("  scheme(s2color)")
        lines.append("")
        if has_regression:
            lines.append("scatter residuals fitted, ///")
            lines.append('  title("Résidus vs Valeurs Ajustées") ///')
            lines.append("  yline(0, lcolor(red)) scheme(s2color)")
            lines.append("")

    lines.append("log close")
    lines.append("* ✅ Script QUANTA exécuté avec succès.")
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════════
# 8. ANALYSE DE PUISSANCE STATISTIQUE (post-test, déterministe)
# ═══════════════════════════════════════════════════════════════════════════════

def interpret_statistical_power(power: float) -> tuple[str, str]:
    """
    Qualification de la puissance observée (1-β).

    Retourne (libellé, couleur hex) :
      < 0.5       → insuffisante (rouge)
      0.5 – < 0.8 → modérée (orange)
      ≥ 0.8       → adéquate (vert)
    """
    p = float(power)
    if p < 0.5:
        return (
            "insuffisante — risque élevé d'erreur de type II",
            "#E74C3C",
        )
    if p < 0.8:
        return "modérée", "#E67E22"
    return "adéquate", "#2ECC71"


def _safe_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num or math.isinf(num):
        return None
    return num


def _power_cohen_f_from_eta2(eta2: float) -> float | None:
    """f de Cohen à partir de η² / ε² : f = sqrt(η² / (1 - η²))."""
    if eta2 <= 0 or eta2 >= 1:
        return None
    return float(math.sqrt(eta2 / (1.0 - eta2)))


def compute_statistical_power(result: dict[str, Any]) -> dict[str, Any]:
    """
    Enrichit un résultat de test d'inférence avec :
      - power              : float arrondi à 3 décimales
      - power_interpretation : libellé (insuffisante / modérée / adéquate)
      - n_required         : N total pour atteindre 1-β = 0.80 avec effet moyen
                             (Cohen d/f/w = 0.3), uniquement si power < 0.8

    Familles couvertes (statsmodels) :
      - t-test / Mann-Whitney → TTestIndPower (effect = |Cohen's d| ou |r|)
      - ANOVA / Kruskal       → FTestAnovaPower (f dérivé de η²/ε²)
      - Chi-deux / Fisher     → GofChisquarePower (w ≈ V de Cramér)

    Ne lève jamais d'exception : en cas d'échec, retourne le dict inchangé.
    """
    if not isinstance(result, dict):
        return result
    if result.get("status") in {"error", "skipped"}:
        return result
    if result.get("power") is not None:
        return result

    test_name = str(result.get("test") or result.get("method") or "").lower()
    out = dict(result)

    try:
        from statsmodels.stats.power import (
            FTestAnovaPower,
            GofChisquarePower,
            TTestIndPower,
        )

        power: float | None = None
        n_required: int | None = None
        analysis_for_n: Any = None
        n_solve_kwargs: dict[str, Any] = {}

        is_two_group = any(
            token in test_name
            for token in (
                "student",
                "welch",
                "t-test",
                "t test",
                "mann-whitney",
                "mann whitney",
            )
        ) or (
            result.get("n_group1") is not None
            and result.get("n_group2") is not None
            and result.get("effect_size") is not None
            and not any(t in test_name for t in ("anova", "kruskal", "chi"))
        )

        is_multi_group = any(
            token in test_name for token in ("anova", "kruskal")
        ) or (
            result.get("n_groups") is not None
            and (
                result.get("eta_squared") is not None
                or result.get("epsilon_squared") is not None
            )
        )

        is_chi2 = any(
            token in test_name for token in ("chi-deux", "chi2", "chi-square", "fisher")
        ) or result.get("cramers_v") is not None

        if is_two_group and not is_multi_group:
            effect = _safe_float(result.get("effect_size"))
            n1 = _safe_float(result.get("n_group1"))
            n2 = _safe_float(result.get("n_group2"))
            if effect is not None and n1 is not None and n2 is not None and n1 > 0:
                effect_abs = abs(effect)
                ratio = float(n2 / n1) if n1 > 0 else 1.0
                analysis = TTestIndPower()
                raw = analysis.solve_power(
                    effect_size=effect_abs if effect_abs > 0 else 1e-6,
                    nobs1=n1,
                    alpha=0.05,
                    ratio=ratio,
                    alternative="two-sided",
                )
                power = float(np.asarray(raw).ravel()[0])
                analysis_for_n = analysis
                n_solve_kwargs = {
                    "effect_size": 0.3,
                    "power": 0.8,
                    "alpha": 0.05,
                    "ratio": 1.0,
                    "alternative": "two-sided",
                }

        elif is_multi_group:
            eta2 = _safe_float(result.get("eta_squared"))
            if eta2 is None:
                eta2 = _safe_float(result.get("epsilon_squared"))
            effect_f = _power_cohen_f_from_eta2(eta2) if eta2 is not None else None
            k = result.get("n_groups")
            if k is None:
                levels = result.get("group_levels")
                if isinstance(levels, list):
                    k = len(levels)
            sizes = result.get("group_sizes")
            n_total: float | None = None
            if isinstance(sizes, list) and sizes:
                n_total = float(sum(int(s) for s in sizes))
            if n_total is None:
                n_total = _safe_float(result.get("n_observations"))
            k_f = _safe_float(k)
            if (
                effect_f is not None
                and n_total is not None
                and k_f is not None
                and k_f >= 2
                and n_total > k_f
            ):
                analysis = FTestAnovaPower()
                raw = analysis.solve_power(
                    effect_size=effect_f,
                    nobs=n_total,
                    alpha=0.05,
                    k_groups=int(k_f),
                )
                power = float(np.asarray(raw).ravel()[0])
                analysis_for_n = analysis
                # f ≈ 0.25 pour effet moyen ANOVA ; 0.3 demandé par contrat produit.
                n_solve_kwargs = {
                    "effect_size": 0.3,
                    "power": 0.8,
                    "alpha": 0.05,
                    "k_groups": int(k_f),
                }

        elif is_chi2:
            cramers_v = _safe_float(result.get("cramers_v"))
            n_obs = _safe_float(
                result.get("n_observations") or result.get("n") or result.get("N")
            )
            df_val = result.get("df", result.get("dof"))
            if df_val is None and isinstance(result.get("chi2_indicatif"), dict):
                df_val = result["chi2_indicatif"].get("df") or result["chi2_indicatif"].get(
                    "dof"
                )
            df_f = _safe_float(df_val)
            if (
                cramers_v is not None
                and n_obs is not None
                and df_f is not None
                and df_f >= 0
                and n_obs > 0
            ):
                n_bins = int(df_f) + 1
                analysis = GofChisquarePower()
                effect_w = abs(cramers_v) if abs(cramers_v) > 0 else 1e-6
                raw = analysis.solve_power(
                    effect_size=effect_w,
                    nobs=n_obs,
                    alpha=0.05,
                    n_bins=max(n_bins, 2),
                )
                power = float(np.asarray(raw).ravel()[0])
                analysis_for_n = analysis
                n_solve_kwargs = {
                    "effect_size": 0.3,
                    "power": 0.8,
                    "alpha": 0.05,
                    "n_bins": max(n_bins, 2),
                }

        if power is None or power != power:
            return out

        # Borner dans [0, 1] (solve_power peut déborder numériquement).
        power = max(0.0, min(1.0, float(power)))
        out["power"] = round(power, 3)
        label, _color = interpret_statistical_power(power)
        out["power_interpretation"] = label

        if power < 0.8 and analysis_for_n is not None and n_solve_kwargs:
            try:
                raw_n = analysis_for_n.solve_power(**n_solve_kwargs)
                n_raw = float(np.asarray(raw_n).ravel()[0])
                if n_raw == n_raw and n_raw > 0:
                    # TTestIndPower renvoie nobs1 (par groupe) → N total ≈ 2 × nobs1.
                    if isinstance(analysis_for_n, TTestIndPower):
                        n_required = int(math.ceil(n_raw * 2))
                    else:
                        n_required = int(math.ceil(n_raw))
                    out["n_required"] = n_required
            except Exception:
                pass

    except Exception:
        return result

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FONCTION PRINCIPALE — PIPELINE DE BASE (sans arbre de décision)
# ═══════════════════════════════════════════════════════════════════════════════

def run_base_compute_pipeline(file_bytes: bytes, filename: str,
                               target_col: str | None = None,
                               theme: str = "dark") -> dict[str, Any]:
    """
    Point d'entrée du module compute pour la couche "de base" (diagnostic,
    nettoyage, descriptives, normalité, corrélations, et régression OLS
    SI ET SEULEMENT SI target_col est fourni et pertinent).

    Ce pipeline NE CHOISIT AUCUN TEST D'INFÉRENCE (t-test, ANOVA, chi2, etc.)
    -- c'est le rôle de test_selector.py / orchestrator.py, qui appelleront
    les fonctions de ce module individuellement avec les bons arguments
    (numeric_cols, cat_cols issus du diagnostic) après avoir déterminé,
    selon l'objectif utilisateur, quels tests exécuter.

    theme : "dark" (défaut) ou "light" (rapport académique clair).
            Si "both", génère les graphiques pour les deux thèmes.

    Sortie : dict prêt à être enrichi par l'orchestrateur avec les résultats
    des tests d'inférence (clé "inference_tests", ajoutée en aval).
    """
    diag = load_and_diagnose(file_bytes, filename)
    if "error" in diag:
        return {"error": diag["error"]}

    df_raw = diag.pop("dataframe")
    numeric_cols = diag["numeric_cols"]
    cat_cols     = diag["cat_cols"]

    clean = clean_dataframe(df_raw, diag)
    df = clean["dataframe_clean"]

    # Recalcule les listes de colonnes après nettoyage (certaines peuvent
    # avoir été supprimées pour trop de valeurs manquantes)
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    cat_cols     = [c for c in cat_cols if c in df.columns]

    # Génère les graphiques pour le thème demandé (ou les deux)
    if theme == "both":
        desc_dark = descriptive_stats(df, numeric_cols, cat_cols, theme="dark")
        norm_dark = normality_tests(df, numeric_cols, theme="dark")
        corr_dark = correlation_analysis(df, numeric_cols, norm_dark.get("normality", {}), theme="dark")
        
        desc_light = descriptive_stats(df, numeric_cols, cat_cols, theme="light")
        norm_light = normality_tests(df, numeric_cols, theme="light")
        corr_light = correlation_analysis(df, numeric_cols, norm_light.get("normality", {}), theme="light")
        
        desc = {k: v for k, v in desc_dark.items() if k != "charts"}
        norm = norm_dark.get("normality", {})
        corr = {k: v for k, v in corr_dark.items() if k != "charts"}
        reg  = ols_regression(df, numeric_cols, target_col, theme="dark")
        reg_light = ols_regression(df, numeric_cols, target_col, theme="light")

        all_charts = {}
        all_charts.update(desc_dark.get("charts", {}))
        all_charts.update(norm_dark.get("charts", {}))
        all_charts.update(corr_dark.get("charts", {}))
        all_charts.update(reg.get("charts", {}))

        all_charts_light = {}
        all_charts_light.update(desc_light.get("charts", {}))
        all_charts_light.update(norm_light.get("charts", {}))
        all_charts_light.update(corr_light.get("charts", {}))
        all_charts_light.update(reg_light.get("charts", {}))
    else:
        desc = descriptive_stats(df, numeric_cols, cat_cols, theme=theme)
        norm = normality_tests(df, numeric_cols, theme=theme)
        corr = correlation_analysis(df, numeric_cols, norm.get("normality", {}), theme=theme)
        reg  = ols_regression(df, numeric_cols, target_col, theme=theme)

        all_charts = {}
        all_charts.update(desc.get("charts", {}))
        all_charts.update(norm.get("charts", {}))
        all_charts.update(corr.get("charts", {}))
        all_charts.update(reg.get("charts", {}))
        
        all_charts_light = None

    r_script = generate_r_script(df, filename, numeric_cols, reg, diag.get("n_missing", 0))
    stata_script = generate_stata_script(
        df, filename, numeric_cols, cat_cols, reg, diag.get("n_missing", 0)
    )

    logger.info(f"Generated {len(all_charts)} charts for theme 'dark'")
    if all_charts_light:
        logger.info(f"Generated {len(all_charts_light)} charts for theme 'light'")
    
    return {
        "diagnosis":   diag,
        "cleaning":    {k: v for k, v in clean.items() if k != "dataframe_clean"},
        "descriptive": {k: v for k, v in desc.items() if k != "charts"},
        "normality":   norm.get("normality", {}),
        "correlation": {k: v for k, v in corr.items() if k != "charts"},
        "regression":  {k: v for k, v in reg.items() if k != "charts"},
        "charts":      all_charts,
        "charts_light": all_charts_light,
        "r_script":     r_script,
        "stata_script": stata_script,
        "n_charts":    len(all_charts),
        # Artefacts post-nettoyage pour l'orchestrateur (colonnes recalculées
        # après suppression éventuelle de variables trop manquantes) :
        "dataframe_clean": df,
        "numeric_cols":    numeric_cols,
        "cat_cols":        cat_cols,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. ANALYSE DES CORRESPONDANCES MULTIPLES (ACM)
# ═══════════════════════════════════════════════════════════════════════════════

def run_acm(df: pd.DataFrame, 
            cat_cols: list[str],
            n_components: int = 5) -> dict:
    """
    Analyse des Correspondances Multiples.
    Uniquement sur les colonnes catégorielles.
    Minimum 3 variables catégorielles requises.
    """
    try:
        import prince
        
        # Préparer les données
        df_cat = df[cat_cols].dropna()
        n_rows = len(df_cat)
        
        if n_rows < 10:
            return {
                "status": "error",
                "error": "Pas assez d'observations pour l'ACM (minimum 10)"
            }
        
        if len(cat_cols) < 3:
            return {
                "status": "error", 
                "error": "L'ACM nécessite au moins 3 variables catégorielles"
            }
        
        # Sampling pour éviter le crash sur grands datasets
        sampling_note = None
        if n_rows > 5000:
            df_cat = df_cat.sample(n=5000, random_state=42)
            n_rows = 5000
            sampling_note = "Échantillon de 5000 lignes utilisé pour l'ACM (dataset > 5000 observations)"
        
        # Convertir en string pour prince
        df_cat = df_cat.astype(str)
        
        # Ajuster n_components
        n_comp = min(n_components, len(cat_cols) - 1)
        
        # Ajuster n_iter
        n_iter = min(10, n_rows - 1)
        
        # Lancer l'ACM
        acm = prince.MCA(
            n_components=n_comp,
            n_iter=n_iter,
            random_state=42,
            engine='sklearn'
        )
        acm = acm.fit(df_cat)
        
        # Valeurs propres et inertie
        eigenvalues = acm.eigenvalues_.tolist()
        total_inertia = sum(eigenvalues)
        inertia_pct = [round(v / total_inertia * 100, 2) for v in eigenvalues]
        cumulative_inertia = []
        cumul = 0
        for v in inertia_pct:
            cumul += v
            cumulative_inertia.append(round(cumul, 2))
        
        # Coordonnées des modalités
        coords = acm.column_coordinates(df_cat)
        modalities_coords = []
        for idx, row in coords.iterrows():
            modalities_coords.append({
                "modalite": str(idx),
                "dim1": round(float(row.iloc[0]), 4),
                "dim2": round(float(row.iloc[1]), 4) 
                        if len(row) > 1 else 0.0
            })
        
        # Contributions des modalités à l'axe 1
        contributions = acm.column_contributions_
        top_contrib_dim1 = []
        if contributions is not None:
            contrib_dim1 = contributions.iloc[:, 0]
            top_10 = contrib_dim1.nlargest(10)
            for mod, val in top_10.items():
                top_contrib_dim1.append({
                    "modalite": str(mod),
                    "contribution": round(float(val), 4)
                })
        
        # Générer le plan factoriel (graphique principal ACM)
        plan_factoriel = _generate_acm_plot(
            modalities_coords,
            inertia_pct,
            cat_cols
        )
        
        # Générer le graphique des valeurs propres
        scree_plot = _generate_scree_plot(
            inertia_pct
        )
        
        result = {
            "status": "ok",
            "n_rows": n_rows,
            "n_variables": len(cat_cols),
            "variables": cat_cols,
            "n_components": n_comp,
            "eigenvalues": eigenvalues,
            "inertia_pct": inertia_pct,
            "cumulative_inertia": cumulative_inertia,
            "modalities_coords": modalities_coords,
            "top_contributions_dim1": top_contrib_dim1,
            "plan_factoriel": plan_factoriel,
            "scree_plot": scree_plot,
            "interpretation_note": (
                f"L'axe 1 explique {inertia_pct[0]}% "
                f"de l'inertie totale. "
                f"Les axes 1 et 2 ensemble expliquent "
                f"{cumulative_inertia[1] if len(cumulative_inertia) > 1 else inertia_pct[0]}%."
            )
        }
        
        if sampling_note:
            result["sampling_note"] = sampling_note
        
        return result
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def _generate_acm_plot(modalities_coords: list,
                        inertia_pct: list,
                        cat_cols: list) -> str | None:
    """Plan factoriel ACM — graphique signature."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')
        import numpy as np
        
        fig, ax = plt.subplots(figsize=(7, 4))
        fig.patch.set_facecolor('#0A0A0F')
        ax.set_facecolor('#13131A')
        
        # Couleurs par variable
        colors = ['#C9A84C', '#00D4FF', '#2ECC71', 
                  '#E74C3C', '#9B59B6', '#F39C12',
                  '#1ABC9C', '#E67E22']
        
        for i, mod in enumerate(modalities_coords):
            label = mod["modalite"]
            x = mod["dim1"]
            y = mod["dim2"]
            
            # Détecter la variable parente
            var_color = '#C9A84C'
            for j, col in enumerate(cat_cols):
                if label.startswith(col):
                    var_color = colors[j % len(colors)]
                    break
            
            ax.scatter(x, y, color=var_color, 
                      s=80, zorder=5, alpha=0.8)
            ax.annotate(
                label, (x, y),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
                color='#E8E8E8',
                alpha=0.9
            )
        
        # Axes centraux
        ax.axhline(y=0, color='#555563', 
                   linewidth=0.5, linestyle='--')
        ax.axvline(x=0, color='#555563', 
                   linewidth=0.5, linestyle='--')
        
        dim1_pct = inertia_pct[0] if inertia_pct else 0
        dim2_pct = inertia_pct[1] if len(inertia_pct) > 1 else 0
        
        ax.set_xlabel(
            f'Dimension 1 ({dim1_pct}%)',
            color='#9A9AA8', fontsize=11
        )
        ax.set_ylabel(
            f'Dimension 2 ({dim2_pct}%)',
            color='#9A9AA8', fontsize=11
        )
        ax.set_title(
            'ACM — Plan Factoriel (Dimensions 1 et 2)',
            color='#E8E8E8', fontsize=13, pad=15
        )
        ax.tick_params(colors='#9A9AA8')
        for spine in ax.spines.values():
            spine.set_edgecolor('#555563')
        ax.grid(True, alpha=0.08, color='#555563')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80,
                    bbox_inches='tight',
                    facecolor='#0A0A0F')
        plt.close()
        buf.seek(0)
        import base64
        return base64.b64encode(buf.read()).decode()
    
    except Exception:
        return None


def _generate_scree_plot(inertia_pct: list) -> str | None:
    """Graphique des valeurs propres (scree plot)."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')
        import numpy as np
        
        fig, ax = plt.subplots(figsize=(7, 4))
        fig.patch.set_facecolor('#0A0A0F')
        ax.set_facecolor('#13131A')
        
        axes = [f'Dim {i+1}' for i in range(len(inertia_pct))]
        bars = ax.bar(axes, inertia_pct, 
                     color='#C9A84C', alpha=0.8,
                     edgecolor='#E8D5A3')
        
        # Courbe cumulative
        cumul = np.cumsum(inertia_pct)
        ax2 = ax.twinx()
        ax2.plot(axes, cumul, 
                color='#00D4FF', linewidth=2,
                marker='o', markersize=6)
        ax2.set_ylabel('Inertie cumulée (%)', 
                      color='#00D4FF')
        ax2.tick_params(colors='#00D4FF')
        ax2.set_ylim(0, 105)
        
        ax.set_title('Inertie expliquée par dimension',
                    color='#E8E8E8', fontsize=12, pad=15)
        ax.set_xlabel('Dimensions', color='#9A9AA8')
        ax.set_ylabel('% d\'inertie', color='#9A9AA8')
        ax.tick_params(colors='#9A9AA8')
        for spine in ax.spines.values():
            spine.set_edgecolor('#555563')
        ax.grid(True, alpha=0.08, axis='y', 
               color='#555563')
        
        fig.patch.set_facecolor('#0A0A0F')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80,
                    bbox_inches='tight',
                    facecolor='#0A0A0F')
        plt.close()
        buf.seek(0)
        import base64
        return base64.b64encode(buf.read()).decode()
    
    except Exception:
        return None