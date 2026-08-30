"""
Test manuel pour valider la robustesse face aux valeurs manquantes extrêmes (60-80%) :
- Uploader le fichier test_extreme_missing.csv
- Lancer /analyze en mode auto
- Vérifier que les calculs statistiques gèrent correctement les valeurs manquantes
- Vérifier que le diagnostic ne crash pas malgré très peu de données valides
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
    print("TEST MANUEL - VALEURS MANQUANTES EXTRÊMES (60-80%)")
    print("=" * 80)
    
    # 1. Upload du fichier
    print("\n[1] Upload du fichier test_extreme_missing.csv...")
    file_path = Path(__file__).parent / "test_extreme_missing.csv"
    
    with open(file_path, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test_extreme_missing.csv", f, "text/csv")}
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
    numeric_cols = diagnosis.get("numeric_cols", [])
    cat_cols = diagnosis.get("cat_cols", [])
    print(f"\n[5.1] Colonnes numériques : {numeric_cols}")
    print(f"[5.2] Colonnes catégorielles : {cat_cols}")
    
    # Vérifier les intentions proposées
    intents = result.get("intents", [])
    print(f"\n[5.3] Intentions proposées ({len(intents)}) :")
    for i, intent in enumerate(intents):
        action = intent.get("action")
        target = intent.get("target_col")
        group = intent.get("group_col")
        print(f"  {i+1}. action={action}, target={target}, group={group}")
    
    # Vérifier action_executed
    action_executed = result.get("action_executed")
    print(f"\n[5.4] action_executed : {action_executed}")
    
    # Vérifier que le diagnostic n'a pas crashé malgré les valeurs manquantes
    if action_executed and action_executed != "failed":
        print("✅ SUCCÈS : Analyse terminée malgré 60-80% de valeurs manquantes")
    else:
        print("❌ ERREUR : Analyse échouée à cause des valeurs manquantes")
    
    # Vérifier les justifications
    audit_log = result.get("audit_log", [])
    print(f"\n[5.5] Audit log ({len(audit_log)} entrées) :")
    for entry in audit_log:
        etape = entry.get("etape")
        justification = entry.get("justification", "")
        print(f"  - {etape}: {justification[:100]}...")
        
        if "manquant" in justification.lower() or "missing" in justification.lower():
            print(f"    ✅ OK : Système a détecté les valeurs manquantes")
    
    # Afficher le JSON complet pour inspection
    print("\n" + "=" * 80)
    print("RÉSULTAT JSON COMPLET")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
