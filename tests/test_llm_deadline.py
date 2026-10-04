"""Tests P0 (pilier crédibilité) : deadline LLM par provider.

Le bug prouvé le 01/10/2026 : le timeout `requests` est par opération
socket et est réarmé par chaque octet keep-alive -> une réponse HTTP 200
« canuleuse » a duré 44,8 s et 72,4 s sans lever Timeout. Ces tests
simulent un serveur qui goutte des octets et vérifient que :
  - _consume_with_deadline coupe la lecture au budget wall-clock ;
  - call_llm n'entame pas de nouvelle tentative une fois le budget du
    provider épuisé (pas de 2e attempt) ;
  - une réponse rapide passe inchangée (non-régression).
Aucun réseau : requests.post est monkeypatché. < 5 s.
"""
from __future__ import annotations

import json
import time

import pytest

import app.llm.brain as brain


class _FakeTrickleResponse:
    """HTTP 200 qui goutte des octets (keep-alive réarmant le read timeout)."""

    status_code = 200

    def __init__(self, n_chunks: int = 50, delay: float = 0.05):
        self._n = n_chunks
        self._delay = delay

    def iter_content(self, chunk_size: int = 2048):
        for _ in range(self._n):
            time.sleep(self._delay)
            yield b"x" * 10

    def close(self):
        pass


def test_consume_with_deadline_cuts_long_trickle():
    resp = _FakeTrickleResponse(n_chunks=50, delay=0.05)  # ~2.5 s au total
    deadline = time.monotonic() + 0.3
    with pytest.raises(brain.requests.exceptions.Timeout):
        brain._consume_with_deadline(resp, deadline, time.monotonic())


def test_consume_fast_response_passes():
    payload = json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()

    class _Fast(_FakeTrickleResponse):
        def iter_content(self, chunk_size: int = 2048):
            yield payload

    body = brain._consume_with_deadline(
        _Fast(), time.monotonic() + 10, time.monotonic()
    )
    assert json.loads(body.decode())["choices"][0]["message"]["content"] == "OK"


def test_call_llm_budget_exhausted_no_second_attempt(monkeypatch):
    calls: list[str] = []

    def fake_post(url, headers=None, json=None, stream=False, timeout=None):
        calls.append(url)
        return _FakeTrickleResponse(n_chunks=50, delay=0.05)

    monkeypatch.setattr(brain.requests, "post", fake_post)
    monkeypatch.setattr(brain, "PROVIDER_TOTAL_BUDGET_SECONDS", 0.3)
    monkeypatch.setattr(brain, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setenv("PRIMARY_API_KEY", "k")
    monkeypatch.setenv("FALLBACK_API_KEY", "")  # pas de provider de secours

    out = brain.call_llm("sys", "user")
    assert out is None
    # budget épuisé après la 1re tentative -> JAMAIS de 2e attempt
    assert len(calls) == 1


def test_call_llm_returns_content_when_fast(monkeypatch):
    payload = json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()

    class _Fast(_FakeTrickleResponse):
        def iter_content(self, chunk_size: int = 2048):
            yield payload

    monkeypatch.setattr(brain.requests, "post", lambda *a, **k: _Fast())
    monkeypatch.setenv("PRIMARY_API_KEY", "k")

    assert brain.call_llm("sys", "user") == "OK"
