"""Test API : /status avec analysis_id inexistant -> 404."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    response = client.get("/status/00000000-0000-0000-0000-000000000000")
    if response.status_code != 404:
        print(f"\nÉCHEC : status attendu 404, obtenu={response.status_code}")
        sys.exit(1)
    print("OK : /status analysis_id inexistant -> 404")
