"""Test API : /upload avec extension non supportée -> 400."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    response = client.post(
        "/upload",
        files={"file": ("corrupt.xyz", b"not,a,valid\n", "application/octet-stream")},
    )
    if response.status_code != 400:
        print(f"\nÉCHEC : status attendu 400, obtenu={response.status_code}")
        sys.exit(1)
    detail = response.json().get("detail", "")
    if "Impossible de lire le fichier" not in detail:
        print(f"\nÉCHEC : message inattendu : {detail}")
        sys.exit(1)
    print(f"OK : /upload invalide -> 400 ({detail[:80]}...)")
