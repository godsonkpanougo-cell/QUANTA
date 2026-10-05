"""
Inspecte les PDF de prévisualisation :
- liste les polices réellement embarquées (nom, type)
- compte les pages
- rend quelques pages en PNG pour inspection visuelle
- fabrique une planche-contact HTML (base64) pour revue dans le navigateur
"""
import base64
import os
import sys

import pymupdf  # noqa: N813

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rapports quanta",
)
PNG_DIR = os.path.join(OUT_DIR, "preview")
PAGES_TO_RENDER = {0, 1, 2}  # cover, section 1, section 2 (+ dernière page)


def inspect(theme: str, contact_parts: list[str]) -> None:
    path = os.path.join(OUT_DIR, f"preview_report_{theme}.pdf")
    doc = pymupdf.open(path)
    print(f"\n=== {theme.upper()} — {doc.page_count} pages ===")

    fonts = set()
    for page in doc:
        for f in page.get_fonts(full=True):
            fonts.add((f[3], f[1]))  # (basefont, ext)
    print("Polices embarquées :")
    for name, ext in sorted(fonts):
        print(f"  - {name} ({ext})")

    pages = sorted(PAGES_TO_RENDER | {doc.page_count - 1})
    os.makedirs(PNG_DIR, exist_ok=True)
    pngs = []
    for i in pages:
        page = doc[i]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.35, 1.35))
        png_path = os.path.join(PNG_DIR, f"{theme}_p{i + 1}.png")
        pix.save(png_path)
        pngs.append((f"{theme} — page {i + 1}", png_path))

    contact_parts.append(f"<h2>Thème {theme.upper()}</h2>")
    for label, png_path in pngs:
        with open(png_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        contact_parts.append(
            f'<figure><figcaption>{label}</figcaption>'
            f'<img src="data:image/png;base64,{b64}"/></figure>'
        )
    doc.close()


def main() -> None:
    contact: list[str] = []
    for theme in ("dark", "light"):
        inspect(theme, contact)

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>QUANTA — Planche contact PDF</title><style>"
        "body{background:#222;color:#eee;font-family:sans-serif;margin:20px;}"
        "h2{margin:28px 0 10px;color:#D6B761;}"
        "figure{margin:0 0 26px 0;}"
        "figcaption{font-size:13px;margin-bottom:6px;color:#aaa;}"
        "img{max-width:640px;width:100%;display:block;box-shadow:0 4px 24px #000;}"
        "</style></head><body>"
        "<h1>Planche contact — rapports QUANTA</h1>" + "\n".join(contact) +
        "</body></html>"
    )
    out_html = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "quanta_pdf_preview.html",
    )
    with open(out_html, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"\nPlanche contact : {out_html}")


if __name__ == "__main__":
    main()
