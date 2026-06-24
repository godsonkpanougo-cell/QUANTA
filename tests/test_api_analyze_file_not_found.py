"""Test API : /analyze avec file_id inexistant -> 404."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    response = client.post(
        "/analyze",
        json={"file_id": "00000000-0000-0000-0000-000000000000", "query": "test"},
    )
    if response.status_code != 404:
        print(f"\nÉCHEC : status attendu 404, obtenu={response.status_code}")
        sys.exit(1)
    print("OK : /analyze file_id inexistant -> 404")
