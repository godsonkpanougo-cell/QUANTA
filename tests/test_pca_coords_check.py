"""Vérifier que column_coordinates_ retourne des valeurs cohérentes pour le cercle des corrélations."""
import pandas as pd
import prince

# Données simples
df = pd.DataFrame({
    'x': [1, 2, 3, 4, 5],
    'y': [2, 4, 6, 8, 10],
    'z': [1, 3, 5, 7, 9]
})

acp = prince.PCA(n_components=2, random_state=42, engine='sklearn', 
                 rescale_with_mean=True, rescale_with_std=True)
acp = acp.fit(df)

# Coordonnées des variables
coords = acp.column_coordinates_
print("=== column_coordinates_ ===")
print(coords)
print(f"\nValeurs min/max:")
print(f"Dim1: min={coords.iloc[:, 0].min():.4f}, max={coords.iloc[:, 0].max():.4f}")
print(f"Dim2: min={coords.iloc[:, 1].min():.4f}, max={coords.iloc[:, 1].max():.4f}")

# Vérifier si les valeurs sont dans [-1, 1] (corrélations)
out_of_bounds = (coords.abs() > 1).any()
print(f"\nValeurs hors du cercle unité [-1, 1]: {out_of_bounds}")

# Vérifier les corrélations réelles
print("\n=== Matrice de corrélation originale ===")
print(df.corr())
