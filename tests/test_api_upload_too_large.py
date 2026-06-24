"""Test API : /upload fichier > MAX_FILE_SIZE_BYTES -> 413."""
from __future__ import annotations

import sys

import main
from tests._api_test import get_client, reset_api_state

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    oversized = b"x" * (main.MAX_FILE_SIZE_BYTES + 1)
    response = client.post(
        "/upload",
        files={"file": ("huge.csv", oversized, "text/csv")},
    )
    if response.status_code != 413:
        print(f"\nÉCHEC : status attendu 413, obtenu={response.status_code}")
        sys.exit(1)
    detail = response.json().get("detail", "")
    if "trop volumineux" not in detail.lower():
        print(f"\nÉCHEC : message inattendu : {detail}")
        sys.exit(1)
    print(f"OK : /upload > 10 Mo -> 413")
