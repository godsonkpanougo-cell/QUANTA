"""Vérification finale : génère un PDF avec V de Cramér + IC visible."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from app.orchestrator import run_full_analysis, auto_intent
from app.compute.compute import load_and_diagnose
from app.compute.test_selector import AnalysisIntent
from app.report_generator import generate_pdf_report

if __name__ == "__main__":
    print("=" * 72)
    print("VERIFICATION FINALE : IC bootstrap V de Cramér dans PDF")
    print("=" * 72)
    
    # Créer un dataset catégoriel pour test chi²
    np.random.seed(42)
    n = 100
    data = {
        "sexe": np.random.choice(["H", "F"], n),
        "preference": np.random.choice(["A", "B", "C"], n),
    }
    df = pd.DataFrame(data)
    csv_content = df.to_csv(index=False)
    
    # Exécuter l'analyse
    diagnosis = load_and_diagnose(csv_content.encode(), "test_verify_cramers_v.csv")
    intents = auto_intent(diagnosis)
    
    # Chercher un intent d'association
    association_intent = None
    for intent in intents:
        if intent.action == "association":
            association_intent = intent
            break
    
    if association_intent is None:
        # Forcer un intent d'association
        association_intent = AnalysisIntent(
            action="association",
            target_col="sexe",
            group_col="preference",
            raw_query="Test association sexe x preference",
        )
    
    print(f"\nIntent: action={association_intent.action}, target={association_intent.target_col}, group={association_intent.group_col}")
    
    result = run_full_analysis(csv_content.encode(), "test_verify_cramers_v.csv", intent=association_intent, theme="dark")
    
    # Vérifier que les IC sont présents dans le résultat
    inference_result = result.get("inference", {}).get("result", {})
    print(f"\n--- Résultat d'inférence ---")
    print(f"Test: {inference_result.get('test')}")
    print(f"V de Cramér: {inference_result.get('cramers_v')}")
    print(f"V de Cramér CI: [{inference_result.get('cramers_v_ci_lower')}, {inference_result.get('cramers_v_ci_upper')}]")
    
    # Générer le PDF
    print(f"\n--- Génération PDF ---")
    try:
        pdf_path = ROOT / "tests" / "output_verify_cramers_v.pdf"
        pdf_bytes = generate_pdf_report(result, theme="dark")
        
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        
        print(f"PDF généré: {pdf_path}")
        
        # Extraire le texte du PDF pour vérifier
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                pdf_reader = pypdf.PdfReader(f)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
            
            print(f"\n--- Extrait texte PDF ---")
            # Chercher les IC dans le texte
            if "[" in text and "]" in text:
                # Trouver les patterns de type "valeur [valeur, valeur]"
                import re
                ic_pattern = r'\d+\.\d+\s*\[\s*\d+\.\d+\s*,\s*\d+\.\d+\s*\]'
                matches = re.findall(ic_pattern, text)
                if matches:
                    print(f"IC bootstrap détectés dans le PDF: {matches}")
                else:
                    print("[WARNING] Aucun IC détecté dans le texte du PDF")
            else:
                print("[WARNING] Pas de crochets détectés dans le texte du PDF")
            
            # Afficher un extrait autour de "Cramér"
            if "Cramér" in text:
                idx = text.find("Cramér")
                if idx >= 0:
                    excerpt = text[max(0, idx-100):min(len(text), idx+200)]
                    print(f"\nExtrait autour de 'Cramér':\n{excerpt}")
            
        except ImportError:
            print("pypdf non installé - impossible d'extraire le texte du PDF")
            print("Vérifiez manuellement le PDF généré: tests/output_verify_cramers_v.pdf")
        
    except Exception as e:
        print(f"ERREUR génération PDF: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 72)
    print("CONCLUSION : Vérification IC bootstrap V de Cramér dans PDF")
    print("Vérifiez visuellement le PDF généré pour confirmer la présence des IC.")
    print("=" * 72)
