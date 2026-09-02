"""Test manuel direct pour vérifier la génération PDF avec section ACP."""
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.compute.compute import run_acp
from app.report_generator import _html_acp_section, generate_pdf_report

def test_acp_report_direct():
    """Test direct de la génération ACP sans API (contourne erreur LLM)."""
    print("=== TEST DIRECT : Génération PDF avec section ACP ===")
    
    # 1. Charger le dataset
    print("\n1. Chargement du dataset test_acp_numeric_id.csv...")
    df = pd.read_csv("tests/test_acp_numeric_id.csv")
    print(f"Dataset chargé: {df.shape}")
    
    # 2. Exécuter l'ACP
    print("\n2. Exécution de run_acp()...")
    numeric_cols = ["SUP_HA", "Rendement", "Production"]
    acp_result = run_acp(df, numeric_cols)
    print(f"ACP status: {acp_result.get('status')}")
    
    if acp_result.get("status") != "ok":
        print(f"ACP error: {acp_result.get('error')}")
        return
    
    print(f"ACP n_rows: {acp_result.get('n_rows')}")
    print(f"ACP n_variables: {acp_result.get('n_variables')}")
    print(f"ACP n_components: {acp_result.get('n_components')}")
    
    # Vérifier la présence des graphiques
    print("\nGraphiques dans acp_result:")
    print(f"  scree_plot: {'présent' if acp_result.get('scree_plot') else 'ABSENT'}")
    print(f"  correlation_circle: {'présent' if acp_result.get('correlation_circle') else 'ABSENT'}")
    print(f"  individuals_plot: {'présent' if acp_result.get('individuals_plot') else 'ABSENT'}")
    print(f"  correlation_circle_coords: {len(acp_result.get('correlation_circle_coords', []))} entrées")
    
    # 3. Tester _html_acp_section
    print("\n3. Test de _html_acp_section()...")
    table_counter = [0]
    html_section = _html_acp_section(acp_result, table_counter)
    
    if not html_section:
        print("ERREUR: _html_acp_section() a retourné une chaîne vide")
        return
    
    print(f"HTML section généré: {len(html_section)} caractères")
    print(f"Table counter après: {table_counter[0]}")
    
    # Vérifier que les éléments clés sont présents
    checks = {
        "Analyse en Composantes Principales": "Analyse en Composantes Principales" in html_section,
        "Note d'interprétation": "Note d'interprétation" in html_section,
        "Valeurs propres": "Valeurs propres" in html_section,
        "Cercle des corrélations": "Cercle des corrélations" in html_section,
        "Plan des individus": "Plan des individus" in html_section,
        "Images base64 (scree_plot)": "data:image/png;base64" in html_section,
        "Images base64 count": html_section.count("data:image/png;base64") >= 3,
    }
    
    print("\nVérifications HTML:")
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
    
    if not all(checks.values()):
        print("\nERREUR: Certains éléments HTML manquent")
        return
    
    # 4. Construire un résultat complet pour generate_pdf_report
    print("\n4. Test de génération PDF complet...")
    
    # Simuler une analyse complète avec résultat ACP
    analysis_result = {
        "intent": {"action": "correlation", "target": "SUP_HA", "group": "Rendement"},
        "analysis": {
            "diagnosis": {
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "numeric_cols": numeric_cols,
                "cat_cols": [],
                "id_cols": ["id"]
            },
            "inference": {
                "result": {
                    "acp": acp_result
                }
            }
        },
        "interpretation": {
            "interpretation_principale": {
                "niveau_technique": "Test de la section ACP dans le rapport PDF.",
                "niveau_analytique": "L'ACP a été exécutée avec succès.",
                "niveau_decisionnel": "La section ACP est correctement intégrée."
            }
        }
    }
    
    # Générer le PDF (theme=dark)
    print("\n5. Génération PDF theme=dark...")
    try:
        pdf_bytes_dark = generate_pdf_report(analysis_result, theme="dark")
        pdf_size_dark = len(pdf_bytes_dark)
        print(f"PDF dark généré: {pdf_size_dark} bytes ({pdf_size_dark/1024:.2f} KB)")
        
        # Sauvegarder le PDF dark
        output_path_dark = "tests/output_acp_test_dark.pdf"
        with open(output_path_dark, "wb") as f:
            f.write(pdf_bytes_dark)
        print(f"PDF dark sauvegardé: {output_path_dark}")
    except Exception as e:
        print(f"ERREUR génération PDF dark: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Générer le PDF (theme=light)
    print("\n6. Génération PDF theme=light...")
    try:
        pdf_bytes_light = generate_pdf_report(analysis_result, theme="light")
        pdf_size_light = len(pdf_bytes_light)
        print(f"PDF light généré: {pdf_size_light} bytes ({pdf_size_light/1024:.2f} KB)")
        
        # Sauvegarder le PDF light
        output_path_light = "tests/output_acp_test_light.pdf"
        with open(output_path_light, "wb") as f:
            f.write(pdf_bytes_light)
        print(f"PDF light sauvegardé: {output_path_light}")
    except Exception as e:
        print(f"ERREUR génération PDF light: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== SUCCÈS ===")
    print(f"Returncode dark: 0")
    print(f"Returncode light: 0")
    print(f"Taille PDF dark: {pdf_size_dark/1024:.2f} KB")
    print(f"Taille PDF light: {pdf_size_light/1024:.2f} KB")

if __name__ == "__main__":
    test_acp_report_direct()
