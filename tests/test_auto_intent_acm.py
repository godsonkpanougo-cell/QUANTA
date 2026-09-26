"""Test auto_intent : vérifie que l'action ACM est correctement générée pour 3+ colonnes catégorielles."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator import auto_intent
from app.compute.compute import load_and_diagnose

if __name__ == "__main__":
    print("=" * 72)
    print("TEST : auto_intent() avec 3+ colonnes catégorielles")
    print("=" * 72)
    
    # Charger le fichier test_acm_with_identifier.csv
    path = ROOT / "data" / "samples" / "test_acm_with_identifier.csv"
    if not path.exists():
        print(f"ERREUR : fichier {path} introuvable")
        sys.exit(1)
    
    # Obtenir le diagnostic
    diagnosis = load_and_diagnose(path.read_bytes(), path.name)
    if "error" in diagnosis:
        print(f"ERREUR : {diagnosis['error']}")
        sys.exit(1)
    
    print(f"\n--- DIAGNOSTIC ---")
    print(f"numeric_cols = {diagnosis.get('numeric_cols', [])}")
    print(f"cat_cols = {diagnosis.get('cat_cols', [])}")
    print(f"id_cols = {diagnosis.get('id_cols', [])}")
    
    # Appeler auto_intent()
    intents = auto_intent(diagnosis)
    
    print(f"\n--- INTENTS GENERES ({len(intents)}) ---")
    for i, intent in enumerate(intents):
        print(f"{i+1}. action={intent.action!r}, target={intent.target_col!r}, group={intent.group_col!r}")
    
    # Vérifier qu'une intention avec action="acm" est présente
    acm_intents = [intent for intent in intents if intent.action == "acm"]
    
    print(f"\n--- VERIFICATION ---")
    print(f"Nombre d'intents avec action='acm' : {len(acm_intents)}")
    
    if len(acm_intents) == 0:
        print("\n[ERROR] Aucune intention avec action='acm' détectée")
        print("Le bug de déduplication est toujours présent.")
        sys.exit(1)
    
    if len(acm_intents) > 1:
        print(f"\n[WARNING] Plusieurs intentions avec action='acm' détectées ({len(acm_intents)})")
    
    acm_intent = acm_intents[0]
    print(f"\n[OK] Intention ACM détectée :")
    print(f"  action = {acm_intent.action!r}")
    print(f"  target_col = {acm_intent.target_col!r}")
    print(f"  group_col = {acm_intent.group_col!r}")
    
    # Vérifier également que l'intention Chi-deux est toujours présente (2 colonnes)
    association_intents = [intent for intent in intents if intent.action == "association"]
    print(f"\nNombre d'intents avec action='association' (Chi-deux) : {len(association_intents)}")
    
    if len(association_intents) > 0:
        print(f"[OK] Intention Chi-deux détectée (pas écrasée par la déduplication)")
    else:
        print(f"[WARNING] Aucune intention Chi-deux détectée (peut être normal selon la logique)")
    
    print("\n" + "=" * 72)
    print("CONCLUSION : auto_intent() génère correctement l'action ACM")
    print("=" * 72)
