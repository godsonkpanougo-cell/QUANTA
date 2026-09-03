"""
Script pour extraire le texte du PDF et vérifier la présence de "Identifier"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Essayer différentes bibliothèques pour extraire le texte
try:
    import fitz  # PyMuPDF
    doc = fitz.open("tests/output_variables_identifier.pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    print("Extraction avec PyMuPDF (fitz)")
except ImportError:
    try:
        import pypdf
        reader = pypdf.PdfReader("tests/output_variables_identifier.pdf")
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        print("Extraction avec pypdf")
    except ImportError:
        print("Aucune bibliothèque PDF disponible (PyMuPDF ou pypdf)")
        text = ""

print("=" * 80)
print("RECHERCHE DE 'Identifier' DANS LE PDF")
print("=" * 80)

if "Identifier" in text:
    print("✓ 'Identifier' TROUVÉ dans le PDF")
    # Extraire le contexte autour de Identifier
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Identifier" in line:
            print(f"\nLigne {i}: {line.strip()}")
            if i > 0:
                print(f"Ligne {i-1}: {lines[i-1].strip()}")
            if i < len(lines) - 1:
                print(f"Ligne {i+1}: {lines[i+1].strip()}")
else:
    print("✗ 'Identifier' NON TROUVÉ dans le PDF")

print("\n" + "=" * 80)
print("RECHERCHE DE 'Identifiant (exclue de l'analyse)' DANS LE PDF")
print("=" * 80)

if "Identifiant (exclue de l'analyse)" in text:
    print("✓ 'Identifiant (exclue de l'analyse)' TROUVÉ dans le PDF")
    # Extraire le contexte
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Identifiant" in line:
            print(f"\nLigne {i}: {line.strip()}")
            if i > 0:
                print(f"Ligne {i-1}: {lines[i-1].strip()}")
            if i < len(lines) - 1:
                print(f"Ligne {i+1}: {lines[i+1].strip()}")
else:
    print("✗ 'Identifiant (exclue de l'analyse)' NON TROUVÉ dans le PDF")
