"""Test API : /analyze avec query vide -> 200 (mode autonome)."""
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
        if response.status_code != 200:
            print(f"\nÉCHEC : query={payload['query']!r} -> status={response.status_code}")
            sys.exit(1)
        data = response.json()
        if "analysis_id" not in data:
            print(f"\nÉCHEC : query={payload['query']!r} -> pas de analysis_id dans la réponse")
            sys.exit(1)

    print("OK : /analyze query vide -> 200 + analysis_id (mode autonome)")
