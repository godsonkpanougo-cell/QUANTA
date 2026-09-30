"""Script de test pour vérifier la section ACM dans le PDF en mode auto"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from app.compute.compute import load_and_diagnose, run_acm
from app.report_generator import generate_pdf_report

# Charger le dataset test_acm_with_identifier.csv
df = pd.read_csv(ROOT / "data" / "samples" / "test_acm_with_identifier.csv")
file_bytes = df.to_csv(index=False).encode()
filename = "test_acm_with_identifier.csv"

print("=" * 72)
print("TEST PDF - Mode auto sur test_acm_with_identifier.csv")
print("=" * 72)
print(f"Dataset: {len(df)} lignes")
print()

# Diagnostic
diag = load_and_diagnose(file_bytes, filename)
cat_cols = diag["cat_cols"]

# Exécuter ACM
acm_result = run_acm(df, cat_cols)
print(f"ACM status: {acm_result.get('status')}")
print(f"ACM n_variables: {acm_result.get('n_variables')}")
print()

# Construire un result mock simulant le mode auto avec ACM
result = {
    "mode": "auto",
    "filename": filename,
    "diagnosis": diag,
    "analysis": {
        "inference": {
            "action_executed": "acm",
            "result": acm_result
        }
    },
    "analyses": [
        {
            "intent": {"action": "acm"},
            "analysis": {
                "inference": {
                    "action_executed": "acm",
                    "result": acm_result
                }
            }
        }
    ],
    "tests_effectues": [
        {
            "action": "acm",
            "action_executed": "acm",
            "result": acm_result
        }
    ]
}

# Générer le PDF
print("Génération du PDF...")
pdf_bytes = generate_pdf_report(result, theme="dark")
print(f"PDF généré: {len(pdf_bytes)} octets")

# Sauvegarder le PDF pour inspection manuelle
pdf_path = ROOT / "test_acm_output.pdf"
with open(pdf_path, "wb") as f:
    f.write(pdf_bytes)
print(f"PDF sauvegardé dans: {pdf_path}")
print()

print("=" * 72)
print("RÉSUMÉ")
print("=" * 72)
print(f"PDF généré: {len(pdf_bytes)} octets")
print(f"PDF sauvegardé: {pdf_path}")
print("Veuillez ouvrir le PDF manuellement pour vérifier la section ACM")
