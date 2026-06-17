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
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # mode sans affichage
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import shapiro, normaltest, pearsonr, spearmanr
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.diagnostic import het_white, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson
from typing import Any

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

# Seuil de cardinalité au-dessous duquel une colonne numérique est considérée
# comme potentiellement catégorielle (codes région, Likert, binaire, etc.)
CATEGORICAL_CARDINALITY_THRESHOLD = 10
# Taille minimale de l'échantillon pour activer le garde-fou catégoriel
# (sous ce seuil, presque rien n'a de sens statistiquement de toute façon)
CATEGORICAL_GUARD_MIN_N = 10
# Taille minimale de l'échantillon pour appliquer la winsorisation des outliers
# (sous ce seuil, le 1er/99e centile ~= min/max -> ce ne sont pas des "outliers"
# mais les extrêmes naturels d'un petit échantillon)
WINSORIZATION_MIN_N = 30
# Noms de colonnes (en minuscules, comparaison par mot entier ou via
# séparateur _/-) considérés comme des identifiants potentiels
ID_COLUMN_NAME_HINTS = ("id", "identifiant", "code", "uuid", "guid", "matricule")

def _fig_style(fig, ax_list=None):
    """Applique le style dark luxury QUANTA sur toutes les figures."""
    fig.patch.set_facecolor(PALETTE["bg"])
    for ax in (ax_list if ax_list is not None else fig.axes):
        ax.set_facecolor(PALETTE["panel"])
        ax.tick_params(colors=PALETTE["text"], labelsize=9)
        ax.xaxis.label.set_color(PALETTE["text"])
        ax.yaxis.label.set_color(PALETTE["text"])
        ax.title.set_color(PALETTE["gold"])
        for spine in ax.spines.values():
            spine.set_edgecolor(PALETTE["muted"])

def _fig_to_b64(fig, dpi: int = 100) -> str:
    """Convertit une figure matplotlib en base64 PNG (dpi réduit pour le poids)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                 facecolor=PALETTE["bg"])
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def _is_likely_id_column(series: pd.Series, col_name: str) -> bool:
    """
    Détecte si une colonne numérique est probablement un identifiant
    (et non une variable à analyser).

    Hints FORTS (id, identifiant, uuid, guid, matricule) : le nom seul
    suffit — pas de condition d'unicité (un dataset avec doublons a une
    colonne id dont les valeurs répétées ne sont que les lignes dupliquées).

    Hints AMBIGUS (code) : exige >= 95 % de valeurs uniques pour distinguer
    code_client (identifiant) de code_region (catégoriel).
    """
    name = col_name.lower().strip()
    name_parts = set(name.replace("-", "_").split("_")) | {name}
    name_matches = any(hint in name_parts for hint in ID_COLUMN_NAME_HINTS)

    if not name_matches:
        return False

    s = series.dropna()
    if s.empty:
        return False

    STRONG_HINTS = {"id", "identifiant", "uuid", "guid", "matricule"}
    AMBIGUOUS_HINTS = {"code"}

    name_parts = set(name.replace("-", "_").split("_")) | {name}

    if name_parts & STRONG_HINTS:
        return True

    if name_parts & AMBIGUOUS_HINTS:
        uniqueness_ratio = s.nunique() / len(s)
        return uniqueness_ratio >= 0.95

    return False

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CHARGEMENT & DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def load_and_diagnose(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """
    Charge le fichier (CSV / Excel / Stata / SPSS) et retourne un diagnostic
    structurel complet, incluant la classification fine des colonnes
    (numérique continu, numérique discret probablement catégoriel, qualitatif,
    date).
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    try:
        if ext == "csv":
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

    raw_numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    raw_cat_cols     = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols        = df.select_dtypes(include=["datetime64"]).columns.tolist()

    # ── Détection des colonnes identifiantes (Fix #1) ────────────────────────
    # Exclues de tout calcul (pas numériques, pas catégorielles) : un ID
    # séquentiel n'a aucun sens statistique (moyenne, winsorisation,
    # corrélation, test de normalité sur un identifiant sont tous absurdes).
    id_cols = []
    for col in raw_numeric_cols:
        if _is_likely_id_column(df[col], col):
            id_cols.append(col)

    candidate_numeric_cols = [c for c in raw_numeric_cols if c not in id_cols]

    # ── Garde-fou numérique-mais-catégoriel (Fix #3) ─────────────────────────
    # Une colonne numérique avec très peu de valeurs uniques (ex: code région
    # 1-12, échelle de Likert 1-5, binaire 0/1) est probablement catégorielle,
    # pas continue. On la reclasse, mais on garde la trace de la décision.
    #
    # Le garde-fou s'active dès n >= CATEGORICAL_GUARD_MIN_N (10), mais on
    # exige en plus n >= 2 * n_unique : ça évite qu'une variable réellement
    # continue avec un petit échantillon (ex: n=12, 11 valeurs uniques) soit
    # reclassée à tort simplement parce que n_unique < 10.
    numeric_cols = []
    cat_cols = list(raw_cat_cols)
    reclassified_as_categorical = {}

    for col in candidate_numeric_cols:
        n_unique = df[col].nunique(dropna=True)
        guard_active = (
            n_rows >= CATEGORICAL_GUARD_MIN_N
            and n_unique < CATEGORICAL_CARDINALITY_THRESHOLD
            and n_rows >= 2 * n_unique
        )
        if guard_active:
            cat_cols.append(col)
            reclassified_as_categorical[col] = {
                "n_unique": int(n_unique),
                "raison": (
                    f"Colonne numérique avec seulement {n_unique} valeurs uniques "
                    f"(< seuil {CATEGORICAL_CARDINALITY_THRESHOLD}) sur {n_rows} lignes "
                    f"-> probablement un code catégoriel (région, échelle de Likert, "
                    f"binaire) plutôt qu'une variable continue."
                ),
            }
        else:
            numeric_cols.append(col)

    missing = df.isnull().sum()
    missing_pct = (missing / n_rows * 100).round(2)

    # Outliers via IQR sur colonnes réellement numériques (continues)
    outlier_counts = {}
    for col in numeric_cols:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        outliers = ((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum()
        if outliers > 0:
            outlier_counts[col] = int(outliers)

    n_dupes = int(df.duplicated().sum())

    # Type probable de dataset (Fix #2 : matching par mot entier, pas sous-chaîne
    # -- "years_exp" ne doit pas matcher "year")
    DATE_KEYWORDS = {"date", "annee", "année", "year", "mois", "month"}

    def _col_has_date_keyword(col_name: str) -> bool:
        parts = set(col_name.lower().replace("-", "_").split("_")) | {col_name.lower()}
        return bool(parts & DATE_KEYWORDS)

    if len(date_cols) > 0 or any(_col_has_date_keyword(c) for c in df.columns):
        dataset_type = "Série temporelle probable"
    elif n_rows > 1000 and n_cols > 20:
        dataset_type = "Enquête / recensement probable (RGPH, EMICOV, EDS)"
    elif n_rows < 200:
        dataset_type = "Petit échantillon — attention à la puissance statistique"
    else:
        dataset_type = "Dataset transversal standard"

    return {
        "dataframe":      df,
        "n_rows":         n_rows,
        "n_cols":         n_cols,
        "numeric_cols":   numeric_cols,
        "cat_cols":       cat_cols,
        "id_cols":        id_cols,
        "date_cols":      date_cols,
        "reclassified_as_categorical": reclassified_as_categorical,
        "missing":        missing[missing > 0].to_dict(),
        "missing_pct":    missing_pct[missing_pct > 0].to_dict(),
        "outlier_counts": outlier_counts,
        "n_duplicates":   n_dupes,
        "dataset_type":   dataset_type,
        "columns":        df.columns.tolist(),
        "dtypes":         df.dtypes.astype(str).to_dict(),
        "memory_mb":      round(df.memory_usage(deep=True).sum() / 1e6, 2),
    }

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

    # 1. Suppression des doublons
    n_before = len(df)
    df = df.drop_duplicates()
    n_removed = n_before - len(df)
    if n_removed:
        audit_log.append({
            "etape": "doublons",
            "colonne": None,
            "decision": "suppression",
            "valeur": n_removed,
            "justification": f"{n_removed} ligne(s) dupliquée(s) exactement supprimée(s).",
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

def descriptive_stats(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str]) -> dict[str, Any]:
    """
    Calcule les statistiques descriptives complètes pour les colonnes
    explicitement classifiées comme numériques continues / catégorielles
    (passées par l'appelant, issues du diagnostic -- évite de re-deviner
    les types ici).
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    cat_cols     = [c for c in cat_cols if c in df.columns]

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
        fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows))
        axes = np.array(axes).flatten() if n > 1 else np.array([axes])

        for i, col in enumerate(cols_to_plot):
            ax = axes[i]
            s = df[col].dropna()
            ax.hist(s, bins=30, color=PALETTE["gold"], alpha=0.85, edgecolor=PALETTE["bg"])
            ax.axvline(s.mean(), color=PALETTE["accent"], linewidth=1.5, linestyle="--",
                       label=f"Moy={s.mean():.2f}")
            ax.axvline(s.median(), color=PALETTE["gold2"], linewidth=1.2, linestyle=":",
                       label=f"Méd={s.median():.2f}")
            ax.set_title(col, fontsize=10, fontweight="bold")
            ax.set_xlabel(col, fontsize=8)
            ax.set_ylabel("Fréquence", fontsize=8)
            ax.legend(fontsize=7, facecolor=PALETTE["panel"], labelcolor=PALETTE["text"])

        for j in range(len(cols_to_plot), len(axes)):
            axes[j].set_visible(False)

        fig.suptitle("QUANTA — Distributions des variables numériques",
                      color=PALETTE["gold"], fontsize=12, fontweight="bold", y=1.02)
        _fig_style(fig, axes[:n])
        plt.tight_layout()
        charts["distributions"] = _fig_to_b64(fig)

    # Barres pour les variables catégorielles (max 3)
    cat_to_plot = cat_cols[:3]
    if cat_to_plot:
        n = len(cat_to_plot)
        fig, axes = plt.subplots(1, n, figsize=(5.5 * n, 3.6))
        axes = np.array([axes]) if n == 1 else axes.flatten()

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

def normality_tests(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
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
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    results = {}
    charts  = {}

    cols_to_plot = numeric_cols[:4]
    fig = axes = None
    if cols_to_plot:
        n = len(cols_to_plot)
        ncols = min(n, 2)
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4.5 * nrows))
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
                      markerfacecolor=PALETTE["gold"], markersize=3,
                      markeredgecolor=PALETTE["gold"])
            ax.get_lines()[0].set_color(PALETTE["gold"])
            ax.get_lines()[1].set_color(PALETTE["accent"])
            conclusion = results.get(col, {}).get("conclusion", "")
            ax.set_title(f"QQ-Plot — {col}\n({conclusion})", fontsize=9)

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

def correlation_analysis(df: pd.DataFrame, numeric_cols: list[str], normality_results: dict) -> dict[str, Any]:
    """
    Pearson si toutes les variables sont normales, Spearman sinon.
    Retourne la matrice de corrélation, la matrice de p-values associée
    (désormais utilisée), les paires significatives classées, et la heatmap.
    """
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    if len(numeric_cols) < 2:
        return {"error": "Moins de 2 variables numériques pour la corrélation."}

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

                    pairs[f"{c1} x {c2}"] = {
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

    # Heatmap
    charts = {}
    n = len(numeric_cols)
    size = max(5, n * 0.85)
    fig, ax = plt.subplots(figsize=(size, size * 0.8))

    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    cmap = sns.diverging_palette(220, 40, as_cmap=True)
    sns.heatmap(
        corr_matrix, mask=mask, ax=ax, cmap=cmap,
        vmin=-1, vmax=1, center=0, square=True,
        annot=True, fmt=".2f", annot_kws={"size": 8, "color": PALETTE["text"]},
        linewidths=0.5, linecolor=PALETTE["muted"],
        cbar_kws={"shrink": 0.8},
    )
    ax.set_title(f"Matrice de corrélation ({method.capitalize()})",
                  fontsize=11, fontweight="bold")
    _fig_style(fig, [ax])
    plt.tight_layout()
    charts["correlation_heatmap"] = _fig_to_b64(fig)

    return {
        "method":     method,
        "all_normal": all_normal,
        "matrix":     corr_matrix.to_dict(),
        "p_matrix":   p_matrix.round(5).to_dict(),
        "pairs":      pairs,
        "charts":     charts,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 6. RÉGRESSION OLS (désormais CONDITIONNELLE)
# ═══════════════════════════════════════════════════════════════════════════════

def ols_regression(df: pd.DataFrame, numeric_cols: list[str], target_col: str | None = None) -> dict[str, Any]:
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
    charts = {}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))

    axes[0].scatter(model.fittedvalues, residuals, color=PALETTE["gold"], alpha=0.6, s=20)
    axes[0].axhline(0, color=PALETTE["accent"], linewidth=1.5, linestyle="--")
    axes[0].set_xlabel("Valeurs ajustées", fontsize=9)
    axes[0].set_ylabel("Résidus", fontsize=9)
    axes[0].set_title("Résidus vs Valeurs ajustées", fontsize=10)

    axes[1].hist(residuals, bins=25, color=PALETTE["gold"], alpha=0.85, edgecolor=PALETTE["bg"])
    axes[1].set_title("Distribution des résidus", fontsize=10)
    axes[1].set_xlabel("Résidus", fontsize=9)
    axes[1].set_ylabel("Fréquence", fontsize=9)

    fig.suptitle(f"QUANTA — Diagnostic Régression OLS (Y = {y_col})",
                  color=PALETTE["gold"], fontsize=12, fontweight="bold")
    _fig_style(fig, axes)
    plt.tight_layout()
    charts["regression_diagnostics"] = _fig_to_b64(fig)

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
                       regression_result: dict | None = None) -> str:
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
    if impute_cols:
        lines.append("# Imputation des valeurs manquantes (médiane pour numériques)")
        for col in impute_cols:
            lines.append(f'df${col}[is.na(df${col})] <- median(df${col}, na.rm = TRUE)')
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
                           regression_result: dict | None = None) -> str:
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
    if impute_cols:
        for col in impute_cols:
            lines.append(f"* egen {col}_median = median({col})")
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
# 8. FONCTION PRINCIPALE — PIPELINE DE BASE (sans arbre de décision)
# ═══════════════════════════════════════════════════════════════════════════════

def run_base_compute_pipeline(file_bytes: bytes, filename: str,
                               target_col: str | None = None) -> dict[str, Any]:
    """
    Point d'entrée du module compute pour la couche "de base" (diagnostic,
    nettoyage, descriptives, normalité, corrélations, et régression OLS
    SI ET SEULEMENT SI target_col est fourni et pertinent).

    Ce pipeline NE CHOISIT AUCUN TEST D'INFÉRENCE (t-test, ANOVA, chi2, etc.)
    -- c'est le rôle de test_selector.py / orchestrator.py, qui appelleront
    les fonctions de ce module individuellement avec les bons arguments
    (numeric_cols, cat_cols issus du diagnostic) après avoir déterminé,
    selon l'objectif utilisateur, quels tests exécuter.

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

    desc = descriptive_stats(df, numeric_cols, cat_cols)
    norm = normality_tests(df, numeric_cols)
    corr = correlation_analysis(df, numeric_cols, norm.get("normality", {}))
    reg  = ols_regression(df, numeric_cols, target_col)

    r_script = generate_r_script(df, filename, numeric_cols, reg)
    stata_script = generate_stata_script(df, filename, numeric_cols, cat_cols, reg)

    all_charts = {}
    all_charts.update(desc.get("charts", {}))
    all_charts.update(norm.get("charts", {}))
    all_charts.update(corr.get("charts", {}))
    all_charts.update(reg.get("charts", {}))

    return {
        "diagnosis":   diag,
        "cleaning":    {k: v for k, v in clean.items() if k != "dataframe_clean"},
        "descriptive": {k: v for k, v in desc.items() if k != "charts"},
        "normality":   norm.get("normality", {}),
        "correlation": {k: v for k, v in corr.items() if k != "charts"},
        "regression":  {k: v for k, v in reg.items() if k != "charts"},
        "charts":      all_charts,
        "r_script":     r_script,
        "stata_script": stata_script,
        "n_charts":    len(all_charts),
        # Artefacts post-nettoyage pour l'orchestrateur (colonnes recalculées
        # après suppression éventuelle de variables trop manquantes) :
        "dataframe_clean": df,
        "numeric_cols":    numeric_cols,
        "cat_cols":        cat_cols,
    }