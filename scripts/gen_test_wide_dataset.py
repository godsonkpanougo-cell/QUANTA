"""
Génère un fichier CSV synthétique pour tester le comportement sur dataset large :
- 200 lignes
- 45 colonnes (mix numérique/catégoriel)
- 25 colonnes numériques
- 20 colonnes catégorielles
- Pour tester la charge sur brain.analyze_with_brain et la taille du rapport
"""
import random
import string
from pathlib import Path

# Configuration
N_ROWS = 200
N_NUMERIC = 25
N_CATEGORICAL = 20
OUTPUT_DIR = Path("tests")
OUTPUT_FILE = OUTPUT_DIR / "test_wide_dataset.csv"

# Génération de noms de colonnes numériques
numeric_cols = [f"Mesure_{i+1}" for i in range(N_NUMERIC)]

# Génération de noms de colonnes catégorielles
categorical_cols = [f"Facteur_{chr(65+i)}" for i in range(N_CATEGORICAL)]

# Génération des données
data = {}
header = []

# Colonnes numériques
for col in numeric_cols:
    data[col] = [round(random.uniform(0, 100), 2) for _ in range(N_ROWS)]
    header.append(col)

# Colonnes catégorielles (3-5 modalités chacune)
for col in categorical_cols:
    n_modalites = random.randint(3, 5)
    modalites = [f"{col}_Val_{j+1}" for j in range(n_modalites)]
    data[col] = [random.choice(modalites) for _ in range(N_ROWS)]
    header.append(col)

# Créer le CSV
OUTPUT_DIR.mkdir(exist_ok=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(','.join(header) + '\n')
    for i in range(N_ROWS):
        row = [str(data[col][i]) for col in header]
        f.write(','.join(row) + '\n')

print(f"Fichier généré : {OUTPUT_FILE}")
print(f"  - Lignes : {N_ROWS}")
print(f"  - Colonnes numériques : {N_NUMERIC}")
print(f"  - Colonnes catégorielles : {N_CATEGORICAL}")
print(f"  - Total colonnes : {len(header)}")
