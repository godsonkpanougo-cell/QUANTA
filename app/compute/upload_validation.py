"""
Module léger de validation d'upload pour l'endpoint /upload.
Contient uniquement les fonctions de chargement et diagnostic qui ne dépendent
que de pandas et du Python standard — pas de matplotlib/scipy/statsmodels/seaborn.

Ce module est importé par main.py pour la validation des fichiers uploadés,
et par compute.py pour les mêmes fonctions utilisées en interne.
"""

import io
import pandas as pd
from typing import Any


# Seuil de cardinalité au-dessous duquel une colonne numérique est considérée
# comme potentiellement catégorielle (codes région, Likert, binaire, etc.)
CATEGORICAL_CARDINALITY_THRESHOLD = 10
# Taille minimale de l'échantillon pour activer le garde-fou catégoriel
# (sous ce seuil, presque rien n'a de sens statistiquement de toute façon)
CATEGORICAL_GUARD_MIN_N = 10
# Noms de colonnes (en minuscules, comparaison par mot entier ou via
# séparateur _/-) considérés comme des identifiants potentiels
ID_COLUMN_NAME_HINTS = ("id", "identifiant", "code", "uuid", "guid", "matricule")


def _detect_csv_encoding(file_bytes: bytes) -> str:
    """
    Détecte l'encodage d'un fichier CSV par essai en cascade. Les fichiers
    produits par Excel/Windows en contexte francophone sont très souvent en
    Latin-1 ou Windows-1252 (cp1252) plutôt qu'en UTF-8 -- un caractère
    accentué (é, è, ê...) dans ces encodages casse le décodage UTF-8 strict
    avec une erreur "invalid continuation byte", ce qui faisait planter
    /upload sur des bases réelles de chercheurs francophones.

    Ordre d'essai : UTF-8 (standard moderne) -> UTF-8 avec BOM (Excel
    Windows) -> Windows-1252 (encodage Excel français le plus courant) ->
    Latin-1 (ISO-8859-1, accepte techniquement tout octet donc toujours en
    dernier recours -- jamais d'erreur, mais peut mal interpréter certains
    caractères si l'encodage réel était différent).
    """
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            file_bytes.decode(encoding)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "latin-1"  # ne lève jamais d'erreur -- filet de sécurité ultime


def _detect_csv_separator(sample_text: str) -> str:
    """
    Détecte le séparateur CSV (virgule, point-virgule, tabulation, pipe)
    en choisissant celui qui produit le nombre de colonnes le plus
    cohérent (et le plus élevé) à travers les premières lignes.

    Un simple comptage brut d'occurrences est trompeur : sur un fichier
    avec peu de lignes, les virgules décimales (ex: "8,5") et les virgules
    à l'intérieur de champs texte (ex: "Paris, France") peuvent dépasser
    en nombre les vrais séparateurs de colonnes. La cohérence du nombre
    de champs obtenus par ligne (toutes les lignes doivent se découper en
    le même nombre de colonnes) est un signal bien plus fiable que le
    comptage brut.
    """
    sample_lines = [l for l in sample_text.splitlines()[:5] if l.strip()]
    if not sample_lines:
        return ","

    candidates = [";", "\t", ",", "|"]
    best_sep = ","
    best_score = (0, 0)  # (n_colonnes_coherent, n_colonnes)

    for sep in candidates:
        field_counts = [line.count(sep) + 1 for line in sample_lines]
        n_cols = field_counts[0]
        if n_cols <= 1:
            continue  # ce séparateur ne découpe rien -- candidat invalide
        is_consistent = all(c == n_cols for c in field_counts)
        score = (1 if is_consistent else 0, n_cols)
        if score > best_score:
            best_score = score
            best_sep = sep

    return best_sep


def _try_convert_french_decimal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convertit les colonnes texte contenant des nombres à virgule décimale
    française (ex: "20090,00", "1,20") en vrais floats. Très courant dans
    les fichiers Excel français/européens exportés en CSV -- sans cette
    conversion, ces colonnes restent en object/string et sont totalement
    invisibles au pipeline statistique (aucun calcul, aucun test, aucune
    corrélation possible dessus).

    Heuristique de détection volontairement stricte : une colonne n'est
    convertie que si, après remplacement virgule->point, au moins 90% des
    valeurs non-nulles deviennent des floats valides. Ça évite de casser
    une vraie colonne catégorielle qui contiendrait occasionnellement une
    virgule (ex: "Paris, France").
    """
    df = df.copy()
    for col in df.select_dtypes(include=["object"]).columns:
        series = df[col].dropna().astype(str)
        if len(series) == 0:
            continue

        # Ne tente la conversion que si les valeurs ressemblent à des
        # nombres avec virgule décimale OU à des entiers purs (ex: "25"
        # sans décimale, qui doivent aussi être reconnus comme numériques
        # -- un dataset mixte entiers/décimaux virgule comme "25" et
        # "173,4" dans la même colonne est courant).
        looks_numeric = series.str.match(r"^\s*-?\d+(,\d+)?\s*$").mean()
        if looks_numeric < 0.9:
            continue

        converted = pd.to_numeric(
            series.str.replace(",", ".", regex=False).str.strip(),
            errors="coerce",
        )
        success_rate = converted.notna().mean()
        if success_rate >= 0.9:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ".", regex=False).str.strip(),
                errors="coerce",
            )
    return df


def _is_likely_id_column(series: pd.Series, col_name: str) -> bool:
    """
    Détecte si une colonne numérique est probablement un identifiant
    (et non une variable à analyser).

    Une colonne est considérée comme identifiant si :
      - son nom (en minuscules) correspond exactement à un des indices
        ID_COLUMN_NAME_HINTS, ou se termine par "_<hint>" / "-<hint>"
        (ex: "client_id", "code-postal" -> "postal" ne matche pas "code",
        mais "id_client" -> "id" matche en préfixe), ET
      - ses valeurs (hors NA) sont toutes uniques (100% -> chaque ligne a
        une valeur distincte, comme un identifiant séquentiel).

    Le nom seul ne suffit pas (une colonne "code_region" avec valeurs
    répétées 1-5 n'est PAS un identifiant -> traitée par le garde-fou
    catégoriel standard). L'unicité seule ne suffit pas non plus (une
    mesure continue peut avoir 100% de valeurs uniques sans être un ID).
    Les deux conditions combinées ciblent spécifiquement le cas "id".
    """
    name = col_name.lower().strip()
    name_parts = set(name.replace("-", "_").split("_")) | {name}
    name_matches = any(
        part == hint or part.startswith(hint) or part.endswith(hint)
        for part in name_parts
        for hint in ID_COLUMN_NAME_HINTS
    )

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


def _is_likely_id_column_categorical(series: pd.Series, col_name: str) -> bool:
    """
    Détecte si une colonne catégorielle est probablement un identifiant,
    uniquement par correspondance de nom (STRONG_HINTS seulement, pas de
    vérification d'unicité car un identifiant catégoriel peut légitimement
    avoir des doublons).
    """
    name = col_name.lower().strip()
    name_parts = set(name.replace("-", "_").split("_")) | {name}
    STRONG_HINTS = {"id", "identifiant", "identifier", "uuid", "guid", "matricule"}
    return any(
        part == hint or part.startswith(hint) or part.endswith(hint)
        for part in name_parts
        for hint in STRONG_HINTS
    )


def _build_diagnosis_descriptive_stats(
    df: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
    n_rows: int,
) -> dict[str, Any]:
    """
    Statistiques descriptives pour le diagnostic (JSON-safe).

    Numériques : moyenne, médiane, écart-type, min, max, skewness, kurtosis,
    % manquants.
    Catégorielles : fréquences, pourcentages, mode, % manquants.
    """
    numeric_out: dict[str, Any] = {}
    for col in numeric_cols:
        if col not in df.columns:
            continue
        series = df[col]
        missing_pct = round(float(series.isna().mean() * 100), 2) if n_rows else 0.0
        valid = series.dropna()
        if valid.empty:
            numeric_out[col] = {
                "mean": None,
                "median": None,
                "std": None,
                "min": None,
                "max": None,
                "skewness": None,
                "kurtosis": None,
                "missing_pct": missing_pct,
            }
            continue
        numeric_out[col] = {
            "mean": round(float(valid.mean()), 4),
            "median": round(float(valid.median()), 4),
            "std": round(float(valid.std()), 4),
            "min": round(float(valid.min()), 4),
            "max": round(float(valid.max()), 4),
            "skewness": round(float(valid.skew()), 4),
            "kurtosis": round(float(valid.kurt()), 4),
            "missing_pct": missing_pct,
        }

    categorical_out: dict[str, Any] = {}
    for col in cat_cols:
        if col not in df.columns:
            continue
        series = df[col]
        missing_pct = round(float(series.isna().mean() * 100), 2) if n_rows else 0.0
        vc = series.value_counts(dropna=True)
        denom = int(series.notna().sum())
        frequencies = {str(k): int(v) for k, v in vc.to_dict().items()}
        percentages = {
            str(k): round(float(v) / denom * 100, 2) if denom else 0.0
            for k, v in vc.to_dict().items()
        }
        mode_val = str(vc.index[0]) if len(vc) else None
        categorical_out[col] = {
            "frequencies": frequencies,
            "percentages": percentages,
            "mode": mode_val,
            "missing_pct": missing_pct,
        }

    return {
        "numeric": numeric_out,
        "categorical": categorical_out,
    }


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
            encoding = _detect_csv_encoding(file_bytes)
            sample = file_bytes[:4096].decode(encoding, errors="replace")
            sep = _detect_csv_separator(sample)
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep,
                             encoding=encoding, low_memory=False)
            df = _try_convert_french_decimal(df)
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

    raw_numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
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

    for col in raw_cat_cols:
        if _is_likely_id_column_categorical(df[col], col):
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

    # Doublons exacts : détection uniquement (aucune suppression ici).
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

    descriptive_stats_diag = _build_diagnosis_descriptive_stats(
        df, numeric_cols, cat_cols, n_rows
    )

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
        "n_missing":      int(missing.sum()),
        "outlier_counts": outlier_counts,
        "n_duplicates":   n_dupes,
        "duplicates_removed": False,
        "descriptive_stats": descriptive_stats_diag,
        "dataset_type":   dataset_type,
        "columns":        df.columns.tolist(),
        "dtypes":         df.dtypes.astype(str).to_dict(),
        "memory_mb":      round(df.memory_usage(deep=True).sum() / 1e6, 2),
    }
