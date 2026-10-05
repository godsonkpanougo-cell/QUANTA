"""
QUANTA — quanta_fonts.py

Infrastructure typographique du rapport PDF.

Les polices (silhouette OFL) sont embarquées en base64 via @font-face,
injectées une seule fois par processus (cache) dans chaque document HTML
généré par WeasyPrint :

  - Orbitron (wordmark / titres d'apparat) — géométrique futuriste
  - Cormorant Garamond (accents éditoriaux, italique élégant)
  - Jost (corps de texte, labels, méta) — géométrique humaniste
  - JetBrains Mono (données, hashes, audit trail)

Toutes sous licence SIL Open Font License (usage commercial libre).
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_FONT_FILES: dict[str, str] = {
    "Orbitron": "Orbitron-Black.ttf",
    "Orbitron SemiBold": "Orbitron-SemiBold.ttf",
    "Cormorant Garamond": "Cormorant-SemiBold.ttf",
    "Cormorant Garamond Italic": "Cormorant-Italic-Medium.ttf",
    "Jost": "Jost-Regular.ttf",
    "Jost Medium": "Jost-Medium.ttf",
    "Jost SemiBold": "Jost-SemiBold.ttf",
    "Jost Italic": "Jost-Italic.ttf",
    "JetBrains Mono": "JetBrainsMono-Regular.ttf",
}

_cached_fontface_css: str | None = None


def _font_base64(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def _mimetype_for(path: Path) -> str:
    return "font/ttf" if path.suffix.lower() == ".ttf" else "application/octet-stream"


def get_fontface_css() -> str:
    """
    Retourne le bloc CSS @font-face complet (embarqué base64).
    Mis en cache au niveau du processus : les fichiers ne sont lus
    qu'une seule fois, quel que soit le nombre de rapports générés.
    """
    global _cached_fontface_css
    if _cached_fontface_css is not None:
        return _cached_fontface_css

    faces: list[str] = []
    for family, filename in _FONT_FILES.items():
        path = _FONTS_DIR / filename
        if not path.exists():
            logger.warning("Police manquante : %s", path)
            continue
        b64 = _font_base64(path)
        faces.append(
            "@font-face {"
            f" font-family: '{family}';"
            " font-style: normal;"
            " font-weight: normal;"
            f" src: url(data:{_mimetype_for(path)};base64,{b64}) format('truetype');"
            " }"
        )

    _cached_fontface_css = "\n".join(faces)
    logger.info(
        "Polices QUANTA chargées (%d faces, CSS %d Ko)",
        len(faces),
        len(_cached_fontface_css) // 1024,
    )
    return _cached_fontface_css


# ---------------------------------------------------------------------------
# Signature logo (SVG inline, fidèle au composant LogoQ du frontend)
# ---------------------------------------------------------------------------

def quanta_signature_svg_flat(height: int = 48) -> str:
    """
    Variante de la signature SANS dégradé : deux tons plats (or pour
    l'anneau et le trait, crème pour le point). Indispensable pour le
    background de @page : WeasyPrint transforme tout remplissage en
    dégradé SVG en pattern rastérisé 72 dpi, alors qu'un remplissage
    uni est rendu en VECTEURS PDF purs — netteté parfaite à tout zoom
    et à l'impression.
    """
    return (
        f'<svg width="{height}" height="{height}" viewBox="0 0 48 48" fill="none" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M 35.5 30 A 14 14 0 1 0 26.4 35.8" stroke="#D6B761" '
        'stroke-width="2.6" stroke-linecap="round"/>'
        '<line x1="26.2" y1="25.4" x2="36" y2="40.5" stroke="#D6B761" '
        'stroke-width="2.6" stroke-linecap="round"/>'
        '<circle cx="37.6" cy="42.8" r="1.9" fill="#E8D5A3"/>'
        "</svg>"
    )


def quanta_signature_page_background(display_px: int = 48) -> str:
    """
    Fragment CSS `url("data:...")` du symbole QUANTA en SVG base64 —
    utilisé en background de @page : présent sur chaque page produite,
    y compris en génération chunked (un document WeasyPrint par section).

    Utilise la variante FLAT (sans dégradé) : un dégradé SVG est aplati
    par WeasyPrint en pattern bitmap 72 dpi (baveux en impression), la
    version unie reste vectorielle — voir quanta_signature_svg_flat().
    """
    svg = quanta_signature_svg_flat(display_px)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'url("data:image/svg+xml;base64,{b64}")'


def quanta_signature_svg(height: int = 18) -> str:
    """
    SVG inline du symbole QUANTA — anneau entaillé traversé par un vecteur
    terminé par un point — exactement la géométrie de LogoQ (frontend).
    Utilisé pour le logo de la page de garde (rendu inline, taille confortable :
    le pattern dégradé y reste acceptable) ; les pieds de page utilisent la
    variante plate vectorielle quanta_signature_svg_flat().
    """
    return (
        f'<svg width="{height}" height="{height}" viewBox="0 0 48 48" fill="none" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<defs><linearGradient id="qsig" x1="10" y1="8" x2="40" y2="44" '
        'gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#E8D5A3"/>'
        '<stop offset="1" stop-color="#C9A84C"/>'
        '</linearGradient></defs>'
        '<path d="M 35.5 30 A 14 14 0 1 0 26.4 35.8" stroke="url(#qsig)" '
        'stroke-width="2.6" stroke-linecap="round"/>'
        '<line x1="26.2" y1="25.4" x2="36" y2="40.5" stroke="url(#qsig)" '
        'stroke-width="2.6" stroke-linecap="round"/>'
        '<circle cx="37.6" cy="42.8" r="1.9" fill="#E8D5A3"/>'
        "</svg>"
    )
