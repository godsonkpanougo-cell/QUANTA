"""
Génère un fichier CSV synthétique pour tester le garde-fou statistique sur haute cardinalité :
- 200 lignes
- Colonne "Parcelle" avec 50 modalités (nom ne contient pas "id" ou "code")
- ~4 observations par modalité (juste au-dessus du seuil de 5)
- 2-3 colonnes numériques normales
- 1 colonne catégorielle à faible cardinalité comme alternative valable
"""
import random
import string
from pathlib import Path

# Configuration
N_ROWS = 200
N_UNIQUE_PARCELLES = 50
OUTPUT_DIR = Path("tests")
OUTPUT_FILE = OUTPUT_DIR / "test_high_cardinality_ambiguous.csv"

# Génération de noms de parcelles (sans "id" ou "code" dans le nom)
def generate_parcelle_name():
    prefix = random.choice(["Parcelle", "Reference_Terrain", "Lieu_Enquete", "Zone_Observation"])
    suffix = ''.join(random.choices(string.digits, k=3))
    return f"{prefix}_{suffix}"

# Créer les parcelles uniques
unique_parcelles = [generate_parcelle_name() for _ in range(N_UNIQUE_PARCELLES)]

# Répartir les parcelles sur 200 lignes (~4 observations par parcelle)
parcelles = []
for i in range(N_ROWS):
    idx = i % N_UNIQUE_PARCELLES
    parcelles.append(unique_parcelles[idx])

# Type de sol (4 modalités - alternative valable)
types_sol = ['Argileux', 'Sableux', 'Calcaire', 'Humique']
sol_col = [random.choice(types_sol) for _ in range(N_ROWS)]

# Colonnes numériques
sup_ha = [round(random.uniform(0.5, 5.0), 2) for _ in range(N_ROWS)]
rendement = [round(random.uniform(1.0, 10.0), 2) for _ in range(N_ROWS)]
production = [round(random.uniform(500, 5000), 0) for _ in range(N_ROWS)]

# Créer le CSV
OUTPUT_DIR.mkdir(exist_ok=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write('Parcelle,Type_Sol,SUP_HA,Rendement,Production\n')
    for i in range(N_ROWS):
        f.write(f'{parcelles[i]},{sol_col[i]},{sup_ha[i]},{rendement[i]},{production[i]}\n')

print(f"Fichier généré : {OUTPUT_FILE}")
print(f"  - Lignes : {N_ROWS}")
print(f"  - Parcelles uniques : {len(set(parcelles))}")
print(f"  - Types de sol : {len(set(sol_col))}")
