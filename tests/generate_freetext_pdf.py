"""
Script pour générer un PDF sur test_freetext_as_categorical.csv et le sauvegarder
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from fastapi.testclient import TestClient
import main
import time

client = TestClient(main.app)

print("=" * 80)
print("GÉNÉRATION PDF SUR test_freetext_as_categorical.csv")
print("=" * 80)

# 1. Upload
file_path = Path(__file__).parent / "test_freetext_as_categorical.csv"
with open(file_path, 'rb') as f:
    upload_response = client.post(
        "/upload",
        files={"file": ("test_freetext_as_categorical.csv", f, "text/csv")}
    )

print(f"Upload status : {upload_response.status_code}")
file_id = upload_response.json().get("file_id")
print(f"File ID : {file_id}")

# 2. Analyze
analyze_response = client.post(
    "/analyze",
    json={
        "file_id": file_id,
        "query": ""
    }
)

print(f"Analyze status : {analyze_response.status_code}")
analysis_id = analyze_response.json().get("analysis_id")
print(f"Analysis ID : {analysis_id}")

# 3. Attendre fin
max_wait = 120
waited = 0
while waited < max_wait:
    status_response = client.get(f"/status/{analysis_id}")
    status_data = status_response.json()
    status = status_data.get("status")
    
    if status in ["done", "error"]:
        break
    
    time.sleep(2)
    waited += 2
    print(f"  Status : {status} ({waited}s)")

if status != "done":
    print(f"Erreur : analyse terminée avec statut '{status}'")
    sys.exit(1)

# 4. Télécharger PDF
pdf_response = client.get(f"/report/{analysis_id}?theme=dark")
print(f"PDF download status : {pdf_response.status_code}")

if pdf_response.status_code == 200:
    output_path = Path(__file__).parent / "output_variables_freetext.pdf"
    with open(output_path, 'wb') as f:
        f.write(pdf_response.content)
    print(f"✓ PDF sauvegardé : {output_path}")
else:
    print("✗ Erreur téléchargement PDF")
    sys.exit(1)
