"""
Test manuel pour valider le comportement sur dataset large (45 colonnes) :
- Uploader le fichier test_wide_dataset.csv
- Lancer /analyze en mode auto
- Vérifier que le système gère correctement le grand nombre de colonnes
- Vérifier que brain.analyze_with_brain ne crash pas
- Vérifier que le rapport ne dépasse pas les limites de taille
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
    print("TEST MANUEL - DATASET LARGE (45 COLONNES)")
    print("=" * 80)
    
    # 1. Upload du fichier
    print("\n[1] Upload du fichier test_wide_dataset.csv...")
    file_path = Path(__file__).parent / "test_wide_dataset.csv"
    
    with open(file_path, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test_wide_dataset.csv", f, "text/csv")}
        )
    
    print(f"Upload status : {upload_response.status_code}")
    
    if upload_response.status_code != 200:
        print(f"Erreur upload : {upload_response.text}")
        return
    
    upload_data = upload_response.json()
    file_id = upload_data.get("file_id")
    print(f"File ID : {file_id}")
    
    # Vérifier le nombre de colonnes détecté
    n_cols = upload_data.get("n_cols")
    print(f"Colonnes détectées : {n_cols}")
    
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
    max_wait = 90  # Plus long pour dataset large
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
        
        time.sleep(3)
        waited += 3
    
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
    print(f"\n[5.1] Colonnes numériques : {len(numeric_cols)}")
    print(f"[5.2] Colonnes catégorielles : {len(cat_cols)}")
    print(f"[5.3] Total colonnes : {len(numeric_cols) + len(cat_cols)}")
    
    if len(numeric_cols) + len(cat_cols) == 45:
        print("✅ OK : Toutes les 45 colonnes détectées")
    else:
        print(f"⚠️ ATTENTION : Nombre de colonnes détectées != 45")
    
    # Vérifier les intentions proposées
    intents = result.get("intents", [])
    print(f"\n[5.4] Intentions proposées ({len(intents)}) :")
    for i, intent in enumerate(intents[:5]):  # Afficher les 5 premières
        action = intent.get("action")
        target = intent.get("target_col")
        group = intent.get("group_col")
        print(f"  {i+1}. action={action}, target={target}, group={group}")
    
    if len(intents) > 5:
        print(f"  ... et {len(intents) - 5} autres intentions")
    
    # Vérifier action_executed
    action_executed = result.get("action_executed")
    print(f"\n[5.5] action_executed : {action_executed}")
    
    # Vérifier que brain.analyze_with_brain n'a pas crashé
    if action_executed and action_executed != "failed":
        print("✅ SUCCÈS : brain.analyze_with_brain a terminé sans crash")
    else:
        print("❌ ERREUR : brain.analyze_with_brain a échoué")
    
    # Afficher le JSON complet pour inspection
    print("\n" + "=" * 80)
    print("RÉSULTAT JSON COMPLET")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
