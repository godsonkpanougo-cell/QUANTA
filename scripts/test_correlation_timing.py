"""Script de timing pour la corrélation - Preuve de performance"""
import sys
from pathlib import Path
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from app.compute.compute import load_and_diagnose, correlation_analysis

# Créer un dataset synthétique avec 20 variables numériques
np.random.seed(42)
n_rows = 500
n_vars = 20

data = {}
for i in range(n_vars):
    data[f'var_{i}'] = np.random.randn(n_rows)

df = pd.DataFrame(data)
file_bytes = df.to_csv(index=False).encode()
diag = load_and_diagnose(file_bytes, "synthetic_20vars.csv")

print("=" * 72)
print("TIMING - Corrélation (boucle originale)")
print("=" * 72)
print(f"Dataset: {n_rows} lignes, {n_vars} variables numériques")
print(f"Nombre de paires à calculer: {n_vars * (n_vars - 1) // 2}")
print()

t0 = time.time()
result = correlation_analysis(df, diag['numeric_cols'], diag.get('normality', {}), theme='dark')
t1 = time.time()

print(f"Temps total: {t1 - t0:.3f}s")
print(f"Nombre de paires calculées: {len(result.get('pairs', {}))}")
print(f"Status: {result.get('status', 'ok')}")
