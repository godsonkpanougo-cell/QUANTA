#!/usr/bin/env python3
"""
A4 — Smoke test rejouable QUANTA (BROUILLON, non commité).

Vérifie de bout en bout un déploiement QUANTA (Render aujourd'hui, Oracle
Cloud demain) : santé, page publique /methodologie, session, statut et
génération PDF. Le pipeline complet (upload → analyse → rapport) est
OPT-IN car il consomme 1 unité de quota mensuel.

Authentification : QUANTA n'a PAS de login email/mot de passe (Google OAuth
uniquement). Pour les étapes authentifiées, copiez le cookie `session_token`
depuis votre navigateur connecté (DevTools → Application → Cookies →
https://quanta-ijmg.onrender.com) puis :
  - export QUANTA_SMOKE_SESSION_TOKEN=...   (recommandé)
  - ou --session-token ...                  (déconseillé : visible dans l'historique shell)

Usage de base :
  python scripts/smoke_test.py
  python scripts/smoke_test.py --base-url https://mon-backend.oracle.example
  python scripts/smoke_test.py --session-token $QUANTA_SMOKE_SESSION_TOKEN \
      --analysis-id <id>            # test /status + /report sur une analyse existante (sans consommer de quota)
  python scripts/smoke_test.py --session-token ... --with-analyze   # pipeline COMPLET (consomme 1 quota)

Sortie : tableau récapitulatif ; code retour 1 si au moins un échec.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

OK, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[dict] = []


def record(name: str, status: str, duration: float, detail: str = "") -> None:
    results.append({"name": name, "status": status, "duration": duration, "detail": detail})
    flag = {"OK": "ok  ", "FAIL": "ECHEC", "SKIP": "skip"}[status]
    print(f"  [{flag}] {name:<28} {duration:>7.2f} s  {detail}")


def timed_get(url: str, **kwargs) -> tuple[requests.Response, float]:
    t0 = time.perf_counter()
    r = requests.get(url, **kwargs)
    return r, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------

def step_health(base_url: str, timeout: float) -> None:
    try:
        r, dur = timed_get(f"{base_url}/health", timeout=timeout)
        note = ""
        if dur > 20:
            note = "(cold start probable)"
        if r.status_code == 200 and r.json().get("status") == "ok":
            record("GET /health", OK, dur, note)
        else:
            record("GET /health", FAIL, dur, f"HTTP {r.status_code} {r.text[:120]}")
    except requests.RequestException as e:
        record("GET /health", FAIL, 0.0, f"réseau : {e}")


def step_methodologie(base_url: str, timeout: float) -> None:
    try:
        r, dur = timed_get(f"{base_url}/methodologie", timeout=timeout)
        if r.status_code == 200 and "Méthodologie" in r.text:
            record("GET /methodologie", OK, dur)
        else:
            record("GET /methodologie", FAIL, dur, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        record("GET /methodologie", FAIL, 0.0, f"réseau : {e}")


def step_session(base_url: str, token: str | None, timeout: float) -> None:
    if not token:
        record("GET /auth/me", SKIP, 0.0, "pas de session_token fourni")
        record("GET /quota", SKIP, 0.0, "pas de session_token fourni")
        return
    cookies = {"session_token": token}
    try:
        r, dur = timed_get(f"{base_url}/auth/me", cookies=cookies, timeout=timeout)
        if r.status_code == 200:
            record("GET /auth/me", OK, dur, r.json().get("email", ""))
        else:
            record("GET /auth/me", FAIL, dur, f"HTTP {r.status_code} — cookie expiré ?")
    except requests.RequestException as e:
        record("GET /auth/me", FAIL, 0.0, f"réseau : {e}")
        record("GET /quota", SKIP, 0.0, "session invalide")
        return
    try:
        r, dur = timed_get(f"{base_url}/quota", cookies=cookies, timeout=timeout)
        if r.status_code == 200:
            record("GET /quota", OK, dur, str(r.json())[:80])
        else:
            record("GET /quota", FAIL, dur, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        record("GET /quota", FAIL, 0.0, f"réseau : {e}")


def step_status_and_report(
    base_url: str,
    analysis_id: str,
    token: str | None,
    timeout: float,
) -> None:
    if not analysis_id:
        record("GET /status/{id}", SKIP, 0.0, "pas de --analysis-id")
        record("GET /report dark", SKIP, 0.0, "pas de --analysis-id")
        return
    cookies = {"session_token": token} if token else {}
    try:
        r, dur = timed_get(
            f"{base_url}/status/{analysis_id}", cookies=cookies, timeout=timeout
        )
        if r.status_code != 200:
            record("GET /status/{id}", FAIL, dur, f"HTTP {r.status_code}")
        else:
            status = r.json().get("status")
            if status == "done":
                record("GET /status/{id}", OK, dur, "done")
            else:
                record("GET /status/{id}", FAIL, dur, f"statut={status} (attendu done)")
    except requests.RequestException as e:
        record("GET /status/{id}", FAIL, 0.0, f"réseau : {e}")
        record("GET /report dark", SKIP, 0.0, "statut inaccessible")
        return

    try:
        r, dur = timed_get(
            f"{base_url}/report/{analysis_id}?theme=dark",
            cookies=cookies,
            timeout=max(timeout, 120.0),  # 1re génération : 30-60 s possibles
        )
        is_pdf = r.content[:4] == b"%PDF"
        if r.status_code == 200 and is_pdf:
            record("GET /report dark", OK, dur, f"{len(r.content) // 1024} Ko")
        else:
            record(
                "GET /report dark",
                FAIL,
                dur,
                f"HTTP {r.status_code} pdf={is_pdf} {r.text[:100]}",
            )
    except requests.RequestException as e:
        record("GET /report dark", FAIL, 0.0, f"réseau : {e}")


def make_csv_bytes() -> bytes:
    """Dataset déterministe minimal : 2 groupes, 60 lignes."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["groupe", "valeur"])
    for i in range(30):
        w.writerow(["A", round(10.0 + (i % 7) * 0.5, 2)])
        w.writerow(["B", round(13.5 + (i % 5) * 0.4, 2)])
    return buf.getvalue().encode("utf-8")


def step_full_pipeline(
    base_url: str,
    token: str | None,
    timeout: float,
    analyze_timeout: float,
) -> None:
    if not token:
        record("upload→analyze→report", SKIP, 0.0, "pas de session_token (--with-analyze)")
        return
    cookies = {"session_token": token}
    print("  — pipeline complet (consomme 1 quota) —")

    # 1) Upload
    try:
        t0 = time.perf_counter()
        r = requests.post(
            f"{base_url}/upload",
            files={"file": ("smoke_test.csv", make_csv_bytes(), "text/csv")},
            cookies=cookies,
            timeout=timeout,
        )
        dur = time.perf_counter() - t0
        if r.status_code != 200:
            record("POST /upload", FAIL, dur, f"HTTP {r.status_code} {r.text[:120]}")
            return
        file_id = r.json().get("file_id")
        if not file_id:
            record("POST /upload", FAIL, dur, "file_id absent de la réponse")
            return
        record("POST /upload", OK, dur, f"file_id={file_id[:8]}…")
    except requests.RequestException as e:
        record("POST /upload", FAIL, 0.0, f"réseau : {e}")
        return

    # 2) Analyze
    try:
        t0 = time.perf_counter()
        r = requests.post(
            f"{base_url}/analyze",
            json={"file_id": file_id, "query": "Compare la moyenne de valeur entre les deux groupes"},
            cookies=cookies,
            timeout=timeout,
        )
        dur = time.perf_counter() - t0
        if r.status_code != 200:
            record("POST /analyze", FAIL, dur, f"HTTP {r.status_code} {r.text[:120]}")
            return
        analysis_id = r.json().get("analysis_id")
        record("POST /analyze", OK, dur, f"analysis_id={analysis_id[:8]}…")
    except requests.RequestException as e:
        record("POST /analyze", FAIL, 0.0, f"réseau : {e}")
        return

    # 3) Poll /status (on mesure le délai total jusqu'à done/error)
    poll_failures = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < analyze_timeout:
        try:
            r = requests.get(
                f"{base_url}/status/{analysis_id}", cookies=cookies, timeout=timeout
            )
            if r.status_code != 200:
                poll_failures += 1
            else:
                poll_failures = 0
                status = r.json().get("status")
                if status == "done":
                    record("poll /status → done", OK, time.perf_counter() - t0,
                           f"{int(time.perf_counter() - t0)} s au total")
                    break
                if status == "error":
                    record("poll /status → error", FAIL, time.perf_counter() - t0,
                           str(r.json().get("error", ""))[:120])
                    break
        except requests.RequestException:
            poll_failures += 1
        if poll_failures >= 3:
            record("poll /status", FAIL, time.perf_counter() - t0,
                   "3 échecs réseau consécutifs")
            break
        time.sleep(3)
    else:
        record("poll /status", FAIL, analyze_timeout, "timeout analyse")

    # 4) Rapport
    try:
        r, dur = timed_get(
            f"{base_url}/report/{analysis_id}?theme=dark",
            cookies=cookies,
            timeout=max(timeout, 120.0),
        )
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            record("GET /report dark", OK, dur, f"{len(r.content) // 1024} Ko")
        else:
            record("GET /report dark", FAIL, dur, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        record("GET /report dark", FAIL, 0.0, f"réseau : {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Consoles Windows (cp1252) : ne jamais crasher sur un caractère non encodable.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Smoke test QUANTA (A4)")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("QUANTA_SMOKE_BASE_URL", "https://quanta-ijmg.onrender.com"),
        help="URL de l'API à tester (défaut : Render)",
    )
    parser.add_argument(
        "--session-token",
        default=os.environ.get("QUANTA_SMOKE_SESSION_TOKEN"),
        help="cookie session_token (ou env QUANTA_SMOKE_SESSION_TOKEN)",
    )
    parser.add_argument(
        "--analysis-id",
        default=os.environ.get("QUANTA_SMOKE_ANALYSIS_ID"),
        help="analyse 'done' existante : teste /status + /report sans consommer de quota",
    )
    parser.add_argument(
        "--with-analyze",
        action="store_true",
        help="exécute le pipeline COMPLET upload→analyze→report (consomme 1 quota)",
    )
    parser.add_argument("--timeout", type=float, default=90.0,
                        help="timeout HTTP par requête (défaut 90 s — cold start Render)")
    parser.add_argument("--analyze-timeout", type=float, default=300.0,
                        help="délai max du pipeline d'analyse (défaut 300 s)")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    token = args.session_token

    print(f"QUANTA smoke test — cible : {base_url}")
    print(f"Session  : {'fournie' if token else 'absente (étapes authentifiées ignorées)'}")
    if args.with_analyze and not token:
        print("ATTENTION : --with-analyze exige un session_token.\n")

    print("\n— Étapes publiques —")
    step_health(base_url, args.timeout)
    step_methodologie(base_url, args.timeout)

    print("\n— Session —")
    step_session(base_url, token, args.timeout)

    print("\n— Analyse & rapport —")
    step_status_and_report(base_url, args.analysis_id, token, args.timeout)
    if args.with_analyze:
        step_full_pipeline(base_url, token, args.timeout, args.analyze_timeout)

    # Récapitulatif
    print("\n=== RÉCAPITULATIF ===")
    for r in results:
        print(f"  {r['name']:<28} {r['duration']:>7.2f} s  {r['status']:<5} {r['detail']}")
    n_fail = sum(1 for r in results if r["status"] == FAIL)
    n_ok = sum(1 for r in results if r["status"] == OK)
    n_skip = sum(1 for r in results if r["status"] == SKIP)
    print(f"\n  {n_ok} OK · {n_fail} échec(s) · {n_skip} ignoré(s)")

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
