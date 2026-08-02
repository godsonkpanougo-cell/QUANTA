"""
QUANTA — report_generator.py

Génère un rapport PDF professionnel à partir du dict retourné par
brain.analyze_with_brain (intent + analysis + interpretation).

Utilise fpdf2 (librairie Python pure, zéro dépendance système) au lieu
de WeasyPrint pour éviter les problèmes de dépendances GTK/Pango/Cairo
sur Railway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF, XPos, YPos


class QuantaPDF(FPDF):
    def __init__(self, theme="dark"):
        super().__init__()
        self.theme = theme
        if theme == "dark":
            self.bg_color = (10, 10, 15)
            self.text_color = (232, 232, 232)
            self.accent_gold = (201, 168, 76)
            self.accent_cyan = (0, 212, 255)
            self.surface_color = (19, 19, 26)
            self.muted_color = (85, 85, 99)
        else:
            self.bg_color = (255, 255, 255)
            self.text_color = (26, 26, 26)
            self.accent_gold = (180, 140, 50)
            self.accent_cyan = (0, 150, 200)
            self.surface_color = (248, 249, 250)
            self.muted_color = (100, 100, 110)

    def header(self):
        if self.page_no() > 1:
            self.set_fill_color(*self.bg_color)
            self.rect(0, 0, 210, 297, 'F')
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*self.muted_color)
            self.cell(0, 10,
                f"QUANTA — Rapport d'analyse statistique · page {self.page_no()}",
                align="C")
            self.ln(5)

    def footer(self):
        pass

    def add_page_with_bg(self):
        self.add_page()
        self.set_fill_color(*self.bg_color)
        self.rect(0, 0, 210, 297, 'F')


def generate_pdf_report(
    analysis_result: dict,
    theme: str = "dark"
) -> bytes | None:
    try:
        pdf = QuantaPDF(theme=theme)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page_with_bg()

        # ── PAGE DE GARDE ──────────────────────────────
        pdf.set_fill_color(*pdf.bg_color)
        pdf.rect(0, 0, 210, 297, 'F')

        # Titre QUANTA
        pdf.set_y(80)
        pdf.set_font("Helvetica", "B", 36)
        pdf.set_text_color(*pdf.accent_gold)
        pdf.cell(0, 20, "QUANTA", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Sous-titre
        pdf.set_font("Helvetica", "", 16)
        pdf.set_text_color(*pdf.text_color)
        pdf.cell(0, 10, "Rapport d'Analyse Statistique",
                 align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(15)

        # Ligne séparatrice or
        pdf.set_draw_color(*pdf.accent_gold)
        pdf.set_line_width(0.5)
        pdf.line(40, pdf.get_y(), 170, pdf.get_y())
        pdf.ln(10)

        # Métadonnées
        filename = (analysis_result.get("analysis", {})
                   .get("filename", "inconnu"))
        date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*pdf.muted_color)
        pdf.cell(0, 7, "Fichier analysé", align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*pdf.text_color)
        pdf.cell(0, 8, filename, align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*pdf.muted_color)
        pdf.cell(0, 7, "Date de génération", align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*pdf.text_color)
        pdf.cell(0, 8, date_str, align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(10)

        # Score de confiance
        confidence = (analysis_result.get("analysis", {})
                     .get("confidence_score", {}))
        score = confidence.get("score_global", 0)
        niveau = confidence.get("niveau", "—")
        
        pdf.set_fill_color(*pdf.surface_color)
        pdf.set_draw_color(*pdf.accent_gold)
        pdf.set_line_width(0.3)
        pdf.rect(55, pdf.get_y(), 100, 25, 'FD')
        pdf.set_y(pdf.get_y() + 3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*pdf.muted_color)
        pdf.cell(0, 5, "SCORE DE CONFIANCE", align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(*pdf.accent_gold)
        pdf.cell(0, 12, f"{int(score)} / 100 — {niveau}",
                 align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)

        # Versions
        import sys
        try:
            import scipy
            scipy_ver = scipy.__version__
        except:
            scipy_ver = "?"
        try:
            import statsmodels
            sm_ver = statsmodels.__version__
        except:
            sm_ver = "?"
        
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*pdf.muted_color)
        py_ver = sys.version.split()[0]
        pdf.cell(0, 5,
            f"QUANTA v0.1.0 · Python {py_ver} · scipy {scipy_ver} · statsmodels {sm_ver}",
            align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # SHA256 si disponible
        file_hash = (analysis_result.get("analysis", {})
                    .get("file_hash", ""))
        if file_hash:
            pdf.set_font("Helvetica", "I", 6)
            pdf.cell(0, 5, f"SHA256: {file_hash}",
                     align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ── SECTION 1 — PRÉSENTATION DES DONNÉES ───────
        pdf.add_page_with_bg()
        _section_title(pdf, "1. Présentation des données")
        
        diag = (analysis_result.get("analysis", {})
               .get("diagnosis", {}))
        
        _key_value(pdf, "Nombre d'observations",
                   str(diag.get("n_rows", "—")))
        _key_value(pdf, "Nombre de variables",
                   str(diag.get("n_cols", "—")))
        _key_value(pdf, "Type de dataset",
                   diag.get("dataset_type", "—"))
        
        n_dupl = diag.get("n_duplicates", 0)
        dupl_text = ("Aucun doublon détecté." if n_dupl == 0
                    else f"{n_dupl} doublon(s) détecté(s).")
        _key_value(pdf, "Doublons", dupl_text)

        n_missing = diag.get("n_missing", 0)
        missing_text = ("Aucune valeur manquante." if n_missing == 0
                       else f"{n_missing} valeur(s) manquante(s).")
        _key_value(pdf, "Valeurs manquantes", missing_text)

        pdf.ln(5)

        # Tableau des variables
        _subsection_title(pdf, "Variables")
        numeric_cols = diag.get("numeric_cols", [])
        cat_cols = diag.get("cat_cols", [])
        
        _table_header(pdf, ["Variable", "Type"], [120, 60])
        for col in numeric_cols:
            _table_row(pdf, [col, "Numérique"], [120, 60])
        for col in cat_cols:
            _table_row(pdf, [col, "Catégorielle"], [120, 60])

        # ── SECTION 2 — ANALYSE STATISTIQUE ────────────
        pdf.add_page_with_bg()
        _section_title(pdf, "2. Analyse statistique")

        interp = analysis_result.get("interpretation", {})
        analyses = analysis_result.get("analyses", [])
        
        if not analyses:
            main_analysis = analysis_result.get("analysis", {})
            inference = main_analysis.get("inference", {})
            analyses = [inference] if inference else []

        for i, analysis in enumerate(analyses, 1):
            result = analysis.get("result", {})
            if not result:
                continue
            
            action = analysis.get("action_executed", "")
            test_name = _format_action(action)
            
            _subsection_title(pdf, f"{i}. {test_name}")
            
            # Hypothèses
            h0, h1 = _get_hypotheses(action, result)
            if h0 and h1:
                pdf.set_fill_color(*pdf.surface_color)
                y_start = pdf.get_y()
                pdf.rect(15, y_start, 180, 20, 'F')
                pdf.set_y(y_start + 2)
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(*pdf.muted_color)
                pdf.cell(0, 4, "HYPOTHÈSES",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(*pdf.text_color)
                pdf.cell(0, 5, f"H\u2080 : {h0}",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.cell(0, 5, f"H\u2081 : {h1}",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(3)

            # Résultats chiffrés
            stat = result.get("statistic")
            pval = result.get("p_value")
            df_val = result.get("df") or result.get("df_between")
            effect = result.get("effect_size")
            effect_name = result.get("effect_size_name", "")
            power = result.get("power")

            _key_value(pdf, "Statistique de test",
                      f"{stat:.4f}" if stat is not None else "—")
            _key_value(pdf, "p-value",
                      _fmt_pvalue(pval) if pval is not None else "—")
            _key_value(pdf, "Degrés de liberté",
                      str(df_val) if df_val is not None else "—")
            
            if effect is not None:
                interp_eff = _interpret_effect(effect_name, effect)
                _key_value(pdf, effect_name or "Taille d'effet",
                          f"{effect:.4f} — {interp_eff}")
            
            if power is not None:
                power_interp = _interpret_power(power)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*pdf.text_color)
                _key_value(pdf, "Puissance (1-β)",
                          f"{power:.3f} ({power_interp})")

            # Décision statistique
            if pval is not None:
                pdf.set_font("Helvetica", "B", 9)
                if pval < 0.05:
                    pdf.set_text_color(*pdf.accent_cyan)
                    decision = f"Rejet de H\u2080 au seuil \u03b1 = 0,05."
                else:
                    pdf.set_text_color(*pdf.text_color)
                    decision = f"Non-rejet de H\u2080 au seuil \u03b1 = 0,05."
                pdf.cell(0, 7, f"Décision statistique : {decision}",
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*pdf.text_color)
            pdf.ln(5)

        # ── SECTION 3 — INTERPRÉTATION ──────────────────
        if interp.get("llm_available"):
            pdf.add_page_with_bg()
            _section_title(pdf, "3. Interprétation")
            
            interp_principale = interp.get(
                "interpretation_principale", {})
            
            _subsection_title(pdf, "Niveau technique")
            _body_text(pdf,
                interp_principale.get("niveau_technique", ""))
            
            _subsection_title(pdf, "Niveau analytique")
            _body_text(pdf,
                interp_principale.get("niveau_analytique", ""))
            
            _subsection_title(pdf, "Niveau décisionnel")
            _body_text(pdf,
                interp_principale.get("niveau_decisionnel", ""))
            
            if interp.get("resume_executif"):
                _subsection_title(pdf, "Résumé exécutif")
                _body_text(pdf, interp["resume_executif"])

            # Skeptic Engine
            if interp.get("skeptic_engine_alert"):
                pdf.ln(5)
                pdf.set_fill_color(28, 28, 38)
                pdf.set_draw_color(243, 156, 18)
                pdf.set_line_width(1)
                y = pdf.get_y()
                pdf.rect(15, y, 180, 20, 'FD')
                pdf.set_y(y + 3)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(243, 156, 18)
                pdf.cell(0, 5,
                    "⚠ SKEPTIC ENGINE — VÉRIFICATION RECOMMANDÉE",
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(*pdf.muted_color)
                pdf.cell(0, 5,
                    interp.get("skeptic_engine_message", ""),
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*pdf.text_color)
                pdf.ln(5)

        # ── SECTION 4 — LIMITES ET RÉSERVES ────────────
        pdf.add_page_with_bg()
        _section_title(pdf, "4. Limites et réserves")
        
        confidence = (analysis_result.get("analysis", {})
                     .get("confidence_score", {}))
        points = confidence.get("points_de_vigilance", [])
        
        _subsection_title(pdf, "Points de vigilance")
        if points:
            for point in points:
                _bullet(pdf, point)
        else:
            _body_text(pdf,
                "Aucun point de vigilance particulier identifié.")

        # ── EN RÉSUMÉ ───────────────────────────────────
        pdf.add_page_with_bg()
        _section_title(pdf, "En résumé")
        
        analyses_list = analysis_result.get("analyses", [])
        if not analyses_list:
            main_analysis = analysis_result.get("analysis", {})
            inference = main_analysis.get("inference", {})
            analyses_list = [inference] if inference else []

        for analysis in analyses_list:
            result = analysis.get("result", {})
            if not result:
                continue
            action = analysis.get("action_executed", "")
            pval = result.get("p_value")
            if pval is None:
                continue
            target = result.get("target_col", "")
            group = result.get("group_col", "")
            test_name = _format_action(action)
            effect = result.get("effect_size", 0) or 0
            effect_name = result.get("effect_size_name", "")
            effect_interp = (_interpret_effect(effect_name, effect)
                           if effect else "")
            
            if pval < 0.05:
                marker = "✓"
                pdf.set_text_color(*pdf.accent_gold)
                text = (f"{marker} Différence significative de {target} "
                       f"selon {group} ({test_name}, "
                       f"p={_fmt_pvalue(pval)}, effet {effect_interp})")
            else:
                marker = "✗"
                pdf.set_text_color(*pdf.muted_color)
                text = (f"{marker} Pas de différence significative de "
                       f"{target} selon {group} "
                       f"({test_name}, p={_fmt_pvalue(pval)})")
            
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 7, text,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*pdf.muted_color)
            pdf.set_line_width(0.2)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)
        
        pdf.set_text_color(*pdf.text_color)

        # ── ANNEXE A — SCRIPT R ─────────────────────────
        r_script = (analysis_result.get("analysis", {})
                   .get("inference", {})
                   .get("r_script", ""))
        if r_script:
            pdf.add_page_with_bg()
            _section_title(pdf, "Annexe A — Script R")
            pdf.set_font("Courier", "", 7)
            pdf.set_text_color(*pdf.muted_color)
            pdf.set_fill_color(13, 13, 13)
            pdf.rect(15, pdf.get_y(), 180,
                    min(len(r_script.split('\n')) * 4, 200), 'F')
            pdf.ln(2)
            for line in r_script.split('\n')[:60]:
                pdf.cell(0, 4, line[:100],
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*pdf.text_color)

        # ── ANNEXE C — BIBLIOGRAPHIE ────────────────────
        pdf.add_page_with_bg()
        _section_title(pdf, "Annexe C — Références méthodologiques")
        
        refs = {
            "Shapiro, S. S., & Wilk, M. B. (1965). An analysis of variance test for normality. Biometrika, 52(3-4), 591-611.",
            "Levene, H. (1960). Robust tests for equality of variances. Stanford University Press, 278-292.",
            "Cohen, J. (1988). Statistical power analysis for the behavioral sciences (2nd ed.). Lawrence Erlbaum.",
            "Kruskal, W. H., & Wallis, W. A. (1952). Use of ranks in one-criterion variance analysis. JASA, 47(260), 583-621.",
            "Pearson, K. (1900). On the criterion that a given system of deviations. Philosophical Magazine, 50(302), 157-175.",
            "Spearman, C. (1904). The proof and measurement of association between two things. Am. Journal of Psychology, 15(1), 72-101.",
            "Fisher, R. A. (1925). Statistical methods for research workers. Oliver & Boyd.",
            "Student. (1908). The probable error of a mean. Biometrika, 6(1), 1-25.",
        }
        
        for ref in refs:
            _bullet(pdf, ref)

        return bytes(pdf.output())

    except Exception as e:
        import traceback
        print(f"ERREUR PDF: {e}")
        traceback.print_exc()
        return None


# ── FONCTIONS UTILITAIRES ────────────────────────────────

def _section_title(pdf: "QuantaPDF", title: str):
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*pdf.accent_gold)
    pdf.cell(0, 10, title,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*pdf.accent_gold)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    pdf.set_text_color(*pdf.text_color)

def _subsection_title(pdf: "QuantaPDF", title: str):
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*pdf.accent_cyan)
    pdf.cell(0, 8, title,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*pdf.text_color)

def _key_value(pdf: "QuantaPDF", key: str, value: str):
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.muted_color)
    pdf.cell(70, 6, key,
             new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_text_color(*pdf.text_color)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, str(value),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

def _body_text(pdf: "QuantaPDF", text: str):
    if not text:
        return
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.text_color)
    pdf.set_fill_color(*pdf.surface_color)
    pdf.rect(15, pdf.get_y(), 180, 2, 'F')
    pdf.ln(2)
    pdf.multi_cell(0, 5, str(text),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

def _bullet(pdf: "QuantaPDF", text: str):
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.text_color)
    pdf.cell(8, 6, "•", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.multi_cell(0, 6, str(text),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)

def _table_header(pdf: "QuantaPDF",
                  cols: list, widths: list):
    pdf.set_fill_color(*pdf.surface_color)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*pdf.accent_gold)
    pdf.set_draw_color(*pdf.accent_gold)
    pdf.set_line_width(0.5)
    for col, w in zip(cols, widths):
        pdf.cell(w, 8, col, border="B",
                 new_x=XPos.RIGHT, new_y=YPos.TOP,
                 fill=True)
    pdf.ln(8)
    pdf.set_text_color(*pdf.text_color)

def _table_row(pdf: "QuantaPDF",
               cells: list, widths: list):
    pdf.set_font("Helvetica", "", 9)
    pdf.set_draw_color(*pdf.muted_color)
    pdf.set_line_width(0.1)
    for cell, w in zip(cells, widths):
        pdf.cell(w, 7, str(cell), border="B",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)

def _fmt_pvalue(p) -> str:
    if p is None:
        return "—"
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3f}"

def _format_action(action: str) -> str:
    mapping = {
        "compare_groups_2": "Comparaison de 2 groupes",
        "compare_groups_k": "Comparaison de k groupes",
        "correlation": "Analyse de corrélation",
        "regression_ols": "Régression linéaire (OLS)",
        "logistic_regression": "Régression logistique",
        "association": "Test d'association (Chi-deux)",
        "descriptive_only": "Analyse descriptive",
    }
    return mapping.get(action, action)

def _get_hypotheses(action: str, result: dict):
    target = result.get("target_col", "la variable")
    group = result.get("group_col", "les groupes")
    if "compare_groups" in action:
        return (
            f"La distribution de {target} est identique dans tous les groupes de {group}.",
            f"Au moins un groupe de {group} diffère des autres pour {target}."
        )
    if action == "correlation":
        return (
            f"Il n'existe pas de corrélation entre {target} et {group} (ρ = 0).",
            f"Une corrélation existe entre {target} et {group} (ρ ≠ 0)."
        )
    if action == "association":
        return (
            f"{target} et {group} sont indépendantes.",
            f"{target} et {group} sont associées."
        )
    return None, None

def _interpret_effect(name: str, value: float) -> str:
    abs_val = abs(value)
    if "d" in name.lower():
        if abs_val < 0.2: return "négligeable"
        if abs_val < 0.5: return "petit"
        if abs_val < 0.8: return "moyen"
        return "grand"
    if "cramér" in name.lower() or "v" in name.lower():
        if abs_val < 0.1: return "négligeable"
        if abs_val < 0.3: return "petit"
        if abs_val < 0.5: return "moyen"
        return "grand"
    # η², ε², r
    if abs_val < 0.01: return "négligeable"
    if abs_val < 0.06: return "petit"
    if abs_val < 0.14: return "moyen"
    return "grand"

def _interpret_power(power: float) -> str:
    if power < 0.5:
        return "insuffisante — risque élevé d'erreur de type II"
    if power < 0.8:
        return "modérée"
    return "adéquate"
