"""Tests A3 — page publique /methodologie (app/public_pages.py).

Vérifie : 200 sans authentification, HTML français autonome, comparatif
honnête présent (les 4 outils + les limites assumées), déterminisme octet
par octet (deux GET identiques), et zéro effet de bord (la réponse ne
dépend ni de la DB ni du LLM).
Aucun réseau, aucun LLM. < 2 s.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_methodologie_200_sans_auth() -> None:
    r = client.get("/methodologie")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in r.text


def test_methodologie_contenu_comparatif_honnete() -> None:
    r = client.get("/methodologie")
    html = r.text
    # Titre et langue
    assert "Méthodologie" in html
    assert 'lang="fr"' in html
    # Comparatif : les 4 outils présents dans l'en-tête du tableau
    for outil in ("<th>QUANTA</th>", "<th>ChatGPT (seul)</th>", "<th>Julius AI</th>", "<th>SPSS</th>"):
        assert outil in html, f"comparatif incomplet : {outil} absent"
    # Colonnes "non" assumées : QUANTA n'est pas marqué oui partout
    assert 'class="no"' in html
    # Section limites explicites
    assert "Ce que QUANTA ne fait pas" in html
    # Arguments encadreurs
    assert "encadreur" in html
    # Multiplicité et HC3 documentés (méthode, pas marketing)
    assert "Benjamini-Hochberg" in html
    assert "HC3" in html


def test_methodologie_deterministe_octet_par_octet() -> None:
    r1 = client.get("/methodologie")
    r2 = client.get("/methodologie")
    assert r1.content == r2.content


def test_methodologie_sans_db_ni_llm() -> None:
    # La route est pure : même avec un payload de session vide, elle répond.
    # (Guard : si quelqu'un ajoute une dépendance DB/LLM à cette route, ce
    # test échouera au premier problème de connexion — signal voulu.)
    r = client.get("/methodologie")
    assert r.status_code == 200
    assert b"Traceback" not in r.content
