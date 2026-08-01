"""
Test API : export Excel français (Latin-1, séparateur ;, virgule décimale).

Vérifie le parcours complet /upload -> /analyze -> /status et que les
colonnes numériques (revenu_annuel, score, etc.) sont bien détectées.
"""
from __future__ import annotations

import sys

from tests._api_test import (
    assert_json_serializable,
    get_client,
    poll_status,
    reset_api_state,
    upload_sample,
)

EXPECTED_NUMERIC = {"age", "revenu_annuel", "score"}


def main() -> int:
    reset_api_state()
    client = get_client()

    upload_resp = upload_sample(client, "french_excel_export.csv")
    if upload_resp.status_code != 200:
        print(f"\nÉCHEC upload : {upload_resp.status_code} {upload_resp.text}")
        return 1
    upload_data = upload_resp.json()
    file_id = upload_data["file_id"]
    assert_json_serializable(upload_data, "upload")

    upload_numeric = set(upload_data.get("numeric_cols", []))
    if not EXPECTED_NUMERIC.issubset(upload_numeric):
        print(
            f"\nÉCHEC : colonnes numériques non détectées à l'upload : "
            f"attendu {EXPECTED_NUMERIC}, obtenu {upload_numeric}"
        )
        return 1

    analyze_resp = client.post(
        "/analyze",
        json={
            "file_id": file_id,
            "query": "comparer le revenu annuel entre les régions",
        },
    )
    if analyze_resp.status_code != 200:
        print(f"\nÉCHEC analyze : {analyze_resp.status_code} {analyze_resp.text}")
        return 1
    analysis_id = analyze_resp.json()["analysis_id"]

    status = poll_status(client, analysis_id)
    if status["status"] != "done":
        print(f"\nÉCHEC : status={status.get('status')}, error={status.get('error')}")
        return 1

    result = status["result"]
    assert_json_serializable(status, "status")

    analysis = result.get("analysis", {})
    if analysis.get("status") != "ok":
        print(f"\nÉCHEC : analysis.status={analysis.get('status')}")
        return 1

    diag = analysis.get("diagnosis", {})
    numeric = set(diag.get("numeric_cols", []))
    if not EXPECTED_NUMERIC.issubset(numeric):
        print(
            f"\nÉCHEC : colonnes numériques non converties : "
            f"attendu {EXPECTED_NUMERIC}, obtenu {numeric}"
        )
        return 1

    desc = analysis.get("descriptive", {}).get("descriptive_numeric", {})
    if not desc.get("revenu_annuel"):
        print("\nÉCHEC : stats descriptives absentes pour revenu_annuel")
        return 1

    print(
        f"OK : french_excel_export.csv — "
        f"n_rows={diag.get('n_rows')}, numeric_cols={sorted(numeric)}, "
        f"revenu mean={desc['revenu_annuel'].get('mean')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
