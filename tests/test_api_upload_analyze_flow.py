"""Test API : parcours /upload -> /analyze -> /status sur dataset simple."""
from __future__ import annotations

import sys

from tests._api_test import (
    assert_json_serializable,
    get_client,
    poll_status,
    reset_api_state,
    upload_sample,
)

if __name__ == "__main__":
    reset_api_state()
    client = get_client()

    upload_resp = upload_sample(client, "clean.csv")
    if upload_resp.status_code != 200:
        print(f"\nÉCHEC upload : {upload_resp.status_code} {upload_resp.text}")
        sys.exit(1)
    upload_data = upload_resp.json()
    file_id = upload_data["file_id"]
    assert_json_serializable(upload_data, "upload")

    analyze_resp = client.post(
        "/analyze",
        json={"file_id": file_id, "query": "corrélation entre age et income"},
    )
    if analyze_resp.status_code != 200:
        print(f"\nÉCHEC analyze : {analyze_resp.status_code} {analyze_resp.text}")
        sys.exit(1)
    analysis_id = analyze_resp.json()["analysis_id"]

    status = poll_status(client, analysis_id)
    if status["status"] != "done":
        print(f"\nÉCHEC : status attendu done, obtenu={status}")
        sys.exit(1)

    result = status["result"]
    assert_json_serializable(status, "status")
    if result.get("analysis", {}).get("status") != "ok":
        print(f"\nÉCHEC : pipeline analysis.status != ok")
        sys.exit(1)

    history = client.get("/history")
    if history.status_code != 200 or history.json().get("count", 0) < 1:
        print(f"\nÉCHEC : /history vide ou erreur")
        sys.exit(1)

    print(f"OK : flux upload/analyze/status (analysis_id={analysis_id})")
