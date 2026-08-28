"""
Génère un fichier CSV synthétique reproduisant le bug Identifier :
- 219 lignes
- Colonne "Identifier" avec codes alphanumériques style "00at-gjje-akss"
- ~77 valeurs uniques avec doublons (~2-3 lignes par code)
- 2-3 colonnes numériques normales (SUP_HA, Rendement)
- 1 colonne catégorielle à 4-5 modalités (Region) comme alternative valable
"""
import random
import string
from pathlib import Path

# Configuration
N_ROWS = 219
N_UNIQUE_IDENTIFIERS = 77
OUTPUT_DIR = Path("tests")
OUTPUT_FILE = OUTPUT_DIR / "test_identifier_bug.csv"

# Génération de codes alphanumériques style "00at-gjje-akss"
def generate_identifier():
    parts = []
    for i in range(3):
        chars = ''.join(random.choices(string.ascii_lowercase, k=4))
        parts.append(chars)
    return '-'.join(parts)

# Créer les identifiants uniques
unique_identifiers = [generate_identifier() for _ in range(N_UNIQUE_IDENTIFIERS)]

# Répartir les identifiens sur 219 lignes (2-3 occurrences par identifiant)
identifiers = []
for i in range(N_ROWS):
    idx = i % N_UNIQUE_IDENTIFIERS
    identifiers.append(unique_identifiers[idx])

# Régions (4 modalités)
regions = ['Nord', 'Sud', 'Est', 'Ouest']
region_col = [random.choice(regions) for _ in range(N_ROWS)]

# Colonnes numériques
sup_ha = [round(random.uniform(0.5, 5.0), 2) for _ in range(N_ROWS)]
rendement = [round(random.uniform(1.0, 10.0), 2) for _ in range(N_ROWS)]
production = [round(random.uniform(500, 5000), 0) for _ in range(N_ROWS)]

# Créer le CSV
OUTPUT_DIR.mkdir(exist_ok=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write('Identifier,Region,SUP_HA,Rendement,Production\n')
    for i in range(N_ROWS):
        f.write(f'{identifiers[i]},{region_col[i]},{sup_ha[i]},{rendement[i]},{production[i]}\n')

print(f"Fichier généré : {OUTPUT_FILE}")
print(f"  - Lignes : {N_ROWS}")
print(f"  - Identifiants uniques : {len(set(identifiers))}")
print(f"  - Régions : {len(set(region_col))}")
