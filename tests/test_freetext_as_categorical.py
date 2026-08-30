"""
Test manuel pour valider la détection de texte libre mal classé comme catégoriel :
- Uploader le fichier test_freetext_as_categorical.csv
- Lancer /analyze en mode auto
- Vérifier que "Commentaire" (texte libre, 150 valeurs uniques) n'est pas utilisé comme variable de groupement
- Vérifier que le système utilise les colonnes catégorielles appropriées (Type_Experience)
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
    print("TEST MANUEL - TEXTE LIBRE COMME CATÉGORIEL")
    print("=" * 80)
    
    # 1. Upload du fichier
    print("\n[1] Upload du fichier test_freetext_as_categorical.csv...")
    file_path = Path(__file__).parent / "test_freetext_as_categorical.csv"
    
    with open(file_path, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test_freetext_as_categorical.csv", f, "text/csv")}
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
    
    if "Commentaire" in cat_cols:
        print("⚠️ ATTENTION : 'Commentaire' classé comme catégoriel (texte libre)")
    else:
        print("✅ OK : 'Commentaire' n'est PAS classé comme catégoriel")
    
    # Vérifier les intentions proposées
    intents = result.get("intents", [])
    print(f"\n[5.2] Intentions proposées ({len(intents)}) :")
    commentaire_used_as_group = False
    type_experience_used = False
    for i, intent in enumerate(intents):
        action = intent.get("action")
        target = intent.get("target_col")
        group = intent.get("group_col")
        print(f"  {i+1}. action={action}, target={target}, group={group}")
        
        if group == "Commentaire":
            commentaire_used_as_group = True
            print(f"    ❌ ERREUR : 'Commentaire' utilisé comme group_col (texte libre)")
        
        if group == "Type_Experience":
            type_experience_used = True
            print(f"    ✅ OK : 'Type_Experience' utilisé comme group_col (catégoriel approprié)")
    
    if not commentaire_used_as_group:
        print("\n✅ SUCCÈS : 'Commentaire' n'est PAS utilisé comme group_col")
    
    if type_experience_used:
        print("✅ SUCCÈS : 'Type_Experience' utilisé comme group_col (alternative appropriée)")
    
    # Vérifier action_executed
    action_executed = result.get("action_executed")
    print(f"\n[5.3] action_executed : {action_executed}")
    
    # Afficher le JSON complet pour inspection
    print("\n" + "=" * 80)
    print("RÉSULTAT JSON COMPLET")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
