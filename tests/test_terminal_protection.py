"""
Test temporaire pour vérifier la protection contre l'écrasement du statut 'done'.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from datetime import datetime

def _now():
    return datetime.utcnow().isoformat() + "Z"

# Test 1: done ne peut pas être écrasé
print("=" * 60)
print("TEST 1: done ne peut pas être écrasé")
print("=" * 60)

db.clear_all()

# Créer un upload et une analyse
file_id = "test_file_001"
db.save_upload(file_id, {
    "path": "/tmp/test.csv",
    "filename": "test.csv",
    "numeric_cols": ["age"],
    "cat_cols": [],
    "id_cols": [],
    "n_rows": 10,
    "n_cols": 1,
    "dataset_type": "test",
    "uploaded_at": _now()
})

analysis_id = "test_analysis_001"
db.create_analysis(analysis_id, file_id, "test query", _now())

# Mettre le statut à "done"
result1 = db.update_analysis(analysis_id, status="done", result={"test": "data"}, updated_at=_now())
print(f"update_analysis(id, status='done') -> {result1}")

# Essayer d'écraser avec "error"
result2 = db.update_analysis(analysis_id, status="error", error="test error", updated_at=_now())
print(f"update_analysis(id, status='error') -> {result2}")

# Vérifier le statut final
analysis = db.get_analysis(analysis_id)
print(f"get_analysis(id)['status'] -> {analysis['status']}")
print(f"Attendu: 'done'")

assert analysis['status'] == 'done', f"ERREUR: statut devrait être 'done', mais est '{analysis['status']}'"
assert result2 == False, f"ERREUR: deuxième appel devrait retourner False, mais a retourné {result2}"

print("✓ TEST 1 RÉUSSI: done ne peut pas être écrasé")

# Test 2: error peut être transformé en done
print("\n" + "=" * 60)
print("TEST 2: error peut être transformé en done")
print("=" * 60)

analysis_id2 = "test_analysis_002"
db.create_analysis(analysis_id2, file_id, "test query 2", _now())

# Mettre le statut à "error"
result3 = db.update_analysis(analysis_id2, status="error", error="premier error", updated_at=_now())
print(f"update_analysis(id, status='error') -> {result3}")

# Transformer en "done"
result4 = db.update_analysis(analysis_id2, status="done", result={"success": True}, updated_at=_now())
print(f"update_analysis(id, status='done') -> {result4}")

# Vérifier le statut final
analysis2 = db.get_analysis(analysis_id2)
print(f"get_analysis(id)['status'] -> {analysis2['status']}")
print(f"Attendu: 'done'")

assert analysis2['status'] == 'done', f"ERREUR: statut devrait être 'done', mais est '{analysis2['status']}'"
assert result4 == True, f"ERREUR: transformation devrait retourner True, mais a retourné {result4}"

print("✓ TEST 2 RÉUSSI: error peut être transformé en done")

# Nettoyage
db.clear_all()
print("\n✓ TOUS LES TESTS RÉUSSIS")
