"""
QUANTA — compute.py
Couche de calcul déterministe (scipy / statsmodels / pandas)
Calcule les VRAIS chiffres avant de les envoyer au LLM.
Le LLM n'interprète que — il ne calcule jamais.
"""

import io
import base64
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # mode sans affichage
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from scipy import stats
from scipy.stats import (
    shapiro, normaltest, kstest, chi2_contingency, fisher_exact,
    ttest_1samp, ttest_ind, ttest_rel,
    mannwhitneyu, wilcoxon, kruskal, spearmanr, kendalltau,
    pearsonr, f_oneway, levene, bartlett, chisquare
)
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tsa.stattools import adfuller, kpss
from statsmodels.stats.diagnostic import het_white, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson
from typing import Any

warnings.filterwarnings("ignore")

# ─── Palette QUANTA ──────────────────────────────────────────────────────────
PALETTE = {
    "bg":     "#0a0a0a",
    "gold":   "#c9a84c",
    "gold2":  "#e8d5a3",
    "text":   "#e8e8e8",
    "accent": "#00d4ff",
    "danger": "#ff4444",
    "muted":  "#555555",
}

def _fig_style(fig, ax_list=None):
    """Applique le style dark luxury QUANTA sur toutes les figures."""
    fig.patch.set_facecolor(PALETTE["bg"])
    for ax in (ax_list if ax_list is not None else fig.axes):
        ax.set_facecolor("#111111")
        ax.tick_params(colors=PALETTE["text"], labelsize=9)
        ax.xaxis.label.set_color(PALETTE["text"])
        ax.yaxis.label.set_color(PALETTE["text"])
        ax.title.set_color(PALETTE["gold"])
        for spine in ax.spines.values():
            spine.set_edgecolor(PALETTE["muted"])

def _fig_to_b64(fig) -> str:
    """Convertit une figure matplotlib en base64 PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=PALETTE["bg"])
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CHARGEMENT & DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def load_and_diagnose(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """
    Charge le fichier (CSV / Excel / Stata / SPSS) et
    retourne un diagnostic structurel complet.
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    try:
        if ext == "csv":
            # Détection automatique du séparateur
            sample = file_bytes[:4096].decode("utf-8", errors="ignore")
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep,
                             encoding="utf-8", low_memory=False)
        elif ext in ("xls", "xlsx"):
            df = pd.read_excel(io.BytesIO(file_bytes))
        elif ext == "dta":
            df = pd.read_stata(io.BytesIO(file_bytes))
        elif ext == "sav":
            import pyreadstat
            df, _ = pyreadstat.read_sav(io.BytesIO(file_bytes))
        else:
            raise ValueError(f"Format non supporté : {ext}")
    except Exception as e:
        return {"error": str(e)}

    n_rows, n_cols = df.shape
    numeric_cols  = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols      = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols     = df.select_dtypes(include=["datetime64"]).columns.tolist()

    missing = df.isnull().sum()
    missing_pct = (missing / n_rows * 100).round(2)

    # Outliers via IQR sur colonnes numériques
    outlier_counts = {}
    for col in numeric_cols:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        outliers = ((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum()
        if outliers > 0:
            outlier_counts[col] = int(outliers)

    # Doublons
    n_dupes = int(df.duplicated().sum())

    # Type probable de dataset
    if len(date_cols) > 0 or any("date" in c.lower() or "annee" in c.lower()
                                   or "year" in c.lower() or "mois" in c.lower()
                                   for c in df.columns):
        dataset_type = "Série temporelle probable"
    elif n_rows > 1000 and n_cols > 20:
        dataset_type = "Enquête / recensement probable (RGPH, EMICOV, EDS)"
    elif n_rows < 200:
        dataset_type = "Petit échantillon — attention à la puissance statistique"
    else:
        dataset_type = "Dataset transversal standard"

    return {
        "dataframe":     df,
        "n_rows":        n_rows,
        "n_cols":        n_cols,
        "numeric_cols":  numeric_cols,
        "cat_cols":      cat_cols,
        "date_cols":     date_cols,
        "missing":       missing[missing > 0].to_dict(),
        "missing_pct":   missing_pct[missing_pct > 0].to_dict(),
        "outlier_counts": outlier_counts,
        "n_duplicates":  n_dupes,
        "dataset_type":  dataset_type,
        "columns":       df.columns.tolist(),
        "dtypes":        df.dtypes.astype(str).to_dict(),
        "memory_mb":     round(df.memory_usage(deep=True).sum() / 1e6, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NETTOYAGE CHIRURGICAL
# ═══════════════════════════════════════════════════════════════════════════════

def clean_dataframe(df: pd.DataFrame, diag: dict) -> dict[str, Any]:
    """
    Nettoie le DataFrame selon des règles académiques documentées.
    Retourne le DF propre + log de chaque décision.
    """
    df = df.copy()
    log = []

    # 1. Suppression des doublons
    n_before = len(df)
    df.drop_duplicates(inplace=True)
    n_removed = n_before - len(df)
    if n_removed:
        log.append(f"Doublons supprimés : {n_removed} lignes retirées.")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols     = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # 2. Valeurs manquantes — stratégie adaptative
    for col in numeric_cols:
        pct = df[col].isnull().mean() * 100
        if pct == 0:
            continue
        elif pct < 5:
            median_val = df[col].median()
            df[col].fillna(median_val, inplace=True)
            log.append(f"[{col}] {pct:.1f}% manquants → imputation par médiane ({median_val:.3f}).")
        elif pct < 20:
            mean_val = df[col].mean()
            df[col].fillna(mean_val, inplace=True)
            log.append(f"[{col}] {pct:.1f}% manquants → imputation par moyenne ({mean_val:.3f}).")
        else:
            df.drop(columns=[col], inplace=True)
            log.append(f"[{col}] {pct:.1f}% manquants → variable supprimée (seuil 20% dépassé).")

    for col in cat_cols:
        pct = df[col].isnull().mean() * 100
        if pct == 0:
            continue
        elif pct < 20:
            mode_val = df[col].mode()[0] if not df[col].mode().empty else "Inconnu"
            df[col].fillna(mode_val, inplace=True)
            log.append(f"[{col}] {pct:.1f}% manquants → imputation par mode ('{mode_val}').")
        else:
            df.drop(columns=[col], inplace=True)
            log.append(f"[{col}] {pct:.1f}% manquants → variable supprimée.")

    # 3. Traitement des outliers (Winsorisation 1%-99%)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    winsorized = []
    for col in numeric_cols:
        q01 = df[col].quantile(0.01)
        q99 = df[col].quantile(0.99)
        n_out = ((df[col] < q01) | (df[col] > q99)).sum()
        if n_out > 0:
            df[col] = df[col].clip(lower=q01, upper=q99)
            winsorized.append(col)
    if winsorized:
        log.append(f"Winsorisation 1%-99% appliquée sur : {', '.join(winsorized)}.")

    # 4. Encodage des colonnes catégorielles en strings propres
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()

    log.append(f"Dataset final : {len(df)} lignes × {len(df.columns)} colonnes après nettoyage.")

    return {
        "dataframe_clean": df,
        "cleaning_log":    log,
        "n_final":         len(df),
        "n_cols_final":    len(df.columns),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. STATISTIQUES DESCRIPTIVES
# ═══════════════════════════════════════════════════════════════════════════════

def descriptive_stats(df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcule les statistiques descriptives complètes.
    Retourne un dict avec les chiffres exacts + graphique distributions.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols     = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # Stats numériques
    desc_num = {}
    for col in numeric_cols:
        s = df[col].dropna()
        q1, q2, q3 = s.quantile([0.25, 0.5, 0.75])
        desc_num[col] = {
            "n":         int(s.count()),
            "mean":      round(float(s.mean()), 4),
            "std":       round(float(s.std()), 4),
            "min":       round(float(s.min()), 4),
            "Q1":        round(float(q1), 4),
            "median":    round(float(q2), 4),
            "Q3":        round(float(q3), 4),
            "max":       round(float(s.max()), 4),
            "skewness":  round(float(s.skew()), 4),
            "kurtosis":  round(float(s.kurt()), 4),
            "cv_pct":    round(float(s.std() / s.mean() * 100), 2) if s.mean() != 0 else None,
            "IQR":       round(float(q3 - q1), 4),
        }

    # Stats catégorielles
    desc_cat = {}
    for col in cat_cols:
        vc = df[col].value_counts()
        desc_cat[col] = {
            "n_unique":    int(df[col].nunique()),
            "mode":        str(vc.index[0]) if len(vc) else "N/A",
            "mode_freq":   int(vc.iloc[0]) if len(vc) else 0,
            "mode_pct":    round(vc.iloc[0] / len(df) * 100, 2) if len(vc) else 0,
            "top5":        vc.head(5).to_dict(),
        }

    # Graphique : histogrammes des variables numériques (max 6)
    charts = {}
    cols_to_plot = numeric_cols[:6]
    if cols_to_plot:
        n = len(cols_to_plot)
        ncols = min(n, 3)
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows))
        axes = np.array(axes).flatten() if n > 1 else [axes]

        for i, col in enumerate(cols_to_plot):
            ax = axes[i]
            s = df[col].dropna()
            ax.hist(s, bins=30, color=PALETTE["gold"], alpha=0.8, edgecolor=PALETTE["bg"])
            ax.axvline(s.mean(),   color=PALETTE["accent"], linewidth=1.5, linestyle="--",
                       label=f"Moy={s.mean():.2f}")
            ax.axvline(s.median(), color=PALETTE["gold2"], linewidth=1.2, linestyle=":",
                       label=f"Méd={s.median():.2f}")
            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel(col, fontsize=8)
            ax.set_ylabel("Fréquence", fontsize=8)
            ax.legend(fontsize=7, facecolor="#1a1a1a", labelcolor=PALETTE["text"])

        for j in range(i + 1, len(axes)):
            axes[j].set_visible(False)

        fig.suptitle("QUANTA — Distributions des variables numériques",
                     color=PALETTE["gold"], fontsize=12, fontweight="bold", y=1.01)
        _fig_style(fig, axes[:n])
        plt.tight_layout()
        charts["distributions"] = _fig_to_b64(fig)

    # Graphique : barres pour les variables catégorielles (max 3)
    cat_to_plot = cat_cols[:3]
    if cat_to_plot:
        n = len(cat_to_plot)
        fig, axes = plt.subplots(1, n, figsize=(6 * n, 4))
        axes = [axes] if n == 1 else axes.flatten()

        for i, col in enumerate(cat_to_plot):
            ax = axes[i]
            vc = df[col].value_counts().head(10)
            bars = ax.barh(vc.index.astype(str), vc.values,
                           color=PALETTE["gold"], edgecolor=PALETTE["bg"])
            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel("Effectif", fontsize=8)
            for bar, v in zip(bars, vc.values):
                ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                        f"{v}", va="center", fontsize=7, color=PALETTE["text"])

        fig.suptitle("QUANTA — Répartition des variables catégorielles",
                     color=PALETTE["gold"], fontsize=12, fontweight="bold")
        _fig_style(fig, axes)
        plt.tight_layout()
        charts["categories"] = _fig_to_b64(fig)

    return {
        "descriptive_numeric":     desc_num,
        "descriptive_categorical": desc_cat,
        "charts":                  charts,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TESTS DE NORMALITÉ (H0/H1 formels)
# ═══════════════════════════════════════════════════════════════════════════════

def normality_tests(df: pd.DataFrame) -> dict[str, Any]:
    """
    Shapiro-Wilk (n<50), D'Agostino-Pearson (n≥50), Kolmogorov-Smirnov.
    Retourne les chiffres exacts + décision formelle H0/H1 + QQ-plots.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    results = {}
    charts  = {}

    cols_to_plot = numeric_cols[:4]
    if cols_to_plot:
        n = len(cols_to_plot)
        ncols = min(n, 2)
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows))
        axes = np.array(axes).flatten() if n > 1 else [axes]

    for i, col in enumerate(numeric_cols):
        s = df[col].dropna()
        n_obs = len(s)
        col_result = {"n": n_obs}

        # Shapiro-Wilk (n < 5000 pour éviter lenteur)
        if n_obs >= 3:
            try:
                stat_sw, p_sw = shapiro(s if n_obs <= 5000 else s.sample(5000, random_state=42))
                col_result["shapiro_wilk"] = {
                    "statistic": round(float(stat_sw), 5),
                    "p_value":   round(float(p_sw), 5),
                    "H0":        "Distribution normale",
                    "decision":  "Ne rejette pas H0 (normale)" if p_sw > 0.05
                                 else "Rejette H0 (non-normale)",
                    "alpha":     0.05,
                }
            except Exception:
                pass

        # D'Agostino-Pearson (recommandé n≥20)
        if n_obs >= 20:
            try:
                stat_da, p_da = normaltest(s)
                col_result["dagostino_pearson"] = {
                    "statistic": round(float(stat_da), 5),
                    "p_value":   round(float(p_da), 5),
                    "decision":  "Ne rejette pas H0 (normale)" if p_da > 0.05
                                 else "Rejette H0 (non-normale)",
                }
            except Exception:
                pass

        # Décision consolidée
        p_values = [v["p_value"] for v in col_result.values()
                    if isinstance(v, dict) and "p_value" in v]
        if p_values:
            col_result["conclusion"] = (
                "NORMALE" if all(p > 0.05 for p in p_values)
                else "NON-NORMALE"
            )
            col_result["recommended_tests"] = (
                "Tests paramétriques (t-test, ANOVA, Pearson)"
                if col_result["conclusion"] == "NORMALE"
                else "Tests non-paramétriques (Mann-Whitney, Kruskal-Wallis, Spearman)"
            )

        results[col] = col_result

        # QQ-plot pour les premières colonnes
        if i < len(cols_to_plot):
            ax = axes[i]
            sm.qqplot(s, line="s", ax=ax, alpha=0.6,
                      markerfacecolor=PALETTE["gold"], markersize=3,
                      markeredgecolor=PALETTE["gold"])
            ax.get_lines()[0].set_color(PALETTE["gold"])
            ax.get_lines()[1].set_color(PALETTE["accent"])
            ax.set_title(f"QQ-Plot — {col}\n({col_result.get('conclusion', '')})",
                         fontsize=9)

    if cols_to_plot:
        for j in range(len(cols_to_plot), len(axes)):
            axes[j].set_visible(False)
        fig.suptitle("QUANTA — Tests de normalité (QQ-Plots)",
                     color=PALETTE["gold"], fontsize=12, fontweight="bold")
        _fig_style(fig, axes[:len(cols_to_plot)])
        plt.tight_layout()
        charts["qqplots"] = _fig_to_b64(fig)

    return {"normality": results, "charts": charts}


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CORRÉLATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def correlation_analysis(df: pd.DataFrame, normality_results: dict) -> dict[str, Any]:
    """
    Pearson si normal, Spearman si non-normal.
    Retourne la matrice + heatmap.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return {"error": "Moins de 2 variables numériques pour la corrélation."}

    # Décide Pearson vs Spearman selon les résultats de normalité
    all_normal = all(
        normality_results.get(col, {}).get("conclusion") == "NORMALE"
        for col in numeric_cols
    )
    method = "pearson" if all_normal else "spearman"

    corr_matrix = df[numeric_cols].corr(method=method).round(4)
    p_matrix    = pd.DataFrame(np.ones((len(numeric_cols), len(numeric_cols))),
                               index=numeric_cols, columns=numeric_cols)

    # P-values pairwise
    pairs = {}
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
                    pairs[f"{c1} × {c2}"] = {
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
                    p_matrix.loc[c1, c2] = p
                    p_matrix.loc[c2, c1] = p

    # Heatmap
    charts = {}
    n = len(numeric_cols)
    size = max(6, n * 0.9)
    fig, ax = plt.subplots(figsize=(size, size * 0.8))

    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    cmap = sns.diverging_palette(220, 40, as_cmap=True)
    sns.heatmap(
        corr_matrix, mask=mask, ax=ax, cmap=cmap,
        vmin=-1, vmax=1, center=0, square=True,
        annot=True, fmt=".2f", annot_kws={"size": 8, "color": PALETTE["text"]},
        linewidths=0.5, linecolor=PALETTE["muted"],
        cbar_kws={"shrink": 0.8}
    )
    ax.set_title(f"Matrice de corrélation ({method.capitalize()})",
                 fontsize=11, fontweight="bold")
    _fig_style(fig, [ax])
    plt.tight_layout()
    charts["correlation_heatmap"] = _fig_to_b64(fig)

    return {
        "method":        method,
        "all_normal":    all_normal,
        "matrix":        corr_matrix.to_dict(),
        "pairs":         pairs,
        "charts":        charts,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RÉGRESSION OLS
# ═══════════════════════════════════════════════════════════════════════════════

def ols_regression(df: pd.DataFrame, target_col: str | None = None) -> dict[str, Any]:
    """
    Régression OLS automatique.
    Si target_col est None, utilise la première colonne numérique comme Y.
    Retourne : coefficients, R², RMSE, diagnostics (VIF, DW, White, BP).
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return {"error": "Pas assez de variables numériques pour la régression."}

    # Choisir Y
    if target_col and target_col in numeric_cols:
        y_col = target_col
    else:
        y_col = numeric_cols[0]

    x_cols = [c for c in numeric_cols if c != y_col][:8]  # max 8 régresseurs

    sub = df[[y_col] + x_cols].dropna()
    if len(sub) < len(x_cols) + 5:
        return {"error": "Pas assez d'observations pour la régression."}

    Y = sub[y_col]
    X = sm.add_constant(sub[x_cols])

    try:
        model  = sm.OLS(Y, X).fit()
    except Exception as e:
        return {"error": str(e)}

    # VIF
    vif_data = {}
    try:
        for idx, col in enumerate(X.columns):
            if col == "const":
                continue
            vif_data[col] = round(variance_inflation_factor(X.values, idx), 3)
    except Exception:
        pass

    # Diagnostics post-estimation
    residuals = model.resid
    dw_stat   = round(float(durbin_watson(residuals)), 4)

    het_bp = {}
    try:
        lm, lm_p, fval, f_p = het_breuschpagan(residuals, X)
        het_bp = {"LM_stat": round(float(lm), 4), "p_value": round(float(lm_p), 5),
                  "decision": "Hétéroscédasticité détectée (p<0.05)" if lm_p < 0.05
                              else "Homoscédasticité (OK)"}
    except Exception:
        pass

    het_w = {}
    try:
        lm_w, lm_p_w, _, _ = het_white(residuals, X)
        het_w = {"LM_stat": round(float(lm_w), 4), "p_value": round(float(lm_p_w), 5),
                 "decision": "Hétéroscédasticité (White)" if lm_p_w < 0.05
                             else "Homoscédasticité (White OK)"}
    except Exception:
        pass

    # Graphique résidus
    charts = {}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Résidus vs Fitted
    axes[0].scatter(model.fittedvalues, residuals,
                    color=PALETTE["gold"], alpha=0.6, s=20)
    axes[0].axhline(0, color=PALETTE["accent"], linewidth=1.5, linestyle="--")
    axes[0].set_xlabel("Valeurs ajustées", fontsize=9)
    axes[0].set_ylabel("Résidus", fontsize=9)
    axes[0].set_title("Résidus vs Valeurs ajustées", fontsize=10)

    # Histogramme résidus
    axes[1].hist(residuals, bins=25, color=PALETTE["gold"], alpha=0.8,
                 edgecolor=PALETTE["bg"])
    axes[1].set_title("Distribution des résidus", fontsize=10)
    axes[1].set_xlabel("Résidus", fontsize=9)
    axes[1].set_ylabel("Fréquence", fontsize=9)

    fig.suptitle(f"QUANTA — Diagnostic Régression OLS (Y = {y_col})",
                 color=PALETTE["gold"], fontsize=12, fontweight="bold")
    _fig_style(fig, axes)
    plt.tight_layout()
    charts["regression_diagnostics"] = _fig_to_b64(fig)

    # Coefficients formatés
    coef_summary = {}
    for var in model.params.index:
        coef_summary[var] = {
            "coefficient": round(float(model.params[var]), 6),
            "std_err":     round(float(model.bse[var]), 6),
            "t_stat":      round(float(model.tvalues[var]), 4),
            "p_value":     round(float(model.pvalues[var]), 5),
            "ci_lower":    round(float(model.conf_int().loc[var, 0]), 6),
            "ci_upper":    round(float(model.conf_int().loc[var, 1]), 6),
            "significant": model.pvalues[var] < 0.05,
        }

    return {
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
# 7. GÉNÉRATEUR DE SCRIPTS R ET STATA
# ═══════════════════════════════════════════════════════════════════════════════

def generate_r_script(df: pd.DataFrame, filename: str,
                      regression_result: dict,
                      normality_result: dict) -> str:
    """Génère un script R commenté et reproductible."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols     = df.select_dtypes(include=["object", "category"]).columns.tolist()
    y_col = regression_result.get("y_variable", numeric_cols[0] if numeric_cols else "Y")
    x_cols = regression_result.get("x_variables", numeric_cols[1:4])

    r_script = f"""# ═══════════════════════════════════════════════════════
# QUANTA — Script R généré automatiquement
# Fichier analysé : {filename}
# ═══════════════════════════════════════════════════════

# ── 0. Packages requis ─────────────────────────────────
packages <- c("tidyverse", "psych", "car", "lmtest",
              "nortest", "ggplot2", "corrplot", "stargazer")
lapply(packages, function(p) {{
  if (!require(p, character.only = TRUE)) install.packages(p)
  library(p, character.only = TRUE)
}})

# ── 1. Chargement des données ──────────────────────────
df <- read.csv("{filename}", sep = ",", header = TRUE,
               stringsAsFactors = FALSE, encoding = "UTF-8")
cat("Dimensions :", nrow(df), "lignes x", ncol(df), "colonnes\\n")

# ── 2. Aperçu structurel ──────────────────────────────
str(df)
summary(df)

# ── 3. Nettoyage ──────────────────────────────────────
# Suppression des doublons
df <- df[!duplicated(df), ]

# Imputation des valeurs manquantes (médiane pour numériques)
{chr(10).join([f'df${col}[is.na(df${col})] <- median(df${col}, na.rm = TRUE)' for col in numeric_cols[:5]])}

# ── 4. Statistiques descriptives ─────────────────────
describe(df[, c({", ".join([f'"{c}"' for c in numeric_cols[:6]])})])

# ── 5. Tests de normalité ─────────────────────────────
{chr(10).join([f'shapiro.test(df${col})  # H0 : distribution normale' for col in numeric_cols[:4]])}

# QQ-Plots
par(mfrow = c({min(len(numeric_cols[:4]), 2)}, {(len(numeric_cols[:4]) + 1) // 2}))
{chr(10).join([f'qqnorm(df${col}, main = "QQ-Plot {col}"); qqline(df${col}, col = "red")' for col in numeric_cols[:4]])}
par(mfrow = c(1, 1))

# ── 6. Matrice de corrélation ────────────────────────
corr_matrix <- cor(df[, c({", ".join([f'"{c}"' for c in numeric_cols[:6]])})],
                   use = "complete.obs", method = "spearman")
print(round(corr_matrix, 3))
corrplot(corr_matrix, method = "color", type = "lower",
         tl.col = "black", addCoef.col = "black")

# ── 7. Régression OLS ────────────────────────────────
# Variable dépendante : {y_col}
# Variables explicatives : {", ".join(x_cols[:6])}
model <- lm({y_col} ~ {" + ".join(x_cols[:6])}, data = df)
summary(model)

# Diagnostics de la régression
par(mfrow = c(2, 2))
plot(model)
par(mfrow = c(1, 1))

# Test de Breusch-Pagan (hétéroscédasticité)
bptest(model)

# Test de Durbin-Watson (autocorrélation)
dwtest(model)

# Facteurs d'inflation de la variance (multicolinéarité)
vif(model)

# ── 8. Visualisations ggplot2 ─────────────────────────
# Histogrammes
ggplot(df, aes(x = {numeric_cols[0] if numeric_cols else "x"})) +
  geom_histogram(fill = "#c9a84c", color = "#0a0a0a", bins = 30) +
  geom_vline(aes(xintercept = mean({numeric_cols[0] if numeric_cols else "x"})),
             color = "#00d4ff", linetype = "dashed") +
  theme_minimal() +
  labs(title = "Distribution — {numeric_cols[0] if numeric_cols else 'Variable'}",
       x = "{numeric_cols[0] if numeric_cols else 'x'}", y = "Fréquence")

cat("\\n✅ Script QUANTA exécuté avec succès.\\n")
"""
    return r_script


def generate_stata_script(df: pd.DataFrame, filename: str,
                          regression_result: dict) -> str:
    """Génère un script Stata (.do) commenté et reproductible."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    y_col  = regression_result.get("y_variable", numeric_cols[0] if numeric_cols else "Y")
    x_cols = regression_result.get("x_variables", numeric_cols[1:4])

    stata_script = f"""* ═══════════════════════════════════════════════════════
* QUANTA — Script Stata généré automatiquement
* Fichier analysé : {filename}
* ═══════════════════════════════════════════════════════

clear all
set more off
capture log close
log using "QUANTA_analyse.log", replace

* ── 1. Chargement des données ─────────────────────────
import delimited "{filename}", delimiter(",") varnames(1) clear
describe
summarize

* ── 2. Nettoyage ──────────────────────────────────────
* Suppression des doublons
duplicates drop
duplicates report

* Valeurs manquantes
misstable summarize
{chr(10).join([f'* egen {col}_median = median({col})' for col in numeric_cols[:4]])}

* ── 3. Statistiques descriptives ─────────────────────
summarize {" ".join(numeric_cols[:8])}, detail
tabstat {" ".join(numeric_cols[:8])}, stats(n mean sd min p25 p50 p75 max skewness kurtosis)

* Variables catégorielles
{chr(10).join([f'tabulate {col}' for col in df.select_dtypes(include=["object"]).columns[:3]])}

* ── 4. Tests de normalité ────────────────────────────
{chr(10).join([f'swilk {col}  /* Shapiro-Wilk : H0 = distribution normale */' for col in numeric_cols[:5]])}
{chr(10).join([f'sktest {col}  /* Skewness-Kurtosis test */' for col in numeric_cols[:5]])}

* ── 5. Corrélations ──────────────────────────────────
pwcorr {" ".join(numeric_cols[:8])}, sig star(0.05)
spearman {" ".join(numeric_cols[:8])}

* ── 6. Régression OLS ────────────────────────────────
* Variable dépendante : {y_col}
* Variables explicatives : {", ".join(x_cols[:6])}
regress {y_col} {" ".join(x_cols[:6])}

* Diagnostics post-estimation
estat vif              /* Multicolinéarité */
estat hettest          /* Breusch-Pagan */
estat ovtest           /* Ramsey RESET */
predict residuals, residuals
predict fitted, xb

* Durbin-Watson (si series temporelles)
* tsset time_var
* dwstat

* ── 7. Visualisations ─────────────────────────────────
histogram {numeric_cols[0] if numeric_cols else "var1"}, bin(30) ///
  title("Distribution — {numeric_cols[0] if numeric_cols else 'Variable'}") ///
  xtitle("{numeric_cols[0] if numeric_cols else 'var1'}") ytitle("Fréquence") ///
  scheme(s2color)

scatter residuals fitted, ///
  title("Résidus vs Valeurs Ajustées") ///
  yline(0, lcolor(red)) scheme(s2color)

log close
* ✅ Script QUANTA exécuté avec succès.
"""
    return stata_script


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FONCTION PRINCIPALE — PIPELINE COMPLET
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_compute_pipeline(file_bytes: bytes, filename: str,
                              target_col: str | None = None) -> dict[str, Any]:
    """
    Point d'entrée unique du module compute.
    Retourne toutes les statistiques réelles + graphiques + scripts.
    """
    print("[COMPUTE] ── Chargement & Diagnostic ──")
    diag = load_and_diagnose(file_bytes, filename)
    if "error" in diag:
        return {"error": diag["error"]}

    df_raw = diag.pop("dataframe")

    print("[COMPUTE] ── Nettoyage chirurgical ──")
    clean = clean_dataframe(df_raw, diag)
    df    = clean["dataframe_clean"]

    print("[COMPUTE] ── Statistiques descriptives ──")
    desc = descriptive_stats(df)

    print("[COMPUTE] ── Tests de normalité ──")
    norm = normality_tests(df)

    print("[COMPUTE] ── Corrélations ──")
    corr = correlation_analysis(df, norm.get("normality", {}))

    print("[COMPUTE] ── Régression OLS ──")
    reg  = ols_regression(df, target_col)

    print("[COMPUTE] ── Génération scripts R & Stata ──")
    r_script     = generate_r_script(df, filename, reg, norm.get("normality", {}))
    stata_script = generate_stata_script(df, filename, reg)

    # Assemblage de tous les graphiques
    all_charts = {}
    all_charts.update(desc.get("charts", {}))
    all_charts.update(norm.get("charts", {}))
    all_charts.update(corr.get("charts", {}))
    all_charts.update(reg.get("charts",  {}))

    print(f"[COMPUTE] ✅ Pipeline terminé — {len(all_charts)} graphiques générés")

    return {
        "diagnosis":    diag,
        "cleaning":     {k: v for k, v in clean.items() if k != "dataframe_clean"},
        "descriptive":  {k: v for k, v in desc.items() if k != "charts"},
        "normality":    norm.get("normality", {}),
        "correlation":  {k: v for k, v in corr.items() if k != "charts"},
        "regression":   {k: v for k, v in reg.items()  if k != "charts"},
        "charts":       all_charts,       # dict {nom: base64_png}
        "r_script":     r_script,
        "stata_script": stata_script,
        "n_charts":     len(all_charts),
    }
