"""
QUANTA — acm_plot_fast.py (prototype optimisation plots ACM, goulot n°1)

Mesure prod (analyse 0090a4af, L2_tobit, 01/10) : `TIMING - ACM plots
generation: 55.301s` sur 61 s d'intent acm, alors que le fit MCA ne prend
que 4,99 s. Cause identifiée dans compute.py `_generate_acm_plot`
(~1825-1845) : UNE boucle par modalité fait ax.scatter + ax.annotate
(artistes matplotlib les plus coûteux) + un scan O(k) de préfixe, sur un
CPU Render bridé.

Design (prototype isolé, comme correlation_fast) :
  - comportement EXACTEMENT identique à la prod si le nombre de modalités
    est <= max_labeled (toutes étiquetées, aucune en gris) ;
  - sinon : top max_labeled modalités par contribution (dim1+dim2 du
    DataFrame prince) reçoivent scatter+annotate ; le reste est dessiné en
    UNE SEULE commande scatter vectorisée, en gris, sans étiquette ;
  - les DONNÉES (payload JSON modalities_coords) restent inchangées : seul
    le rendu figure est plafonné — changement visuel assumé, à valider par
    le directeur avant branchement dans compute.py.

Ce module est volontairement ISOLÉ : rien dans l'application ne l'importe
sans mandat.
"""
from __future__ import annotations

import base64
import io
from typing import Any

DEFAULT_MAX_LABELED = 25

# Palettes copiées exactement de compute._generate_acm_plot (non-régression visuelle)
_PALETTE: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#FFFFFF", "ax": "#F4F4F6", "text": "#1C1C22",
        "axis": "#6B6B76", "grid": "#33333A",
        "accents": ["#96751E", "#0077A8"],
    },
    "dark": {
        "bg": "#0A0A0F", "ax": "#13131A", "text": "#E8E8E8",
        "axis": "#9A9AA8", "grid": "#555563",
        "accents": ["#C9A84C", "#00D4FF"],
    },
}
_COLOR_CYCLE = ["#2ECC71", "#E74C3C", "#9B59B6", "#F39C12", "#1ABC9C", "#E67E22"]


def _full_palette(theme: str) -> tuple[dict[str, str], list[str]]:
    pal = _PALETTE.get(theme, _PALETTE["dark"])
    colors = list(pal["accents"]) + _COLOR_CYCLE
    return pal, colors


def select_modalities(
    modalities_coords: list[dict[str, Any]],
    contributions_map: dict[str, float] | None = None,
    max_labeled: int = DEFAULT_MAX_LABELED,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Retourne (labeled, gray) :
      - len <= max_labeled  -> tout labellisé, rien en gris (comportement prod) ;
      - len >  max_labeled  -> top max_labeled par score de contribution
        (somme dims 1-2 si contributions_map fournie, sinon ordre de la liste),
        le reste renvoyé en 'gray'.
    """
    total = len(modalities_coords)
    if total <= max_labeled:
        return list(modalities_coords), []

    if contributions_map:
        def score(mod: dict[str, Any]) -> float:
            return -float(contributions_map.get(str(mod.get("modalite")), 0.0))
        ordered = sorted(modalities_coords, key=score)
    else:
        ordered = list(modalities_coords)

    labeled = ordered[:max_labeled]
    labeled_names = {str(m.get("modalite")) for m in labeled}
    gray = [m for m in modalities_coords if str(m.get("modalite")) not in labeled_names]
    return labeled, gray


def contributions_rank_map(column_contributions: Any) -> dict[str, float]:
    """{modalite: score dim1+dim2} depuis un DataFrame prince (ou {})."""
    try:
        df = column_contributions
        if df is None or df.empty:
            return {}
        use = df.iloc[:, :2]
        return {str(idx): float(row.sum()) for idx, row in use.iterrows()}
    except Exception:
        return {}


def build_acm_plot(
    modalities_coords: list[dict[str, Any]],
    inertia_pct: list,
    cat_cols: list,
    theme: str = "dark",
    contributions_map: dict[str, float] | None = None,
    max_labeled: int = DEFAULT_MAX_LABELED,
) -> str | None:
    """
    Rendu du plan factoriel ACM, compatible non-régression avec
    compute._generate_acm_plot :
      - <= max_labeled modalités : rendu IDENTIQUE à la prod (même boucle,
        mêmes styles) — aucune NaN de comportement ;
      - > max_labeled : top N étiqueté par contribution + reste en nuage
        gris vectorisé (1 seul appel scatter) + suffixe dans le titre.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        pal, colors = _full_palette(theme)
        total = len(modalities_coords)
        labeled, gray = select_modalities(
            modalities_coords, contributions_map, max_labeled
        )
        capped = total > len(labeled)

        fig, ax = plt.subplots(figsize=(7, 4))
        fig.patch.set_facecolor(pal["bg"])
        ax.set_facecolor(pal["ax"])

        # Nuage des modalités non étiquetées : 1 SEUL appel scatter (le gain).
        if gray:
            xs = [m["dim1"] for m in gray]
            ys = [m["dim2"] for m in gray]
            ax.scatter(xs, ys, color=pal["grid"], s=20, alpha=0.45, zorder=2)

        # Modalités étiquetées : styles identiques à la prod.
        for mod in labeled:
            label = mod["modalite"]
            x = mod["dim1"]
            y = mod["dim2"]
            var_color = pal["accents"][0]
            for j, col in enumerate(cat_cols):
                if label.startswith(col):
                    var_color = colors[j % len(colors)]
                    break
            ax.scatter(x, y, color=var_color, s=80, zorder=5, alpha=0.8)
            ax.annotate(
                label, (x, y), textcoords="offset points", xytext=(5, 5),
                fontsize=8, color=pal["text"], alpha=0.9,
            )

        ax.axhline(y=0, color=pal["grid"], linewidth=0.5, linestyle="--")
        ax.axvline(x=0, color=pal["grid"], linewidth=0.5, linestyle="--")

        dim1_pct = inertia_pct[0] if inertia_pct else 0
        dim2_pct = inertia_pct[1] if len(inertia_pct) > 1 else 0
        ax.set_xlabel(f"Dimension 1 ({dim1_pct}%)", color=pal["axis"], fontsize=11)
        ax.set_ylabel(f"Dimension 2 ({dim2_pct}%)", color=pal["axis"], fontsize=11)
        title = "ACM — Plan Factoriel (Dimensions 1 et 2)"
        if capped:
            title += f" — top {len(labeled)}/{total} modalités"
        ax.set_title(title, color=pal["text"], fontsize=13, pad=15)
        ax.tick_params(colors=pal["axis"])
        for spine in ax.spines.values():
            spine.set_edgecolor(pal["axis"])
        ax.grid(True, alpha=0.08, color=pal["grid"])

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=80, bbox_inches="tight", facecolor=pal["bg"])
        plt.close()
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception:
        import traceback
        traceback.print_exc()
        return None
