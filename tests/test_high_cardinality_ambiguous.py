"""
Test manuel pour valider le garde-fou statistique sur haute cardinalité ambiguë :
- Uploader le fichier test_high_cardinality_ambiguous.csv
- Lancer /analyze en mode auto
- Vérifier que "Parcelle" (50 modalités, nom non détecté) n'est pas utilisé pour comparaison multi-groupes
- Vérifier que le garde-fou statistique (>30 modalités ou <5 obs/groupe) est activé
"""
import sys
import json
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app

def main():
    client = TestClient(app)
    
    print("=" * 80)
    print("TEST MANUEL - HAUTE CARDINALITÉ AMBIGUË")
    print("=" * 80)
    
    # 1. Upload du fichier
    print("\n[1] Upload du fichier test_high_cardinality_ambiguous.csv...")
    file_path = Path(__file__).parent / "test_high_cardinality_ambiguous.csv"
    
    with open(file_path, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test_high_cardinality_ambiguous.csv", f, "text/csv")}
        )
    
    print(f"Upload status : {upload_response.status_code}")
    
    if upload_response.status_code != 200:
        print(f"Erreur upload : {upload_response.text}")
        return
    
    upload_data = upload_response.json()
    file_id = upload_data.get("file_id")
    print(f"File ID : {file_id}")
    
    # 2. Lancer /analyze en mode auto (query vide)
    print("\n[2] Lancement /analyze en mode auto...")
    analyze_response = client.post(
        "/analyze",
        json={"file_id": file_id, "query": ""}
    )
    
    print(f"Analyze status : {analyze_response.status_code}")
    
    if analyze_response.status_code != 200:
        print(f"Erreur analyze : {analyze_response.text}")
        return
    
    analyze_data = analyze_response.json()
    analysis_id = analyze_data.get("analysis_id")
    print(f"Analysis ID : {analysis_id}")
    
    # 3. Attendre la fin de l'analyse
    print("\n[3] Attente de la fin de l'analyse...")
    import time
    max_wait = 60
    waited = 0
    
    while waited < max_wait:
        status_response = client.get(f"/status/{analysis_id}")
        status_data = status_response.json()
        status = status_data.get("status")
        
        print(f"  Status : {status} ({waited}s)")
        
        if status == "done":
            break
        elif status == "failed":
            print(f"Erreur analyse : {status_data.get('error')}")
            return
        
        time.sleep(2)
        waited += 2
    
    if waited >= max_wait:
        print("Timeout : analyse non terminée")
        return
    
    # 4. Récupérer le résultat complet
    print("\n[4] Récupération du résultat complet...")
    status_response = client.get(f"/status/{analysis_id}")
    status_data = status_response.json()
    
    result = status_data.get("result")
    
    # 5. Vérifications
    print("\n" + "=" * 80)
    print("VÉRIFICATIONS")
    print("=" * 80)
    
    # Vérifier le diagnostic
    diagnosis = result.get("diagnosis", {})
    cat_cols = diagnosis.get("cat_cols", [])
    print(f"\n[5.1] Colonnes catégorielles : {cat_cols}")
    
    # Vérifier les intentions proposées
    intents = result.get("intents", [])
    print(f"\n[5.2] Intentions proposées ({len(intents)}) :")
    parcelle_used_as_group = False
    for i, intent in enumerate(intents):
        action = intent.get("action")
        target = intent.get("target_col")
        group = intent.get("group_col")
        print(f"  {i+1}. action={action}, target={target}, group={group}")
        
        if group == "Parcelle":
            parcelle_used_as_group = True
            print(f"    ❌ ERREUR : 'Parcelle' utilisé comme group_col (50 modalités)")
        else:
            print(f"    ✅ OK : group_col != 'Parcelle'")
    
    if not parcelle_used_as_group:
        print("\n✅ SUCCÈS : 'Parcelle' n'est PAS utilisé comme group_col")
    
    # Vérifier action_executed
    action_executed = result.get("action_executed")
    print(f"\n[5.3] action_executed : {action_executed}")
    
    # Vérifier les justifications (garde-fou statistique)
    audit_log = result.get("audit_log", [])
    print(f"\n[5.4] Audit log ({len(audit_log)} entrées) :")
    guardrail_triggered = False
    for entry in audit_log:
        etape = entry.get("etape")
        justification = entry.get("justification", "")
        print(f"  - {etape}: {justification[:100]}...")
        
        if "Parcelle" in justification and ("50" in justification or "30" in justification or "modalité" in justification.lower()):
            guardrail_triggered = True
            print(f"    ✅ OK : Garde-fou statistique mentionne 'Parcelle' avec haute cardinalité")
    
    if guardrail_triggered:
        print("\n✅ SUCCÈS : Garde-fou statistique activé pour 'Parcelle'")
    else:
        print("\n⚠️ ATTENTION : Garde-fou statistique non détecté dans les justifications")
    
    # Afficher le JSON complet pour inspection
    print("\n" + "=" * 80)
    print("RÉSULTAT JSON COMPLET")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
