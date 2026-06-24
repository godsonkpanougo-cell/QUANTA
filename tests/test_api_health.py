"""Test API : GET /health."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state

if __name__ == "__main__":
    reset_api_state()
    client = get_client()
    response = client.get("/health")
    if response.status_code != 200:
        print(f"\nÉCHEC : status={response.status_code}")
        sys.exit(1)
    data = response.json()
    if data.get("status") != "ok" or data.get("service") != "quanta-api":
        print(f"\nÉCHEC : payload inattendu {data}")
        sys.exit(1)
    print(f"OK : /health -> {data}")
