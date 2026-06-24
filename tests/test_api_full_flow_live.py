"""Test API : flux complet live avec Groq (upload -> analyze -> interprétation)."""
from __future__ import annotations

import sys

from tests._api_test import (
    assert_json_serializable,
    get_client,
    llm_is_configured,
    poll_status,
    reset_api_state,
    upload_sample,
)

if __name__ == "__main__":
    if not llm_is_configured():
        print("SKIP : aucune clé API LLM configurée (.env) — test live ignoré")
        sys.exit(0)

    reset_api_state()
    client = get_client()

    upload_resp = upload_sample(client, "region_likert.csv")
    if upload_resp.status_code != 200:
        print(f"\nÉCHEC upload : {upload_resp.text}")
        sys.exit(1)
    file_id = upload_resp.json()["file_id"]

    analyze_resp = client.post(
        "/analyze",
        json={"file_id": file_id, "query": "comparer le revenu entre régions"},
    )
    if analyze_resp.status_code != 200:
        print(f"\nÉCHEC analyze : {analyze_resp.text}")
        sys.exit(1)
    analysis_id = analyze_resp.json()["analysis_id"]

    status = poll_status(client, analysis_id)
    if status["status"] != "done":
        print(f"\nÉCHEC : status={status.get('status')} error={status.get('error')}")
        sys.exit(1)

    result = status["result"]
    assert_json_serializable(result, "full_result")

    intent = result.get("intent", {})
    interpretation = result.get("interpretation", {})
    analysis = result.get("analysis", {})

    if intent.get("action") != "compare_groups":
        print(f"\nÉCHEC : intent.action={intent.get('action')!r}")
        sys.exit(1)
    if analysis.get("status") != "ok":
        print(f"\nÉCHEC : analysis.status={analysis.get('status')!r}")
        sys.exit(1)
    if not interpretation.get("llm_available"):
        print(f"\nÉCHEC : interprétation indisponible — {interpretation.get('reason')}")
        sys.exit(1)

    levels = interpretation.get("interpretation_principale", {})
    for key in ("niveau_technique", "niveau_analytique", "niveau_decisionnel"):
        if not levels.get(key, "").strip():
            print(f"\nÉCHEC : niveau manquant : {key}")
            sys.exit(1)

    print(f"OK : flux API complet live (analysis_id={analysis_id}, LLM OK)")
