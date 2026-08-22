#!/usr/bin/env python3
"""
PDF Worker — exécuté en subprocess séparé.
Reçoit le chemin vers un fichier JSON contenant
analysis_result, génère le PDF, écrit le résultat.
Usage: python pdf_worker.py input.json output.pdf dark
"""
import sys
import json
import os
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    if len(sys.argv) < 4:
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    theme = sys.argv[3]
    
    # Charger les données
    with open(input_path, 'r', encoding='utf-8') as f:
        analysis_result = json.load(f)
    
    # Importer WeasyPrint uniquement dans ce processus
    from app.report_generator import generate_pdf_report
    
    pdf_bytes = generate_pdf_report(
        analysis_result, theme=theme
    )
    
    if pdf_bytes:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
