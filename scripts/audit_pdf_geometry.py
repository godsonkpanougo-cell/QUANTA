"""
Audit géométrique des PDF QUANTA :
- page de garde : centrage horizontal du wordmark (lettres reconstituées,
  la letter-spacing morcele l'extraction), ordre vertical des blocs
- pages de contenu : signature logo en pied (bas-droite), footer paginé
- page 1 : pas de footer ni signature
"""
import os

import pymupdf  # noqa: N813

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rapports quanta",
)


def text_spans(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    spans.append((text, pymupdf.Rect(span["bbox"])))
    return spans


def find_wordmark(page: pymupdf.Page, word: str = "QUANTA"):
    """Reconstitue le wordmark depuis des lettres extraites séparément."""
    h = page.rect.height
    letters = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                t = span["text"].strip()
                r = pymupdf.Rect(span["bbox"])
                if t.isalpha() and len(t) <= 2 and r.y1 < h * 0.55:
                    letters.append((r, t.upper()))
    if not letters:
        return None
    # tri par ligne (bandes de 6 pt) puis x
    letters.sort(key=lambda rt: (round(rt[0].y0 / 6), rt[0].x0))
    seq = ""
    rects: list[pymupdf.Rect] = []
    for r, t in letters:
        seq += t
        rects.append(r)
        if seq.endswith(word):
            union = rects[-len(word)]
            for rr in rects[-len(word) + 1:]:
                union |= rr
            return union
    return None


def lines_normalized(page: pymupdf.Page) -> list[tuple[str, float]]:
    """Lignes reconstruites (letter-spacing morcele les spans) : texte
    sans espaces + y0 de la ligne."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            raw = "".join(s["text"] for s in line["spans"])
            flat = "".join(raw.split())
            if flat:
                out.append((flat.lower(), line["spans"][0]["bbox"][1]))
    return out


def audit(theme: str) -> None:
    doc = pymupdf.open(os.path.join(OUT_DIR, f"preview_report_{theme}.pdf"))
    print(f"\n===== {theme.upper()} — {doc.page_count} pages =====")

    # --- Page de garde ---
    cover = doc[0]
    W = cover.rect.width
    print("PAGE 1 (garde) :")
    quanta = find_wordmark(cover)
    if quanta is None:
        print("  [X] wordmark QUANTA introuvable (même reconstitué)")
    else:
        center_off = abs((quanta.x0 + quanta.x1) / 2 - W / 2)
        print(f"  wordmark centré : écart horizontal = {center_off:.1f} pt "
              f"({'OK' if center_off < 6 else 'TROP GRAND'})")
        print(f"  wordmark y0 = {quanta.y0:.0f} pt "
              f"(page {cover.rect.height:.0f} pt)")

    spans1 = text_spans(cover)
    lines1 = lines_normalized(cover)
    order_keys = []
    for label in ("Rapport d'analyse statistique", "intelligence statistique",
                  "Fichier analysé", "Score de confiance"):
        key = "".join(label.split()).lower()
        hit = next((y for flat, y in lines1 if key in flat), None)
        order_keys.append((label, hit))
    ok_order = all(
        a[1] is not None and b[1] is not None and a[1] < b[1]
        for a, b in zip(order_keys, order_keys[1:])
    )
    for label, y in order_keys:
        print(f"  y0 {y and round(y, 1)!s:>8}  {label}")
    print(f"  ordre vertical : {'OK' if ok_order else 'A VERIFIER'}")

    foot1 = [t for t, _ in spans1 if "Rapport d'analyse statistique · page" in t]
    print(f"  footer paginé page 1 : {'ABSENT (OK)' if not foot1 else 'PRESENT (KO)'}")

    # --- Pages de contenu : signature + footer ---
    for pno in (1, 2, doc.page_count - 1):
        page = doc[pno]
        spans = text_spans(page)
        footer = next(
            ((t, r) for t, r in spans
             if "Rapport d'analyse statistique · page" in t),
            None,
        )
        footer_text = footer[0] if footer else ""
        footer = footer[1] if footer else None
        has_footer = footer is not None
        # La signature est un background @page : rendue en VECTEURS PDF
        # (variante flat sans dégradé — un dégradé SVG serait aplati en
        # pattern bitmap 72 dpi par WeasyPrint). On regroupe tous les
        # tracés du coin bas-droit et on vérifie que leur union forme un
        # cluster de la taille du logo (~24-45 pt) : évite les faux
        # positifs (filets de tableaux, tuiles de dégradés de graphiques).
        # Bande 130 pt : la signature 48 px (36 pt) démarre plus haut
        # que l'ancienne 16 px.
        sig_rects = [
            pymupdf.Rect(d["rect"])
            for d in page.get_drawings()
            if (d["rect"].y0 > page.rect.height - 130
                and d["rect"].x1 > page.rect.width * 0.72
                and d["rect"].width < 40)
        ]
        has_sig = False
        if sig_rects:
            union = sig_rects[0]
            for r in sig_rects[1:]:
                union |= r
            has_sig = 15 <= union.width <= 45 and 15 <= union.height <= 45
        if not has_sig:
            for inf in page.get_image_info():
                b = inf["bbox"]
                if (b[1] > page.rect.height - 120
                        and b[2] > page.rect.width * 0.75
                        and (b[2] - b[0]) < 40):
                    has_sig = True
                    break
        page_num = None
        if footer is not None:
            import re
            m = re.search(r"page\s*(\d+)", footer_text)
            page_num = m.group(1) if m else None
        print(f"PAGE {pno + 1} : footer={'OK' if has_footer else 'MANQUANT'}"
              f" | n°page={page_num}"
              f" | signature bas-droite={'OK' if has_sig else 'MANQUANT'}")
    doc.close()


def main() -> None:
    for theme in ("dark", "light"):
        audit(theme)


if __name__ == "__main__":
    main()
