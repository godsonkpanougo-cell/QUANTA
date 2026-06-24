"""Test API : /analyze avec query vide -> 422."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state, upload_sample

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    upload_resp = upload_sample(client, "clean.csv")
    file_id = upload_resp.json()["file_id"]

    for payload in ({"file_id": file_id, "query": ""}, {"file_id": file_id, "query": "   "}):
        response = client.post("/analyze", json=payload)
        if response.status_code != 422:
            print(f"\nÉCHEC : query={payload['query']!r} -> status={response.status_code}")
            sys.exit(1)

    print("OK : /analyze query vide -> 422")
