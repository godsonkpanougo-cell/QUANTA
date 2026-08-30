"""
Génère un fichier CSV synthétique pour tester la détection de texte libre mal classé comme catégoriel :
- 150 lignes
- Colonne "Commentaire" avec texte libre (phrases complètes, quasiment toutes uniques)
- 2-3 colonnes numériques normales
- 1 colonne catégorielle à faible cardinalité comme alternative valable
"""
import random
from pathlib import Path

# Configuration
N_ROWS = 150
OUTPUT_DIR = Path("tests")
OUTPUT_FILE = OUTPUT_DIR / "test_freetext_as_categorical.csv"

# Échantillons de phrases pour les commentaires
commentaires_templates = [
    "Le participant a mentionné que l'expérience était globalement positive.",
    "Observation notée : le rendement semble inférieur aux attentes initiales.",
    "Remarque importante : les conditions météo ont affecté les résultats.",
    "Le sujet a indiqué une préférence pour la méthode alternative proposée.",
    "Note de terrain : l'échantillon prélevé présente des caractéristiques atypiques.",
    "Commentaire du superviseur : procédure suivie conformément au protocole.",
    "Observation : la variation entre les mesures est plus élevée que prévu.",
    "Le participant a signalé des difficultés avec la deuxième phase du test.",
    "Remarque : les données collectées nécessitent une vérification supplémentaire.",
    "Note : le temps de réponse a été plus long que la moyenne observée.",
]

# Génération de commentaires avec variations
def generate_commentaire():
    template = random.choice(commentaires_templates)
    # Ajouter un suffixe aléatoire pour maximiser l'unicité
    suffix = random.randint(1, 999)
    return f"{template} (Ref: {suffix})"

# Créer les commentaires
commentaires = [generate_commentaire() for _ in range(N_ROWS)]

# Type d'expérience (4 modalités - alternative valable)
types_experience = ['Type_A', 'Type_B', 'Type_C', 'Type_D']
experience_col = [random.choice(types_experience) for _ in range(N_ROWS)]

# Colonnes numériques
score = [round(random.uniform(0, 100), 1) for _ in range(N_ROWS)]
temps = [round(random.uniform(10, 120), 1) for _ in range(N_ROWS)]
reussite = [random.choice([0, 1]) for _ in range(N_ROWS)]

# Créer le CSV
OUTPUT_DIR.mkdir(exist_ok=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write('Commentaire,Type_Experience,Score,Temps,Reussite\n')
    for i in range(N_ROWS):
        f.write(f'"{commentaires[i]}",{experience_col[i]},{score[i]},{temps[i]},{reussite[i]}\n')

print(f"Fichier généré : {OUTPUT_FILE}")
print(f"  - Lignes : {N_ROWS}")
print(f"  - Commentaires uniques : {len(set(commentaires))}")
print(f"  - Types d'expérience : {len(set(experience_col))}")
