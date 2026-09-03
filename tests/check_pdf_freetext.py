"""
Script pour extraire le texte du PDF et vérifier la présence de "Commentaire"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Essayer différentes bibliothèques pour extraire le texte
try:
    import fitz  # PyMuPDF
    doc = fitz.open("tests/output_variables_freetext.pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    print("Extraction avec PyMuPDF (fitz)")
except ImportError:
    try:
        import pypdf
        reader = pypdf.PdfReader("tests/output_variables_freetext.pdf")
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        print("Extraction avec pypdf")
    except ImportError:
        print("Aucune bibliothèque PDF disponible (PyMuPDF ou pypdf)")
        text = ""

print("=" * 80)
print("RECHERCHE DE 'Commentaire' DANS LE PDF")
print("=" * 80)

if "Commentaire" in text:
    print("✓ 'Commentaire' TROUVÉ dans le PDF")
    # Extraire le contexte autour de Commentaire
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Commentaire" in line:
            print(f"\nLigne {i}: {line.strip()}")
            if i > 0:
                print(f"Ligne {i-1}: {lines[i-1].strip()}")
            if i < len(lines) - 1:
                print(f"Ligne {i+1}: {lines[i+1].strip()}")
else:
    print("✗ 'Commentaire' NON TROUVÉ dans le PDF")

print("\n" + "=" * 80)
print("RECHERCHE DE 'Texte libre' DANS LE PDF")
print("=" * 80)

if "Texte libre" in text:
    print("✓ 'Texte libre' TROUVÉ dans le PDF")
    # Extraire le contexte
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Texte libre" in line:
            print(f"\nLigne {i}: {line.strip()}")
            if i > 0:
                print(f"Ligne {i-1}: {lines[i-1].strip()}")
            if i < len(lines) - 1:
                print(f"Ligne {i+1}: {lines[i+1].strip()}")
else:
    print("✗ 'Texte libre' NON TROUVÉ dans le PDF")
