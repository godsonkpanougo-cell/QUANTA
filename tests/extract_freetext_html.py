"""
Script temporaire pour extraire l'HTML du rapport et vérifier la présence de freetext_cols
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import json
from app.report_generator import generate_pdf_report

# Charger le résultat du test (sauvegardé dans le test)
# Pour l'instant, on va créer un diagnosis manuel pour tester
diagnosis = {
    "n_rows": 150,
    "n_cols": 5,
    "dataset_type": "Petit échantillon",
    "numeric_cols": ["Score", "Temps"],
    "cat_cols": ["Type_Experience", "Reussite"],
    "id_cols": [],
    "freetext_cols": ["Commentaire"],  # C'est ce qu'on veut vérifier
    "date_cols": [],
    "reclassified_as_categorical": {},
    "missing": {},
    "missing_pct": {},
    "n_duplicates": 0,
    "descriptive_stats": {
        "numeric": {},
        "categorical": {}
    }
}

from app.report_generator import _html_variables_table

table_counter = [0]
html = _html_variables_table(diagnosis, table_counter)

print("=" * 80)
print("SECTION VARIABLES DU DATASET (HTML)")
print("=" * 80)
print(html)
print()

# Vérifier si "Commentaire" apparaît
if "Commentaire" in html:
    print("✓ Commentaire apparaît dans le HTML")
else:
    print("✗ Commentaire N'APPARAÎT PAS dans le HTML")
    print("  Seules les colonnes numeric_cols et cat_cols sont listées")
