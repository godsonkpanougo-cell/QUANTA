"""
Script temporaire pour vérifier si freetext_cols est transmis dans le diagnosis
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import pandas as pd
from app.compute.upload_validation import load_and_diagnose

# Charger test_freetext_as_categorical.csv
file_path = Path(__file__).parent / "test_freetext_as_categorical.csv"
with open(file_path, 'rb') as f:
    file_bytes = f.read()

diagnosis = load_and_diagnose(file_bytes, "test_freetext_as_categorical.csv")

print("=" * 80)
print("DIAGNOSIS RETOURNÉ PAR load_and_diagnose()")
print("=" * 80)
print(f"numeric_cols: {diagnosis.get('numeric_cols')}")
print(f"cat_cols: {diagnosis.get('cat_cols')}")
print(f"id_cols: {diagnosis.get('id_cols')}")
print(f"freetext_cols: {diagnosis.get('freetext_cols')}")
print()

if "freetext_cols" in diagnosis:
    print("✓ freetext_cols est présent dans le diagnosis retourné par load_and_diagnose()")
else:
    print("✗ freetext_cols N'EST PAS présent dans le diagnosis retourné par load_and_diagnose()")
