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
import resource

def _rss_mo():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

print(f"MEM CHECKPOINT [tout début fichier, avant sys.path.insert] : {_rss_mo():.1f} Mo", flush=True)

# Ajouter le répertoire racine au PYTHONPATH pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

print(f"MEM CHECKPOINT [après sys.path.insert] : {_rss_mo():.1f} Mo", flush=True)
print(f"MODULES DEJA CHARGES : {sorted(m for m in sys.modules if m.split('.')[0] in ('pandas','numpy','matplotlib','scipy','statsmodels','sklearn','weasyprint'))}", flush=True)

# Configuration pour sortie non tamponnée
sys.stdout.reconfigure(line_buffering=True)


def _mem_checkpoint(label: str) -> None:
    mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"MEM CHECKPOINT [{label}] : {mb:.1f} Mo", flush=True)

def main():
    if len(sys.argv) < 4:
        sys.exit(1)

    _mem_checkpoint("début main")

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    theme = sys.argv[3]

    # Charger les données
    with open(input_path, 'r', encoding='utf-8') as f:
        analysis_result = json.load(f)

    _mem_checkpoint("après chargement JSON")

    print(f"MODULES AVANT IMPORT REPORT_GENERATOR : {sorted(m for m in sys.modules if m.split('.')[0] in ('pandas','numpy','matplotlib','scipy','statsmodels','sklearn','weasyprint'))}", flush=True)

    # Importer WeasyPrint uniquement dans ce processus
    from app.report_generator import generate_pdf_chunked, generate_pdf_report

    _mem_checkpoint("après import report_generator")

    pdf_bytes = None
    try:
        pdf_bytes = generate_pdf_chunked(analysis_result, theme=theme)
    except Exception as e:
        print(f"generate_pdf_chunked a échoué, tentative avec generate_pdf_report: {e}")

    if not pdf_bytes:
        pdf_bytes = generate_pdf_report(analysis_result, theme=theme)
    
    if pdf_bytes:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
