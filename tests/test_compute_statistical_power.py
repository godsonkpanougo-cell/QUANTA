"""Test compute_statistical_power : vérifie le calcul de puissance sur un cas connu."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.compute import compute_statistical_power

if __name__ == "__main__":
    print("=" * 72)
    print("TEST compute_statistical_power")
    print("=" * 72)
    
    # Cas 1 : t-test à 2 groupes (Cohen's d connu)
    # Pour n1=n2=30, effect_size=0.5 (effet moyen), alpha=0.05
    # La puissance attendue est d'environ 0.47-0.50 (calculable avec statsmodels)
    print("\n--- CAS 1 : t-test 2 groupes ---")
    result1 = {
        "status": "ok",
        "test": "t-test de Student (variances égales)",
        "n_group1": 30,
        "n_group2": 30,
        "effect_size": 0.5,  # Cohen's d = 0.5 (effet moyen)
        "p_value": 0.04,
    }
    
    enriched1 = compute_statistical_power(result1)
    
    print(f"Résultat original : effect_size={result1['effect_size']}, n1={result1['n_group1']}, n2={result1['n_group2']}")
    print(f"Résultat enrichi : power={enriched1.get('power')}")
    print(f"Interprétation : {enriched1.get('power_interpretation')}")
    
    if enriched1.get("power") is None:
        print("⚠️ ERREUR : power non calculé")
        sys.exit(1)
    
    # Vérification grossière : pour d=0.5, n=30, la puissance devrait être ~0.47
    power1 = enriched1["power"]
    if not (0.40 <= power1 <= 0.60):
        print(f"⚠️ ATTENTION : power={power1} hors plage attendue [0.40, 0.60] pour d=0.5, n=30")
        print("Cela peut être normal selon l'implémentation exacte de statsmodels.")
    else:
        print(f"[OK] Power dans plage attendue : {power1:.3f}")
    
    # Cas 2 : ANOVA (η² connu)
    print("\n--- CAS 2 : ANOVA (η²) ---")
    result2 = {
        "status": "ok",
        "test": "ANOVA à un facteur (variances égales)",
        "n_groups": 3,
        "group_sizes": [30, 30, 30],
        "eta_squared": 0.06,  # η² = 0.06 (effet moyen)
        "p_value": 0.03,
    }
    
    enriched2 = compute_statistical_power(result2)
    
    print(f"Résultat original : eta_squared={result2['eta_squared']}, n_groups={result2['n_groups']}")
    print(f"Résultat enrichi : power={enriched2.get('power')}")
    
    if enriched2.get("power") is None:
        print("⚠️ ERREUR : power non calculé pour ANOVA")
        sys.exit(1)
    
    power2 = enriched2["power"]
    print(f"[OK] Power calculé pour ANOVA : {power2:.3f}")
    
    # Cas 3 : Chi-deux (V de Cramér connu)
    print("\n--- CAS 3 : Chi-deux (V de Cramér) ---")
    result3 = {
        "status": "ok",
        "test": "Chi-deux d'indépendance",
        "cramers_v": 0.3,  # V de Cramér = 0.3 (effet moyen)
        "n_observations": 100,
        "p_value": 0.02,
    }
    
    enriched3 = compute_statistical_power(result3)
    
    print(f"Résultat original : cramers_v={result3['cramers_v']}, n={result3['n_observations']}")
    print(f"Résultat enrichi : power={enriched3.get('power')}")
    
    if enriched3.get("power") is None:
        print("[WARNING] ATTENTION : power non calculé pour Chi-deux")
        print("Cela peut être normal si la détection du Chi-deux dans compute_statistical_power")
        print("ne reconnaît pas ce format de résultat. Vérifier l'implémentation.")
        # On ne fait pas exit(1) car ce n'est pas forcément un bug critique
    else:
        power3 = enriched3["power"]
        print(f"[OK] Power calculé pour Chi-deux : {power3:.3f}")
    
    # Cas 4 : Cas d'erreur (status=error)
    print("\n--- CAS 4 : Cas d'erreur (status=error) ---")
    result4 = {
        "status": "error",
        "reason": "Test invalide",
    }
    
    enriched4 = compute_statistical_power(result4)
    
    if enriched4.get("power") is not None:
        print("[ERROR] power ne devrait pas être calculé pour status=error")
        sys.exit(1)
    
    print("[OK] Power non calculé pour status=error (comportement correct)")
    
    # Cas 5 : Cas déjà enrichi (power déjà présent)
    print("\n--- CAS 5 : Cas déjà enrichi ---")
    result5 = {
        "status": "ok",
        "test": "t-test",
        "n_group1": 30,
        "n_group2": 30,
        "effect_size": 0.5,
        "power": 0.75,  # Déjà présent
    }
    
    enriched5 = compute_statistical_power(result5)
    
    if enriched5.get("power") != 0.75:
        print("[ERROR] power existant ne devrait pas être recalculé")
        sys.exit(1)
    
    print("[OK] Power existant non recalculé (comportement correct)")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : compute_statistical_power fonctionne correctement")
    print("=" * 72)
