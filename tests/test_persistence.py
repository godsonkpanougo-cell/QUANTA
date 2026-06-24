"""
Test critique J21 — persistance SQLite survit au redémarrage du serveur.

Ce test lance un vrai process uvicorn, exécute upload + analyse, ARRÊTE
le serveur, le RELANCE, puis vérifie que /status et /history retrouvent
l'analyse. Pas de TestClient in-process : le redémarrage process est
obligatoire pour valider la migration.

Commande :
    python -m tests.test_persistence
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TEST_PORT = int(os.environ.get("QUANTA_PERSISTENCE_PORT", "8765"))
POLL_INTERVAL_S = 1
POLL_TIMEOUT_S = 120
STARTUP_TIMEOUT_S = 30


def _base_url() -> str:
    return f"http://127.0.0.1:{TEST_PORT}"


def _sample_path(name: str) -> Path:
    path = ROOT / "data" / "samples" / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _wait_for_health(base_url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Serveur non prêt après {timeout_s}s sur {base_url}")


def _start_server(db_path: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["QUANTA_DB_PATH"] = str(db_path)
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1",
            "--port", str(TEST_PORT),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    _wait_for_health(_base_url(), STARTUP_TIMEOUT_S)
    return proc


def _stop_server(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    if proc.stderr:
        proc.stderr.read()


def _upload_and_analyze(base_url: str) -> tuple[str, dict[str, Any]]:
    path = _sample_path("clean.csv")
    with path.open("rb") as f:
        upload_resp = requests.post(
            f"{base_url}/upload",
            files={"file": (path.name, f, "text/csv")},
            timeout=30,
        )
    if upload_resp.status_code != 200:
        raise RuntimeError(f"POST /upload -> {upload_resp.status_code}: {upload_resp.text}")

    file_id = upload_resp.json()["file_id"]
    analyze_resp = requests.post(
        f"{base_url}/analyze",
        json={"file_id": file_id, "query": "corrélation entre age et income"},
        timeout=10,
    )
    if analyze_resp.status_code != 200:
        raise RuntimeError(f"POST /analyze -> {analyze_resp.status_code}: {analyze_resp.text}")

    analysis_id = analyze_resp.json()["analysis_id"]

    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        status_resp = requests.get(f"{base_url}/status/{analysis_id}", timeout=10)
        if status_resp.status_code != 200:
            raise RuntimeError(f"GET /status -> {status_resp.status_code}: {status_resp.text}")
        payload = status_resp.json()
        if payload.get("status") in ("done", "error"):
            if payload.get("status") != "done":
                raise RuntimeError(f"Analyse en erreur : {payload.get('error')}")
            return analysis_id, payload
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(f"Analyse {analysis_id} non terminée après {POLL_TIMEOUT_S}s")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "persistence_test.db"

        print("=" * 72)
        print("TEST PERSISTENCE J21 — redémarrage process uvicorn")
        print(f"Port     : {TEST_PORT}")
        print(f"DB path  : {db_path}")
        print("=" * 72)

        print("\n[1/4] Démarrage serveur (process 1)...")
        proc1 = _start_server(db_path)

        try:
            print("[2/4] Upload + analyse + attente done...")
            analysis_id, first_status = _upload_and_analyze(_base_url())
            print(f"      analysis_id={analysis_id}, status=done")

            print("[3/4] Arrêt serveur (kill process 1)...")
            _stop_server(proc1)
            proc1 = None
            time.sleep(1)

            print("[4/4] Redémarrage serveur (process 2, même DB)...")
            proc2 = _start_server(db_path)

            try:
                status_resp = requests.get(
                    f"{_base_url()}/status/{analysis_id}",
                    timeout=10,
                )
                if status_resp.status_code != 200:
                    print(
                        f"\nÉCHEC : GET /status après redémarrage -> "
                        f"{status_resp.status_code} {status_resp.text}"
                    )
                    return 1

                status_data = status_resp.json()
                if status_data.get("status") != "done":
                    print(f"\nÉCHEC : status attendu done, obtenu={status_data}")
                    return 1

                if status_data.get("result") is None:
                    print("\nÉCHEC : result absent après redémarrage")
                    return 1

                if status_data["result"].get("analysis", {}).get("status") != "ok":
                    print("\nÉCHEC : pipeline analysis.status != ok après redémarrage")
                    return 1

                history_resp = requests.get(f"{_base_url()}/history", timeout=10)
                if history_resp.status_code != 200:
                    print(
                        f"\nÉCHEC : GET /history -> "
                        f"{history_resp.status_code} {history_resp.text}"
                    )
                    return 1

                history = history_resp.json()
                ids = [a["analysis_id"] for a in history.get("analyses", [])]
                if analysis_id not in ids:
                    print(f"\nÉCHEC : analysis_id absent de /history : {ids}")
                    return 1

                if history.get("count", 0) < 1:
                    print(f"\nÉCHEC : /history count={history.get('count')}")
                    return 1

                print(
                    f"\nOK : persistance validée — "
                    f"/status/{analysis_id} et /history survivent au redémarrage"
                )
                return 0

            finally:
                _stop_server(proc2)

        finally:
            if proc1 is not None:
                _stop_server(proc1)


if __name__ == "__main__":
    sys.exit(main())
