"""Test orchestrateur : fichier corrompu -> error + status failed sans exception."""
from __future__ import annotations

import sys

from app.compute.test_selector import AnalysisIntent
from tests._print_orchestrator import run_orchestrator_sample

if __name__ == "__main__":
    result = run_orchestrator_sample(
        None,
        AnalysisIntent(raw_query="fichier invalide"),
        label="fichier corrompu",
        file_bytes=b"contenu invalide",
        filename="corrupt.xyz",
    )
    if result.get("status") != "failed":
        print(f"\nÉCHEC : status attendu 'failed', obtenu {result.get('status')!r}")
        sys.exit(1)
    if "error" not in result:
        print("\nÉCHEC : clé 'error' absente")
        sys.exit(1)
    print(f"\nOK : erreur capturée proprement : {result['error'][:80]}...")
