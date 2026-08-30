"""
Génère un fichier CSV synthétique pour tester la robustesse face aux valeurs manquantes extrêmes :
- 200 lignes
- 60-80% de valeurs manquantes sur plusieurs colonnes
- 5 colonnes numériques avec taux de manquants variables
- 3 colonnes catégorielles avec taux de manquants variables
- Pour tester la robustesse des calculs statistiques et du diagnostic
"""
import random
from pathlib import Path

# Configuration
N_ROWS = 200
OUTPUT_DIR = Path("tests")
OUTPUT_FILE = OUTPUT_DIR / "test_extreme_missing.csv"

# Taux de valeurs manquantes par colonne (60-80%)
missing_rates = {
    'Mesure_1': 0.70,
    'Mesure_2': 0.75,
    'Mesure_3': 0.80,
    'Mesure_4': 0.65,
    'Mesure_5': 0.72,
    'Facteur_A': 0.68,
    'Facteur_B': 0.74,
    'Facteur_C': 0.78,
}

# Colonnes
numeric_cols = ['Mesure_1', 'Mesure_2', 'Mesure_3', 'Mesure_4', 'Mesure_5']
categorical_cols = ['Facteur_A', 'Facteur_B', 'Facteur_C']
all_cols = numeric_cols + categorical_cols

# Génération des données
data = {}

# Colonnes numériques
for col in numeric_cols:
    missing_rate = missing_rates[col]
    data[col] = []
    for _ in range(N_ROWS):
        if random.random() < missing_rate:
            data[col].append('')  # Valeur manquante
        else:
            data[col].append(str(round(random.uniform(0, 100), 2)))

# Colonnes catégorielles (3 modalités chacune)
for col in categorical_cols:
    missing_rate = missing_rates[col]
    modalites = [f"{col}_Val_{j+1}" for j in range(3)]
    data[col] = []
    for _ in range(N_ROWS):
        if random.random() < missing_rate:
            data[col].append('')  # Valeur manquante
        else:
            data[col].append(random.choice(modalites))

# Créer le CSV
OUTPUT_DIR.mkdir(exist_ok=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(','.join(all_cols) + '\n')
    for i in range(N_ROWS):
        row = [data[col][i] for col in all_cols]
        f.write(','.join(row) + '\n')

print(f"Fichier généré : {OUTPUT_FILE}")
print(f"  - Lignes : {N_ROWS}")
print(f"  - Colonnes numériques : {len(numeric_cols)}")
print(f"  - Colonnes catégorielles : {len(categorical_cols)}")
print(f"  - Taux de manquants par colonne :")
for col, rate in missing_rates.items():
    print(f"    {col}: {rate*100:.0f}%")
