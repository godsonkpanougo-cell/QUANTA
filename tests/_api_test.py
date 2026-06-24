"""Helpers communs pour les tests de l'API FastAPI (TestClient)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import main


def get_client() -> TestClient:
    return TestClient(main.app)


def reset_api_state() -> None:
    """Réinitialise la base SQLite entre les scripts de test API in-process."""
    import db

    db.clear_all()


def sample_path(name: str) -> Path:
    path = ROOT / "data" / "samples" / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def assert_json_serializable(obj: Any, label: str = "response") -> None:
    json.dumps(obj, ensure_ascii=False)
    print(f"json.dumps({label}) : OK")


def upload_sample(client: TestClient, csv_name: str) -> dict[str, Any]:
    path = sample_path(csv_name)
    with path.open("rb") as f:
        response = client.post("/upload", files={"file": (path.name, f, "text/csv")})
    return response


def poll_status(client: TestClient, analysis_id: str) -> dict[str, Any]:
    response = client.get(f"/status/{analysis_id}")
    if response.status_code != 200:
        raise RuntimeError(f"GET /status failed: {response.status_code} {response.text}")
    return response.json()


def llm_is_configured() -> bool:
    keys = (
        __import__("os").environ.get("PRIMARY_API_KEY", ""),
        __import__("os").environ.get("GROQ_API_KEY", ""),
        __import__("os").environ.get("FALLBACK_API_KEY", ""),
        __import__("os").environ.get("OPENROUTER_API_KEY", ""),
    )
    return any(k and k.strip() for k in keys)
