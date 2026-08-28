"""
QUANTA — report_generator.py

Génère un rapport PDF professionnel à partir du dict retourné par
brain.analyze_with_brain (intent + analysis + interpretation).

Pipeline :
  analysis_result (dict)
       → HTML/CSS complet (string)
       → weasyprint.HTML(string=...).write_pdf()
       → bytes PDF

Ne fusionne jamais les couches compute / brain : ce module lit uniquement
le résultat déjà assemblé et le met en page. Aucune statistique n'est
recalculée ici.
"""

from __future__ import annotations

import html
import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Limite de graphiques dans le PDF (subprocess PDF Worker peut utiliser toute la RAM)
MAX_CHARTS_IN_PDF = 10


def _select_charts(all_charts: dict, max_charts: int = MAX_CHARTS_IN_PDF) -> dict:
    """
    Priorise les graphiques les plus importants pour le PDF.
    Ordre de priorité strict (max 3 images) :
    1. distributions (histogrammes des numériques)
    2. plan_factoriel (ACM si présent)
    3. boxplot (premier seulement)
    
    Exclus du PDF (disponibles dans l'interface web) :
    - qqplots, categories, scatter_plot, correlation_heatmap, scree_plot, individuals_plot
    """
    priority = [
        "distributions",
        "plan_factoriel",
        "boxplot",
    ]
    selected = {}
    for key in priority:
        if len(selected) >= max_charts:
            break
        if key in all_charts and all_charts[key]:
            selected[key] = all_charts[key]
    return selected


def _get_weasyprint():
    try:
        from weasyprint import HTML
        print("WeasyPrint import réussi")
        return HTML
    except Exception as e:
        print(f"WeasyPrint non disponible: {e}")
        import traceback
        traceback.print_exc()
        return None


def _weasyprint_safe(html: str) -> bytes | None:
    """WeasyPrint avec gestion d'erreur."""
    try:
        HTML = _get_weasyprint()
        if HTML is None:
            return None
        return HTML(string=html).write_pdf()
    except Exception as e:
        print(f"WeasyPrint error: {e}")
        return None


def _split_html_by_sections(full_html: str) -> list[str]:
    """Divise le HTML complet en sections basées sur les balises <section>."""
    import re
    # Trouver toutes les sections avec leur contenu (peu importe la classe)
    pattern = r'<section[^>]*>(.*?)</section>'
    sections = re.findall(pattern, full_html, re.DOTALL)
    return sections


def _wrap_section_in_html(section_html: str, theme: str = "dark") -> str:
    """Enveloppe une section dans un HTML complet avec CSS."""
    css = _css()
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>{css}</style>
</head>
<body>
    {section_html}
</body>
</html>"""


def generate_pdf_chunked(analysis_result: dict[str, Any], theme: str = "dark") -> bytes | None:
    """
    Génère le PDF en chunks séparés pour éviter le dépassement mémoire.
    Divise le HTML en sections et génère chaque chunk séparément.
    """
    def _mem_checkpoint(label: str) -> None:
        try:
            import resource
            mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            print(f"MEM CHECKPOINT [{label}] : {mb:.1f} Mo", flush=True)
        except Exception:
            pass  # resource non disponible sur certaines plateformes

    try:
        import gc
        from pypdf import PdfWriter
        import io

        print("CHUNKED PDF - Début génération", flush=True)
        
        # Générer le HTML complet
        import resource
        mb_avant_acm = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(f"CHUNKED PDF - AVANT construction HTML (incluant ACM) : {mb_avant_acm:.1f} Mo", flush=True)
        
        full_html = _build_html(analysis_result, theme)
        
        mb_apres_acm = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(f"CHUNKED PDF - APRÈS construction HTML (incluant ACM) : {mb_apres_acm:.1f} Mo (delta: {mb_apres_acm - mb_avant_acm:.1f} Mo)", flush=True)
        print(f"CHUNKED PDF - HTML généré, longueur: {len(full_html)}", flush=True)

        # Diviser en sections
        sections = _split_html_by_sections(full_html)
        print(f"CHUNKED PDF - Sections trouvées: {len(sections)}", flush=True)

        if not sections:
            print("CHUNKED PDF - ERREUR: Aucune section trouvée!", flush=True)
            return None
        
        writer = PdfWriter()
        
        # Checkpoint avant boucle de rendu
        print(f"CHUNKED PDF - AVANT boucle de rendu, {len(sections)} sections construites : {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.1f} Mo", flush=True)
        
        # Générer chaque section comme un chunk séparé
        for i, section_html in enumerate(sections):
            print(f"CHUNKED PDF - Traitement section {i+1}/{len(sections)}, longueur: {len(section_html)}", flush=True)

            # Limiter les graphiques dans les sections volumineuses
            if len(section_html) > 500_000:
                nb_images = section_html.count("data:image")
                print(f"CHUNKED PDF - Section {i+1} contient {nb_images} images base64", flush=True)
                taille_avant = len(section_html)
                section_html = _limit_charts_in_html(section_html, max_charts=3)
                print(f"CHUNKED PDF - Graphiques limités dans section {i+1} (taille avant: {taille_avant}, après: {len(section_html)})", flush=True)

            # Envelopper dans un HTML complet
            wrapped_html = _wrap_section_in_html(section_html, theme)
            print(f"CHUNKED PDF - HTML enveloppé pour section {i+1}, longueur: {len(wrapped_html)}", flush=True)

            # Générer PDF pour ce chunk
            import resource
            section_id = section_html[:80].replace("\n", " ") if len(section_html) > 80 else section_html.replace("\n", " ")
            mb_avant = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            print(f"CHUNKED PDF - Section {i+1} ({len(section_html)} car.) - ID: {section_id} - AVANT rendu : {mb_avant:.1f} Mo", flush=True)
            
            pdf_chunk = _weasyprint_safe(wrapped_html)
            
            if pdf_chunk:
                mb_apres = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                print(f"CHUNKED PDF - Section {i+1} - APRÈS rendu : {mb_apres:.1f} Mo (delta: {mb_apres - mb_avant:.1f} Mo)", flush=True)
            if pdf_chunk:
                print(f"CHUNKED PDF - PDF chunk {i+1} généré, taille: {len(pdf_chunk)}", flush=True)
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf_chunk))
                print(f"CHUNKED PDF - Chunk {i+1} a {len(reader.pages)} pages", flush=True)
                for page in reader.pages:
                    writer.add_page(page)
            else:
                print(f"CHUNKED PDF - ERREUR: Chunk {i+1} échoué", flush=True)
            
            # Libérer la mémoire
            del pdf_chunk, wrapped_html, section_html
            gc.collect()
        
        # Fusionner en un seul PDF
        output = io.BytesIO()
        writer.write(output)
        result = output.getvalue()
        print(f"CHUNKED PDF - PDF final généré, taille: {len(result)}", flush=True)
        return result

    except Exception as e:
        print(f"CHUNKED PDF - Erreur: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


def _limit_charts_in_html(html: str, max_charts: int = 2) -> str:
    """Limite le nombre d'images dans le HTML."""
    import re
    # Trouver toutes les balises img
    img_pattern = r'<img[^>]*>'
    images = re.findall(img_pattern, html)
    
    if len(images) <= max_charts:
        return html
    
    # Garder seulement les max_charts premières images
    kept_images = images[:max_charts]
    
    # Remplacer toutes les images par les gardées
    result = html
    for i, img in enumerate(images):
        if i >= max_charts:
            result = result.replace(img, '', 1)
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS D'EXTRACTION (défensifs — jamais d'exception sur clé absente)
# ═══════════════════════════════════════════════════════════════════════════════

def _esc(value: Any) -> str:
    """Échappe une valeur pour insertion dans du HTML."""
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _fmt_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _esc(value)
    if abs(num) >= 1000 or (abs(num) > 0 and abs(num) < 1e-3):
        return f"{num:.6g}"
    return f"{num:.{digits}f}".rstrip("0").rstrip(".")


def format_pvalue(p: float) -> str:
    """
    Format APA des p-values pour le rapport :
      - p < 0.001  → "< 0.001"
      - p >= 0.001 → "0.XXX" (zéro de tête obligatoire, jamais ".XXX")
    """
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3f}"


def _fmt_pvalue(value: Any) -> str:
    if value is None:
        return "—"
    try:
        p = float(value)
    except (TypeError, ValueError):
        return _esc(value)
    if p != p:  # NaN
        return "—"
    return format_pvalue(p)


def interpret_effect_size(name: str, value: float) -> str:
    """
    Qualification de taille d'effet selon les conventions de Cohen (1988).

    Seuils :
      Cohen's d          : 0.2 / 0.5 / 0.8
      r (rang bisériel)  : 0.1 / 0.3 / 0.5
      η² / ε²            : 0.01 / 0.06 / 0.14
      V de Cramér        : 0.1 / 0.3 / 0.5
    """
    label = (name or "").strip().lower()
    abs_v = abs(float(value))

    # η² / ε² — seuils sur la valeur absolue (mesures déjà ≥ 0 en pratique)
    if (
        "η" in name
        or "ε" in name
        or "eta" in label
        or "epsilon" in label
        or label in {"η²", "ε²", "eta_squared", "epsilon_squared"}
    ):
        if abs_v < 0.01:
            return "négligeable"
        if abs_v < 0.06:
            return "petit"
        if abs_v < 0.14:
            return "moyen"
        return "grand"

    # V de Cramér
    if "cram" in label or label in {"v", "v de cramér", "v de cramer"}:
        if abs_v < 0.1:
            return "négligeable"
        if abs_v < 0.3:
            return "petit"
        if abs_v < 0.5:
            return "moyen"
        return "grand"

    # Cohen's d
    if "cohen" in label or label in {"d", "cohen's d", "cohens_d"}:
        if abs_v < 0.2:
            return "négligeable"
        if abs_v < 0.5:
            return "petit"
        if abs_v < 0.8:
            return "moyen"
        return "grand"

    # r bisériel / corrélation r (mêmes seuils Cohen pour |r|)
    if (
        "bis" in label
        or "rang" in label
        or label.startswith("r ")
        or label in {"r", "rho", "ρ"}
    ):
        if abs_v < 0.1:
            return "négligeable"
        if abs_v < 0.3:
            return "petit"
        if abs_v < 0.5:
            return "moyen"
        return "grand"

    return "négligeable"


def _effect_interpretation_html(name: str, value: Any) -> str | None:
    """Ligne HTML d'interprétation Cohen, ou None si valeur non numérique."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN
        return None
    qual = interpret_effect_size(name, num)
    return (
        f'<em style="color:#9A9AA8;">effet {_esc(qual)} selon Cohen (1988)</em>'
    )


def _next_table_caption(table_counter: list[int], title: str) -> str:
    """Incrémente le compteur et retourne la légende APA au-dessus du tableau."""
    table_counter[0] += 1
    return (
        f'<p style="color:#E8E8E8; font-size:12px; font-weight:600; '
        f'margin:16px 0 4px 0;">'
        f"Tableau {table_counter[0]}. {_esc(title)}"
        f"</p>"
    )


def _engine_versions_line() -> str:
    """Ligne de versioning moteur pour la page de garde."""
    from importlib.metadata import version as _pkg_version
    import sys

    try:
        scipy_version = _pkg_version("scipy")
    except Exception:
        scipy_version = "?"

    try:
        statsmodels_version = _pkg_version("statsmodels")
    except Exception:
        statsmodels_version = "?"

    python_ver = sys.version.split()[0]
    return (
        f"QUANTA v0.1.0 · Python {python_ver} · "
        f"scipy {scipy_version} · statsmodels {statsmodels_version}"
    )


_METHODOLOGY_REFERENCES: dict[str, str] = {
    "kruskal": (
        "Kruskal, W. H., & Wallis, W. A. (1952). Use of ranks in one-criterion "
        "variance analysis. Journal of the American Statistical Association, "
        "47(260), 583–621."
    ),
    "mann_whitney": (
        "Mann, H. B., & Whitney, D. R. (1947). On a test of whether one of two "
        "random variables is stochastically larger than the other. Annals of "
        "Mathematical Statistics, 18(1), 50–60."
    ),
    "t_test": (
        "Student. (1908). The probable error of a mean. Biometrika, 6(1), 1–25."
    ),
    "anova": (
        "Fisher, R. A. (1925). Statistical methods for research workers. "
        "Oliver & Boyd."
    ),
    "chi2": (
        "Pearson, K. (1900). On the criterion that a given system of deviations "
        "from the probable in the case of a correlated system of variables is "
        "such that it can be reasonably supposed to have arisen from random "
        "sampling. Philosophical Magazine, 50(302), 157–175."
    ),
    "spearman": (
        "Spearman, C. (1904). The proof and measurement of association between "
        "two things. American Journal of Psychology, 15(1), 72–101."
    ),
    "cohen": (
        "Cohen, J. (1988). Statistical power analysis for the behavioral "
        "sciences (2nd ed.). Lawrence Erlbaum Associates."
    ),
    "shapiro": (
        "Shapiro, S. S., & Wilk, M. B. (1965). An analysis of variance test "
        "for normality. Biometrika, 52(3–4), 591–611."
    ),
    "levene": (
        "Levene, H. (1960). Robust tests for equality of variances. In I. Olkin "
        "(Ed.), Contributions to Probability and Statistics (pp. 278–292). "
        "Stanford University Press."
    ),
}

_REFERENCE_DISPLAY_ORDER: tuple[str, ...] = (
    "shapiro",
    "levene",
    "t_test",
    "mann_whitney",
    "anova",
    "kruskal",
    "chi2",
    "spearman",
    "cohen",
)


def _reference_keys_from_test_name(test_name: str) -> set[str]:
    """Associe un nom de test à une ou plusieurs clés bibliographiques."""
    name = test_name.lower()
    keys: set[str] = set()
    if "kruskal" in name:
        keys.add("kruskal")
    if "mann" in name or "whitney" in name:
        keys.add("mann_whitney")
    if "student" in name or "welch" in name or "t-test" in name or "t test" in name:
        keys.add("t_test")
    if "anova" in name:
        keys.add("anova")
    if "chi" in name or "fisher" in name:
        keys.add("chi2")
    if "spearman" in name:
        keys.add("spearman")
    return keys


def _collect_methodology_reference_keys(
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    multi_entries: list[dict[str, Any]],
) -> list[str]:
    """Déduit les références méthodologiques à afficher selon les tests du rapport."""
    keys: set[str] = set()

    test_payloads: list[dict[str, Any]] = []
    if multi_entries:
        for entry in multi_entries:
            test_payloads.append(_resolve_entry_test_result(entry))
    else:
        test_payloads.append(
            _coerce_inference_result(_as_dict(analysis.get("inference")).get("result"))
        )

    for data in test_payloads:
        if not data:
            continue
        test_name = str(data.get("test") or data.get("method") or "")
        keys |= _reference_keys_from_test_name(test_name)
        if data.get("levene"):
            keys.add("levene")
        if data.get("effect_size") is not None or any(
            data.get(k) is not None for k in ("eta_squared", "epsilon_squared", "cramers_v")
        ):
            keys.add("cohen")

    normality = _collect_normality_sources(analysis)
    if normality:
        keys.add("shapiro")

    corr = _as_dict(analysis.get("correlation_base")) or _as_dict(analysis.get("correlation"))
    if str(corr.get("method", "")).lower() == "spearman":
        keys.add("spearman")

    for entry in multi_entries:
        entry_analysis = _as_dict(entry.get("analysis"))
        corr_entry = _as_dict(entry_analysis.get("correlation_base")) or _as_dict(
            entry_analysis.get("correlation")
        )
        if str(corr_entry.get("method", "")).lower() == "spearman":
            keys.add("spearman")

    return [key for key in _REFERENCE_DISPLAY_ORDER if key in keys]


def _html_methodology_bibliography(reference_keys: list[str]) -> str:
    """Annexe C — références méthodologiques automatiques."""
    if not reference_keys:
        return ""
    items = "\n".join(
        f'<p style="color:#9A9AA8; font-family:Courier New,monospace; '
        f'font-size:10px; margin:0 0 10px 0; padding-left:1.2em; '
        f'text-indent:-1.2em; line-height:1.5;">'
        f"{_esc(_METHODOLOGY_REFERENCES[key])}</p>"
        for key in reference_keys
        if key in _METHODOLOGY_REFERENCES
    )
    return f"""
  <section class="section">
    <h2 style="color:#C9A84C;">Annexe C — Références méthodologiques</h2>
    {items}
  </section>
"""


def _py_str(value: Any) -> str:
    """Litéral Python sûr pour insertion dans le script généré."""
    return repr(str(value))


def _collect_script_test_specs(
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    intent: dict[str, Any],
    multi_entries: list[dict[str, Any]],
    is_multi: bool,
) -> list[dict[str, Any]]:
    """Liste de specs (test, target, group, action) pour le script Python."""
    specs: list[dict[str, Any]] = []
    if is_multi and multi_entries:
        for entry in multi_entries:
            if _is_descriptive_only_entry(entry):
                continue
            data = _resolve_entry_test_result(entry)
            entry_intent = _as_dict(entry.get("intent"))
            specs.append({
                "test": str(data.get("test") or data.get("method") or entry.get("test") or ""),
                "target": entry_intent.get("target_col") or data.get("target") or data.get("col1"),
                "group": entry_intent.get("group_col") or data.get("group") or data.get("col2"),
                "action": entry.get("action_executed") or entry_intent.get("action"),
                "result": data,
            })
        return specs

    data = _coerce_inference_result(_as_dict(analysis.get("inference")).get("result"))
    if data and data.get("status") not in {"error", "skipped"}:
        specs.append({
            "test": str(data.get("test") or data.get("method") or ""),
            "target": intent.get("target_col") or data.get("target") or data.get("col1"),
            "group": intent.get("group_col") or data.get("group") or data.get("col2"),
            "action": _as_dict(analysis.get("inference")).get("action_executed")
            or intent.get("action"),
            "result": data,
        })
    return specs


def _python_code_for_test(spec: dict[str, Any]) -> list[str]:
    """Génère le bloc Python Colab pour un test effectué."""
    test = str(spec.get("test") or "").lower()
    action = str(spec.get("action") or "").lower()
    target = spec.get("target")
    group = spec.get("group")
    data = _as_dict(spec.get("result"))
    lines: list[str] = []

    if not target:
        return ["# Test sans variable cible identifiable — code non généré."]

    t_lit = _py_str(target)
    g_lit = _py_str(group) if group else None

    is_corr = (
        action == "correlation"
        or "pearson" in test
        or "spearman" in test
        or "corrél" in test
        or "correl" in test
    )
    is_assoc = action == "association" or "chi" in test or "fisher" in test
    is_anova = "anova" in test and "welch" not in test
    is_welch = "welch" in test and "anova" in test
    is_kruskal = "kruskal" in test
    is_mann = "mann" in test or "whitney" in test
    is_student = ("student" in test or "t-test" in test) and "welch" not in test and not is_mann
    is_welch_t = "welch" in test and "anova" not in test
    is_logistic = "logist" in test or "regression_logistic" in action

    title = str(spec.get("test") or action or "Test")
    lines.append(f"# --- {title} ---")

    n_groups_raw = data.get("n_groups")
    try:
        n_groups = int(n_groups_raw) if n_groups_raw is not None else None
    except (TypeError, ValueError):
        n_groups = None

    if is_corr and group:
        method = "spearman" if "spearman" in test else "pearson"
        lines.append(f"x = df[{t_lit}].dropna()")
        lines.append(f"y = df[{g_lit}].dropna()")
        lines.append("idx = x.index.intersection(y.index)")
        lines.append("x, y = x.loc[idx], y.loc[idx]")
        if method == "spearman":
            lines.append("r, p = stats.spearmanr(x, y)")
            lines.append('print(f"Spearman : rho={r:.4f}, p={p:.4f}")')
        else:
            lines.append("r, p = stats.pearsonr(x, y)")
            lines.append('print(f"Pearson : r={r:.4f}, p={p:.4f}")')
        return lines

    if is_assoc and group:
        lines.append(f"table = pd.crosstab(df[{t_lit}], df[{g_lit}])")
        lines.append("print(table)")
        if "fisher" in test:
            lines.append("odds, p = stats.fisher_exact(table.values)")
            lines.append('print(f"Fisher exact : OR={odds:.4f}, p={p:.4f}")')
        else:
            lines.append("chi2, p, dof, expected = stats.chi2_contingency(table)")
            lines.append('print(f"Chi-deux : chi2={chi2:.4f}, ddl={dof}, p={p:.4f}")')
            lines.append("print('Effectifs attendus :')")
            lines.append("print(expected)")
        return lines

    if is_logistic:
        preds = _as_list(data.get("predictors"))
        if not preds:
            lines.append("# Régression logistique : prédicteurs non disponibles dans le résultat.")
            return lines
        pred_repr = "[" + ", ".join(_py_str(p) for p in preds) + "]"
        lines.append("import statsmodels.api as sm")
        lines.append(f"target = {t_lit}")
        lines.append(f"predictors = {pred_repr}")
        lines.append("sub = df[[target] + predictors].dropna()")
        lines.append("levels = sub[target].unique()")
        lines.append("y = sub[target].map({levels[0]: 0, levels[1]: 1})")
        lines.append("X = sm.add_constant(sub[predictors])")
        lines.append("model = sm.Logit(y, X).fit(disp=0)")
        lines.append("print(model.summary())")
        return lines

    # 2 groupes AVANT multi (sinon "compare_groups" matche "compare_groups_2").
    is_two = bool(
        group
        and (
            is_mann
            or is_student
            or is_welch_t
            or action == "compare_groups_2"
            or n_groups == 2
        )
    )
    is_multi = bool(
        group
        and (
            is_kruskal
            or is_anova
            or is_welch
            or action in {"compare_groups_multi", "compare_groups_k"}
            or (n_groups is not None and n_groups >= 3)
        )
    )

    if is_two and not is_multi:
        lines.append(f"sub = df[[{t_lit}, {g_lit}]].dropna()")
        lines.append(f"levels = list(sub[{g_lit}].unique())")
        lines.append("assert len(levels) == 2, levels")
        lines.append(f"g1 = sub.loc[sub[{g_lit}] == levels[0], {t_lit}]")
        lines.append(f"g2 = sub.loc[sub[{g_lit}] == levels[1], {t_lit}]")
        if is_mann:
            lines.append("stat, p = stats.mannwhitneyu(g1, g2, alternative='two-sided')")
            lines.append('print(f"Mann-Whitney U : U={stat:.4f}, p={p:.4f}")')
        elif is_welch_t:
            lines.append("stat, p = stats.ttest_ind(g1, g2, equal_var=False)")
            lines.append('print(f"t-Welch : t={stat:.4f}, p={p:.4f}")')
        else:
            lines.append("stat, p = stats.ttest_ind(g1, g2, equal_var=True)")
            lines.append('print(f"t-Student : t={stat:.4f}, p={p:.4f}")')
        lines.append("print('Groupes :', levels[0], 'vs', levels[1])")
        return lines

    if is_multi:
        lines.append(f"sub = df[[{t_lit}, {g_lit}]].dropna()")
        lines.append(f"levels = sorted(sub[{g_lit}].unique(), key=str)")
        lines.append(
            f"groups = [sub.loc[sub[{g_lit}] == lvl, {t_lit}].to_numpy() for lvl in levels]"
        )
        if is_kruskal:
            lines.append("stat, p = stats.kruskal(*groups)")
            lines.append('print(f"Kruskal-Wallis : H={stat:.4f}, p={p:.4f}")')
            lines.append("print('Niveaux :', levels)")
            lines.append("# Post-hoc Dunn (si significatif) :")
            lines.append("# import scikit_posthocs as sp")
            lines.append(
                f"# print(sp.posthoc_dunn(sub, val_col={t_lit}, "
                f"group_col={g_lit}, p_adjust='bonferroni'))"
            )
        elif is_welch:
            lines.append("# Welch ANOVA (pingouin)")
            lines.append("import pingouin as pg")
            lines.append(
                f"print(pg.welch_anova(data=sub, dv={t_lit}, between={g_lit}))"
            )
        else:
            lines.append("stat, p = stats.f_oneway(*groups)")
            lines.append('print(f"ANOVA : F={stat:.4f}, p={p:.4f}")')
            lines.append("print('Niveaux :', levels)")
            lines.append("# Post-hoc Tukey (si significatif) :")
            lines.append("from statsmodels.stats.multicomp import pairwise_tukeyhsd")
            lines.append("if p < 0.05:")
            lines.append(f"    print(pairwise_tukeyhsd(sub[{t_lit}], sub[{g_lit}]))")
        return lines

    lines.append(
        f"# Test « {title} » — génération générique non couverte ; "
        "voir le rapport QUANTA."
    )
    return lines


def generate_python_colab_script(
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    intent: dict[str, Any],
    multi_entries: list[dict[str, Any]],
    is_multi: bool,
    filename: str,
) -> str:
    """
    Script Python exécutable dans Google Colab, miroir des tests du rapport.
    """
    diagnosis = _as_dict(analysis.get("diagnosis"))
    numeric_cols = [str(c) for c in _as_list(diagnosis.get("numeric_cols"))]
    if not numeric_cols:
        numeric_cols = [
            str(c) for c in _as_list(_as_dict(analysis_result.get("analysis")).get("numeric_cols"))
        ]

    specs = _collect_script_test_specs(
        analysis_result, analysis, intent, multi_entries, is_multi,
    )

    lines: list[str] = [
        "# ============================================",
        "# QUANTA — Script Python généré automatiquement",
        f"# Fichier analysé : {filename}",
        "# Exécutable dans Google Colab (gratuit)",
        "# ============================================",
        "",
        "# == 0. Installation des packages ===========",
        "!pip install pandas numpy scipy statsmodels pingouin matplotlib seaborn scikit-posthocs -q",
        "",
        "# == 1. Chargement des données ==============",
        "import pandas as pd",
        "import numpy as np",
        "from scipy import stats",
        "import matplotlib.pyplot as plt",
        "import seaborn as sns",
        "",
        "# Dans Colab : Runtime > Upload du fichier, ou montez Drive.",
        f"df = pd.read_csv({_py_str(filename)}, sep=',', encoding='utf-8')",
        'print(f"Dimensions : {df.shape[0]} lignes, {df.shape[1]} colonnes")',
        "print(df.head())",
        "",
        "# == 2. Statistiques descriptives ===========",
    ]

    if numeric_cols:
        cols_repr = "[" + ", ".join(_py_str(c) for c in numeric_cols) + "]"
        lines.append(f"numeric_cols = {cols_repr}")
        lines.append("print(df[numeric_cols].describe())")
    else:
        lines.append("print(df.describe(include='all'))")

    lines.extend(["", "# == 3. Tests de normalité =================="])
    if numeric_cols:
        lines.append("for col in numeric_cols:")
        lines.append("    series = df[col].dropna()")
        lines.append("    if len(series) < 3:")
        lines.append('        print(f"Shapiro-Wilk {col} : échantillon insuffisant")')
        lines.append("        continue")
        lines.append("    # Shapiro limité à n<=5000 (contrainte scipy)")
        lines.append("    sample = series if len(series) <= 5000 else series.sample(5000, random_state=42)")
        lines.append("    stat, p = stats.shapiro(sample)")
        lines.append('    print(f"Shapiro-Wilk {col} : W={stat:.4f}, p={p:.3f}")')
    else:
        lines.append("# Aucune colonne numérique détectée.")

    lines.extend(["", "# == 4. Tests effectués ====================="])
    if not specs:
        lines.append("# Aucun test inférentiel à reproduire (analyse descriptive).")
    else:
        for spec in specs:
            lines.append("")
            lines.extend(_python_code_for_test(spec))

    lines.extend([
        "",
        "# == 5. Visualisations ======================",
        "plt.style.use('dark_background')",
        "sns.set_theme(style='darkgrid', rc={",
        "    'axes.facecolor': '#13131A',",
        "    'figure.facecolor': '#0A0A0F',",
        "    'text.color': '#E8E8E8',",
        "    'axes.labelcolor': '#E8E8E8',",
        "    'xtick.color': '#9A9AA8',",
        "    'ytick.color': '#9A9AA8',",
        "})",
    ])
    if numeric_cols:
        lines.append("plot_cols = numeric_cols[:4]  # limiter pour lisibilité Colab")
        lines.append("fig, axes = plt.subplots(len(plot_cols), 2, figsize=(10, 3 * len(plot_cols)))")
        lines.append("if len(plot_cols) == 1:")
        lines.append("    axes = np.array([axes])")
        lines.append("for i, col in enumerate(plot_cols):")
        lines.append("    series = df[col].dropna()")
        lines.append("    axes[i, 0].hist(series, bins=20, color='#C9A84C', edgecolor='#0A0A0F')")
        lines.append("    axes[i, 0].set_title(f'Histogramme — {col}', color='#C9A84C')")
        lines.append("    stats.probplot(series, dist='norm', plot=axes[i, 1])")
        lines.append("    axes[i, 1].set_title(f'QQ-Plot — {col}', color='#00D4FF')")
        lines.append("plt.tight_layout()")
        lines.append("plt.show()")
    else:
        lines.append("# Pas de variable numérique pour histogrammes / QQ-plots.")

    lines.extend([
        "",
        'print("\\n[OK] Script QUANTA execute — comparer les p-values au rapport PDF.")',
    ])
    return "\n".join(lines)


def _html_python_annex(python_script: str) -> str:
    """Annexe D — Script Python (Colab)."""
    return f"""
  <section class="section">
    <h2 style="color:#C9A84C;">Annexe D — Script Python</h2>
    <p style="color:#9A9AA8; font-size:12px; font-style:italic; margin-bottom:12px;">
      Script généré automatiquement — exécutable dans Google Colab (upload du fichier requis).
    </p>
    <pre class="code">{_esc(python_script)}</pre>
  </section>
"""


def _html_audit_trail(audit_trail: list[Any]) -> str:
    """Annexe E — Journal d'audit horodaté."""
    if not audit_trail:
        return ""
    rows: list[str] = []
    for entry in audit_trail:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("timestamp") or "—"
        # Afficher HH:MM:SS si ISO complet.
        ts_display = str(ts)
        if "T" in ts_display:
            try:
                ts_display = ts_display.split("T", 1)[1][:8]
            except Exception:
                pass
        rows.append(
            "<tr>"
            f"<td>{_esc(ts_display)}</td>"
            f"<td>{_esc(entry.get('etape'))}</td>"
            f"<td>{_esc(entry.get('detail'))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return f"""
  <section class="section">
    <h2 style="color:#C9A84C;">Annexe E — Journal d'audit</h2>
    <p style="color:#9A9AA8; font-size:12px; font-style:italic; margin-bottom:12px;">
      Chronologie des étapes d'analyse (horodatage UTC).
    </p>
    <table class="audit-trail">
      <thead>
        <tr>
          <th>Heure</th>
          <th>Étape</th>
          <th>Détail</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </section>
"""


def _html_hypotheses(
    intent: dict[str, Any],
    test_result: dict[str, Any],
    *,
    action_executed: Any = None,
) -> str:
    """Bloc H₀/H₁ pour une sous-section de test inférentiel."""
    data = _coerce_inference_result(test_result)
    if data.get("status") in {"error", "skipped"}:
        return ""

    action = str(action_executed or intent.get("action") or "")
    test_name = str(data.get("test") or data.get("method") or "").lower()

    target = intent.get("target_col") or data.get("target") or data.get("col1") or "—"
    group = intent.get("group_col") or data.get("group") or data.get("col2")

    h0: str | None = None
    h1: str | None = None

    is_corr = (
        action == "correlation"
        or (
            data.get("r") is not None
            and data.get("col1") is not None
            and data.get("col2") is not None
        )
        or "spearman" in test_name
        or "pearson" in test_name
        or "corrélation" in test_name
        or "correlation" in test_name
    )
    is_assoc = (
        action == "association"
        or "chi" in test_name
        or "fisher" in test_name
    )

    if is_corr:
        v1 = data.get("col1") or target
        v2 = data.get("col2") or group or "—"
        h0 = f"Il n'existe pas de corrélation entre {v1} et {v2} (ρ = 0)."
        h1 = "Une corrélation existe (ρ ≠ 0)."
    elif is_assoc:
        v1 = target
        v2 = group or "—"
        h0 = f"{v1} et {v2} sont indépendantes."
        h1 = f"{v1} et {v2} sont associées."
    elif (
        action in {"compare_groups", "compare_groups_2", "compare_groups_multi"}
        or "compare_groups" in action
        or any(
            token in test_name
            for token in ("student", "welch", "mann", "whitney", "anova", "kruskal")
        )
    ):
        n_groups = data.get("n_groups")
        if n_groups is None:
            levels = data.get("group_levels")
            if isinstance(levels, list) and levels:
                n_groups = len(levels)
        if n_groups is None and action == "compare_groups_multi":
            n_groups = 3
        if n_groups is None:
            n_groups = 2

        if int(n_groups) >= 3 and group:
            h0 = (
                f"La distribution de {target} est identique dans les "
                f"{int(n_groups)} groupes de {group}."
            )
            h1 = "Au moins un groupe diffère des autres."
        elif group:
            h0 = (
                f"La moyenne (ou distribution) de {target} est identique "
                f"dans les 2 groupes de {group}."
            )
            h1 = "Les groupes diffèrent significativement."

    if not h0 or not h1:
        return ""

    return f"""
    <div style="background:#1C1C26; border-radius:8px; padding:12px 16px; margin:12px 0;">
      <p style="color:#9A9AA8; font-size:11px; letter-spacing:0.06em; margin:0 0 6px 0;">
        HYPOTHÈSES
      </p>
      <p style="color:#E8E8E8; font-size:12px; font-family:Georgia,serif; margin:2px 0;">
        <strong>H₀ :</strong> {_esc(h0)}
      </p>
      <p style="color:#E8E8E8; font-size:12px; font-family:Georgia,serif; margin:2px 0;">
        <strong>H₁ :</strong> {_esc(h1)}
      </p>
    </div>
    """


def _unpack(analysis_result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Sépare intent / analysis / interpretation selon le contrat brain."""
    analysis = _as_dict(analysis_result.get("analysis"))
    # Tolérance : si on reçoit directement le dict orchestrator (sans wrapper).
    if not analysis and "diagnosis" in analysis_result:
        analysis = analysis_result
    interpretation = _as_dict(analysis_result.get("interpretation"))
    intent = _as_dict(analysis_result.get("intent"))
    return intent, analysis, interpretation


# Libellés publics pour action_executed (jamais d'identifiant interne brut).
_ACTION_LABELS: dict[str, str] = {
    "descriptive_only": "Analyse descriptive",
    "compare_groups_2": "Comparaison de 2 groupes indépendants",
    "compare_groups_k": "Comparaison de k groupes (ANOVA)",
    "compare_groups_multi": "Comparaison de k groupes (ANOVA)",
    "correlation": "Analyse de corrélation",
    "regression_ols": "Régression linéaire (OLS)",
    "logistic_regression": "Régression logistique",
    "regression_logistic": "Régression logistique",
    "association": "Test d'association (Chi-deux / Fisher)",
}

_GENERIC_JUSTIFICATIONS: dict[str, str] = {
    "descriptive_only": (
        "Aucun test inférentiel sélectionné. L'analyse se limite aux "
        "statistiques descriptives du dataset (distributions, tendances "
        "centrales, corrélations entre variables)."
    ),
    "compare_groups_2": (
        "Test de comparaison entre deux groupes indépendants sélectionné "
        "selon la normalité et l'homogénéité des variances de la variable cible."
    ),
    "compare_groups_k": (
        "Test de comparaison multi-groupes (ANOVA ou équivalent non "
        "paramétrique) sélectionné selon les diagnostics de normalité "
        "et d'homogénéité des variances."
    ),
    "compare_groups_multi": (
        "Test de comparaison multi-groupes (ANOVA ou équivalent non "
        "paramétrique) sélectionné selon les diagnostics de normalité "
        "et d'homogénéité des variances."
    ),
    "correlation": (
        "Analyse de corrélation sélectionnée pour quantifier l'association "
        "linéaire ou monotone entre variables numériques."
    ),
    "regression_ols": (
        "Régression linéaire (OLS) sélectionnée pour modéliser la relation "
        "entre une variable réponse continue et un ou plusieurs prédicteurs."
    ),
    "logistic_regression": (
        "Régression logistique sélectionnée pour modéliser une variable "
        "réponse binaire en fonction des prédicteurs disponibles."
    ),
    "regression_logistic": (
        "Régression logistique sélectionnée pour modéliser une variable "
        "réponse binaire en fonction des prédicteurs disponibles."
    ),
    "association": (
        "Test d'association (Chi-deux ou Fisher) sélectionné pour évaluer "
        "le lien entre deux variables catégorielles."
    ),
}


def _format_action_executed(action: Any) -> str:
    """Convertit un code action_executed interne en libellé lisible."""
    if action is None:
        return "—"
    key = str(action).strip()
    if not key:
        return "—"
    return _ACTION_LABELS.get(key, key.replace("_", " ").strip().capitalize())


def _generic_justification(action: Any) -> str:
    key = str(action).strip() if action is not None else ""
    if key in _GENERIC_JUSTIFICATIONS:
        return _GENERIC_JUSTIFICATIONS[key]
    return (
        "La procédure statistique a été sélectionnée automatiquement "
        "par le sélecteur de tests à partir de l'intention d'analyse "
        "et des diagnostics du dataset."
    )


def _selection_justification(analysis: dict[str, Any]) -> str:
    """Justification du test : dérivée de l'audit_log du sélecteur."""
    inference = _as_dict(analysis.get("inference"))
    action = inference.get("action_executed")

    for entry in reversed(_as_list(analysis.get("audit_log"))):
        if not isinstance(entry, dict):
            continue
        etape = str(entry.get("etape", ""))
        if etape in {"selection_test", "validation_intention", "delegation"}:
            justification = entry.get("justification")
            if justification:
                text = str(justification)
                # Ne jamais exposer le fallback interne brut au lecteur.
                if "Action exécutée par le sélecteur" in text:
                    return _generic_justification(action)
                return text

    if action:
        return _generic_justification(action)
    return "Justification de sélection non documentée dans l'audit."


def _statistical_decision(test_result: dict[str, Any]) -> str:
    if test_result.get("status") == "error":
        reason = test_result.get("reason") or "erreur lors du test"
        return f"Décision statistique non applicable ({reason})."
    significant = test_result.get("significant")
    if significant is True:
        return "Rejet de H₀ au seuil α = 0,05."
    if significant is False:
        return "Non-rejet de H₀ au seuil α = 0,05."
    p = test_result.get("p_value")
    if p is None:
        return "Non applicable — analyse descriptive uniquement."
    try:
        return (
            "Rejet de H₀ au seuil α = 0,05."
            if float(p) < 0.05
            else "Non-rejet de H₀ au seuil α = 0,05."
        )
    except (TypeError, ValueError):
        return "Non applicable — analyse descriptive uniquement."


def _coerce_inference_result(payload: Any) -> dict[str, Any]:
    """
    Normalise vers inference['result'].

    Accepte :
      - le dict résultat du test,
      - un wrapper analysis {\"inference\": {\"result\": {...}}},
      - l'enveloppe inference {\"result\": {...}, \"action_executed\": ...}.
    """
    data = _as_dict(payload)
    nested = _as_dict(_as_dict(data.get("inference")).get("result"))
    if nested:
        return nested
    # Enveloppe inference (sans clé "inference" parente).
    if isinstance(data.get("result"), dict):
        has_direct_test_fields = any(
            data.get(key) is not None
            for key in (
                "p_value",
                "statistic",
                "r",
                "rho",
                "dof",
                "df",
                "df1",
                "df2",
                "test",
                "method",
                "correlation",
            )
        )
        if not has_direct_test_fields:
            inner = _as_dict(data.get("result"))
            if inner:
                return inner
    return data


def _format_df_value(value: Any) -> str | None:
    """Formate une valeur de ddl (scalaire ou couple). None si inutilisable."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [
            part
            for item in value
            if item is not None
            for part in (_format_df_value(item),)
            if part is not None
        ]
        return ", ".join(parts) if parts else None
    if isinstance(value, dict):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        text = _esc(value)
        return None if text == "—" else text
    # Ne pas passer par _fmt_number(..., digits=0) : rstrip("0") casse 10, 20, 40…
    if num.is_integer():
        return str(int(num))
    return f"{num:.4g}"


def _extract_degrees_of_freedom(test_result: dict[str, Any]) -> str:
    """
    Extrait les ddl depuis result['inference']['result'].

    Ordre de recherche : df, df1, df2, dof, degrees_of_freedom,
    df_between, df_within. Affiche la première valeur trouvée.
    Si df1 et df2 (ou df_between et df_within) coexistent, affiche le couple.
    Corrélation Pearson / Spearman : df = N - 2 si `n` est disponible.
    """
    data = _coerce_inference_result(test_result)

    # Couple ANOVA / F : préférer l'affichage joint quand les deux existent.
    df1 = data.get("df1")
    df2 = data.get("df2")
    if df1 is not None and df2 is not None:
        left = _format_df_value(df1)
        right = _format_df_value(df2)
        if left and right:
            return f"{left}, {right}"

    between = data.get("df_between")
    within = data.get("df_within")
    if between is not None and within is not None:
        left = _format_df_value(between)
        right = _format_df_value(within)
        if left and right:
            return f"{left}, {right}"

    for key in (
        "df",
        "df1",
        "df2",
        "dof",
        "degrees_of_freedom",
        "df_between",
        "df_within",
    ):
        formatted = _format_df_value(data.get(key))
        if formatted is not None:
            return formatted

    # Corrélation : df = N - 2 (Pearson / Spearman)
    corr_df = _correlation_df(data)
    if corr_df is not None:
        return corr_df

    return "—"


def _correlation_df(data: dict[str, Any]) -> str | None:
    """ddl = N - 2 pour une corrélation bivariée si N est connu."""
    method = str(data.get("method") or data.get("test") or "").lower()
    has_r = data.get("r") is not None or data.get("rho") is not None
    is_corr = (
        "pearson" in method
        or "spearman" in method
        or "corrélation" in method
        or "correlation" in method
        or (has_r and data.get("n") is not None)
    )
    if not is_corr:
        return None
    n = data.get("n")
    if n is None:
        n = data.get("n_observations")
    if n is None:
        n = data.get("N")
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return None
    if n_int < 3:
        return None
    return str(n_int - 2)


def _extract_test_statistic(test_result: dict[str, Any]) -> tuple[Any, str]:
    """
    Statistique de test affichable (y compris r/ρ de corrélation).

    Pour les corrélations, cherche correlation / r / rho / statistic et
    renvoie la valeur pour la ligne « Statistique » du tableau APA.
    """
    data = _coerce_inference_result(test_result)

    if data.get("odds_ratio") is not None and data.get("statistic") is None:
        return data.get("odds_ratio"), "Statistique"

    for key in ("correlation", "r", "rho", "statistic"):
        value = data.get(key)
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        return value, "Statistique"
    return None, "Statistique"


def _resolve_entry_test_result(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Résultat de test pour une entrée multi-tests.
    Priorité : analysis.inference.result, puis entry.result, puis champs résumé.
    """
    from_analysis = _coerce_inference_result(entry.get("analysis"))
    from_entry = _coerce_inference_result(entry.get("result"))
    merged: dict[str, Any] = {}
    if from_analysis:
        merged.update(from_analysis)
    if from_entry:
        merged.update(from_entry)
    for key in (
        "dof",
        "df",
        "df1",
        "df2",
        "degrees_of_freedom",
        "p_value",
        "statistic",
        "r",
        "rho",
        "correlation",
        "odds_ratio",
        "test",
        "method",
        "significant",
        "status",
        "reason",
    ):
        if entry.get(key) is not None and merged.get(key) is None:
            merged[key] = entry[key]
    return merged


def _collect_normality_sources(analysis: dict[str, Any]) -> dict[str, Any]:
    """
    Agrège les diagnostics de normalité depuis les emplacements possibles :
      analysis['normality']
      analysis['diagnosis']['normality_tests'] / ['normality']
      analysis['inference']['result']['normality']
    """
    diagnosis = _as_dict(analysis.get("diagnosis"))
    inference_result = _as_dict(_as_dict(analysis.get("inference")).get("result"))
    merged: dict[str, Any] = {}
    for source in (
        _as_dict(analysis.get("normality")),
        _as_dict(diagnosis.get("normality_tests")),
        _as_dict(diagnosis.get("normality")),
        _as_dict(inference_result.get("normality")),
    ):
        for col, info in source.items():
            if not isinstance(info, dict):
                continue
            existing = _as_dict(merged.get(col))
            # Préférer la fiche la plus riche (avec Shapiro si disponible).
            if "shapiro_wilk" in info or "shapiro_wilk" not in existing:
                merged[col] = {**existing, **info}
            else:
                merged[col] = {**info, **existing}
    return merged


def _shapiro_detail(info: dict[str, Any]) -> str | None:
    """Extrait « Shapiro-Wilk : W = X.XXXX, p = 0.XXX » si disponible."""
    sw = info.get("shapiro_wilk")
    if not isinstance(sw, dict):
        # Alias éventuels
        for key in ("shapiro", "Shapiro-Wilk", "shapiro_wilk_test"):
            candidate = info.get(key)
            if isinstance(candidate, dict):
                sw = candidate
                break
    if not isinstance(sw, dict):
        return None
    w = sw.get("statistic", sw.get("W", sw.get("w")))
    p = sw.get("p_value", sw.get("p", sw.get("pvalue")))
    if w is None or p is None:
        return None
    try:
        w_f = float(w)
        p_f = float(p)
    except (TypeError, ValueError):
        return None
    if w_f != w_f or p_f != p_f:
        return None
    return f"Shapiro-Wilk : W = {w_f:.4f}, p = {format_pvalue(p_f)}"


def _conditions_application(analysis: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """
    Liste (libellé, statut, détail_optionnel) des conditions d'application.
    Statut ∈ {"vérifiée", "non vérifiée", "partielle", "non évaluée"}.
    Le détail porte typiquement la ligne Shapiro-Wilk (W, p).
    """
    conditions: list[tuple[str, str, str | None]] = []
    normality = _collect_normality_sources(analysis)
    for col, info in normality.items():
        if not isinstance(info, dict):
            continue
        conclusion = str(info.get("conclusion", "")).upper()
        detail = _shapiro_detail(info)
        if conclusion == "NORMALE":
            conditions.append((f"Normalité de « {col} »", "vérifiée", detail))
        elif conclusion == "NON-NORMALE":
            conditions.append((f"Normalité de « {col} »", "non vérifiée", detail))
        elif conclusion == "AMBIGUE":
            conditions.append((f"Normalité de « {col} »", "partielle", detail))
        else:
            conditions.append((f"Normalité de « {col} »", "non évaluée", detail))

    test_result = _as_dict(_as_dict(analysis.get("inference")).get("result"))
    levene = _as_dict(test_result.get("levene"))
    if levene:
        equal_var = levene.get("equal_variance")
        if equal_var is True:
            conditions.append(("Homogénéité des variances (Levene)", "vérifiée", None))
        elif equal_var is False:
            conditions.append(("Homogénéité des variances (Levene)", "non vérifiée", None))
        else:
            p_lev = levene.get("p_value")
            if p_lev is not None:
                try:
                    ok = float(p_lev) >= 0.05
                    conditions.append(
                        (
                            "Homogénéité des variances (Levene)",
                            "vérifiée" if ok else "non vérifiée",
                            None,
                        )
                    )
                except (TypeError, ValueError):
                    conditions.append(
                        ("Homogénéité des variances (Levene)", "non évaluée", None)
                    )

    min_expected = test_result.get("min_expected_count")
    if min_expected is not None:
        try:
            ok = float(min_expected) >= 5
            conditions.append(
                (
                    "Effectifs attendus du Chi-deux (≥ 5)",
                    "vérifiée" if ok else "non vérifiée",
                    None,
                )
            )
        except (TypeError, ValueError):
            pass

    if test_result.get("avertissement"):
        conditions.append(
            ("Réserve méthodologique signalée par le test", "non vérifiée", None)
        )

    conf = _as_dict(analysis.get("confidence_score"))
    details = _as_dict(conf.get("details"))
    respect = details.get("respect_conditions")
    if respect is not None:
        try:
            score = float(respect)
            if score >= 85:
                statut = "vérifiée"
            elif score >= 65:
                statut = "partielle"
            else:
                statut = "non vérifiée"
            conditions.append(
                (f"Score composite « respect des conditions » ({score}/100)", statut, None)
            )
        except (TypeError, ValueError):
            pass

    if not conditions:
        conditions.append(("Conditions d'application du test", "non évaluée", None))
    return conditions


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION HTML
# ═══════════════════════════════════════════════════════════════════════════════

def _css() -> str:
    return """
    @page {
      size: A4;
      margin: 1.8cm 1.6cm 2.0cm 1.6cm;
      @bottom-center {
        content: "QUANTA — Rapport d'analyse statistique · page " counter(page);
        font-family: Arial, Helvetica, sans-serif;
        font-size: 8pt;
        color: #8A8A96;
      }
    }
    @page :first {
      @bottom-center { content: none; }
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background: #0A0A0F;
      color: #E8E8E8;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      height: 100%;
    }
    h1, h2, h3 {
      font-family: Georgia, "Times New Roman", serif;
      font-weight: normal;
      color: #E8E8E8;
      margin: 0 0 0.6em 0;
    }
    h1 { font-size: 28pt; letter-spacing: 0.12em; color: #C9A84C; }
    h2 {
      font-size: 14pt;
      color: #C9A84C;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding-bottom: 0.35em;
      margin-top: 0;
      margin-bottom: 1em;
    }
    h3 {
      font-size: 11.5pt;
      color: #00D4FF;
      margin-top: 1.2em;
      margin-bottom: 0.4em;
    }
    p { margin: 0 0 0.75em 0; }
    .muted { color: #8A8A96; }
    .gold { color: #C9A84C; }
    .cyan { color: #00D4FF; }
    .mono {
      font-family: "Courier New", Courier, monospace;
      font-size: 9.5pt;
    }
    .cover {
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      page-break-after: always;
    }
    .cover .subtitle {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 14pt;
      color: #E8E8E8;
      margin: 0.4em 0 2.2em 0;
      letter-spacing: 0.04em;
    }
    .cover-meta {
      width: 78%;
      border-top: 1px solid rgba(255,255,255,0.08);
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding: 1.4em 0;
      margin-top: 1em;
    }
    .cover-meta p { margin: 0.45em 0; font-size: 11pt; }
    .score-badge {
      margin-top: 2em;
      background: #13131A;
      border: 1px solid rgba(255,255,255,0.08);
      padding: 0.9em 1.4em;
      display: inline-block;
    }
    .score-badge .label {
      font-size: 8.5pt;
      color: #8A8A96;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.25em;
    }
    .score-badge .value {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 16pt;
      color: #C9A84C;
    }
    .section { page-break-before: always; }
    .section.first-content { page-break-before: auto; }
    .card {
      background: #13131A;
      border: 1px solid rgba(255,255,255,0.08);
      padding: 0.9em 1.1em;
      margin: 0.8em 0 1.1em 0;
    }
    .kv { width: 100%; border-collapse: collapse; margin: 0.4em 0 1em 0; }
    .kv td {
      padding: 0.35em 0.5em;
      vertical-align: top;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .kv td:first-child {
      width: 38%;
      color: #8A8A96;
      font-size: 9.5pt;
    }
    .apa {
      width: 100%;
      border-collapse: collapse;
      margin: 0.8em 0 1.2em 0;
      font-size: 10pt;
    }
    .apa th, .apa td {
      padding: 0.45em 0.55em;
      border-left: none;
      border-right: none;
      border-top: none;
      border-bottom: none;
      text-align: left;
    }
    .apa thead th {
      font-family: Georgia, "Times New Roman", serif;
      font-weight: normal;
      color: #C9A84C;
      border-top: 1.5pt solid #E8E8E8;
      border-bottom: 1pt solid #E8E8E8;
    }
    .apa tbody td {
      border-bottom: none;
    }
    .apa tbody tr:last-child td {
      border-bottom: 1.5pt solid #E8E8E8;
    }
    .apa td.num, .apa th.num {
      text-align: center;
      font-family: "Courier New", Courier, monospace;
      font-size: 9.5pt;
    }
    ul.plain {
      margin: 0.3em 0 1em 1.1em;
      padding: 0;
    }
    ul.plain li { margin-bottom: 0.35em; }
    .status-ok { color: #00D4FF; }
    .status-ko { color: #E8A0A0; }
    .status-partial { color: #C9A84C; }
    .status-na { color: #8A8A96; }
    pre.code {
      background: #0D0D0D;
      border: 1px solid rgba(255,255,255,0.08);
      padding: 0.9em 1em;
      font-family: "Courier New", Courier, monospace;
      font-size: 8pt;
      line-height: 1.4;
      white-space: pre-wrap;
      word-wrap: break-word;
      color: #E8E8E8;
      page-break-inside: auto;
    }
    .audit-trail {
      width: 100%;
      border-collapse: collapse;
      margin: 0.8em 0 1.2em 0;
      font-family: "Courier New", Courier, monospace;
      font-size: 8.5pt;
      background: #0D0D0D;
      color: #9A9AA8;
    }
    .audit-trail th, .audit-trail td {
      padding: 0.45em 0.55em;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      vertical-align: top;
    }
    .audit-trail thead th {
      color: #C9A84C;
      font-weight: normal;
      border-bottom: 1pt solid rgba(255,255,255,0.12);
    }
    .footnote {
      font-size: 8.5pt;
      color: #8A8A96;
      margin-top: 1.5em;
    }
    """


def _html_variables_table(
    diagnosis: dict[str, Any],
    table_counter: list[int],
) -> str:
    numeric = _as_list(diagnosis.get("numeric_cols"))
    categorical = _as_list(diagnosis.get("cat_cols"))
    rows: list[str] = []
    for col in numeric:
        rows.append(
            f"<tr><td>{_esc(col)}</td><td>Numérique</td></tr>"
        )
    for col in categorical:
        rows.append(
            f"<tr><td>{_esc(col)}</td><td>Catégorielle</td></tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='2'>Aucune variable typée disponible.</td></tr>")
    body = "\n".join(rows)
    caption = _next_table_caption(table_counter, "Variables du dataset")
    return f"""
    {caption}
    <table class="apa">
      <thead>
        <tr><th>Variable</th><th>Type</th></tr>
      </thead>
      <tbody>
        {body}
      </tbody>
    </table>
    """


def _html_missing(
    diagnosis: dict[str, Any],
    table_counter: list[int],
) -> str:
    missing = _as_dict(diagnosis.get("missing"))
    missing_pct = _as_dict(diagnosis.get("missing_pct"))
    if not missing:
        return "<p class='muted'>Aucune valeur manquante détectée.</p>"
    rows = []
    for col, count in missing.items():
        pct = missing_pct.get(col)
        pct_txt = f" ({_fmt_number(pct, 2)} %)" if pct is not None else ""
        rows.append(
            f"<tr><td>{_esc(col)}</td>"
            f"<td class='num'>{_esc(count)}</td>"
            f"<td class='num'>{_esc(pct_txt.strip() or '—')}</td></tr>"
        )
    body = "\n".join(rows)
    caption = _next_table_caption(table_counter, "Valeurs manquantes")
    return f"""
    <h3>Valeurs manquantes</h3>
    {caption}
    <table class="apa">
      <thead>
        <tr>
          <th>Variable</th>
          <th class="num">Effectif manquant</th>
          <th class="num">Pourcentage</th>
        </tr>
      </thead>
      <tbody>
        {body}
      </tbody>
    </table>
    """


def _html_duplicates(diagnosis: dict[str, Any]) -> str:
    """Message Section 1 — doublons détectés (jamais supprimés au diagnostic)."""
    raw = diagnosis.get("n_duplicates")
    try:
        n_dupes = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        n_dupes = 0
    if n_dupes <= 0:
        return "<p>Aucun doublon détecté.</p>"
    return (
        f"<p>Doublons détectés : <span class='mono'>{_esc(n_dupes)}</span> "
        f"lignes identiques (non supprimées automatiquement — vérifier avant "
        f"publication)</p>"
    )


def _html_descriptive_stats(
    diagnosis: dict[str, Any],
    table_counter: list[int],
) -> str:
    """
    Section 1.5 — tableaux APA des statistiques descriptives
    (champ diagnosis['descriptive_stats']).
    """
    stats = _as_dict(diagnosis.get("descriptive_stats"))
    numeric = _as_dict(stats.get("numeric"))
    categorical = _as_dict(stats.get("categorical"))

    if not numeric and not categorical:
        return (
            "<h2>1.5 Statistiques descriptives</h2>"
            "<p class='muted'>Statistiques descriptives non disponibles.</p>"
        )

    blocks: list[str] = ['<h2>1.5 Statistiques descriptives</h2>']

    if numeric:
        rows: list[str] = []
        for col, info in numeric.items():
            data = _as_dict(info)
            rows.append(
                "<tr>"
                f"<td>{_esc(col)}</td>"
                f"<td class='num'>{_fmt_number(data.get('mean'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('median'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('std'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('min'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('max'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('skewness'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('kurtosis'))}</td>"
                f"<td class='num'>{_fmt_number(data.get('missing_pct'), 2)}</td>"
                "</tr>"
            )
        caption = _next_table_caption(
            table_counter,
            "Statistiques descriptives des variables numériques",
        )
        blocks.append(
            f"""
            {caption}
            <table class="apa">
              <thead>
                <tr>
                  <th>Variable</th>
                  <th class="num">Moyenne</th>
                  <th class="num">Médiane</th>
                  <th class="num">Écart-type</th>
                  <th class="num">Min</th>
                  <th class="num">Max</th>
                  <th class="num">Skewness</th>
                  <th class="num">Kurtosis</th>
                  <th class="num">% manquant</th>
                </tr>
              </thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
            """
        )

    if categorical:
        cat_blocks: list[str] = []
        for col, info in categorical.items():
            data = _as_dict(info)
            frequencies = _as_dict(data.get("frequencies"))
            percentages = _as_dict(data.get("percentages"))
            mode = data.get("mode")
            missing_pct = data.get("missing_pct")
            modal_rows: list[str] = []
            for modality, freq in frequencies.items():
                pct = percentages.get(modality)
                modal_rows.append(
                    "<tr>"
                    f"<td>{_esc(modality)}</td>"
                    f"<td class='num'>{_esc(freq)}</td>"
                    f"<td class='num'>{_fmt_number(pct, 2)}</td>"
                    "</tr>"
                )
            if not modal_rows:
                modal_rows.append(
                    "<tr><td colspan='3'>Aucune modalité disponible.</td></tr>"
                )
            caption = _next_table_caption(
                table_counter,
                f"Distribution de {col}",
            )
            cat_blocks.append(
                f"""
                <h3>Variable catégorielle — {_esc(col)}</h3>
                <table class="kv">
                  <tr><td>Mode</td><td>{_esc(mode)}</td></tr>
                  <tr><td>% manquant</td><td class="mono">{_fmt_number(missing_pct, 2)}</td></tr>
                </table>
                {caption}
                <table class="apa">
                  <thead>
                    <tr>
                      <th>Modalité</th>
                      <th class="num">Fréquence</th>
                      <th class="num">Pourcentage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(modal_rows)}
                  </tbody>
                </table>
                """
            )
        blocks.extend(cat_blocks)

    return "\n".join(blocks)


def _apa_effect_rows(data: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Lignes taille d'effet + interprétation Cohen pour le tableau APA."""
    rows: list[tuple[str, str, bool]] = []

    effect = data.get("effect_size")
    effect_name = data.get("effect_size_name") or "Taille d'effet"
    if isinstance(effect, dict):
        for k, v in effect.items():
            rows.append((str(k), _fmt_number(v), True))
            interp = _effect_interpretation_html(str(k), v)
            if interp:
                rows.append(("Interprétation", interp, False))
    elif effect is not None:
        rows.append((str(effect_name), _fmt_number(effect), True))
        interp = _effect_interpretation_html(str(effect_name), effect)
        if interp:
            rows.append(("Interprétation", interp, False))

    for key, label in (
        ("cramers_v", "V de Cramér"),
        ("eta_squared", "η²"),
        ("epsilon_squared", "ε²"),
        ("R2", "R²"),
        ("adj_R2", "R² ajusté"),
        ("n_observations", "N"),
    ):
        if key in data and data[key] is not None:
            rows.append((label, _fmt_number(data[key]), True))
            if key in {"cramers_v", "eta_squared", "epsilon_squared"}:
                interp = _effect_interpretation_html(label, data[key])
                if interp:
                    rows.append(("Interprétation", interp, False))
    return rows


def _power_interpretation_parts(power: float) -> tuple[str, str]:
    """(libellé, couleur) pour la puissance 1-β."""
    if power < 0.5:
        return (
            "insuffisante — risque élevé d'erreur de type II",
            "#E74C3C",
        )
    if power < 0.8:
        return "modérée", "#E67E22"
    return "adéquate", "#2ECC71"


def _apa_power_rows(data: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Ligne Puissance (1-β) + interprétation colorée, après la taille d'effet."""
    raw = data.get("power")
    if raw is None:
        return []
    try:
        power = float(raw)
    except (TypeError, ValueError):
        return []
    if power != power:
        return []
    label = data.get("power_interpretation")
    color: str
    if isinstance(label, str) and label.strip():
        interp = label.strip()
        _, color = _power_interpretation_parts(power)
    else:
        interp, color = _power_interpretation_parts(power)
    value_html = (
        f'{_fmt_number(power, 3)} '
        f'<em style="color:{color};">({_esc(interp)})</em>'
    )
    return [("Puissance (1-β)", value_html, True)]


def _html_posthoc(
    test_result: dict[str, Any],
    table_counter: list[int],
) -> str:
    """Sous-section Comparaisons post-hoc après le tableau APA principal."""
    data = _coerce_inference_result(test_result)
    posthoc = data.get("posthoc")
    if not posthoc or not isinstance(posthoc, dict):
        return ""
    if posthoc.get("error"):
        return ""

    comparisons = posthoc.get("comparisons")
    if not comparisons:
        matrix = posthoc.get("matrix_p_values")
        if isinstance(matrix, dict):
            comparisons = []
            groups = list(matrix.keys())
            for i, g1 in enumerate(groups):
                row = matrix.get(g1)
                if not isinstance(row, dict):
                    continue
                for g2 in groups[i + 1 :]:
                    if g2 not in row:
                        continue
                    try:
                        p_adj = float(row[g2])
                    except (TypeError, ValueError):
                        continue
                    comparisons.append({
                        "group1": str(g1),
                        "group2": str(g2),
                        "meandiff": None,
                        "p_adj": p_adj,
                        "significant": bool(p_adj < 0.05),
                    })
        if not comparisons:
            return ""

    # Diagnostic : compter les comparaisons et les groupes
    nb_comparisons = len(comparisons) if comparisons else 0
    nb_groups = len(set([c.get("group1") for c in comparisons] + [c.get("group2") for c in comparisons])) if comparisons else 0
    print(f"ACM DEBUG - _html_posthoc: {nb_comparisons} comparaisons, {nb_groups} groupes", flush=True)

    # Plafond dur pour éviter OOM avec trop de groupes
    MAX_POSTHOC_ROWS = 50
    total_comparisons = len(comparisons) if comparisons else 0
    if total_comparisons > MAX_POSTHOC_ROWS:
        # Garder seulement les comparaisons les plus significatives (p_adj le plus petit)
        comparisons = sorted(
            comparisons,
            key=lambda c: c.get("p_adj") if c.get("p_adj") is not None else 1.0
        )[:MAX_POSTHOC_ROWS]

    method = str(posthoc.get("method") or "Comparaisons post-hoc")
    rows: list[str] = []
    for comp in comparisons:
        if not isinstance(comp, dict):
            continue
        # Couleur basée sur p_adj (contrat rapport) ; repli sur le flag significant.
        try:
            p_adj_f = float(comp.get("p_adj"))
            sig = bool(p_adj_f < 0.05) if p_adj_f == p_adj_f else bool(
                comp.get("significant", False)
            )
        except (TypeError, ValueError):
            sig = bool(comp.get("significant", False))
        color = "#C9A84C" if sig else "#9A9AA8"
        rows.append(
            "<tr>"
            f'<td style="color:{color};">{_esc(comp.get("group1"))}</td>'
            f'<td style="color:{color};">{_esc(comp.get("group2"))}</td>'
            f'<td class="num" style="color:{color};">'
            f'{_fmt_number(comp.get("meandiff"))}</td>'
            f'<td class="num" style="color:{color};">'
            f'{_fmt_pvalue(comp.get("p_adj"))}</td>'
            f'<td style="color:{color};">'
            f'{"Oui" if sig else "Non"}</td>'
            "</tr>"
        )

    if not rows:
        return ""

    caption = _next_table_caption(table_counter, "Comparaisons post-hoc")
    
    troncature_note = ""
    if total_comparisons > MAX_POSTHOC_ROWS:
        troncature_note = (
            f'<p class="muted" style="font-size:10px; margin-top:4px;">'
            f'Affichage limité aux {MAX_POSTHOC_ROWS} comparaisons les plus '
            f'significatives sur {total_comparisons} au total '
            f'(nombre de groupes trop élevé pour un affichage exhaustif).</p>'
        )
    
    html_posthoc_final = f"""
    <h3 style="color:#00D4FF;">Comparaisons post-hoc</h3>
    <p class="muted" style="font-size:11px; margin-bottom:8px;">{_esc(method)}</p>
    {caption}
    <table class="apa">
      <thead>
        <tr>
          <th>Groupe 1</th>
          <th>Groupe 2</th>
          <th class="num">Δ Moyen</th>
          <th class="num">p ajusté</th>
          <th>Significatif</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    {troncature_note}
    """
    print(f"ACM DEBUG - _html_posthoc HTML généré: {len(html_posthoc_final)} car.", flush=True)
    return html_posthoc_final


def _shapiro_pvalue(info: dict[str, Any]) -> float | None:
    """Extrait la p-value Shapiro-Wilk d'un diagnostic de normalité."""
    sw = info.get("shapiro_wilk")
    if not isinstance(sw, dict):
        for key in ("shapiro", "Shapiro-Wilk", "shapiro_wilk_test"):
            candidate = info.get(key)
            if isinstance(candidate, dict):
                sw = candidate
                break
    if not isinstance(sw, dict):
        return None
    p = sw.get("p_value", sw.get("p", sw.get("pvalue")))
    try:
        p_f = float(p)
    except (TypeError, ValueError):
        return None
    return p_f if p_f == p_f else None


def _collect_inferential_test_payloads(
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    multi_entries: list[dict[str, Any]],
    is_multi: bool,
) -> list[dict[str, Any]]:
    """Liste des résultats inférentiels pour la défense scientifique."""
    if is_multi and multi_entries:
        return [
            _resolve_entry_test_result(entry)
            for entry in multi_entries
            if not _is_descriptive_only_entry(entry)
        ]
    inference = _as_dict(analysis.get("inference"))
    data = _coerce_inference_result(inference.get("result"))
    return [data] if data and data.get("status") not in {"error", "skipped"} else []


def _resolve_effect_metric_for_defense(data: dict[str, Any]) -> tuple[str, float] | None:
    """(nom métrique, valeur) pour l'objection sur taille d'effet."""
    effect = data.get("effect_size")
    effect_name = str(data.get("effect_size_name") or "Taille d'effet")
    if effect is not None and not isinstance(effect, dict):
        try:
            return effect_name, float(effect)
        except (TypeError, ValueError):
            pass
    for key, label in (
        ("cramers_v", "V de Cramér"),
        ("eta_squared", "η²"),
        ("epsilon_squared", "ε²"),
        ("r", "r"),
        ("rho", "r"),
        ("correlation", "r"),
    ):
        if data.get(key) is not None:
            try:
                return label, float(data[key])
            except (TypeError, ValueError):
                continue
    return None


def _defense_block_html(critique: str, reponse: str, verdict: str, *, warning: bool = False) -> str:
    icon = "⚠" if warning else "✓"
    return f"""
    <div style="border:1px solid rgba(255,255,255,0.06);
       border-radius:8px; padding:16px; margin:12px 0;">
      <p style="color:#E74C3C; font-size:12px;
         font-weight:600; margin:0 0 6px 0;">
        ⚔ Critique possible
      </p>
      <p style="color:#E8E8E8; font-size:12px;
         margin:0 0 12px 16px; font-style:italic;">
        &ldquo;{_esc(critique)}&rdquo;
      </p>
      <p style="color:#00D4FF; font-size:12px;
         font-weight:600; margin:0 0 6px 0;">
        🛡 Réponse QUANTA
      </p>
      <p style="color:#E8E8E8; font-size:12px;
         margin:0 0 12px 16px;">
        {_esc(reponse)}
      </p>
      <p style="font-size:11px; margin:0;
         padding:6px 12px; border-radius:4px;
         background:#1C1C26; display:inline-block;">
        {icon} {_esc(verdict)}
      </p>
    </div>
    """


def _html_scientific_defense(
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    interpretation: dict[str, Any],
    multi_entries: list[dict[str, Any]],
    is_multi: bool,
) -> str:
    """Section Défense Scientifique — 3 à 6 objections/réponses automatiques."""
    blocks: list[str] = []
    diagnosis = _as_dict(analysis.get("diagnosis"))
    n_obs = diagnosis.get("n_rows")

    test_payloads = _collect_inferential_test_payloads(
        analysis_result, analysis, multi_entries, is_multi,
    )

    # Objection 1 — normalité violée
    normality = _collect_normality_sources(analysis)
    non_normal_cols: list[tuple[str, float | None, str | None]] = []
    for col, info in normality.items():
        if not isinstance(info, dict):
            continue
        if str(info.get("conclusion", "")).upper() != "NON-NORMALE":
            continue
        shapiro_p = _shapiro_pvalue(info)
        test_used: str | None = None
        for payload in test_payloads:
            target = payload.get("target") or payload.get("col1")
            if target == col or col in str(payload.get("test", "")):
                test_used = str(payload.get("test") or payload.get("method") or "")
                break
        if not test_used:
            for entry in _as_list(analysis.get("audit_log")):
                if not isinstance(entry, dict):
                    continue
                if entry.get("etape") == "selection_test" and entry.get("colonne") == col:
                    test_used = str(entry.get("decision") or "")
                    break
        non_normal_cols.append((str(col), shapiro_p, test_used))

    for col, shapiro_p, test_used in non_normal_cols:
        p_txt = format_pvalue(shapiro_p) if shapiro_p is not None else "—"
        test_label = test_used or "un test non paramétrique"
        blocks.append(_defense_block_html(
            critique=f"La normalité est violée pour {col}.",
            reponse=(
                f"Le moteur a sélectionné {test_label} précisément parce que "
                f"la normalité de {col} a été rejetée (Shapiro-Wilk p={p_txt}). "
                f"Ce test ne requiert pas la normalité."
            ),
            verdict="Défense validée",
        ))

    # Objection 2 — absence de significativité (tous les tests p >= 0.05)
    p_values: list[float] = []
    power_payload: dict[str, Any] | None = None
    for payload in test_payloads:
        p_raw = payload.get("p_value")
        if p_raw is None:
            continue
        try:
            p = float(p_raw)
        except (TypeError, ValueError):
            continue
        if p == p:
            p_values.append(p)
        if power_payload is None and payload.get("power") is not None:
            power_payload = payload

    if p_values and all(p >= 0.05 for p in p_values):
        n_txt = str(n_obs) if n_obs is not None else "—"
        power_val: float | None = None
        if power_payload is not None:
            try:
                power_val = float(power_payload.get("power"))
            except (TypeError, ValueError):
                power_val = None
            if power_val is not None and power_val != power_val:
                power_val = None

        if power_val is not None:
            stored_interp = power_payload.get("power_interpretation") if power_payload else None
            if isinstance(stored_interp, str) and stored_interp.strip():
                interp = stored_interp.strip()
            else:
                interp, _ = _power_interpretation_parts(power_val)
            if power_val >= 0.8:
                suite = (
                    "L'absence d'effet ne semble pas liée à un manque de puissance."
                )
                warning = False
                verdict = "Défense validée"
            else:
                n_req = None
                if power_payload is not None:
                    n_req = power_payload.get("n_required")
                n_req_txt = str(int(n_req)) if n_req is not None else "—"
                suite = (
                    f"Une puissance plus élevée nécessiterait "
                    f"N={n_req_txt} observations."
                )
                warning = True
                verdict = "À vérifier avec une analyse de puissance formelle"
            blocks.append(_defense_block_html(
                critique=(
                    "L'absence de significativité pourrait être due à un manque de puissance."
                ),
                reponse=(
                    f"Avec N={n_txt}, la puissance calculée est "
                    f"{_fmt_number(power_val, 3)} ({interp}). {suite}"
                ),
                verdict=verdict,
                warning=warning,
            ))
        else:
            blocks.append(_defense_block_html(
                critique=(
                    "L'absence de significativité pourrait être due à un manque de puissance."
                ),
                reponse=(
                    f"L'échantillon comprend N={n_txt} observations. "
                    f"Une analyse de puissance formelle n'a pas pu être calculée "
                    f"pour ce(s) test(s) ; les conclusions restent prudentes."
                ),
                verdict="À vérifier avec une analyse de puissance formelle",
                warning=True,
            ))

    # Objection 3 — taille d'effet négligeable
    seen_effects: set[tuple[str, float]] = set()
    for payload in test_payloads:
        resolved = _resolve_effect_metric_for_defense(payload)
        if not resolved:
            continue
        metric, eff_val = resolved
        key = (metric, round(eff_val, 6))
        if key in seen_effects:
            continue
        seen_effects.add(key)
        if interpret_effect_size(metric, eff_val) == "négligeable":
            blocks.append(_defense_block_html(
                critique=f"La taille d'effet est négligeable ({metric} = {_fmt_number(eff_val)}).",
                reponse=(
                    "Correct. Même si un test était significatif, l'effet pratique "
                    "serait minimal. Les conclusions restent prudentes sur la pertinence "
                    "pratique des résultats."
                ),
                verdict="Évaluation honnête",
            ))

    # Objection 4 — Skeptic Engine
    if interpretation.get("skeptic_engine_alert") is True:
        blocks.append(_defense_block_html(
            critique="L'interprétation semble incohérente avec les p-values.",
            reponse=(
                "Le Skeptic Engine de QUANTA a détecté cette incohérence et l'a "
                "signalée explicitement en Section 3. Les conclusions doivent être "
                "lues avec cette réserve."
            ),
            verdict="Incohérence documentée",
        ))

    if not blocks:
        return ""

    # Limiter à 6 blocs maximum ; viser 3+ si possible via les règles ci-dessus.
    blocks = blocks[:6]
    return f"""
  <section class="section">
    <h2 style="color:#C9A84C;">Défense Scientifique</h2>
    <p style="color:#9A9AA8; font-size:12px;
       font-style:italic; margin-bottom:16px;">
      Anticipation des objections méthodologiques les plus fréquentes face à ces résultats.
    </p>
    {''.join(blocks)}
  </section>
"""


def _html_apa_results(
    test_result: dict[str, Any],
    table_counter: list[int],
    *,
    target_col: str | None = None,
    group_col: str | None = None,
) -> str:
    data = _coerce_inference_result(test_result)
    test_name = data.get("test") or data.get("method") or "—"
    statistic, stat_label = _extract_test_statistic(data)

    rows: list[tuple[str, str, bool]] = [
        ("Test", _esc(test_name), False),
        (stat_label, _fmt_number(statistic), True),
        ("ddl", _extract_degrees_of_freedom(data), True),
        ("p", _fmt_pvalue(data.get("p_value")), True),
    ]
    rows.extend(_apa_effect_rows(data))
    rows.extend(_apa_power_rows(data))

    body_rows = []
    for label, value, is_num in rows:
        cls = " class='num'" if is_num else ""
        body_rows.append(f"<tr><td>{_esc(label)}</td><td{cls}>{value}</td></tr>")

    target = target_col or data.get("target") or data.get("col1")
    group = group_col or data.get("group") or data.get("col2")
    if target and group:
        apa_title = f"Résultats du {test_name} — {target} selon {group}"
    elif target:
        apa_title = f"Résultats du {test_name} — {target}"
    else:
        apa_title = f"Résultats du {test_name}"
    caption = _next_table_caption(table_counter, apa_title)

    html_apa_final = f"""
    {caption}
    <table class="apa">
      <thead>
        <tr><th>Mesure</th><th class="num">Valeur</th></tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
    {_html_posthoc(data, table_counter)}
    """
    print(f"ACM DEBUG - _html_apa_results HTML généré: {len(html_apa_final)} car.", flush=True)
    return html_apa_final

# Titres HTML pour les clés de graphiques du pipeline compute (jamais la clé brute).
_CHART_SECTION_TITLES: dict[str, str] = {
    "distributions": "Distributions des variables numériques",
    "categories": "Répartition des variables catégorielles",
    "qqplots": "Tests de normalité (QQ-Plots)",
    "correlation_heatmap": "Matrice de corrélation",
    "regression_diagnostics": "Diagnostics de régression",
}

_HEATMAP_FEW_VARS_NOTE = (
    '<p style="color:#555563; font-size:11px; font-style:italic; '
    'margin:4px 0 16px 0;">'
    "Note : la matrice de corrélation est plus informative "
    "avec 4 variables numériques ou plus."
    "</p>"
)


def _chart_section_title(chart_key: str, filename: str | None = None) -> str | None:
    """
    Titre affiché au-dessus d'un graphique.
    Clés pipeline → libellé FR. Identifiants snake_case inconnus → None
    (ne jamais afficher la clé brute). Titres déjà humains → conservés.
    Suffixe « — [filename] » si un nom de fichier est fourni.
    """
    if chart_key in _CHART_SECTION_TITLES:
        title = _CHART_SECTION_TITLES[chart_key]
    elif chart_key.isidentifier() and "_" in chart_key:
        return None
    else:
        title = chart_key

    if filename and filename != "fichier inconnu":
        return f"{title} — {filename}"
    return title


def _n_numeric_vars(analysis: dict[str, Any] | None) -> int | None:
    """Nombre de variables numériques (pour la note sous heatmap)."""
    analysis = _as_dict(analysis)
    diag = _as_dict(analysis.get("diagnosis"))
    cols = diag.get("numeric_cols")
    if isinstance(cols, list):
        return len(cols)
    for key in ("correlation", "correlation_base"):
        corr = _as_dict(analysis.get(key))
        matrix = corr.get("matrix")
        if isinstance(matrix, dict):
            return len(matrix)
    return None


def _normalize_chart_payload(payload: Any) -> list[tuple[str, str]]:
    """
    Normalise charts / distribution_charts vers (clé_ou_titre, base64_png).
    Pour un dict pipeline, conserve la clé technique (ex. correlation_heatmap)
    afin d'appliquer titres FR + notes ; ne jamais l'afficher brute dans le HTML.
    """
    out: list[tuple[str, str]] = []

    def _strip_data_uri(raw: str) -> str:
        text = raw.strip()
        marker = "base64,"
        if text.startswith("data:") and marker in text:
            return text.split(marker, 1)[1].strip()
        return text

    if isinstance(payload, dict):
        for name, value in payload.items():
            if isinstance(value, str) and value.strip():
                out.append((str(name), _strip_data_uri(value)))
            elif isinstance(value, dict):
                data = value.get("data") or value.get("base64") or value.get("image")
                if isinstance(data, str) and data.strip():
                    title = str(name) if str(name) in _CHART_SECTION_TITLES else (
                        value.get("title") or value.get("name") or name
                    )
                    out.append((str(title), _strip_data_uri(data)))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload, start=1):
            if isinstance(item, str) and item.strip():
                out.append((f"Graphique {idx}", _strip_data_uri(item)))
            elif isinstance(item, dict):
                data = item.get("data") or item.get("base64") or item.get("image")
                if isinstance(data, str) and data.strip():
                    title = item.get("title") or item.get("name") or f"Graphique {idx}"
                    out.append((str(title), _strip_data_uri(data)))
    elif isinstance(payload, str) and payload.strip():
        out.append(("Graphique", _strip_data_uri(payload)))
    return out


def _collect_charts_for_section(
    analysis: dict[str, Any] | None = None,
    test_result: dict[str, Any] | None = None,
    theme: str = "dark",
) -> list[tuple[str, str]]:
    """
    Chemins prioritaires :
      analysis['inference']['result']['charts']
      analysis['inference']['result']['distribution_charts']
    Fallback (pipeline actuel) :
      analysis['charts'], analysis['distribution_charts']
      test_result['charts'], test_result['distribution_charts']
    
    theme : "dark" (défaut) ou "light". Si "light" et charts_light disponible,
            utilise les graphiques light.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    seen: set[str] = set()
    collected: list[tuple[str, str]] = []

    def _add(payload: Any) -> None:
        for label, b64 in _normalize_chart_payload(payload):
            if not b64 or b64 in seen:
                continue
            seen.add(b64)
            collected.append((label, b64))

    analysis = _as_dict(analysis)
    nested_result = _as_dict(
        _as_dict(analysis.get("inference")).get("result")
    )
    data = _coerce_inference_result(test_result) if test_result else {}

    # Détermine la source de graphiques à utiliser selon le thème
    charts_source = "charts"
    if theme == "light" and analysis.get("charts_light"):
        charts_source = "charts_light"

    # LOGGING DIAGNOSTIC
    logger.info(f"CHARTS DEBUG - analysis keys: {list(analysis.keys())}")
    logger.info(f"CHARTS DEBUG - nested_result keys: {list(nested_result.keys())}")
    logger.info(f"CHARTS DEBUG - charts_source: {charts_source}")
    logger.info(f"CHARTS DEBUG - analysis.get(charts_source): {analysis.get(charts_source) is not None}")
    if analysis.get(charts_source):
        logger.info(f"CHARTS DEBUG - charts count: {len(analysis.get(charts_source, {}))}")

    for source in (
        nested_result.get(charts_source),
        nested_result.get("distribution_charts"),
        analysis.get(charts_source),
        analysis.get("distribution_charts"),
        data.get(charts_source),
        data.get("distribution_charts"),
    ):
        if source:
            logger.info(f"CHARTS DEBUG - Found source with {len(source) if isinstance(source, dict) else len(source)} items")
            _add(source)
    
    # Ajouter le boxplot si disponible (comparaison de groupes)
    boxplot = data.get("boxplot") or nested_result.get("boxplot")
    if boxplot:
        logger.info("CHARTS DEBUG - Found boxplot")
        _add(("Boxplot - Distribution par groupe", boxplot))
    
    # Ajouter les scatter plots si disponibles (corrélations significatives)
    scatter_plots = data.get("scatter_plots") or nested_result.get("scatter_plots")
    if scatter_plots and isinstance(scatter_plots, dict):
        logger.info(f"CHARTS DEBUG - Found {len(scatter_plots)} scatter plots")
        for pair_key, scatter_b64 in scatter_plots.items():
            if scatter_b64:
                _add((f"Scatter plot - {pair_key}", scatter_b64))

    logger.info(f"CHARTS DEBUG - Total collected: {len(collected)} charts")
    return collected


def _html_charts(
    charts: list[tuple[str, str]],
    *,
    n_numeric_vars: int | None = None,
    filename: str | None = None,
) -> str:
    """Intègre les graphiques base64 PNG dans le HTML du rapport."""
    if not charts:
        return ""
    blocks: list[str] = ['<h3>Graphiques</h3>']
    for chart_key, b64 in charts:
        title = _chart_section_title(chart_key, filename=filename)
        if title:
            blocks.append(f'<p class="muted">{_esc(title)}</p>')
        alt = title or "Graphique"
        blocks.append(
            f'<img src="data:image/png;base64,{b64}" '
            f'alt="{_esc(alt)}" '
            f'style="max-width:100%; border-radius:8px; margin:16px 0;"/>'
        )
        if (
            chart_key == "correlation_heatmap"
            and n_numeric_vars is not None
            and n_numeric_vars < 4
        ):
            blocks.append(_HEATMAP_FEW_VARS_NOTE)
    return "\n".join(blocks)


def _status_class(statut: str) -> str:
    mapping = {
        "vérifiée": "status-ok",
        "non vérifiée": "status-ko",
        "partielle": "status-partial",
        "non évaluée": "status-na",
    }
    return mapping.get(statut, "status-na")


def _collect_multi_tests(analysis_result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Liste normalisée des tests en mode autonome.
    Sources possibles : tests_effectues (brain) et/ou analyses[].
    """
    analyses_by_index = _as_list(analysis_result.get("analyses"))
    entries: list[dict[str, Any]] = []

    for idx, item in enumerate(_as_list(analysis_result.get("tests_effectues"))):
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        if "analysis" not in entry and idx < len(analyses_by_index):
            paired = _as_dict(analyses_by_index[idx])
            entry["analysis"] = _as_dict(paired.get("analysis"))
            if "intent" not in entry:
                entry["intent"] = _as_dict(paired.get("intent"))
        if "result" not in entry or not entry.get("result"):
            entry["result"] = _as_dict(
                _as_dict(_as_dict(entry.get("analysis")).get("inference")).get("result")
            )
        entries.append(entry)

    if not entries:
        for item in analyses_by_index:
            if not isinstance(item, dict):
                continue
            intent = _as_dict(item.get("intent"))
            analysis = _as_dict(item.get("analysis"))
            inference = _as_dict(analysis.get("inference"))
            test_result = _as_dict(inference.get("result"))
            confidence = _as_dict(analysis.get("confidence_score"))
            entries.append(
                {
                    "intent": intent,
                    "action_executed": inference.get("action_executed"),
                    "test": test_result.get("test"),
                    "statistic": test_result.get(
                        "statistic", test_result.get("odds_ratio")
                    ),
                    "p_value": test_result.get("p_value"),
                    "dof": test_result.get("dof", test_result.get("df")),
                    "significant": test_result.get("significant"),
                    "status": test_result.get("status"),
                    "reason": test_result.get("reason"),
                    "score_confiance": confidence.get("score_global"),
                    "result": test_result,
                    "analysis": analysis,
                }
            )
    return _filter_descriptive_when_inferential(entries)


def _test_display_name(entry: dict[str, Any]) -> str:
    raw_test = entry.get("test")
    if raw_test:
        return str(raw_test)
    action = entry.get("action_executed")
    if not action:
        intent = _as_dict(entry.get("intent"))
        action = intent.get("action")
    return _format_action_executed(action)


def _is_descriptive_only_entry(entry: dict[str, Any]) -> bool:
    action = entry.get("action_executed")
    if not action:
        action = _as_dict(entry.get("intent")).get("action")
    return str(action or "") == "descriptive_only"


def _entry_pvalue(entry: dict[str, Any]) -> Any:
    """p-value résolue depuis le résumé, result, ou analysis.inference.result."""
    p = entry.get("p_value")
    if p is not None:
        return p
    return _resolve_entry_test_result(entry).get("p_value")


def _filter_descriptive_when_inferential(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Si au moins un test inférentiel porte une vraie p-value
    (p != None et action != descriptive_only), on retire les entrées
    descriptive_only du rapport (elles n'apportent rien).
    """
    has_real_inferential = False
    for entry in entries:
        if _is_descriptive_only_entry(entry):
            continue
        p = _entry_pvalue(entry)
        if p is None:
            continue
        try:
            float(p)
        except (TypeError, ValueError):
            continue
        has_real_inferential = True
        break

    if not has_real_inferential:
        return entries
    return [entry for entry in entries if not _is_descriptive_only_entry(entry)]


def _html_multi_section2(
    entries: list[dict[str, Any]],
    table_counter: list[int],
    *,
    filename: str | None = None,
    theme: str = "dark",
) -> str:
    """Section 2 complète pour le mode autonome multi-tests."""
    entries = _filter_descriptive_when_inferential(entries)
    recap_rows: list[str] = []
    for i, entry in enumerate(entries, start=1):
        test_result = _resolve_entry_test_result(entry)
        decision = _statistical_decision(test_result)
        statistic, _ = _extract_test_statistic(test_result)
        if statistic is None:
            statistic = entry.get("statistic")
        p_value = _entry_pvalue(entry)
        intent = _as_dict(entry.get("intent"))
        vars_txt = " / ".join(
            part
            for part in (
                intent.get("target_col"),
                intent.get("group_col"),
            )
            if part
        ) or "—"
        recap_rows.append(
            "<tr>"
            f"<td class='num'>{i}</td>"
            f"<td>{_esc(_test_display_name(entry))}</td>"
            f"<td>{_esc(vars_txt)}</td>"
            f"<td class='num'>{_fmt_number(statistic)}</td>"
            f"<td class='num'>{_fmt_pvalue(p_value)}</td>"
            f"<td>{_esc(decision)}</td>"
            "</tr>"
        )

    recap_caption = _next_table_caption(
        table_counter,
        "Récapitulatif des analyses statistiques — mode autonome",
    )
    recap_table = f"""
    {recap_caption}
    <p class="muted">
      Mode autonome : QUANTA a sélectionné et exécuté plusieurs analyses
      à partir de la structure du dataset.
    </p>
    <table class="apa">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Test</th>
          <th>Variables</th>
          <th class="num">Statistique</th>
          <th class="num">p</th>
          <th>Décision (α = 0,05)</th>
        </tr>
      </thead>
      <tbody>
        {''.join(recap_rows)}
      </tbody>
    </table>
    """

    subsections: list[str] = []
    charts_already_emitted: set[str] = set()
    for i, entry in enumerate(entries, start=1):
        test_result = _resolve_entry_test_result(entry)
        analysis = _as_dict(entry.get("analysis"))
        intent = _as_dict(entry.get("intent"))
        if analysis:
            justification = _selection_justification(analysis)
        else:
            justification = _generic_justification(
                entry.get("action_executed")
                or intent.get("action")
            )
        decision = _statistical_decision(test_result)
        statistic, _ = _extract_test_statistic(test_result)
        if statistic is None:
            statistic = entry.get("statistic")
        p_value = _entry_pvalue(entry)
        has_inferential = bool(
            test_result.get("test")
            or test_result.get("method")
            or p_value is not None
            or statistic is not None
        ) and test_result.get("status") not in {"error", "skipped"}

        if has_inferential:
            apa_block = _html_apa_results(
                test_result,
                table_counter,
                target_col=intent.get("target_col"),
                group_col=intent.get("group_col"),
            )
            hypotheses_block = _html_hypotheses(
                intent,
                test_result,
                action_executed=entry.get("action_executed"),
            )
            section_charts = [
                (label, b64)
                for label, b64 in _collect_charts_for_section(
                    analysis=analysis, test_result=test_result, theme=theme
                )
                if b64 not in charts_already_emitted
            ]
            for _, b64 in section_charts:
                charts_already_emitted.add(b64)
            charts_block = _html_charts(
                section_charts,
                n_numeric_vars=_n_numeric_vars(analysis),
                filename=filename,
            )
            detail_extra = ""
        else:
            fallback_msg = test_result.get("reason") or (
                "Aucun test inférentiel pour cette sous-analyse "
                "(descriptif ou intention non aboutie)."
            )
            apa_block = ""
            charts_block = ""
            hypotheses_block = ""
            detail_extra = f"<div class='card'><p>{_esc(fallback_msg)}</p></div>"

        bloc_html = f"""
            <h3>{i}. {_esc(_test_display_name(entry))}</h3>
            <div class="card">
              <p class="muted" style="margin-bottom:0.3em;">Justification de la sélection</p>
              <p style="margin:0;">{_esc(justification)}</p>
            </div>
            {detail_extra}
            {hypotheses_block}
            <table class="kv">
              <tr><td>Statistique de test</td><td class="mono">{_fmt_number(statistic)}</td></tr>
              <tr><td>p-value</td><td class="mono">{_fmt_pvalue(p_value)}</td></tr>
              <tr><td>Degrés de liberté</td><td class="mono">{_extract_degrees_of_freedom(test_result)}</td></tr>
            </table>
            <p><strong class="gold">Décision statistique :</strong> {_esc(decision)}</p>
            {apa_block}
            {charts_block}
            """
        print(f"ACM DEBUG - Bloc analyse {i}: {len(bloc_html)} car.", flush=True)
        subsections.append(bloc_html)

    return recap_table + "\n".join(subsections)


def _html_single_section2(
    analysis: dict[str, Any],
    test_result: dict[str, Any],
    test_name: str,
    justification: str,
    table_counter: list[int],
    *,
    intent: dict[str, Any] | None = None,
    filename: str | None = None,
    action_executed: Any = None,
    theme: str = "dark",
) -> str:
    """Section 2 pour une analyse mono-intent (comportement historique)."""
    data = _coerce_inference_result(test_result)
    if not data.get("p_value") and not data.get("statistic") and not data.get("r"):
        # Tolérance : analysis entière passée à la place du result.
        data = _coerce_inference_result(analysis) or data
    decision = _statistical_decision(data)
    statistic, _ = _extract_test_statistic(data)
    has_inferential = bool(
        data.get("test")
        or data.get("method")
        or data.get("p_value") is not None
        or statistic is not None
    ) and data.get("status") != "error"
    intent = _as_dict(intent)
    if not has_inferential:
        fallback_msg = data.get("reason") or (
            "Aucun test inférentiel applicable pour cette requête "
            "(analyse descriptive ou intention non aboutie)."
        )
        analyse_extra = f"<div class='card'><p>{_esc(fallback_msg)}</p></div>"
        apa_block = ""
        charts_block = ""
        hypotheses_block = ""
    else:
        analyse_extra = ""
        hypotheses_block = _html_hypotheses(
            intent,
            data,
            action_executed=action_executed,
        )
        apa_block = _html_apa_results(
            data,
            table_counter,
            target_col=intent.get("target_col"),
            group_col=intent.get("group_col"),
        )
        charts_block = _html_charts(
            _collect_charts_for_section(analysis=analysis, test_result=data, theme=theme),
            n_numeric_vars=_n_numeric_vars(analysis),
            filename=filename,
        )
    decision_block = (
        f"<p><strong class='gold'>Décision statistique :</strong> {_esc(decision)}</p>"
    )
    return f"""
    <h3>Test appliqué</h3>
    <p><strong class="cyan">{_esc(test_name)}</strong></p>
    <div class="card">
      <p class="muted" style="margin-bottom:0.3em;">Justification de la sélection</p>
      <p style="margin:0;">{_esc(justification)}</p>
    </div>
    {analyse_extra}
    {hypotheses_block}
    <h3>Résultats chiffrés</h3>
    <table class="kv">
      <tr><td>Statistique de test</td><td class="mono">{_fmt_number(statistic)}</td></tr>
      <tr><td>p-value</td><td class="mono">{_fmt_pvalue(data.get("p_value"))}</td></tr>
      <tr><td>Degrés de liberté</td><td class="mono">{_extract_degrees_of_freedom(data)}</td></tr>
    </table>
    {decision_block}
    {apa_block}
    {charts_block}
    """


def _resolve_effect_for_resume(data: dict[str, Any]) -> tuple[str | None, Any]:
    """(nom, valeur) de taille d'effet pour la section En résumé."""
    if data.get("effect_size") is not None and not isinstance(data.get("effect_size"), dict):
        return (
            str(data.get("effect_size_name") or "Taille d'effet"),
            data.get("effect_size"),
        )
    for key, label in (
        ("cramers_v", "V de Cramér"),
        ("eta_squared", "η²"),
        ("epsilon_squared", "ε²"),
        ("r", "r"),
        ("rho", "r"),
        ("correlation", "r"),
    ):
        if data.get(key) is not None:
            return label, data.get(key)
    return None, None


def _resume_bullet_from_test(
    *,
    test_result: dict[str, Any],
    intent: dict[str, Any],
    action_executed: Any = None,
) -> str | None:
    """
    Une puce actionnable pour la section En résumé, ou None si non applicable.
    """
    data = _coerce_inference_result(test_result)
    if data.get("status") in {"error", "skipped"}:
        return None
    p_raw = data.get("p_value")
    if p_raw is None:
        return None
    try:
        p = float(p_raw)
    except (TypeError, ValueError):
        return None
    if p != p:
        return None

    target = (
        intent.get("target_col")
        or data.get("target")
        or data.get("col1")
    )
    group = (
        intent.get("group_col")
        or data.get("group")
        or data.get("col2")
    )
    test_name = data.get("test") or data.get("method") or "test"
    p_txt = format_pvalue(p)

    action = str(action_executed or intent.get("action") or "")
    is_corr = (
        action == "correlation"
        or "corrél" in str(test_name).lower()
        or "correl" in str(test_name).lower()
        or (
            data.get("r") is not None
            and data.get("col1") is not None
            and data.get("col2") is not None
        )
    )

    check = '<span style="color:#C9A84C;">✓</span>'
    cross = '<span style="color:#555563;">✗</span>'

    if is_corr:
        v1 = data.get("col1") or target or "variable 1"
        v2 = data.get("col2") or group or "variable 2"
        r_val = data.get("r", data.get("rho", data.get("correlation")))
        r_txt = _fmt_number(r_val)
        if p < 0.05:
            qual = ""
            if r_val is not None:
                try:
                    qual = interpret_effect_size("r", float(r_val))
                except (TypeError, ValueError):
                    qual = ""
            effet_txt = f", effet={qual}" if qual else ""
            return (
                f"{check} Corrélation significative entre {_esc(v1)} et "
                f"{_esc(v2)} (r={_esc(r_txt)}, p={_esc(p_txt)}{effet_txt})"
            )
        return (
            f"{cross} Pas de corrélation significative entre {_esc(v1)} et "
            f"{_esc(v2)} (r={_esc(r_txt)}, p={_esc(p_txt)})"
        )

    if not target or not group:
        return None

    if p < 0.05:
        effect_name, effect_val = _resolve_effect_for_resume(data)
        effet_txt = ""
        if effect_name is not None and effect_val is not None:
            try:
                qual = interpret_effect_size(effect_name, float(effect_val))
                effet_txt = f", effet={qual}"
            except (TypeError, ValueError):
                effet_txt = ""
        return (
            f"{check} {_esc(target)} diffère significativement selon "
            f"{_esc(group)} ({_esc(test_name)}, p={_esc(p_txt)}{effet_txt})"
        )
    return (
        f"{cross} Aucune différence significative de {_esc(target)} selon "
        f"{_esc(group)} ({_esc(test_name)}, p={_esc(p_txt)})"
    )


def _html_en_resume(
    *,
    multi_entries: list[dict[str, Any]] | None,
    is_multi: bool,
    intent: dict[str, Any],
    analysis: dict[str, Any],
    test_result: dict[str, Any],
) -> str:
    """Section « En résumé » — 3 à 6 bullets actionnables avant l'annexe."""
    bullets: list[str] = []

    if is_multi and multi_entries:
        for entry in multi_entries:
            if len(bullets) >= 6:
                break
            if _is_descriptive_only_entry(entry):
                continue
            bullet = _resume_bullet_from_test(
                test_result=_resolve_entry_test_result(entry),
                intent=_as_dict(entry.get("intent")),
                action_executed=entry.get("action_executed"),
            )
            if bullet:
                bullets.append(bullet)
    else:
        inference = _as_dict(analysis.get("inference"))
        bullet = _resume_bullet_from_test(
            test_result=test_result,
            intent=intent,
            action_executed=inference.get("action_executed"),
        )
        if bullet:
            bullets.append(bullet)

    if not bullets:
        return ""

    # Conserver entre 3 et 6 si possible ; sinon afficher ce qui est disponible.
    bullets = bullets[:6]
    items = "\n".join(
        f'<li style="padding:8px 0; border-bottom:1px solid '
        f'rgba(255,255,255,0.06); font-size:13px; color:#E8E8E8; '
        f'line-height:1.6;">{b}</li>'
        for b in bullets
    )
    return f"""
  <section class="section">
    <h2>En résumé</h2>
    <ul style="list-style:none; padding:0;">
      {items}
    </ul>
  </section>
"""

def _html_acm_section(acm_result: dict[str, Any], table_counter: list[int]) -> str:
    """Génère la section ACM du rapport PDF."""
    if not acm_result or acm_result.get("status") != "ok":
        return ""
    
    n_rows = acm_result.get("n_rows", "—")
    n_variables = acm_result.get("n_variables", "—")
    variables = acm_result.get("variables", [])
    inertia_pct = acm_result.get("inertia_pct", [])
    cumulative_inertia = acm_result.get("cumulative_inertia", [])
    interpretation_note = acm_result.get("interpretation_note", "")
    plan_factoriel = acm_result.get("plan_factoriel")
    scree_plot = acm_result.get("scree_plot")
    top_contributions = acm_result.get("top_contributions_dim1", [])
    
    # Tableau des valeurs propres
    eigenvalues_rows = ""
    for i, (inertia, cumul) in enumerate(zip(inertia_pct, cumulative_inertia), start=1):
        eigenvalues_rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="num">{_fmt_number(inertia, 2)}%</td>
          <td class="num">{_fmt_number(cumul, 2)}%</td>
        </tr>
        """
    
    eigenvalues_caption = _next_table_caption(
        table_counter,
        "Valeurs propres et inertie expliquée par dimension — ACM"
    )
    eigenvalues_table = f"""
    {eigenvalues_caption}
    <table class="apa">
      <thead>
        <tr>
          <th class="num">Dimension</th>
          <th class="num">% d'inertie</th>
          <th class="num">% cumulé</th>
        </tr>
      </thead>
      <tbody>
        {eigenvalues_rows}
      </tbody>
    </table>
    """
    
    # Tableau des contributions
    contrib_rows = ""
    for contrib in top_contributions[:10]:
        modalite = contrib.get("modalite", "—")
        contribution = contrib.get("contribution", 0)
        contrib_rows += f"""
        <tr>
          <td>{_esc(modalite)}</td>
          <td class="num">{_fmt_number(contribution * 100, 2)}%</td>
        </tr>
        """
    
    contrib_caption = _next_table_caption(
        table_counter,
        "Contributions des modalités à l'axe 1 — ACM"
    )
    contrib_table = f"""
    {contrib_caption}
    <table class="apa">
      <thead>
        <tr>
          <th>Modalité</th>
          <th class="num">Contribution (%)</th>
        </tr>
      </thead>
      <tbody>
        {contrib_rows}
      </tbody>
    </table>
    """
    
    # Graphiques
    plan_factoriel_img = ""
    if plan_factoriel:
        plan_factoriel_img = f"""
    <div style="text-align:center; margin:16px 0;">
      <img src="data:image/png;base64,{plan_factoriel}" 
           alt="Plan factoriel ACM" 
           style="max-width:100%; height:auto; border-radius:8px;"/>
    </div>
        """
    
    scree_plot_img = ""
    if scree_plot:
        scree_plot_img = f"""
    <div style="text-align:center; margin:16px 0;">
      <img src="data:image/png;base64,{scree_plot}" 
           alt="Scree plot ACM" 
           style="max-width:100%; height:auto; border-radius:8px;"/>
    </div>
        """
    
    return f"""
  <section class="section">
    <h2>Analyse des Correspondances Multiples (ACM)</h2>
    <p class="muted">
      L'ACM explore les structures d'association entre {n_variables} variables catégorielles
      sur {n_rows} observations.
    </p>
    
    <h3>Note d'interprétation</h3>
    <div class="card">
      <p>{_esc(interpretation_note)}</p>
    </div>
    
    <h3>Plan factoriel</h3>
    {plan_factoriel_img}
    
    <h3>Valeurs propres</h3>
    {scree_plot_img}
    {eigenvalues_table}
    
    <h3>Contributions à l'axe 1</h3>
    {contrib_table}
  </section>
"""

def _build_html(analysis_result: dict[str, Any], theme: str = "dark") -> str:
    intent, analysis, interpretation = _unpack(analysis_result)

    diagnosis = _as_dict(analysis.get("diagnosis"))
    inference = _as_dict(analysis.get("inference"))
    test_result = _as_dict(inference.get("result"))
    confidence = _as_dict(analysis.get("confidence_score"))
    interp_main = _as_dict(interpretation.get("interpretation_principale"))

    # Logs diagnostic ACM
    print(f"ACM DEBUG - analysis_result: {len(analysis_result)} clés", flush=True)
    print(f"ACM DEBUG - analysis: {len(analysis)} clés", flush=True)
    print(f"ACM DEBUG - test_result: {len(test_result)} clés", flush=True)
    print(f"ACM DEBUG - 'acm' in test_result: {'acm' in test_result}", flush=True)
    print(f"ACM DEBUG - 'acm' in analysis: {'acm' in analysis}", flush=True)
    print(f"ACM DEBUG - 'acm' in analysis_result: {'acm' in analysis_result}", flush=True)
    
    # Vérifier chemin multi-analyses
    if "analyses" in analysis_result:
        print(f"ACM DEBUG - analyses found, count: {len(analysis_result['analyses'])}", flush=True)
        for i, a in enumerate(analysis_result['analyses'][:3]):  # Vérifier les 3 premiers
            print(f"ACM DEBUG - analysis[{i}]: {len(a)} clés", flush=True)
            if 'result' in a:
                print(f"ACM DEBUG - analysis[{i}]['result']: {len(a['result'])} clés", flush=True)
                print(f"ACM DEBUG - 'acm' in analysis[{i}]['result']: {'acm' in a['result']}", flush=True)

    # Limiter les graphiques pour éviter crash mémoire WeasyPrint
    charts_source = "charts"
    if theme == "light" and analysis.get("charts_light"):
        charts_source = "charts_light"
    
    all_charts = analysis.get(charts_source, {})
    if all_charts:
        limited_charts = _select_charts(all_charts)
        analysis[charts_source] = limited_charts

    # Compteur APA partagé pour toute la génération du rapport.
    table_counter: list[int] = [0]

    filename = (
        analysis.get("filename")
        or analysis_result.get("filename")
        or "fichier inconnu"
    )
    file_hash = analysis_result.get("file_hash") or analysis.get("file_hash")
    engine_versions = _engine_versions_line()
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    score = confidence.get("score_global")
    niveau = confidence.get("niveau") or "—"
    score_display = f"{_fmt_number(score, 1)} / 100 — {_esc(niveau)}" if score is not None else f"— — {_esc(niveau)}"

    n_rows = diagnosis.get("n_rows", "—")
    n_cols = diagnosis.get("n_cols", "—")
    dataset_type = diagnosis.get("dataset_type") or "—"

    justification = _selection_justification(analysis)
    # Préférer le nom du test statistique ; sinon le libellé de l'action.
    raw_test = test_result.get("test")
    if raw_test:
        test_name = str(raw_test)
    else:
        test_name = _format_action_executed(inference.get("action_executed"))

    # Section 1 d'abord (ordre de numérotation APA = ordre d'apparition).
    variables_table_html = _html_variables_table(diagnosis, table_counter)
    missing_html = _html_missing(diagnosis, table_counter)
    descriptive_html = _html_descriptive_stats(diagnosis, table_counter)

    multi_entries = _collect_multi_tests(analysis_result)
    is_multi = (
        analysis_result.get("mode") == "auto" or len(multi_entries) > 1
    )
    if is_multi and multi_entries:
        section2_html = _html_multi_section2(
            multi_entries,
            table_counter,
            filename=str(filename),
            theme=theme,
        )
    else:
        section2_html = _html_single_section2(
            analysis,
            test_result,
            test_name,
            justification,
            table_counter,
            intent=intent,
            filename=str(filename),
            action_executed=inference.get("action_executed"),
            theme=theme,
        )

    # Interprétation (trois niveaux + résumé) — porte sur l'ensemble en mode auto.
    if interpretation.get("llm_available") is False:
        reason = interpretation.get("reason") or "Interprétation textuelle indisponible."
        niveau_technique = reason
        niveau_analytique = reason
        niveau_decisionnel = reason
        resume = reason
    else:
        niveau_technique = interp_main.get("niveau_technique") or "—"
        niveau_analytique = interp_main.get("niveau_analytique") or "—"
        niveau_decisionnel = interp_main.get("niveau_decisionnel") or "—"
        resume = interpretation.get("resume_executif") or "—"

    vigilance = _as_list(confidence.get("points_de_vigilance"))
    if not vigilance:
        # Complément éventuel depuis limites LLM
        vigilance = _as_list(interpretation.get("limites_et_reserves"))
    if not vigilance:
        vigilance = ["Aucun point de vigilance particulier identifié."]

    # Conditions : fusionner les diagnostics de chaque run en mode multi.
    conditions: list[tuple[str, str, str | None]]
    if is_multi and multi_entries:
        conditions = []
        seen: set[str] = set()
        # Normalité / Shapiro depuis l'analyse principale (souvent absente des sous-runs).
        for label, statut, detail in _conditions_application(
            {
                "normality": analysis.get("normality"),
                "diagnosis": diagnosis,
                "inference": {},
                "confidence_score": {},
            }
        ):
            if label.startswith("Normalité de"):
                key = f"{label}|{statut}|{detail or ''}"
                if key not in seen:
                    seen.add(key)
                    conditions.append((label, statut, detail))
        for entry in multi_entries:
            entry_analysis = _as_dict(entry.get("analysis"))
            if not entry_analysis:
                # Reconstruire un squelette minimal pour les conditions du test.
                entry_analysis = {
                    "inference": {"result": _as_dict(entry.get("result"))},
                    "normality": _as_dict(analysis.get("normality")),
                    "diagnosis": diagnosis,
                    "confidence_score": {},
                }
            else:
                # Enrichir avec la normalité globale si le sous-run n'en a pas.
                if not entry_analysis.get("normality") and analysis.get("normality"):
                    entry_analysis = {
                        **entry_analysis,
                        "normality": analysis.get("normality"),
                        "diagnosis": entry_analysis.get("diagnosis") or diagnosis,
                    }
            for label, statut, detail in _conditions_application(entry_analysis):
                key = f"{label}|{statut}|{detail or ''}"
                if key not in seen:
                    seen.add(key)
                    conditions.append((label, statut, detail))
        if not conditions:
            conditions = _conditions_application(analysis)
    else:
        conditions = _conditions_application(analysis)

    r_script = analysis.get("r_script") or "# Script R non disponible."
    stata_script = analysis.get("stata_script")

    vigilance_html = "\n".join(f"<li>{_esc(item)}</li>" for item in vigilance)
    condition_items: list[str] = []
    for label, statut, detail in conditions:
        item = (
            f"<li>{_esc(label)} — "
            f"<span class='{_status_class(statut)}'>{_esc(statut)}</span>"
        )
        if detail:
            item += (
                f"<br/><span class='muted' style='font-size:12px;'>"
                f"{_esc(detail)}</span>"
            )
        item += "</li>"
        condition_items.append(item)
    conditions_html = "\n".join(condition_items)

    en_resume_html = _html_en_resume(
        multi_entries=multi_entries if is_multi else None,
        is_multi=bool(is_multi and multi_entries),
        intent=intent,
        analysis=analysis,
        test_result=test_result,
    )

    scientific_defense_html = _html_scientific_defense(
        analysis_result,
        analysis,
        interpretation,
        multi_entries if is_multi else [],
        bool(is_multi and multi_entries),
    )

    # Skeptic Engine : alerte visible uniquement si le flag est explicitement True.
    skeptic_alert_html = ""
    if interpretation.get("skeptic_engine_alert") is True:
        skeptic_msg = interpretation.get("skeptic_engine_message") or (
            "Incohérence potentielle détectée entre conclusions et p-values — "
            "vérification recommandée."
        )
        skeptic_alert_html = f"""
    <div style="background:#1C1C26; border-left:3px solid #F39C12; padding:16px; border-radius:8px; margin:16px 0;">
      <p style="color:#F39C12; font-size:11px; letter-spacing:0.08em; margin:0 0 8px 0; font-weight:600;">
        ⚠ SKEPTIC ENGINE — VÉRIFICATION RECOMMANDÉE
      </p>
      <p style="color:#9A9AA8; font-size:12px; line-height:1.6; margin:0;">
        {_esc(skeptic_msg)}
      </p>
    </div>
"""

    stata_block = ""
    if stata_script:
        stata_block = f"""
        <h3>Code Stata</h3>
        <pre class="code">{_esc(stata_script)}</pre>
        """
    else:
        stata_block = "<h3>Code Stata</h3><p class='muted'>Script Stata non disponible pour cette analyse.</p>"

    reference_keys = _collect_methodology_reference_keys(
        analysis_result, analysis, multi_entries if is_multi else []
    )
    bibliography_html = _html_methodology_bibliography(reference_keys)

    python_script = generate_python_colab_script(
        analysis_result,
        analysis,
        intent,
        multi_entries if is_multi else [],
        bool(is_multi and multi_entries),
        str(filename),
    )
    python_annex_html = _html_python_annex(python_script)

    audit_trail_raw = (
        analysis_result.get("audit_trail")
        or analysis.get("audit_trail")
        or []
    )
    audit_trail_html = _html_audit_trail(
        audit_trail_raw if isinstance(audit_trail_raw, list) else []
    )

    file_hash_html = ""
    if file_hash:
        file_hash_html = f"""
    <p style="color:#555563; font-size:9px; font-family:Courier New; text-align:center; margin-top:4px; word-break:break-all;">
      SHA256 : {_esc(file_hash)}
    </p>"""

    html_document = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <title>QUANTA — Rapport d'analyse</title>
  <style>{_css()}</style>
</head>
<body>

  <!-- PAGE DE GARDE -->
  <section class="cover">
    <h1>QUANTA</h1>
    <p class="subtitle">Rapport d'Analyse Statistique</p>
    <div class="cover-meta">
      <p><span class="muted">Fichier analysé</span><br/><strong>{_esc(filename)}</strong></p>
      <p><span class="muted">Date de génération</span><br/>{_esc(generated_at)}</p>
      <p style="color:#555563; font-size:10px; font-family:Courier New; text-align:center; margin-top:4px;">
        {_esc(engine_versions)}
      </p>
      {file_hash_html}
    </div>
    <div class="score-badge">
      <div class="label">Score de confiance</div>
      <div class="value">{score_display}</div>
    </div>
    <p style="color:#555563; font-size:10px; font-style:italic; text-align:center; margin-top:8px;">
      Le score reflète les propriétés statistiques mesurables. Il n'évalue pas la qualité du
      design d'étude ni la validité externe.
    </p>
  </section>

  <!-- SECTION 1 -->
  <section class="section first-content">
    <h2>1. Présentation des données</h2>
    <table class="kv">
      <tr><td>Nombre d'observations</td><td class="mono">{_esc(n_rows)}</td></tr>
      <tr><td>Nombre de variables</td><td class="mono">{_esc(n_cols)}</td></tr>
      <tr><td>Type de dataset</td><td>{_esc(dataset_type)}</td></tr>
    </table>
    {_html_duplicates(diagnosis)}
    <h3>Variables</h3>
    {variables_table_html}
    {missing_html}
    {descriptive_html}
  </section>

  <!-- SECTION 2 -->
  <section class="section">
    <h2>2. Analyse statistique</h2>
    {section2_html}
  </section>

  <!-- SECTION ACM -->
  {_html_acm_section(test_result.get("acm") if test_result else None, table_counter)}

  <!-- SECTION 3 -->
  <section class="section">
    <h2>3. Interprétation</h2>
    <h3>Niveau technique</h3>
    <div class="card"><p>{_esc(niveau_technique)}</p></div>
    <h3>Niveau analytique</h3>
    <div class="card"><p>{_esc(niveau_analytique)}</p></div>
    <h3>Niveau décisionnel</h3>
    <div class="card"><p>{_esc(niveau_decisionnel)}</p></div>
    {skeptic_alert_html}
    <h3>Résumé exécutif</h3>
    <div class="card"><p>{_esc(resume)}</p></div>
  </section>

  <!-- SECTION 4 -->
  <section class="section">
    <h2>4. Limites et réserves</h2>
    <h3>Points de vigilance du score de confiance</h3>
    <ul class="plain">
      {vigilance_html}
    </ul>
    <h3>Conditions d'application</h3>
    <ul class="plain">
      {conditions_html}
    </ul>
    <p class="footnote">
      Les conditions listées ci-dessus reflètent les diagnostics automatiques
      produits par le pipeline compute/sélecteur. Elles ne remplacent pas
      un jugement statistique expert sur le plan d'analyse.
    </p>
  </section>

  {en_resume_html}

  {scientific_defense_html}

  <!-- ANNEXE -->
  <section class="section">
    <h2>Annexe A — Scripts reproductibles</h2>
    <h3>Code R</h3>
    <pre class="code">{_esc(r_script)}</pre>
    {stata_block}
  </section>

  {bibliography_html}

  {python_annex_html}

  {audit_trail_html}

</body>
</html>
"""
    return _apply_theme(html_document, theme)


def _apply_theme(html_document: str, theme: str) -> str:
    """
    Applique le thème light/académique sur le HTML complet (CSS + styles inline).

    Conservés : or (#C9A84C) titres, cyan (#00D4FF) accents, vert puissance.
    """
    if (theme or "dark").strip().lower() != "light":
        return html_document

    replacements: tuple[tuple[str, str], ...] = (
        ("#0A0A0F", "#FFFFFF"),
        ("#0D0D0D", "#F5F5F5"),
        ("#13131A", "#F8F9FA"),
        ("#1C1C26", "#F0F0F0"),
        ("#E8E8E8", "#1A1A1A"),
        ("#9A9AA8", "#555555"),
        ("#8A8A96", "#555555"),
        ("#555563", "#888888"),
        ("rgba(255,255,255,0.08)", "#E0E0E0"),
        ("rgba(255,255,255,0.06)", "#E0E0E0"),
        ("rgba(255,255,255,0.05)", "#E0E0E0"),
        ("rgba(255,255,255,0.12)", "#E0E0E0"),
    )
    out = html_document
    for old, new in replacements:
        out = out.replace(old, new)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# API PUBLIQUE
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pdf_report(
    analysis_result: dict[str, Any],
    theme: str = "dark",
) -> bytes | None:
    """
    Génère le PDF de rapport QUANTA.

    theme : "dark" (défaut) ou "light" (rapport académique clair).

    Retourne les bytes du PDF, ou None en cas d'erreur (jamais d'exception
    vers l'appelant).
    """
    try:
        if not isinstance(analysis_result, dict):
            logger.error("PDF generation failed: analysis_result is not a dict")
            return None
        theme_norm = (theme or "dark").strip().lower()
        if theme_norm not in {"dark", "light"}:
            theme_norm = "dark"
        html_document = _build_html(analysis_result, theme=theme_norm)
        HTML = _get_weasyprint()
        if HTML is None:
            print("WeasyPrint indisponible - fallback vers fpdf2")
            return _generate_fallback_pdf(analysis_result)
        pdf_buffer = io.BytesIO()
        HTML(string=html_document, base_url=".").write_pdf(target=pdf_buffer)
        pdf_bytes = pdf_buffer.getvalue()
        if not pdf_bytes:
            logger.error("PDF generation failed: WeasyPrint returned empty PDF")
            return _generate_fallback_pdf(analysis_result)
        return pdf_bytes
    except Exception as e:
        print(f"ERREUR PDF WeasyPrint: {e}")
        import traceback
        traceback.print_exc()
        logger.error(
            f"PDF generation failed: {type(e).__name__}: {str(e)}",
            extra={"analysis_keys": list(analysis_result.keys()) if isinstance(analysis_result, dict) else None}
        )
        return _generate_fallback_pdf(analysis_result)


def _generate_fallback_pdf(analysis_result: dict[str, Any]) -> bytes:
    """PDF minimal sans WeasyPrint si celui-ci échoue."""
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError:
        print("fpdf2 non disponible - fallback impossible")
        return b""
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(201, 168, 76)
    pdf.cell(0, 20, "QUANTA", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 10, "Rapport d Analyse Statistique",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    
    # Score de confiance
    confidence = (analysis_result.get("analysis", {})
                 .get("confidence_score", {}))
    score = confidence.get("score_global", 0)
    niveau = confidence.get("niveau", "")
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Score de confiance : {int(score)}/100 - {niveau}",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    
    # Résumé interprétation
    interp = analysis_result.get("interpretation", {})
    resume = interp.get("resume_executif", "")
    if resume:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 7, resume[:500],
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    return bytes(pdf.output())


def _sanitize_for_fpdf(text: str) -> str:
    """Remplace les caractères Unicode non supportés par la police 
    core fpdf2 (helvetica) par des équivalents ASCII, pour garantir 
    que ce fallback ne plante jamais."""
    if not isinstance(text, str):
        return text
    replacements = {
        "→": "->",
        "←": "<-",
        "–": "-",
        "—": "-",
        "'": "'",
        "'": "'",
        """: '"',
        """: '"',
        "…": "...",
        "×": "x",
        "≥": ">=",
        "≤": "<=",
        "≠": "!=",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Filet de sécurité final : supprime tout caractère encore hors 
    # Latin-1 plutôt que de laisser fpdf2 planter dessus.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_lightweight_pdf(analysis_result: dict[str, Any], theme: str = "dark") -> bytes | None:
    """
    PDF léger avec fpdf2 (zero WeasyPrint) pour les datasets volumineux.
    Texte uniquement, pas de graphiques.
    """
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError:
        print("fpdf2 non disponible - PDF léger impossible")
        return None
    
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Page de garde simple
        pdf.set_font("Helvetica", "B", 24)
        pdf.set_text_color(201, 168, 76)
        pdf.cell(0, 20, _sanitize_for_fpdf("QUANTA"), align="C",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 10, _sanitize_for_fpdf("Rapport d Analyse Statistique"),
                align="C", new_x=XPos.LMARGIN, 
                new_y=YPos.NEXT)
        pdf.ln(10)
        
        # Score confiance
        confidence = (analysis_result
                     .get("analysis", {})
                     .get("confidence_score", {}))
        score = confidence.get("score_global", 0)
        niveau = confidence.get("niveau", "")
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10,
            _sanitize_for_fpdf(f"Score de confiance : {int(score)}/100 - {niveau}"),
            align="C", new_x=XPos.LMARGIN, 
            new_y=YPos.NEXT)
        pdf.ln(10)
        
        # Résumé exécutif
        interp = analysis_result.get("interpretation", {})
        resume = interp.get("resume_executif", "")
        if resume:
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, _sanitize_for_fpdf("Resume executif"),
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, _sanitize_for_fpdf(resume))  # Plus de limite de caractères
            pdf.ln(5)
        
        # Interprétation 3 niveaux
        interp_principale = interp.get("interpretation_principale", {})
        for niveau_name, niveau_key in [
            ("Niveau technique", "niveau_technique"),
            ("Niveau analytique", "niveau_analytique"),
            ("Niveau decisionnel", "niveau_decisionnel")
        ]:
            texte = interp_principale.get(niveau_key, "")
            if texte:
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(0, 100, 150)
                pdf.cell(0, 8, _sanitize_for_fpdf(niveau_name),
                        new_x=XPos.LMARGIN, 
                        new_y=YPos.NEXT)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(50, 50, 50)
                pdf.multi_cell(0, 5, _sanitize_for_fpdf(texte))  # Plus de limite de caractères
                pdf.ln(4)
        
        # En résumé
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(201, 168, 76)
        pdf.cell(0, 10, _sanitize_for_fpdf("En resume"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 7,
            _sanitize_for_fpdf("Note : rapport allege (dataset volumineux)."),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)
        
        # Résultats des tests
        tests = analysis_result.get("analysis", {}).get("tests", [])
        if tests:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(201, 168, 76)
            pdf.cell(0, 10, _sanitize_for_fpdf("Resultats des tests"),
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)
            
            for test in tests[:10]:  # Limiter à 10 tests pour éviter PDF trop long
                test_name = test.get("test_name", "Test inconnu")
                p_value = test.get("p_value", "N/A")
                conclusion = test.get("conclusion", "")
                
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 6, _sanitize_for_fpdf(test_name),
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(50, 50, 50)
                pdf.cell(0, 5, _sanitize_for_fpdf(f"p-value: {p_value}"),
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                
                if conclusion:
                    pdf.multi_cell(0, 5, _sanitize_for_fpdf(conclusion[:300]))
                pdf.ln(3)
        
        return bytes(pdf.output())
    
    except Exception as e:
        print(f"Erreur PDF léger: {e}")
        import traceback
        traceback.print_exc()
        return None
