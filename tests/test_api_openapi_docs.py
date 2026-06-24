"""Test API : schéma OpenAPI expose les 5 endpoints attendus."""
from __future__ import annotations

import sys

from tests._api_test import get_client, reset_api_state

EXPECTED_PATHS = {"/health", "/upload", "/analyze", "/status/{analysis_id}", "/history"}

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    response = client.get("/openapi.json")
    if response.status_code != 200:
        print(f"\nÉCHEC : /openapi.json status={response.status_code}")
        sys.exit(1)

    paths = set(response.json().get("paths", {}).keys())
    missing = EXPECTED_PATHS - paths
    if missing:
        print(f"\nÉCHEC : endpoints manquants dans OpenAPI : {missing}")
        sys.exit(1)

    docs_resp = client.get("/docs")
    if docs_resp.status_code != 200:
        print(f"\nÉCHEC : /docs status={docs_resp.status_code}")
        sys.exit(1)

    print(f"OK : OpenAPI + /docs — endpoints : {sorted(EXPECTED_PATHS)}")
